"""Portable CPU example for Model 2 (no network, no raw data, no GPU).

Loads the committed checkpoints and runtime_data/jo-maan/stack.npz, then
  1. verifies the LightGBM checkpoints against their sha256 and runs one prediction,
  2. analyses a small sample geometry (models/restoration/sample_data/sample_geometry.geojson),
  3. analyses three Model 1 polygon ids from the committed models/suitability/outputs/jo-maan (skipped with a message if absent),
and writes results to a temporary folder (nothing is written into the repository).
Run from anywhere:  python models/restoration/examples/run_example.py      (PowerShell wrapper: run_example.ps1)
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from models.restoration import config, infer, soilml  # noqa: E402

SAMPLE = ROOT / "models" / "restoration" / "sample_data" / "sample_geometry.geojson"
M1_DIR = ROOT / "models" / "suitability" / "outputs" / "jo-maan"


def main() -> int:
    t0 = time.time()
    # 1) checkpoints
    meta = json.loads((config.CKPT_DIR / "soil_models_meta.json").read_text())["models"]
    for name, m in meta.items():
        sha = hashlib.sha256((config.CKPT_DIR / m["file"]).read_bytes()).hexdigest()
        assert sha == m["sha256"], f"checkpoint {name} sha256 mismatch"
        feat = {k: [v] for k, v in zip(m["features"], [90.0] * len(m["features"]))}
        feat.update({"bio1": [18.0], "bio12": [60.0], "dm_aridity": [60.0 / 28.0], "sg_ph": [8.0], "sg_clay": [30.0], "sg_sand": [30.0], "sg_soc": [3.0]})
        val, lo, hi, _, _ = soilml.predict(name, {k: __import__("numpy").asarray(v, dtype="float32") for k, v in feat.items()})
        print(f"checkpoint {name}: sha256 ok; sample prediction {float(val[0]):.2f} (90% interval {float(lo[0]):.2f}-{float(hi[0]):.2f}) {soilml.TARGETS[name]['unit']}")
    # 2) geometry
    geom = json.loads(SAMPLE.read_text())["features"][0]["geometry"]
    feat = infer.analyze_geometry(geom)
    p = feat["properties"]
    assert p["feasibility"]["class"] in ("high", "moderate", "low", "not_feasible") and p["scenarios"] and p["limiting_factors"] is not None
    print(f"geometry: feasibility {p['feasibility']['score']} ({p['feasibility']['class']}), interval {p['feasibility']['interval']}, best scenario {p['feasibility_meta']['best_scenario']}, "
          f"limiting factors {[l['factor'] for l in p['limiting_factors']][:3]}")
    # 3) Model 1 polygons
    if (M1_DIR / "polygons.geojson").exists():
        gj = json.loads((M1_DIR / "polygons.geojson").read_text())
        ids = [f["properties"]["id"] for f in gj["features"] if f["properties"].get("class_code") in (3, 4)][:3]
        with tempfile.TemporaryDirectory() as tmp:
            res = infer.run_region("jo-maan", suitability_dir=str(M1_DIR), out_dir=tmp, polygon_ids=ids, raster=False)
            out = json.loads((Path(tmp) / "polygons.geojson").read_text())
            assert len(out["features"]) == len(ids) and not res["standin"]
            for f in out["features"]:
                q = f["properties"]
                print(f"model1 polygon {q['source_polygon_id']}: class {q['current_class_code']} -> feasibility {q['feasibility']['class']} ({q['feasibility']['score']}), area {q['area_ha']} ha")
    else:
        print("Model 1 outputs not found (models/suitability/outputs/jo-maan): polygon-id step skipped")
    print(f"EXAMPLE OK in {time.time() - t0:.1f} s (CPU only, no network)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
