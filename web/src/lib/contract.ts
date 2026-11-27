/**
 * GREEN NOVA AI - data contract (mirrors docs/CONTRACT.md v0.1, lead-owned).
 *
 * Rules (from the contract):
 *  - Never rename or remove contract fields here; ML agents may ADD optional fields, which the UI must tolerate.
 *  - Therefore none of the guards below reject unknown extra properties.
 *  - Units: area_ha (hectares) and area_dunum; 1 dunum = 1,000 m2 = 0.1 ha.
 *  - Probabilities / confidence are floats in [0, 1].
 *  - Every numeric/textual statement about land carries an `evidence` class.
 *
 * Anything not in docs/CONTRACT.md lives in `src/lib/types.ts`, never here.
 */
import type { Feature, FeatureCollection, MultiPolygon, Polygon } from "geojson";

/* ------------------------------------------------------------------ conventions */

/** Region id convention: `jo-maan` (country JO, ADM1 Ma'an). */
export type RegionId = string;

/** Evidence vocabulary. Everything numeric/textual about land must carry one. */
export const EVIDENCE_VALUES = ["observed", "ml_predicted", "expert_rule", "simulated"] as const;
export type Evidence = (typeof EVIDENCE_VALUES)[number];

/** 1 currently suitable, 2 suitable with limitations, 3 requires reclamation, 4 currently unsuitable, 5 excluded. */
export const SUITABILITY_CLASS_CODES = [1, 2, 3, 4, 5] as const;
export type SuitabilityClassCode = (typeof SUITABILITY_CLASS_CODES)[number];

export const FACTOR_STATUS_VALUES = ["favourable", "marginal", "limiting", "restricted"] as const;
export type FactorStatus = (typeof FACTOR_STATUS_VALUES)[number];

/** `"1".."5"` keys, as used by `class_probabilities`. */
export type ClassKey = "1" | "2" | "3" | "4" | "5";

/* ------------------------------------------------------------------ Model 1 - suitability */

export interface SuitabilityFactor {
  name: string;
  value: number | string | null;
  unit?: string;
  status: FactorStatus;
  evidence: Evidence;
  note?: string;
  importance?: number;
  /** Optional, added by the web demo provider only (not part of the contract). Real data may omit it. */
  category?: string;
}

export interface Provenance {
  model_version: string;
  /** Contract: `label_basis` per polygon is a string; run_metadata may carry a per-class record. */
  label_basis: string | Record<string, string>;
  data_sources: string[];
}

export interface SuitabilityProperties {
  /** `m1-<region>-<n>`, stable within a run. */
  id: string;
  class_code: SuitabilityClassCode;
  class_label: string;
  area_ha: number;
  area_dunum: number;
  /** 0..1 */
  confidence: number;
  /** How `confidence` is defined (calibrated class probability, ensemble agreement, conformal set size, ...). */
  confidence_method: string;
  class_probabilities: Record<ClassKey, number>;
  factors: SuitabilityFactor[];
  /** [lon, lat] */
  centroid: [number, number];
  effective_resolution_m: number;
  provenance: Provenance;
}

export type SuitabilityGeometry = Polygon | MultiPolygon;
export type SuitabilityFeature = Feature<SuitabilityGeometry, SuitabilityProperties>;
export type SuitabilityCollection = FeatureCollection<SuitabilityGeometry, SuitabilityProperties>;

/** Per-class entry of summary.json (polygon_count, area_ha, area_dunum, share). Exact container shape: see types.ts. */
export interface ClassSummary {
  polygon_count: number;
  area_ha: number;
  area_dunum: number;
  /** Fraction 0..1 of the classified area. */
  share: number;
}

/** run_metadata.json (fields named in the contract; others tolerated). */
export interface RunMetadata {
  model_version: string;
  checkpoint_sha256?: string;
  data_sources?: unknown;
  acquisition_date_range?: unknown;
  label_basis?: string | Record<string, string>;
  effective_resolution_m?: number;
  created_at?: string;
  [extra: string]: unknown;
}

