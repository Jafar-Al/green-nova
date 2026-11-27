# Model 2 - agricultural land restoration potential

Version `restoration-0.1.0`. Delivered for **all 12 governorates** (`models/restoration/outputs/<region-id>/`; statistics in [`GOVERNORATES.md`](GOVERNORATES.md)). Everything below is relative to the repository root.
**Restoration outcomes are simulated; there is no observed before/after data.** Model 2 evaluates only land that Model 1 classified as 3 (requires reclamation) or 4 (currently unsuitable); class 5 is reported as restricted. It does not change Model 1's suitability result.

## 1. Architecture (hybrid, not a recommender)
1. **Soil-property ML (observed labels):** LightGBM regressors for topsoil (0-30 cm) **ECe** (log10 dS/m) and **ESP** (log1p %), trained on measured points
   (WoSIS 2023 saturated-paste EC, CC BY / public-domain rows only + Hassani et al. 2020 measured ECe/ESP points) with 14 climate/terrain/SoilGrids covariates; 5x5-degree block CV, a held-out
   Levant+Arabian region, Mondrian split-conformal 90 % intervals (`soilml.py`, `checkpoints/`).  pH, SOC, texture, coarse fragments, bulk density, CEC come from SoilGrids 2.0 (third party,
   `ml_predicted`) with 1-sigma taken from its measured error at arid WoSIS sites (`eval/soilgrids_check.json`).  Depth-to-bedrock: SoilGrids 2017 (capped 200 cm, uninformative in Ma'an).
2. **Constraint / reversibility layer (`assemble.py`, `engine.py`):** per-unit limiting factors (salinity, sodicity, alkalinity, SOC, texture, coarse fragments, depth, slope, erosion, water, restriction) with severity,
   reversibility class and evidence tag, using FAO IDP29 Table 4 (Maas-Hoffman), FAO SB39 ESP classes, FAO-56 Kc/rooting depth, FAO SB55 relative-yield suitability classes.
3. **Intervention scenarios (5 archetypes):** drip + fresh groundwater, treated wastewater, brackish water with tolerant crops, rain-fed water harvesting, terraced irrigation; reclamation leaching (C/C0=exp(-k r), FAO 70-90 % removal per unit depth),
   gypsum (stoichiometry = FAO SB39 worked example), organic amendment (assumed range), terracing (assumed limit), water harvesting (FAO C:CA equation), drainage feasibility (probabilistic).
4. **Monte-Carlo feasibility:** nested draws (16 parameter x 4 input-noise for the raster, 32 x 6 for polygons); feasibility score = P(at least one scenario brings the best crop to relative yield >= 0.6 with the water that is locally available, see section 5e);
   interval = 5-95 % over parameter draws; classes cut at 0.15/0.40/0.70. Post-restoration class from the best-crop relative yield (S1>=0.8, S2 0.6-0.8, S3 0.4-0.6, N<0.4).
   There is **no universal water allocation**: the water a unit can irrigate with is its own locally generated renewable water.

## 2. Files
| Path | What |
|---|---|
| `models/restoration/infer.py` | CLI + Python API (`run_region`, `analyze_geometry`, `load_runtime`) |
| `models/restoration/runtime_data/<region-id>/stack.npz` (0.2-19 MB per governorate) + `stack_meta.json` | ALL runtime inputs (250 m stack + native-grid climate); no network/raw data at inference. Built per governorate by `build_runtime.py` |
| `models/restoration/checkpoints/{ece,esp}_lgbm.txt`, `soil_models_meta.json` | trained LightGBM boosters + conformal tables + sha256 (used at stack-build time; the deployed engine reads the pre-computed stack) |
| `models/restoration/knowledge/` | crop table (FAO IDP29 Table 4, FAO-56 Kc/Zr), intervention library, source registry with verification levels |
| `models/restoration/outputs/<region-id>/` | `restoration_feasibility.tif`, `post_restoration_suitability.tif` (SIMULATED), `feasibility_score.tif`, `*_4326.tif` previews, `polygons.geojson`, `summary.json`, `run_metadata.json` |
| `models/restoration/eval/` | `soil_models_report.json`, `soilgrids_check.json`, `restoration_eval.json`, report `docs/MODEL2_EVALUATION.md` |
| `docs/DATA_SOURCES_model2.md` | datasets, sizes, licences, what was verified |

## 2b. Portable example, install, rebuild
`models/restoration/README.md` (3 commands), `examples/run_example.ps1|.py` (CPU, no network; loads checkpoints with sha256 check + `stack.npz`, analyses `sample_data/sample_geometry.geojson` and three Model 1 polygon ids; covered by `tests/test_example.py`), `requirements.txt` (exact versions), `RUNTIME_MANIFEST.json` (files NOT in the repo with sizes, sources and rebuild commands).

## 3. Interface
```
python -m models.restoration.infer --region <region-id> --suitability-dir models/suitability/outputs/<region-id> --out <dir> [--polygon-ids ID ...] [--geometry area.geojson] [--water-cap M3_PER_HA] [--include-class2] [--no-raster]
```
```python
from models.restoration.infer import run_region, analyze_geometry, load_runtime
rt = load_runtime("jo-maan")                       # once per process (~0.5 s, ~150 MB RAM); any governorate id works
feat = analyze_geometry(geojson_geometry, region_id="jo-maan")   # ~1 s, contract-shaped Feature
res = run_region("jo-maan", suitability_dir=..., out_dir=..., polygon_ids=[...], progress=lambda frac, msg: ...)   # returns {"paths": {...}, "summary": {...}}
```
Typed errors: `RestorationError` > `RuntimeDataMissing`, `GeometryError`. Inputs from Model 1: `polygons.geojson` (`id`, `class_code`) and `suitability.tif`; classes 3,4 are assessed, 5 reported as `not_feasible` (restriction), class 2 only with `--include-class2`.
If no Model 1 files are found a documented **stand-in** current-class map is used (rule-based, flagged in `run_metadata.json` and `summary.json`); the Model 1 path is the same code with the real files.

## 4. Runtime (CPU, measured)
Region raster (537,381 cells, 16 parameter x 4 input draws = 64 draws/cell, 5 scenarios x up to 11 crops): 632 s with the stand-in mask at 16 x 4 draws; **231 s** for the delivered Model 1 run at 12 x 3 draws (single-process numpy, about 0.6 GB RSS, CPU only). Polygons: 32 x 6 draws, 511 polygons. One polygon / geometry: about 1 s. Deterministic for a fixed seed (20261122).

## 5. Checkpoints (sha256)
- `models/restoration/checkpoints/ece_lgbm.txt` 0239b4a2c064db35629cfb54af8882f75d8cc0d265f463e09c5577bc3967762b (80 rounds, 9,402 locations)
- `models/restoration/checkpoints/esp_lgbm.txt` f965557f7ca664ff3a4bbd210425c1fb9ae7a54a0ac2447fc090ea6e8c28106b (106 rounds, 8,698 locations)
Conformal tables in `soil_models_meta.json`. Deployment does not need to reload them unless the stack is rebuilt (`python -m models.restoration.build_runtime`).

## 5b. Evidence breakdown (also in run_metadata.json)
observed: slope/elevation (GLO-30), climate (TerraClimate 2011-2020). ml_predicted: ECe, ESP (own LightGBM + conformal), pH/SOC/texture/CF/BD/CEC/depth (SoilGrids). expert_rule: Maas-Hoffman/ESP tolerance, response curves, class boundaries, erosion index. simulated: interventions, post-restoration class, water requirement, time to effect, feasibility score/interval.

## 5c. Delivered runs
All 12 governorates were computed from their own Model 1 output (current class from Model 1 `m1-0.1.0`, checkpoint sha256 c24c5cf0569c9d68a52f617bd44f456c07e4c38e241db1dca299043b721ed8e3) with the same Model 2 code, the same Monte-Carlo budget
(raster 16 x 4 = 64 draws per candidate cell, polygons 32 x 6 = 192 draws) and the water-aware method of section 5e. Per-governorate class areas, feasibility shares and water figures are generated into [`GOVERNORATES.md`](GOVERNORATES.md).
- Inputs: Model 1 `polygons.geojson` (classes 3, 4, 5 used; class 2 skipped unless `--include-class2`) and `suitability.tif` resampled (mode) to the 250 m grid.
- Class-5 polygons are `not_feasible` because of a restriction (protected, built-up, water, extreme slope), not for lack of water; the `feasibility.main_limiting_factor` and the water block of each polygon tell the two apart.
- Machine-readable caveats for the UI are in `summary.json` and `run_metadata.json` under `caveats` (`water_supply` method and evidence, `feasibility_is_conditional_on_water`, soil-model held-out skill with CI and conformal coverage, evidence classes, MC draws, effective resolution). Show `caveats.ui_banner`.
- Class-3/4 polygons are large (hundreds to 100,000+ ha) and the soil inputs are ~1 km: per-polygon values are regional, not field-level.

## 5e. Water: what is used, what is not
**Removed:** the earlier universal "reference allocation" of 8,000 m3/ha/yr applied to every unit. It had no geography, so it could not tell Irbid from Aqaba. It survives only as an explicit optional what-if (`--water-cap`, or the client-side water selector in the web UI) and is never the default.
**Used now:** for each unit, the water supplied to the irrigated scenarios is that location's **local renewable water**: the mean over 2011-2020 of max(P - AET, 0) from TerraClimate (annual precipitation minus actual evapotranspiration, ~4 km, bilinear interpolation to the unit), converted at 1 mm = 10 m3/ha. The year-to-year standard deviation is carried into the Monte-Carlo as supply uncertainty. Supply is therefore geographic (high in the north-western highlands, near zero in the eastern and southern desert) and is an *upper bound* on locally generated renewable water: no runoff capture, storage or infiltration losses are applied.
- **Required water** (net irrigation requirement, FAO-56 `ETc - effective rainfall`, plus the leaching requirement) is computed per scenario from observed climate. Effective rainfall is deducted from the requirement and is not also counted as supply from irrigation, so rainfall is not counted twice.
- **Deficit** = max(central requirement - local renewable supply, 0), reported per scenario as `water_deficit_m3_ha_yr`, and for every polygon (also the not-feasible ones) in `properties.water.irrigation` (cheapest irrigated route: requirement, local supply, deficit, surplus, share of the need met locally); **surplus** is the reverse. Where the requirement exceeds the supply, the delivered water fraction falls below 1, relative yield falls with the crop's yield-response factor Ky (`RY = 1 - Ky (1 - supply/demand)`), and feasibility falls with it, so land that needs far more water than it generates cannot be classed 'high'. Rain-fed scenarios have no irrigation demand and are unaffected.
- **Not mapped (stated, never filled with invented numbers):** groundwater recharge and sustainable abstraction limits (no basin-resolved dataset is included), fossil aquifers (e.g. Disi), surface-water storage and dam yields, national transfers and canals (King Abdullah Canal), treated-wastewater volumes and plant locations, infrastructure and water-rights allocations. `caveats.water_supply.not_mapped` lists them. A unit marked 'not feasible' could still be reclaimed with such external water if its other limits allow; a unit marked 'high' may still compete with other uses for the local surplus.
- **Resolution and uncertainty:** the climate grid is ~4 km, so the water figure is regional and a single value serves many 250 m cells.
- Actual water availability is **not established** by this method: it states what the local climate generates and how that compares with the scenario's need, nothing more.

## 5d. Sub-area / polygon queries in seconds
`analyze_geometry()`, `--polygon-ids`, `--geometry` read only `runtime_data/<region>/stack.npz` (zonal statistics on the 250 m stack + climate interpolation + Monte-Carlo for the selected units); `--no-raster` skips the region raster. About 1 s per geometry (measured 0.7 s). Typed progress callback `progress(fraction, message)`.

## 6. Known failure modes / limitations (read these)
- The ECe/ESP models have **weak skill on held-out geography** (see `docs/MODEL2_EVALUATION.md`): the spatial pattern of salinity/sodicity inside a governorate is mostly a regional prior with very wide intervals. The same applies to all 12 governorates.
- SOC has no regional skill in SoilGrids at arid held-out sites; depth to bedrock is uninformative (cap).
- Water SOURCE availability/quality, groundwater depth, aquifer sustainability, canals, dams and wastewater plant locations are **not mapped**. Feasibility compares each scenario's need with the renewable water generated locally (section 5e), an upper bound with ~4 km resolution; water that is imported or abstracted from groundwater is outside the model.
- Climate window is 2011-2020 (10 years) for the design rainfall; salinity/sodicity effective resolution ~1 km, climate ~4 km: do not read sub-km polygon values as measurements.
- Wind erosion, flash floods, frost damage, economics are not modelled. Response curves other than Maas-Hoffman/ESP classes are documented assumptions (`engine.FACTOR_ASSUMPTIONS`).
- Agreement with expert-rule labels measures consistency, not real restoration success.

## 7. Validation status (honest)
Done: block-CV and held-out-region validation of ECe/ESP (weak skill), SoilGrids arid-site error check, held-out-region pipeline consistency (no discriminating power), sensitivity analysis, ETo cross-check, 11 unit/contract/example tests. **Pending, not estimated:** observed-analog check (existing irrigated cropland vs feasibility), AfSIS/iSDA domain-shift test, Hassani global-map benchmark, 30-year climate, own pH/SOC/texture models, any calibration against real restoration outcomes (none exist). The sensitivity table in `MODEL2_EVALUATION.md` was computed on the earlier Ma'an stand-in run under uniform water allocations (legacy what-if, `eval/evaluate.py`); it is kept for the other parameters but does not describe the delivered, geographic water treatment.
