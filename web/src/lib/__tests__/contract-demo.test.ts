import { describe, expect, it } from "vitest";
import {
  EVIDENCE_VALUES,
  isEvidence,
  isRestorationProperties,
  isSuitabilityProperties,
  parseRestorationCollection,
  parseSuitabilityCollection,
} from "../contract";
import { generateDemoDataset } from "../demo/generate";
import { geometryAreaHaDunum, pointInRing } from "../geo";
import { demoDataset, maanRing } from "./fixtures";

describe("contract guards", () => {
  const ds = demoDataset();
  const sample = ds.suitability.features[0]!;

  it("accepts every generated Model 1 and Model 2 record", () => {
    expect(ds.suitability.features.every((f) => isSuitabilityProperties(f.properties))).toBe(true);
    expect(ds.restoration.features.every((f) => isRestorationProperties(f.properties))).toBe(true);
    expect(parseSuitabilityCollection(ds.suitability).errors).toEqual([]);
    expect(parseRestorationCollection(ds.restoration).errors).toEqual([]);
  });

  it("tolerates unknown extra properties (contract: ML agents may ADD optional fields)", () => {
    const extra = { ...sample.properties, brand_new_field: { a: 1 }, factors: sample.properties.factors.map((f) => ({ ...f, extra_note: "x" })) };
    expect(isSuitabilityProperties(extra)).toBe(true);
  });

  it("rejects out-of-contract values", () => {
    const p = sample.properties;
    expect(isSuitabilityProperties({ ...p, class_code: 6 })).toBe(false);
    expect(isSuitabilityProperties({ ...p, confidence: 1.2 })).toBe(false);
    expect(isSuitabilityProperties({ ...p, centroid: [200, 0] })).toBe(false);
    expect(isSuitabilityProperties({ ...p, factors: [{ ...p.factors[0], evidence: "guess" }] })).toBe(false);
    const { class_probabilities: _omit, ...missing } = p;
    void _omit;
    expect(isSuitabilityProperties(missing)).toBe(false);
    expect(isSuitabilityProperties(null)).toBe(false);
  });

  it("restoration scenarios must be evidence 'simulated' with ordered water ranges", () => {
    const withScen = ds.restoration.features.find((f) => f.properties.scenarios.length > 0)!;
    const bad = {
      ...withScen.properties,
      scenarios: [{ ...withScen.properties.scenarios[0]!, evidence: "observed" }],
    };
    expect(isRestorationProperties(bad)).toBe(false);
    const sc = withScen.properties.scenarios[0]!;
    const unordered = { ...withScen.properties, scenarios: [{ ...sc, water_requirement_m3_ha_yr: { low: 9, central: 5, high: 7 } }] };
    expect(isRestorationProperties(unordered)).toBe(false);
  });

  it("parse drops and reports bad features instead of repairing them", () => {
    const fc = { type: "FeatureCollection", features: [sample, { ...sample, properties: { id: "x" } }, { type: "Feature", geometry: null, properties: {} }] };
    const r = parseSuitabilityCollection(fc);
    expect(r.features).toHaveLength(1);
    expect(r.errors).toHaveLength(2);
    expect(parseSuitabilityCollection({ type: "Nope" }).errors[0]).toMatch(/FeatureCollection/);
  });

  it("evidence vocabulary is exactly the four contract values", () => {
    expect([...EVIDENCE_VALUES]).toEqual(["observed", "ml_predicted", "expert_rule", "simulated"]);
    expect(isEvidence("observed")).toBe(true);
    expect(isEvidence("verified")).toBe(false);
  });
});

