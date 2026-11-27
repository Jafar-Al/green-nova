# GREEN NOVA AI — Discover. Restore. Grow.

Satellite-informed agricultural land intelligence for Jordan. For each of Jordan's **12 governorates** it answers two questions:

1. **Where is land suitable for agriculture today?** (Model 1 — land suitability)
2. **Which land that is not suitable today could realistically be reclaimed, and how?** (Model 2 — restoration potential)

Users open the website, pick a governorate on the satellite map and see its heatmap, area statistics (hectares and dunums), and per-parcel details with the evidence behind every number. There is no image or model upload: the models and datasets run behind the scenes and the results are precomputed per governorate.

> **Scientific status.** Suitability classes are *estimates*: rule-derived (FAO-style land evaluation) combined with a machine-learning cultivation likelihood and observed land cover — never field-verified. Effective resolution is about 1 km (Model 1) and 1–4 km (Model 2), regardless of the finer working grids. Restoration outcomes are simulated; Model 2 compares each scenario's water need with the renewable water generated locally (climatic surplus), and external water sources are not mapped. Read [`docs/GOVERNORATES.md`](docs/GOVERNORATES.md) and the model documents before using any number.

## Contents
* `web/` – Next.js 16 + TypeScript + Tailwind + MapLibre frontend; a server-side allow-listed proxy (`src/app/api/gn`) is the only code that talks to the backend.
* `backend/` – FastAPI service (job queue, validation, exports). Internal only; see [`backend/README.md`](backend/README.md).
* `models/suitability/` – Model 1: rule engine + LightGBM ensemble, checkpoint, inference, per-governorate outputs.
* `models/restoration/` – Model 2: soil-property ML + constraint engine + Monte-Carlo feasibility, checkpoints, inference, per-governorate outputs.
* `regions/jordan_adm1.geojson` – governorate boundaries (geoBoundaries gbOpen JOR ADM1, CC BY 2.5).
* `docs/` – architecture, model documentation, data sources, evaluation, deployment. `scripts/` – setup, run, test and data-build helpers. `tests/` – cross-governorate integrity tests.

## Requirements (CPU only — no GPU is used or needed)
| Tool | Version |
|---|---|
| Python | 3.10 – 3.12 (developed on 3.10) |
| Node.js | ≥ 20.9 (developed on 25.9) |
| Git | any recent version |
| RAM / disk | ≈ 8 GB RAM, ≈ 1 GB disk for the repository and dependencies |

## Install
```powershell
git clone https://github.com/Jafar-Al/green-nova.git
cd green-nova
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
```
Manual equivalent (any OS):
```bash
python -m venv .venv && .venv/bin/python -m pip install -r requirements.txt     # Windows: .venv\Scripts\python.exe
cd web && npm ci
```

## Run the application
Two terminals from the repository root:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_backend.ps1      # FastAPI on 127.0.0.1:8000 (internal)
powershell -ExecutionPolicy Bypass -File scripts\run_frontend.ps1     # Next.js on 0.0.0.0:3000 (production build; -Dev for hot reload)
```
Open <http://localhost:3000>, choose Jordan and a governorate. Health: <http://127.0.0.1:8000/health>, readiness per governorate and model: <http://127.0.0.1:8000/ready>.
On Linux/macOS run the equivalent commands: `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1` from the repo root and `npm run build && npm start` in `web/`.

## The models (no retraining needed)
Both trained models are in the repository: `models/suitability/checkpoints/model1_suitability_v0.1.pkl` and `models/restoration/checkpoints/{ece,esp}_lgbm.txt`.
```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_model_examples.ps1     # loads both checkpoints, predicts on small bundled samples
```
The assessments of all 12 governorates are committed in `models/suitability/outputs/<region-id>/` and `models/restoration/outputs/<region-id>/` (region ids such as `jo-irbid`, `jo-maan`). The application serves exactly these files.
Rebuilding a governorate from the source data (hours of one-off downloads, then minutes per governorate) is documented in [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md); the per-governorate pipeline is `scripts/build_governorate.ps1`.
Model details: [`docs/MODEL1_SUITABILITY.md`](docs/MODEL1_SUITABILITY.md), [`docs/MODEL2_RESTORATION.md`](docs/MODEL2_RESTORATION.md), [`docs/MODEL2_EVALUATION.md`](docs/MODEL2_EVALUATION.md).

## Configuration
Templates: [`.env.example`](.env.example), [`web/.env.example`](web/.env.example), [`backend/.env.example`](backend/.env.example). No secrets are needed.
* `GREEN_NOVA_DATA` / `GREEN_NOVA_RUNTIME` – backend job database and result folder (default `~/GreenNovaData/runtime`).
* `BACKEND_URL` – where the web server reaches the backend (loopback/private only, default `http://127.0.0.1:8000`).
* `NEXT_PUBLIC_SITE_URL` – your public URL (canonical links, sitemap).
* `NEXT_PUBLIC_SATELLITE_TILE_URL` – basemap tiles; the default is a self-hosted Sentinel-2 pyramid of Jordan in `web/public/tiles` (see `docs/ASSETS.md` for the licence caveat when using other providers).
* Map layers and data paths: boundaries come from `regions/jordan_adm1.geojson`; model layers are read from `models/*/outputs/<region-id>/`.

## Tests
```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1
```
Python (`backend/tests`, `models/*/tests`, `tests/` for the 12-governorate integrity checks) and web (`npm run typecheck`, `npm run lint`, `npm test`). `web/scripts/smoke.ps1` is an end-to-end check against a running stack.

## Deployment
The project has no dependency on any particular host, domain or tunnel. See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for running behind your own reverse proxy and for container files.

## Data, licences and attribution
Raw datasets are not in the repository. Sources, versions, licences and rebuild steps: [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md), [`docs/DATA_SOURCES_model1.md`](docs/DATA_SOURCES_model1.md), [`docs/DATA_SOURCES_model2.md`](docs/DATA_SOURCES_model2.md).
Keep the attributions the sources require (e.g. "Contains modified Copernicus Sentinel data", SoilGrids, ESA WorldCover, Impact Observatory IO-LULC, OpenStreetMap contributors, geoBoundaries). Open licence questions (SOTWIS terms, OpenStreetMap-derived restrictions) are listed in the model documents. No software licence has been chosen yet.
