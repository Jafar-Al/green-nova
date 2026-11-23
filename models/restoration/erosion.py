"""Relative water-erosion risk index (RUSLE-type structure).  evidence = expert_rule.  NOT a calibrated soil-loss prediction.

A_rel = R_rel * K * LS   with
  R_rel = (P / 300 mm)^1.61        shape of the Renard & Freimund (1994) annual-rainfall power law, normalised to 300 mm (coefficients of the paper were NOT
                                   verified here -> only the relative shape is used; hyper-arid Ma'an is far below the fitted rainfall range: low confidence)
  K     = EPIC erodibility (Williams 1995) as transcribed in the SWAT+ documentation (SWATPLUS_K, read), x 0.1317 to SI (t ha h / (ha MJ mm))
  LS    = USLE slope-length/steepness (Wischmeier & Smith 1978 metric form, slope length lambda = 100 m assumed; standard formula, not re-read here)
index = 1 - exp(-A_rel / A0) in [0,1]  (A0 chosen so that a 15 degree bare loam slope at 300 mm gives ~0.9: relative ranking only)
Hyper-arid desert erosion is dominated by wind and flash floods that this index does not capture (stated in residual_risks).
"""
from __future__ import annotations

import numpy as np

SLOPE_LENGTH_M = 100.0


def k_epic(sand, silt, clay, soc_pct):
    """EPIC K factor, SI units (t ha h ha-1 MJ-1 mm-1). Inputs in % (soc in % organic carbon)."""
    sand = np.clip(sand, 0, 100)
    silt = np.clip(silt, 0, 100)
    clay = np.clip(clay, 0, 100)
    soc = np.clip(soc_pct, 0, 20)
    f_csand = 0.2 + 0.3 * np.exp(-0.256 * sand * (1 - silt / 100.0))
    f_clsi = (silt / np.maximum(clay + silt, 1e-6)) ** 0.3
    f_orgc = 1 - 0.25 * soc / (soc + np.exp(3.72 - 2.95 * soc))
    sn = 1 - sand / 100.0
    f_hisand = 1 - 0.7 * sn / (sn + np.exp(-5.51 + 22.9 * sn))
    return f_csand * f_clsi * f_orgc * f_hisand * 0.1317


def ls_factor(slope_deg, length_m=SLOPE_LENGTH_M):
    th = np.deg2rad(np.clip(slope_deg, 0.05, 60))
    s = np.tan(th) * 100.0                      # percent
    m = np.where(s >= 5, 0.5, np.where(s >= 3, 0.4, np.where(s >= 1, 0.3, 0.2)))
    return (length_m / 22.13) ** m * (65.41 * np.sin(th) ** 2 + 4.56 * np.sin(th) + 0.065)


def erosion_index(slope_deg, sand, silt, clay, soc_pct, p_mm, terraced=False, conservation_factor=1.0):
    """Return (index in [0,1], A_rel).  conservation_factor multiplies A_rel (terracing/contouring/cover; scenario parameter)."""
    r_rel = (np.maximum(p_mm, 5.0) / 300.0) ** 1.61
    a_rel = r_rel * k_epic(sand, silt, clay, soc_pct) * ls_factor(np.where(terraced, 3.0, slope_deg)) * conservation_factor
    a0 = 0.035 * (300.0 / 300.0) ** 1.61 * ls_factor(15.0)      # reference: loam (K~0.035 SI), 15 deg, 300 mm
    return 1 - np.exp(-a_rel / (a0 / 2.3)), a_rel
