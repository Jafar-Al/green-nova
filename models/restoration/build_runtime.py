"""Build runtime_data/<region>/stack.npz (development-time; network/raw caches allowed here, NOT at inference).

Run: python -m models.restoration.build_runtime --region jo-maan
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.windows import from_bounds
from scipy.ndimage import uniform_filter

from . import config, features, hydro, soilml, stack

COV = config.COV
SG_DIR = COV / "soilgrids"
DEM = COV / "dem_cop30" / "cop30_jordan_4326.tif"
W = {"0-5cm": 5.0, "5-15cm": 10.0, "15-30cm": 15.0}


def sg_layer(prop: str, grid: stack.Grid, scale: float = 1.0):
    num = np.zeros(grid.shape, "float64")
    den = np.zeros(grid.shape, "float64")
    used = []
    for d, w in W.items():
        p = SG_DIR / f"{prop}_{d}_mean.tif"
        if p.exists():
            a = stack.warp_tif(p, grid, Resampling.bilinear) / scale
            ok = np.isfinite(a)
            num[ok] += w * a[ok]
            den[ok] += w
            used.append(d)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den > 0, num / den, np.nan).astype("float32")
    return out, used


def bdricm(grid: stack.Grid, cache: Path) -> np.ndarray:
    """SoilGrids 2017 absolute depth to bedrock (cm, capped at 200), window read once and cached."""
    tif = cache / f"bdricm_{int(grid.x0)}_{int(grid.y0)}_{grid.width}x{grid.height}.tif"     # one window per governorate grid (a shared name served Ma'an's window to every region)
    if not tif.exists():
        os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="3")
        u = "/vsicurl/https://files.isric.org/soilgrids/former/2017-03-10/data/BDRICM_M_250m_ll.tif"
        from pyproj import Transformer
        lon0, lat0, lon1, lat1 = Transformer.from_crs(grid.crs, 4326, always_xy=True).transform_bounds(grid.x0, grid.y0 - grid.height * grid.res, grid.x0 + grid.width * grid.res, grid.y0)
        with rasterio.open(u) as s:
            w = from_bounds(lon0 - 0.05, lat0 - 0.05, lon1 + 0.05, lat1 + 0.05, s.transform).round_offsets().round_lengths()
            a = s.read(1, window=w).astype("float32")
            a[a == s.nodata] = np.nan
            tr = s.window_transform(w)
        with rasterio.open(tif, "w", driver="GTiff", height=a.shape[0], width=a.shape[1], count=1, dtype="float32", crs="EPSG:4326", transform=tr, nodata=np.nan, compress="deflate") as d:
            d.write(a, 1)
    return stack.warp_tif(tif, grid, Resampling.nearest)


def climate_arrays(region_id: str) -> dict:
    z = np.load(config.M2CACHE / f"tc_{region_id}.npz")
    lat, lon = z["lat"], z["lon"]
    ppt, pet, tmax, tmin = z["ppt"], z["pet"], z["tmax"], z["tmin"]
    ann = z["ppt_annual"]
    extra = {}
    if "aet_annual_y" in z.files:   # locally generated renewable water = annual climatic surplus P - AET (>= 0), mean and year-to-year sd over 2011-2020
        sur = np.clip(ann - z["aet_annual_y"], 0, None)
        extra = dict(water_surplus_mm=sur.mean(0).astype("float32"), water_surplus_sd_mm=sur.std(0).astype("float32"))
    LAT = np.broadcast_to(lat[:, None], ann.shape[1:])
    eto_hg = hydro.eto_hargreaves_monthly(tmin, tmax, LAT[None] if False else LAT)
    return dict(lat=lat, lon=lon, ppt_m=ppt.astype("float32"), eto_m=pet.astype("float32"), p_mean=ann.mean(0).astype("float32"), p67=hydro.design_rainfall_67(ann).astype("float32"),
                p_cv=(ann.std(0) / np.maximum(ann.mean(0), 1e-3)).astype("float32"), tmin_cold=tmin.min(0).astype("float32"), t_mean=(0.5 * (tmin + tmax)).mean(0).astype("float32"),
                eto_hg_annual=eto_hg.sum(0).astype("float32"), eto_pm_annual=pet.sum(0).astype("float32"), ppt_annual=ann.astype("float32"), **extra)


def build(region_id: str = "jo-maan", out_dir: Path | None = None) -> Path:
    t0 = time.time()
    config.ensure_dirs()
    out_dir = Path(out_dir) if out_dir else config.MODEL_DIR / "runtime_data" / region_id
    out_dir.mkdir(parents=True, exist_ok=True)
    grid = stack.make_grid(region_id)
    mask = stack.region_mask(region_id, grid)
    print(f"grid {grid.width}x{grid.height} cells, {int(mask.sum())} in region", flush=True)
    L = {}
    meta = dict(region=region_id, built=time.strftime("%Y-%m-%dT%H:%M:%S"), model_version=config.MODEL_VERSION, layers={})
    # --- terrain
    L["slope_deg"], L["elev_m"] = stack.slope_from_dem(DEM, grid)
    e = np.where(np.isfinite(L["elev_m"]), L["elev_m"], np.nanmean(L["elev_m"]))
    L["tpi5"] = (L["elev_m"] - uniform_filter(e, size=21)).astype("float32")                # 250 m cells x 21 ~ 5 km
    meta["layers"]["slope_deg"] = "Copernicus GLO-30 -> 50 m slope -> 250 m mean (observed)"
    # --- SoilGrids
    for key, prop, scale in (("ph", "phh2o", 1.0), ("soc_pct", "soc", 10.0), ("sand", "sand", 1.0), ("clay", "clay", 1.0), ("silt", "silt", 1.0), ("cfvo", "cfvo", 1.0), ("cec", "cec", 1.0), ("bd", "bdod", 1.0)):
        a, used = sg_layer(prop, grid, scale)
        if np.isfinite(a).sum() == 0:
            print("  WARNING: no SoilGrids data for", prop)
        L[key] = a
        meta["layers"][key] = f"SoilGrids 2.0 {prop} depths {used} weighted to 0-30 cm (ml_predicted, third party)"
    L["depth_cm"] = bdricm(grid, config.M2CACHE)
    meta["layers"]["depth_cm"] = "SoilGrids 2017 BDRICM, capped at 200 cm (ml_predicted, third party)"
    # --- ECe / ESP at 1 km (own models)
    g1 = grid.coarse(4)
    lon1, lat1 = g1.centres_lonlat()
    feat = features.extract(lon1.ravel(), lat1.ravel(), with_soil=True, with_terrain=True)
    for name, outk in (("ece", "ece"), ("esp", "esp")):
        val, lo, hi, pt, sd_t = soilml.predict(name, feat)
        v1 = val.reshape(g1.shape).astype("float32")
        sd1 = sd_t.reshape(g1.shape).astype("float32")
        if name == "ece":
            L["ece"] = stack.upsample_nn(v1, 4)
            L["ece_log10"] = stack.upsample_nn(np.log10(np.maximum(v1, 1e-3)), 4)
            L["ece_lsd"] = stack.upsample_nn(sd1 / np.log(10.0) * 1.0 if False else sd1, 4)
        else:
            L["esp"] = stack.upsample_nn(v1, 4)
            # conformal half-width is in log1p units: convert to an approximate sd in % at the predicted level
            L["esp_sd"] = stack.upsample_nn((np.expm1(pt.reshape(g1.shape) + sd_t.reshape(g1.shape)) - np.expm1(pt.reshape(g1.shape) - sd_t.reshape(g1.shape))).astype("float32") / 2.0, 4)
        meta["layers"][outk] = f"own LightGBM ({name}) on 1 km features, replicated to 250 m grid (effective resolution 1 km; ml_predicted)"
    # mask outside region
    for k in L:
        L[k] = np.where(mask, L[k], np.nan).astype("float32")
    clim = climate_arrays(region_id)
    meta["climate"] = "TerraClimate 2011-2020 monthly climatology (ppt, pet = FAO-56 PM ETo), annual rainfall series for design rainfall (33rd percentile), native ~4 km"
    meta["effective_resolution_m"] = config.EFFECTIVE_RESOLUTION_M
    path = out_dir / "stack.npz"
    stack.save_stack(path, grid, mask, L, {k: v for k, v in clim.items()}, meta)
    (out_dir / "stack_meta.json").write_text(json.dumps(meta, indent=1))
    print(f"saved {path.name} {path.stat().st_size / 1e6:.1f} MB in {time.time() - t0:.0f}s", flush=True)
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="jo-maan")
    a = ap.parse_args()
    build(a.region)
