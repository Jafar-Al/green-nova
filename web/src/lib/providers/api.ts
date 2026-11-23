/**
 * apiProvider (Phase C): real analysis through the same-origin BFF (/api/gn/*), which calls the internal FastAPI service server-side.
 * Browsers never learn the backend address. Everything returned here comes from the models' real output files (validated server-side);
 * nothing is synthesised. Exports are built from those real results with the demo marker OFF.
 */
import type { RestorationCollection, SuitabilityCollection } from "../contract";
import { buildRestorationCSV, buildRestorationGeoJSON, buildRestorationReportHTML, buildSuitabilityCSV, buildSuitabilityGeoJSON, buildSuitabilitySummaryJSON } from "../export";
import {
  ProviderError,
  type AnalysisJob,
  type Country,
  type DataProvider,
  type ExportArtifact,
  type ExportFormat,
  type LandDetail,
  type ProviderCapabilities,
  type RegionBoundary,
  type RegionInfo,
  type RestorationExportOptions,
  type RestorationJobRequest,
  type RestorationRun,
  type SuitabilityRun,
} from "../types";

export const NOT_IMPLEMENTED_MESSAGE = "not implemented — Phase C";
const BASE = "/api/gn";

interface ApiRegion {
  id: string;
  country: string;
  name: string;
  iso: string | null;
  bbox: [number, number, number, number];
  boundary_area_km2: number;
  models: { suitability: { available: boolean; reason?: string | null; version?: string | null }; restoration: { available: boolean } };
}