describe("demo dataset", () => {
  const ds = demoDataset();
  const feats = ds.suitability.features;

  it("is Ma'an-shaped, sizeable and covers all five classes", () => {
    expect(feats.length).toBeGreaterThanOrEqual(150);
    for (const c of [1, 2, 3, 4, 5]) expect(feats.filter((f) => f.properties.class_code === c).length).toBeGreaterThan(5);
  });

  it("is deterministic for a seed and differs across seeds", () => {
    const again = generateDemoDataset({ regionId: "jo-maan", ring: maanRing(), now: "2026-01-01T00:00:00.000Z" });
    expect(JSON.stringify(again)).toBe(JSON.stringify(ds));
    const other = generateDemoDataset({ regionId: "jo-maan", ring: maanRing(), seed: 7, now: "2026-01-01T00:00:00.000Z" });
    expect(JSON.stringify(other.suitability)).not.toBe(JSON.stringify(ds.suitability));
  });

  it("ids are unique and follow m1-<region>-<n> / m2-<region>-<n>", () => {
    expect(new Set(feats.map((f) => f.properties.id)).size).toBe(feats.length);
    expect(feats.every((f) => /^m1-jo-maan-\d+$/.test(f.properties.id))).toBe(true);
    expect(ds.restoration.features.every((f) => /^m2-jo-maan-\d+$/.test(f.properties.id))).toBe(true);
  });

  it("every polygon lies inside the Ma'an boundary and stated area matches the equal-area geometry", () => {
    const ring = maanRing();
    for (const f of feats) {
      const g = f.geometry;
      expect(g.type).toBe("Polygon");
      if (g.type !== "Polygon") continue;
      expect(g.coordinates[0]!.every(([x, y]) => pointInRing(x!, y!, ring))).toBe(true);
      const { area_ha, area_dunum } = geometryAreaHaDunum(g);
      expect(Math.abs(area_ha - f.properties.area_ha) / area_ha).toBeLessThan(0.01);
      expect(Math.abs(area_dunum / f.properties.area_dunum - 1)).toBeLessThan(0.01);
      expect(f.properties.area_dunum / f.properties.area_ha).toBeCloseTo(10, 1);
    }
  });

  it("coordinates are rounded to <= 6 decimals (contract)", () => {
    for (const f of feats.slice(0, 40)) {
      for (const [x, y] of (f.geometry as { coordinates: number[][][] }).coordinates[0]!) {
        expect(Math.abs(x! * 1e6 - Math.round(x! * 1e6))).toBeLessThan(1e-3);
        expect(Math.abs(y! * 1e6 - Math.round(y! * 1e6))).toBeLessThan(1e-3);
      }
    }
  });

  it("class probabilities sum to 1 and confidence is the top probability", () => {
    for (const f of feats) {
      const p = f.properties;
      const probs = Object.values(p.class_probabilities);
      expect(probs.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 2);
      expect(p.confidence).toBe(p.class_probabilities[String(p.class_code) as "1"]);
      expect(Math.max(...probs)).toBe(p.confidence);
    }
  });

  it("is labelled synthetic in its own provenance and confidence method", () => {
    for (const f of feats) {
      expect(f.properties.provenance.model_version).toMatch(/demo-synthetic/);
      expect(f.properties.confidence_method).toMatch(/Synthetic/);
    }
    for (const f of ds.restoration.features) {
      expect(f.properties.provenance.source_studies).toEqual([]);
      expect(f.properties.interventions.every((i) => i.source_refs.some((s) => /placeholder/i.test(s)))).toBe(true);
    }
  });

  it("only class 3 and 4 units have restoration records; class 5 never does", () => {
    const byId = new Map(feats.map((f) => [f.properties.id, f.properties.class_code] as const));
    for (const f of ds.restoration.features) expect([3, 4]).toContain(byId.get(f.properties.source_polygon_id));
    const n34 = feats.filter((f) => f.properties.class_code === 3 || f.properties.class_code === 4).length;
    expect(ds.restoration.features.length).toBe(n34);
    expect(ds.restoration.features.some((f) => byId.get(f.properties.source_polygon_id) === 5)).toBe(false);
  });

  it("class 5 units carry a restricted factor; class 1 has no limiting factor", () => {
    for (const f of feats) {
      const st = f.properties.factors.map((x) => x.status);
      if (f.properties.class_code === 5) expect(st).toContain("restricted");
      if (f.properties.class_code === 1) expect(st).not.toContain("limiting");
    }
  });

  it("restoration feasibility is coherent with scenarios", () => {
    for (const f of ds.restoration.features) {
      const p = f.properties;
      expect(p.feasibility.interval[0]).toBeLessThanOrEqual(p.feasibility.score);
      expect(p.feasibility.interval[1]).toBeGreaterThanOrEqual(p.feasibility.score);
      if (p.feasibility.class === "not_feasible") expect(p.scenarios).toHaveLength(0);
      for (const s of p.scenarios) {
        expect(s.evidence).toBe("simulated");
        expect(s.post_class_code).toBeLessThanOrEqual(p.current_class_code);
        expect(s.intervention_ids.every((id) => p.interventions.some((i) => i.id === id) || id === "iv-drip-irrigation" || id === "iv-organic-matter")).toBe(true);
      }
    }
    const classes = new Set(ds.restoration.features.map((f) => f.properties.feasibility.class));
    expect(classes.size).toBeGreaterThanOrEqual(3);
  });
});