/* ------------------------------------------------------------------ Model 2 - restoration */

export const REVERSIBILITY_VALUES = ["reversible", "partially_reversible", "irreversible"] as const;
export type Reversibility = (typeof REVERSIBILITY_VALUES)[number];

export const FEASIBILITY_CLASS_VALUES = ["high", "moderate", "low", "not_feasible"] as const;
export type FeasibilityClass = (typeof FEASIBILITY_CLASS_VALUES)[number];

/** Raster codes of restoration_feasibility.tif: 0 nodata, 1 not_feasible, 2 low, 3 moderate, 4 high. */
export const FEASIBILITY_RASTER_CODE: Record<FeasibilityClass, 1 | 2 | 3 | 4> = {
  not_feasible: 1,
  low: 2,
  moderate: 3,
  high: 4,
};

export interface LimitingFactor {
  factor: string;
  /** 0..1 */
  severity: number;
  reversibility: Reversibility;
  evidence: Evidence;
  detail: string;
}

export interface Feasibility {
  /** 0..1 */
  score: number;
  class: FeasibilityClass;
  /** 0..1 */
  confidence: number;
  interval: [number, number];
}

export interface Intervention {
  id: string;
  name: string;
  description: string;
  targets_factor: string;
  expected_effect: string;
  evidence: Evidence;
  source_refs: string[];
}

export interface WaterRequirement {
  low: number;
  central: number;
  high: number;
}

export interface RestorationScenario {
  id: string;
  name: string;
  intervention_ids: string[];
  post_class_code: SuitabilityClassCode;
  post_class_probability: number;
  water_requirement_m3_ha_yr: WaterRequirement;
  /** Renewable water generated locally (climatic surplus, ~4 km), m3/ha/yr. Absent in older outputs and in demonstration data. */
  local_renewable_water_m3_ha_yr?: number | null;
  /** max(central requirement - local renewable water, 0): water that would have to come from sources the model does not map. */
  water_deficit_m3_ha_yr?: number | null;
  water_sources: string[];
  infrastructure: string[];
  crop_categories: string[];
  time_to_effect_years: { low: number; high: number };
  residual_risks: string[];
  /** Always "simulated" - scenario outcomes are never observed restoration results. */
  evidence: "simulated";
}

export type UncertaintyValue = number | [number, number] | Record<string, number>;

/** A measured/estimated quantity: value, unit, evidence, optional uncertainty. */
export interface MeasuredValue {
  value: number;
  unit: string;
  evidence: Evidence;
  uncertainty?: UncertaintyValue;
}

/** Soil: ph, ec_ds_m, soc_pct, sand_pct, silt_pct, clay_pct, depth_cm, plus any further keys. */
export type SoilBlock = Record<string, MeasuredValue>;

export interface TerrainBlock {
  elevation_m?: MeasuredValue | number;
  slope_deg?: MeasuredValue | number;
  erosion_risk?: { value: number | string; evidence: Evidence };
  [extra: string]: unknown;
}

export interface ClimateBlock {
  rainfall_mm_yr?: MeasuredValue | number;
  temp_mean_c?: MeasuredValue | number;
  [extra: string]: unknown;
}

export interface RestorationProvenance {
  model_version: string;
  evidence_summary: string | Record<string, unknown>;
  data_sources: string[];
  source_studies: string[];
}

export interface RestorationProperties {
  /** `m2-<region>-<n>` */
  id: string;
  /** Model 1 polygon id. */
  source_polygon_id: string;
  current_class_code: 2 | 3 | 4;
  area_ha: number;
  area_dunum: number;
  limiting_factors: LimitingFactor[];
  feasibility: Feasibility;
  interventions: Intervention[];
  scenarios: RestorationScenario[];
  soil: SoilBlock;
  terrain: TerrainBlock;
  climate: ClimateBlock;
  provenance: RestorationProvenance;
}

