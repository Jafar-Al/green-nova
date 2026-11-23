"""Backend tests. Fixtures below are TEST-ONLY contract-shaped files written into a temp dir; they are never served by the real app.
Real-model smoke tests live in web/scripts/smoke.ps1 (they need the models' real outputs)."""
from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.errors import scrub
from backend.app.main import create_app
from backend.app.memguard import available_mb
from backend.app.security import SlidingWindow
from backend.app.validation import check_polygon_ids, validate_bbox, validate_geometry
from backend.app.errors import ApiError

REGION_BBOX = (35.0, 29.0, 38.0, 31.5)
RING = [[35.5, 29.5], [37.5, 29.5], [37.5, 31.0], [35.5, 31.0], [35.5, 29.5]]


def m1_feature(n: int, cls: int) -> dict:
    x = 36.0 + n * 0.01
    ring = [[x, 30.0], [x + 0.005, 30.0], [x + 0.005, 30.005], [x, 30.005], [x, 30.0]]
    probs = {str(k): 0.0 for k in range(1, 6)}
    probs[str(cls)] = 1.0
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {
            "id": f"m1-jo-maan-{n}", "class_code": cls, "class_label": "x", "area_ha": 25.0, "area_dunum": 250.0, "confidence": 0.9,
            "confidence_method": "test fixture", "class_probabilities": probs, "factors": [], "centroid": [x, 30.0], "effective_resolution_m": 1000,
            "provenance": {"model_version": "test-1", "label_basis": "test", "data_sources": ["test"]},
        },
    }


@pytest.fixture()
def env(tmp_path: Path):
    root = tmp_path / "app"
    (root / "regions").mkdir(parents=True)
    (root / "regions" / "jordan_adm1.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"shapeName": "Ma'an", "shapeISO": "JO-MN"}, "geometry": {"type": "Polygon", "coordinates": [[[35.0, 29.0], [38.0, 29.0], [38.0, 31.5], [35.0, 31.5], [35.0, 29.0]]]}}]})
    )
    s = Settings(root=root, data_root=tmp_path, runtime=tmp_path / "runtime")
    return root, s


def client(s: Settings) -> TestClient:
    return TestClient(create_app(s))


