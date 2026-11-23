/**
 * demoProvider: clearly labelled synthetic, Ma'an-shaped data generated locally.
 * Nothing here calls a model or a server. Jobs are simulated timers that replay precomputed synthetic results.
 */
import type { Feature, FeatureCollection, MultiPolygon, Polygon } from "geojson";
import type { RestorationCollection, RunMetadata, SuitabilityClassCode, SuitabilityCollection } from "../contract";
import { SUITABILITY_CLASSES, CLASS_LIST, CLASS5_NOTE } from "../classes";
import {
  buildRestorationCSV,
  buildRestorationGeoJSON,
  buildRestorationReportHTML,
  buildSuitabilityCSV,
  buildSuitabilityGeoJSON,
  buildSuitabilitySummaryJSON,
} from "../export";
import { geometryAreaM2, geometryBBox } from "../geo";
import { m2ToDunum, m2ToHa, roundArea } from "../units";
import {
  ProviderError,
  type AnalysisJob,
  type ClassStat,
  type Country,
  type DataProvider,
  type ExportArtifact,
  type ExportFormat,
  type JobKind,
  type LandDetail,
  type ProviderCapabilities,
  type RegionBoundary,
  type RegionInfo,
  type RestorationExportOptions,
  type RestorationJobRequest,
  type RestorationRun,
  type SuitabilityRun,
} from "../types";
import { generateDemoDataset, type DemoDataset } from "../demo/generate";
import { DEMO_MODEL_VERSION, DEMO_SOURCE_LABEL } from "../demo/notice";

export const DEMO_REGION_ID = "jo-maan";
export const ADM1_URL = "/data/jordan_adm1.geojson";

type AdmProps = { shapeName: string; shapeISO?: string; shapeID?: string };
type AdmCollection = FeatureCollection<Polygon | MultiPolygon, AdmProps>;

export interface DemoProviderDeps {
  /** Loads the geoBoundaries ADM1 FeatureCollection (defaults to fetching /data/jordan_adm1.geojson). */
  loadAdm1?: () => Promise<AdmCollection>;
  /** Artificial latency for data calls, ms (exercises loading states). 0 in tests. */
  latencyMs?: number;
  /** Clock, ms epoch (injectable for tests). */
  now?: () => number;
  /** Simulated job durations, ms. */
  jobDurationMs?: Partial<Record<JobKind, number>>;
}

const slug = (name: string): string => name.toLowerCase().replace(/[^a-z]+/g, "");
const regionIdFor = (country: string, name: string): string => `${country.toLowerCase()}-${slug(name)}`;

const STAGES: Record<JobKind, string[]> = {
  suitability: [
    "Queued (demo)",
    "Loading synthetic covariates",
    "Replaying precomputed synthetic classification",
    "Vectorising land units",
    "Computing areas (equal-area projection)",
    "Finalising",
  ],
  restoration: [
    "Queued (demo)",
    "Loading selected land units",
    "Replaying precomputed synthetic feasibility",
    "Assembling synthetic scenarios",
    "Finalising",
  ],
};

interface JobRecord {
  id: string;
  kind: JobKind;
  region: string;
  startedAt: number;
  durationMs: number;
  failAt: number | null;
  cancelledAt: number | null;
  polygonIds: string[];
}

