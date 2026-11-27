# DATA_SOURCES - Model 1 (agricultural land suitability, `jo-maan`)

Verified = fetched and read directly on 2026-11-23; "not verified" = could not be checked.
All raw data live under `<GREEN_NOVA_DATA>` (outside the repository). Shared covariate layers are registered in
`<GREEN_NOVA_DATA>/cache/covariates/manifest.json` (format `{"entries":[{layer, source_url, license, resolution, crs, bbox, date, files, notes}]}`).
(`docs/DATA_SOURCES.md` is an index pointing to this file and `DATA_SOURCES_model2.md`.)

## Used by the shipped checkpoint

| Dataset | Access method | Size | License | Native res. / vintage | Role | Verified |
|---|---|---|---|---|---|---|
| geoBoundaries gbOpen JOR ADM1 (`JOR-ADM1-50493656`) | GitHub release file `geoBoundaries-JOR-ADM1.geojson` | 84 KB | CC BY 2.5 (API field `boundaryLicense`) | vector, year represented 2006 (Wikimedia-derived, ~155 vertices/polygon, coarse) | region boundaries (`regions/jordan_adm1.geojson`) | yes: Ma'an area 33,587 km2 = API `maxAreaSqKM` |
| Copernicus DEM GLO-30 | Planetary Computer STAC `cop-dem-glo-30` (anonymous SAS signing, no account) | 29 tiles, mosaic ~0.6 GB (cache) | Copernicus free/open | ~30 m | covariate (slope, terrain context) | yes |
| ISRIC SoilGrids 2.0 | `files.isric.org/soilgrids/latest/data/<prop>/<prop>_<depth>_<stat>.vrt`, read by window | 64 layers x ~3 MB (Jordan clip, cache) | CC BY 4.0 | 250 m, 2020 | covariate: pH, SOC, sand/silt/clay, CEC, bulk density, coarse fragments (+Q05/Q95) | yes. ML-predicted soil maps, not measurements |
| SOTWIS Jordan v1.0 (ISRIC) | `files.isric.org/public/sotwis/SOTWIS_JO.zip` | 3.3 MB | **CC BY 3.0 on the data hub record; the zip's own metadata says educational/non-commercial use only and commercial reuse needs ISRIC permission - conflict: clarify with ISRIC before commercial use** | 1:500 000 SOTER units (survey 1996, published 2013) | covariate + rules: EC (ECe, dS/m), ESP, gypsum, CaCO3, drainage, AWC | yes (ECe units = saturated paste per ISRIC Report 2003/04). Very coarse: ~50% of Jordan is mapped ECe > 8 dS/m |
| WorldClim 2.1 monthly precipitation | `geodata.ucdavis.edu/.../wc2.1_30s_prec.zip` | 1,025,401,472 B (raw zip, kept in raw/) | CC BY 4.0 (worldclim.org) | 30 arc-sec ~1 km, 1970-2000 | covariate: annual rainfall (sum of 12 months) | yes (one corrupt zip member repaired by HTTP range re-download, tested) |
| TerraClimate | Planetary Computer zarr `terraclimate` (anonymous) | ~10 MB (Jordan, 2011-2020) | CC0 per PC catalog (not independently verified) | 1/24 deg ~4 km, 2011-2020 (10-yr window; 1991-2020 was too slow to read) | covariate: PET, deficit, AET, tmin/tmax, rain CV; lapse-rate downscaled with 100 m DEM (-6.5 C/km) | yes |
| JRC Global Surface Water occurrence | Planetary Computer `jrc-gsw` | 1.7 MB (Jordan) | Copernicus free/open | 30 m, 1984-2021 | covariate (water occurrence) | yes |
| ESA WorldCover 2020 v100, 2021 v200 | Planetary Computer `esa-worldcover` | 9 tiles/year read by window | CC BY 4.0 | 10 m | **OBSERVED label** (cropland fraction), exclusion (built-up, water) | yes. Global accuracy ~75%; arid-zone cropland not verified for Jordan |
| Impact Observatory 10 m annual LULC v02 (2017, 2021, 2023) | Planetary Computer `io-lulc-annual-v02` (window reads of UTM-band mosaics) | - | CC BY 4.0 | 10 m | **OBSERVED label** (crop class 5) | yes |
| OpenStreetMap, Geofabrik Jordan extract | `download.geofabrik.de/asia/jordan-latest-free.shp.zip` | 61,414,967 B | ODbL 1.0 | vector, extract of 2026-11-21 | class-5 restriction masks (protected, military, quarry, cemetery, built-up, airport, water, heritage) | yes. OSM object 1073421633 (a 129,639 km2 "nature_reserve", larger than Jordan) was dropped as a mapping artefact. Crowd-sourced, incomplete; not the official WDPA/cadastre |

