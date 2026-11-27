# Model 1 - agricultural land suitability

Version `m1-0.1.0`. The assessment is delivered for **all 12 governorates of Jordan** (`models/suitability/outputs/<region-id>/`, e.g. `jo-irbid`); statistics per governorate are in
[`GOVERNORATES.md`](GOVERNORATES.md). Labels for classes 1-4 are **rule-derived + ML + observed evidence, never field-verified**; no 5-class ground truth exists for Jordan.
Sentinel-2 enters **only indirectly** (ESA WorldCover / Impact Observatory land-cover labels are Sentinel-2 products); no Sentinel imagery or Sentinel-1 is read by the model.

## What it does
Per 100 m equal-area cell (EPSG:6933, 1 cell = 1 ha): (1) FAO-style limiting-factor rule engine on 12 land qualities (slope, stoniness, AWC,
salinity, sodicity, gypsum, carbonate, pH, fertility, drainage, rainfall, temperature) with reversibility -> class 1-4; (2) LightGBM ensemble
(5 spatial-block models + isotonic calibration) estimating the probability that land with these terrain/soil/climate conditions is **cultivated in
Jordan today** (observed label = ESA WorldCover 2021 AND Impact Observatory 2021 cropland agreement); (3) fusion: ML can move class 3/4 -> one class
better if calibrated P>=0.5 (not over hard irreversible limits), 1 -> 2 if P<=0.01; observed cultivation caps the class at 2; OSM/WorldCover
restrictions give class 5; (4) confidence = share of 24 Monte-Carlo draws (inputs perturbed by documented error models, ML member and thresholds resampled)
that reproduce the central class = **robustness to input uncertainty, not validated accuracy**; (5) MMU sieve 10 ha (class 5 never merged), polygons
(connected components, 50 m Douglas-Peucker), per-polygon factors computed from zonal means (value, rating, severity, evidence, importance).
Irrigation water availability (groundwater/licences) is NOT modelled: class 4 where rain <100 mm/yr means no rainfed option.

