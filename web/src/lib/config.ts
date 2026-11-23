/**
 * Public configuration. Every NEXT_PUBLIC_* value must be referenced literally so Next inlines it into the client bundle.
 * No absolute localhost URLs live here: the site is reached on localhost:3000 and as https://greennova.dosteam.org
 * (Cloudflare Tunnel), so relative URLs are resolved against the page origin at runtime.
 */

export const SITE_NAME = "GREEN NOVA AI";
export const SITE_TAGLINE = "Discover. Restore. Grow.";

const rawDomain = (process.env.GREEN_NOVA_DOMAIN || "greennova.dosteam.org").replace(/^https?:\/\//, "").replace(/\/.*$/, "");
/** Canonical origin for metadata, sitemap and robots (server-side use). */
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || `https://${rawDomain}`).replace(/\/$/, "");

/** true unless the live provider is selected. Drives the persistent DEMONSTRATION DATA marker. */
export const IS_DEMO_MODE = process.env.NEXT_PUBLIC_DATA_PROVIDER !== "api";

const num = (v: string | undefined, d: number): number => {
  const n = Number(v);
  return v && Number.isFinite(n) ? n : d;
};

const rawBounds = process.env.NEXT_PUBLIC_SATELLITE_BOUNDS;
const parsedBounds = rawBounds ? rawBounds.split(",").map(Number) : [];

export const BASEMAP = {
  /** XYZ template; a leading "/" is resolved against window.location.origin at runtime. */
  tileUrl: process.env.NEXT_PUBLIC_SATELLITE_TILE_URL || "/tiles/s2/{z}/{x}/{y}.jpg",
  attribution: process.env.NEXT_PUBLIC_SATELLITE_ATTRIBUTION || "Contains modified Copernicus Sentinel data",
  minZoom: num(process.env.NEXT_PUBLIC_SATELLITE_MIN_ZOOM, 5),
  maxZoom: num(process.env.NEXT_PUBLIC_SATELLITE_MAX_ZOOM, 11),
  /** west, south, east, north in which tiles exist. Default = buffered Ma'an extent of the self-hosted pyramid. */
  bounds: (parsedBounds.length === 4 && parsedBounds.every(Number.isFinite) ? parsedBounds : [35.2, 29.1, 38.1, 31.35]) as [number, number, number, number],
} as const;

export const BOUNDARY_ATTRIBUTION = "Boundaries: geoBoundaries gbOpen (Jordan ADM1), CC BY 2.5";
