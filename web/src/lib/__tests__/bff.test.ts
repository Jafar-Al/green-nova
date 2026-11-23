import { describe, expect, it, vi, afterEach } from "vitest";
import { backendBase, isRejection, resolveBff } from "../bff/allowlist";
import { createApiProvider } from "../providers/api";
import { ProviderError } from "../types";

const JOB = "a".repeat(32);

describe("BFF allowlist", () => {
  it("maps allowed GET shapes to fixed backend paths", () => {
    const ok = (segs: string[], search = "") => {
      const r = resolveBff("GET", segs, search, null);
      if (isRejection(r)) throw new Error(`rejected ${segs.join("/")}`);
      return r.path;
    };
    expect(ok(["regions"])).toBe("/v1/regions");
    expect(ok(["regions", "jo-maan", "boundary"])).toBe("/v1/regions/jo-maan/boundary");
    expect(ok(["regions", "jo-maan", "suitability", "run"])).toBe("/v1/regions/jo-maan/suitability/run");
    expect(ok(["regions", "jo-maan", "suitability", "polygons"])).toBe("/v1/regions/jo-maan/suitability/polygons");
    expect(ok(["regions", "jo-maan", "restoration", "layer"])).toBe("/v1/regions/jo-maan/restoration/layer");
    expect(ok(["jobs", JOB])).toBe(`/v1/jobs/${JOB}`);
    expect(ok(["jobs", JOB, "result"])).toBe(`/v1/jobs/${JOB}/result`);
    expect(ok(["land", "m1-jo-maan-12"])).toBe("/v1/land/m1-jo-maan-12");
    expect(ok(["land", "m1-jo-maan-12", "geotiff"], "?layer=feasibility")).toBe("/v1/land/m1-jo-maan-12/geotiff?layer=feasibility");
  });

  it("rejects everything else: unknown paths, traversal, bad ids, other methods", () => {
    const bad = (m: string, segs: string[], search = "", body: string | null = null) => isRejection(resolveBff(m, segs, search, body));
    expect(bad("GET", ["health"])).toBe(true);
    expect(bad("GET", ["docs"])).toBe(true);
    expect(bad("GET", ["openapi.json"])).toBe(true);
    expect(bad("GET", ["regions", "..", "boundary"])).toBe(true);
    expect(bad("GET", ["regions", "JO-MAAN", "boundary"])).toBe(true);
    expect(bad("GET", ["regions", "jo-maan", "admin"])).toBe(true);
    expect(bad("GET", ["jobs", "notahexid"])).toBe(true);
    expect(bad("GET", ["land", "m1-jo-maan-12", "geotiff"], "?layer=../../etc")).toBe(true);
    expect(bad("DELETE", ["jobs", JOB])).toBe(true);
    expect(bad("PUT", ["jobs"])).toBe(true);
    expect(bad("POST", ["regions"], "", "{}")).toBe(true);
  });

  it("validates and re-serialises job bodies; drops nothing silently", () => {
    const post = (b: unknown) => resolveBff("POST", ["jobs"], "", typeof b === "string" ? b : JSON.stringify(b));
    const ok = post({ kind: "restoration", region_id: "jo-maan", polygon_ids: ["m1-jo-maan-1", "m1-jo-maan-2"] });
    expect(isRejection(ok)).toBe(false);
    if (!isRejection(ok)) expect(JSON.parse(ok.body!)).toEqual({ kind: "restoration", region_id: "jo-maan", polygon_ids: ["m1-jo-maan-1", "m1-jo-maan-2"] });
    expect(isRejection(post({ kind: "suitability", region_id: "jo-maan" }))).toBe(false);
    expect(isRejection(post({ kind: "suitability", region_id: "jo-maan", extra: 1 }))).toBe(true);
    expect(isRejection(post({ kind: "hack", region_id: "jo-maan" }))).toBe(true);
    expect(isRejection(post({ kind: "restoration", region_id: "jo-maan", polygon_ids: [] }))).toBe(true);
    expect(isRejection(post({ kind: "restoration", region_id: "jo-maan", polygon_ids: ["../x"] }))).toBe(true);
    expect(isRejection(post({ kind: "restoration", region_id: "jo-maan", polygon_ids: Array.from({ length: 501 }, (_, i) => `m1-jo-maan-${i}`) }))).toBe(true);
    expect(isRejection(post("not json"))).toBe(true);
    expect(isRejection(post([1]))).toBe(true);
    const cancel = resolveBff("POST", ["jobs", JOB, "cancel"], "", "{}");
    expect(isRejection(cancel)).toBe(false);
  });

  it("only talks to a loopback backend", () => {
    expect(backendBase(undefined)).toBe("http://127.0.0.1:8000");
    expect(backendBase("http://localhost:8000/")).toBe("http://localhost:8000");
    expect(() => backendBase("http://evil.example.com:8000")).toThrow();
    expect(() => backendBase("http://10.0.0.5:8000")).toThrow();
  });
});

