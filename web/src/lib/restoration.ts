/**
 * Restoration helpers: apply user constraints to Model 2 output and aggregate current-vs-simulated outcomes.
 * Pure functions (unit-tested). Constraints filter and rank what the analysis already produced; they never invent results.
 */
import type {
  FeasibilityClass,
  RestorationFeature,
  RestorationScenario,
  SuitabilityClassCode,
} from "./contract";
import { FEASIBILITY_META } from "./classes";
import type { RestorationConstraints } from "./types";

export const FEASIBILITY_ORDER: FeasibilityClass[] = ["not_feasible", "low", "moderate", "high"];

export const DEFAULT_CONSTRAINTS: RestorationConstraints = {
  max_water_m3_ha_yr: null,
  allowed_water_sources: [],
  max_years: 10,
  min_feasibility: "low",
  exclude_irreversible: false,
};

/** Every distinct water source named by any scenario, sorted. */
export function availableWaterSources(features: RestorationFeature[]): string[] {
  const set = new Set<string>();
  // the region-wide layer served by the API is slim and has no scenarios; only analysed units carry them
  for (const f of features) for (const s of f.properties.scenarios ?? []) for (const w of s.water_sources) set.add(w);
  return [...set].sort((a, b) => a.localeCompare(b));
}

export function withAllSources(c: RestorationConstraints, features: RestorationFeature[]): RestorationConstraints {
  return { ...c, allowed_water_sources: availableWaterSources(features) };
}

/** Scenario "tier" key: the last dash-separated token of its id (e.g. `...-standard`). Free-form ids fall back to the id. */
export function scenarioKey(s: RestorationScenario): string {
  const tail = s.id.split("-").pop();
  return tail && tail.length > 0 ? tail : s.id;
}

export interface ScenarioEvaluation {
  scenario: RestorationScenario;
  viable: boolean;
  /** Why it is not viable under the current constraints (empty when viable). */
  reasons: string[];
}

export interface PolygonEvaluation {
  feature: RestorationFeature;
  /** Non-empty => polygon is excluded entirely by the constraints. */
  excludedReasons: string[];
  scenarios: ScenarioEvaluation[];
}

export function evaluatePolygon(feature: RestorationFeature, c: RestorationConstraints): PolygonEvaluation {
  const p = feature.properties;
  const excludedReasons: string[] = [];
  if (FEASIBILITY_ORDER.indexOf(p.feasibility.class) < FEASIBILITY_ORDER.indexOf(c.min_feasibility)) {
    excludedReasons.push(
      `Feasibility ${FEASIBILITY_META[p.feasibility.class].label.toLowerCase()} is below the minimum (${FEASIBILITY_META[c.min_feasibility].label.toLowerCase()}).`,
    );
  }
  if (c.exclude_irreversible) {
    const bad = p.limiting_factors.find((l) => l.reversibility === "irreversible" && l.severity >= 0.6);
    if (bad) excludedReasons.push(`Severe irreversible limiting factor: ${bad.factor.replace(/_/g, " ")} (severity ${bad.severity}).`);
  }
  if (p.feasibility.class === "not_feasible") excludedReasons.push("Model 2 classes this unit as not feasible to restore.");

  const scenarios = p.scenarios.map<ScenarioEvaluation>((scenario) => {
    const reasons: string[] = [];
    if (c.max_water_m3_ha_yr != null && scenario.water_requirement_m3_ha_yr.central > c.max_water_m3_ha_yr) {
      reasons.push(
        `Central water need ${scenario.water_requirement_m3_ha_yr.central.toLocaleString("en-US")} m³/ha/yr exceeds the limit of ${c.max_water_m3_ha_yr.toLocaleString("en-US")}.`,
      );
    }
    if (scenario.time_to_effect_years.high > c.max_years) {
      reasons.push(`Time to effect (up to ${scenario.time_to_effect_years.high} years) exceeds the ${c.max_years}-year horizon.`);
    }
    if (scenario.water_sources.length > 0 && !scenario.water_sources.some((w) => c.allowed_water_sources.includes(w))) {
      reasons.push("None of the water sources this scenario relies on is available.");
    }
    return { scenario, viable: reasons.length === 0, reasons };
  });
  return { feature, excludedReasons, scenarios };
}

export function evaluateRun(features: RestorationFeature[], c: RestorationConstraints): PolygonEvaluation[] {
  return features.map((f) => evaluatePolygon(f, c));
}

/** "best" = lowest post-restoration class code, then highest post-class probability, then lowest central water. */
export function chooseScenario(ev: PolygonEvaluation, preference: string): RestorationScenario | null {
  if (ev.excludedReasons.length > 0) return null;
  const viable = ev.scenarios.filter((s) => s.viable).map((s) => s.scenario);
  if (viable.length === 0) return null;
  if (preference !== "best") {
    const hit = viable.find((s) => scenarioKey(s) === preference);
    if (hit) return hit;
    return null;
  }
  return viable
    .slice()
    .sort(
      (a, b) =>
        a.post_class_code - b.post_class_code ||
        b.post_class_probability - a.post_class_probability ||
        a.water_requirement_m3_ha_yr.central - b.water_requirement_m3_ha_yr.central,
    )[0] as RestorationScenario;
}

export interface Outcome {
  /** Hectares per suitability class code, before (Model 1 current) and after (simulated). */
  before: Record<SuitabilityClassCode, number>;
  after: Record<SuitabilityClassCode, number>;
  total_ha: number;
  /** Polygons that end up with a chosen scenario / excluded / viable-scenario-less. */
  counts: { analysed: number; with_scenario: number; excluded: number; no_viable_scenario: number };
  /** Aggregate yearly water over polygons with a chosen scenario, million m3/yr. */
  water_mm3_yr: { low: number; central: number; high: number };
  improved_ha: number;
}

const emptyByClass = (): Record<SuitabilityClassCode, number> => ({ 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 });

export function summariseOutcome(evals: PolygonEvaluation[], preference: string): Outcome {
  const before = emptyByClass();
  const after = emptyByClass();
  const counts = { analysed: evals.length, with_scenario: 0, excluded: 0, no_viable_scenario: 0 };
  const water = { low: 0, central: 0, high: 0 };
  let improved = 0;
  let total = 0;
  for (const ev of evals) {
    const p = ev.feature.properties;
    const cls = p.current_class_code as SuitabilityClassCode;
    before[cls] += p.area_ha;
    total += p.area_ha;
    const chosen = chooseScenario(ev, preference);
    if (ev.excludedReasons.length > 0) counts.excluded += 1;
    else if (!chosen) counts.no_viable_scenario += 1;
    if (chosen) {
      counts.with_scenario += 1;
      after[chosen.post_class_code] += p.area_ha;
      if (chosen.post_class_code < cls) improved += p.area_ha;
      const w = chosen.water_requirement_m3_ha_yr;
      water.low += (w.low * p.area_ha) / 1e6;
      water.central += (w.central * p.area_ha) / 1e6;
      water.high += (w.high * p.area_ha) / 1e6;
    } else {
      after[cls] += p.area_ha;
    }
  }
  return { before, after, total_ha: total, counts, water_mm3_yr: water, improved_ha: improved };
}
