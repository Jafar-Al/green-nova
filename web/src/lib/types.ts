/**
 * App-level types that are NOT part of docs/CONTRACT.md: view models, provider interface, jobs, exports.
 * Contract types live in `contract.ts` and are imported, never redefined here.
 */
import type { Feature, MultiPolygon, Polygon } from "geojson";
import type {
  ClassSummary,
  FeasibilityClass,
  RegionId,
  RestorationCollection,
  RestorationFeature,
  RunMetadata,
  SuitabilityClassCode,
  SuitabilityCollection,
  SuitabilityFeature,
} from "./contract";
import type { BBox } from "./geo";

/* ------------------------------------------------------------------ regions */

export interface Country {
  /** ISO 3166-1 alpha-2 */
  code: string;
  name: string;
  /** false = listed for context but no analysis exists. */
  available: boolean;
}

export interface RegionInfo {
  id: RegionId;
  country: string;
  name: string;
  /** ISO 3166-2 (e.g. JO-MN) when known. */
  iso?: string;
  /** true when this provider can serve an analysis for the region. */
  available: boolean;
  bbox: BBox;
  /** Area computed from the boundary geometry (equal-area), km2. Not an official figure. */
  boundary_area_km2: number;
}

export type RegionBoundary = Feature<Polygon | MultiPolygon, { name: string; id: RegionId; iso?: string }>;

/* ------------------------------------------------------------------ jobs */

export type JobKind = "suitability" | "restoration";
export type JobState = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface AnalysisJob {
  id: string;
  kind: JobKind;
  region_id: RegionId;
  state: JobState;
  /** 0..1 */
  progress: number;
  /** Current stage, human readable. */
  message: string;
  stages: string[];
  created_at: string;
  finished_at?: string;
  error?: { code: string; message: string; recoverable: boolean };
  /** true => the job replays precomputed synthetic results; no model executed. */
  demo: boolean;
}

/* ------------------------------------------------------------------ suitability view models */

export interface ClassStat extends ClassSummary {
  code: SuitabilityClassCode;
  label: string;
}

export interface SuitabilityRun {
  region_id: RegionId;
  created_at: string;
  stats: ClassStat[];
  polygon_count: number;
  total_area_ha: number;
  total_area_dunum: number;
  metadata: RunMetadata;
  demo: boolean;
}

/* ------------------------------------------------------------------ restoration */

export interface RestorationConstraints {
  /** Upper bound on the scenario's central water requirement (m3/ha/yr); null = unconstrained. */
  max_water_m3_ha_yr: number | null;
  /** Water sources the user can actually use; a scenario needs at least one of its sources in this list. */
  allowed_water_sources: string[];
  /** Upper bound on the high end of time-to-effect (years). */
  max_years: number;
  /** Polygons below this feasibility class are excluded. */
  min_feasibility: FeasibilityClass;
  /** Exclude polygons with a severe (>= 0.6) irreversible limiting factor. */
  exclude_irreversible: boolean;
}

export interface RestorationExportOptions {
  constraints: RestorationConstraints;
  /** "best" or a scenario tier key (see restoration.scenarioKey). */
  preference: string;
}

export interface RestorationJobRequest {
  region_id: RegionId;
  /** Model 1 polygon ids (class 3 or 4). */
  polygon_ids: string[];
}

export interface RestorationRun {
  job_id: string;
  region_id: RegionId;
  polygon_ids: string[];
  features: RestorationFeature[];
  /** Ids requested but not analysable (e.g. class 5), with the reason. Never silently dropped. */
  rejected: { id: string; reason: string }[];
  metadata: RunMetadata;
  created_at: string;
  demo: boolean;
}

/* ------------------------------------------------------------------ land details */

export interface LandDetail {
  suitability: SuitabilityFeature;
  /** null when Model 2 does not apply (class 1, 2 or 5) or no restoration result exists. */
  restoration: RestorationFeature | null;
  /** Why `restoration` is null, when it is. */
  restoration_note?: string;
  demo: boolean;
}

/* ------------------------------------------------------------------ export */

export type ExportFormat = "geojson" | "csv" | "summary_json" | "report_html" | "geotiff" | "pdf";

export interface ExportArtifact {
  filename: string;
  mime: string;
  /** Inline content (demo provider). */
  content?: string;
  /** Download URL (api provider; Phase C). */
  url?: string;
  /** true => file carries the DEMONSTRATION DATA marker. */
  demo: boolean;
}

export interface ProviderCapabilities {
  exports: Record<ExportFormat, { available: boolean; reason?: string }>;
  /** true when COG / tiles for model rasters exist. */
  rasterLayers: boolean;
}

/* ------------------------------------------------------------------ provider */

export type ProviderErrorCode = "not_found" | "unavailable" | "not_implemented" | "invalid_response" | "offline";

export class ProviderError extends Error {
  readonly code: ProviderErrorCode;
  constructor(code: ProviderErrorCode, message: string) {
    super(message);
    this.name = "ProviderError";
    this.code = code;
  }
}

/**
 * The single data-access interface. `demoProvider` (labelled synthetic) and `apiProvider` (Phase C) both implement it.
 * Views only ever talk to this interface, so swapping providers needs no UI change.
 */
export interface DataProvider {
  readonly id: "demo" | "api";
  readonly isDemo: boolean;
  /** Human label, shown in the demonstration marker. */
  readonly label: string;

  capabilities(): ProviderCapabilities;
  listCountries(): Promise<Country[]>;
  listRegions(countryCode: string): Promise<RegionInfo[]>;
  getRegionBoundary(regionId: RegionId): Promise<RegionBoundary>;

  /** Latest completed Model 1 run for the region; null when none exists (empty state). */
  getSuitabilityRun(regionId: RegionId): Promise<SuitabilityRun | null>;
  getSuitabilityPolygons(regionId: RegionId): Promise<SuitabilityCollection>;

  /** Region-wide precomputed Model 2 layer (class 3/4 units); null when none exists. */
  getRestorationLayer(regionId: RegionId): Promise<RestorationCollection | null>;

  startSuitabilityJob(regionId: RegionId, opts?: { simulateFailure?: boolean }): Promise<AnalysisJob>;
  startRestorationJob(req: RestorationJobRequest, opts?: { simulateFailure?: boolean }): Promise<AnalysisJob>;
  getJob(jobId: string): Promise<AnalysisJob>;
  cancelJob(jobId: string): Promise<AnalysisJob>;
  getRestorationRun(jobId: string): Promise<RestorationRun>;

  getLandDetail(polygonId: string): Promise<LandDetail>;

  exportSuitability(regionId: RegionId, format: ExportFormat): Promise<ExportArtifact>;
  exportRestoration(jobId: string, format: ExportFormat, opts: RestorationExportOptions): Promise<ExportArtifact>;
}
