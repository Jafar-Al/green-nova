/**
 * Rule-based limitations and recommendations shown on land details. Derived ONLY from the record's own factors,
 * confidence and class; evidence class is always "expert_rule" (a rule, not a model output).
 */
import type { RestorationFeature, SuitabilityFeature } from "./contract";
import { factorLabel } from "./classes";

export interface Statement {
  text: string;
  evidence: "expert_rule";
}

const ACTION: Record<string, string> = {
  rainfall: "Plan for supplementary water: runoff harvesting or a reliable irrigation source.",
  soil_salinity_ec: "Measure soil EC in the field before planting; consider leaching with drainage and salt-tolerant crops.",
  soil_ph: "Test pH in the field; strongly alkaline soils limit nutrient availability and may need amendment.",
  soil_organic_carbon: "Build organic matter (compost, residues, reduced tillage) to improve fertility and water retention.",
  soil_depth: "Dig profile pits to confirm rooting depth; shallow soils restrict deep-rooted crops.",
  slope: "Use contour planting, bunds or terraces to control runoff and erosion.",
  sand_fraction: "Light soils drain fast: use drip irrigation, mulch and windbreaks.",
  water_availability: "Confirm the water source, quantity and quality before committing to cultivation.",
  vegetation_ndvi: "Low or marginal vegetation activity: check recent imagery and land cover on the ground.",
};

export function limitationsFor(f: SuitabilityFeature): Statement[] {
  const p = f.properties;
  const out: Statement[] = [];
  const push = (text: string) => out.push({ text, evidence: "expert_rule" });
  for (const x of p.factors.filter((x) => x.status === "limiting" || x.status === "restricted")) {
    push(`${factorLabel(x.name)} is ${x.status}${x.value !== null ? ` (${typeof x.value === "number" ? x.value : x.value}${x.unit ? " " + x.unit : ""})` : ""}.`);
  }
  if (p.confidence < 0.6) push(`Confidence is ${p.confidence.toFixed(2)}, below 0.60: treat this class as indicative and verify on the ground.`);
  const top2 = Object.entries(p.class_probabilities)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2);
  if (top2[1] && top2[1][1] >= 0.2) push(`Class ${top2[1][0]} is also plausible (probability ${top2[1][1].toFixed(2)}); the class boundary here is uncertain.`);
  push(`Spatial detail is limited to the ${p.effective_resolution_m} m effective resolution of the inputs; the polygon edge is not a surveyed boundary.`);
  push("The classification has not been verified by a field visit for this unit.");
  return out;
}

export function recommendationsFor(f: SuitabilityFeature, r: RestorationFeature | null): Statement[] {
  const p = f.properties;
  const out: Statement[] = [];
  const push = (text: string) => out.push({ text, evidence: "expert_rule" });
  if (p.class_code === 5) {
    push("Do not plan cultivation: the restriction applies. Confirm the restriction with the competent authority before any land-use decision.");
    return out;
  }
  if (p.class_code === 1) push("Proceed to field verification and soil sampling before investment; maintain current management.");
  if (p.class_code === 2) push("Cultivable with care: address the limiting factors below and choose crops that tolerate them.");
  const seen = new Set<string>();
  for (const x of p.factors.filter((x) => x.status === "limiting" || x.status === "marginal")) {
    const a = ACTION[x.name];
    if (a && !seen.has(a)) {
      seen.add(a);
      push(`${factorLabel(x.name)}: ${a}`);
    }
  }
  if (r) {
    if (r.properties.feasibility.class === "not_feasible") push("Model 2 classes restoration as not feasible: do not invest in reclamation without a new assessment.");
    else push(`Restoration is rated ${r.properties.feasibility.class.replace("_", " ")} feasibility. Compare the scenarios on the Restoration page against your water and time constraints.`);
  }
  push("Verify with a field visit and laboratory soil analysis. Demonstration data must not be used for decisions.");
  return out;
}
