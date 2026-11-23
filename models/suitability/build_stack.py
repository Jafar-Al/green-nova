"""Assemble the analysis-ready covariate stack on the 100 m equal-area Jordan grid (M1CACHE/stack/*.tif).

Adds to what terrain.py / acquire_labels.py / acquire_vectors.py / acquire_s2.py already wrote:
  SoilGrids depth-weighted layers  : ph_0_30, soc_0_30, sand_0_30, silt_0_30, clay_0_30, cec_0_30, bdod_0_30, cfvo_0_60,
                                     sand_30_100, clay_30_100 and 1-sigma uncertainty (Q95-Q05)/3.29 for ph/soc/sand/clay
  climate                          : ppt_annual (WorldClim 1 km), ppt_cv, pet_annual, def_annual, aet_annual, aridity (ppt/pet),
                                     tmax_mean, tmin_mean, tmin_coldest, tmax_hottest (TerraClimate 4 km, lapse-rate
                                     downscaled with the 100 m DEM at -6.5 degC/km)
  gsw_occ                          : JRC surface-water occurrence (max within cell)
Missing SoilGrids cells (e.g. rock/water masks) are nearest-neighbour filled; the filled share is logged.
Run: python -m models.suitability.build_stack
"""
from __future__ import annotations

import json

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
from scipy import ndimage as ndi

from . import config
from .grid import Grid, read_tif, write_tif
from .regions import jordan_grid

STACK = config.M1CACHE / "stack"
SG = config.COV / "soilgrids"
TC = config.COV / "terraclimate"
WC = config.COV / "worldclim_prec"
LAPSE = -6.5e-3     # degC per metre


def to_grid(path, grid: Grid, resampling=Resampling.bilinear, src_nodata=None):
    out = np.full(grid.shape, np.nan, "float32")
    with rasterio.open(path) as s:
        reproject(rasterio.band(s, 1), out, src_nodata=src_nodata if src_nodata is not None else s.nodata,
                  dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=np.nan, resampling=resampling)
    return out


def nn_fill(a: np.ndarray, valid_domain: np.ndarray):
    m = ~np.isfinite(a)
    share = float((m & valid_domain).sum() / max(valid_domain.sum(), 1))
    if m.any():
        idx = ndi.distance_transform_edt(m, return_distances=False, return_indices=True)
        a = a[tuple(idx)]
    return a, share


def wavg(layers, weights):
    w = np.array(weights, "float32")
    acc = np.zeros_like(layers[0]); ws = np.zeros_like(layers[0])
    for l, wi in zip(layers, w):
        v = np.isfinite(l)
        acc += np.where(v, l * wi, 0); ws += np.where(v, wi, 0)
    return np.where(ws > 0, acc / np.maximum(ws, 1e-6), np.nan).astype("float32")


