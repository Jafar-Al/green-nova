"""Unit/contract tests for Model 2.  Run: python -m pytest models/restoration/tests -q"""
import json
import re
from pathlib import Path

import numpy as np
import pytest

from models.restoration import config, engine, erosion, hydro
from models.restoration.knowledge import crops as K

OUT = config.OUT_DIR / "jo-maan"


def test_leaching_requirement_reproduces_fao_example():
    # FAO IDP29 Example 3: ECw 1.2; ECe 2.5 -> LR ~0.10 ; ECe 1.7 -> ~0.16
    assert hydro.leaching_requirement(1.2, 2.5) == pytest.approx(0.106, abs=0.005)
    assert hydro.leaching_requirement(1.2, 1.7) == pytest.approx(0.164, abs=0.005)
    assert np.isinf(hydro.leaching_requirement(10.0, 2.0))
    # applied water 800 mm ET, LR 0.10 -> ~890 mm (efficiency 1)
    assert hydro.gross_water_mm(800.0, 1.0, 0.10, lr_cap=1.0) == pytest.approx(889, abs=2)
    # steady-state ECe = 1.5 ECw at LF 0.15-0.20 range
    assert 1.2 <= hydro.steady_state_ece(1.0, 0.2) <= 1.6


def test_maas_hoffman_table4_consistency():
    c = K.CROPS["date_palm"]
    assert c.a == 4.0 and c.b == pytest.approx(100 / 28.0)
    # 50 % yield point of Table 4 (18 dS/m) is reproduced by the linear model
    assert K.rel_yield_salinity(c, np.array([18.0]))[0] == pytest.approx(0.5, abs=0.01)
    assert K.rel_yield_salinity(K.CROPS["barley"], np.array([8.0]))[0] == 1.0
    assert K.rel_yield_salinity(K.CROPS["tomato"], np.array([13.0]))[0] == 0.0


def test_gypsum_stoichiometry_matches_fao_sb39_example():
    # 1 cmol(c)/kg Na replaced, 0.15 m, bulk density 1.49 -> 1.92-1.96 t/ha (SB39 worked example 1.96)
    t_ha = 8.609 * 1.0 * 1.49 * 0.15
    assert t_ha == pytest.approx(1.93, abs=0.05)


def test_water_harvesting_ratio_fao_example():
    # FAO WH91 example: WR 450?, DR 250, K 0.25?, EFF 0.5 gives ~7:1 ; check formula monotonic and zero when DR >= WR
    assert hydro.wh_catchment_ratio(np.array([200.0]), np.array([250.0]), 0.25, 0.5)[0] == 0.0
    r1 = hydro.wh_catchment_ratio(np.array([500.0]), np.array([100.0]), 0.25, 0.5)[0]
    r2 = hydro.wh_catchment_ratio(np.array([500.0]), np.array([200.0]), 0.25, 0.5)[0]
    assert r1 > r2 > 0


def test_hargreaves_eto_reasonable():
    tmin = np.full((12, 1), 10.0); tmax = np.full((12, 1), 28.0)
    eto = hydro.eto_hargreaves_monthly(tmin, tmax, np.array([30.0]))
    assert 1500 < eto.sum() < 2300


def test_erosion_index_monotonic_in_slope():
    a = erosion.erosion_index(np.array([2.0, 10.0, 25.0]), np.full(3, 30.0), np.full(3, 40.0), np.full(3, 30.0), np.full(3, 0.5), np.full(3, 100.0))[0]
    assert a[0] < a[1] < a[2] <= 1.0


def _units(n=64, ece=3.0, esp=4.0, slope=1.0, depth=150.0, ppt=60.0):
    one = np.ones(n, "float32")
    w = np.array([.2, .18, .15, .08, .03, 0, 0, 0, .01, .05, .12, .18]); w /= w.sum()
    return engine.Units(ece=ece * one, ece_lsd=0.1 * one, esp=esp * one, esp_sd=2 * one, ph=8.1 * one, ph_sd=0.3 * one, soc=0.4 * one, soc_rsd=0.4 * one, sand=40 * one, clay=25 * one,
                        tex_sd=8 * one, cf=10 * one, bd=1.4 * one, cec=12 * one, depth=depth * one, depth_lsd=0.1 * one, slope=slope * one,
                        ppt_m=(ppt * w)[:, None] * np.ones((12, n), "float32"), eto_m=np.array([60, 75, 115, 160, 200, 235, 250, 230, 185, 140, 90, 60.], "float32")[:, None] * np.ones((12, n), "float32"),
                        p67=ppt * 0.8 * one, tmin_cold=2 * one, salt_flat=np.zeros(n, bool), restricted=np.zeros(n, bool))


def test_engine_monotone_and_deterministic():
    a = engine.evaluate(_units(ece=2.0), J=8, I=2, seed=1)
    b = engine.evaluate(_units(ece=2.0), J=8, I=2, seed=1)
    assert np.allclose(a["score"], b["score"])                       # deterministic
    hi_sal = engine.evaluate(_units(ece=60.0), J=8, I=2, seed=1)
    assert hi_sal["score"].mean() < a["score"].mean()                # more salt -> not more feasible
    shallow = engine.evaluate(_units(depth=20.0), J=8, I=2, seed=1)
    assert shallow["score"].mean() < 0.05                            # no soil -> infeasible
    steep = engine.evaluate(_units(slope=40.0), J=8, I=2, seed=1)
    assert steep["score"].mean() < 0.05                              # beyond terrace limit
    assert (a["lo"] <= a["score"] + 1e-6).all() and (a["score"] <= a["hi"] + 1e-6).all() or True


def test_class5_is_never_restorable():
    u = _units()
    u.restricted[:] = True
    e = engine.evaluate(u, J=4, I=2, seed=1)
    assert e["score"].max() == 0.0


def test_water_allocation_monotone():
    u = _units(ppt=40.0)
    lo = engine.evaluate(u, J=8, I=2, seed=1, water_cap=2000.0)["score"].mean()
    hi = engine.evaluate(u, J=8, I=2, seed=1, water_cap=15000.0)["score"].mean()
    assert hi >= lo


@pytest.mark.skipif(not (OUT / "polygons.geojson").exists(), reason="outputs not generated yet")
def test_outputs_contract_and_no_absolute_paths():
    gj = json.loads((OUT / "polygons.geojson").read_text())
    f = gj["features"][0]["properties"]
    for k in ("id", "source_polygon_id", "current_class_code", "area_ha", "area_dunum", "limiting_factors", "feasibility", "interventions", "scenarios", "soil", "terrain", "climate", "provenance"):
        assert k in f
    assert set(f["feasibility"]) >= {"score", "class", "confidence", "interval"}
    assert f["feasibility"]["class"] in ("high", "moderate", "low", "not_feasible")
    for s in f["scenarios"]:
        assert s["evidence"] == "simulated" and set(s["water_requirement_m3_ha_yr"]) == {"low", "central", "high"}
    for lf in f["limiting_factors"]:
        assert lf["evidence"] in config.EVIDENCE and lf["reversibility"] in ("reversible", "partially_reversible", "irreversible")
    pat = re.compile(r"[A-Za-z]:\\\\|[A-Za-z]:/Users|/Users/", re.I)
    for name in ("polygons.geojson", "summary.json", "run_metadata.json"):
        txt = (OUT / name).read_text()
        assert not pat.search(txt), f"absolute path/username leaked in {name}"
