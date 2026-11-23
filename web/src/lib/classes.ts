import type {
  ClassKey,
  Evidence,
  FactorStatus,
  FeasibilityClass,
  Reversibility,
  SuitabilityClassCode,
} from "./contract";

export interface SuitabilityClassMeta {
  code: SuitabilityClassCode;
  key: ClassKey;
  label: string;
  /** Short label for chips and tight legends. */
  short: string;
  description: string;
  /** Map / legend fill. Hue + lightness chosen to stay distinguishable on desert imagery; the code number is the non-colour cue. */
  color: string;
  /** Colour of the number printed on a swatch (verified >= 4.5:1 in tests). */
  onColor: string;
  /** Excluded land is additionally hatched on the map so it never relies on colour alone. */
  hatch: boolean;
}

export const SUITABILITY_CLASSES: Record<SuitabilityClassCode, SuitabilityClassMeta> = {
  1: {
    code: 1,
    key: "1",
    label: "Currently suitable",
    short: "Suitable",
    description: "Suitable for agriculture under current conditions with ordinary management.",
    color: "#2d9a63",
    onColor: "#07120c",
    hatch: false,
  },
  2: {
    code: 2,
    key: "2",
    label: "Suitable with limitations",
    short: "With limitations",
    description: "Cultivable now, but one or more factors constrain crop choice or yield.",
    color: "#a8c256",
    onColor: "#0d1405",
    hatch: false,
  },
  3: {
    code: 3,
    key: "3",
    label: "Requires reclamation",
    short: "Needs reclamation",
    description: "Not cultivable as is; limiting factors are expected to be addressable by reclamation.",
    color: "#e3a43a",
    onColor: "#1b1203",
    hatch: false,
  },
  4: {
    code: 4,
    key: "4",
    label: "Currently unsuitable",
    short: "Unsuitable",
    description: "Not cultivable under current conditions; limiting factors are severe or hard to reverse.",
    color: "#b8572e",
    onColor: "#ffffff",
    hatch: false,
  },
  5: {
    code: 5,
    key: "5",
    label: "Excluded (legal or environmental restriction)",
    short: "Excluded",
    description: "Agriculture is excluded by a legal or environmental restriction. Never treated as restorable.",
    color: "#7a89b4",
    onColor: "#08101f",
    hatch: true,
  },
};

export const CLASS_LIST: SuitabilityClassMeta[] = [1, 2, 3, 4, 5].map((c) => SUITABILITY_CLASSES[c as SuitabilityClassCode]);

/** Classes Model 2 may analyse (class 2 optional in the contract; the web UI offers 3 and 4). */
export const RESTORABLE_CLASS_CODES: SuitabilityClassCode[] = [3, 4];

export interface EvidenceMeta {
  value: Evidence;
  label: string;
  /** Plain-language definition shown in the UI glossary and tooltips. */
  definition: string;
}

export const EVIDENCE_META: Record<Evidence, EvidenceMeta> = {
  observed: {
    value: "observed",
    label: "Observed",
    definition: "Measured or directly derived from a real sensor, survey or archive (e.g. a satellite band, a DEM, a gauge product).",
  },
  ml_predicted: {
    value: "ml_predicted",
    label: "ML-predicted",
    definition: "Estimated by a trained model. Carries model error; see the confidence definition for how uncertainty is expressed.",
  },
  expert_rule: {
    value: "expert_rule",
    label: "Expert rule",
    definition: "Derived from a documented threshold or rule written by domain experts. Not learned from labelled outcomes.",
  },
  simulated: {
    value: "simulated",
    label: "Simulated",
    definition: "Scenario output (for example a post-restoration outcome). Never an observed result.",
  },
};

export const FACTOR_STATUS_META: Record<FactorStatus, { label: string; rank: number }> = {
  favourable: { label: "Favourable", rank: 0 },
  marginal: { label: "Marginal", rank: 1 },
  limiting: { label: "Limiting", rank: 2 },
  restricted: { label: "Restricted", rank: 3 },
};

export const FEASIBILITY_META: Record<FeasibilityClass, { label: string; color: string; onColor: string; rank: number }> = {
  high: { label: "High", color: "#246d9c", onColor: "#ffffff", rank: 3 },
  moderate: { label: "Moderate", color: "#4aa6b8", onColor: "#041418", rank: 2 },
  low: { label: "Low", color: "#9ed2d6", onColor: "#06191c", rank: 1 },
  not_feasible: { label: "Not feasible", color: "#64707a", onColor: "#ffffff", rank: 0 },
};

export const REVERSIBILITY_META: Record<Reversibility, string> = {
  reversible: "Reversible",
  partially_reversible: "Partially reversible",
  irreversible: "Irreversible",
};

export const CONFIDENCE_EXPLAINER =
  "Confidence is a number from 0 to 1 that expresses how strongly the analysis supports the assigned class. " +
  "Its exact definition (calibrated class probability, ensemble agreement, conformal set size, ...) is stated per record in " +
  "“confidence method”. It is not accuracy, and an uncalibrated score must never be read as a probability of being correct.";

export const CLASS5_NOTE =
  "Class 5 land is excluded by a legal or environmental restriction. It is never treated as restorable; the restriction is reported instead.";

/** Human-readable factor names (contract leaves `name` free text; known demo/ML keys get tidy labels, others pass through). */
const FACTOR_LABELS: Record<string, string> = {
  rainfall: "Annual rainfall",
  soil_salinity_ec: "Soil salinity (EC)",
  soil_ph: "Soil pH",
  soil_organic_carbon: "Soil organic carbon",
  soil_depth: "Soil depth",
  slope: "Terrain slope",
  sand_fraction: "Sand fraction",
  water_availability: "Water availability",
  vegetation_ndvi: "Vegetation activity (peak NDVI)",
  land_use_restriction: "Land-use restriction",
};

export function factorLabel(name: string): string {
  return FACTOR_LABELS[name] ?? name.replace(/[_-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export const CLASS_KEYS: ClassKey[] = ["1", "2", "3", "4", "5"];
