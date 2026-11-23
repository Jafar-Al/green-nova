"""FAO-style land evaluation rule engine (EXPERT/RULE-DERIVED, never field-verified).

Method (adapted from FAO Framework for Land Evaluation 1976, FAO Soils Bulletin 55 (1985) irrigated-agriculture critical
limits, Sys et al. 1991 parametric rating, USDA salinity classes; thresholds below are crop-agnostic expert settings for
"irrigated or supplementary-irrigated annual/perennial crops under modern management", NOT crop-specific and NOT calibrated
to Jordanian yield data):

  1. each land quality gets a rating R in [0,100] by a piecewise-linear curve whose knots sit on the classic class borders
        R>=85 S1 (sev 0) | 60-85 S2 (sev 1) | 40-60 S3 (sev 2) | 25-40 N1 (sev 3) | <25 N2 (sev 4)
  2. limiting-factor law decides the class:
        restricted (legal/environmental)                                     -> class 5
        any *irreversible* factor at sev 4 (steepness, stoniness, hyper-aridity, gypsic, temperature) -> class 4
        any other factor at sev >=3, or >=3 factors at sev >=2               -> class 3 (reclaimable limitation)
        any factor at sev >=2, or >=2 factors at sev >=1                     -> class 2
        otherwise                                                            -> class 1
  3. a continuous index (Sys square-root: Rmin * prod_other (R/100)^0.5) is kept for ranking / baseline AUC.
Everything is vectorised numpy; inputs are arrays (any shape) keyed by covariate name.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SEV_EDGES = np.array([85.0, 60.0, 40.0, 25.0])      # R >= edge[i] -> sev i ; R < 25 -> sev 4


def rating(x, xs, rs):
    x = np.asarray(x, dtype="float32")
    out = np.interp(x, xs, rs).astype("float32")
    out[~np.isfinite(x)] = np.nan
    return out


def severity(R):
    R = np.asarray(R)
    s = np.full(R.shape, 4, dtype="uint8")
    s[R >= 25] = 3
    s[R >= 40] = 2
    s[R >= 60] = 1
    s[R >= 85] = 0
    s[~np.isfinite(R)] = 255
    return s


@dataclass
class Factor:
    key: str
    label: str
    unit: str
    inputs: tuple
    fn: object                      # (cov dict) -> (value, R)
    irreversible: bool = False      # sev 4 forces class 4 (cannot be fixed by soil/land management)
    reversibility: str = "reversible"     # reversible | partially_reversible | irreversible
    evidence: str = "expert_rule"
    native_res_m: float = 250.0
    source: str = ""
    note: str = ""


def awc_cm_per_m(sand, clay, soc_gkg, cfvo):
    """Saxton & Rawls (2006) pedotransfer: plant-available water (theta33 - theta1500), cm/m, reduced for coarse fragments."""
    S = np.clip(sand, 0, 100) / 100.0
    C = np.clip(clay, 0, 100) / 100.0
    OM = np.clip(soc_gkg / 10.0 * 1.724, 0, 8)      # % organic matter (Van Bemmelen factor), capped like the PTF range
    t1500t = -0.024 * S + 0.487 * C + 0.006 * OM + 0.005 * S * OM - 0.013 * C * OM + 0.068 * S * C + 0.031
    t1500 = t1500t + (0.14 * t1500t - 0.02)
    t33t = -0.251 * S + 0.195 * C + 0.011 * OM + 0.006 * S * OM - 0.027 * C * OM + 0.452 * S * C + 0.299
    t33 = t33t + (1.283 * t33t ** 2 - 0.374 * t33t - 0.015)
    return (np.clip(t33 - t1500, 0, 0.45) * 100.0 * (1 - np.clip(cfvo, 0, 100) / 100.0)).astype("float32")


def _slope(c):
    v = 0.5 * (c["slope_mean"] + c["slope_p90"])
    return v, rating(v, [0, 2, 5, 9, 16, 30], [100, 85, 60, 40, 25, 0])


def _stone(c):
    v = c["cfvo_0_60"]
    return v, rating(v, [0, 15, 35, 55, 75, 95], [100, 85, 60, 40, 25, 0])


def _awc(c):
    v = awc_cm_per_m(c["sand_0_30"], c["clay_0_30"], c["soc_0_30"], c["cfvo_0_60"])
    return v, rating(v, [0, 4, 6, 8, 11, 14], [0, 25, 40, 60, 85, 100])


def _ec(c):
    v = c["sotwis_ec"]
    return v, rating(v, [0, 2, 4, 8, 16, 32], [100, 85, 60, 40, 25, 0])


def _esp(c):
    v = c["sotwis_esp"]
    return v, rating(v, [0, 10, 20, 35, 50, 70], [100, 85, 60, 40, 25, 0])


def _gyp(c):
    v = c["sotwis_gypsum"]
    return v, rating(v, [0, 20, 100, 250, 500, 800], [100, 85, 60, 40, 25, 0])


def _caco3(c):
    v = c["sotwis_caco3"]
    return v, rating(v, [0, 300, 500, 700, 850, 1000], [100, 85, 60, 40, 25, 0])


def _ph(c):
    v = c["ph_0_30"]
    lo = rating(v, [4.0, 4.5, 5.0, 5.5, 6.0, 6.5], [0, 25, 40, 60, 85, 100])
    hi = rating(v, [8.4, 8.6, 8.9, 9.2, 9.5, 10.0], [100, 85, 60, 40, 25, 0])
    return v, np.minimum(lo, hi)


def _fert(c):
    soc, cec = c["soc_0_30"], c["cec_0_30"]
    r_soc = rating(soc, [0, 1.5, 3, 6, 10], [40, 50, 60, 85, 100])      # floor 40: amendable with inputs (never N)
    r_cec = rating(cec, [0, 4, 8, 12], [45, 60, 85, 100])
    return soc, 0.5 * (r_soc + r_cec)


_DRAIN_R = np.array([np.nan, 30, 50, 75, 95, 100, 90, 70], dtype="float32")     # index = SOTWIS ordinal 1..7


def _drain(c):
    v = c["sotwis_drainage"].astype("int64")
    R = _DRAIN_R[np.clip(v, 0, 7)]
    return v.astype("float32"), R


def _water(c):
    v = c["ppt_annual"]
    return v, rating(v, [0, 50, 100, 200, 300, 400, 500], [0, 12, 25, 40, 60, 85, 100])


def _temp(c):
    cold = rating(c["tmin_coldest"], [-10, -6, -3, 0, 3, 6], [0, 25, 40, 60, 85, 100])
    heat = rating(c["tmax_hottest"], [34, 38, 41, 44, 47, 50], [100, 85, 60, 40, 25, 0])
    return c["tmin_coldest"], np.minimum(cold, heat)


FACTORS = [
    Factor("slope", "Terrain slope", "deg (mean/P90 blend)", ("slope_mean", "slope_p90"), _slope, True, "irreversible",
           "observed", 30.0, "Copernicus GLO-30 DEM", "irreversible at >16 deg (N2); 9-16 deg needs terracing"),
    Factor("stoniness", "Coarse fragments (0-60 cm)", "vol%", ("cfvo_0_60",), _stone, True, "irreversible", "ml_predicted",
           250.0, "SoilGrids 2.0 cfvo", "stone content >75 vol% = N2"),
    Factor("water_holding", "Plant-available water capacity", "cm/m", ("sand_0_30", "clay_0_30", "soc_0_30", "cfvo_0_60"), _awc,
           False, "partially_reversible", "ml_predicted", 250.0, "Saxton-Rawls PTF on SoilGrids sand/clay/SOC/CFVO",
           "computed pedotransfer estimate, not measured"),
    Factor("salinity", "Soil salinity (ECe)", "dS/m", ("sotwis_ec",), _ec, False, "partially_reversible", "expert_rule",
           5000.0, "SOTWIS Jordan 1:500 000 map unit (topsoil 0-20 cm)", "legacy survey estimate per map unit; coarse"),
    Factor("sodicity", "Sodicity (ESP)", "%", ("sotwis_esp",), _esp, False, "partially_reversible", "expert_rule", 5000.0,
           "SOTWIS Jordan", "classes after FAO Soils Bulletin 55 Table 39"),
    Factor("gypsum", "Gypsum content", "g/kg", ("sotwis_gypsum",), _gyp, True, "partially_reversible", "expert_rule", 5000.0,
           "SOTWIS Jordan", "gypsic horizon (>500 g/kg) treated as irreversible"),
    Factor("carbonate", "Calcium carbonate equivalent", "g/kg", ("sotwis_caco3",), _caco3, False, "partially_reversible",
           "expert_rule", 5000.0, "SOTWIS Jordan", "lenient: FAO gives no critical limit; Jordan soils are calcareous"),
    Factor("soil_reaction", "Soil pH", "pH (H2O)", ("ph_0_30",), _ph, False, "reversible", "ml_predicted", 250.0,
           "SoilGrids 2.0 phh2o 0-30 cm", ""),
    Factor("fertility", "Fertility (SOC, CEC)", "g/kg SOC", ("soc_0_30", "cec_0_30"), _fert, False, "reversible", "ml_predicted",
           250.0, "SoilGrids 2.0 soc, cec 0-30 cm", "capped at S3: amendable with organic matter/fertiliser"),
    Factor("drainage", "Soil drainage class", "ordinal 1(very poor)-7(excessive)", ("sotwis_drainage",), _drain, False,
           "partially_reversible", "expert_rule", 5000.0, "SOTWIS Jordan", ""),
    Factor("water_supply", "Rainfall (moisture supply)", "mm/yr", ("ppt_annual",), _water, True, "irreversible", "observed",
           1000.0, "WorldClim 2.1 precipitation normals 1970-2000",
           "<100 mm/yr: no rainfed cropping; irrigation water source not evaluated (no groundwater layer)"),
    Factor("temperature", "Temperature (frost / heat)", "degC coldest-month Tmin", ("tmin_coldest", "tmax_hottest"), _temp, True,
           "irreversible", "observed", 4000.0, "TerraClimate 1991-2020 (downscaled WorldClim pattern)", ""),
]
FACTOR_KEYS = [f.key for f in FACTORS]
IRREVERSIBLE = np.array([f.irreversible for f in FACTORS])

RESTRICTION_NAMES = {1: "protected area", 2: "military area", 3: "quarry / mining", 4: "cemetery", 5: "built-up land",
                     6: "airport / airfield", 7: "surface water", 8: "archaeological / heritage site"}


def evaluate(cov: dict) -> dict:
    """cov: dict name -> ndarray (same shape).  Returns dict with values, ratings R (F,...), sev (F,...), rule_class, index."""
    vals, Rs = [], []
    for f in FACTORS:
        v, R = f.fn(cov)
        vals.append(v)
        Rs.append(R)
    R = np.stack(Rs)                                   # (F, ...)
    sev = severity(R)                                  # 255 where missing
    sev_f = np.where(sev == 255, 0, sev).astype("uint8")
    irr = IRREVERSIBLE.reshape((-1,) + (1,) * (R.ndim - 1))
    irreversible_hit = ((sev_f == 4) & irr).any(0)
    smax = sev_f.max(0)
    n2 = (sev_f >= 2).sum(0)
    n1 = (sev_f >= 1).sum(0)
    cls = np.ones(smax.shape, dtype="uint8")
    cls[(smax >= 2) | (n1 >= 2)] = 2
    cls[(smax >= 3) | (n2 >= 3)] = 3
    cls[irreversible_hit] = 4
    r = np.where(np.isfinite(R), R, 100.0)
    rmin = r.min(0)
    am = r.argmin(0)
    others = np.exp(0.5 * (np.log(np.clip(r, 1, 100) / 100.0).sum(0) - np.log(np.clip(rmin, 1, 100) / 100.0)))
    index = (rmin * others / 100.0).astype("float32")  # 0..1
    r_cls = cls.copy()
    restr = cov.get("restriction_code")
    if restr is not None:
        cls = np.where(np.asarray(restr) > 0, 5, cls).astype("uint8")
    return dict(values=np.stack(vals), R=R, sev=sev_f, rule_class=cls, rule_class_nonrestricted=r_cls, index=index,
                limiting=am.astype("uint8"), irreversible=irreversible_hit)


def status_from_sev(sev: int, restricted: bool = False) -> str:
    if restricted:
        return "restricted"
    return "favourable" if sev == 0 else ("marginal" if sev == 1 else "limiting")
