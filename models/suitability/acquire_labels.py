"""Observed land-cover layers used for (a) the cultivation label and (b) exclusion masks: ESA WorldCover (2020 v100,
2021 v200) and Impact Observatory 10 m annual LULC (2017-2023). All read from Planetary Computer COGs (anonymous
signing) and aggregated to per-cell class fractions on the 100 m equal-area grid.

Outputs (M1CACHE/stack/):  wc2021_{crop,built,water,tree,shrub,grass,bare,wetland}.tif, wc2020_crop.tif, io{YYYY}_crop.tif
Run: python -m models.suitability.acquire_labels wc | io
"""
from __future__ import annotations

import argparse
import time
from collections import defaultdict

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds

from . import config, manifest
from .acquire_static import GDAL_ENV, PC_STAC, _stac
from .grid import window_grid, write_tif
from .regions import jordan_bbox_4326, jordan_grid

STACK = config.M1CACHE / "stack"
WC_CLASSES = {"tree": 10, "shrub": 20, "grass": 30, "crop": 40, "built": 50, "bare": 60, "water": 80, "wetland": 90}
IO_YEARS = [2017, 2021, 2023]
IO_CROP = 5


def _signed(href: str) -> str:
    import planetary_computer as pc
    return pc.sign(href.split("?")[0])


def _frac_blocks(grid, read_block, classes: dict, block: int = 500, reopen=None):
    """Generic block loop: read_block(bounds_4326) -> (array uint8, transform, crs) for the block;
    returns dict name->float32 fraction raster on `grid`."""
    out = {k: np.full(grid.shape, np.nan, "float32") for k in classes}
    for r0 in range(0, grid.height, block):
        for c0 in range(0, grid.width, block):
            r1, c1 = min(r0 + block, grid.height), min(c0 + block, grid.width)
            wg = window_grid(grid, r0, r1, c0, c1)
            res = None
            for attempt in range(8):
                try:
                    res = read_block(wg)
                    break
                except Exception as e:  # transient HTTP/strile errors or expired SAS token: re-sign, reopen, retry
                    print("   retry block", r0, c0, attempt, repr(e)[:80], flush=True)
                    time.sleep(4 * (attempt + 1))
                    if reopen:
                        reopen()
            else:
                raise RuntimeError(f"block {r0},{c0} failed after retries")
            if res is None:
                continue
            a, tr, crs = res
            for k, code in classes.items():
                m = (a == code).astype("float32")
                dst = np.full(wg.shape, np.nan, "float32")
                reproject(m, dst, src_transform=tr, src_crs=crs, dst_transform=wg.transform, dst_crs=wg.crs,
                          dst_nodata=np.nan, resampling=Resampling.average)
                out[k][r0:r1, c0:c1] = dst
        print("  rows", r0, flush=True)
    return out


def acquire_worldcover():
    grid = jordan_grid()
    minx, miny, maxx, maxy = jordan_bbox_4326(0.05)
    cat = _stac()
    for year, classes in ((2021, WC_CLASSES), (2020, {"crop": 40})):
        if (STACK / f"wc{year}_crop.tif").exists():
            print("have", year); continue
        items = [i for i in cat.search(collections=["esa-worldcover"], bbox=[minx, miny, maxx, maxy]).items()
                 if i.properties["start_datetime"].startswith(str(year))]
        print(year, len(items), "tiles", flush=True)
        hrefs = [i.assets["map"].href for i in items]
        srcs = [rasterio.open(h) for h in hrefs]

        def reopen():
            for s_ in srcs:
                try: s_.close()
                except Exception: pass
            srcs[:] = [rasterio.open(_signed(h)) for h in hrefs]

        def read_block(wg):
            l, b, r, t = transform_bounds(wg.crs, "EPSG:4326", *wg.bounds)
            pieces = []
            for s in srcs:
                sb = s.bounds
                if r < sb.left or l > sb.right or t < sb.bottom or b > sb.top:
                    continue
                win = from_bounds(max(l, sb.left), max(b, sb.bottom), min(r, sb.right), min(t, sb.top), s.transform)
                win = win.round_offsets().round_lengths()
                a = s.read(1, window=win)
                pieces.append((a, s.window_transform(win)))
            if not pieces:
                return None
            if len(pieces) == 1:
                a, tr = pieces[0]
                return a, tr, "EPSG:4326"
            # block straddles 3-degree tiles: mosaic into a common 10 m array
            px = abs(pieces[0][1].a)
            W = int(round((r - l) / px)) + 2; H = int(round((t - b) / px)) + 2
            from rasterio.transform import from_origin
            tr = from_origin(l, t, px, px)
            mos = np.zeros((H, W), "uint8")
            for a, ptr in pieces:
                c = int(round((ptr.c - l) / px)); rr = int(round((t - ptr.f) / px))
                hh, ww = a.shape
                sl = (slice(max(rr, 0), min(rr + hh, H)), slice(max(c, 0), min(c + ww, W)))
                sub = a[sl[0].start - rr: sl[0].stop - rr, sl[1].start - c: sl[1].stop - c]
                mos[sl] = np.where(sub > 0, sub, mos[sl])
            return mos, tr, "EPSG:4326"

        with rasterio.Env(**GDAL_ENV):
            fr = _frac_blocks(grid, read_block, classes, reopen=reopen)
        for k, arr in fr.items():
            write_tif(STACK / f"wc{year}_{k}.tif", arr, grid, nodata=float("nan"), dtype="float32")
            print(year, k, float(np.nanmean(arr)))
        for s in srcs:
            s.close()
    manifest.add_entry("esa_worldcover_fractions", "https://planetarycomputer.microsoft.com/dataset/esa-worldcover (ESA WorldCover 2020 v100, 2021 v200)",
                       "CC BY 4.0 (ESA WorldCover project / Contains modified Copernicus Sentinel data)",
                       "10 m native; per-cell class fractions on 100 m grid (EPSG:6933)", config.WORK_CRS, tuple(grid.bounds),
                       "2020, 2021", files=[str(p) for p in STACK.glob("wc20*_*.tif")],
                       notes="Class fractions (crop=40, built=50, water=80, tree=10, shrub=20, grass=30, bare=60, wetland=90). Global product accuracy ~74.4% (v100) / 76.7% (v200); lower for cropland in arid zones (not verified for Jordan).")


