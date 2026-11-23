/**
 * Pure builders that turn contract features into map-ready unit collections (colour, hatch, dash, dim).
 * Keeping this out of components makes the legend, filters and map agree by construction (and unit-testable).
 */
import type { FeatureCollection, Geometry } from "geojson";
import type {
  FeasibilityClass,
  RestorationCollection,
  SuitabilityClassCode,
  SuitabilityCollection,
  SuitabilityFeature,
} from "./contract";
import { FEASIBILITY_META, SUITABILITY_CLASSES } from "./classes";

export interface UnitProps {
  id: string;
  fill: string;
  hatch?: boolean;
  dashed?: boolean;
  dim?: boolean;
}
export type UnitCollection = FeatureCollection<Geometry, UnitProps>;

/** Sequential single-hue ramp for confidence (light = low). Bins are stated in the legend. */
export const CONFIDENCE_BINS: { min: number; label: string; color: string }[] = [
  { min: 0, label: "below 0.50", color: "#efe0a8" },
  { min: 0.5, label: "0.50 to 0.65", color: "#9fcfae" },
  { min: 0.65, label: "0.65 to 0.80", color: "#3f9c92" },
  { min: 0.8, label: "0.80 and above", color: "#17606f" },
];

export function confidenceColor(c: number): string {
  let out = CONFIDENCE_BINS[0]!.color;
  for (const b of CONFIDENCE_BINS) if (c >= b.min) out = b.color;
  return out;
}

export interface SuitabilityFilters {
  classes: Set<SuitabilityClassCode>;
  minConfidence: number;
  minAreaHa: number;
}

export const ALL_CLASSES: SuitabilityClassCode[] = [1, 2, 3, 4, 5];

export const defaultSuitabilityFilters = (): SuitabilityFilters => ({
  classes: new Set(ALL_CLASSES),
  minConfidence: 0,
  minAreaHa: 0,
});

export function passesSuitabilityFilters(f: SuitabilityFeature, flt: SuitabilityFilters): boolean {
  const p = f.properties;
  return flt.classes.has(p.class_code) && p.confidence >= flt.minConfidence && p.area_ha >= flt.minAreaHa;
}

export function suitabilityUnits(fc: SuitabilityCollection, flt: SuitabilityFilters, mode: "class" | "confidence"): UnitCollection {
  return {
    type: "FeatureCollection",
    features: fc.features
      .filter((f) => passesSuitabilityFilters(f, flt))
      .map((f) => ({
        type: "Feature" as const,
        id: f.properties.id,
        geometry: f.geometry,
        properties: {
          id: f.properties.id,
          fill: mode === "class" ? SUITABILITY_CLASSES[f.properties.class_code].color : confidenceColor(f.properties.confidence),
          hatch: f.properties.class_code === 5,
        },
      })),
  };
}

/** Dashboard restoration layer: Model 2 units coloured by feasibility, everything else muted (out of Model 2 scope). */
export function restorationLayerUnits(
  suit: SuitabilityCollection,
  rest: RestorationCollection | null,
  visible: Set<FeasibilityClass>,
): UnitCollection {
  const byM1 = new Map((rest?.features ?? []).map((f) => [f.properties.source_polygon_id, f] as const));
  const features: UnitCollection["features"] = [];
  for (const s of suit.features) {
    const r = byM1.get(s.properties.id);
    if (r) {
      if (!visible.has(r.properties.feasibility.class)) continue;
      features.push({
        type: "Feature",
        id: s.properties.id,
        geometry: s.geometry,
        properties: { id: s.properties.id, fill: FEASIBILITY_META[r.properties.feasibility.class].color },
      });
    } else {
      features.push({
        type: "Feature",
        id: s.properties.id,
        geometry: s.geometry,
        properties: { id: s.properties.id, fill: "#8a948d", dim: true },
      });
    }
  }
  return { type: "FeatureCollection", features };
}

/** Restoration page: selectable class 3/4, out-of-scope muted, class 5 hatched and muted. */
export function selectionUnits(suit: SuitabilityCollection, restorable: Set<SuitabilityClassCode>): UnitCollection {
  return {
    type: "FeatureCollection",
    features: suit.features.map((s) => {
      const c = s.properties.class_code;
      const ok = restorable.has(c);
      return {
        type: "Feature" as const,
        id: s.properties.id,
        geometry: s.geometry,
        properties: { id: s.properties.id, fill: SUITABILITY_CLASSES[c].color, hatch: c === 5, dim: !ok },
      };
    }),
  };
}

/** Post-restoration view: simulated class for analysed units (dashed outline + hatch), unchanged class for the rest. */
export function simulatedUnits(
  suit: SuitabilityCollection,
  analysedIds: Set<string>,
  postClassById: Map<string, SuitabilityClassCode>,
): UnitCollection {
  return {
    type: "FeatureCollection",
    features: suit.features
      .filter((s) => analysedIds.has(s.properties.id))
      .map((s) => {
        const post = postClassById.get(s.properties.id);
        const cls = post ?? s.properties.class_code;
        return {
          type: "Feature" as const,
          id: s.properties.id,
          geometry: s.geometry,
          properties: { id: s.properties.id, fill: SUITABILITY_CLASSES[cls].color, hatch: post !== undefined, dashed: post !== undefined },
        };
      }),
  };
}

export function currentUnits(suit: SuitabilityCollection, ids: Set<string>): UnitCollection {
  return {
    type: "FeatureCollection",
    features: suit.features
      .filter((s) => ids.has(s.properties.id))
      .map((s) => ({
        type: "Feature" as const,
        id: s.properties.id,
        geometry: s.geometry,
        properties: { id: s.properties.id, fill: SUITABILITY_CLASSES[s.properties.class_code].color },
      })),
  };
}
