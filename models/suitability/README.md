# GREEN NOVA Model 1 - agricultural land suitability (Jordan, first region `jo-maan`)

CPU-only, no GPU, no network at inference. Python 3.10+ (tested 3.10.11, Windows). Full documentation: `docs/handoff/model1.md`.

```powershell
# 1) install (from the repository root)
python -m pip install -r models/suitability/requirements.txt

# 2) portable example on the bundled 20 km x 20 km sample (7.5 MB, runs in seconds, prints class + confidence); then run the tests
powershell -File models/suitability/examples/run_example.ps1        # or: python models/suitability/examples/run_example.py
python -m pytest models/suitability/tests -q

# 3) full-region inference for Ma'an (needs the 1.13 GB runtime folder, see RUNTIME_MANIFEST.json; ~5 min, <2 GB RAM)
$env:GREEN_NOVA_RUNTIME = "<path to runtime/model1>"
python -m models.suitability.infer --region jo-maan --out models/suitability/outputs/jo-maan [--geometry area.geojson]
```
Pre-computed Ma'an results are already in `models/suitability/outputs/jo-maan/` (GeoTIFFs, `polygons.geojson`, `summary.json`, `run_metadata.json`).
Checkpoint: `models/suitability/checkpoints/model1_suitability_v0.1.pkl` (sha256 in `docs/handoff/model1.md`; a pickle - load only trusted files).
Classes 1-4 are rule-derived + ML + observed evidence, not field-verified; confidence is Monte-Carlo agreement under input uncertainty, not accuracy.
