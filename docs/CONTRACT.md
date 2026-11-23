# Data contract between Model 1, Model 2 and the website (v0.1 — lead-owned)

Change requests go through the lead. ML agents may ADD optional fields (document them in your handoff); never rename or
remove contract fields. The website must tolerate unknown extra properties.

## Conventions
- Region id: `jo-maan` (country `JO`, ADM1 Ma'an). Boundaries: geoBoundaries gbOpen JOR ADM1 (public). Canonical copy:
  `regions/jordan_adm1.geojson` (model1 owns; web may fetch the same public source for its own demo needs).
  Pipelines are parameterized by region id so further governorates can be added by config.
- Vector outputs: GeoJSON, EPSG:4326, RFC 7946, coordinates rounded to ≤6 decimals.
- Raster outputs: Cloud-Optimized GeoTIFF, native working CRS recorded in `run_metadata.json`; also provide a web-friendly
  EPSG:4326 or EPSG:3857 preview. Declare nodata. Preserve native resolution; record `effective_resolution_m`.
- Area: computed in an equal-area projection (e.g. EPSG:6933 or local LAEA), never in degrees.
  Units: `area_ha` hectares and `area_dunum`. **1 dunum = 1,000 m² = 0.1 ha** (Jordanian metric dunum) — state this in UI/docs.
- Probabilities/confidence are floats in [0,1]. Say how confidence is defined (calibrated class probability, ensemble
  agreement, conformal set size, …) in `confidence_method`; never present uncalibrated softmax as "accuracy".
- `evidence` vocabulary (everything numeric/textual about land must carry one): `observed` | `ml_predicted` | `expert_rule` | `simulated`.

## Model 1 — suitability
Class codes: `1` currently suitable · `2` suitable with limitations · `3` requires reclamation · `4` currently unsuitable ·
`5` excluded (legal/environmental restriction). Raster nodata = `0`.
Outputs in `models/suitability/outputs/<region_id>/`:
`suitability.tif` (uint8) · `confidence.tif` (uint8 0–100 or float32 0–1, say which) · `polygons.geojson` ·
`summary.json` (per class: polygon_count, area_ha, area_dunum, share) · `run_metadata.json` (model_version, checkpoint_sha256,
data sources + vintages + acquisition date range, label basis per class, effective_resolution_m, created_at).
Polygon `properties`:
```
id: "m1-<region>-<n>"            stable within a run
class_code: 1..5, class_label: string
area_ha, area_dunum: number
confidence: 0..1, confidence_method: string
class_probabilities: {"1":p,...,"5":p}
factors: [{name, value, unit, status: "favourable"|"marginal"|"limiting"|"restricted", evidence, note, importance?}]
centroid: [lon, lat], effective_resolution_m: number
provenance: {model_version, label_basis, data_sources:[...]}
```
Factors are computed per polygon (e.g. zonal stats + attribution), not templated text.

## Model 2 — restoration potential
Applies to polygons with Model 1 `class_code` ∈ {3,4} (class 2 optional). Class 5 is never "restorable" — report the restriction.
Outputs in `models/restoration/outputs/<region_id>/`:
`restoration_feasibility.tif` (uint8: 0 nodata, 1 not_feasible, 2 low, 3 moderate, 4 high) ·
`post_restoration_suitability.tif` (uint8 class codes 1–4, simulated — name/metadata must say "simulated") ·
`polygons.geojson` · `summary.json` · `run_metadata.json` (incl. which parts are observed / expert_rule / simulated, source studies).
Polygon `properties`:
```
id: "m2-<region>-<n>", source_polygon_id: "<m1 id>", current_class_code: 3|4|2
area_ha, area_dunum
limiting_factors: [{factor, severity: 0..1, reversibility: "reversible"|"partially_reversible"|"irreversible",
                    evidence, detail}]
feasibility: {score: 0..1, class: "high"|"moderate"|"low"|"not_feasible", confidence: 0..1, interval: [lo, hi]}
interventions: [{id, name, description, targets_factor, expected_effect, evidence, source_refs:[...]}]
scenarios: [{id, name, intervention_ids:[...], post_class_code, post_class_probability,
             water_requirement_m3_ha_yr: {low, central, high}, water_sources:[...], infrastructure:[...],
             crop_categories:[...], time_to_effect_years: {low, high}, residual_risks:[...], evidence: "simulated"}]
soil: {ph, ec_ds_m, soc_pct, sand_pct, silt_pct, clay_pct, depth_cm, ...each with value, unit, evidence, uncertainty?}
terrain: {elevation_m, slope_deg, erosion_risk: {value, evidence}}, climate: {rainfall_mm_yr, temp_mean_c}
provenance: {model_version, evidence_summary, data_sources:[...], source_studies:[...]}
```
Water requirements, intervention effects and post-restoration outcomes are **simulated/expert-derived**, flagged as such, with
ranges and cited source studies — never presented as observed restoration results.

## Inference interface (each ML agent documents exact signatures in its handoff)
- CLI: `python -m models.suitability.infer --region jo-maan --out <dir> [--geometry <geojson>] [--device cuda|cpu]` and
  `python -m models.restoration.infer --region jo-maan --suitability-dir <model1 outputs> --out <dir> [--polygon-ids ...]`.
- Python: importable functions that accept a region id and/or GeoJSON geometry, return output file paths + summary dict, accept a
  `progress(fraction, message)` callback, and raise typed exceptions. No network access at inference except documented cached fetches.
- Region-wide batch may be precomputed; sub-area/polygon queries must be answerable in seconds–minutes from cached covariates.
- Deterministic given (checkpoint, data vintage, seed). Report runtime and peak RAM/VRAM on this machine.

## Website data layer (web agent)
TypeScript types mirror this file exactly (generate from a single `web/src/lib/contract.ts`). Two providers behind one interface:
`demoProvider` (labelled synthetic) and `apiProvider` (Phase C, real endpoints). Endpoints to be finalized in Phase C from the
ML handoffs; expected shape: region list, region boundary, start analysis job (+status), polygons GeoJSON, polygon detail, raster
tiles/COG URL, export (GeoJSON, GeoTIFF, PDF/CSV report).
