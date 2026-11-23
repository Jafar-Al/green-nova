"""Terrain derivatives on the 100 m equal-area grid from Copernicus GLO-30 (processed at 25 m, aggregated to 100 m).

Layers (M1CACHE/stack/): elev_mean, elev_std (sub-cell roughness), slope_mean, slope_p90, slope_frac_gt15 (deg),
tpi_1km, tpi_5km (TPI = elev - focal mean), relief_5km (max-min in ~5 km window), flat_share_5km (focal share of cells with
slope_mean<2 deg), twi (topographic wetness index, from D8 flow accumulation on the 100 m DEM; see hydro.py).
Run: python -m models.suitability.terrain
"""
from __future__ import annotations

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
from scipy import ndimage as ndi

from . import config
from .grid import Grid, window_grid, write_tif
from .regions import jordan_grid

STACK = config.M1CACHE / "stack"
DEM = config.COV / "dem_cop30" / "cop30_jordan_4326.tif"


def horn_slope_deg(z: np.ndarray, res: float) -> np.ndarray:
    zp = np.pad(z, 1, mode="edge")
    a, b, c = zp[:-2, :-2], zp[:-2, 1:-1], zp[:-2, 2:]
    d, f = zp[1:-1, :-2], zp[1:-1, 2:]
    g, h, i = zp[2:, :-2], zp[2:, 1:-1], zp[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * res)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * res)
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy))).astype("float32")


def build(strip_rows: int = 200):
    grid = jordan_grid()
    f = int(round(config.RES / config.TERRAIN_RES))            # sub-cells per cell side (4)
    names = ["elev_mean", "elev_std", "slope_mean", "slope_p90", "slope_frac_gt15"]
    out = {n: np.full(grid.shape, np.nan, "float32") for n in names}
    with rasterio.open(DEM) as src:
        for r0 in range(0, grid.height, strip_rows):
            r1 = min(r0 + strip_rows, grid.height)
            hr0, hr1 = max(r0 - 1, 0), min(r1 + 1, grid.height)          # 1-cell halo (4 sub-rows)
            wg = window_grid(grid, hr0, hr1, 0, grid.width).with_res(config.TERRAIN_RES)
            z = np.full(wg.shape, np.nan, "float32")
            reproject(rasterio.band(src, 1), z, src_nodata=-9999.0, dst_transform=wg.transform, dst_crs=wg.crs,
                      dst_nodata=np.nan, resampling=Resampling.bilinear)
            if not np.isfinite(z).any():
                continue
            zf = np.where(np.isfinite(z), z, np.nanmedian(z))
            s = horn_slope_deg(zf, config.TERRAIN_RES)
            s[~np.isfinite(z)] = np.nan
            h, w = z.shape
            zb = z.reshape(h // f, f, w // f, f).transpose(0, 2, 1, 3).reshape(h // f, w // f, f * f)
            sb = s.reshape(h // f, f, w // f, f).transpose(0, 2, 1, 3).reshape(h // f, w // f, f * f)
            with np.errstate(all="ignore"):
                em, es = np.nanmean(zb, 2), np.nanstd(zb, 2)
                sm = np.nanmean(sb, 2)
                ss = np.sort(sb, axis=2)                                   # NaNs sort last
                nv = np.isfinite(sb).sum(2)
                k90 = np.clip(np.round(0.9 * (nv - 1)).astype("int64"), 0, f * f - 1)
                sp = np.take_along_axis(ss, k90[..., None], 2)[..., 0]
                sp = np.where(nv > 0, sp, np.nan)
                sg = np.nanmean(np.where(np.isfinite(sb), sb > 15, np.nan), 2)
            a, b = r0 - hr0, r0 - hr0 + (r1 - r0)
            for n, arr in zip(names, (em, es, sm, sp, sg)):
                out[n][r0:r1] = arr[a:b]
            print("strip", r0, "of", grid.height, flush=True)
    # focal context layers at 100 m
    z = out["elev_mean"]
    zf = np.where(np.isfinite(z), z, np.nanmean(z))
    k1, k5 = 11, 51
    out["tpi_1km"] = (z - ndi.uniform_filter(zf, k1, mode="nearest")).astype("float32")
    out["tpi_5km"] = (z - ndi.uniform_filter(zf, k5, mode="nearest")).astype("float32")
    out["relief_5km"] = (ndi.maximum_filter(zf, k5, mode="nearest") - ndi.minimum_filter(zf, k5, mode="nearest")).astype("float32")
    flat = np.where(np.isfinite(out["slope_mean"]), (out["slope_mean"] < 2).astype("float32"), np.nan)
    out["flat_share_5km"] = ndi.uniform_filter(np.nan_to_num(flat, nan=0.0), k5, mode="nearest").astype("float32")
    for n, arr in out.items():
        arr = arr.astype("float32")
        write_tif(STACK / f"{n}.tif", arr, grid, nodata=float("nan"), dtype="float32")
        print(n, float(np.nanmin(arr)), float(np.nanmean(arr)), float(np.nanmax(arr)))


if __name__ == "__main__":
    config.ensure_dirs()
    STACK.mkdir(parents=True, exist_ok=True)
    build()
