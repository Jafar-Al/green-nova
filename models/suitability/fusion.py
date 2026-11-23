"""Evidence fusion: rule-engine class + calibrated ML cultivation likelihood + observed cultivation + restrictions -> class 1..5,
and Monte-Carlo propagation of input uncertainty to class probabilities / confidence.

Final class (vectorised):
  start  = FAO-style rule class (1..4) from rules.evaluate()                                  [expert_rule]
  ML up  : P >= P_HI and class >= 3 and no *hard* irreversible limit (slope, stoniness, gypsum, temperature at sev 4)
           -> class - 1  (similar-condition land elsewhere in Jordan is commonly cultivated)   [ml_predicted]
  ML down: P <= P_LO and class == 1 -> 2   (rules say good but no cultivated analogue exists)  [ml_predicted]
  observed: cultivated now (label evidence) and class >= 3 -> 2                                  [observed]
  restricted (legal/environmental) -> 5 (always wins)                                             [observed/expert]
`reason` codes: 0 rules only | 1 ML upgrade | 2 ML downgrade | 3 observed cultivation | 4 restriction
"""
from __future__ import annotations

import numpy as np

from . import rules

P_HI = 0.50
P_LO = 0.01
HARD_KEYS = ["slope", "stoniness", "gypsum", "temperature"]
HARD_IDX = [rules.FACTOR_KEYS.index(k) for k in HARD_KEYS]


def fuse(rule_cls_nonrestricted, sev, restriction, p, cult_obs, p_hi=P_HI, p_lo=P_LO):
    """sev: (F,...) uint8 severities; p: calibrated cultivation probability; cult_obs: bool observed cultivation."""
    cls = rule_cls_nonrestricted.astype("int8").copy()
    reason = np.zeros(cls.shape, "uint8")
    hard = (sev[HARD_IDX] >= 4).any(0)
    up = (p >= p_hi) & (cls >= 3) & ~hard
    cls = np.where(up, cls - 1, cls); reason[up] = 1
    down = (p <= p_lo) & (cls == 1)
    cls = np.where(down, 2, cls); reason[down] = 2
    ob = cult_obs & (cls >= 3)
    cls = np.where(ob, 2, cls); reason[ob] = 3
    rs = restriction > 0
    cls = np.where(rs, 5, cls); reason[rs] = 4
    return cls.astype("uint8"), reason


_M = np.uint64(0xFFFFFFFFFFFFFFFF)


def _splitmix(x):
    with np.errstate(over="ignore"):
        x = x + np.uint64(0x9E3779B97F4A7C15)
        z = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return z ^ (z >> np.uint64(31))


def uniform(ids: np.ndarray, salt: int) -> np.ndarray:
    """Counter-based U(0,1): depends only on (global cell id, salt) -> results are independent of chunking/window."""
    h = _splitmix(ids.astype("uint64") ^ _splitmix(np.uint64(salt)))
    return ((h >> np.uint64(11)).astype("float64") + 0.5) * (1.0 / 9007199254740992.0)


def normal(ids, salt):
    from scipy.special import ndtri
    return ndtri(uniform(ids, salt)).astype("float32")


def perturb(cov: dict, sd: dict, ids: np.ndarray, k: int) -> dict:
    """One deterministic Monte-Carlo draw k of the rule inputs. Documented assumptions (NOT validated error models):
    SoilGrids pH/SOC/sand/clay ~ N(mu, (Q95-Q05)/3.29); other SoilGrids x lognormal(0.25);
    SOTWIS EC/ESP/gypsum/CaCO3 x lognormal(0.5) (legacy 1:500 000 map unit); slope x lognormal(0.15);
    rainfall x lognormal(0.20); temperatures + N(0, 1 degC). Cells are perturbed independently."""
    c = dict(cov)
    base = 100 * (k + 1)

    def z(j):
        return normal(ids, base + j)

    c["ph_0_30"] = c["ph_0_30"] + z(0) * sd["ph_sd"]
    c["soc_0_30"] = np.maximum(c["soc_0_30"] + z(1) * sd["soc_sd"], 0)
    c["sand_0_30"] = np.clip(c["sand_0_30"] + z(2) * sd["sand_sd"], 0, 100)
    c["clay_0_30"] = np.clip(c["clay_0_30"] + z(3) * sd["clay_sd"], 0, 100)
    c["cfvo_0_60"] = np.clip(c["cfvo_0_60"] * np.exp(0.25 * z(4)), 0, 100)
    c["cec_0_30"] = c["cec_0_30"] * np.exp(0.25 * z(5))
    for j, key in enumerate(("sotwis_ec", "sotwis_esp", "sotwis_gypsum", "sotwis_caco3")):
        c[key] = c[key] * np.exp(0.5 * z(6 + j))
    f = np.exp(0.15 * z(10))
    c["slope_mean"] = c["slope_mean"] * f
    c["slope_p90"] = c["slope_p90"] * f
    c["ppt_annual"] = c["ppt_annual"] * np.exp(0.20 * z(11))
    c["tmin_coldest"] = c["tmin_coldest"] + z(12)
    c["tmax_hottest"] = c["tmax_hottest"] + z(13)
    return c


def mc_class_probs(cov: dict, sd: dict, p_members: np.ndarray, restriction, cult_obs, ids: np.ndarray, K: int = 24):
    """Return (class_probs (5, N) float32, central class, central rule evaluation). p_members: (M, N) calibrated member
    probabilities. ML member and fusion thresholds are resampled per draw; restrictions/observed cultivation are fixed."""
    cen = rules.evaluate({**cov, "restriction_code": restriction})
    p_mean = p_members.mean(0)
    central, reason = fuse(cen["rule_class_nonrestricted"], cen["sev"], restriction, p_mean, cult_obs)
    counts = np.zeros((5,) + central.shape, "float32")
    M = p_members.shape[0]
    for k in range(K):
        pc = perturb(cov, sd, ids, k)
        ev = rules.evaluate({**pc, "restriction_code": restriction})
        m = np.minimum((uniform(ids, 100 * (k + 1) + 20) * M).astype("int64"), M - 1)
        p = np.take_along_axis(p_members, m[None], 0)[0]
        jit = float(np.exp(0.1 * normal(np.array([0], dtype="uint64"), 7000 + k)[0]))
        cl, _ = fuse(ev["rule_class_nonrestricted"], ev["sev"], restriction, p, cult_obs, P_HI * jit, P_LO * jit)
        for c_ in range(1, 6):
            counts[c_ - 1] += (cl == c_)
    return counts / K, central, reason, cen
