"""Point/grid covariate extraction for the soil (ECe, ESP) models.  The SAME code path is used for training points and for region grid cells,
so there is no train/serve feature skew.

Sources (all open; see docs/DATA_SOURCES.md):
  WorldClim 2.1 5-arcmin bioclim (BIO1,4,5,6,12,14,15,17,18)  ~9 km     CC BY 4.0
  WorldClim 2.1 30-arcsec elevation -> elevation, TPI at ~4.5 km and ~20 km, relief (std, ~4.5 km)       ~1 km
  SoilGrids 2.0 aggregated 1 km, 5-15 cm mean: pH(H2O), clay, sand, SOC (CC BY 4.0).  NOTE: SoilGrids was itself trained on WoSIS profiles ->
  using it as a covariate for WoSIS targets leaks some information; the ablation without SoilGrids is reported in the evaluation.
Feature names are fixed in FEATURES (order matters for the saved checkpoints).
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window

from . import config

G = config.CACHE / "model2" / "global"
BIO_ZIP = G / "wc2.1_5m_bio.zip"
ELEV_ZIP = G / "wc2.1_30s_elev.zip"
BIO_DIR = G / "bio5m"
ELEV_TIF = G / "wc2.1_30s_elev.tif"
SG = {"sg_ph": "phh2o", "sg_clay": "clay", "sg_sand": "sand", "sg_soc": "soc"}
BIO_USE = [1, 4, 5, 6, 12, 14, 15, 17, 18]

CLIMATE = [f"bio{i}" for i in BIO_USE] + ["dm_aridity"]
TERRAIN = ["elev", "tpi4", "tpi20", "relief4"]
SOILGRIDS = list(SG)
FEATURES = CLIMATE + TERRAIN + SOILGRIDS
FEATURES_NOSOIL = CLIMATE + TERRAIN


def prepare_global_layers():
    """Unzip the needed WorldClim layers once."""
    BIO_DIR.mkdir(parents=True, exist_ok=True)
    if BIO_ZIP.exists():
        with zipfile.ZipFile(BIO_ZIP) as z:
            for n in z.namelist():
                if n.endswith(".tif") and int(n.rsplit("_", 1)[1].split(".")[0]) in BIO_USE and not (BIO_DIR / Path(n).name).exists():
                    z.extract(n, BIO_DIR)
    if ELEV_ZIP.exists() and not ELEV_TIF.exists():
        try:
            with zipfile.ZipFile(ELEV_ZIP) as z:
                n = [x for x in z.namelist() if x.endswith(".tif")][0]
                z.extract(n, G)
                (G / n).rename(ELEV_TIF)
        except zipfile.BadZipFile:
            pass                                    # still downloading


def _sample_local(path, lon, lat, nodata_fill=np.nan):
    out = np.full(len(lon), nodata_fill, dtype="float32")
    with rasterio.open(path) as s:
        if s.crs.to_string() != "EPSG:4326":
            x, y = Transformer.from_crs(4326, s.crs, always_xy=True).transform(lon, lat)
        else:
            x, y = lon, lat
        vals = np.array([v[0] for v in s.sample(list(zip(x, y)), indexes=1)], dtype="float64")
        nd = s.nodata
        if nd is not None:
            vals = np.where(vals == nd, np.nan, vals)
        out[:] = vals
    return out


def _elev_windows(lon, lat, half=10):
    """elevation + TPI4 (5x5 window) + TPI20 (21x21 window) + relief4 (std 5x5) per point from the 30-arcsec elevation grid."""
    n = len(lon)
    elev = np.full(n, np.nan, "float32"); tpi4 = elev.copy(); tpi20 = elev.copy(); rel4 = elev.copy()
    with rasterio.open(ELEV_TIF) as s:
        inv = ~s.transform
        cols, rows = inv * (np.asarray(lon, dtype="float64"), np.asarray(lat, dtype="float64"))
        cols = np.floor(cols).astype(int)
        rows = np.floor(rows).astype(int)
        order = np.lexsort((cols // 200, rows // 200))          # read spatially coherent points together
        for i in order:
            r, c = rows[i], cols[i]
            if r < half or c < half or r >= s.height - half or c >= s.width - half:
                continue
            w = s.read(1, window=Window(c - half, r - half, 2 * half + 1, 2 * half + 1)).astype("float32")
            if s.nodata is not None:
                w = np.where(w == s.nodata, np.nan, w)
            ctr = w[half, half]
            if np.isnan(ctr):
                continue
            w5 = w[half - 2:half + 3, half - 2:half + 3]
            elev[i] = ctr
            tpi4[i] = ctr - np.nanmean(w5)
            tpi20[i] = ctr - np.nanmean(w)
            rel4[i] = np.nanstd(w5)
    return elev, tpi4, tpi20, rel4


def extract(lon, lat, with_soil: bool = True, with_terrain: bool = True) -> dict:
    """Return dict feature-name -> float32 array for points (lon/lat, EPSG:4326)."""
    lon = np.asarray(lon, dtype="float64"); lat = np.asarray(lat, dtype="float64")
    f = {}
    for i in BIO_USE:
        p = BIO_DIR / f"wc2.1_5m_bio_{i}.tif"
        f[f"bio{i}"] = _sample_local(p, lon, lat)
    f["dm_aridity"] = f["bio12"] / (f["bio1"] + 10.0)                      # De Martonne index; <10 arid, <20 semi-arid (Ma'an ~3-5)
    if with_terrain:
        f["elev"], f["tpi4"], f["tpi20"], f["relief4"] = _elev_windows(lon, lat)
    if with_soil:
        for k, name in SG.items():
            v = _sample_local(G / f"{name}_5-15cm_mean_1000.tif", lon, lat)
            f[k] = {"sg_ph": v / 10.0, "sg_clay": v / 10.0, "sg_sand": v / 10.0, "sg_soc": v / 10.0}[k]   # SoilGrids stores pH*10, g/kg*10 (clay/sand), dg/kg (SOC)
    return f


def matrix(feat: dict, names=FEATURES) -> np.ndarray:
    return np.column_stack([feat[n] for n in names]).astype("float32")
