"""Sentinel-2 L2A temporal-statistics layers for Jordan on the 100 m working grid (Planetary Computer, anonymous).

For every MGRS tile intersecting Jordan we read each selected low-cloud scene at ~100 m through the COG overviews
(rasterio decimated read, average resampling), mask clouds with SCL, and compute per-pixel temporal statistics in the
tile's UTM space; the statistics are then warped (bilinear) onto the equal-area grid window and stored per tile.
`mosaic()` merges overlapping tiles (nan-mean) into one GeoTIFF per layer under M1CACHE/stack/.

NOTE on resolution: 10 m / 20 m bands are decimated to 100 m (spectral means of the 10 m pixels, via overviews).
Run:  python -m models.suitability.acquire_s2 run --year 2024 [--max-scenes 30] [--workers 6]
      python -m models.suitability.acquire_s2 mosaic --year 2024
"""
from __future__ import annotations

import argparse
import time
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import reproject, transform_bounds

from . import config, manifest
from .acquire_static import GDAL_ENV, PC_STAC, _stac
from .grid import Grid, window_grid, write_tif
from .regions import jordan_bbox_4326, jordan_grid

BANDS = ["B02", "B03", "B04", "B08", "B11", "B12"]
STAT_NAMES = (["ndvi_p10", "ndvi_p50", "ndvi_p90", "ndvi_max", "ndvi_std", "ndvi_summer", "ndvi_winter",
               "ndmi_p50", "ndmi_p90", "mndwi_p90"]
              + [f"soil_{b.lower()}" for b in BANDS]
              + ["soil_bsi", "soil_si1", "soil_clay", "soil_iron", "soil_nbr2", "soil_bright", "n_valid", "n_bare"])
S2DIR = config.M1CACHE / "s2"


def _offset_scale(item):
    """(scale, offset) to convert DN -> BOA reflectance. PB>=04.00 uses offset -1000."""
    pb = item.properties.get("s2:processing_baseline", "02.14")
    try:
        off = -1000.0 if float(pb) >= 4.0 else 0.0
    except ValueError:
        off = 0.0
    return 1e-4, off * 1e-4


def select_scenes(items, max_scenes: int):
    """Spread scenes across months: take lowest-cloud scenes per month (round-robin) up to max_scenes."""
    by_m = defaultdict(list)
    for it in items:
        by_m[it.datetime.month].append(it)
    for m in by_m:
        by_m[m].sort(key=lambda i: i.properties.get("eo:cloud_cover", 100))
    sel, k = [], 0
    while len(sel) < max_scenes and any(len(v) > k for v in by_m.values()):
        for m in sorted(by_m):
            if len(by_m[m]) > k and len(sel) < max_scenes:
                sel.append(by_m[m][k])
        k += 1
    return sel


def read_scene(item, n_out: int):
    """Return dict(band-> float32 reflectance array (n_out,n_out), 'valid'-> bool, 'month') or None on failure."""
    scale, off = _offset_scale(item)
    out = {}
    try:
        with rasterio.Env(**GDAL_ENV):
            with rasterio.open(item.assets["SCL"].href) as s:
                scl = s.read(1, out_shape=(n_out, n_out), resampling=Resampling.nearest)
            valid = ~np.isin(scl, [0, 1, 8, 9, 10])
            for b in BANDS:
                with rasterio.open(item.assets[b].href) as s:
                    dn = s.read(1, out_shape=(n_out, n_out), resampling=Resampling.average).astype("float32")
                r = dn * scale + off
                r[(dn == 0)] = np.nan
                out[b] = np.clip(r, 0, 1.5)
    except Exception as e:  # noqa
        print("   scene failed", item.id, repr(e)[:120])
        return None
    out["valid"] = valid
    out["month"] = item.datetime.month
    return out


def _nd(a, b):
    with np.errstate(invalid="ignore", divide="ignore"):
        return (a - b) / (a + b)


