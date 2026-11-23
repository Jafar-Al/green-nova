import type { NextConfig } from "next";

/**
 * Fixed topology (owner instruction, docs/ORCHESTRATION.md "FIXED ports, domain and tunnel"):
 *  - the frontend always listens on 0.0.0.0:3000 (explicit in every npm script);
 *  - public host greennova.dosteam.org reaches it through the owner's Cloudflare Tunnel (HTTPS terminates at Cloudflare);
 *  - FastAPI (Phase C) is internal at 127.0.0.1:8000 and is only ever called server-side (BFF route handlers).
 * No rewrites/proxies exist in Phase A. Do not add a blanket /api/* rewrite.
 */
const PUBLIC_HOST = (process.env.GREEN_NOVA_DOMAIN || "greennova.dosteam.org").replace(/^https?:\/\//, "").replace(/\/.*$/, "");
const isProd = process.env.NODE_ENV === "production";

/**
 * Content-Security-Policy (production only; the dev server needs eval for HMR).
 * - 'unsafe-inline' scripts: Next injects inline bootstrap/flight scripts; a nonce needs middleware (Phase C hardening item).
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
  // Lets the dev server (HMR websocket, /_next/* dev resources) work when browsed through the tunnel host.
  allowedDevOrigins: [PUBLIC_HOST, "localhost", "127.0.0.1"],
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
        // HTML must revalidate so a redeploy is visible immediately, also when a CDN sits in front of the tunnel.
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