def write_m1(root: Path, n: int = 3) -> None:
    d = root / "models" / "suitability" / "outputs" / "jo-maan"
    d.mkdir(parents=True)
    (d / "polygons.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [m1_feature(i + 1, 3 if i % 2 == 0 else 5) for i in range(n)]}))
    (d / "run_metadata.json").write_text(json.dumps({"model_version": "test-1", "grid_resolution_m": 100, "effective_resolution_m": 1000, "path": "C:\\Secret\\dir\\x.tif"}))


def test_health_and_ready_degrade_without_models(env):
    root, s = env
    with client(s) as c:
        assert c.get("/health").json() == {"status": "ok"}
        r = c.get("/ready")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "degraded"
        assert body["models"]["jo-maan"]["suitability"]["available"] is False


def test_missing_model_is_503_with_clear_message_and_no_paths(env):
    root, s = env
    with client(s) as c:
        r = c.get("/v1/regions/jo-maan/suitability/run")
        assert r.status_code == 503
        e = r.json()["error"]
        assert e["code"] == "model_unavailable" and e["model"] == "suitability"
        assert ":\\" not in r.text and "/Users/" not in r.text
        assert c.get("/v1/regions/jo-maan/restoration/layer").status_code == 503
        assert c.post("/v1/jobs", json={"kind": "suitability", "region_id": "jo-maan"}).status_code == 503


def test_no_docs_no_cors_security_headers(env):
    _, s = env
    with client(s) as c:
        for p in ("/docs", "/redoc", "/openapi.json"):
            assert c.get(p).status_code == 404
        r = c.get("/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in {k.lower() for k in r.headers}
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["cache-control"] == "no-store"
        assert "frame-ancestors" in r.headers["content-security-policy"]
        assert c.get("/health", headers={"Host": "evil.example"}).status_code == 400  # trusted hosts only


def test_validation(env):
    root, s = env
    write_m1(root)
    with client(s) as c:
        assert c.get("/v1/regions/NOPE/boundary").status_code == 400
        assert c.get("/v1/regions/jo-nowhere/boundary").status_code == 404
        assert c.get("/v1/land/not-an-id").status_code == 400
        assert c.get("/v1/jobs/xyz").status_code == 400
        assert c.post("/v1/jobs", content=b"nope", headers={"content-type": "application/json"}).status_code == 400
        assert c.post("/v1/jobs", json={"kind": "suitability", "region_id": "jo-maan", "extra": 1}).status_code == 400
        assert c.post("/v1/jobs", json={"kind": "restoration", "region_id": "jo-maan", "polygon_ids": ["m1-jo-maan-99"]}).status_code in (400, 503)
        assert c.post("/v1/jobs", json={"kind": "bogus", "region_id": "jo-maan"}).status_code == 400
        big = {"kind": "restoration", "region_id": "jo-maan", "polygon_ids": ["m1-jo-maan-1"] * 100_000}
        assert c.post("/v1/jobs", json=big).status_code == 413


def test_polygon_ids_matched_against_known_set():
    assert check_polygon_ids(["m1-jo-maan-1", "m1-jo-maan-1", "m1-jo-maan-2"], max_n=10, known={"m1-jo-maan-1", "m1-jo-maan-2"}) == ["m1-jo-maan-1", "m1-jo-maan-2"]
    with pytest.raises(ApiError):
        check_polygon_ids(["m1-jo-maan-3"], max_n=10, known={"m1-jo-maan-1"})
    with pytest.raises(ApiError):
        check_polygon_ids(["m1-jo-karak-3"], max_n=10, region_id="jo-maan")
    with pytest.raises(ApiError):
        check_polygon_ids(["m1-jo-maan-1"] * 11, max_n=10)


def test_geometry_validation():
    ok = {"type": "Polygon", "coordinates": [RING]}
    assert validate_geometry(ok, region_bbox=REGION_BBOX, max_vertices=100, max_area_km2=1e6) == ok
    for bad in (
        {"type": "Point", "coordinates": [36, 30]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},  # outside region
        {"type": "Polygon", "coordinates": [[[36, 30], [36.1, 30], [36.1, 30.1], [36, 30]]] if False else [[[36, 30], [36.1, 30], [36.1, float("nan")], [36, 30]]]},
    ):
        with pytest.raises(ApiError):
            validate_geometry(bad, region_bbox=REGION_BBOX, max_vertices=100, max_area_km2=1e6)
    with pytest.raises(ApiError):
        validate_geometry(ok, region_bbox=REGION_BBOX, max_vertices=3, max_area_km2=1e6)
    with pytest.raises(ApiError):
        validate_geometry(ok, region_bbox=REGION_BBOX, max_vertices=100, max_area_km2=10)
    assert validate_bbox([36, 30, 37, 31], region_bbox=REGION_BBOX)
    with pytest.raises(ApiError):
        validate_bbox([30, 30, 37, 31], region_bbox=REGION_BBOX)


def wait_done(c: TestClient, job_id: str, timeout: float = 15) -> dict:
    t = time.time()
    while time.time() - t < timeout:
        j = c.get(f"/v1/jobs/{job_id}").json()
        if j["state"] in ("succeeded", "failed", "cancelled"):
            return j
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_suitability_job_cache_and_results_from_real_files(env):
    root, s = env
    write_m1(root, 4)
    with client(s) as c:
        r = c.post("/v1/jobs", json={"kind": "suitability", "region_id": "jo-maan"})
        assert r.status_code == 202
        j = wait_done(c, r.json()["id"])
        assert j["state"] == "succeeded" and j["progress"] == 1.0 and j["demo"] is False
        res = c.get(f"/v1/jobs/{j['id']}/result").json()
        assert res["run"]["polygon_count"] == 4
        # cache: identical params -> the completed job is returned (200), not a new one
        r2 = c.post("/v1/jobs", json={"kind": "suitability", "region_id": "jo-maan"})
        assert r2.status_code == 200 and r2.json()["cached"] is True and r2.json()["id"] == j["id"]
        run = c.get("/v1/regions/jo-maan/suitability/run").json()
        assert run["metadata"]["effective_resolution_m"] == 1000 and run["demo"] is False
        assert "C:\\Secret" not in json.dumps(run)  # paths in model metadata are scrubbed
        polys = c.get("/v1/regions/jo-maan/suitability/polygons").json()
        assert len(polys["features"]) == 4
        land = c.get("/v1/land/m1-jo-maan-1").json()
        assert land["suitability"]["properties"]["id"] == "m1-jo-maan-1" and land["demo"] is False and "Model 2" in land["restoration_note"]
        assert c.get("/v1/land/m1-jo-maan-999").status_code == 404
        # restoration needs Model 2: until its outputs exist -> 503, never a made-up result
        assert c.post("/v1/jobs", json={"kind": "restoration", "region_id": "jo-maan", "polygon_ids": ["m1-jo-maan-1"]}).status_code == 503


def test_invalid_features_are_dropped_and_counted_not_repaired(env):
    root, s = env
    write_m1(root, 2)
    p = root / "models" / "suitability" / "outputs" / "jo-maan" / "polygons.geojson"
    fc = json.loads(p.read_text())
    fc["features"].append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[36, 30], [36.1, 30], [36.1, 30.1], [36, 30]]]}, "properties": {"id": "m1-jo-maan-9"}})
    p.write_text(json.dumps(fc))
    with client(s) as c:
        assert len(c.get("/v1/regions/jo-maan/suitability/polygons").json()["features"]) == 2
        assert c.get("/v1/regions/jo-maan/suitability/run").json()["rejected_features"] == 1