def tile_stats(scenes):
    T = len(scenes)
    h, w = scenes[0]["B04"].shape
    ndvi = np.full((T, h, w), np.nan, "float32")
    ndmi = np.full_like(ndvi, np.nan)
    mndwi = np.full_like(ndvi, np.nan)
    months = np.array([s["month"] for s in scenes])
    for i, s in enumerate(scenes):
        v = s["valid"] & np.isfinite(s["B04"]) & np.isfinite(s["B08"]) & np.isfinite(s["B11"])
        nd = _nd(s["B08"], s["B04"]); nm = _nd(s["B08"], s["B11"]); mw = _nd(s["B03"], s["B11"])
        ndvi[i] = np.where(v, nd, np.nan); ndmi[i] = np.where(v, nm, np.nan); mndwi[i] = np.where(v, mw, np.nan)
    st = {}
    with np.errstate(all="ignore"):
        p = np.nanpercentile(ndvi, [10, 50, 90], axis=0)
        st["ndvi_p10"], st["ndvi_p50"], st["ndvi_p90"] = p
        st["ndvi_max"] = np.nanmax(ndvi, 0)
        st["ndvi_std"] = np.nanstd(ndvi, 0)
        st["ndvi_summer"] = np.nanmean(ndvi[np.isin(months, [6, 7, 8, 9])], 0) if np.isin(months, [6, 7, 8, 9]).any() else np.full((h, w), np.nan, "float32")
        st["ndvi_winter"] = np.nanmax(ndvi[np.isin(months, [1, 2, 3, 4])], 0) if np.isin(months, [1, 2, 3, 4]).any() else np.full((h, w), np.nan, "float32")
        st["ndmi_p50"] = np.nanpercentile(ndmi, 50, axis=0)
        st["ndmi_p90"] = np.nanpercentile(ndmi, 90, axis=0)
        st["mndwi_p90"] = np.nanpercentile(mndwi, 90, axis=0)
        bare = (ndvi < 0.20) & (mndwi < 0.0)
        for b in BANDS:
            arr = np.stack([s[b] for s in scenes]).astype("float32")
            arr[~bare] = np.nan
            st[f"soil_{b.lower()}"] = np.nanmedian(arr, 0)
        st["n_valid"] = np.isfinite(ndvi).sum(0).astype("float32")
        st["n_bare"] = bare.sum(0).astype("float32")
    g, r, rd, b2, s1, s2, nir = (st["soil_b03"], st["soil_b04"], None, st["soil_b02"], st["soil_b11"], st["soil_b12"], st["soil_b08"])
    with np.errstate(all="ignore"):
        st["soil_bsi"] = _nd(s1 + r, nir + b2)
        st["soil_si1"] = np.sqrt(g * r)
        st["soil_clay"] = s1 / s2
        st["soil_iron"] = r / b2
        st["soil_nbr2"] = _nd(s1, s2)
        st["soil_bright"] = (b2 + g + r + nir + s1 + s2) / 6.0
    return np.stack([st[n].astype("float32") for n in STAT_NAMES])


