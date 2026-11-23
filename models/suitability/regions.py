"""Canonical boundaries (regions/jordan_adm1.geojson) and the Jordan working grid + governorate raster."""
from __future__ import annotations

import json
import re

import geopandas as gpd
import numpy as np
import rasterio
from rasterio import features
from shapely import set_precision

from . import config
from .grid import Grid, grid_for_bounds, write_tif

SRC = config.RAW / "boundaries" / "geoBoundaries-JOR-ADM1.geojson"
GRID_JSON = config.M1CACHE / "grid_jordan.json"
ADM1_TIF = config.M1CACHE / "adm1_id.tif"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def build_canonical() -> gpd.GeoDataFrame:
    """Write regions/jordan_adm1.geojson (EPSG:4326, RFC 7946, <=6 decimals) from geoBoundaries gbOpen JOR ADM1."""
    gdf = gpd.read_file(SRC).to_crs(4326)
    gdf["region_id"] = ["jo-" + slug(n) for n in gdf["shapeName"]]
    gdf["name"] = gdf["shapeName"]
    gdf["iso"] = gdf["shapeISO"]
    gdf["country"] = "JO"
    gdf["adm1_index"] = np.arange(1, len(gdf) + 1)
    gdf["source"] = "geoBoundaries gbOpen JOR ADM1 (boundaryID JOR-ADM1-50493656; year represented 2006; Wikimedia-derived, coarse)"
    gdf["license"] = "CC BY 2.5 (geoBoundaries gbOpen / Wikimedia Commons)"
    gdf["geometry"] = [set_precision(g, 1e-6) for g in gdf.geometry]
    out = gdf[["region_id", "name", "iso", "country", "adm1_index", "source", "license", "geometry"]]
    config.REGIONS_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    out.to_file(config.REGIONS_GEOJSON, driver="GeoJSON", COORDINATE_PRECISION=6, RFC7946="YES")
    return out


def load_regions() -> gpd.GeoDataFrame:
    return gpd.read_file(config.REGIONS_GEOJSON)


def region_geom(region_id: str):
    g = load_regions()
    r = g[g.region_id == region_id]
    if r.empty:
        raise KeyError(f"unknown region id {region_id!r}; known: {list(g.region_id)}")
    return r.geometry.iloc[0]


def jordan_grid() -> Grid:
    if GRID_JSON.exists():
        return Grid.from_dict(json.loads(GRID_JSON.read_text()))
    g = load_regions().to_crs(config.WORK_CRS)
    grid = grid_for_bounds(tuple(g.total_bounds))
    config.M1CACHE.mkdir(parents=True, exist_ok=True)
    GRID_JSON.write_text(json.dumps(grid.to_dict()))
    return grid


def build_adm1_raster() -> np.ndarray:
    grid = jordan_grid()
    g = load_regions().to_crs(config.WORK_CRS)
    shapes = [(geom, int(i)) for geom, i in zip(g.geometry, g["adm1_index"])]
    arr = features.rasterize(shapes, out_shape=grid.shape, transform=grid.transform, fill=0, dtype="uint8",
                             all_touched=False)
    write_tif(ADM1_TIF, arr, grid, nodata=0, dtype="uint8")
    return arr


def adm1_raster() -> np.ndarray:
    if not ADM1_TIF.exists():
        return build_adm1_raster()
    with rasterio.open(ADM1_TIF) as s:
        return s.read(1)


def region_mask(region_id: str) -> np.ndarray:
    g = load_regions()
    idx = int(g[g.region_id == region_id]["adm1_index"].iloc[0])
    return adm1_raster() == idx


def jordan_bbox_4326(pad: float = 0.05):
    g = load_regions()
    minx, miny, maxx, maxy = g.total_bounds
    return (minx - pad, miny - pad, maxx + pad, maxy + pad)


if __name__ == "__main__":
    config.ensure_dirs()
    g = build_canonical()
    print(g[["region_id", "name", "iso"]])
    grid = jordan_grid()
    print(grid)
    a = build_adm1_raster()
    print("cells per governorate (ha):")
    gg = load_regions()
    for rid, idx in zip(gg.region_id, gg.adm1_index):
        print(rid, int((a == idx).sum()))
