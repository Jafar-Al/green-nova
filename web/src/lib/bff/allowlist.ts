/**
 * Allowlist for the server-side BFF (web/src/app/api/gn/[...path]/route.ts).
 * Browsers only ever call same-origin /api/gn/*; each (method, path shape, query, body) below maps to ONE backend path.
 * Anything else is rejected here, before any request leaves the Next.js server. There is NO blanket proxy.
 * Pure functions: unit-tested (src/lib/__tests__/bff.test.ts).
 */
const REGION = /^[a-z]{2}-[a-z0-9]{2,30}$/;
const POLYGON = /^m1-[a-z]{2}-[a-z0-9]{2,30}-\d{1,7}$/;
const JOB = /^[0-9a-f]{32}$/;
const MAX_BODY = 64 * 1024;
const MAX_IDS = 500;

export interface Resolved {
  method: "GET" | "POST";
  /** Backend path + query, e.g. `/v1/regions`. Always starts with /v1/. */
  path: string;
  body?: string;
  /** Allowed upstream response content types. */
  accept: "json" | "tiff";
}
export type Rejection = { status: number; code: string; message: string };

const no = (status: number, code: string, message: string): Rejection => ({ status, code, message });

export function resolveBff(method: string, segments: string[], search: string, bodyText: string | null): Resolved | Rejection {
  const m = method.toUpperCase();
  if (m !== "GET" && m !== "POST") return no(405, "method_not_allowed", "Method not allowed.");
  if (segments.some((s) => s.length === 0 || s.length > 80 || /[^A-Za-z0-9_.-]/.test(s) || s === "." || s === "..")) return no(400, "bad_request", "Invalid path.");
  const [a, b, c, d] = segments;
  const n = segments.length;
  const params = new URLSearchParams(search);

  if (m === "GET") {
    if (n === 1 && a === "regions") return { method: "GET", path: "/v1/regions", accept: "json" };
    if (a === "regions" && b && REGION.test(b)) {
      if (n === 3 && c === "boundary") return { method: "GET", path: `/v1/regions/${b}/boundary`, accept: "json" };
      if (n === 4 && c === "suitability" && d === "run") return { method: "GET", path: `/v1/regions/${b}/suitability/run`, accept: "json" };
      if (n === 4 && c === "suitability" && d === "polygons") return { method: "GET", path: `/v1/regions/${b}/suitability/polygons`, accept: "json" };
      if (n === 4 && c === "restoration" && d === "layer") return { method: "GET", path: `/v1/regions/${b}/restoration/layer`, accept: "json" };
    }
    if (a === "jobs" && b && JOB.test(b)) {
      if (n === 2) return { method: "GET", path: `/v1/jobs/${b}`, accept: "json" };
      if (n === 3 && c === "result") return { method: "GET", path: `/v1/jobs/${b}/result`, accept: "json" };
    }
    if (a === "land" && b && POLYGON.test(b)) {
      if (n === 2) return { method: "GET", path: `/v1/land/${b}`, accept: "json" };
      if (n === 3 && c === "geotiff") {
        const layer = params.get("layer") ?? "suitability";
        if (!["suitability", "feasibility", "post_restoration"].includes(layer)) return no(400, "bad_request", "Unknown raster layer.");
        return { method: "GET", path: `/v1/land/${b}/geotiff?layer=${layer}`, accept: "tiff" };
      }
    }
    return no(404, "not_found", "Not found.");
  }

  // POST
  if (n === 1 && a === "jobs") {
    if (bodyText === null || bodyText.length > MAX_BODY) return no(413, "payload_too_large", "Request body too large.");
    let body: unknown;
    try {
      body = JSON.parse(bodyText);
    } catch {
      return no(400, "invalid_json", "Request body must be JSON.");
    }
    if (typeof body !== "object" || body === null || Array.isArray(body)) return no(400, "invalid_json", "Request body must be a JSON object.");
    const o = body as Record<string, unknown>;
    if (Object.keys(o).some((k) => !["kind", "region_id", "polygon_ids"].includes(k))) return no(400, "invalid_fields", "Unknown fields in request.");
    if (o.kind !== "suitability" && o.kind !== "restoration") return no(400, "invalid_kind", "kind must be 'suitability' or 'restoration'.");
    if (typeof o.region_id !== "string" || !REGION.test(o.region_id)) return no(400, "invalid_region", "Invalid region id.");
    const clean: Record<string, unknown> = { kind: o.kind, region_id: o.region_id };
    if (o.kind === "restoration") {
      const ids = o.polygon_ids;
      if (!Array.isArray(ids) || ids.length === 0 || ids.length > MAX_IDS || !ids.every((i) => typeof i === "string" && POLYGON.test(i))) {
        return no(400, "invalid_polygon_ids", `polygon_ids must be 1 to ${MAX_IDS} valid land-unit ids.`);
      }
      clean.polygon_ids = ids;
    }
    return { method: "POST", path: "/v1/jobs", body: JSON.stringify(clean), accept: "json" };
  }
  if (n === 3 && a === "jobs" && b && JOB.test(b) && c === "cancel") return { method: "POST", path: `/v1/jobs/${b}/cancel`, body: "{}", accept: "json" };
  return no(404, "not_found", "Not found.");
}

export const isRejection = (r: Resolved | Rejection): r is Rejection => "status" in r;

/** Backend base URL (server-only env). Must be loopback: the BFF never talks to anything else. */
export function backendBase(env: string | undefined): string {
  const raw = (env && env.trim()) || "http://127.0.0.1:8000";
  const u = new URL(raw);
  if (!["127.0.0.1", "localhost", "[::1]", "::1"].includes(u.hostname)) throw new Error("BACKEND_URL must be a loopback address");
  return `${u.protocol}//${u.host}`;
}
