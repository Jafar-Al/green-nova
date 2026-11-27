import type { NextConfig } from "next";

/**
 * Topology:
 *  - the frontend listens on 0.0.0.0:3000 (explicit in every npm script; terminate TLS in your own reverse proxy / platform);
 *  - FastAPI is internal (127.0.0.1:8000 by default) and is only ever called server-side by the BFF route handlers
 *    (src/app/api/gn). Do not add a blanket /api/* rewrite: the BFF is an explicit allow-list.
 */
// Extra hostnames allowed to use the dev server (HMR websocket, /_next/* dev resources), e.g. a LAN name: ALLOWED_DEV_ORIGINS=dev.example.lan
const EXTRA_DEV_ORIGINS = (process.env.ALLOWED_DEV_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);
const isProd = process.env.NODE_ENV === "production";

/**
 * Content-Security-Policy (production only; the dev server needs eval for HMR).
 * - 'unsafe-inline' scripts: Next injects inline bootstrap/flight scripts; a nonce needs middleware (hardening item).
 * - worker-src blob: and img-src blob:/data: are required by MapLibre GL (tile decode worker, hatch pattern).
 * - If NEXT_PUBLIC_SATELLITE_TILE_URL points at another origin, add that origin to img-src and connect-src.
 */
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  "connect-src 'self'",
  "worker-src 'self' blob:",
  "child-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Data provider is inlined at build time. Production default = "api" (real models through the BFF); set NEXT_PUBLIC_DATA_PROVIDER=demo
  // to build the clearly-labelled demonstration variant.
  env: { NEXT_PUBLIC_DATA_PROVIDER: process.env.NEXT_PUBLIC_DATA_PROVIDER || "api" },
  // Generic path: plain `npm run build` + `npm start` (next start). Set GN_STANDALONE=1 at build time for a self-contained
  // folder (`node server.js` with .next/static and public beside it): see scripts/assemble-standalone.mjs.
  ...(process.env.GN_STANDALONE === "1" ? { output: "standalone" as const } : {}),
  allowedDevOrigins: ["localhost", "127.0.0.1", ...EXTRA_DEV_ORIGINS],
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          ...(isProd ? [{ key: "Content-Security-Policy", value: csp }] : []),
        ],
      },
      {
        // HTML must revalidate so a redeploy is visible immediately, also when a CDN or reverse proxy sits in front.
        source: "/((?!_next/static|_next/image|img|tiles|data|icon.svg).*)",
        headers: [{ key: "Cache-Control", value: "public, max-age=0, must-revalidate" }],
      },
      {
        // Optimised imagery and the self-hosted basemap pyramid are static; cache hard.
        source: "/:dir(img|tiles)/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=2592000, stale-while-revalidate=86400" }],
      },
      {
        source: "/data/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=86400, stale-while-revalidate=86400" }],
      },
    ];
  },
};

export default nextConfig;
