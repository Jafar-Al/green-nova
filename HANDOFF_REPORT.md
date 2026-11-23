# HANDOFF REPORT — GREEN NOVA AI

**Instruction to the next Claude Code session:**
"Read HANDOFF_REPORT.md and README.md first. Inspect the existing implementation and checkpoints. Do not retrain either model unless explicitly necessary. Continue from the saved state."

Written 2026-11-23 on the original PC (Windows 11 Pro, RTX 4060 Ti, 15.8 GB RAM) so work can continue on a second CPU-only Windows machine. Everything below was verified against files unless marked *(reported by agent, not independently verified)*.

---------------------------------------------------------------------------------------------------

## 1. What this is and what state it is in

A geospatial platform for Jordan (first region **jo-maan**, Ma'an Governorate): two models + website + backend.

| Part | State |
|---|---|
| Model 1 suitability | Trained, checkpoint saved, inference works on CPU, full Ma'an outputs generated and verified. Validation partial (3 leave-governorate-out folds). |
| Model 2 restoration | Hybrid (ML soil models + FAO-based rule engine + Monte-Carlo) built, outputs generated from Model 1's real polygons. Soil ML has **almost no held-out skill**; feasibility is **conditional on an assumed water allocation**. |
| Backend (FastAPI) | Written, 13 tests pass, ran on the old PC at 127.0.0.1:8000. |
| Frontend (Next.js) | 5 routes, 77 unit tests pass, axe 0 violations, ran on the old PC at 0.0.0.0:3000. Browser walkthrough on real data **not done**. |
| End-to-end smoke | `web/scripts/smoke.ps1`: 18/18 passed three times in a row (agent-run, on its own copy with the latest fixes). The version running on the old PC was one build older (had an intermittent proxy bug). |
| Public deployment | **NOT working.** https://greennova.dosteam.org returned HTTP 522 although the app answered locally. Cloudflare access was never available (see §9). |

## 2. Architecture

```
Browser ──HTTPS──> Cloudflare Tunnel (owner-managed) ──> Next.js 0.0.0.0:3000
                                                          │  server-side allow-listed BFF  web/src/app/api/gn/[...path]/route.ts
                                                          ▼
                                       FastAPI 127.0.0.1:8000 (ONE worker, internal only)
                                          │  SQLite job store + result files (GREEN_NOVA_RUNTIME)
                                          │  bounded queue: 1 heavy job at a time, memory guard, per-IP limits
                                          ├─ reads precomputed  models/suitability/outputs/jo-maan/*   (Model 1)
                                          ├─ reads precomputed  models/restoration/outputs/jo-maan/*   (Model 2)
                                          └─ runs Model 2 live per selection (about 1–2.5 s) via models.restoration.infer
```
Model 1 **sub-area re-inference is not wired** into the backend (region-wide views read precomputed files). Fixed ports: web 3000, backend 8000. Data contract between models and website: `docs/CONTRACT.md`.

## 3. Repository structure
`web/` frontend · `backend/` FastAPI · `models/suitability/` · `models/restoration/` · `regions/jordan_adm1.geojson` · `docs/` · `ops/` (old-PC production helpers) · `scripts/` (new-machine helpers). Details: `README.md`. Per-agent docs: `docs/handoff/model1.md`, `docs/handoff/model2.md`, `docs/handoff/web-phaseA.md`, `docs/handoff/web-status.md`, `docs/BACKEND_DESIGN.md`, `docs/DESIGN_SYSTEM.md`, `docs/ASSETS.md`, `docs/EVAL_model2.md`.

## 4. Work completed by the three agents (plus the lead)
* **Model 1 agent** — grid (100 m, EPSG:6933), covariate acquisition (DEM, SoilGrids, WorldClim, TerraClimate, WorldCover, IO-LULC, SOTWIS, OSM restrictions), rule engine, LightGBM ensemble, fusion, inference CLI/API, polygons, outputs, 9 tests, portable example, handoff docs.
* **Model 2 agent** — WoSIS/Hassani soil data → ECe and ESP LightGBM models with conformal intervals; constraint/reversibility engine (FAO), nested Monte-Carlo feasibility, 5 scenario archetypes, 11 crops; inference CLI/API (about 1 s per geometry), outputs, evaluation, 11 tests, portable example.
* **Website agent** — complete frontend (5 routes), design system, FastAPI backend, BFF, job queue, exports (GeoJSON/CSV/HTML report/GeoTIFF clip), tests, smoke script, docs.
* **Lead** — environment (shared venv), ops layer (`ops/`: supervisor, watchdog, health check, installer, release script, Cloudflare helper, security checker), Kaggle/consent handling, integration and verification, this handoff.

## 5. Model checkpoints and exact paths

| Model | File | Size / hash |
|---|---|---|
| Model 1 | `models/suitability/checkpoints/model1_suitability_v0.1.pkl` | 19,490,352 B, sha256 `c24c5cf0569c9d68a52f617bd44f456c07e4c38e241db1dca299043b721ed8e3` |
| Model 2 ECe | `models/restoration/checkpoints/ece_lgbm.txt` (LightGBM text model) | hash in `models/restoration/checkpoints/soil_models_meta.json` |
| Model 2 ESP | `models/restoration/checkpoints/esp_lgbm.txt` | same |
| Model 2 runtime inputs | `models/restoration/runtime_data/jo-maan/stack.npz` (19.8 MB, in repo) | in `run_metadata.json` |

Outputs (committed): `models/suitability/outputs/jo-maan/{suitability.tif, confidence.tif, class_probabilities.tif, suitability_wgs84.tif, polygons.geojson (632 polygons), summary.json, run_metadata.json}` and `models/restoration/outputs/jo-maan/{restoration_feasibility.tif, post_restoration_suitability.tif (SIMULATED), feasibility_score.tif, *_4326.tif, polygons.geojson (511 polygons), summary.json, run_metadata.json}`.

## 6. Architectures and training configuration (details in the handoff docs)
* **Model 1** — FAO-style limiting-factor rule engine (12 factors with reversibility) + 5-model LightGBM ensemble with isotonic calibration. Trained on **observed cultivation** (ESA WorldCover 2021 AND IO-LULC 2021 agreement, kappa 0.47) from terrain/soil/climate features (37). Fused with OSM/WorldCover restriction masks (class 5) and an observed-cultivation cap at class 2. 100 m grid; `effective_resolution_m = 1000`. Confidence = Monte-Carlo agreement over 24 draws of input uncertainty — **not accuracy**. Sentinel-2 enters only through the land-cover labels. Full hyper-parameters, feature list and thresholds: `docs/handoff/model1.md`.
* **Model 2** — LightGBM (log ECe, ESP) trained on measured WoSIS 2023 and Hassani 2020 points, conformal 90% intervals; pH/SOC/texture/depth from SoilGrids (third party, not retrained); FAO IDP29/SB39/FAO-56 constraint and water-requirement equations; nested Monte-Carlo (raster 12×3 draws/cell, polygons 32×6); feasibility is evaluated for an **assumed 8,000 m³/ha/yr water allocation**. Parameters/assumptions: `docs/handoff/model2.md`, `engine.FACTOR_ASSUMPTIONS`.
* CPU inference: Model 1 full Ma'an 271–338 s, peak 1.54 GB RAM, bit-identical re-run, about 1.5 s for a 12×8 km query. Model 2 full region 231 s, about 0.6 GB RAM, about 1 s per geometry.

## 7. Actual validation results (real numbers, nothing estimated)
**Model 1** (leave-governorate-out, 3 folds Ma'an | Karak+Tafilah | Mafraq; calibrated): AUC 0.845 / 0.960 / 0.991; AP 0.205 / 0.681 / 0.696; ECE 0.001 / 0.033 / 0.004. Baselines AUC: rule index 0.803 / 0.783 / 0.971, climate-only GBM 0.800 / 0.607 / 0.974. Ma'an AUC CI is wide (0.57–0.97). Pooled 5-fold spatial-block AUC 0.989 is **optimistic** (random 30 km blocks). Temporal new-cropland AUC in Ma'an only 0.61. Not done: other CV folds, EuroSAT ablation, Sentinel-1/2 features, GAEZ cross-check.
Ma'an result (ha): class 1: **0** · class 2: 35,449 · class 3: 492,750 · class 4: 2,780,524 · class 5: 50,006 (1 dunum = 0.1 ha). With the observed-cultivation override off, rules put 52% of observed farms in class 4 and 16% in class 3 (rules+ML: 26% / 31%); the delivered map shows 92% of them in class 2 only because of the override. Thresholds were deliberately not retuned.

**Model 2** (Levant+Arabia region held out; 5° block CV):
| Target | Block-CV R²(log) | Held-out R²(log) | Held-out 95% CI | Conformal 90% coverage (held-out) |
|---|---|---|---|---|
| ECe | 0.22 | 0.01 | −0.08 … 0.27 | 0.87 |
| ESP | 0.18 | 0.01 | −0.99 … 0.13 | 0.905 |
Both beat a global-median baseline but **within-region salinity/sodicity skill is essentially nil**. SoilGrids at arid sites: pH RMSE 0.34, SOC RMSE 0.55 (R² ≈ 0), sand RMSE 10.8, clay RMSE 9.2. Pipeline-consistency check has no discriminating power (104 profiles, Spearman 0.04). Output: 511 polygons (307 high feasibility; 204 class-5 not_feasible); raster 523,848 cells: 91.6% high, 6.7% moderate, 0.1% low, 1.6% not_feasible. Sensitivity to water: 3,000 m³/ha → mean score 0.03; 5,000 → 0.51 (from the earlier stand-in run). Pending (not estimated): observed-analog cropland check, AfSIS domain shift, Hassani-map benchmark, 30-year climate, own pH/SOC/texture models, more MC draws.

## 8. Dataset sources and licence notes (full list: `docs/DATA_SOURCES*.md`)
Used: SoilGrids 2.0, WorldClim 2.1, TerraClimate (2011–2020), Copernicus DEM GLO-30, ESA WorldCover 2021, IO-LULC 2021, JRC Global Surface Water, OpenStreetMap restrictions (ODbL), SOTWIS, geoBoundaries JOR ADM1 (**CC BY 2.5**), WoSIS 2023-12 (public-domain and CC BY rows only; NC rows excluded), Hassani 2020 salinity points (CC BY 4.0), FAO publications (IDP29, IDP56, SB39, SB55). Sentinel-2 imagery for the website basemap/hero (Copernicus, free and open).
Audited and **not used in any model**: Kaggle EuroSAT (land cover, not suitability), Kaggle AfSIS competition (transformed values, no coordinates, no EC; the public AWS `s3://afsis` original data was downloaded but not used), Kaggle AgriYield 2025 (no coordinates, **CC BY-NC-SA 4.0**; the zip could not be retrieved through the browser pane).
Open licence issues: **SOTWIS** (CC BY 3.0 vs non-commercial text — unresolved); OSM restrictions incomplete (WDPA needs a click-wrap acceptance by the owner; one 129,639 km² OSM polygon was dropped). Review before any commercial use.

## 9. Known limitations and unresolved issues
1. **Public access (Cloudflare).** greennova.dosteam.org → HTTP 522 while the app answered locally (also with the public Host header). No API token or signed-in dashboard was ever available; nothing on Cloudflare was changed. `ops/cloudflare/configure-greennova.ps1` is ready (dry-run by default; changes only that hostname's ingress rule and DNS record; needs user env var `CLOUDFLARE_API_TOKEN`, scopes Zone:DNS:Edit, Zone:Zone:Read, Account:Cloudflare Tunnel:Edit). Likely cause is Cloudflare-side routing (a connected tunnel with a down origin normally returns 502, not 522).
2. Model 1: ~1 km effective resolution; class 1 empty in Ma'an; labels rule-derived + observed, not field-verified; groundwater not modelled; one cosmetic issue (1-ha class-2 slivers from the 10 ha sieve across class-5 cells).
3. Model 2: weak soil ML; feasibility conditional on the assumed water allocation; post-restoration outcomes are **simulated**; effective resolution 1–4 km; the delivered outputs predate a later clip of the ESP lower bound at 0 (outputs not regenerated).
4. Frontend/backend: browser walkthrough of live mode on real data, Playwright E2E and Lighthouse performance not done; `npm run build` on a clean machine not yet verified (plain `npm ci && npm run build && npm start`; `build-release.ps1` is only the old PC's OneDrive workaround); Model 1 sub-area re-inference not wired; large `polygons.geojson` files are served in capped/simplified form by the backend.
5. `web/next-env.d.ts` is generated by Next.js and git-ignored: run `npm run build` (or `npm run dev` once) before `npm run typecheck` on a fresh clone. Do not change `.gitattributes`: the `-text` rules keep checkpoint bytes exact so their sha256 checks pass on Windows (line-ending conversion broke them once).
6. The old PC runs a build one step older than the source (before the BFF retry/stale-text fix); redeploy there if needed.

## 10. Current backend and frontend status
Both started and passed the smoke test on the old PC (ports 8000 and 3000, supervised by scheduled tasks `GreenNova-backend`, `GreenNova-frontend`, `GreenNova-watchdog`; run folder `C:\GreenNovaRun`, data folder `C:\GreenNovaData` — **old PC only**). A real reboot test was not done. Details of the ops layer: `ops/greennova.ps1 help`.

## 11. Commands to resume development / run everything on another Windows machine
```powershell
git clone https://github.com/Jafar-Al/green-nova.git
cd green-nova
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1        # venv + pip + npm ci (CPU only)
powershell -ExecutionPolicy Bypass -File scripts\run_model_examples.ps1   # loads both checkpoints, predicts, no retraining
powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1            # all tests
powershell -ExecutionPolicy Bypass -File scripts\run_backend.ps1          # terminal 1  -> http://127.0.0.1:8000/ready
powershell -ExecutionPolicy Bypass -File scripts\run_frontend.ps1         # terminal 2  -> http://localhost:3000
powershell -ExecutionPolicy Bypass -File web\scripts\smoke.ps1            # end-to-end smoke (backend + frontend running)
```
Everything is CPU-only; nothing needs a GPU.

## 12. Remaining tasks, in priority order
1. **Cloudflare public routing** (owner must provide a signed-in dashboard or a scoped token as a *user environment variable*, never in chat) → run `ops\cloudflare\configure-greennova.ps1` dry-run, then `-Apply`; verify https://greennova.dosteam.org externally.
2. Verify a clean-machine install: `scripts\setup_windows.ps1` then `scripts\run_tests.ps1`, fix any gaps; verify `npm run build && npm start` on a plain checkout.
3. Browser walkthrough of live mode on real data (375 / 768 / desktop), then Playwright E2E.
4. Model 1: investigate farm-scale agreement (why rules put 52% of observed farms in class 4), add Sentinel-1/2 features and GAEZ cross-check, run remaining LOGO folds, resolve SOTWIS licence and add WDPA restrictions (needs owner acceptance), wire sub-area re-inference (needs the runtime bundle, §13).
5. Model 2: replace the assumed 8,000 m³/ha/yr with mapped water availability (groundwater/treated wastewater/rainfall harvesting), own pH/SOC/texture models, more MC draws, 30-year climate, observed-analog cropland check.
6. Production on a Windows host: `ops\greennova.ps1 install` (one administrator approval), reboot test, Lighthouse performance.
7. Choose a software licence; final licence/attribution review.

## 13. Files intentionally excluded from GitHub (and why)
| What | Size | Why / how to get it |
|---|---|---|
| Model 1 runtime bundle `C:\GreenNovaData\runtime\model1\jo-maan\{features.npy, region_mask.npy, meta.json,…}` | 1.13 GB | Exceeds GitHub limits. Needed only for Model 1 sub-area/full re-inference. Rebuild: `models/suitability/RUNTIME_MANIFEST.json` (sizes, sha256, commands) — or copy the folder from the old PC. The 7 MB sample in `models/suitability/sample_data` runs the example without it. |
| Raw datasets and caches (`C:\GreenNovaData\raw`, `cache`) | about 8 GB | Licences/size; download scripts and exact sources in `docs/DATA_SOURCES*.md`, `models/restoration/RUNTIME_MANIFEST.json`. |
| Python venv, `node_modules`, `.next` | — | Recreated by `scripts\setup_windows.ps1`. |
| `.claude/`, logs, job database | — | Local only. |
| Secrets (none were found in the repo; none were committed) | — | Placeholders only in `.env.example` files. |
No model weights were omitted: every checkpoint is in the repo (all files < 100 MB, so Git LFS was not needed).

## 14. Rules established with the owner (keep following them)
* Never accept terms, create accounts/tokens, change DNS/tunnel, or publish anything beyond what the owner explicitly authorizes in chat. Kaggle rules were accepted **only** for AgriYield 2025 (owner-authorized); AfSIS/EuroSAT were not accepted.
* Never fabricate metrics, labels or predictions; always show evidence class (observed / ml_predicted / expert_rule / simulated) and the real resolution; demo data must be labelled.
* Fixed ports: web 0.0.0.0:3000, backend 127.0.0.1:8000 (internal). Public domain: greennova.dosteam.org via the owner's existing Cloudflare Tunnel.
