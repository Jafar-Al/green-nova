import type { StyleSpecification } from "maplibre-gl";
import { BASEMAP } from "@/lib/config";

/** Resolve a tile template against the page origin when it is a root-relative path (tunnel- and localhost-safe). */
export function resolveTileUrl(template: string): string {
  if (typeof window === "undefined") return template;
  return template.startsWith("/") ? `${window.location.origin}${template}` : template;
}

export const NO_BASEMAP_COLOR = "#0b0f0d";

export function buildStyle(withBasemap: boolean): StyleSpecification {
  return {
    version: 8,
    sources: withBasemap
      ? {
          sat: {
            type: "raster",
            tiles: [resolveTileUrl(BASEMAP.tileUrl)],
            tileSize: 256,
            minzoom: BASEMAP.minZoom,
            maxzoom: BASEMAP.maxZoom,
            bounds: [...BASEMAP.bounds],
            attribution: BASEMAP.attribution,
          },
        }
      : {},
    layers: [
      { id: "bg", type: "background", paint: { "background-color": NO_BASEMAP_COLOR } },
      ...(withBasemap
        ? [{ id: "sat", type: "raster" as const, source: "sat", paint: { "raster-fade-duration": 150, "raster-saturation": -0.32, "raster-brightness-max": 0.78, "raster-contrast": 0.08 } }]
        : []),
    ],
  };
}

/** 8x8 diagonal hatch (white, semi-transparent). Used for class 5 / simulated outcomes so meaning never relies on colour alone. */
export function makeHatchImage(): { width: number; height: number; data: Uint8Array } {
  const size = 8;
  const data = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const on = (x + y) % size < 2;
      const i = (y * size + x) * 4;
      data[i] = 255;
      data[i + 1] = 255;
      data[i + 2] = 255;
      data[i + 3] = on ? 150 : 0;
    }
  }
  return { width: size, height: size, data };
}
