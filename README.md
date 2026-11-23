# GREEN NOVA AI — Discover. Restore. Grow.

Geospatial agricultural intelligence for Jordan (first region: **Ma'an Governorate**):

1. **Model 1 – Land Suitability**: classifies land into 5 classes (suitable / suitable with limitations / requires reclamation / unsuitable / excluded).
2. **Model 2 – Restoration Potential**: for land that needs reclamation or is unsuitable, estimates what limits it, whether that is reversible, a feasibility score with uncertainty, intervention scenarios, water needs and crop categories.
3. **Website** (Next.js) + **backend** (FastAPI) that serve both models' real outputs on a satellite map.

> **Read `HANDOFF_REPORT.md` first** (architecture, real validation numbers, limitations, open issues, what to do next).
> This is a research-grade MVP. Labels are rule-derived + observed evidence, **not field-verified**; the effective resolution is ~1 km. See the limitations in `HANDOFF_REPORT.md` before using any number.

## Requirements (Windows 10/11, CPU only — no GPU needed)

| Tool | Version | Notes |
|---|---|---|
| Python | 3.10 – 3.12 (developed on 3.10.11) | https://www.python.org |
| Node.js | >= 20.9 (developed on 25.9) | https://nodejs.org |
| Git | any recent | |
| RAM / disk | 8 GB RAM recommended, ~1 GB disk | Models are LightGBM + rules; **no torch/GPU is used** |

## Install (copy-paste)

```powershell
git clone https://github.com/Jafar-Al/green-nova.git
cd green-nova
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
```

What it does (you can run these by hand instead):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd web; npm ci; cd ..
```

## Load both trained models and predict (no retraining, CPU, no network)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_model_examples.ps1
```

This loads `models/suitability/checkpoints/model1_suitability_v0.1.pkl` and `models/restoration/checkpoints/{ece,esp}_lgbm.txt`, runs inference on small bundled samples (`models/*/sample_data`) and prints the results. Per-model details: `models/suitability/README.md`, `models/restoration/README.md`.

Direct commands (from the repo root, venv active or use `.\.venv\Scripts\python.exe`):

```powershell
$env:PYTHONPATH = (Get-Location).Path
# Model 2, full region, using Model 1's committed outputs (about 4 minutes on CPU, <1 GB RAM)
python -m models.restoration.infer --region jo-maan --suitability-dir models/suitability/outputs/jo-maan --out out_m2
# Model 2, one geometry (about 1 second)
python -m models.restoration.infer --region jo-maan --geometry models/restoration/sample_data/sample_geometry.geojson --out out_m2_geom
# Model 1, sub-area / full region: needs the 1.13 GB runtime bundle that is NOT in the repo (see HANDOFF_REPORT.md "Excluded files").
# The portable example uses the bundled 7 MB sample instead.
```

The precomputed full-region results the website shows are committed:
`models/suitability/outputs/jo-maan/` and `models/restoration/outputs/jo-maan/`.

## Run the application

Two terminals, from the repo root:

```powershell
# 1) backend: FastAPI on 127.0.0.1:8000 (internal only)
powershell -ExecutionPolicy Bypass -File scripts\run_backend.ps1

# 2) frontend: Next.js on 0.0.0.0:3000 (production build + start; add -Dev for hot reload)
powershell -ExecutionPolicy Bypass -File scripts\run_frontend.ps1
```

Open http://localhost:3000 . Fixed ports: **web 3000, backend 8000** (never switch automatically). The browser only talks to port 3000; the Next.js server calls the backend through an allow-listed route (`web/src/app/api/gn/[...path]/route.ts`).

Health: http://127.0.0.1:8000/health and http://127.0.0.1:8000/ready (shows whether each model's outputs are available).

## Configuration

* Copy `.env.example` → your own env; web variables live in `web/.env.local` (template `web/.env.example`); backend variables are documented in `backend/.env.example` and `backend/app/config.py`.
* **Data paths**: `GREEN_NOVA_DATA` (default `%USERPROFILE%\GreenNovaData`) holds the job database/results/logs under `runtime\`. `GREEN_NOVA_APP_ROOT` overrides the repo root that contains `backend\`, `models\`, `regions\`.
* **Map layers**: region boundary `regions/jordan_adm1.geojson`; model layers are read from `models/*/outputs/jo-maan/` (GeoJSON polygons + GeoTIFF rasters). Satellite basemap: `NEXT_PUBLIC_SATELLITE_TILE_URL` (default = self-hosted Sentinel-2 tiles in `web/public/tiles`, Copernicus open data). Do **not** point it at EOX Sentinel-2 cloudless (CC BY-NC-SA), Esri or Mapbox for a commercial site without their terms. See `docs/ASSETS.md`.

## Tests

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1
```

Python: `pytest backend/tests models/suitability/tests models/restoration/tests`. Web: `npm run typecheck`, `npm run lint`, `npm test` inside `web/`.

## Repository map

* `web/` Next.js 16 + TypeScript + Tailwind + MapLibre frontend and its server-side proxy
* `backend/` FastAPI service (job queue, validation, exports) — see `backend/README.md`
* `models/suitability/`, `models/restoration/` code, checkpoints, outputs, examples, tests
* `regions/` canonical boundaries · `docs/` specs, contracts, data sources, evaluations, handoffs
* `ops/` Windows production helpers used on the original PC (supervisor, scheduled tasks, health check, Cloudflare helper)
* `scripts/` setup / run / test helpers for a new machine

## Data licences and attribution

Raw datasets are **not** in the repo. Exact sources, versions, licences and download/rebuild commands: `docs/DATA_SOURCES.md`, `docs/DATA_SOURCES_model1.md`, `docs/DATA_SOURCES_model2.md`. Attribution required by the sources (e.g. "Contains modified Copernicus Sentinel data", SoilGrids, ESA WorldCover, IO-LULC, OpenStreetMap contributors, geoBoundaries) must be kept in any derived product. Two open licence questions (SOTWIS, OpenStreetMap-derived restrictions) are listed in `HANDOFF_REPORT.md`. No software licence has been chosen yet.