export function createDemoProvider(deps: DemoProviderDeps = {}): DataProvider {
  const latency = deps.latencyMs ?? 180;
  const now = deps.now ?? (() => Date.now());
  const durations: Record<JobKind, number> = { suitability: 4200, restoration: 3200, ...deps.jobDurationMs };
  const loadAdm1 =
    deps.loadAdm1 ??
    (async (): Promise<AdmCollection> => {
      let res: Response;
      try {
        res = await fetch(ADM1_URL);
      } catch {
        throw new ProviderError("offline", "Could not load the Jordan boundary file. Check your connection and try again.");
      }
      if (!res.ok) throw new ProviderError("unavailable", `Boundary file request failed (${res.status}).`);
      return (await res.json()) as AdmCollection;
    });

  let adm1P: Promise<AdmCollection> | null = null;
  const adm1 = (): Promise<AdmCollection> => (adm1P ??= loadAdm1().catch((e) => ((adm1P = null), Promise.reject(e))));
  const datasets = new Map<string, DemoDataset>();
  const jobs = new Map<string, JobRecord>();
  let jobSeq = 0;
  const delay = (): Promise<void> => (latency > 0 ? new Promise((r) => setTimeout(r, latency)) : Promise.resolve());

  async function boundaryFeature(regionId: string): Promise<Feature<Polygon | MultiPolygon, AdmProps>> {
    const fc = await adm1();
    const f = fc.features.find((x) => regionIdFor("JO", x.properties.shapeName) === regionId);
    if (!f) throw new ProviderError("not_found", `Unknown region "${regionId}".`);
    return f;
  }

  async function dataset(regionId: string): Promise<DemoDataset> {
    const cached = datasets.get(regionId);
    if (cached) return cached;
    if (regionId !== DEMO_REGION_ID) {
      throw new ProviderError(
        "not_found",
        `No demonstration analysis exists for "${regionId}". The demo covers Ma’an only; other governorates are added by configuration once the pipelines have run.`,
      );
    }
    const f = await boundaryFeature(regionId);
    const ring = f.geometry.type === "Polygon" ? f.geometry.coordinates[0] : f.geometry.coordinates[0]?.[0];
    if (!ring) throw new ProviderError("invalid_response", "Boundary geometry is empty.");
    const ds = generateDemoDataset({ regionId, ring });
    datasets.set(regionId, ds);
    return ds;
  }

  function statsFor(fc: SuitabilityCollection): { stats: ClassStat[]; total_ha: number; total_dunum: number } {
    const total = fc.features.reduce((a, f) => a + f.properties.area_ha, 0);
    const totalDunum = fc.features.reduce((a, f) => a + f.properties.area_dunum, 0);
    const stats = CLASS_LIST.map<ClassStat>((meta) => {
      const fs = fc.features.filter((f) => f.properties.class_code === meta.code);
      const ha = fs.reduce((a, f) => a + f.properties.area_ha, 0);
      const dn = fs.reduce((a, f) => a + f.properties.area_dunum, 0);
      return {
        code: meta.code,
        label: meta.label,
        polygon_count: fs.length,
        area_ha: roundArea(ha),
        area_dunum: roundArea(dn),
        share: total > 0 ? Math.round((ha / total) * 10000) / 10000 : 0,
      };
    });
    return { stats, total_ha: roundArea(total), total_dunum: roundArea(totalDunum) };
  }

  function metadata(ds: DemoDataset, kind: JobKind): RunMetadata {
    return {
      model_version: DEMO_MODEL_VERSION,
      data_sources: [DEMO_SOURCE_LABEL],
      label_basis: Object.fromEntries(
        CLASS_LIST.map((c) => [String(c.code), kind === "suitability" ? "none: synthetic demonstration" : "synthetic; expert-rule limits; simulated outcomes"]),
      ),
      effective_resolution_m: 30,
      created_at: ds.createdAt,
      demonstration_data: true,
      seed: ds.seed,
    };
  }

  function jobView(j: JobRecord): AnalysisJob {
    const t = now() - j.startedAt;
    const stages = STAGES[j.kind];
    const base = {
      id: j.id,
      kind: j.kind,
      region_id: j.region,
      stages,
      created_at: new Date(j.startedAt).toISOString(),
      demo: true as const,
    };
    if (j.cancelledAt !== null) {
      return { ...base, state: "cancelled", progress: Math.min(0.95, (j.cancelledAt - j.startedAt) / j.durationMs), message: "Cancelled", finished_at: new Date(j.cancelledAt).toISOString() };
    }
    const frac = Math.max(0, Math.min(1, t / j.durationMs));
    if (j.failAt !== null && frac >= j.failAt) {
      return {
        ...base,
        state: "failed",
        progress: j.failAt,
        message: "Failed",
        finished_at: new Date(j.startedAt + j.failAt * j.durationMs).toISOString(),
        error: {
          code: "demo_simulated_failure",
          message: "Simulated failure requested in the demo controls. No real job ran. Start the analysis again to recover.",
          recoverable: true,
        },
      };
    }
    if (frac >= 1) {
      return { ...base, state: "succeeded", progress: 1, message: "Complete", finished_at: new Date(j.startedAt + j.durationMs).toISOString() };
    }
    if (t < 450) return { ...base, state: "queued", progress: 0, message: stages[0] as string };
    const idx = Math.min(stages.length - 1, 1 + Math.floor(frac * (stages.length - 1)));
    return { ...base, state: "running", progress: frac, message: stages[idx] as string };
  }

  function newJob(kind: JobKind, region: string, simulateFailure: boolean | undefined, polygonIds: string[] = []): JobRecord {
    jobSeq += 1;
    const rec: JobRecord = {
      id: `demo-job-${kind}-${jobSeq}`,
      kind,
      region,
      startedAt: now(),
      durationMs: durations[kind],
      failAt: simulateFailure ? 0.55 : null,
      cancelledAt: null,
      polygonIds,
    };
    jobs.set(rec.id, rec);
    return rec;
  }

  const unavailable = (what: string): ProviderError =>
    new ProviderError("not_implemented", `${what} needs the live backend and a real model result (Phase C). It is not available for demonstration data.`);

  const exportsCaps: ProviderCapabilities["exports"] = {
    geojson: { available: true },
    csv: { available: true },
    summary_json: { available: true },
    report_html: { available: true },
    geotiff: { available: false, reason: "GeoTIFF export needs a real model raster (live backend, Phase C)." },
    pdf: { available: false, reason: "PDF export arrives with the live backend. Open the HTML report and use Print > Save as PDF." },
  };

  const provider: DataProvider = {
    id: "demo",
    isDemo: true,
    label: "Demonstration data",
    capabilities: () => ({ exports: exportsCaps, rasterLayers: false }),

    async listCountries(): Promise<Country[]> {
      await delay();
      return [{ code: "JO", name: "Jordan", available: true }];
    },

    async listRegions(countryCode: string): Promise<RegionInfo[]> {
      await delay();
      if (countryCode.toUpperCase() !== "JO") return [];
      const fc = await adm1();
      return fc.features
        .map<RegionInfo>((f) => ({
          id: regionIdFor("JO", f.properties.shapeName),
          country: "JO",
          name: f.properties.shapeName,
          iso: f.properties.shapeISO,
          available: regionIdFor("JO", f.properties.shapeName) === DEMO_REGION_ID,
          bbox: geometryBBox(f.geometry),
          boundary_area_km2: Math.round(geometryAreaM2(f.geometry) / 1e6),
        }))
        .sort((a, b) => Number(b.available) - Number(a.available) || a.name.localeCompare(b.name));
    },

    async getRegionBoundary(regionId: string): Promise<RegionBoundary> {
      await delay();
      const f = await boundaryFeature(regionId);
      return { type: "Feature", geometry: f.geometry, properties: { name: f.properties.shapeName, id: regionId, iso: f.properties.shapeISO } };
    },

    async getSuitabilityRun(regionId: string): Promise<SuitabilityRun | null> {
      await delay();
      if (regionId !== DEMO_REGION_ID) return null;
      const ds = await dataset(regionId);
      const { stats, total_ha, total_dunum } = statsFor(ds.suitability);
      return {
        region_id: regionId,
        created_at: ds.createdAt,
        stats,
        polygon_count: ds.suitability.features.length,
        total_area_ha: total_ha,
        total_area_dunum: total_dunum,
        metadata: metadata(ds, "suitability"),
        demo: true,
      };
    },

    async getSuitabilityPolygons(regionId: string): Promise<SuitabilityCollection> {
      await delay();
      return (await dataset(regionId)).suitability;
    },

    async getRestorationLayer(regionId: string): Promise<RestorationCollection | null> {
      await delay();
      if (regionId !== DEMO_REGION_ID) return null;
      return (await dataset(regionId)).restoration;
    },

    async startSuitabilityJob(regionId, opts) {
      await delay();
      if (regionId !== DEMO_REGION_ID) {
        throw new ProviderError("not_found", `No demonstration analysis exists for "${regionId}". The demo covers Ma’an only.`);
      }
      await dataset(regionId);
      return jobView(newJob("suitability", regionId, opts?.simulateFailure));
    },

    async startRestorationJob(req: RestorationJobRequest, opts) {
      await delay();
      if (req.polygon_ids.length === 0) throw new ProviderError("invalid_response", "Select at least one land unit first.");
      await dataset(req.region_id);
      return jobView(newJob("restoration", req.region_id, opts?.simulateFailure, req.polygon_ids));
    },

    async getJob(jobId: string): Promise<AnalysisJob> {
      const j = jobs.get(jobId);
      if (!j) throw new ProviderError("not_found", `Unknown job "${jobId}". Demo jobs live only for the current page session.`);
      return jobView(j);
    },

    async cancelJob(jobId: string): Promise<AnalysisJob> {
      const j = jobs.get(jobId);
      if (!j) throw new ProviderError("not_found", `Unknown job "${jobId}".`);
      if (jobView(j).state === "running" || jobView(j).state === "queued") j.cancelledAt = now();
      return jobView(j);
    },

    async getRestorationRun(jobId: string): Promise<RestorationRun> {
      await delay();
      const j = jobs.get(jobId);
      if (!j || j.kind !== "restoration") throw new ProviderError("not_found", `Unknown restoration job "${jobId}".`);
      if (jobView(j).state !== "succeeded") throw new ProviderError("unavailable", "The job has not completed.");
      const ds = await dataset(j.region);
      const wanted = new Set(j.polygonIds);
      const features = ds.restoration.features.filter((f) => wanted.has(f.properties.source_polygon_id));
      const byId = new Map(ds.suitability.features.map((f) => [f.properties.id, f] as const));
      const rejected = j.polygonIds
        .filter((id) => !features.some((f) => f.properties.source_polygon_id === id))
        .map((id) => {
          const m1 = byId.get(id);
          if (!m1) return { id, reason: "Unknown land unit id." };
          const c = m1.properties.class_code as SuitabilityClassCode;
          if (c === 5) return { id, reason: CLASS5_NOTE };
          return { id, reason: `Class ${c} (${SUITABILITY_CLASSES[c].label}): restoration analysis applies to class 3 and 4 land.` };
        });
      return {
        job_id: jobId,
        region_id: j.region,
        polygon_ids: j.polygonIds,
        features,
        rejected,
        metadata: metadata(ds, "restoration"),
        created_at: new Date(j.startedAt + j.durationMs).toISOString(),
        demo: true,
      };
    },

    async getLandDetail(polygonId: string): Promise<LandDetail> {
      await delay();
      const m = /^m1-(.+)-(\d+)$/.exec(polygonId);
      if (!m) throw new ProviderError("not_found", `"${polygonId}" is not a land unit id (expected m1-<region>-<n>).`);
      const ds = await dataset(m[1] as string);
      const f = ds.suitability.features.find((x) => x.properties.id === polygonId);
      if (!f) throw new ProviderError("not_found", `Land unit "${polygonId}" does not exist in this run.`);
      const restoration = ds.restoration.features.find((x) => x.properties.source_polygon_id === polygonId) ?? null;
      const c = f.properties.class_code;
      const note =
        restoration || c === 3 || c === 4
          ? undefined
          : c === 5
            ? CLASS5_NOTE
            : `Restoration analysis applies to class 3 and 4 land. This unit is class ${c} (${SUITABILITY_CLASSES[c].label.toLowerCase()}).`;
      return { suitability: f, restoration, restoration_note: note, demo: true };
    },

    async exportSuitability(regionId: string, format: ExportFormat): Promise<ExportArtifact> {
      await delay();
      const ds = await dataset(regionId);
      const o = { demo: true, generatedAt: new Date(now()).toISOString() };
      const stem = `green-nova-DEMO-suitability-${regionId}`;
      if (format === "geojson") return { filename: `${stem}.geojson`, mime: "application/geo+json", content: buildSuitabilityGeoJSON(ds.suitability, regionId, o), demo: true };
      if (format === "csv") return { filename: `${stem}.csv`, mime: "text/csv", content: buildSuitabilityCSV(ds.suitability, regionId, o), demo: true };
      if (format === "summary_json") {
        const run = await provider.getSuitabilityRun(regionId);
        if (!run) throw new ProviderError("not_found", "No run to summarise.");
        return { filename: `${stem}-summary.json`, mime: "application/json", content: buildSuitabilitySummaryJSON(run, o), demo: true };
      }
      throw unavailable(format === "geotiff" ? "GeoTIFF export" : "This export");
    },

    async exportRestoration(jobId: string, format: ExportFormat, opts: RestorationExportOptions): Promise<ExportArtifact> {
      const run = await provider.getRestorationRun(jobId);
      const o = { demo: true, generatedAt: new Date(now()).toISOString() };
      const stem = `green-nova-DEMO-restoration-${run.region_id}`;
      if (format === "geojson") return { filename: `${stem}.geojson`, mime: "application/geo+json", content: buildRestorationGeoJSON(run, opts.constraints, opts.preference, o), demo: true };
      if (format === "csv") return { filename: `${stem}.csv`, mime: "text/csv", content: buildRestorationCSV(run, opts.constraints, opts.preference, o), demo: true };
      if (format === "report_html")
        return { filename: `${stem}-report.html`, mime: "text/html", content: buildRestorationReportHTML(run, opts.constraints, opts.preference, o), demo: true };
      throw unavailable(format === "pdf" ? "PDF export" : "This export");
    },
  };
  return provider;
}

/** Re-exported helpers for tests. */
export { m2ToDunum, m2ToHa };