export type RestorationFeature = Feature<SuitabilityGeometry, RestorationProperties>;
export type RestorationCollection = FeatureCollection<SuitabilityGeometry, RestorationProperties>;

/* ------------------------------------------------------------------ runtime guards (tolerant of extra properties) */

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const isStr = (v: unknown): v is string => typeof v === "string";
const isUnit = (v: unknown): v is number => isNum(v) && v >= 0 && v <= 1;
const isStrArray = (v: unknown): v is string[] => Array.isArray(v) && v.every(isStr);

export const isEvidence = (v: unknown): v is Evidence => (EVIDENCE_VALUES as readonly unknown[]).includes(v);
export const isSuitabilityClassCode = (v: unknown): v is SuitabilityClassCode =>
  (SUITABILITY_CLASS_CODES as readonly unknown[]).includes(v);
export const isFactorStatus = (v: unknown): v is FactorStatus => (FACTOR_STATUS_VALUES as readonly unknown[]).includes(v);
export const isFeasibilityClass = (v: unknown): v is FeasibilityClass =>
  (FEASIBILITY_CLASS_VALUES as readonly unknown[]).includes(v);
export const isReversibility = (v: unknown): v is Reversibility => (REVERSIBILITY_VALUES as readonly unknown[]).includes(v);

export function isLonLat(v: unknown): v is [number, number] {
  return Array.isArray(v) && v.length === 2 && isNum(v[0]) && isNum(v[1]) && Math.abs(v[0]) <= 180 && Math.abs(v[1]) <= 90;
}

export function isSuitabilityFactor(v: unknown): v is SuitabilityFactor {
  return (
    isObj(v) &&
    isStr(v.name) &&
    (isNum(v.value) || isStr(v.value) || v.value === null) &&
    isFactorStatus(v.status) &&
    isEvidence(v.evidence)
  );
}

function isProvenance(v: unknown): v is Provenance {
  return isObj(v) && isStr(v.model_version) && (isStr(v.label_basis) || isObj(v.label_basis)) && isStrArray(v.data_sources);
}

export function isSuitabilityProperties(v: unknown): v is SuitabilityProperties {
  if (!isObj(v)) return false;
  if (!isStr(v.id) || !isSuitabilityClassCode(v.class_code) || !isStr(v.class_label)) return false;
  if (!isNum(v.area_ha) || v.area_ha < 0 || !isNum(v.area_dunum) || v.area_dunum < 0) return false;
  if (!isUnit(v.confidence) || !isStr(v.confidence_method)) return false;
  if (!isObj(v.class_probabilities)) return false;
  const probs = v.class_probabilities;
  for (const k of ["1", "2", "3", "4", "5"]) if (!isUnit(probs[k])) return false;
  if (!Array.isArray(v.factors) || !v.factors.every(isSuitabilityFactor)) return false;
  if (!isLonLat(v.centroid) || !isNum(v.effective_resolution_m)) return false;
  return isProvenance(v.provenance);
}

function isMeasuredValue(v: unknown): v is MeasuredValue {
  return isObj(v) && isNum(v.value) && isStr(v.unit) && isEvidence(v.evidence);
}

function isLimitingFactor(v: unknown): v is LimitingFactor {
  return (
    isObj(v) && isStr(v.factor) && isUnit(v.severity) && isReversibility(v.reversibility) && isEvidence(v.evidence) && isStr(v.detail)
  );
}

