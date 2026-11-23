"""Region covariate stack on the 250 m equal-area working grid (EPSG:6933), built ONCE (development time, network allowed) and shipped as
runtime_data/<region>/stack.npz so that inference needs no network and no raw data.

Layers (grid arrays unless noted)                                      native resolution        evidence
  ph, soc_pct, sand, clay, silt, cfvo, bd, cec  (0-30 cm weighted)     SoilGrids 2.0 250 m      ml_predicted (third party)
  depth_cm                                                             SoilGrids 2017 BDRICM 250 m (capped at 200 cm)   ml_predicted (third party)
  ece, ece_lsd                                                          own LightGBM, 1 km       ml_predicted
  esp, esp_sd                                                           own LightGBM, 1 km       ml_predicted
  slope_deg, elev_m                                                     Copernicus GLO-30 -> 50 m slope -> 250 m mean     observed (remote-sensing DEM)
  climate (native 1/24 deg arrays): ppt_m, eto_m (TerraClimate PM-ETo), ppt_annual (30 y), tmin_cold  ~4 km      observed (gridded climate product)
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio import features as rfeatures
from rasterio.enums import Resampling
from rasterio.transform import Affine, from_origin
from rasterio.warp import reproject, transform_bounds

from . import config


@dataclass(frozen=True)
class Grid:
    crs: str
    res: float
    x0: float
    y0: float
    width: int
    height: int

    @property
    def transform(self) -> Affine:
        return from_origin(self.x0, self.y0, self.res, self.res)

    @property
    def shape(self):
        return (self.height, self.width)

    def to_dict(self):
        return dict(crs=self.crs, res=self.res, x0=self.x0, y0=self.y0, width=self.width, height=self.height)

    def coarse(self, f: int):
        assert self.width % f == 0 and self.height % f == 0
        return Grid(self.crs, self.res * f, self.x0, self.y0, self.width // f, self.height // f)

    def centres_xy(self):
        xs = self.x0 + (np.arange(self.width) + 0.5) * self.res
        ys = self.y0 - (np.arange(self.height) + 0.5) * self.res
        return np.meshgrid(xs, ys)

    def centres_lonlat(self):
        X, Y = self.centres_xy()
        lon, lat = Transformer.from_crs(self.crs, 4326, always_xy=True).transform(X, Y)
        return lon, lat


def region_geometry(region_id: str):
    import geopandas as gpd
    if config.REGIONS_GEOJSON.exists():
        g = gpd.read_file(config.REGIONS_GEOJSON)
        r = g[g["region_id"] == region_id]
        if len(r):
            return r.to_crs(4326).geometry.iloc[0]
    from shapely.geometry import box
    return box(*config.REGIONS[region_id]["bbox_4326_fallback"])


def make_grid(region_id: str, res: float = config.RES) -> Grid:
    geom = region_geometry(region_id)
    minx, miny, maxx, maxy = transform_bounds(4326, config.WORK_CRS, *geom.bounds)
    snap = 4000.0           # multiple of 1 km and 250 m; keeps 1 km / 4 km coarse grids nested
    minx = np.floor((minx - 1000) / snap) * snap
    miny = np.floor((miny - 1000) / snap) * snap
    maxx = np.ceil((maxx + 1000) / snap) * snap
    maxy = np.ceil((maxy + 1000) / snap) * snap
    return Grid(config.WORK_CRS, res, float(minx), float(maxy), int((maxx - minx) / res), int((maxy - miny) / res))


def region_mask(region_id: str, grid: Grid) -> np.ndarray:
    import geopandas as gpd
    geom = gpd.GeoSeries([region_geometry(region_id)], crs=4326).to_crs(grid.crs).iloc[0]
    return rfeatures.rasterize([(geom, 1)], out_shape=grid.shape, transform=grid.transform, fill=0, dtype="uint8").astype(bool)


def warp_tif(path, grid: Grid, resampling=Resampling.bilinear, scale: float = 1.0, band: int = 1):
    dst = np.full(grid.shape, np.nan, dtype="float32")
    with rasterio.open(path) as s:
        src = s.read(band).astype("float32")
        nd = s.nodata
        if nd is not None and not np.isnan(nd):
            src = np.where(src == nd, np.nan, src)
        reproject(src, dst, src_transform=s.transform, src_crs=s.crs, dst_transform=grid.transform, dst_crs=grid.crs, src_nodata=np.nan, dst_nodata=np.nan, resampling=resampling)
    return dst / scale


def slope_from_dem(dem_path, grid: Grid, work_res: float = 50.0):
    """Slope (deg) computed from the 30 m DEM resampled to 50 m (exact divisor of the 250 m grid), mean-aggregated to the grid; also mean elevation."""
    f = int(round(grid.res / work_res))
    H, W = grid.height * f, grid.width * f
    tr = from_origin(grid.x0, grid.y0, work_res, work_res)
    dem = np.full((H, W), np.nan, "float32")
    with rasterio.open(dem_path) as s:
        reproject(rasterio.band(s, 1), dem, dst_transform=tr, dst_crs=grid.crs, src_nodata=s.nodata, dst_nodata=np.nan, resampling=Resampling.bilinear)
    gy, gx = np.gradient(dem, work_res)
    slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")
    slope_a = np.nanmean(slope.reshape(grid.height, f, grid.width, f), axis=(1, 3))
    elev_a = np.nanmean(dem.reshape(grid.height, f, grid.width, f), axis=(1, 3))
    return slope_a.astype("float32"), elev_a.astype("float32")


def upsample_nn(a: np.ndarray, f: int) -> np.ndarray:
    return np.kron(a, np.ones((f, f), dtype=a.dtype))


def save_stack(path, grid: Grid, mask: np.ndarray, layers: dict, climate: dict, meta: dict):
    np.savez_compressed(path, grid=json.dumps(grid.to_dict()), mask=np.packbits(mask.astype(np.uint8)), mask_shape=np.array(mask.shape),
                        meta=json.dumps(meta), **{f"L_{k}": v.astype("float32") for k, v in layers.items()}, **{f"C_{k}": v for k, v in climate.items()})


def load_stack(path):
    z = np.load(path, allow_pickle=False)
    grid = Grid(**json.loads(str(z["grid"])))
    shape = tuple(z["mask_shape"])
    mask = np.unpackbits(z["mask"])[: shape[0] * shape[1]].reshape(shape).astype(bool)
    layers = {k[2:]: z[k] for k in z.files if k.startswith("L_")}
    climate = {k[2:]: z[k] for k in z.files if k.startswith("C_")}
    return grid, mask, layers, climate, json.loads(str(z["meta"]))