## Applying the model to every governorate
There is one checkpoint, trained once on the whole of Jordan (the 12 governorates share one 100 m grid and one set of input layers). Each governorate is processed by cutting its window from the Jordan-wide
input stack (`package_runtime.py`) and running the same inference (`infer.py`) restricted to its boundary mask, so every governorate gets its own statistics, polygons and rasters.
Input coverage was verified for all 12 governorates: soil, rainfall, elevation and land-cover layers are 100% valid inside each boundary. **Consequence for validation:** for governorates that were part of the
training data the predictions are in-sample with respect to the land-cover labels. Held-out evidence exists only for the leave-governorate-out folds listed below (Ma'an | Karak+Tafilah | Mafraq);
no independent accuracy estimate exists for the other governorates. The consistency check against observed cultivation with the override switched off is reported per governorate in `GOVERNORATES.md`.

## Training config, features, thresholds (v0.1.0)
- Target: observed cultivation (label 1 = WorldCover-2021 crop fraction >= 0.5 AND IO-LULC-2021 crop fraction >= 0.3; label 0 = both <= 0.05 and WorldCover-2020 <= 0.05; else ambiguous, excluded; restricted/built-up/water cells excluded). Jordan, 8.94 M cells in 12 governorates; 7,897,287 labelled; 109,268 positives.
- LightGBM binary, lr 0.05, num_leaves 79, min_data_in_leaf 535, feature_fraction 0.611, bagging 0.694 (freq 1), lambda_l2 74.6, max_bin 127, early stopping 40 on a held-out spatial block fold; Optuna TPE 8 trials x 3 inner spatial-block folds (30 km blocks); per fit <=150 k positives + 450 k negatives sampled; 5 models (5 spatial-block folds), best iterations 245/483/394/600/570; isotonic calibrator fit on out-of-fold predictions at natural prevalence.
- Features (37, intrinsic only; no vegetation index, no land cover, no coordinates): terrain elev_mean, elev_std, slope_mean, slope_p90, slope_frac_gt15, tpi_1km, tpi_5km, relief_5km, flat_share_5km; soil ph_0_30, soc_0_30, sand_0_30, silt_0_30, clay_0_30, cec_0_30, bdod_0_30, cfvo_0_60, sand_30_100, clay_30_100 (SoilGrids); SOTWIS sotwis_ec, esp, gypsum, caco3, drainage, awc; climate ppt_annual, ppt_cv, pet_annual, def_annual, aet_annual, aridity, tmax_mean, tmin_mean, tmin_coldest, tmax_hottest; gsw_occ; awc_ptf (Saxton-Rawls). Top gain: soc_0_30, bdod_0_30, slope, rainfall (SoilGrids may encode land cover - see validation caveat).
- Rule thresholds (rating knots at class borders R=85/60/40/25; code `rules.py`): slope deg 0/2/5/9/16/30; coarse fragments 0/15/35/55/75/95 vol%; ECe 0/2/4/8/16/32 dS/m; ESP 0/10/20/35/50/70 %; gypsum 0/20/100/250/500/800 g/kg; CaCO3 0/300/500/700/850/1000 g/kg; pH 6.5-8.4 plateau (6.0, 5.5, 5.0, 4.5 / 8.6, 8.9, 9.2, 9.5); rainfall 0/50/100/200/300/400/500 mm -> R 0/12/25/40/60/85/100; AWC 4/6/8/11/14 cm/m; SOC/CEC floor-capped (never class N). Class = restricted -> 5; irreversible factor (slope, stoniness, gypsum, temperature, rainfall) severity 4 -> 4; any severity >=3 or >=3 factors >=2 -> 3; severity >=2 or >=2 factors >=1 -> 2; else 1.
- Fusion: P_HI 0.50 (class 3/4 -> one better unless a hard limit), P_LO 0.01 (1 -> 2), observed cultivation caps at 2. MMU 10 ha; polygons simplified 50 m. Monte-Carlo K=24; error models in `run_metadata.json`.

## Portable CPU example and rebuild
`models/suitability/sample_data/` (20 km x 20 km feature subset near Shobak, 7.5 MB) + `examples/run_example.ps1|.py` (sets GREEN_NOVA_M1_RUNTIME to the sample, CPU only; tested by `tests/test_example.py`). `requirements.txt`, `README.md`.
`RUNTIME_MANIFEST.json` lists the files of the 1.13 GB runtime folder (outside the repo) with sizes, sha256 and rebuild commands. The example's tiny class-2 slivers (1 ha) come from the MMU sieve not merging across class-5 cells.

## Run
CLI: `python -m models.suitability.infer --region <region-id> --out <dir> [--geometry <geojson>] [--device cpu|cuda] [--mc-draws 24]`
(working dir = repository root, `PYTHONPATH` = repository root). `--device cuda` is accepted but the GBM runs on CPU (no GPU needed, 0 VRAM).
All governorates in one go: `scripts/build_governorate.ps1 -Region jo-irbid,jo-jerash,...`.
Python: `from models.suitability.infer import run_inference, Model, InferenceResult`;
`run_inference(region_id, out_dir, geometry=None, device="cpu", progress=cb(fraction, message), mc_draws=24, mmu_cells=10) -> InferenceResult(paths, summary, metadata, timings)`.
`Model.load()` / `Runtime.get(region)` are cached singletons: load once, serve many calls (no retraining, no network). Typed errors:
`Model1Error` > `RegionNotFoundError`, `RuntimeDataMissingError`, `InvalidGeometryError`, `CheckpointError`. `geometry` = GeoJSON (EPSG:4326) Polygon/Feature/FeatureCollection,
intersected with the region. Deterministic: Monte-Carlo noise is counter-based on global cell id (identical results for any window/chunking; test-verified).
Region-wide precompute: run the CLI without `--geometry` (the outputs of all 12 governorates are committed in `models/suitability/outputs/`).

## Files
- Checkpoint `models/suitability/checkpoints/model1_suitability_v0.1.pkl` (19,490,352 B) sha256 `c24c5cf0569c9d68a52f617bd44f456c07e4c38e241db1dca299043b721ed8e3`
  (pickle of: feature list, 5 LightGBM model strings, isotonic calibrator, fusion thresholds). Load only from this trusted path.
- Runtime inputs (self-contained, not in the repository; Ma'an alone is ~1.13 GB): `<GREEN_NOVA_DATA>/runtime/model1/<region-id>/` (`features.npy` float32 memmap, 47 layers; for Ma'an 2311 x 2607,
  `meta.json`, `region_mask.npy`, plus `regions_jordan_adm1.geojson`); override the folder with env `GREEN_NOVA_M1_RUNTIME`. Rebuild: `python -m models.suitability.package_runtime --region <region-id>`
  (needs the build cache in `<GREEN_NOVA_DATA>/cache/model1`, see `DATA_SOURCES_model1.md`). Boundaries: `regions/jordan_adm1.geojson`.
- Outputs per run (`out_dir`): `suitability.tif` (uint8 COG, 0 = nodata, classes 1-5, EPSG:6933 100 m), `confidence.tif` (uint8 0-100, nodata 255),
  `class_probabilities.tif` (5 bands uint8 percent), `suitability_wgs84.tif` (EPSG:4326 ~0.001 deg preview), `polygons.geojson` (EPSG:4326, RFC 7946, <=6 decimals; contract properties
  + extras `grid_resolution_m`, `mmu_ha`, `decision_shares`, `limiting_factor`, per-factor `native_resolution_m`), `summary.json`, `run_metadata.json`. No absolute paths inside any output.
- `effective_resolution_m` = **1000** (coarsest driving inputs: climate 1-4 km, SOTWIS 1:500 000 units, SoilGrids 250 m); the 100 m grid is a sampling grid. Do not present 100 m precision.

## Results
Per-governorate class areas, shares and polygon counts are in `outputs/<region-id>/summary.json` and tabulated in [`GOVERNORATES.md`](GOVERNORATES.md) (generated from those files).
Reading them: class 4 dominates in the south and east because most of Jordan gets <100 mm/yr rain (severity 4, irreversible in the rules); class 3 is mainly saline (SOTWIS ECe > 8 dS/m) or 100-200 mm/yr land;
the northern, wetter governorates have a much larger class 2 share. Class 1 is empty or tiny everywhere because the rules treat rainfall below ~400 mm/yr, slopes above 9 degrees and calcareous soils as limitations.

## Runtime (CPU only)
Full Ma'an (3.36 M cells): 271 s (LightGBM 139 s, Monte-Carlo 119 s); Mafraq (2.66 M cells) 144 s; the smaller governorates take seconds to a minute. Sub-area query (~12 x 8 km, ~1 k cells): ~1.5 s. Peak working set for Ma'an: **1.54 GB** (features memory-mapped, 80-row chunks);
re-runs reproduce `suitability.tif` and `confidence.tif` bit-identically (determinism verified). VRAM 0. 8 unit/e2e tests: `pytest models/suitability/tests`.

## Validation (honest)
- Rule engine alone (no training; thresholds fixed a priori from FAO guidance) vs observed cultivation, all Jordan, 8.4 M labelled cells: AUC 0.940, AP 0.580 (prevalence 0.0138);
  cultivated share by rule class 1/2/3/4 = 0.914 / 0.180 / 0.013 / 0.0018 (monotone). This is a sanity check against the same land-cover labels, not field validation.
- ML pooled 5-fold **spatial-block** OOF (30 km random blocks, Jordan, 1.5 M-cell natural-prevalence sample): AUC 0.989, AP 0.848, Brier 0.0051, raw ECE 0.004. **Optimistic**: blocks are not
  whole governorates and SoilGrids (top features: SOC, bulk density) is itself ML-predicted from covariates that may encode land cover.
- Leave-governorate-out CV (nested tuning, 10 km buffer, baselines: rule index and climate-only GBM): 3 folds finished (reduced: trials=6, 3 inner spatial folds, 10 km buffer; groups Ma'an | Karak+Tafilah | Mafraq; trained only on other governorates; 95% CI = spatial-block bootstrap, wide where few blocks). Test cells / positives: 3.25 M / 2,860 | 405 k / 14,549 | 2.40 M / 20,290.
  | held-out | prevalence | GBM calibrated AUC (CI) | AP (CI) | ECE cal (raw) | rule-index AUC / AP | climate-only GBM AUC / AP |
  |---|---|---|---|---|---|---|
  | Ma'an | 0.0009 | 0.845 (0.57-0.97) | 0.205 (0.008-0.278) | 0.001 (0.001) | 0.803 / 0.021 | 0.800 / 0.009 |
  | Karak+Tafilah | 0.036 | 0.960 (0.88-0.99) | 0.681 (0.05-0.92) | 0.033 (0.068) | 0.783 / 0.297 | 0.607 / 0.219 |
  | Mafraq | 0.008 | 0.991 (0.975-0.999) | 0.696 (0.51-0.87) | 0.004 (0.003) | 0.971 / 0.550 | 0.974 / 0.163 |
  Reading: ranking skill transfers to unseen governorates and beats the rule-only and climate-only baselines most clearly in AP; the Ma'an AUC CI is wide and its AP is low in absolute terms (rare, small farms).
  Cultivated share by rule class (held-out, 1/2/3/4): Ma'an n/a / 5.2% / 0.1% / 0.1%; Karak+Tafilah 54% / 9.8% / 0.1% / 2.8%; Mafraq 100% (90 cells) / 45% / 1.7% / 0.0%. In held-out Ma'an the ML/fusion step moved 0 cells (calibrated P never reached 0.5), i.e. the Ma'an classes are essentially the rule classes plus the observed-cultivation cap.
  Temporal hold-out (cells cultivated only in 2023, never 2017/2020/2021, vs stable non-cultivated; GBM AUC): Ma'an 0.61, Karak+Tafilah 0.68, Mafraq 0.91 (AP ~0.002-0.01): weak in Ma'an.
- Not done (cut): GAEZ comparison, EuroSAT pre-training ablation, CNN comparison, Sentinel-2/-1 features, folds for Zarqa/Aqaba, central and northern groups; no claim is made about them.

## Agreement with observed cultivation in Ma'an (also in `summary.json` / `run_metadata.json`, key `agreement_with_observed_cultivation`)
Observed cultivated = WorldCover-2021 AND IO-LULC-2021 cropland agreement (2,860 cells = 28.6 km2; land-cover products, not field survey). Delivered map (override caps these cells at class 2 by design, so this is partly circular):
class 1/2/3/4/5 = 0% / 92.4% / 2.8% / 4.8% / 0% (the 3/4 remainder is mostly the 10 ha MMU sieve removing small patches). Observed not-cultivated cells (3.24 M): 0 / 0.5% / 14.5% / 85.0% / 0%.
**Non-circular view (override switched off), observed-cultivated cells:** rules only 0% / 32.5% / 16.0% / 51.5% (classes 1/2/3/4); rules + ML 0% / 42.6% / 31.2% / 26.3%. So **most observed Ma'an farms would fall in classes 3/4
without the observed override** (rules rely on 1-4 km climate and 1:500,000 soil units, conservative at farm scale; no groundwater layer); class 1 is empty in Ma'an. Thresholds were NOT retuned.
Mean calibrated ML cultivation probability: observed-cultivated 0.558 vs observed-not-cultivated 0.0014 (in-sample: Ma'an was in the Jordan-wide training set; held-out numbers below).

## Limitations / failure modes
Labels (WorldCover vs IO LULC agree only kappa 0.47 in arid Jordan; ambiguous cells excluded; only 2,860 Ma'an positive cells = 28.6 km2); no groundwater/irrigation licence layer; SOTWIS EC (1:500 000, ~50% of
Jordan mapped > 8 dS/m) drives class 3 over huge areas and is legacy survey data (licence text conflict: CC BY 3.0 vs non-commercial - clarify with the data provider before commercial use); OSM restrictions are incomplete (a 129,639 km2 OSM "reserve" was dropped as an artefact;
WDPA not used); geoBoundaries ADM1 is a coarse 2006 boundary; Monte-Carlo error models are assumptions; class 5 vector precision is not 1 km. AgriYield 2025 (synthetic-looking, no coordinates, NC licence), AfSIS (Africa, no coordinates in the
competition file) and EuroSAT (land cover) were audited and **not used** (details in `docs/DATA_SOURCES_model1.md`).

## Possible improvements
Remaining leave-governorate-out folds, GAEZ cross-check, Sentinel-derived features, a groundwater layer, WDPA protected areas, per-farm refinement of class 3/4 (see the agreement section).
