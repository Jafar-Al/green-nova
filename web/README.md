# GREEN NOVA AI web

Next.js 16 (App Router, webpack) + React 19 + TypeScript + Tailwind CSS 4 + MapLibre GL JS 5. Routes: `/` `/dashboard` `/suitability` `/restoration` `/land/[id]`.
Browsers talk only to this app; the app talks to the FastAPI backend server-side (BFF at `/api/gn/*`, allowlisted, see `docs/BACKEND_DESIGN.md`).

## Ports
Web **0.0.0.0:3000** (dev and production; the npm scripts pass the port explicitly so they fail loudly if it is busy). Backend **127.0.0.1:8000** (internal only; point `BACKEND_URL` elsewhere if you host it on another loopback/private address).
TLS and the public host name are handled by whatever reverse proxy or platform you deploy behind (see `docs/DEPLOYMENT.md`).

## Install and run (generic path, any machine)
Requires Node >= 20.9 (developed on 25.9) and network access during the first build (fonts are fetched by `next/font` and self-hosted).
```
cd web
cp .env.example .env.local        # Windows: copy .env.example .env.local   (edit only if needed)
npm ci
npm run dev                        # http://localhost:3000, hot reload
npm run build && npm start         # production: next start --port 3000 --hostname 0.0.0.0
```
The backend must be running for the default (`api`) mode: see `backend/README.md`. To explore without any backend, build or run with `NEXT_PUBLIC_DATA_PROVIDER=demo`:
the UI then uses clearly labelled synthetic data and shows **DEMONSTRATION DATA - not a model prediction** on every page and in every export.

Self-contained output (optional, e.g. for containers): build with `GN_STANDALONE=1 npm run build`, copy `.next/static` to `.next/standalone/.next/static` and `public` to `.next/standalone/public`,
then run `PORT=3000 HOSTNAME=0.0.0.0 node .next/standalone/server.js`. The Dockerfiles in `deploy/` do exactly this.

## Environment (`web/.env.example`)
| Variable | Meaning |
|---|---|
| `NEXT_PUBLIC_DATA_PROVIDER` | `api` (default, inlined at build time) or `demo` |
| `BACKEND_URL` | server-only, must be loopback, default `http://127.0.0.1:8000` |
| `NEXT_PUBLIC_SITE_URL` | canonical public URL for metadata, sitemap, robots (default `http://localhost:3000`; set it to your own URL when deploying) |
| `ALLOWED_DEV_ORIGINS` | optional comma-separated extra host names allowed to use the dev server |
| `NEXT_PUBLIC_SATELLITE_TILE_URL` (+ `_ATTRIBUTION`, `_MIN_ZOOM`, `_MAX_ZOOM`, `_BOUNDS`) | basemap tile source |
No secrets are used. Data paths are configured on the backend side (`GREEN_NOVA_DATA`, `GREEN_NOVA_RUNTIME`), not here.

## Map tile source and licence caveat
Default `NEXT_PUBLIC_SATELLITE_TILE_URL=/tiles/s2/{z}/{x}/{y}.jpg` = a self-hosted XYZ pyramid rendered from Sentinel-2 L2A by `scripts/imagery/render_assets.py`
(Copernicus data: free and open, attribution "Contains modified Copernicus Sentinel data [2026]"; scene ids and licences in `docs/ASSETS.md`). A path starting with `/` is resolved against the page origin at runtime
(works on localhost and behind any proxy). Another origin must also be added to `img-src` and `connect-src` in `next.config.ts`.
**Do not point it at EOX Sentinel-2 cloudless (CC BY-NC-SA, non-commercial), Esri World Imagery or Mapbox Satellite for a public/commercial site** unless you hold the terms/keys.
Tiles are committed (`public/tiles`, ~16 MB, all of Jordan); regenerate with the script (needs a Python env with rasterio, numpy, Pillow, pystac-client, planetary-computer).

## Tests and checks
```
npm run check        # tsc --noEmit + eslint + vitest (77 unit tests: contract guards, demo data, geometry/units, providers, BFF allowlist/upstream retry, WCAG contrast of tokens)
npm run typecheck | npm run lint | npm test
powershell -File scripts/smoke.ps1 [-Base http://127.0.0.1:3000] [-Backend http://127.0.0.1:8000]   # end-to-end through BFF with the real models (Windows PowerShell; exit 0/1)
```
`docs/DESIGN_SYSTEM.md` documents tokens, type scale, components and the honesty rules. Do not commit `node_modules`, `.next`, `.env*` (only `.env.example`).
