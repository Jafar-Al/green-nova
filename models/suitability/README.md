# GREEN NOVA Model 1 - agricultural land suitability (all 12 governorates of Jordan)

CPU-only, no GPU, no network at inference. Python 3.10+ (tested 3.10.11, Windows). Full documentation: `docs/MODEL1_SUITABILITY.md`.

```powershell
# 1) install (from the repository root)
python -m pip install -r models/suitability/requirements.txt

# 2) portable example on the bundled 20 km x 20 km sample (7.5 MB, runs in seconds, prints class + confidence); then run the tests
powershell -File models/suitability/examples/run_example.ps1        # or: python models/suitability/examples/run_example.py
python -m pytest models/suitability/tests -q

# 3) full-region inference for any governorate (needs that governorate's runtime window, not in the repo: see RUNTIME_MANIFEST.json and
#    scripts/build_governorate.ps1; Ma'an: ~5 min and <2 GB RAM, smaller governorates seconds to minutes)
$env:GREEN_NOVA_M1_RUNTIME = "<path to runtime/model1>"
python -m models.suitability.infer --region jo-irbid --out models/suitability/outputs/jo-irbid [--geometry area.geojson]
```
Pre-computed results for all 12 governorates (`jo-ajloun`, `jo-amman`, `jo-aqaba`, `jo-balqa`, `jo-irbid`, `jo-jerash`, `jo-karak`, `jo-maan`, `jo-madaba`, `jo-mafraq`, `jo-tafilah`, `jo-zarqa`) are already in
`models/suitability/outputs/<region-id>/` (GeoTIFFs, `polygons.geojson`, `summary.json`, `run_metadata.json`); statistics are tabulated in `docs/GOVERNORATES.md`.
Checkpoint: `models/suitability/checkpoints/model1_suitability_v0.1.pkl` (sha256 in `docs/MODEL1_SUITABILITY.md`; a pickle - load only trusted files).
Classes 1-4 are rule-derived + ML + observed evidence, not field-verified; confidence is Monte-Carlo agreement under input uncertainty, not accuracy.
