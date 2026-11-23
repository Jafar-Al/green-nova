"""Portable CPU example: classify the small sample AOI with the shipped checkpoint (no network, no GPU, no big runtime data).

Usage (from anywhere):  python models/suitability/examples/run_example.py [output_dir]
It points GREEN_NOVA_RUNTIME at ../sample_data (a 20 km x 20 km feature subset near Shobak, 7.5 MB) and prints the
class / confidence results for the AOI polygon in ../sample_data/aoi.geojson.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE.parent / "sample_data"
os.environ["GREEN_NOVA_RUNTIME"] = str(SAMPLE)          # sample features instead of the 1.13 GB runtime folder
sys.path.insert(0, str(HERE.parents[2]))                # repository root, so `models.suitability` is importable

from models.suitability.infer import run_inference  # noqa: E402


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="m1_example_"))
    geom = json.loads((SAMPLE / "aoi.geojson").read_text())
    res = run_inference("jo-maan", out, geom, device="cpu", progress=lambda f, m: print(f"[{f * 100:5.1f}%] {m}", flush=True))
    s = res.summary
    print("\nCLASS RESULTS for the sample AOI (area in ha; 1 dunum = 0.1 ha):")
    for k, v in s["classes"].items():
        if v["area_ha"] > 0:
            print(f"  class {k} {v['label']:<42} {v['area_ha']:>9.0f} ha  {v['polygon_count']:>3} polygons  share {v['share']:.1%}")
    print(f"mean confidence (Monte-Carlo agreement, not accuracy): {s['mean_confidence']}")
    gj = json.loads(Path(res.paths["polygons"]).read_text())
    for f in gj["features"][:3]:
        p = f["properties"]
        print(f"  polygon {p['id']}: class {p['class_code']} ({p['class_label']}), {p['area_ha']} ha, confidence {p['confidence']}, "
              f"limiting factor: {p['limiting_factor']}")
    print("files written:", ", ".join(sorted(Path(v).name for v in res.paths.values())))
    print(f"checkpoint {res.metadata['model_version']} sha256 {res.metadata['checkpoint_sha256'][:16]}...; device used: {res.metadata['device_used']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
