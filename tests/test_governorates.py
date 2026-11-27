"""Cross-governorate integrity tests on the committed outputs (no data cache needed).

They check that every one of Jordan's 12 governorates has its OWN real assessment: areas add up, polygons stay inside the
governorate boundary, Model 2 covers exactly the land Model 1 flagged, nothing was copied between governorates, and both
models' provenance matches the committed checkpoints.
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
M1 = ROOT / "models" / "suitability" / "outputs"
M2 = ROOT / "models" / "restoration" / "outputs"
CKPT1 = ROOT / "models" / "suitability" / "checkpoints" / "model1_suitability_v0.1.pkl"

EXPECTED = {"jo-ajloun", "jo-amman", "jo-aqaba", "jo-balqa", "jo-irbid", "jo-jerash", "jo-karak", "jo-maan", "jo-madaba", "jo-mafraq", "jo-tafilah", "jo-zarqa"}
_to_equal_area = Transformer.from_crs(4326, 6933, always_xy=True).transform


def _boundaries() -> dict:
    fc = json.loads((ROOT / "regions" / "jordan_adm1.geojson").read_text(encoding="utf-8"))
    return {f["properties"]["region_id"]: shape(f["geometry"]) for f in fc["features"]}


BOUNDS = _boundaries()
REGIONS = sorted(EXPECTED)


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def test_boundary_file_has_the_twelve_governorates():
    assert set(BOUNDS) == EXPECTED


@pytest.mark.parametrize("rid", REGIONS)
def test_both_models_have_outputs(rid):
    for d in (M1 / rid, M2 / rid):
        for f in ("summary.json", "run_metadata.json", "polygons.geojson"):
            assert (d / f).exists(), f"{d.name}/{f} missing for {rid}"
    for f in ("suitability.tif", "confidence.tif"):
        assert (M1 / rid / f).exists()
    for f in ("restoration_feasibility.tif", "post_restoration_suitability.tif"):
        assert (M2 / rid / f).exists()


@pytest.mark.parametrize("rid", REGIONS)
def test_model1_areas_are_consistent_and_match_the_boundary(rid):
    s = _load(M1 / rid / "summary.json")
    cls = s["classes"]
    total = sum(v["area_ha"] for v in cls.values())
    assert abs(total - s["total_area_ha"]) < 1.0, "class areas must sum to the governorate area (no double counting)"
    assert abs(sum(v["share"] for v in cls.values()) - 1.0) < 0.002
    for v in cls.values():
        assert abs(v["area_dunum"] - v["area_ha"] * 10.0) < 1.0, "1 dunum = 0.1 ha"
    # independent check of the total against the vector boundary in an equal-area CRS (grid rasterisation tolerance 3 %)
    boundary_ha = transform(_to_equal_area, BOUNDS[rid]).area / 10_000.0
    assert abs(s["total_area_ha"] - boundary_ha) / boundary_ha < 0.03, (s["total_area_ha"], boundary_ha)


@pytest.mark.parametrize("rid", REGIONS)
def test_model1_polygons_match_summary_and_stay_inside_the_governorate(rid):
    fc = _load(M1 / rid / "polygons.geojson")
    s = _load(M1 / rid / "summary.json")
    per = {k: 0.0 for k in s["classes"]}
    for f in fc["features"]:
        per[str(f["properties"]["class_code"])] += f["properties"]["area_ha"]
    for k, v in s["classes"].items():
        assert abs(per[k] - v["area_ha"]) <= max(1.0, 0.005 * v["area_ha"]), f"class {k}: polygons {per[k]} vs summary {v['area_ha']}"
    boundary = BOUNDS[rid].buffer(0.003)  # ~300 m: polygons come from a 100 m raster, edges are cell-aligned
    rng = random.Random(7)
    sample = rng.sample(fc["features"], min(400, len(fc["features"])))
    outside = [f["properties"]["id"] for f in sample if not boundary.contains(shape(f["geometry"]).representative_point())]
    assert not outside, f"{len(outside)} sampled polygons lie outside {rid}"


@pytest.mark.parametrize("rid", REGIONS)
def test_model2_covers_exactly_the_land_model1_flagged(rid):
    s1 = _load(M1 / rid / "summary.json")
    s2 = _load(M2 / rid / "summary.json")
    flagged = s1["classes"]["3"]["area_ha"] + s1["classes"]["4"]["area_ha"] + s1["classes"]["5"]["area_ha"]
    by = s2["headline"]["area_ha_by_class"]
    covered = sum(by.values())
    assert abs(covered - flagged) <= max(2.0, 0.005 * flagged), f"Model 2 covers {covered} ha but Model 1 flagged {flagged} ha"
    # class 5 (legal/environmental restriction) is never restorable
    assert abs(by["not_feasible"] - s1["classes"]["5"]["area_ha"]) <= max(2.0, 0.005 * s1["classes"]["5"]["area_ha"]) or by["not_feasible"] >= s1["classes"]["5"]["area_ha"] - 2.0
    m1_ids = {f["properties"]["id"] for f in _load(M1 / rid / "polygons.geojson")["features"]}
    feats = _load(M2 / rid / "polygons.geojson")["features"]
    assert feats, "Model 2 produced no polygons"
    assert all(f["properties"]["source_polygon_id"] in m1_ids for f in feats), "Model 2 polygons must link to Model 1 polygon ids of the same governorate"
    for f in feats[:200]:
        for sc in f["properties"]["scenarios"]:
            assert sc["evidence"] == "simulated"


def test_each_governorate_has_its_own_results():
    sigs, bboxes = {}, {}
    for rid in REGIONS:
        s = _load(M1 / rid / "summary.json")
        sigs[rid] = tuple(round(v["area_ha"]) for v in s["classes"].values())
        bboxes[rid] = tuple(round(x, 3) for x in BOUNDS[rid].bounds)
    assert len(set(sigs.values())) == len(REGIONS), "two governorates have identical class areas"
    assert len(set(bboxes.values())) == len(REGIONS)
    pol_hashes = {hashlib.sha256((M1 / rid / "polygons.geojson").read_bytes()).hexdigest() for rid in REGIONS}
    assert len(pol_hashes) == len(REGIONS), "two governorates share an identical polygon file"


@pytest.mark.parametrize("rid", REGIONS)
def test_provenance_matches_the_committed_checkpoint(rid):
    sha = hashlib.sha256(CKPT1.read_bytes()).hexdigest()
    m1 = _load(M1 / rid / "run_metadata.json")
    assert m1["region_id"] == rid
    assert m1["checkpoint_sha256"] == sha
    assert m1["grid_resolution_m"] == 100.0 and m1["effective_resolution_m"] >= 1000
    m2 = _load(M2 / rid / "run_metadata.json")
    assert "model1_run" in m2 and m2["model1_run"]["checkpoint_sha256"] == sha, "Model 2 must consume this governorate's Model 1 output"
    assert m2["caveats"]["feasibility_is_conditional_on_water"] is True
    assert m2["caveats"]["assumed_water_allocation_m3_ha_yr"] is None, "no universal water allocation may be assumed"
    ws = m2["caveats"]["water_supply"]
    assert ws["not_mapped"] and "local" in ws["method"].lower()


def test_water_differs_between_governorates_and_limits_feasibility():
    """Water must actually change the assessment: the climatically wetter north has far more local renewable water than the desert south,
    and feasibility is not the same for every governorate (no universal allocation)."""
    def stats(rid):
        sup, wts, high, tot = 0.0, 0.0, 0.0, 0.0
        for f in _load(M2 / rid / "polygons.geojson")["features"]:
            p = f["properties"]
            if p["current_class_code"] not in (3, 4):
                continue
            a = p["area_ha"]
            sup += p["water"]["local_renewable_supply_m3_ha_yr"]["central"] * a
            wts += a
            tot += a
            high += a if p["feasibility"]["class"] == "high" else 0.0
        return sup / wts, high / tot
    for rid in REGIONS:   # required vs available vs deficit are consistent, and land that needs far more water than it can get is never rated high
        for f in _load(M2 / rid / "polygons.geojson")["features"]:
            p = f["properties"]
            irr = p["water"]["irrigation"]
            if irr is not None:   # None only where no irrigated scenario has a finite water figure (a few tiny, extremely saline polygons)
                assert abs(irr["deficit_m3_ha_yr"] - max(irr["central_requirement_m3_ha_yr"] - irr["local_renewable_supply_m3_ha_yr"], 0)) <= 1.5
                assert 0 <= irr["share_of_need_met_locally"] <= 1
            if p["feasibility"]["class"] == "high":
                best = next(s for s in p["scenarios"] if s["id"] == p["feasibility_meta"]["best_scenario"])
                need = best["water_requirement_m3_ha_yr"]["central"]
                assert best["water_deficit_m3_ha_yr"] <= 0.3 * need or best["water_deficit_m3_ha_yr"] == 0, (rid, p["id"], best["water_deficit_m3_ha_yr"], need)
    north, south = stats("jo-irbid"), stats("jo-maan")
    assert north[0] > 3 * south[0], (north, south)
    shares = {rid: stats(rid)[1] for rid in REGIONS}
    assert max(shares.values()) - min(shares.values()) > 0.02, "high-feasibility share must vary with local water"
    assert shares["jo-irbid"] >= shares["jo-maan"]
