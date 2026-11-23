"""Reference evapotranspiration, crop water requirement, leaching requirement, water-harvesting design.  All vectorised (numpy).

Equations (all read in the cited FAO documents, see knowledge/sources.py):
  * ETo (primary) = TerraClimate PET (FAO-56 Penman-Monteith reference ET, Abatzoglou et al. 2018) monthly 1991-2020 normals;
    ETo (cross-check) = Hargreaves, FAO56 eq. 52:  ETo = 0.0023 (Tmean + 17.8) (Tmax - Tmin)^0.5 Ra   [Ra in mm/day equivalent]
  * ETc = Kc ETo  (FAO56), monthly Kc from the crop calendar in knowledge/crops.py (Table 11 stage lengths, Table 12 Kc)
  * Leaching requirement  LR = ECw / (5 ECe - ECw)            (FAO_IDP29 eq. 9; reproduces the worked example: 0.10 and 0.16)
  * Applied water         AW = ETc_net / (1 - LR)             (FAO_IDP29 eq. 7); if application losses exceed LR the extra leaching is free
                          (FAO_IDP29 Example 3) -> gross = max(net/E, net/(1-LR))
  * Water harvesting      C:CA = (WR - DR) / (DR K EFF)       (FAO_WH91 ch.4), K 0.1-0.5, EFF 0.5-0.75, DR = rainfall at 67 % exceedance
Assumed (not read in a source, flagged expert_rule/assumed in outputs): drip application efficiency 0.80-0.92; effective-rainfall fraction 0.5-0.8.
"""
from __future__ import annotations

import numpy as np

DAYS = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], dtype="float64")
MID_DOY = np.array([15, 46, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349], dtype="float64")


# ------------------------------------------------------------------ radiation / Hargreaves (FAO56 eq. 21, 52)
def ra_mm_day(lat_deg, doy):
    """Extra-terrestrial radiation expressed as mm/day evaporation equivalent (FAO56 eq. 21 / 2.45)."""
    lat = np.deg2rad(np.asarray(lat_deg, dtype="float64"))
    doy = np.asarray(doy, dtype="float64")
    dr = 1 + 0.033 * np.cos(2 * np.pi / 365 * doy)
    dec = 0.409 * np.sin(2 * np.pi / 365 * doy - 1.39)
    ws = np.arccos(np.clip(-np.tan(lat) * np.tan(dec), -1, 1))
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (ws * np.sin(lat) * np.sin(dec) + np.cos(lat) * np.cos(dec) * np.sin(ws))
    return ra / 2.45


def eto_hargreaves_monthly(tmin, tmax, lat_deg):
    """tmin/tmax (12, ...) degC, lat (...) -> monthly ETo mm/month, shape (12, ...)."""
    tmean = 0.5 * (tmin + tmax)
    out = np.empty_like(tmin, dtype="float64")
    for m in range(12):
        ra = ra_mm_day(lat_deg, MID_DOY[m])
        out[m] = 0.0023 * (tmean[m] + 17.8) * np.sqrt(np.clip(tmax[m] - tmin[m], 0, None)) * ra * DAYS[m]
    return out


# ------------------------------------------------------------------ crop calendar -> monthly Kc
def monthly_kc(crop) -> np.ndarray:
    """Return (12,) day-weighted mean Kc per calendar month (0 outside the crop's active period)."""
    kc_day = np.zeros(365)
    if crop.evergreen_kc is not None:
        return np.full(12, crop.evergreen_kc)
    ini, mid, end = crop.kc
    Li, Ld, Lm, Ll = crop.stages
    d0 = int(crop.plant_doy) - 1
    seq = np.concatenate([np.full(Li, ini), np.linspace(ini, mid, Ld, endpoint=False) if Ld else [], np.full(Lm, mid),
                          np.linspace(mid, end, Ll) if Ll else []])
    idx = (d0 + np.arange(len(seq))) % 365
    kc_day[idx] = seq
    out = np.empty(12)
    start = 0
    for m in range(12):
        n = int(DAYS[m])
        out[m] = kc_day[start:start + n].mean()
        start += n
    return out


def crop_etc_monthly(crop, eto_m):
    """eto_m (12, ...) mm/month -> ETc (12, ...) mm/month."""
    kc = monthly_kc(crop)
    return eto_m * kc.reshape((12,) + (1,) * (eto_m.ndim - 1))


def net_irrigation_mm(etc_m, ppt_m, peff_frac):
    """Net irrigation requirement (mm/yr) = sum_m max(ETc_m - f*P_m, 0).  peff_frac scalar or broadcastable."""
    return np.clip(etc_m - peff_frac * ppt_m, 0, None).sum(axis=0)


# ------------------------------------------------------------------ leaching / applied water (FAO_IDP29)
def leaching_requirement(ecw, ece_target):
    ecw = np.asarray(ecw, dtype="float64")
    ece_target = np.asarray(ece_target, dtype="float64")
    """LR = ECw/(5 ECe - ECw); np.inf where ECw >= 5 ECe (no leaching fraction can reach the target)."""
    den = 5.0 * ece_target - ecw
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.where(den > 0, ecw / den, np.inf)
    return lr


def gross_water_mm(net_mm, efficiency, lr, lr_cap=0.5):
    """Gross applied water (mm/yr) incl. leaching; inf if LR exceeds `lr_cap` (unmanageable salinity)."""
    lr_c = np.where(np.isfinite(lr), lr, 1.0)
    gross = np.maximum(net_mm / efficiency, net_mm / np.maximum(1 - np.minimum(lr_c, 0.99), 0.01))
    return np.where(lr_c > lr_cap, np.inf, gross)


def steady_state_ece(ecw, lf):
    """Root-zone ECe at steady state from irrigation water ECw and leaching fraction LF (inverse of FAO_IDP29 eq. 9)."""
    lf = np.maximum(lf, 1e-3)
    return ecw * (1.0 + 1.0 / lf) / 5.0


def reclamation_residual_fraction(depth_ratio, k):
    """Fraction of initial salts remaining after leaching with (applied depth / soil depth) = depth_ratio, C/C0 = exp(-k r).
    k is calibrated so that r = 1 removes 70-80 % (continuous ponding) or 80-90 % (intermittent) of salts (FAO_IDP29 ch.2.4.6);
    the exponential form itself is an assumption."""
    return np.exp(-k * depth_ratio)


# ------------------------------------------------------------------ water harvesting (FAO_WH91 ch.4)
def wh_catchment_ratio(wr_mm, design_rain_mm, k_runoff, eff):
    """C:CA = (WR - DR)/(DR * K * EFF). Returns np.inf if DR <= 0 or WR > DR with negligible harvest."""
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(wr_mm <= design_rain_mm, 0.0, (wr_mm - design_rain_mm) / (design_rain_mm * k_runoff * eff))
    return np.where(~np.isfinite(r) | (design_rain_mm <= 1.0), np.inf, r)


def design_rainfall_67(ppt_annual_years):
    """Annual rainfall exceeded in 2 years out of 3 (33rd percentile of the annual series), axis 0 = years."""
    return np.percentile(ppt_annual_years, 33.0, axis=0)
