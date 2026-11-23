# Model 2 RESUME (keep current; commands run from project root with PYTHONPATH=.)
PY = python of the shared venv (see README.md) | logs: $GREEN_NOVA_DATA/logs/m2_*.log | launch long jobs detached (Start-Process -WindowStyle Hidden)

## Done (survives restarts)
- Data: WoSIS 2023 (raw\wosis, sha256 ok), Hassani 2020 points (raw\hassani2020_salinity), AfSIS AWS mirror (raw\afsis\aws_mirror), FAO docs (raw\fao_docs)
- cache\model2: wosis_topsoil.csv.gz, ece_training.csv.gz (14112 loc), esp_training.csv.gz (30204), global\ (SoilGrids 1km, WorldClim 5m bio, 30s elev)
- Soil ML DONE: checkpoints\ece_lgbm.txt, esp_lgbm.txt, soil_models_meta.json; eval\soil_models_report.json; eval\soilgrids_check.json
- Code: config, hydro, erosion, engine (MC), assemble, units, stack, outputs, infer, build_runtime, features, soilml, knowledge\{crops,interventions,sources}

## Status 06:55: runtime_data\jo-maan\stack.npz BUILT (19.8 MB, TerraClimate 2011-2020 via model1 cache); tests pass (python -m pytest models/restoration/tests -q);
## infer (stand-in) was running detached -> outputs\jo-maan ; then run eval: $PY -m models.restoration.eval.evaluate (detached) ; docs\DATA_SOURCES_model2.md written
## Next (in order; each idempotent)
1. TerraClimate monthly for Ma'an -> cache\model2\tc_jo-maan.npz :  $PY -m models.restoration.data.climate   (slow remote zarr; fallback = model1 cache terraclimate)
2. $PY -m models.restoration.build_runtime --region jo-maan  -> models\restoration\runtime_data\jo-maan\stack.npz
3. $PY -m models.restoration.infer --region jo-maan --out models\restoration\outputs\jo-maan [--suitability-dir models\suitability\outputs\jo-maan]
4. eval: models\restoration\eval\evaluate.py (class consistency, sensitivity), tests, docs\handoff\model2.md, docs\DATA_SOURCES.md entries
## Notes
- Kaggle AfSIS NOT accepted (owner instruction changed); AWS mirror used. Browser pane: don't touch.
- No absolute paths in outputs. Runtime = runtime_data only (no network).

## 07:05 STATE: outputs/jo-maan DONE (stand-in current class, 632 s). eval DONE (docs/EVAL_model2.md). handoff docs/handoff/model2.md DONE.
To use real Model 1 data when models/suitability/outputs/jo-maan exists (detached, ~11 min): python -m models.restoration.infer --region jo-maan --suitability-dir models/suitability/outputs/jo-maan --out models/restoration/outputs/jo-maan
Improvements not done: 30-yr TerraClimate, observed-analog check, AfSIS domain shift.

## 07:10 STATE: outputs/jo-maan now built from Model 1 (511 polygons, 12x3 raster draws, 231 s). Swap done (jo-maan_new -> jo-maan). Rerun with more draws: add --mc-outer 16 --mc-inner 4 and --out models/restoration/outputs/jo-maan_new then swap by rename.
