# GREEN NOVA AI backend (FastAPI)

Internal API at **127.0.0.1:8000**, one uvicorn worker, called only by the Next.js BFF. It serves the models' real output files, runs Model 2 on selected units as async jobs, and clips GeoTIFFs.
Design, endpoints and security: `docs/BACKEND_DESIGN.md`. It never returns sample data: a model whose outputs are missing answers `503 model_unavailable`.

## Install
Python 3.10+ (developed on 3.10). From the repository root:
```
python -m venv .venv
.venv/Scripts/activate            # Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements.txt          # FastAPI stack + rasterio/shapely (CPU only)
pip install -r backend/requirements-dev.txt      # adds pytest/httpx
```
Real analysis additionally needs the models' own dependencies in the same environment (lightgbm, geopandas, pyproj, ...): see `docs/handoff/model1.md` and `docs/handoff/model2.md`.

## Run (fixed port, loopback only)
Run from the **app root** = the folder that contains `backend/`, `models/` and `regions/` (the repository root in development):
```
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-server-header
```
`/health` (liveness, instant) and `/ready` (job store, boundaries, per-model availability; 200 `ready` or `degraded`, 503 only if infrastructure is broken). There is no `/docs`, no CORS, no admin route.
Use exactly one worker: the job queue, memory guard and Model 2 runtime cache live in the process.

## Configuration (environment, see `.env.example`)
| Variable | Default | Meaning |
|---|---|---|
| `GREEN_NOVA_DATA` | `<home>/GreenNovaData` | data root (raw data, caches) |
| `GREEN_NOVA_RUNTIME` | `<GREEN_NOVA_DATA>/runtime` | `jobs.sqlite`, `jobs/<id>/result.json`, `logs/backend.log` |
| `GREEN_NOVA_APP_ROOT` | two levels above `backend/app` | where `models/` and `regions/` are found |
| `GN_*` limits | see `.env.example` | body size, queue length, per-IP limits, job timeout, memory guard |

## How model outputs are discovered
For region `jo-maan` the backend reads, relative to the app root and re-reading whenever a file's mtime/size changes (so an atomic output swap needs no restart):
- `models/suitability/outputs/jo-maan/{polygons.geojson, run_metadata.json, suitability.tif}` (Model 1)
- `models/restoration/outputs/jo-maan/{polygons.geojson, run_metadata.json, restoration_feasibility.tif, post_restoration_suitability.tif}` (Model 2)
- `models/restoration/runtime_data/jo-maan/stack.npz` (needed to run Model 2 on selected units: `models.restoration.infer.run_region`, in-process)
- `regions/jordan_adm1.geojson` (region catalogue and boundaries)
Features that do not satisfy the data contract (`docs/CONTRACT.md`) are dropped and counted, never repaired. Paths never appear in responses or logs.

## Tests
```
python -m pytest backend/tests -q        # 13 tests: degradation, validation, jobs, cache, restart persistence, rate limits, scrubbing
```
End-to-end with the real models and the web app: `web/scripts/smoke.ps1` (Windows PowerShell).