Label agreement (verified, `labels.py`): WorldCover-2021 vs IO-2021 cropland at 100 m, Cohen kappa 0.47 (agreement 97.4% driven by the
97% non-crop majority). Only cells where both agree are positives (109,268 cells = 1,093 km2 in Jordan; 2,860 cells = 28.6 km2 in Ma'an).

## Audited, NOT used for training

| Dataset | What was verified | Why not used |
|---|---|---|
| Kaggle EuroSAT `apollo2506/eurosat-dataset` | Kaggle page is JavaScript-only (WebFetch returned only the title); file listing/license NOT verified. The original dataset: Zenodo 10.5281/zenodo.7711810, **MIT** (Zenodo API `license.id`), `EuroSAT_MS.zip` 2,065,402,329 B (md5 091174add3c8e680a49244acf185b9f0, 13-band 64x64 Sentinel-2 patches, 10 land-cover classes, 27,000 images, European), `EuroSAT_RGB.zip` 94,658,721 B | Land-cover, not suitability. The planned ablation (does EuroSAT pre-training help held-out Jordan cultivation detection?) was **cut for time and NOT run**; no claim is made that it helps. Partial MS download (~0.3 GB) left in `raw/eurosat/` |
| Kaggle AfSIS (`afsis-soil-properties`) | Not accepted/downloaded by me. model2 mirrored the AfSIS AWS open data (`raw/afsis/aws_mirror`: wet-chemistry CSVs + georeferences.csv; sub-Saharan Africa only, ~1.4 MB). Competition data per public descriptions: ~3,594 MIR spectral columns + 16 coarse MODIS/terrain predictors, **no coordinates** | Africa only, mid-infrared lab spectra (not Sentinel-2), no coordinates in the competition file -> cannot be joined to rasters or used for Jordan. SoilGrids already provides pH/SOC/sand. Not used |
| Kaggle AgriYield 2025 (`agriyield-2025`) | Audited from the data page's own Data Explorer (a Kaggle account that had accepted the competition rules was used to view it): 4 files, 577.18 kB, CC BY-NC-SA 4.0; `train.csv` 10,000 rows x 9 columns (`field_id, soil_ph, organic_matter, sand_pct, temperature, humidity, rainfall, ndvi, yield`); the "19 columns" on the page is the sum over the 4 files (9+8+... ). Every numeric column's histogram is flat (about 1,000 rows per bin; pH 5.5-7.5, OM 1.5-4 %, sand 30-60 %, temperature 24-30, rainfall 100-180 mm, NDVI 0.40-0.75, yield 3,500-5,000 kg/ha) -> looks **synthetic (uniform random draws)**. No coordinates, no dates, maize only. The "Download as zip" click did not produce a retrievable file on disk (browser pane), so no local copy | Synthetic-looking, no geography, a yield (not suitability) target, non-commercial licence (the site is deployed). Not used for anything in the checkpoint; audit only |
| FAO GAEZ v4 suitability (`s3.eu-west-1.amazonaws.com/data.gaezdev.aws.fao.org/res05/CRUTS32/Hist/8110H/sxHi_whe.tif` etc.) | HTTP HEAD returned 200 for several `sx*` rasters (5 arc-min ~9 km); license/terms NOT verified; not downloaded | Planned only as an evaluation reference; cut. Too coarse (9 km) to validate a 100 m map |
| Jordan NARC suitability maps | No public download found | n/a |
| WDPA (Protected Planet) | Requires terms acceptance at download | Replaced by OSM protected areas (documented limitation) |
| Sentinel-2 L2A / Sentinel-1 | S2 temporal-statistics pipeline written (`acquire_s2.py`), first tile tested; reading 36 tiles from this machine was ~5 min/tile | Cut for time; **v0.1 checkpoint uses no Sentinel imagery directly** (land-cover labels derive from Sentinel-2 via WorldCover/IO). Sentinel-1 not used |
| Hassani et al. global salinity (downloaded by model2) | present in `raw/hassani2020_salinity` | 0.25 deg product; SOTWIS used instead |