def warp_tile(stats, tile_tr: Affine, tile_crs, grid: Grid):
    """Warp (L,h,w) tile-space stats to the minimal grid window covering the tile; returns (row0, col0, arr)."""
    h, w = stats.shape[1:]
    left, top = tile_tr * (0, 0)
    right, bottom = tile_tr * (w, h)
    minx, miny, maxx, maxy = transform_bounds(tile_crs, grid.crs, left, bottom, right, top)
    c0 = max(int(np.floor((minx - grid.x0) / grid.res)), 0)
    c1 = min(int(np.ceil((maxx - grid.x0) / grid.res)), grid.width)
    r0 = max(int(np.floor((grid.y0 - maxy) / grid.res)), 0)
    r1 = min(int(np.ceil((grid.y0 - miny) / grid.res)), grid.height)
    if c1 <= c0 or r1 <= r0:
        return None
    wg = window_grid(grid, r0, r1, c0, c1)
    out = np.full((stats.shape[0], wg.height, wg.width), np.nan, "float32")
    for i in range(stats.shape[0]):
        reproject(stats[i], out[i], src_transform=tile_tr, src_crs=tile_crs, src_nodata=np.nan,
                  dst_transform=wg.transform, dst_crs=wg.crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
    return r0, c0, out


def run(year: int, max_scenes: int, workers: int, cloud: float):
    grid = jordan_grid()
    S2DIR.joinpath(str(year)).mkdir(parents=True, exist_ok=True)
    minx, miny, maxx, maxy = jordan_bbox_4326(0.0)
    cat = _stac()
    items = list(cat.search(collections=["sentinel-2-l2a"], bbox=[minx, miny, maxx, maxy],
                            datetime=f"{year}-01-01/{year}-12-31",
                            query={"eo:cloud_cover": {"lt": cloud}}).items())
    by_tile = defaultdict(list)
    for it in items:
        by_tile[it.properties["s2:mgrs_tile"]].append(it)
    print(len(items), "scenes,", len(by_tile), "tiles", flush=True)
    for tile, its in sorted(by_tile.items()):
        out = S2DIR / str(year) / f"{tile}.npz"
        if out.exists():
            continue
        t0 = time.time()
        sel = select_scenes(its, max_scenes)
        crs = sel[0].properties.get("proj:code") or f'EPSG:{sel[0].properties["proj:epsg"]}'
        # tile transform at 100 m from the item's proj:transform (10 m) - scale x10 (same extent)
        pt = sel[0].assets["B04"].extra_fields["proj:transform"]
        shp = sel[0].assets["B04"].extra_fields.get("proj:shape", [10980, 10980])
        a10 = Affine(*pt[:6])
        n_out = int(round(shp[0] * abs(a10.a) / config.RES))
        tr = Affine(config.RES, 0, a10.c, 0, -config.RES, a10.f)
        try:
            with ThreadPoolExecutor(workers) as ex:
                scenes = [s for s in ex.map(lambda it: read_scene(it, n_out), sel) if s is not None]
            if len(scenes) < 6:
                print("tile", tile, "too few scenes", len(scenes)); continue
            st = tile_stats(scenes)
            wr = warp_tile(st, tr, crs, grid)
            if wr is None:
                continue
            r0, c0, arr = wr
            np.savez_compressed(out, r0=r0, c0=c0, arr=arr, names=np.array(STAT_NAMES), n_scenes=len(scenes),
                                dates=np.array([s["month"] for s in scenes]))
            print(f"tile {tile}: {len(scenes)}/{len(its)} scenes, window {arr.shape}, {time.time()-t0:.0f}s", flush=True)
        except Exception:
            traceback.print_exc()


def mosaic(year: int):
    grid = jordan_grid()
    files = sorted((S2DIR / str(year)).glob("*.npz"))
    outdir = config.M1CACHE / "stack"
    outdir.mkdir(parents=True, exist_ok=True)
    for li, name in enumerate(STAT_NAMES):
        acc = np.zeros(grid.shape, "float32"); cnt = np.zeros(grid.shape, "uint8")
        for f in files:
            z = np.load(f)
            r0, c0, a = int(z["r0"]), int(z["c0"]), z["arr"][li]
            v = np.isfinite(a)
            sl = (slice(r0, r0 + a.shape[0]), slice(c0, c0 + a.shape[1]))
            acc[sl] += np.where(v, a, 0); cnt[sl] += v
        with np.errstate(invalid="ignore", divide="ignore"):
            res = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan).astype("float32")
        write_tif(outdir / f"s2_{year}_{name}.tif", res, grid, nodata=float("nan"), dtype="float32")
        print(name, float(np.nanmean(res)))
    manifest.add_entry(f"sentinel2_l2a_stats_{year}", f"{PC_STAC} collection sentinel-2-l2a (Copernicus Sentinel-2 L2A, COG)",
                       "Copernicus Sentinel data free/open (Regulation (EU) No 1159/2013); attribution: contains modified Copernicus Sentinel data",
                       "10/20 m native; decimated to 100 m (EPSG:6933 grid)", config.WORK_CRS, tuple(grid.bounds),
                       f"{year}-01-01/{year}-12-31", files=[str(outdir / f"s2_{year}_{n}.tif") for n in STAT_NAMES],
                       notes="Temporal statistics (NDVI/NDMI/MNDWI percentiles; bare-soil composite reflectance + indices) from cloud-masked low-cloud scenes. Model1-private derived layer on the 100 m equal-area grid.", added_by="model1")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "mosaic"])
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--max-scenes", type=int, default=30)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--cloud", type=float, default=20.0)
    a = ap.parse_args()
    config.ensure_dirs()
    run(a.year, a.max_scenes, a.workers, a.cloud) if a.cmd == "run" else mosaic(a.year)
