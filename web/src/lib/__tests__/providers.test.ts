import { describe, expect, it } from "vitest";
import { createDemoProvider } from "../providers/demo";
import { ProviderError } from "../types";
import { DEMO_NOTICE } from "../demo/notice";
import { loadAdm1 } from "./fixtures";

function setup() {
  let t = 1_000_000;
  const provider = createDemoProvider({ loadAdm1: async () => loadAdm1(), latencyMs: 0, now: () => t, jobDurationMs: { suitability: 4000, restoration: 3000 } });
  return { provider, advance: (ms: number) => void (t += ms) };
}

describe("demoProvider", () => {
  it("identifies itself as demo", () => {
    const { provider } = setup();
    expect(provider.isDemo).toBe(true);
    expect(provider.id).toBe("demo");
  });

  it("lists Jordan and 12 governorates, Ma'an first and the only available one", async () => {
    const { provider } = setup();
    expect((await provider.listCountries()).map((c) => c.code)).toEqual(["JO"]);
    const regions = await provider.listRegions("JO");
    expect(regions).toHaveLength(12);
    expect(regions[0]).toMatchObject({ id: "jo-maan", available: true });
    expect(regions.filter((r) => r.available)).toHaveLength(1);
    const maan = regions[0]!;
    expect(maan.boundary_area_km2).toBeGreaterThan(30000);
    expect(maan.boundary_area_km2).toBeLessThan(36000);
    expect(await provider.listRegions("XX")).toEqual([]);
  });

  it("serves the Ma'an run with per-class stats that add up", async () => {
    const { provider } = setup();
    const run = await provider.getSuitabilityRun("jo-maan");
    expect(run).not.toBeNull();
    const r = run!;
    expect(r.demo).toBe(true);
    expect(r.stats.map((s) => s.code)).toEqual([1, 2, 3, 4, 5]);
    expect(r.stats.reduce((a, s) => a + s.polygon_count, 0)).toBe(r.polygon_count);
    expect(r.stats.reduce((a, s) => a + s.share, 0)).toBeCloseTo(1, 2);
    expect(r.stats.reduce((a, s) => a + s.area_ha, 0)).toBeCloseTo(r.total_area_ha, -1);
    expect(r.total_area_dunum / r.total_area_ha).toBeCloseTo(10, 1);
  });

  it("serves a region-wide precomputed restoration layer (class 3/4 only) and null elsewhere", async () => {
    const { provider } = setup();
    const layer = await provider.getRestorationLayer("jo-maan");
    expect(layer!.features.length).toBeGreaterThan(50);
    expect(await provider.getRestorationLayer("jo-karak")).toBeNull();
  });

  it("returns an empty run (null) for an unanalysed governorate and refuses polygons / jobs", async () => {
    const { provider } = setup();
    expect(await provider.getSuitabilityRun("jo-karak")).toBeNull();
    await expect(provider.getSuitabilityPolygons("jo-karak")).rejects.toMatchObject({ code: "not_found" });
    await expect(provider.startSuitabilityJob("jo-karak")).rejects.toBeInstanceOf(ProviderError);
    await expect(provider.getRegionBoundary("jo-nowhere")).rejects.toMatchObject({ code: "not_found" });
  });

  it("job lifecycle: queued -> running -> succeeded (simulated clock)", async () => {
    const { provider, advance } = setup();
    const job = await provider.startSuitabilityJob("jo-maan");
    expect(job.demo).toBe(true);
    expect(job.state).toBe("queued");
    advance(1500);
    const running = await provider.getJob(job.id);
    expect(running.state).toBe("running");
    expect(running.progress).toBeGreaterThan(0);
    expect(running.progress).toBeLessThan(1);
    advance(3000);
    const done = await provider.getJob(job.id);
    expect(done.state).toBe("succeeded");
    expect(done.progress).toBe(1);
  });

  it("simulated failure ends in a recoverable failed state", async () => {
    const { provider, advance } = setup();
    const job = await provider.startSuitabilityJob("jo-maan", { simulateFailure: true });
    advance(3000);
    const failed = await provider.getJob(job.id);
    expect(failed.state).toBe("failed");
    expect(failed.error?.recoverable).toBe(true);
    expect(failed.error?.message).toMatch(/Simulated/);
  });

  it("jobs can be cancelled while running", async () => {
    const { provider, advance } = setup();
    const job = await provider.startSuitabilityJob("jo-maan");
    advance(1000);
    expect((await provider.cancelJob(job.id)).state).toBe("cancelled");
    advance(10_000);
    expect((await provider.getJob(job.id)).state).toBe("cancelled");
  });

  it("restoration run: only class 3/4 are analysed; class 5 and 1/2 are rejected with a reason", async () => {
    const { provider, advance } = setup();
    const fc = await provider.getSuitabilityPolygons("jo-maan");
    const pick = (c: number) => fc.features.find((f) => f.properties.class_code === c)!.properties.id;
    const ids = [pick(3), pick(4), pick(5), pick(1)];
    const job = await provider.startRestorationJob({ region_id: "jo-maan", polygon_ids: ids });
    await expect(provider.getRestorationRun(job.id)).rejects.toMatchObject({ code: "unavailable" });
    advance(5000);
    const run = await provider.getRestorationRun(job.id);
    expect(run.features.map((f) => f.properties.source_polygon_id).sort()).toEqual([pick(3), pick(4)].sort());
    expect(run.rejected.map((r) => r.id).sort()).toEqual([pick(5), pick(1)].sort());
    expect(run.rejected.find((r) => r.id === pick(5))!.reason).toMatch(/never treated as restorable/);
    await expect(provider.startRestorationJob({ region_id: "jo-maan", polygon_ids: [] })).rejects.toBeInstanceOf(ProviderError);
  });

  it("land detail: restoration present for class 3/4 with a note otherwise", async () => {
    const { provider } = setup();
    const fc = await provider.getSuitabilityPolygons("jo-maan");
    const id3 = fc.features.find((f) => f.properties.class_code === 3)!.properties.id;
    const id5 = fc.features.find((f) => f.properties.class_code === 5)!.properties.id;
    const id1 = fc.features.find((f) => f.properties.class_code === 1)!.properties.id;
    expect((await provider.getLandDetail(id3)).restoration).not.toBeNull();
    const d5 = await provider.getLandDetail(id5);
    expect(d5.restoration).toBeNull();
    expect(d5.restoration_note).toMatch(/never treated as restorable/);
    expect((await provider.getLandDetail(id1)).restoration_note).toMatch(/class 3 and 4/);
    await expect(provider.getLandDetail("m1-jo-maan-99999")).rejects.toMatchObject({ code: "not_found" });
    await expect(provider.getLandDetail("garbage")).rejects.toMatchObject({ code: "not_found" });
  });

  it("every demo export carries the DEMONSTRATION DATA marker", async () => {
    const { provider, advance } = setup();
    const geo = await provider.exportSuitability("jo-maan", "geojson");
    const parsed = JSON.parse(geo.content!);
    expect(geo.demo).toBe(true);
    expect(geo.filename).toMatch(/DEMO/);
    expect(parsed.demonstration_data).toBe(true);
    expect(parsed.notice).toBe(DEMO_NOTICE);
    expect(parsed.area_units.area_dunum).toMatch(/1,000/);
    expect(parsed.features.every((f: { properties: { demonstration_data?: boolean } }) => f.properties.demonstration_data === true)).toBe(true);

    const csv = await provider.exportSuitability("jo-maan", "csv");
    expect(csv.content!.split("\r\n")[0]).toBe(`# ${DEMO_NOTICE}`);
    expect(csv.content).toContain("demonstration_data");

    const summary = JSON.parse((await provider.exportSuitability("jo-maan", "summary_json")).content!);
    expect(summary.demonstration_data).toBe(true);
    expect(Object.keys(summary.per_class)).toEqual(["1", "2", "3", "4", "5"]);

    const fc = await provider.getSuitabilityPolygons("jo-maan");
    const ids = fc.features.filter((f) => f.properties.class_code === 3).slice(0, 3).map((f) => f.properties.id);
    const job = await provider.startRestorationJob({ region_id: "jo-maan", polygon_ids: ids });
    advance(5000);
    const constraints = { max_water_m3_ha_yr: null, allowed_water_sources: ["Treated wastewater", "Groundwater", "Rainwater harvesting", "Existing groundwater wells", "Desalinated brackish water"], max_years: 10, min_feasibility: "low" as const, exclude_irreversible: false };
    const rg = await provider.exportRestoration(job.id, "geojson", { constraints, preference: "best" });
    expect(JSON.parse(rg.content!).demonstration_data).toBe(true);
    const rc = await provider.exportRestoration(job.id, "csv", { constraints, preference: "best" });
    expect(rc.content!.startsWith(`# ${DEMO_NOTICE}`)).toBe(true);
    const rh = await provider.exportRestoration(job.id, "report_html", { constraints, preference: "best" });
    expect(rh.content).toContain(DEMO_NOTICE);
    expect(rh.content).toContain("1 dunum = 1,000");
  });

  it("GeoTIFF / PDF are honestly unavailable in demo mode", async () => {
    const { provider } = setup();
    const caps = provider.capabilities();
    expect(caps.exports.geotiff.available).toBe(false);
    expect(caps.exports.pdf.available).toBe(false);
    expect(caps.exports.geotiff.reason).toMatch(/Phase C/);
    await expect(provider.exportSuitability("jo-maan", "geotiff")).rejects.toMatchObject({ code: "not_implemented" });
  });
});
