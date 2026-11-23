# Web handoff, Phase A (frontend, demonstration data only)

## Stack and versions
Next.js 16.4.6 (App Router, **webpack**), React 19.3.1, TypeScript 5.9.3 (strict, noUncheckedIndexedAccess), Tailwind CSS 4.3.5, MapLibre GL JS 5.24.1,
Vitest 3.2.7, ESLint 9.39.5 + eslint-config-next 16.4.6. Node 25.9 / npm 11.12. Fonts Archivo + JetBrains Mono via `next/font` (build needs network once).

## Build and run (exact)
- Dev: `cd web && npm run dev` = `next dev --webpack --port 3000 --hostname 0.0.0.0`.
- **Release build (use this)**: `powershell -ExecutionPolicy Bypass -File web\scripts\build-release.ps1 [-Out <data root>\web\release]`
  mirrors `web\` to `<data root>\web` (which owns a real node_modules), runs `npm ci` only if the lockfile changed, `npm run build`
  (= `next build --webpack`, `output: "standalone"`), then `node scripts/assemble-standalone.mjs <Out>` -> `Out\server.js`, `Out\.next\static`, `Out\public`, traced `node_modules`
  (60 MB, no OneDrive path or source tree needed).
- Run: `cd <Out>; $env:PORT='3000'; $env:HOSTNAME='0.0.0.0'; node server.js` (verified from an isolated copy).
- Evidence (final build): `http://localhost:3000/` 200 (81,446 B); same with `Host: greennova.dosteam.org` + `X-Forwarded-Proto: https` 200; /dashboard,
  /suitability, /restoration, /land/m1-jo-maan-12, /robots.txt, /sitemap.xml, /data/jordan_adm1.geojson, tiles and images all 200; canonical/og/sitemap use
  `https://greennova.dosteam.org` (`GREEN_NOVA_DOMAIN`/`NEXT_PUBLIC_SITE_URL`). Headers: CSP (prod only), nosniff, Referrer-Policy, Permissions-Policy, X-Frame-Options, COOP,
  `Cache-Control: public, max-age=0, must-revalidate` on HTML.
- **Toolchain caveats**: (1) `web/node_modules` and `web/.next` are junctions to `<data root>\web\...` (keeps ~30k files out of OneDrive). npm *replaces* a junction on
  install, so run installs in `<data root>\web` (copy package.json there, copy package-lock.json back). (2) Turbopack cannot resolve through the junction, hence `--webpack`
  everywhere. (3) Standalone tracing refuses files outside the project root, hence the release script builds in `<data root>\web`.
- Ports: only 3000 appears in scripts/config/docs (`grep -rn "localhost:\|:8000\|:3000" web --include=*.ts --include=*.tsx --include=*.json --include=*.mjs --include=*.ps1`).
  No absolute localhost URL exists in client code.

## Route map
`/` landing | `/dashboard` | `/suitability` | `/restoration` | `/land/[id]` (dynamic, `noindex`) | `/robots.txt` `/sitemap.xml` `/icon.svg` | not-found + error boundary.
Workspace routes take `?region=jo-maan`. All views: loading skeleton, empty, error + retry, offline banner; job states idle/starting/queued/running/complete/failed/cancelled.

## Component inventory
See `docs/DESIGN_SYSTEM.md` (ui, layout, map, data, views). Map: `components/map/MapView.tsx` (MapLibre, client-only, lazy); layer colouring in `lib/layers.ts`.

