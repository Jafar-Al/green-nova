# Backend design and integration

Topology: browser -> your TLS-terminating reverse proxy / platform -> Next.js **0.0.0.0:3000** -> server-side BFF
(`web/src/app/api/gn/[...path]/route.ts`) -> FastAPI **127.0.0.1:8000** (`backend.app.main:app`, ONE uvicorn worker, cwd = `<app root>`).
Browsers never talk to FastAPI. `BACKEND_URL` is a server-only env var and must be loopback (enforced in code).

## Layout
`backend/app/`: `main.py` (app factory, /health, /ready, handlers) · `api.py` (routes) · `jobs.py` (queue + persistence) · `db.py` (SQLite) · `adapters/{base,suitability,restoration}.py` ·
`contract.py` (CONTRACT.md validators) · `validation.py` · `security.py` · `memguard.py` · `regions.py` · `config.py` · `errors.py` · `logging_setup.py`. Tests: `backend/tests/test_api.py` (13, pytest).
Web side: `web/src/lib/bff/allowlist.ts` (pure, 7 vitest cases), `web/src/lib/providers/api.ts` (apiProvider), `web/scripts/smoke.ps1`.

## Endpoints (all JSON; errors are `{"error":{"code","message","model"?}}`, no paths, no traces)
| Backend | BFF (browser) | Notes |
|---|---|---|
| `GET /health` | - | liveness, no I/O, never rate limited |
| `GET /ready` | - | 200 `ready` or `degraded` (a model's files missing, reported per model); **503 only if the job store or region boundaries are broken** |
| `GET /v1/regions` | `GET /api/gn/regions` | regions from `regions/jordan_adm1.geojson` + per-model availability |
| `GET /v1/regions/{r}/boundary` | same | |
| `GET /v1/regions/{r}/suitability/run` | same | per-class stats, metadata (grid vs effective resolution, confidence method, label basis) from the model's real files; 503 if Model 1 outputs missing |
| `GET /v1/regions/{r}/suitability/polygons` | same | validated Model 1 polygons (632 for Ma'an, 5.6 MB) |
| `GET /v1/regions/{r}/restoration/layer` | same | **slim** Model 2 layer: simplified geometry + 6 properties, only units linked to current Model 1 ids (full file is 43 MB, never sent to browsers) |
| `POST /v1/jobs` `{kind: suitability\|restoration, region_id, polygon_ids?}` | `POST /api/gn/jobs` | 202 + job, or 200 + `cached:true` |
| `GET /v1/jobs/{id}` `POST /v1/jobs/{id}/cancel` `GET /v1/jobs/{id}/result` | same | states queued/running/succeeded/failed/cancelled; result survives restarts |
| `GET /v1/land/{m1-id}` | same | Model 1 feature + Model 2 feature (if any) + note |
| `GET /v1/land/{m1-id}/geotiff?layer=suitability\|feasibility\|post_restoration` | same | rasterio mask/clip of the real model raster to the unit; attachment |
GeoJSON/CSV/HTML-report exports are built in the browser from the real results with the same tested builders as the demo, with the demo marker OFF. PDF = print the HTML report.
No `/docs`, `/redoc`, `/openapi.json`, no admin/debug routes, no CORS middleware.

## Models
- Both adapters read the models' **real output files** (`models/<m>/outputs/<region>/polygons.geojson`, `run_metadata.json`, rasters). Missing files => 503 `model_unavailable` ("not available for this region yet"), never a crash, never sample data.
- Files are re-read by `(path, mtime, size)`, so Model 2's atomic output swap is picked up without a restart. Features that fail the contract validators are dropped and counted (`rejected_features`), never repaired.
- Region-wide views use the precomputed outputs. A "suitability job" validates and registers the precomputed Model 1 result (full re-inference took 271 s; `run_inference` is wired as a follow-up for sub-area geometry).
  A "restoration job" runs the real Model 2 engine in-process (`models.restoration.infer.run_region(..., polygon_ids, raster=False)`): about 2.5 s for 3 units, runtime data loaded once and cached by Model 2. Units of class 5 / 1 / 2 are returned in `rejected` with the reason (class 5 is never restorable).
- Checkpoints are loaded by the models themselves and never retrained here. Model 2's feasibility is **conditional on an assumed 8,000 m3/ha/yr water allocation**; the UI shows this on every Model 2 view (`Model2Caveats`), plus Model 1's effective-vs-grid resolution and "confidence is Monte-Carlo agreement, not accuracy" (`RunMetaNote`).

## Jobs, caching, limits
SQLite `<data root>\runtime\jobs.sqlite` (WAL) + `runtime\jobs\<id>\result.json`. Cache key = sha256(kind, model, model_version, region, params[, Model 1 version]). One worker thread = **one heavy job at a time**;
bounded queue (`GN_MAX_QUEUE=6`, then 429 `queue_full`); per-IP: 2 active jobs, 30 jobs/hour, 240 requests/min; job timeout 1800 s (cooperative, checked in the progress callback); cancel supported.
**Memory guard**: a job only starts if >= `GN_MIN_FREE_MB` (2500) MB of physical RAM is free (Win32 `GlobalMemoryStatusEx`); otherwise it waits up to 120 s, then fails `insufficient_memory`.
Jobs that were queued/running when the process died are marked failed `interrupted` at startup; completed ones persist.

## Validation and security
- region ids `^[a-z]{2}-[a-z0-9]{2,30}$` and must exist; polygon ids `^m1-<region>-<n>$`, deduplicated, <= 500, **matched against the current Model 1 id set** (unknown ids rejected, not guessed); job ids 32-hex; unknown JSON fields rejected; body limit 256 KB (BFF 64 KB).
- Geometry validators (`validation.validate_geometry/validate_bbox`): Polygon/MultiPolygon only, finite coordinates, <= 5000 vertices, area cap, entirely inside the region bbox. (Ready for a drawn-area endpoint; not exposed yet.)
- BFF: explicit allowlist table rebuilds each upstream path from validated parts (no pass-through), forwards only `X-GN-Client-IP` (from `CF-Connecting-IP` / `X-Forwarded-For` set by the reverse proxy; the backend honours it only from loopback peers), 90 s timeout, content-type allowlist, loopback-only `BACKEND_URL`.
- Headers: API sends nosniff, no-store, no-referrer, `default-src 'none'`, CORP same-origin; Next sends CSP (`default-src 'self'`, `worker-src blob:` for MapLibre, `frame-ancestors 'none'`), X-Frame-Options, Referrer-Policy, Permissions-Policy, COOP. TrustedHost allows loopback only. No secrets exist in the client bundle (only `NEXT_PUBLIC_*` non-secrets).
- Logs: JSON lines `<data root>\runtime\logs\backend.log` (rotating 5 MB x 5): method, route, status, ms, hashed IP; stack traces only in the file; responses and logs pass a path scrubber.

## Tests
`python -m pytest backend/tests` (13 pass: health/ready degradation, 503 for missing models, no docs/CORS/headers, validation, geometry bounds, job lifecycle + cache + restart persistence, mtime reload, rate limit, scrubbing) ·
`npx vitest run` in `web` (74 pass incl. BFF allowlist and apiProvider via mocked fetch) · `web/scripts/smoke.ps1` = full journey through :3000 -> BFF -> :8000 with the real models (exit 0/1).
Real-model checks done directly against the backend: Model 1 run (632 polygons, 3,358,729 ha, effective 1000 m, grid 100 m), Model 2 job on 3 class 3/4 units (2.5 s, feasibility high/0.979, 3 simulated scenarios), GeoTIFF clips for all three rasters.
Playwright-style browser E2E of the whole journey against the production build is **not** done yet.

## Operations
Start: `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-server-header` (cwd `<app root>`; env `GREEN_NOVA_DATA`, `GREEN_NOVA_RUNTIME`). `/health` answers without touching the models.
Deploy: `web\scripts\build-release.ps1` (builds `NEXT_PUBLIC_DATA_PROVIDER=api` by default) then `ops\release.ps1`. Demo variant: build with `NEXT_PUBLIC_DATA_PROVIDER=demo`.
