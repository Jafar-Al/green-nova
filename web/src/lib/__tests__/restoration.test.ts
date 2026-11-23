import { describe, expect, it } from "vitest";
import {
  availableWaterSources,
  chooseScenario,
  evaluatePolygon,
  evaluateRun,
  scenarioKey,
  summariseOutcome,
  withAllSources,
  DEFAULT_CONSTRAINTS,
} from "../restoration";
import { buildRestorationCSV, buildSuitabilityCSV, csvEscape } from "../export";
import type { RestorationRun } from "../types";
import { demoDataset } from "./fixtures";

const ds = demoDataset();
const features = ds.restoration.features;
const open = withAllSources({ ...DEFAULT_CONSTRAINTS, min_feasibility: "not_feasible" }, features);

describe("restoration constraints", () => {
  it("collects water sources from the data", () => {
    const s = availableWaterSources(features);
    expect(s).toContain("Treated wastewater");
    expect(s).toEqual([...s].sort((a, b) => a.localeCompare(b)));
  });

  it("scenarioKey is the tier suffix", () => {
    const sc = features.find((f) => f.properties.scenarios.length)!.properties.scenarios[0]!;
    expect(["conservative", "standard", "intensive"]).toContain(scenarioKey(sc));
    expect(scenarioKey({ ...sc, id: "free" })).toBe("free");
  });

  it("a tight water limit removes scenarios; a short horizon removes slow ones", () => {
    const f = features.find((x) => x.properties.scenarios.length === 3)!;
    const base = evaluatePolygon(f, open);
    expect(base.scenarios.every((s) => s.viable)).toBe(true);
    const dry = evaluatePolygon(f, { ...open, max_water_m3_ha_yr: 1 });
    expect(dry.scenarios.every((s) => !s.viable)).toBe(true);
    expect(dry.scenarios[0]!.reasons[0]).toMatch(/exceeds the limit/);
    const fast = evaluatePolygon(f, { ...open, max_years: 2 });
    expect(fast.scenarios.every((s) => !s.viable)).toBe(true);
    const noSources = evaluatePolygon(f, { ...open, allowed_water_sources: [] });
    expect(noSources.scenarios.every((s) => !s.viable)).toBe(true);
  });

  it("minimum feasibility and irreversible-exclusion exclude polygons with reasons", () => {
    const high = features.filter((f) => f.properties.feasibility.class === "high");
    const notFeasible = features.filter((f) => f.properties.feasibility.class === "not_feasible");
    expect(high.length + notFeasible.length).toBeGreaterThan(0);
    for (const f of notFeasible) {
      const ev = evaluatePolygon(f, open);
      expect(ev.excludedReasons.length).toBeGreaterThan(0);
      expect(chooseScenario(ev, "best")).toBeNull();
    }
    const strict = { ...open, min_feasibility: "high" as const };
    for (const f of features.filter((x) => x.properties.feasibility.class === "low")) {
      expect(evaluatePolygon(f, strict).excludedReasons.join(" ")).toMatch(/below the minimum/);
    }
    const noIrrev = { ...open, exclude_irreversible: true };
    const hit = features.find((f) => f.properties.limiting_factors.some((l) => l.reversibility === "irreversible" && l.severity >= 0.6));
    if (hit) expect(evaluatePolygon(hit, noIrrev).excludedReasons.join(" ")).toMatch(/irreversible/);
  });

  it("chooseScenario('best') prefers the lowest post class", () => {
    const f = features.find((x) => x.properties.scenarios.length === 3)!;
    const ev = evaluatePolygon(f, open);
    const best = chooseScenario(ev, "best")!;
    expect(best.post_class_code).toBe(Math.min(...f.properties.scenarios.map((s) => s.post_class_code)));
    expect(chooseScenario(ev, "conservative")!.id).toMatch(/conservative$/);
    expect(chooseScenario(ev, "does-not-exist")).toBeNull();
  });

  it("outcome totals are conserved: before area = after area, water aggregates add up", () => {
    const evals = evaluateRun(features, open);
    const out = summariseOutcome(evals, "best");
    const sum = (r: Record<number, number>) => Object.values(r).reduce((a, b) => a + b, 0);
    expect(sum(out.before)).toBeCloseTo(out.total_ha, 6);
    expect(sum(out.after)).toBeCloseTo(out.total_ha, 6);
    expect(out.before[1] + out.before[2] + out.before[5]).toBe(0);
    expect(out.counts.analysed).toBe(features.length);
    expect(out.counts.with_scenario + out.counts.excluded + out.counts.no_viable_scenario).toBe(features.length);
    expect(out.water_mm3_yr.low).toBeLessThanOrEqual(out.water_mm3_yr.central);
    expect(out.water_mm3_yr.central).toBeLessThanOrEqual(out.water_mm3_yr.high);
    expect(out.improved_ha).toBeGreaterThan(0);
    // tightening constraints can only reduce the number of units that get a scenario
    const tight = summariseOutcome(evaluateRun(features, { ...open, max_water_m3_ha_yr: 3000 }), "best");
    expect(tight.counts.with_scenario).toBeLessThanOrEqual(out.counts.with_scenario);
  });
});

describe("exports", () => {
  const run: RestorationRun = {
    job_id: "j1",
    region_id: "jo-maan",
    polygon_ids: [],
    features: features.slice(0, 5),
    rejected: [],
    metadata: { model_version: "demo" },
    created_at: "2026-01-01T00:00:00Z",
    demo: true,
  };
  it("csvEscape quotes commas, quotes and newlines", () => {
    expect(csvEscape('a,"b"')).toBe('"a,""b"""');
    expect(csvEscape("x\ny")).toBe('"x\ny"');
    expect(csvEscape(null)).toBe("");
  });
  it("restoration CSV flags simulated columns and the demo marker; real data has none", () => {
    const demo = buildRestorationCSV(run, open, "best", { demo: true, generatedAt: "t" });
    expect(demo.split("\r\n")[0]).toMatch(/DEMONSTRATION DATA/);
    expect(demo).toMatch(/SIMULATED/);
    const real = buildRestorationCSV(run, open, "best", { demo: false, generatedAt: "t" });
    expect(real).not.toMatch(/DEMONSTRATION DATA/);
    const rows = demo.trim().split("\r\n").filter((l) => !l.startsWith("#"));
    expect(rows.length).toBe(1 + run.features.length);
  });
  it("suitability CSV has one row per polygon", () => {
    const csv = buildSuitabilityCSV({ type: "FeatureCollection", features: ds.suitability.features.slice(0, 7) }, "jo-maan", { demo: true, generatedAt: "t" });
    expect(csv.trim().split("\r\n").filter((l) => !l.startsWith("#")).length).toBe(8);
  });
});
