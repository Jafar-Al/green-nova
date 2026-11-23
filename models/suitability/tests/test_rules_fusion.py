"""Unit tests: rule engine, fusion, deterministic counter-based Monte-Carlo noise."""
import numpy as np

from models.suitability import fusion, rules


def cov(n=1, **over):
    base = dict(slope_mean=1.0, slope_p90=2.0, cfvo_0_60=5.0, sand_0_30=40.0, clay_0_30=25.0, soc_0_30=12.0, cec_0_30=18.0,
                ph_0_30=7.6, sotwis_ec=0.8, sotwis_esp=2.0, sotwis_gypsum=2.0, sotwis_caco3=150.0, sotwis_drainage=5,
                ppt_annual=450.0, tmin_coldest=4.0, tmax_hottest=36.0, restriction_code=0)
    base.update(over)
    return {k: np.full(n, v, dtype="float32") for k, v in base.items()}


def test_rating_curves_hit_class_borders():
    assert rules.severity(rules.rating(np.array([2.0]), [0, 2, 5, 9, 16, 30], [100, 85, 60, 40, 25, 0]))[0] == 0
    assert rules.severity(rules.rating(np.array([5.0]), [0, 2, 5, 9, 16, 30], [100, 85, 60, 40, 25, 0]))[0] == 1
    assert rules.severity(rules.rating(np.array([20.0]), [0, 2, 5, 9, 16, 30], [100, 85, 60, 40, 25, 0]))[0] == 4


def test_good_land_is_class_1_and_restriction_wins():
    ev = rules.evaluate(cov())
    assert ev["rule_class"][0] == 1
    ev = rules.evaluate(cov(restriction_code=1))
    assert ev["rule_class"][0] == 5
    assert ev["rule_class_nonrestricted"][0] == 1


def test_irreversible_and_reclaimable_limits():
    assert rules.evaluate(cov(slope_mean=22.0, slope_p90=30.0))["rule_class"][0] == 4          # steep: irreversible
    assert rules.evaluate(cov(ppt_annual=40.0))["rule_class"][0] == 4                          # hyper-arid
    assert rules.evaluate(cov(sotwis_ec=12.0))["rule_class"][0] == 3                           # saline: reclaimable
    assert rules.evaluate(cov(sotwis_ec=5.0))["rule_class"][0] == 2                            # severe-but-S3 limitation
    assert rules.evaluate(cov(sotwis_ec=3.0))["rule_class"][0] == 1                            # a single moderate (S2) limitation
    assert rules.evaluate(cov(sotwis_ec=3.0, ph_0_30=8.7))["rule_class"][0] == 2               # two moderate limitations aggregate


def test_fusion_rules():
    rc = np.array([4, 3, 1, 3, 4], dtype="uint8")
    sev = np.zeros((len(rules.FACTORS), 5), dtype="uint8")
    sev[rules.FACTOR_KEYS.index("slope"), 4] = 4                                              # hard limit on last cell
    restr = np.array([0, 0, 0, 0, 0], dtype="uint8")
    p = np.array([0.9, 0.9, 0.001, 0.1, 0.9], dtype="float32")
    obs = np.array([False, False, False, True, False])
    cls, reason = fusion.fuse(rc, sev, restr, p, obs)
    assert list(cls) == [3, 2, 2, 2, 4]            # ML up, ML up, ML down, observed override, hard limit blocks upgrade
    cls, _ = fusion.fuse(rc, sev, np.array([1, 0, 0, 0, 0], dtype="uint8"), p, obs)
    assert cls[0] == 5


def test_noise_is_chunk_independent_and_deterministic():
    ids = np.arange(1000, dtype="uint64")
    a = fusion.normal(ids, 5)
    b = np.concatenate([fusion.normal(ids[:300], 5), fusion.normal(ids[300:], 5)])
    assert np.array_equal(a, b)
    assert abs(float(a.mean())) < 0.15 and 0.85 < float(a.std()) < 1.15


def test_mc_probabilities_sum_to_one():
    n = 50
    c = cov(n)
    sd = {k: np.full(n, 0.3, "float32") for k in ("ph_sd", "soc_sd", "sand_sd", "clay_sd")}
    pm = np.full((3, n), 0.2, "float32")
    probs, central, reason, _ = fusion.mc_class_probs(c, sd, pm, np.zeros(n, "uint8"), np.zeros(n, bool), np.arange(n, dtype="uint64"), K=8)
    assert np.allclose(probs.sum(0), 1.0)
    assert central.shape == (n,)
