# Model 2 handoff - agricultural land restoration potential (GREEN NOVA AI)

Version `restoration-0.1.0`. Region `jo-maan`. Everything below is relative to the project root. **Restoration outcomes are simulated; there is no observed before/after data.**

## 1. Architecture (hybrid, not a recommender)
1. **Soil-property ML (observed labels):** LightGBM regressors for topsoil (0-30 cm) **ECe** (log10 dS/m) and **ESP** (log1p %), trained on measured points
   (WoSIS 2023 saturated-paste EC, CC BY / public-domain rows only + Hassani et al. 2020 measured ECe/ESP points) with 14 climate/terrain/SoilGrids covariates; 5x5-degree block CV, a held-out
   Levant+Arabian region, Mondrian split-conformal 90 % intervals (`soilml.py`, `checkpoints/`).  pH, SOC, texture, coarse fragments, bulk density, CEC come from SoilGrids 2.0 (third party,
   `ml_predicted`) with 1-sigma taken from its measured error at arid WoSIS sites (`eval/soilgrids_check.json`).  Depth-to-bedrock: SoilGrids 2017 (capped 200 cm, uninformative in Ma'an).
2. **Constraint / reversibility layer (`assemble.py`, `engine.py`):** per-unit limiting factors (salinity, sodicity, alkalinity, SOC, texture, coarse fragments, depth, slope, erosion, water, restriction) with severity,
   reversibility class and evidence tag, using FAO IDP29 Table 4 (Maas-Hoffman), FAO SB39 ESP classes, FAO-56 Kc/rooting depth, FAO SB55 relative-yield suitability classes.
3. **Intervention scenarios (5 archetypes):** drip + fresh groundwater, treated wastewater, brackish water with tolerant crops, rain-fed water harvesting, terraced irrigation; reclamation leaching (C/C0=exp(-k r), FAO 70-90 % removal per unit depth),
   gypsum (stoichiometry = FAO SB39 worked example), organic amendment (assumed range), terracing (assumed limit), water harvesting (FAO C:CA equation), drainage feasibility (probabilistic).
4. **Monte-Carlo feasibility:** nested draws (16 parameter x 4 input-noise for the raster, 32 x 6 for polygons); feasibility score = P(at least one scenario brings the best crop to relative yield >= 0.6 under the reference water allocation);
   interval = 5-95 % over parameter draws; classes cut at 0.15/0.40/0.70. Post-restoration class from the best-crop relative yield (S1>=0.8, S2 0.6-0.8, S3 0.4-0.6, N<0.4).

## 2. Files
| Path | What |
|---|---|
| `models/restoration/infer.py` | CLI + Python API (`run_region`, `analyze_geometry`, `load_runtime`) |
| `models/restoration/runtime_data/jo-maan/stack.npz` (19.8 MB) + `stack_meta.json` | ALL runtime inputs (250 m stack + native-grid climate); no network/raw data at inference |
| `models/restoration/checkpoints/{ece,esp}_lgbm.txt`, `soil_models_meta.json` | trained LightGBM boosters + conformal tables + sha256 (used at stack-build time; the deployed engine reads the pre-computed stack) |
| `models/restoration/knowledge/` | crop table (FAO IDP29 Table 4, FAO-56 Kc/Zr), intervention library, source registry with verification levels |
| `models/restoration/outputs/jo-maan/` | `restoration_feasibility.tif`, `post_restoration_suitability.tif` (SIMULATED), `feasibility_score.tif`, `*_4326.tif` previews, `polygons.geojson`, `summary.json`, `run_metadata.json` |
| `models/restoration/eval/` | `soil_models_report.json`, `soilgrids_check.json`, `restoration_eval.json`, report `docs/EVAL_model2.md` |
| `docs/DATA_SOURCES_model2.md` | datasets, sizes, licences, what was verified |

## 2b. Portable example, install, rebuild
`models/restoration/README.md` (3 commands), `examples/run_example.ps1|.py` (CPU, no network; loads checkpoints with sha256 check + `stack.npz`, analyses `sample_data/sample_geometry.geojson` and three Model 1 polygon ids; covered by `tests/test_example.py`), `requirements.txt` (exact versions), `RUNTIME_MANIFEST.json` (files NOT in the repo with sizes, sources and rebuild commands).

## 3. Interface
```
python -m models.restoration.infer --region jo-maan --suitability-dir models/suitability/outputs/jo-maan --out <dir> [--polygon-ids ID ...] [--geometry area.geojson] [--water-cap 8000] [--include-class2] [--no-raster]
```
```python
from models.restoration.infer import run_region, analyze_geometry, load_runtime
rt = load_runtime("jo-maan")                       # once per process (~0.5 s, ~150 MB RAM)
feat = analyze_geometry(geojson_geometry)          # ~1 s, contract-shaped Feature
res = run_region("jo-maan", suitability_dir=..., out_dir=..., polygon_ids=[...], progress=lambda frac, msg: ...)   # returns {"paths": {...}, "summary": {...}}
```
Typed errors: `RestorationError` > `RuntimeDataMissing`, `GeometryError`. Inputs from Model 1: `polygons.geojson` (`id`, `class_code`) and `suitability.tif`; classes 3,4 are assessed, 5 reported as `not_feasible` (restriction), class 2 only with `--include-class2`.
If no Model 1 files are found a documented **stand-in** current-class map is used (rule-based, flagged in `run_metadata.json` and `summary.json`); the Model 1 path is the same code with the real files.

## 4. Runtime on this machine (measured)
Region raster (537,381 cells, 16 parameter x 4 input draws = 64 draws/cell, 5 scenarios x up to 11 crops): 632 s with the stand-in mask at 16 x 4 draws; **231 s** for the delivered Model 1 run at 12 x 3 draws (single-process numpy, about 0.6 GB RSS, CPU only). Polygons: 32 x 6 draws, 511 polygons. One polygon / geometry: about 1 s. Deterministic for a fixed seed (20261122).

## 5. Checkpoints (sha256)
- `models/restoration/checkpoints/ece_lgbm.txt` 0239b4a2c064db35629cfb54af8882f75d8cc0d265f463e09c5577bc3967762b (80 rounds, 9,402 locations)
- `models/restoration/checkpoints/esp_lgbm.txt` f965557f7ca664ff3a4bbd210425c1fb9ae7a54a0ac2447fc090ea6e8c28106b (106 rounds, 8,698 locations)
Conformal tables in `soil_models_meta.json`. Deployment does not need to reload them unless the stack is rebuilt (`python -m models.restoration.build_runtime`).

## 5b. Evidence breakdown (also in run_metadata.json)
observed: slope/elevation (GLO-30), climate (TerraClimate 2011-2020). ml_predicted: ECe, ESP (own LightGBM + conformal), pH/SOC/texture/CF/BD/CEC/depth (SoilGrids). expert_rule: Maas-Hoffman/ESP tolerance, response curves, class boundaries, erosion index. simulated: interventions, post-restoration class, water requirement, time to effect, feasibility score/interval.

## 5c. Delivered run (current class from Model 1 `m1-0.1.0`, checkpoint sha256 c24c5cf0569c9d68a52f617bd44f456c07e4c38e241db1dca299043b721ed8e3; reference water 8,000 m3/ha/yr)
- Inputs: Model 1 `polygons.geojson` (classes 3, 4, 5 used; class 2 skipped unless `--include-class2`) and `suitability.tif` resampled (mode) to the 250 m grid.
- 511 polygons: 307 high-feasibility (187 class-3 + 120 class-4 polygons; 3,273,274 ha), 204 class-5 polygons = `not_feasible` (restriction, 50,006 ha). Raster: 487,044 candidate cells high, 8,627 class-5 cells not_feasible (others moderate/low: see summary.json).
- **Monte-Carlo sample counts (reduced to meet the time limit): raster 12 parameter x 3 input draws = 36 draws on all 523,848 candidate cells (no subset, 250 m grid); polygons 32 x 6 = 192 draws.** Runtime 231 s measured (CPU).
- Machine-readable caveats for the UI are in `summary.json` and `run_metadata.json` under `caveats` (assumed water allocation, `feasibility_is_conditional_on_water`, soil-model held-out skill with CI and conformal coverage, evidence classes, MC draws, effective resolution, sensitivity to water). Show `caveats.ui_banner`.
- Honest reading: with 8,000 m3/ha/yr nearly all non-restricted land is 'high' (technical feasibility conditional on water); at 3,000 m3/ha/yr the mean score is 0.03, at 5,000 0.51 (`docs/EVAL_model2.md`). Class-3/4 polygons here are large (hundreds to 100,000+ ha) and the soil inputs are ~1 km: per-polygon values are regional, not field-level.

## 5d. Sub-area / polygon queries in seconds
`analyze_geometry()`, `--polygon-ids`, `--geometry` read only `runtime_data/<region>/stack.npz` (zonal statistics on the 250 m stack + climate interpolation + Monte-Carlo for the selected units); `--no-raster` skips the region raster. About 1 s per geometry (measured 0.7 s). Typed progress callback `progress(fraction, message)`.

## 6. Known failure modes / limitations (read these)
- The ECe/ESP models have **weak skill on held-out geography** (see `docs/EVAL_model2.md`): the spatial pattern of salinity/sodicity inside Ma'an is mostly a regional prior with very wide intervals.
- SOC has no regional skill in SoilGrids at arid held-out sites; depth to bedrock is uninformative (cap).
- Water SOURCE availability/quality, groundwater depth, aquifer sustainability and wastewater plant locations are **not mapped**; feasibility is conditional on a reference water allocation (default 8,000 m3/ha/yr, a scenario condition) - see sensitivity table.
- Climate window is 2011-2020 (10 years) for the design rainfall; salinity/sodicity effective resolution ~1 km, climate ~4 km: do not read sub-km polygon values as measurements.
- Wind erosion, flash floods, frost damage, economics are not modelled. Response curves other than Maas-Hoffman/ESP classes are documented assumptions (`engine.FACTOR_ASSUMPTIONS`).
- Agreement with expert-rule labels measures consistency, not real restoration success.

## 7. Validation status (honest)
Done: block-CV and held-out-region validation of ECe/ESP (weak skill), SoilGrids arid-site error check, held-out-region pipeline consistency (no discriminating power), sensitivity analysis, ETo cross-check, 11 unit/contract/example tests. **Pending, not estimated:** observed-analog check (existing irrigated cropland vs feasibility), AfSIS/iSDA domain-shift test, Hassani global-map benchmark, 30-year climate, own pH/SOC/texture models, any calibration against real restoration outcomes (none exist). Sensitivity table was computed on the stand-in run (16x4 draws, reference water 8,000); the delivered Model 1 run uses 12x3 draws.
