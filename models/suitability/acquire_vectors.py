"""Vector sources -> grid rasters: (1) SOTWIS Jordan soil map units (ISRIC, 1:500 000, 47 polygons) -> soil attribute
rasters incl. EC/ESP/gypsum/CaCO3; (2) OSM (Geofabrik extract) restriction masks -> `restriction_code` raster.

restriction_code (uint8): 0 none | 1 protected area | 2 military | 3 quarry/mining | 4 cemetery | 5 built-up
                          6 airport/airfield | 7 surface water | 8 archaeological/heritage site
Run: python -m models.suitability.acquire_vectors sotwis | osm
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio import features

from . import config, manifest
from .grid import write_tif
from .regions import jordan_bbox_4326, jordan_grid

SOT = config.RAW / "sotwis_jo" / "x" / "SOTWIS_JO" / "GIS" / "SOTWIS"
OSMD = config.RAW / "osm_jordan" / "x"
STACK = config.M1CACHE / "stack"

SOT_ATTRS = {  # field -> (layer name, unit)  (units per SOTWIS v1.0 / ISRIC Report 2003/04; verified in handoff)
    "ELCO": ("sotwis_ec", "dS/m (saturated paste)"), "ESP": ("sotwis_esp", "%"), "GYPS": ("sotwis_gypsum", "g/kg"),
    "TCEQ": ("sotwis_caco3", "g/kg"), "PHAQ": ("sotwis_ph", "pH (H2O)"), "TAWC": ("sotwis_awc", "cm/m"),
    "CFRAG": ("sotwis_cfrag", "vol%"), "CLPC": ("sotwis_clay", "%"), "SDTO": ("sotwis_sand", "%"),
    "STPC": ("sotwis_silt", "%"), "BULK": ("sotwis_bulk", "g/cm3"), "CECS": ("sotwis_cec", "cmol(c)/kg"),
    "TOTC": ("sotwis_toc", "g/kg"),
}
DRAIN_ORD = {"V": 1, "P": 2, "I": 3, "M": 4, "W": 5, "S": 6, "E": 7}   # FAO drainage classes (very poor .. excessive)


def acquire_sotwis():
    grid = jordan_grid()
    par = gpd.read_file(SOT / "SOTWIS_0-20cm_parametersestimates" / "JO_SOTWISv1_t1s1d1.shp")
    comp = gpd.read_file(SOT / "SOTWIS_soterunitcomposition" / "JO_SOTWISv1_soterunitcomposition.shp")
    ter = gpd.read_file(SOT / "SOTWIS_terrainproperties" / "JO_SOTWISv1_terrainproperties.shp")
    print(par.crs, par.total_bounds)
    if par.crs is None:
        par = par.set_crs(4326)
    par = par.to_crs(config.WORK_CRS)
    for c in list(SOT_ATTRS) + ["DRAIN"]:
        if c in par.columns and c != "DRAIN":
            par[c] = np.asarray(par[c], dtype="float64")
    meta = {}
    for fld, (name, unit) in SOT_ATTRS.items():
        shapes = [(g, float(v)) for g, v in zip(par.geometry, par[fld]) if g is not None and np.isfinite(v) and v >= 0]
        arr = features.rasterize(shapes, out_shape=grid.shape, transform=grid.transform, fill=np.nan, dtype="float32")
        write_tif(STACK / f"{name}.tif", arr, grid, nodata=float("nan"), dtype="float32", units=unit)
        meta[name] = dict(field=fld, unit=unit, min=float(np.nanmin(arr)), max=float(np.nanmax(arr)), mean=float(np.nanmean(arr)))
    dr = [(g, DRAIN_ORD.get(str(v).strip()[:1].upper(), 0)) for g, v in zip(par.geometry, par["DRAIN"])]
    arr = features.rasterize([(g, v) for g, v in dr if v > 0], out_shape=grid.shape, transform=grid.transform, fill=0, dtype="uint8")
    write_tif(STACK / "sotwis_drainage.tif", arr, grid, nodata=0, dtype="uint8", scale="1 very poor .. 7 excessive (FAO)")
    # dominant FAO soil group (categorical) + landform/slope class for explanations
    comp = comp.set_crs(par.crs) if comp.crs is None else comp
    dom = {str(v): i + 1 for i, v in enumerate(sorted(set(comp["DomFAOgrou"].astype(str))))}
    shapes = [(g, dom[str(v)]) for g, v in zip(comp.to_crs(config.WORK_CRS).geometry, comp["DomFAOgrou"])]
    arr = features.rasterize(shapes, out_shape=grid.shape, transform=grid.transform, fill=0, dtype="uint8")
    write_tif(STACK / "sotwis_domsoil.tif", arr, grid, nodata=0, dtype="uint8")
    (STACK / "sotwis_domsoil_legend.json").write_text(json.dumps({v: k for k, v in dom.items()}, indent=1))
    (STACK / "sotwis_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta, indent=1))
    manifest.add_entry("sotwis_jordan", "https://files.isric.org/public/sotwis/SOTWIS_JO.zip (ISRIC data hub record 943d57ef-1eaf-4528-8508-9c81c1c2fcd3)",
                       "Data hub: CC BY 3.0. NOTE: the zip's metadata states ISRIC materials are for educational/non-commercial use and commercial reuse needs ISRIC permission - conflict flagged; attribute ISRIC (Batjes 2006).",
                       "1:500 000 SOTER map units (47 polygons); topsoil 0-20 cm dominant soil", config.WORK_CRS, tuple(grid.bounds), "v1.0 2013 (source survey 1996)",
                       files=[str(p) for p in STACK.glob("sotwis_*")], notes="EC, ESP, gypsum, CaCO3 etc. per SOTER unit rasterised to 100 m grid. EXPERT/legacy survey, not per-pixel measurements.")


OSM_RULES = [  # (code, shapefile, fclass list or None for all)
    (1, "gis_osm_protected_areas_a_free_1.shp", None),
    (2, "gis_osm_landuse_a_free_1.shp", ["military"]),
    (3, "gis_osm_landuse_a_free_1.shp", ["quarry"]),
    (4, "gis_osm_landuse_a_free_1.shp", ["cemetery"]),
    (5, "gis_osm_landuse_a_free_1.shp", ["residential", "industrial", "commercial", "retail"]),
    (6, "gis_osm_transport_a_free_1.shp", ["airport", "airfield", "apron", "runway", "helipad"]),
    (7, "gis_osm_water_a_free_1.shp", None),
    (8, "gis_osm_pois_a_free_1.shp", ["archaeological", "ruins", "castle", "monument", "memorial", "fort"]),
]
CODE_NAMES = {1: "protected_area", 2: "military_area", 3: "quarry_mining", 4: "cemetery", 5: "built_up", 6: "airport_airfield",
              7: "surface_water", 8: "archaeological_heritage"}


def acquire_osm():
    grid = jordan_grid()
    out = np.zeros(grid.shape, "uint8")
    stats = {}
    for code in [7, 6, 4, 3, 5, 8, 2, 1]:       # later writes win -> protected area has highest priority
        for c, shp, fcl in [r for r in OSM_RULES if r[0] == code]:
            g = gpd.read_file(OSMD / shp)
            if fcl is not None and "fclass" in g.columns:
                g = g[g["fclass"].isin(fcl)]
            g = g[g.geometry.notna()]
            g = g.to_crs(config.WORK_CRS)
            if code == 1:      # OSM object 1073421633 (129,639 km2 > Jordan's area) is a mapping artefact: drop implausible polygons
                big = g.geometry.area / 1e6 > 3000
                stats["protected_area_dropped_implausible_polygons"] = dict(osm_ids=[int(i) for i in g.loc[big, "osm_id"]],
                                                                            km2=[round(float(a), 0) for a in g.geometry.area[big] / 1e6])
                g = g[~big]
            if code == 8:                       # heritage sites are often mapped as small polygons: buffer 100 m
                g["geometry"] = g.geometry.buffer(100)
            if len(g) == 0:
                stats[CODE_NAMES[code]] = 0
                continue
            m = features.rasterize([(geom, 1) for geom in g.geometry], out_shape=grid.shape, transform=grid.transform,
                                   fill=0, dtype="uint8", all_touched=True)
            out[m == 1] = code
            stats[CODE_NAMES[code]] = dict(features=int(len(g)), cells=int(m.sum()))
    write_tif(STACK / "restriction_code.tif", out, grid, nodata=0, dtype="uint8")
    (STACK / "restriction_code_meta.json").write_text(json.dumps({"codes": CODE_NAMES, "stats": stats}, indent=1))
    print(json.dumps(stats, indent=1))
    manifest.add_entry("osm_restrictions_jordan", "https://download.geofabrik.de/asia/jordan-latest-free.shp.zip (OpenStreetMap extract 2026-11-21)",
                       "ODbL 1.0 (c) OpenStreetMap contributors", "vector (mapping accuracy varies); rasterised to 100 m grid", config.WORK_CRS,
                       tuple(grid.bounds), "2026-11-21", files=[str(STACK / "restriction_code.tif")],
                       notes="Protected areas, military, quarries, cemeteries, built-up landuse, airports, water, heritage sites. Crowd-sourced and incomplete: NOT the WDPA / official cadastre. WDPA download requires terms acceptance at protectedplanet.net and was not used.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sotwis", "osm"])
    a = ap.parse_args()
    config.ensure_dirs()
    STACK.mkdir(parents=True, exist_ok=True)
    acquire_sotwis() if a.cmd == "sotwis" else acquire_osm()
