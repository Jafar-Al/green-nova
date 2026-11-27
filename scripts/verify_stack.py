"""End-to-end verification of a RUNNING stack for all 12 governorates, through the web server's allow-listed proxy.

    python scripts/verify_stack.py [--web http://127.0.0.1:3000] [--only jo-irbid jo-maan] [--skip-jobs]

For every governorate it checks: the region list, the boundary, the Model 1 run statistics against the committed `summary.json`
(areas must match), the polygon layer (counts and areas), the Model 2 layer links to Model 1 polygons, a REAL Model 2 job on up to three
class 3/4 polygons (queued -> succeeded, simulated scenarios), the land detail and a GeoTIFF clip. Exit code 0 only when everything passes.
Needs `pip install httpx` (already in requirements.txt).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
M1 = ROOT / "models" / "suitability" / "outputs"
CKPT = ROOT / "models" / "suitability" / "checkpoints" / "model1_suitability_v0.1.pkl"
FAILS: list[str] = []


def check(ok: bool, msg: str) -> bool:
    if not ok:
        FAILS.append(msg)
        print(f"    FAIL {msg}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", default="http://127.0.0.1:3000")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--skip-jobs", action="store_true")
    ap.add_argument("--job-timeout", type=int, default=300)
    a = ap.parse_args()
    api = a.web.rstrip("/") + "/api/gn"
    c = httpx.Client(timeout=120, follow_redirects=False)
    sha = hashlib.sha256(CKPT.read_bytes()).hexdigest()

    regs = c.get(f"{api}/regions").json()["regions"]
    ids = sorted(r["id"] for r in regs)
    check(len(ids) == 12, f"expected 12 governorates, API lists {len(ids)}")
    todo = [i for i in ids if not a.only or i in a.only]
    print(f"{'region':11s} {'run':>5s} {'poly MB':>8s} {'poly s':>7s} {'layer':>6s} {'job s':>6s}  result")
    for rid in todo:
        start_fails = len(FAILS)
        info = next(r for r in regs if r["id"] == rid)
        check(info["available"] and info["models"]["suitability"]["available"] and info["models"]["restoration"]["available"], f"{rid}: models not available")
        for page in ("dashboard", "suitability", "restoration"):
            check(c.get(f"{a.web.rstrip('/')}/{page}?region={rid}").status_code == 200, f"{rid}: page /{page} not 200")

        t0 = time.time()
        b = c.get(f"{api}/regions/{rid}/boundary").json()
        check(b.get("type") == "Feature" and b["geometry"]["type"] in ("Polygon", "MultiPolygon"), f"{rid}: bad boundary")

        run = c.get(f"{api}/regions/{rid}/suitability/run").json()
        committed = json.loads((M1 / rid / "summary.json").read_text())
        check(run["demo"] is False, f"{rid}: run flagged demo")
        check(run["region_id"] == rid and run["metadata"]["region_id"] == rid, f"{rid}: run belongs to another region")
        check(run["metadata"]["checkpoint_sha256"] == sha, f"{rid}: checkpoint hash differs from the committed checkpoint")
        check(run["metadata"]["effective_resolution_m"] >= 1000 and run["metadata"]["grid_resolution_m"] == 100.0, f"{rid}: resolution disclosure missing")
        for s in run["stats"]:
            want = committed["classes"][str(s["code"])]["area_ha"]
            check(abs(s["area_ha"] - want) < 0.5, f"{rid}: class {s['code']} area {s['area_ha']} != committed {want}")
            check(abs(s["area_dunum"] - s["area_ha"] * 10) < 1.0, f"{rid}: dunum != 10 x ha for class {s['code']}")
        check(abs(sum(s["share"] for s in run["stats"]) - 1.0) < 0.002, f"{rid}: class shares do not add up to 1")
        t_run = time.time() - t0

        t1 = time.time()
        pr = c.get(f"{api}/regions/{rid}/suitability/polygons")
        t_poly = time.time() - t1
        pol = pr.json()
        n = len(pol["features"])
        check(n == run["polygon_count"], f"{rid}: {n} polygons != run.polygon_count {run['polygon_count']}")
        check(abs(sum(f["properties"]["area_ha"] for f in pol["features"]) - run["total_area_ha"]) <= 0.005 * run["total_area_ha"], f"{rid}: polygon areas do not add up to the governorate area")
        check(all(f["properties"]["class_code"] in (1, 2, 3, 4, 5) and f["properties"].get("confidence_method") for f in pol["features"]), f"{rid}: bad polygon properties")
        m1_ids = {f["properties"]["id"] for f in pol["features"]}

        lay = c.get(f"{api}/regions/{rid}/restoration/layer").json()
        check(len(lay["features"]) > 0, f"{rid}: empty restoration layer")
        check(all(f["properties"]["source_polygon_id"] in m1_ids for f in lay["features"]), f"{rid}: restoration layer not linked to this governorate's Model 1 polygons")

        t_job = float("nan")
        cand = [f["properties"]["id"] for f in pol["features"] if f["properties"]["class_code"] in (3, 4)][:3]
        if cand and not a.skip_jobs:
            t2 = time.time()
            j = c.post(f"{api}/jobs", json={"kind": "restoration", "region_id": rid, "polygon_ids": cand}).json()
            while j["state"] in ("queued", "running") and time.time() - t2 < a.job_timeout:
                time.sleep(0.5)
                j = c.get(f"{api}/jobs/{j['id']}").json()
            t_job = time.time() - t2
            if check(j["state"] == "succeeded", f"{rid}: Model 2 job ended {j['state']} {j.get('error')}"):
                res = c.get(f"{api}/jobs/{j['id']}/result").json()
                feats = res["features"]
                check(len(feats) > 0 and all(f["properties"]["source_polygon_id"] in cand for f in feats), f"{rid}: job result not for the selected polygons")
                for f in feats:
                    p = f["properties"]
                    check(p["feasibility"]["class"] in ("high", "moderate", "low", "not_feasible") and p["limiting_factors"] and p["scenarios"], f"{rid}: incomplete Model 2 result")
                    check(all(s["evidence"] == "simulated" for s in p["scenarios"]), f"{rid}: scenario not tagged simulated")
        if cand:
            d = c.get(f"{api}/land/{cand[0]}").json()
            check(d["suitability"]["properties"]["id"] == cand[0] and d["demo"] is False, f"{rid}: land detail wrong")
            g = c.get(f"{api}/land/{cand[0]}/geotiff?layer=suitability")
            check(g.status_code == 200 and g.content[:2] in (b"II", b"MM"), f"{rid}: GeoTIFF clip is not a TIFF")
        ok = len(FAILS) == start_fails
        print(f"{rid:11s} {t_run:5.2f} {len(pr.content) / 1e6:8.1f} {t_poly:7.2f} {len(lay['features']):6d} {t_job:6.1f}  {'ok' if ok else 'FAILED'}")
    print(f"\n{'ALL CHECKS PASSED' if not FAILS else str(len(FAILS)) + ' CHECK(S) FAILED'} ({len(todo)} governorates)")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