describe("apiProvider (real, through the BFF)", () => {
  afterEach(() => vi.unstubAllGlobals());
  const stub = (handler: (url: string, init?: RequestInit) => { status: number; body: unknown }) =>
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const r = handler(String(url), init);
        return new Response(JSON.stringify(r.body), { status: r.status, headers: { "content-type": "application/json" } });
      }),
    );

  it("is not demo, calls only same-origin /api/gn paths", async () => {
    const urls: string[] = [];
    stub((u) => {
      urls.push(u);
      return { status: 200, body: { regions: [{ id: "jo-maan", country: "JO", name: "Ma'an", iso: null, bbox: [1, 2, 3, 4], boundary_area_km2: 1, models: { suitability: { available: true }, restoration: { available: false } } }] } };
    });
    const api = createApiProvider();
    expect(api.isDemo).toBe(false);
    const regions = await api.listRegions("JO");
    expect(regions[0]).toMatchObject({ id: "jo-maan", available: true });
    expect(urls.every((u) => u.startsWith("/api/gn/"))).toBe(true);
  });

  it("maps 503 to 'unavailable' with the server's user-facing message, 404 to not_found, network failure to offline", async () => {
    const api = createApiProvider();
    stub(() => ({ status: 503, body: { error: { code: "model_unavailable", message: "Model 2 (restoration potential) is not available for this region yet." } } }));
    await expect(api.getRestorationRun("a".repeat(32))).rejects.toMatchObject({ code: "unavailable", message: expect.stringContaining("not available") });
    stub(() => ({ status: 404, body: { error: { code: "unknown_polygon", message: "Land unit not found in the current analysis." } } }));
    await expect(api.getLandDetail("m1-jo-maan-999999")).rejects.toMatchObject({ code: "not_found" });
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("network"))));
    await expect(api.getJob("a".repeat(32))).rejects.toBeInstanceOf(ProviderError);
    await expect(api.getJob("a".repeat(32))).rejects.toMatchObject({ code: "offline" });
  });

  it("restoration layer is optional: 503 -> null", async () => {
    stub(() => ({ status: 503, body: { error: { code: "model_unavailable", message: "x" } } }));
    expect(await createApiProvider().getRestorationLayer("jo-maan")).toBeNull();
  });

  it("real exports carry NO demonstration marker", async () => {
    const polys = { type: "FeatureCollection", features: [] };
    const run = { region_id: "jo-maan", created_at: "t", stats: [], polygon_count: 0, total_area_ha: 0, total_area_dunum: 0, metadata: { model_version: "m1" }, demo: false };
    stub((u) => ({ status: 200, body: u.includes("/run") ? run : polys }));
    const art = await createApiProvider().exportSuitability("jo-maan", "geojson");
    expect(art.demo).toBe(false);
    expect(art.content).not.toMatch(/DEMONSTRATION DATA/);
    const csv = await createApiProvider().exportSuitability("jo-maan", "csv");
    expect(csv.content).not.toMatch(/DEMONSTRATION DATA/);
    await expect(createApiProvider().exportSuitability("jo-maan", "geotiff")).rejects.toMatchObject({ code: "not_implemented" });
  });
});
