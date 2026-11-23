# Web + backend status (handoff to the second machine)

## Works (verified)
- Frontend: 5 routes in `api` mode (default) and `demo` mode. `tsc` clean, `eslint` 0 problems, **77 vitest tests pass**, `next build --webpack` passes. axe-core: 0 violations on all 5 routes (demo build); Lighthouse a11y 100, SEO 100 (home).
- Backend: `python -m pytest backend/tests` **13 pass**. Real Model 1 served (632 polygons, 3,358,729 ha, grid 100 m, effective 1000 m); real Model 2 job on class 3/4 units (about 2.5 s for 3 units, feasibility + 3 simulated scenarios); GeoTIFF clips (suitability, feasibility, post-restoration) work.
- `web/scripts/smoke.ps1` (pages, backend health/ready, BFF allowlist, Model 1 + Model 2 jobs through the BFF, land detail, GeoTIFF export, "no demo marker in live HTML"): **18/18 passed on three consecutive runs with 8 s gaps** against the latest build.
- Fixed since the first deployed release: (1) BFF socket error: upstream calls now use non-pooled loopback connections (`web/src/lib/bff/upstream.ts`, `Connection: close`) and idempotent GETs retry once (3 unit tests); (2) live (`api`) mode no longer says "demonstration" anywhere (metadata, landing, notes). **The supervised production server may still run the earlier build until a new release is deployed.**
- Live-mode honesty UI: Model 1 effective-vs-grid resolution, confidence = Monte-Carlo agreement not accuracy, rule-derived labels never field-verified (`RunMetaNote`); Model 2 caveats on every view (conditional on an assumed 8,000 m3/ha/yr, weak salinity/sodicity skill, simulated outcomes, 1-4 km resolution) (`Model2Caveats`); classes with zero polygons show 0.

## Open
- Browser walkthrough of the `api`-mode UI on real data (375/768/desktop) **not done**: untested risks are real Model 2 field shapes in the detail panels, large lists, and the dashboard restoration layer once Model 2 is rerun on Model 1's polygons.
- Model 2's `polygons.geojson` may still reference stand-in ids until its rerun is swapped in; the layer endpoint then returns 0 features with a note (it re-reads by mtime).
- No Playwright E2E; Lighthouse performance could not be measured (headless trace failed); no keyboard/screen-reader pass by hand; 360 px not checked (375 verified).
- Sub-area re-inference (`models.suitability.infer.run_inference` with a geometry) is not wired: region-wide views read the precomputed files. `validation.validate_geometry` is ready for it.
- CSP keeps `'unsafe-inline'` scripts (a nonce needs middleware).

## File map
`web/src/app` routes + `api/gn/[...path]/route.ts` (BFF) · `web/src/lib` contract, types, providers (`demo`, `api`), `bff/{allowlist,upstream}.ts`, `demo/` generator, `layers.ts`, `restoration.ts`, `export.ts` · `web/src/components` ui, layout, map, data, views, landing ·
`web/scripts` smoke, imagery renderer, release helpers · `web/public` tiles (6 MB), img, data (boundary) · `backend/app` main, api, jobs, db, adapters, contract, validation, security, memguard · `backend/tests` · `docs/` BACKEND_DESIGN, DESIGN_SYSTEM, ASSETS, this file, `web/README.md`, `backend/README.md`.

## How the backend finds model outputs
Relative to the app root, per region id (`jo-maan`): `models/suitability/outputs/<region>/`, `models/restoration/outputs/<region>/`, `models/restoration/runtime_data/<region>/stack.npz`, `regions/jordan_adm1.geojson`. Files are re-read on mtime/size change. Missing => `503 model_unavailable`. Data/runtime dirs come from `GREEN_NOVA_DATA` / `GREEN_NOVA_RUNTIME` (see `backend/README.md`).

## Known limits
Basemap about 66 m per pixel. Model 1 is a 1 km effective-resolution product; Model 2 feasibility is conditional on assumed water and its soil salinity/sodicity models have weak held-out skill; post-restoration outcomes are simulated. Jordan ADM1 boundary is a coarse 2006 representation, licence CC BY 2.5 (not 4.0). Demo mode data are synthetic and unrelated to the imagery.
Original-PC quirks (OneDrive junctions, `build-release.ps1`) are explained in `web/README.md`; they do not apply to a normal install (`npm ci && npm run build && npm start`).