## Data layer the API provider must satisfy
Contract types: `web/src/lib/contract.ts` (mirrors docs/CONTRACT.md; guards `isSuitabilityProperties`, `isRestorationProperties`, `parseSuitabilityCollection`, `parseRestorationCollection`
tolerate extra properties). App types and the interface: `web/src/lib/types.ts` -> `DataProvider`:
`capabilities()`, `listCountries()`, `listRegions(country)`, `getRegionBoundary(id)`, `getSuitabilityRun(id)` (null = no analysis), `getSuitabilityPolygons(id)`,
`getRestorationLayer(id)` (region-wide Model 2, null if none), `startSuitabilityJob(id)`, `startRestorationJob({region_id, polygon_ids})`, `getJob(id)`, `cancelJob(id)`,
`getRestorationRun(jobId)` (features + `rejected[]` with reasons), `getLandDetail(m1Id)` (suitability + restoration|null + note), `exportSuitability(id, fmt)`,
`exportRestoration(jobId, fmt, {constraints, preference})`. `ProviderError` codes: not_found | unavailable | not_implemented | invalid_response | offline.
`demoProvider` (`lib/providers/demo.ts`, synthetic generator in `lib/demo/`) and `apiProvider` stub (`lib/providers/api.ts`, every method throws
"not implemented — Phase C"). Selection: `NEXT_PUBLIC_DATA_PROVIDER=demo|api`; the DEMONSTRATION DATA bar is shown unless it is `api`.
The api provider must use same-origin relative URLs only (BFF route handlers); never the FastAPI address.
Not in the contract and guessed (adapt in the mapping layer): `summary.json` container shape (UI uses `SuitabilityRun.stats[]`), `run_metadata` extras, region list.
Optional field the UI reads when present: factor `category`.

## Imagery and licences
See `docs/ASSETS.md`: Sentinel-2 L2A via Planetary Computer (attribution "Contains modified Copernicus Sentinel data [2026]"), self-hosted tile pyramid + hero/section images,
geoBoundaries gbOpen JOR ADM1 (**licence reported as CC BY 2.5, not 4.0**, coarse 2006 representation), fonts OFL. EOX cloudless = non-commercial, do not use.

## Verification (real numbers)
- `tsc --noEmit` clean, `eslint .` 0 problems, **67 unit tests pass** (contract guards, demo data coherence, equal-area geometry, providers incl. job lifecycle/failure/cancel, apiProvider stub,
  constraints/outcome maths, exports carry the demo marker, rule-based statements, WCAG contrast of every theme token pair).
- `next build` passes; 9 routes. Standalone release 60 MB; public assets: tiles 6.1 MB, img 2.6 MB.
- axe-core 4.14 (wcag2a/aa, 2.1, 2.2 AA, best-practice) on the production build: **0 violations** on /, /dashboard, /suitability (results open), /restoration (results + unit detail), /land/[id];
  `color-contrast` on the landing hero (text over imagery + scrim) is "needs review" (axe cannot compute through images; scrim is >= 74 % forest at the text).
- Lighthouse 12 CLI (mobile): accessibility 100 on / and /dashboard, SEO 100 on / (dashboard 92 before removing the non-standard `Host:` line from robots.txt, fixed). The performance and
  best-practices categories **could not be measured** (headless Chrome returned NO_NAVSTART in this environment); no performance numbers are claimed.
- Browser walkthrough: every route at 375, 768 and 1440 px, no horizontal overflow at 375/768; defects found and fixed (map container collapse, grid-area class typo, column overflow,
  invisible semantic colours via non-inline theme, header overflow at 375, legend covering the mobile map, duplicate landmark labels).
- Not done: keyboard-only walkthrough by hand (focus styles and native controls used; axe passes), real screen-reader test, 360 px check (375 verified), RTL.

## Open issues
1. Basemap is 66 m/pixel (z11); fine for context, not for 10 m field inspection.
2. Demo polygons are arbitrary synthetic shapes placed inside the Ma'an boundary; they do not correspond to the imagery (stated in the UI).
3. CSP uses `'unsafe-inline'` scripts (Next inline bootstrap); a nonce needs middleware (hardening item).
4. The demo job timers live in the page session; reloading loses a "completed this session" state (the "latest precomputed run" link restores the view).
5. `valid-source-maps` Lighthouse audit: production source maps are intentionally off.
