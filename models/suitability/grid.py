"""Working-grid definition and raster -> grid resampling helpers (EPSG:6933 equal-area, RES metres)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, reproject

from . import config


@dataclass(frozen=True)
class Grid:
    crs: str
    res: float
    x0: float   # west edge
    y0: float   # north edge
    width: int
    height: int

    @property
    def transform(self) -> Affine:
        return from_origin(self.x0, self.y0, self.res, self.res)

    @property
    def shape(self):
        return (self.height, self.width)

    @property
    def bounds(self):
        return (self.x0, self.y0 - self.height * self.res, self.x0 + self.width * self.res, self.y0)

    def with_res(self, res: float) -> "Grid":
        f = self.res / res
        assert abs(f - round(f)) < 1e-9 or abs(1 / f - round(1 / f)) < 1e-9, "res must divide/multiply grid res"
        return Grid(self.crs, res, self.x0, self.y0, int(round(self.width * f)), int(round(self.height * f)))

    def to_dict(self):
        return dict(crs=self.crs, res=self.res, x0=self.x0, y0=self.y0, width=self.width, height=self.height)

    @staticmethod
    def from_dict(d):
        return Grid(**d)


def grid_for_bounds(bounds_6933, res: float = config.RES, pad: float = 2000.0, crs: str = config.WORK_CRS) -> Grid:
    """Snap bounds (minx,miny,maxx,maxy in WORK_CRS) outward to multiples of 10*res so grids nest cleanly."""
    snap = res * 10
    minx, miny, maxx, maxy = bounds_6933
    minx = np.floor((minx - pad) / snap) * snap
    miny = np.floor((miny - pad) / snap) * snap
    maxx = np.ceil((maxx + pad) / snap) * snap
    maxy = np.ceil((maxy + pad) / snap) * snap
    return Grid(crs, res, float(minx), float(maxy), int((maxx - minx) / res), int((maxy - miny) / res))


def window_grid(grid: Grid, row0: int, row1: int, col0: int, col1: int) -> Grid:
    return Grid(grid.crs, grid.res, grid.x0 + col0 * grid.res, grid.y0 - row0 * grid.res, col1 - col0, row1 - row0)


def warp_to_grid(src_arr: np.ndarray, src_transform, src_crs, grid: Grid, resampling=Resampling.bilinear,
                 src_nodata=None, dst_nodata=np.nan, dtype="float32") -> np.ndarray:
    dst = np.full(grid.shape, dst_nodata, dtype=dtype)
    reproject(source=src_arr, destination=dst, src_transform=src_transform, src_crs=src_crs,
              src_nodata=src_nodata, dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=dst_nodata,
              resampling=resampling)
    return dst


def write_tif(path, arr: np.ndarray, grid: Grid, nodata=None, dtype=None, cog: bool = False, **tags):
    """Write a (H,W) or (B,H,W) array on the grid. Tiled+deflate; optional COG overviews."""
    arr = np.asarray(arr)
    if arr.ndim == 2:
        arr = arr[None]
    dtype = dtype or str(arr.dtype)
    prof = dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=arr.shape[0], dtype=dtype,
                crs=grid.crs, transform=grid.transform, nodata=nodata, tiled=True, blockxsize=256, blockysize=256,
                compress="deflate", predictor=2 if np.issubdtype(np.dtype(dtype), np.integer) else 3, BIGTIFF="IF_SAFER")
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(arr.astype(dtype))
        if tags:
            dst.update_tags(**{k: str(v) for k, v in tags.items()})
        if cog:
            factors = [2, 4, 8, 16, 32]
            dst.build_overviews(factors, Resampling.nearest if "int" in dtype else Resampling.average)
            dst.update_tags(ns="rio_overview", resampling="nearest" if "int" in dtype else "average")


def read_tif(path, band: int | None = None, masked: bool = False):
    with rasterio.open(path) as src:
        a = src.read(band) if band else src.read()
        if masked:
            nd = src.nodata
            if nd is not None:
                a = np.where(a == nd, np.nan, a.astype("float32")) if not np.isnan(nd) else a
        return a


def cell_xy(grid: Grid, rows: np.ndarray, cols: np.ndarray):
    x = grid.x0 + (cols + 0.5) * grid.res
    y = grid.y0 - (rows + 0.5) * grid.res
    return x, y
