import type { Geometry, Position } from "geojson";
import { m2ToDunum, m2ToHa } from "./units";

/* WGS84 */
const A = 6378137.0;
const E2 = 0.00669437999014;
const E = Math.sqrt(E2);

/** Authalic q(phi) (Snyder 3-12). */
function q(phi: number): number {
  const s = Math.sin(phi);
  return (1 - E2) * (s / (1 - E2 * s * s) - (1 / (2 * E)) * Math.log((1 - E * s) / (1 + E * s)));
}
const QP = q(Math.PI / 2);
const RQ = A * Math.sqrt(QP / 2);

/**
 * Area of a lon/lat ring in square metres, computed in the exact authalic (equal-area) cylindrical projection of the
 * WGS84 ellipsoid (equivalent to EPSG:6933 up to a constant scale that cancels). Never computes area in degrees.
 * Holes: pass them as separate rings and subtract.
 */
export function ringAreaM2(ring: Position[]): number {
  if (ring.length < 4) return 0;
  const pts = ring.map(([lon, lat]) => {
    const phi = ((lat ?? 0) * Math.PI) / 180;
    const beta = Math.asin(Math.max(-1, Math.min(1, q(phi) / QP)));
    return [RQ * (((lon ?? 0) * Math.PI) / 180), RQ * Math.sin(beta)] as const;
  });
  let s = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const p = pts[i]!;
    const n = pts[i + 1]!;
    s += p[0] * n[1] - n[0] * p[1];
  }
  return Math.abs(s) / 2;
}

export function polygonAreaM2(rings: Position[][]): number {
  const [outer, ...holes] = rings;
  if (!outer) return 0;
  return ringAreaM2(outer) - holes.reduce((a, h) => a + ringAreaM2(h), 0);
}

export function geometryAreaM2(g: Geometry): number {
  if (g.type === "Polygon") return polygonAreaM2(g.coordinates);
  if (g.type === "MultiPolygon") return g.coordinates.reduce((a, p) => a + polygonAreaM2(p), 0);
  return 0;
}

export function geometryAreaHaDunum(g: Geometry): { area_ha: number; area_dunum: number } {
  const m2 = geometryAreaM2(g);
  return { area_ha: m2ToHa(m2), area_dunum: m2ToDunum(m2) };
}

export type BBox = [number, number, number, number]; // west, south, east, north

export function ringBBox(ring: Position[]): BBox {
  let w = Infinity;
  let s = Infinity;
  let e = -Infinity;
  let n = -Infinity;
  for (const [x, y] of ring) {
    if (x! < w) w = x!;
    if (x! > e) e = x!;
    if (y! < s) s = y!;
    if (y! > n) n = y!;
  }
  return [w, s, e, n];
}

export function geometryBBox(g: Geometry): BBox {
  const rings: Position[][] =
    g.type === "Polygon" ? g.coordinates : g.type === "MultiPolygon" ? g.coordinates.flat() : [];
  const boxes = rings.map(ringBBox);
  if (boxes.length === 0) return [0, 0, 0, 0];
  return boxes.reduce<BBox>(
    (a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])],
    [Infinity, Infinity, -Infinity, -Infinity],
  );
}

export function unionBBox(boxes: BBox[]): BBox | null {
  if (boxes.length === 0) return null;
  return boxes.reduce<BBox>(
    (a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])],
    [Infinity, Infinity, -Infinity, -Infinity],
  );
}

/** Ray casting; ring must be closed or open, lon/lat. */
export function pointInRing(lon: number, lat: number, ring: Position[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]!;
    const [xj, yj] = ring[j]!;
    if (yi! > lat !== yj! > lat && lon < ((xj! - xi!) * (lat - yi!)) / (yj! - yi!) + xi!) inside = !inside;
  }
  return inside;
}

/** Polygon-with-holes containment. */
export function pointInPolygon(lon: number, lat: number, rings: Position[][]): boolean {
  const [outer, ...holes] = rings;
  if (!outer || !pointInRing(lon, lat, outer)) return false;
  return !holes.some((h) => pointInRing(lon, lat, h));
}

/** Local km offsets <-> lon/lat (adequate at the 10-100 km scale used by the demo generator only). */
export const KM_PER_DEG_LAT = 110.574;
export const kmPerDegLon = (lat: number): number => 111.32 * Math.cos((lat * Math.PI) / 180);

export function round6(v: number): number {
  return Math.round(v * 1e6) / 1e6;
}

/** Area-weighted centroid of the outer ring (planar in lon/lat; fine for polygons far smaller than a degree). */
export function ringCentroid(ring: Position[]): [number, number] {
  let a = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const [x0, y0] = ring[i]!;
    const [x1, y1] = ring[i + 1]!;
    const f = x0! * y1! - x1! * y0!;
    a += f;
    cx += (x0! + x1!) * f;
    cy += (y0! + y1!) * f;
  }
  if (a === 0) {
    const [x, y] = ring[0] ?? [0, 0];
    return [x!, y!];
  }
  return [cx / (3 * a), cy / (3 * a)];
}

/* ------------------------------------------------------------------ formatting */

function dms(v: number, pos: string, neg: string): string {
  const hemi = v >= 0 ? pos : neg;
  const abs = Math.abs(v);
  const d = Math.floor(abs);
  const mFull = (abs - d) * 60;
  const m = Math.floor(mFull);
  const s = (mFull - m) * 60;
  return `${d}°${String(m).padStart(2, "0")}′${s.toFixed(1).padStart(4, "0")}″${hemi}`;
}

/** "30.123456° N, 36.123456° E" */
export function formatLatLon(lon: number, lat: number, digits = 5): string {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(digits)}° ${ns}, ${Math.abs(lon).toFixed(digits)}° ${ew}`;
}

export function formatLatLonDms(lon: number, lat: number): string {
  return `${dms(lat, "N", "S")} ${dms(lon, "E", "W")}`;
}