function isScenario(v: unknown): v is RestorationScenario {
  if (!isObj(v)) return false;
  const w = v.water_requirement_m3_ha_yr;
  const t = v.time_to_effect_years;
  return (
    isStr(v.id) &&
    isStr(v.name) &&
    isStrArray(v.intervention_ids) &&
    isSuitabilityClassCode(v.post_class_code) &&
    isUnit(v.post_class_probability) &&
    isObj(w) &&
    isNum(w.low) &&
    isNum(w.central) &&
    isNum(w.high) &&
    w.low <= w.central &&
    w.central <= w.high &&
    isStrArray(v.water_sources) &&
    isStrArray(v.infrastructure) &&
    isStrArray(v.crop_categories) &&
    isObj(t) &&
    isNum(t.low) &&
    isNum(t.high) &&
    isStrArray(v.residual_risks) &&
    v.evidence === "simulated"
  );
}

function isIntervention(v: unknown): v is Intervention {
  return (
    isObj(v) &&
    isStr(v.id) &&
    isStr(v.name) &&
    isStr(v.description) &&
    isStr(v.targets_factor) &&
    isStr(v.expected_effect) &&
    isEvidence(v.evidence) &&
    isStrArray(v.source_refs)
  );
}

export function isRestorationProperties(v: unknown): v is RestorationProperties {
  if (!isObj(v)) return false;
  if (!isStr(v.id) || !isStr(v.source_polygon_id)) return false;
  if (!(v.current_class_code === 2 || v.current_class_code === 3 || v.current_class_code === 4)) return false;
  if (!isNum(v.area_ha) || !isNum(v.area_dunum)) return false;
  if (!Array.isArray(v.limiting_factors) || !v.limiting_factors.every(isLimitingFactor)) return false;
  const f = v.feasibility;
  if (!isObj(f) || !isUnit(f.score) || !isFeasibilityClass(f.class) || !isUnit(f.confidence)) return false;
  if (!Array.isArray(f.interval) || f.interval.length !== 2 || !isUnit(f.interval[0]) || !isUnit(f.interval[1])) return false;
  if (!Array.isArray(v.interventions) || !v.interventions.every(isIntervention)) return false;
  if (!Array.isArray(v.scenarios) || !v.scenarios.every(isScenario)) return false;
  if (!isObj(v.soil) || !Object.values(v.soil).every(isMeasuredValue)) return false;
  if (!isObj(v.terrain) || !isObj(v.climate)) return false;
  const p = v.provenance;
  return isObj(p) && isStr(p.model_version) && isStrArray(p.data_sources) && isStrArray(p.source_studies);
}

export function isPolygonGeometry(g: unknown): g is SuitabilityGeometry {
  return isObj(g) && (g.type === "Polygon" || g.type === "MultiPolygon") && Array.isArray(g.coordinates);
}

export interface ParseResult<F> {
  features: F[];
  /** One message per rejected feature (index + reason). Rejected features are dropped, never silently repaired. */
  errors: string[];
}

function parseCollection<P>(raw: unknown, guard: (p: unknown) => p is P, label: string): ParseResult<Feature<SuitabilityGeometry, P>> {
  const errors: string[] = [];
  const features: Feature<SuitabilityGeometry, P>[] = [];
  if (!isObj(raw) || raw.type !== "FeatureCollection" || !Array.isArray(raw.features)) {
    return { features, errors: [`${label}: not a GeoJSON FeatureCollection`] };
  }
  raw.features.forEach((f: unknown, i: number) => {
    if (!isObj(f) || f.type !== "Feature") return void errors.push(`${label}[${i}]: not a Feature`);
    if (!isPolygonGeometry(f.geometry)) return void errors.push(`${label}[${i}]: geometry is not Polygon/MultiPolygon`);
    if (!guard(f.properties)) return void errors.push(`${label}[${i}]: properties do not match the contract`);
    features.push(f as unknown as Feature<SuitabilityGeometry, P>);
  });
  return { features, errors };
}

export const parseSuitabilityCollection = (raw: unknown) =>
  parseCollection<SuitabilityProperties>(raw, isSuitabilityProperties, "suitability");
export const parseRestorationCollection = (raw: unknown) =>
  parseCollection<RestorationProperties>(raw, isRestorationProperties, "restoration");