def acquire_io():
    """IO LULC items are whole UTM zone x latitude-band mosaics (~89000 x 57000 px): read block windows only."""
    from rasterio.warp import transform_bounds as tb
    grid = jordan_grid()
    minx, miny, maxx, maxy = jordan_bbox_4326(0.0)
    cat = _stac()
    for year in IO_YEARS:
        if (STACK / f"io{year}_crop.tif").exists():
            print("have", year); continue
        items = list(cat.search(collections=["io-lulc-annual-v02"], bbox=[minx, miny, maxx, maxy],
                                datetime=f"{year}-01-01/{year}-12-31").items())
        print(year, len(items), "items", flush=True)
        hrefs = [it.assets["data"].href for it in items]
        srcs = [(it, rasterio.open(h)) for it, h in zip(items, hrefs)]

        def reopen():
            for _, s_ in srcs:
                try: s_.close()
                except Exception: pass
            srcs[:] = [(it, rasterio.open(_signed(h))) for it, h in zip(items, hrefs)]

        def read_block(wg):
            l, b, r, t = tb(wg.crs, "EPSG:4326", *wg.bounds)
            for it, s in srcs:
                bb = it.bbox
                if bb[0] <= l and bb[2] >= r and bb[1] <= b and bb[3] >= t:
                    left, bottom, right, top = tb(wg.crs, s.crs, *wg.bounds)
                    win = from_bounds(left, bottom, right, top, s.transform).round_offsets().round_lengths()
                    return s.read(1, window=win, boundless=True, fill_value=0), s.window_transform(win), s.crs
            return None

        with rasterio.Env(**GDAL_ENV):
            fr = _frac_blocks(grid, read_block, {"crop": IO_CROP}, reopen=reopen)
        write_tif(STACK / f"io{year}_crop.tif", fr["crop"], grid, nodata=float("nan"), dtype="float32")
        print(year, "crop frac mean", float(np.nanmean(fr["crop"])), flush=True)
        for _, s in srcs:
            s.close()
    manifest.add_entry("io_lulc_crop_fractions", "https://planetarycomputer.microsoft.com/dataset/io-lulc-annual-v02 (Impact Observatory / Esri 10 m Annual LULC v02)",
                       "CC BY 4.0 (Esri, Impact Observatory, Microsoft)", "10 m native; crop-class (5) fraction per 100 m cell",
                       config.WORK_CRS, tuple(grid.bounds), ",".join(map(str, IO_YEARS)),
                       files=[str(STACK / f"io{y}_crop.tif") for y in IO_YEARS],
                       notes="Deep-learning land-cover product; crop class accuracy in arid regions not verified for Jordan.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["wc", "io"])
    a = ap.parse_args()
    config.ensure_dirs()
    STACK.mkdir(parents=True, exist_ok=True)
    acquire_worldcover() if a.cmd == "wc" else acquire_io()
