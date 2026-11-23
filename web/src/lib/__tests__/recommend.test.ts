import { describe, expect, it } from "vitest";
import { limitationsFor, recommendationsFor } from "../recommend";
import { demoDataset } from "./fixtures";

const ds = demoDataset();
const byClass = (c: number) => ds.suitability.features.find((f) => f.properties.class_code === c)!;

describe("rule-based statements", () => {
  it("are always expert_rule evidence", () => {
    for (const c of [1, 2, 3, 4, 5]) {
      const f = byClass(c);
      const rest = ds.restoration.features.find((r) => r.properties.source_polygon_id === f.properties.id) ?? null;
      for (const s of [...limitationsFor(f), ...recommendationsFor(f, rest)]) expect(s.evidence).toBe("expert_rule");
    }
  });
  it("class 5 is never recommended for cultivation", () => {
    const recs = recommendationsFor(byClass(5), null).map((r) => r.text).join(" ");
    expect(recs).toMatch(/Do not plan cultivation/);
  });
  it("limitations always state the resolution caveat and missing field verification", () => {
    const l = limitationsFor(byClass(1)).map((s) => s.text).join(" ");
    expect(l).toMatch(/30 m effective resolution/);
    expect(l).toMatch(/not been verified/);
  });
  it("restorable units get a restoration pointer", () => {
    const f = ds.suitability.features.find((x) => x.properties.class_code === 3)!;
    const rest = ds.restoration.features.find((r) => r.properties.source_polygon_id === f.properties.id)!;
    expect(recommendationsFor(f, rest).map((r) => r.text).join(" ")).toMatch(/Restoration is rated|not feasible/);
  });
});
