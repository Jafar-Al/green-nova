"""End-to-end smoke test on a small sub-area (skipped when the checkpoint / packaged runtime data are absent)."""
import json
from pathlib import Path

import numpy as np
import pytest

from models.suitability import config, infer
from models.suitability.package_runtime import runtime_root

CK = config.CKPT_DIR / infer.CKPT_NAME
RT = runtime_root() / "jo-maan" / "meta.json"
pytestmark = pytest.mark.skipif(not (CK.exists() and RT.exists()), reason="checkpoint or runtime data not built")

# ~12 km x 8 km box around Shobak highlands (lon/lat, EPSG:4326)
GEOM = {"type": "Polygon", "coordinates": [[[35.50, 30.45], [35.62, 30.45], [35.62, 30.52], [35.50, 30.52], [35.50, 30.45]]]}


def test_subarea_query_outputs_and_determinism(tmp_path):
    calls = []
    r1 = infer.run_inference("jo-maan", tmp_path / "a", GEOM, progress=lambda f, m: calls.append(f))
    r2 = infer.run_inference("jo-maan", tmp_path / "b", GEOM)
    assert calls and calls[0] == 0.0 and calls[-1] == 1.0 and all(0 <= c <= 1 for c in calls)
    import rasterio
    with rasterio.open(r1.paths["suitability"]) as a, rasterio.open(r2.paths["suitability"]) as b:
        A, B = a.read(1), b.read(1)
        assert a.nodata == 0 and a.dtypes[0] == "uint8"
    assert np.array_equal(A, B)                                   # deterministic
    assert set(np.unique(A)) <= {0, 1, 2, 3, 4, 5}
    gj = json.loads(Path(r1.paths["polygons"]).read_text())
    assert gj["features"], "no polygons"
    p = gj["features"][0]["properties"]
    for k in ("id", "class_code", "class_label", "area_ha", "area_dunum", "confidence", "confidence_method",
              "class_probabilities", "factors", "centroid", "effective_resolution_m", "provenance"):
        assert k in p
    assert abs(p["area_dunum"] - p["area_ha"] * 10) < 0.2
    assert set(p["class_probabilities"]) == {"1", "2", "3", "4", "5"}
    assert all(f["status"] in ("favourable", "marginal", "limiting", "restricted") for f in p["factors"])
    for name in ("polygons.geojson", "summary.json", "run_metadata.json"):          # no absolute local paths in outputs
        txt = (tmp_path / "a" / name).read_text()
        assert "C:\\\\" not in txt and "C:/" not in txt and "Users" not in txt, name
    s = r1.summary
    assert abs(sum(v["area_ha"] for v in s["classes"].values()) - s["total_area_ha"]) < 1.0


def test_typed_errors(tmp_path):
    with pytest.raises(infer.RegionNotFoundError):
        infer.run_inference("jo-nowhere", tmp_path)
    with pytest.raises(infer.InvalidGeometryError):
        infer.run_inference("jo-maan", tmp_path, {"type": "Point", "coordinates": [0, 0]})