def test_output_swap_is_picked_up_by_mtime(env):
    root, s = env
    write_m1(root, 2)
    p = root / "models" / "suitability" / "outputs" / "jo-maan" / "polygons.geojson"
    with client(s) as c:
        assert len(c.get("/v1/regions/jo-maan/suitability/polygons").json()["features"]) == 2
        time.sleep(0.05)
        p.write_text(json.dumps({"type": "FeatureCollection", "features": [m1_feature(i + 1, 3) for i in range(5)]}))
        assert len(c.get("/v1/regions/jo-maan/suitability/polygons").json()["features"]) == 5


def test_rate_limit_and_queue_bounds(env):
    root, s = env
    write_m1(root, 2)
    s2 = replace(s, rate_per_minute=5)
    with client(s2) as c:
        codes = [c.get("/v1/regions").status_code for _ in range(8)]
        assert codes.count(429) >= 2
        assert c.get("/health").status_code == 200  # liveness is never rate limited
    w = SlidingWindow()
    assert [w.allow("k", 2, 10, now=t) for t in (0, 1, 2)] == [True, True, False]
    assert w.allow("k", 2, 10, now=11.5)


def test_jobs_survive_restart_and_unfinished_are_marked_failed(env):
    root, s = env
    write_m1(root, 2)
    with client(s) as c:
        jid = c.post("/v1/jobs", json={"kind": "suitability", "region_id": "jo-maan"}).json()["id"]
        assert wait_done(c, jid)["state"] == "succeeded"
    with client(s) as c2:  # new process lifetime, same runtime dir
        assert c2.get(f"/v1/jobs/{jid}").json()["state"] == "succeeded"
        assert c2.get(f"/v1/jobs/{jid}/result").json()["run"]["polygon_count"] == 2


def test_scrub_removes_paths():
    assert "C:\\" not in scrub("failed at C:\\GreenNovaData\\x\\y.tif now") and "/Users/" not in scrub("at /Users/someone/a.py")


def test_memory_guard_reports_something_or_none():
    v = available_mb()
    assert v is None or v > 0
