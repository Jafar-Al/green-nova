"""Feature access: flat (cell-wise) loading of stack layers for a domain, ML feature lists, block/fold helpers."""
from __future__ import annotations

import numpy as np
import rasterio

from . import config, rules
from .regions import jordan_grid

STACK = config.M1CACHE / "stack"

TERRAIN = ["elev_mean", "elev_std", "slope_mean", "slope_p90", "slope_frac_gt15", "tpi_1km", "tpi_5km", "relief_5km", "flat_share_5km"]
SOIL = ["ph_0_30", "soc_0_30", "sand_0_30", "silt_0_30", "clay_0_30", "cec_0_30", "bdod_0_30", "cfvo_0_60", "sand_30_100", "clay_30_100"]
SOTWIS = ["sotwis_ec", "sotwis_esp", "sotwis_gypsum", "sotwis_caco3", "sotwis_drainage", "sotwis_awc"]
CLIMATE = ["ppt_annual", "ppt_cv", "pet_annual", "def_annual", "aet_annual", "aridity", "tmax_mean", "tmin_mean", "tmin_coldest",
           "tmax_hottest"]
WATER = ["gsw_occ"]
INTRINSIC = TERRAIN + SOIL + SOTWIS + CLIMATE + WATER + ["awc_ptf"]          # ML 'potential' model: NO vegetation / land-cover
CLIMATE_ONLY = ["ppt_annual", "ppt_cv", "pet_annual", "def_annual", "aridity", "tmax_mean", "tmin_mean", "tmin_coldest",
                "tmax_hottest", "elev_mean"]
RULE_INPUTS = ["slope_mean", "slope_p90", "cfvo_0_60", "sand_0_30", "clay_0_30", "soc_0_30", "cec_0_30", "ph_0_30",
               "sotwis_ec", "sotwis_esp", "sotwis_gypsum", "sotwis_caco3", "sotwis_drainage", "ppt_annual", "tmin_coldest",
               "tmax_hottest"]
SD_LAYERS = ["ph_sd", "soc_sd", "sand_sd", "clay_sd"]


def read_layer(name: str) -> np.ndarray:
    with rasterio.open(STACK / f"{name}.tif") as s:
        return s.read(1)


def domain_index(adm1: np.ndarray | None = None):
    if adm1 is None:
        adm1 = read_layer_path(config.M1CACHE / "adm1_id.tif")
    return np.flatnonzero(adm1.ravel() > 0)


def read_layer_path(p):
    with rasterio.open(p) as s:
        return s.read(1)


def load_cells(names, idx, dtype="float32"):
    """(N, L) matrix of the requested layers at flat cell indices `idx` ('awc_ptf' is derived on the fly)."""
    out = np.empty((len(idx), len(names)), dtype=dtype)
    cache = {}
    for j, n in enumerate(names):
        if n == "awc_ptf":
            for dep in ("sand_0_30", "clay_0_30", "soc_0_30", "cfvo_0_60"):
                if dep not in cache:
                    cache[dep] = read_layer(dep).ravel()[idx]
            out[:, j] = rules.awc_cm_per_m(cache["sand_0_30"], cache["clay_0_30"], cache["soc_0_30"], cache["cfvo_0_60"])
        else:
            out[:, j] = read_layer(n).ravel()[idx]
    return out


def rowcol(idx, width):
    return idx // width, idx % width


def block_ids(idx, width, block_cells=300):
    r, c = rowcol(idx, width)
    return (r // block_cells) * 1000 + (c // block_cells)


def assign_folds(blocks: np.ndarray, k: int, seed: int = 0, stratify_weights: np.ndarray | None = None):
    """Random assignment of whole blocks to k folds (balanced by block count); returns fold id per cell."""
    ub, inv = np.unique(blocks, return_inverse=True)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(ub))
    fold_of = np.empty(len(ub), dtype="int16")
    fold_of[perm] = np.arange(len(ub)) % k
    return fold_of[inv]
