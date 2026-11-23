# Model 1 RESUME (keep current)

Python: `C:\GreenNovaData\venv\Scripts\python.exe` ; run from project root `green nova`. Long jobs: detached
`Start-Process -WindowStyle Hidden` with logs in `C:\GreenNovaData\logs\m1_*.log`. All stages idempotent (skip existing files).
Stack (100 m EPSG:6933 grid, Jordan) = `C:\GreenNovaData\cache\model1\stack\*.tif`; shared covariates `C:\GreenNovaData\cache\covariates\`.

## STATUS: v0.1 DELIVERED (checkpoint, runtime data, jo-maan outputs, handoff, 3-fold LORO). Remaining = improvements only.
## Done (as of resume)
- regions/jordan_adm1.geojson, grid, adm1 raster (regions.py)
- covariate caches: dem_cop30, soilgrids (64 layers), worldclim_prec, terraclimate (10-yr 2011-2020), jrc_gsw
- stack: sotwis_*, restriction_code (OSM, huge 129,639 km2 polygon dropped), wc2020/2021 + io2017/2021/2023 crop fractions, label_cult.tif (labels.py)
- code: acquire_*.py, terrain.py, build_stack.py, rules.py, fusion.py, train.py, infer.py, polygons.py, package_runtime.py, tests/
- DATA_SOURCES text in docs/DATA_SOURCES_model1.md

## Next (in order)
1. `python -m models.suitability.terrain`           (-> stack/elev_mean, slope_*, tpi_*, ...)  [check stack/slope_mean.tif exists]
2. `python -m models.suitability.build_stack`       (-> ph_0_30, ppt_annual, tmin_coldest ... + SOTWIS fill)
3. `python -m models.suitability.train prep`        (rule cache), then `train loro 6` (spatial CV report -> reports/loro_results.json),
   `train final 8` (checkpoint -> checkpoints/model1_suitability_v0.1.pkl + reports/final_training.json)
4. `python -m models.suitability.package_runtime --region jo-maan` (-> C:\GreenNovaData\runtime\model1\jo-maan)
5. `python -m models.suitability.infer --region jo-maan --out models/suitability/outputs/jo-maan`
6. docs/handoff/model1.md, tests for infer, merge docs/DATA_SOURCES_model1.md into docs/DATA_SOURCES.md, notify main.
Cut: Sentinel-2 temporal features (acquire_s2.py exists, 1 tile done, NOT used), CNN, EuroSAT ablation, Sentinel-1.