def build():
    grid = jordan_grid()
    domain = read_tif(config.M1CACHE / "adm1_id.tif", 1) > 0
    log = {}
    dem = read_tif(STACK / "elev_mean.tif", 1)

    def put(name, arr, nodata=float("nan")):
        write_tif(STACK / f"{name}.tif", arr.astype("float32"), grid, nodata=nodata, dtype="float32")

    # ------------------------------------------------------------ SOTWIS: fill border cells not covered by the SOTER polygons
    for n in ("sotwis_ec", "sotwis_esp", "sotwis_gypsum", "sotwis_caco3", "sotwis_ph", "sotwis_awc", "sotwis_cfrag", "sotwis_clay",
              "sotwis_sand", "sotwis_silt", "sotwis_bulk", "sotwis_cec", "sotwis_toc"):
        a = read_tif(STACK / f"{n}.tif", 1)
        a, sh = nn_fill(a, domain); log[n] = dict(filled_share=round(sh, 4)); put(n, a)
    dr = read_tif(STACK / "sotwis_drainage.tif", 1).astype("float32")
    dr[dr == 0] = np.nan
    dr, sh = nn_fill(dr, domain); log["sotwis_drainage"] = dict(filled_share=round(sh, 4))
    write_tif(STACK / "sotwis_drainage.tif", dr.astype("uint8"), grid, nodata=0, dtype="uint8")

    # ------------------------------------------------------------ SoilGrids
    def sg(prop, depth, stat="mean"):
        return to_grid(SG / f"{prop}_{depth}_{stat}.tif", grid)

    d3, w3 = ["0-5cm", "5-15cm", "15-30cm"], [5, 10, 15]
    for prop, name in (("phh2o", "ph_0_30"), ("soc", "soc_0_30"), ("sand", "sand_0_30"), ("silt", "silt_0_30"),
                       ("clay", "clay_0_30"), ("cec", "cec_0_30"), ("bdod", "bdod_0_30")):
        a = wavg([sg(prop, d) for d in d3], w3)
        a, sh = nn_fill(a, domain)
        log[name] = dict(filled_share=round(sh, 4))
        put(name, a)
    a = wavg([sg("cfvo", d) for d in d3 + ["30-60cm"]], w3 + [30])
    a, sh = nn_fill(a, domain); log["cfvo_0_60"] = dict(filled_share=round(sh, 4)); put("cfvo_0_60", a)
    for prop in ("sand", "clay"):
        a = wavg([sg(prop, d) for d in ("30-60cm", "60-100cm")], [30, 40])
        a, sh = nn_fill(a, domain); put(f"{prop}_30_100", a)
    for prop, name in (("phh2o", "ph_sd"), ("soc", "soc_sd"), ("sand", "sand_sd"), ("clay", "clay_sd")):
        lo = wavg([sg(prop, d, "Q0.05") for d in d3], w3)
        hi = wavg([sg(prop, d, "Q0.95") for d in d3], w3)
        a, _ = nn_fill(np.maximum(hi - lo, 0) / 3.29, domain)
        put(name, a)

    # ------------------------------------------------------------ climate
    mon = []
    for m in range(1, 13):
        mon.append(to_grid(WC / f"wc2.1_30s_prec_{m:02d}_jordan.tif", grid))
    ppt = np.sum(mon, axis=0)
    ppt, sh = nn_fill(ppt, domain); log["ppt_annual"] = dict(filled_share=round(sh, 4)); put("ppt_annual", ppt)
    for src_name, name in (("ppt_annual_cv", "ppt_cv"), ("pet_annual_mean", "pet_annual"), ("def_annual_mean", "def_annual"),
                           ("aet_annual_mean", "aet_annual")):
        a, _ = nn_fill(to_grid(TC / f"{src_name}.tif", grid), domain); put(name, a)
    pet = read_tif(STACK / "pet_annual.tif", 1)
    put("aridity", ppt / np.maximum(pet, 1.0))
    # lapse-rate downscaling of TerraClimate temperatures with the 100 m DEM
    with rasterio.open(TC / "tmax_mean.tif") as s:
        tc_h, tc_w, tc_tr, tc_crs = s.height, s.width, s.transform, s.crs
    dem_tc = np.full((tc_h, tc_w), np.nan, "float32")
    reproject(np.where(np.isfinite(dem), dem, np.nan).astype("float32"), dem_tc, src_transform=grid.transform,
              src_crs=grid.crs, src_nodata=np.nan, dst_transform=tc_tr, dst_crs=tc_crs, dst_nodata=np.nan,
              resampling=Resampling.average)
    dem_tc_on_grid = np.full(grid.shape, np.nan, "float32")
    reproject(dem_tc, dem_tc_on_grid, src_transform=tc_tr, src_crs=tc_crs, src_nodata=np.nan, dst_transform=grid.transform,
              dst_crs=grid.crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
    dz = np.nan_to_num(dem - dem_tc_on_grid, nan=0.0)
    for src_name, name in (("tmax_mean", "tmax_mean"), ("tmin_mean", "tmin_mean"), ("tmin_coldest_month", "tmin_coldest"),
                           ("tmax_hottest_month", "tmax_hottest")):
        a, _ = nn_fill(to_grid(TC / f"{src_name}.tif", grid), domain)
        put(name, a + LAPSE * dz)

    # ------------------------------------------------------------ water occurrence (max within cell)
    gsw = config.COV / "jrc_gsw" / "gsw_occurrence_jordan_4326.tif"
    if gsw.exists():
        out = np.zeros(grid.shape, "float32")
        with rasterio.open(gsw) as s:
            reproject(rasterio.band(s, 1), out, dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=0,
                      resampling=Resampling.max)
        put("gsw_occ", out)
    (STACK / "build_stack_log.json").write_text(json.dumps(log, indent=1))
    print(json.dumps(log, indent=1))


if __name__ == "__main__":
    config.ensure_dirs()
    build()
