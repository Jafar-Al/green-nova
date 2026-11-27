import type { NextRequest } from "next/server";
import { backendBase, isRejection, resolveBff } from "@/lib/bff/allowlist";
import { callUpstream } from "@/lib/bff/upstream";

/**
 * Server-side BFF to the internal FastAPI service (BACKEND_URL, server-only, loopback only).
 * Not a proxy: every request must match an entry in lib/bff/allowlist.ts, which rebuilds the upstream path from validated parts.
 * The visitor address (CF-Connecting-IP / X-Forwarded-For, as set by the reverse proxy in front of the site) is forwarded in
 * X-GN-Client-IP for rate limiting. Deploy behind a proxy that overwrites these headers; without one they are client-controlled.
 * Upstream calls use non-pooled loopback connections (lib/bff/upstream.ts) so uvicorn's 5 s keep-alive can never hand us a dead socket.
 */
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const json = (status: number, code: string, message: string) =>
  new Response(JSON.stringify({ error: { code, message } }), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

async function handle(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await ctx.params;
  let bodyText: string | null = null;
  if (req.method === "POST") {
    const len = Number(req.headers.get("content-length") ?? "0");
    if (len > 64 * 1024) return json(413, "payload_too_large", "Request body too large.");
    bodyText = await req.text();
  }
  const r = resolveBff(req.method, path, req.nextUrl.search, bodyText);
  if (isRejection(r)) return json(r.status, r.code, r.message);

  let base: string;
  try {
    base = backendBase(process.env.BACKEND_URL);
  } catch {
    return json(500, "misconfigured", "The analysis service is not configured correctly.");
  }
  const ip = (req.headers.get("cf-connecting-ip") ?? req.headers.get("x-forwarded-for")?.split(",")[0] ?? "unknown").trim().slice(0, 64);
  try {
    const up = await callUpstream(base, r.method, r.path, { "content-type": "application/json", "x-gn-client-ip": ip, accept: r.accept === "tiff" ? "image/tiff" : "application/json" }, r.body);
    const ct = up.contentType;
    const okType = r.accept === "tiff" ? ct.startsWith("image/tiff") || ct.startsWith("application/json") : ct.startsWith("application/json");
    if (!okType) return json(502, "bad_upstream", "The analysis service returned an unexpected response.");
    const headers = new Headers({ "content-type": ct, "cache-control": "no-store", "x-content-type-options": "nosniff" });
    if (up.contentDisposition && /^attachment; filename="[A-Za-z0-9._-]+"$/.test(up.contentDisposition)) headers.set("content-disposition", up.contentDisposition);
    return new Response(new Uint8Array(up.body), { status: up.status, headers });
  } catch {
    return json(502, "backend_unreachable", "The analysis service is not reachable right now.");
  }
}

export const GET = handle;
export const POST = handle;