async function call<T>(path: string, init?: RequestInit & { allow404?: boolean }): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/${path}`, { ...init, headers: { accept: "application/json", ...(init?.body ? { "content-type": "application/json" } : {}) }, cache: "no-store" });
  } catch {
    throw new ProviderError("offline", "Could not reach the server. Check your connection and try again.");
  }
  if (res.ok) return (await res.json()) as T;
  let code = "error";
  let message = `The server answered with status ${res.status}.`;
  try {
    const j = (await res.json()) as { error?: { code?: string; message?: string } };
    if (j.error?.message) message = j.error.message;
    if (j.error?.code) code = j.error.code;
  } catch {
    /* non-JSON error body: keep the generic message */
  }
  if (res.status === 404) throw new ProviderError("not_found", message);
  if (res.status === 503 || res.status === 502 || res.status === 429 || code === "model_unavailable") throw new ProviderError("unavailable", message);
  throw new ProviderError("invalid_response", message);
}

let regionsP: Promise<ApiRegion[]> | null = null;
const regions = (): Promise<ApiRegion[]> => (regionsP ??= call<{ regions: ApiRegion[] }>("regions").then((r) => r.regions).catch((e) => ((regionsP = null), Promise.reject(e))));

const jobBody = (o: Record<string, unknown>): RequestInit => ({ method: "POST", body: JSON.stringify(o) });

export function createApiProvider(): DataProvider {
  const caps: ProviderCapabilities = {
    exports: {
      geojson: { available: true },
      csv: { available: true },
      summary_json: { available: true },
      report_html: { available: true },
      geotiff: { available: false, reason: "GeoTIFF clips are downloaded per land unit from the land details page." },
      pdf: { available: false, reason: "Open the HTML report and use Print > Save as PDF." },
    },
    rasterLayers: false,
  };

  const suitabilityRunAndPolygons = async (regionId: string) => {
    const [run, polys] = await Promise.all([call<SuitabilityRun>(`regions/${regionId}/suitability/run`), call<SuitabilityCollection>(`regions/${regionId}/suitability/polygons`)]);
    return { run, polys };
  };

  const provider: DataProvider = {
    id: "api",
    isDemo: false,
    label: "Live analysis",
    capabilities: () => caps,

    async listCountries(): Promise<Country[]> {
      await regions();
      return [{ code: "JO", name: "Jordan", available: true }];
    },

    async listRegions(country: string): Promise<RegionInfo[]> {
      if (country.toUpperCase() !== "JO") return [];
      return (await regions()).map((r) => ({
        id: r.id,
        country: r.country,
        name: r.name,
        iso: r.iso ?? undefined,
        available: !!r.models.suitability.available,
        bbox: r.bbox,
        boundary_area_km2: r.boundary_area_km2,
      }));
    },

    getRegionBoundary: (id: string) => call<RegionBoundary>(`regions/${id}/boundary`),

    async getSuitabilityRun(id: string): Promise<SuitabilityRun | null> {
      try {
        return await call<SuitabilityRun>(`regions/${id}/suitability/run`);
      } catch (e) {
        if (e instanceof ProviderError && e.code === "unavailable") {
          // other governorates simply have no analysis; if NO region has Model 1 output the model itself is unavailable
          const rs = await regions();
          const here = rs.find((r) => r.id === id);
          if (here && !here.models.suitability.available && rs.some((r) => r.models.suitability.available)) return null;
        }
        throw e;
      }
    },

    getSuitabilityPolygons: (id: string) => call<SuitabilityCollection>(`regions/${id}/suitability/polygons`),

    async getRestorationLayer(id: string): Promise<RestorationCollection | null> {
      try {
        const layer = await call<RestorationCollection>(`regions/${id}/restoration/layer`);
        return layer.features.length > 0 ? layer : null; // empty = not yet linked to the current Model 1 polygons
      } catch (e) {
        if (e instanceof ProviderError && (e.code === "unavailable" || e.code === "not_found")) return null; // optional layer
        throw e;
      }
    },

    startSuitabilityJob: (id: string) => call<AnalysisJob>("jobs", jobBody({ kind: "suitability", region_id: id })),
    startRestorationJob: (req: RestorationJobRequest) => call<AnalysisJob>("jobs", jobBody({ kind: "restoration", region_id: req.region_id, polygon_ids: req.polygon_ids })),
    getJob: (id: string) => call<AnalysisJob>(`jobs/${id}`),
    cancelJob: (id: string) => call<AnalysisJob>(`jobs/${id}/cancel`, { method: "POST", body: "{}" }),
    getRestorationRun: (jobId: string) => call<RestorationRun>(`jobs/${jobId}/result`),
    getLandDetail: (polygonId: string) => call<LandDetail>(`land/${encodeURIComponent(polygonId)}`),

    async exportSuitability(regionId: string, format: ExportFormat): Promise<ExportArtifact> {
      const { run, polys } = await suitabilityRunAndPolygons(regionId);
      const o = { demo: false };
      const stem = `green-nova-suitability-${regionId}`;
      if (format === "geojson") return { filename: `${stem}.geojson`, mime: "application/geo+json", content: buildSuitabilityGeoJSON(polys, regionId, o), demo: false };
      if (format === "csv") return { filename: `${stem}.csv`, mime: "text/csv", content: buildSuitabilityCSV(polys, regionId, o), demo: false };
      if (format === "summary_json") return { filename: `${stem}-summary.json`, mime: "application/json", content: buildSuitabilitySummaryJSON(run, o), demo: false };
      throw new ProviderError("not_implemented", caps.exports[format].reason ?? "This export is not available.");
    },

    async exportRestoration(jobId: string, format: ExportFormat, opts: RestorationExportOptions): Promise<ExportArtifact> {
      const run = await call<RestorationRun>(`jobs/${jobId}/result`);
      const o = { demo: false };
      const stem = `green-nova-restoration-${run.region_id}`;
      if (format === "geojson") return { filename: `${stem}.geojson`, mime: "application/geo+json", content: buildRestorationGeoJSON(run, opts.constraints, opts.preference, o), demo: false };
      if (format === "csv") return { filename: `${stem}.csv`, mime: "text/csv", content: buildRestorationCSV(run, opts.constraints, opts.preference, o), demo: false };
      if (format === "report_html") return { filename: `${stem}-report.html`, mime: "text/html", content: buildRestorationReportHTML(run, opts.constraints, opts.preference, o), demo: false };
      throw new ProviderError("not_implemented", caps.exports[format].reason ?? "This export is not available.");
    },
  };
  return provider;
}
