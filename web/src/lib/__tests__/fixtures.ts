import fs from "node:fs";
import path from "node:path";
import type { FeatureCollection, MultiPolygon, Polygon, Position } from "geojson";
import { generateDemoDataset, type DemoDataset } from "../demo/generate";

type Adm = FeatureCollection<Polygon | MultiPolygon, { shapeName: string; shapeISO?: string }>;

export function loadAdm1(): Adm {
  const p = path.resolve(__dirname, "../../../public/data/jordan_adm1.geojson");
  return JSON.parse(fs.readFileSync(p, "utf-8")) as Adm;
}

export function maanRing(): Position[] {
  const f = loadAdm1().features.find((x) => x.properties.shapeName === "Ma'an");
  if (!f) throw new Error("Ma'an not found in ADM1 file");
  return f.geometry.type === "Polygon" ? (f.geometry.coordinates[0] as Position[]) : (f.geometry.coordinates[0]?.[0] as Position[]);
}

let cached: DemoDataset | null = null;
export function demoDataset(): DemoDataset {
  cached ??= generateDemoDataset({ regionId: "jo-maan", ring: maanRing(), now: "2026-01-01T00:00:00.000Z" });
  return cached;
}
