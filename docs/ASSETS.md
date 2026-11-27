# Web assets, imagery and licences 

Every image in the site is rendered by `web/scripts/imagery/render_assets.py` from open Sentinel-2 L2A data. Nothing is hot-linked,
AI-generated, recoloured or invented: the ESA true-colour (`visual`/TCI) band is only decimated, reprojected, mosaicked and re-encoded.
Large intermediates live in `<data root>\cache\web\s2` (scenes.json, mosaic_z11.npy, crops); only optimised assets are in the repo.

## Satellite imagery
- **Source**: Sentinel-2 L2A (processing baseline 05.12), Copernicus programme, via Microsoft Planetary Computer STAC
  `https://planetarycomputer.microsoft.com/api/stac/v1`, collection `sentinel-2-l2a`, anonymous signed read of the public COGs.
- **Licence**: Copernicus Sentinel data are free, full and open (Regulation (EU) No 1159/2013; Sentinel Data Legal Notice), commercial use
  allowed. **Required attribution (shown on the map, in image captions, in the footer and `public/tiles/s2/ATTRIBUTION.txt`)**:
  "Contains modified Copernicus Sentinel data [2026]".
- **Basemap pyramid scenes**: 37 scenes covering all of Jordan (36 MGRS tiles), acquired 25 Feb - 28 Jun 2026, cloud <= 1.8 %: one low-cloud scene per MGRS tile from a narrow Feb-Mar window for consistent tone,
  plus one June 2026 scene (T36RYT) that patches a swath-edge gap. The complete scene list is in `web/public/tiles/s2/ATTRIBUTION.txt` (written by `render_assets.py meta`).
- **Landing-page crops (Ma'an)**: rendered earlier from 13 scenes acquired 25 Feb - 10 Mar 2026, cloud <= 1.8 %, one per MGRS tile:
  S2C_MSIL2A_20260302T080841_R078_T37RDQ_20260302T115912, S2A_MSIL2A_20260225T082201_R078_T37RBQ_20260225T110609,
  S2C_MSIL2A_20260302T080841_R078_T37RBP_20260302T115912, S2C_MSIL2A_20260302T080841_R078_T37RBN_20260302T115912,
  S2B_MSIL2A_20260310T081649_R121_T36RYV_20260310T124942, S2A_MSIL2A_20260307T082031_R121_T36RYU_20260307T140513,
  S2C_MSIL2A_20260302T080841_R078_T36RYT_20260302T115912, S2B_MSIL2A_20260310T081649_R121_T36RXV_20260310T124942,
  S2C_MSIL2A_20260309T075751_R035_T37RDP_20260309T162129, S2B_MSIL2A_20260304T075729_R035_T37RDN_20260304T115621,
  S2C_MSIL2A_20260302T080841_R078_T37RCP_20260302T115912, S2C_MSIL2A_20260302T080841_R078_T37RCN_20260302T115912,
  S2C_MSIL2A_20260302T080841_R078_T37RCQ_20260302T115912.
- **Verified**: scenes exist and were read; the Jordan mosaic has 0.000 % nodata inside the boundary of every one of the 12 governorates (black wedges remain only outside Jordan, in the
  masked buffer: Syria, Saudi Arabia). **Not verified**: absolute radiometric/geolocation quality beyond ESA's L2A product; seams between tiles are visible as tone steps.

| Asset | Path | Detail |
|---|---|---|
| Basemap pyramid (default map tiles) | `web/public/tiles/s2/{z}/{x}/{y}.jpg`, z5-z11, 1,227 tiles covering Jordan, ~16 MB on disk | EPSG:3857 XYZ, 256 px JPEG q80; z11 = 76.4 m/px in Web Mercator = ~66 m on the ground at 30 N. Overzoom beyond z11 enlarges pixels, adds no detail (stated in the UI). |
| Hero | `web/public/img/hero-maan-{800,1600,2400}.{avif,webp,jpg}` | bbox 35.80,30.20,36.40,30.49 (near Al-Jafr, inside Ma'an), ~24 m/px, scenes T36RYU 2026-03-07 + T37RBP 2026-03-02. 2400 px AVIF 210 KB. |
| Discover | `web/public/img/discover-{800,1200}.*` | bbox 36.04,30.20,36.20,30.304, ~13 m/px. |
| Restore | `web/public/img/restore-{800,1200}.*` | bbox 35.81,30.33,35.97,30.434, ~13 m/px. |
All three crop windows were checked to lie 100 % inside the geoBoundaries Ma'an polygon.

## Basemap configuration and production licence caveat
`NEXT_PUBLIC_SATELLITE_TILE_URL` (+ `_ATTRIBUTION`, `_MIN_ZOOM`, `_MAX_ZOOM`, `_BOUNDS`) selects the tile source; default is the self-hosted
Sentinel-2 pyramid above (works offline, no third party, licence above is sufficient for commercial use). Do **not** switch to:
- EOX Sentinel-2 cloudless: CC BY-NC-SA 4.0 for the free layers, non-commercial only;
- Esri World Imagery / Mapbox Satellite: need account terms/keys; requests would also need CSP `img-src`/`connect-src` additions.
If another origin is configured, add it to `img-src` and `connect-src` in `web/next.config.ts`. Regenerate/extend the pyramid with
`render_assets.py select | mosaic | fill | tiles | meta` (`GN_IMAGERY_SET=jordan` by default, `maan` for the old Ma'an-only extent; needs rasterio, numpy, Pillow, scipy, pystac-client, planetary-computer).

## Boundary data
- `web/public/data/jordan_adm1.geojson` (84 KB, 12 governorates) = geoBoundaries **gbOpen JOR ADM1**, build 2023-12-12, "boundaryYearRepresented 2006",
  source "geoBoundaries, Wikimedia", fetched from `github.com/wmgeolab/geoBoundaries` commit 9469f09 (`geoBoundaries-JOR-ADM1.geojson`).
- **Licence discrepancy to note**: the geoBoundaries API reports `boundaryLicense = "Creative Commons Attribution 2.5 Generic"`
  (licenceSource commons.wikimedia.org), **not CC BY 4.0** as the brief assumed. Attribution is shown on the map ("Boundaries: geoBoundaries gbOpen
  (Jordan ADM1), CC BY 2.5") and in the footer (Runfola et al. 2020 + Wikimedia Commons). Attribution licence allows commercial use.
- Precision: 147 vertices for Ma'an, 2006 representation: a coarse administrative line, not a survey boundary. Area computed from it = ~33,620 km2
  (not an official figure). The canonical copy owned by model1 is `regions/jordan_adm1.geojson`; the web copy is the same public source, loaded
  by the demo provider only for placement and display.

## Fonts
Archivo (variable, wdth axis) and JetBrains Mono, SIL Open Font License 1.1, delivered by `next/font/google` (fetched from Google Fonts at
**build time** and self-hosted from `/_next/static/media`; no runtime request to Google). Building needs network access once.

## Icons / logo
Hand-authored inline SVG (24 px grid, 1.6 stroke) in `web/src/components/ui/icons.tsx`; logo mark in `web/src/components/brand/Logo.tsx`,
favicon `web/src/app/icon.svg`. No third-party icon set, no licence obligations.
