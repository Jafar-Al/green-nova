# Model 2 - agricultural land restoration potential (GREEN NOVA AI)

CPU only, no network, no GPU. Python 3.10. Run all commands from the repository root. Outputs are simulated/expert-rule results, never observed restoration outcomes
(read `docs/handoff/model2.md`, `docs/EVAL_model2.md`: the salinity/sodicity models have weak held-out skill and feasibility is conditional on an assumed water allocation).

1. Install
```
python -m venv .venv && .venv\Scripts\activate && pip install -r models/restoration/requirements.txt
```
2. Example (checkpoints + `runtime_data/jo-maan/stack.npz` + sample geometry + three Model 1 polygon ids; about 1 s)
```
powershell -File models\restoration\examples\run_example.ps1          # or: python models/restoration/examples/run_example.py
python -m pytest models/restoration/tests -q
```
3. Full region with Model 1 outputs (about 4-10 min on a few CPU cores; write to a temp folder, then rename over `outputs/jo-maan`)
```
python -m models.restoration.infer --region jo-maan --suitability-dir models/suitability/outputs/jo-maan --out models/restoration/outputs/jo-maan_new --mc-outer 12 --mc-inner 3
```
Sub-area / polygons in seconds: `--polygon-ids m1-jo-maan-122 ... --no-raster`, or `--geometry models/restoration/sample_data/sample_geometry.geojson`.
Python: `from models.restoration.infer import run_region, analyze_geometry`.

Files not in the repo and how to rebuild them: `models/restoration/RUNTIME_MANIFEST.json` (only needed to retrain or rebuild `stack.npz`, never for inference).
