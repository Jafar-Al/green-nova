# Model 2 - agricultural land restoration potential (GREEN NOVA AI, all 12 governorates)

CPU only, no network, no GPU. Python 3.10-3.12. Run all commands from the repository root. Pre-computed results for every governorate are in `models/restoration/outputs/<region-id>/`
(statistics: `docs/GOVERNORATES.md`); each was computed from that governorate's Model 1 output. Outputs are simulated/expert-rule results, never observed restoration outcomes
(read `docs/MODEL2_RESTORATION.md`, `docs/MODEL2_EVALUATION.md`: the salinity/sodicity models have weak held-out skill and feasibility compares each scenario's water need with the renewable water generated locally, section 5e of `docs/MODEL2_RESTORATION.md`; external water sources are not mapped).

1. Install
```
python -m venv .venv && .venv\Scripts\activate && pip install -r models/restoration/requirements.txt
```
2. Example (checkpoints + `runtime_data/jo-maan/stack.npz` + sample geometry + three Model 1 polygon ids; about 1 s)
```
powershell -File models\restoration\examples\run_example.ps1          # or: python models/restoration/examples/run_example.py
python -m pytest models/restoration/tests -q
```
3. Full region with Model 1 outputs (seconds to ~10 min on a few CPU cores depending on the governorate; write to a temp folder, then rename over `outputs/<region-id>`)
```
python -m models.restoration.infer --region jo-irbid --suitability-dir models/suitability/outputs/jo-irbid --out models/restoration/outputs/jo-irbid_new
```
(defaults: 16 parameter x 4 input-noise Monte-Carlo draws per raster cell, 32 x 6 per polygon; `--mc-outer/--mc-inner` change the raster budget. Water: local renewable water from the runtime stack; `--water-cap M3_PER_HA` is an optional uniform what-if, not the default.)
The runtime stack of a governorate is built once with `python -m models.restoration.build_runtime --region <region-id>` (see `scripts/build_governorate.ps1`).
Sub-area / polygons in seconds: `--polygon-ids m1-jo-maan-122 ... --no-raster`, or `--geometry models/restoration/sample_data/sample_geometry.geojson`.
Python: `from models.restoration.infer import run_region, analyze_geometry`.

Files not in the repo and how to rebuild them: `models/restoration/RUNTIME_MANIFEST.json` (only needed to retrain or rebuild `stack.npz`, never for inference).
