import http from "node:http";

/**
 * Upstream call from the BFF to the loopback FastAPI service using node:http with a NON-pooled agent (keepAlive: false).
 * uvicorn closes idle keep-alive sockets after 5 s; a pooled client then reuses a dead socket (UND_ERR_SOCKET / ECONNRESET).
 * A fresh loopback connection per request costs microseconds and removes the race. Idempotent GETs are retried once on a socket error.
 */
const agent = new http.Agent({ keepAlive: false, maxSockets: 16 });
const RETRYABLE = new Set(["ECONNRESET", "EPIPE", "ECONNREFUSED", "ETIMEDOUT", "UND_ERR_SOCKET"]);
const MAX_BYTES = 120 * 1024 * 1024;

export interface UpstreamResponse {
  status: number;
  contentType: string;
  contentDisposition: string | null;
  body: Buffer;
}

function once(base: string, method: string, path: string, headers: Record<string, string>, body: string | undefined, timeoutMs: number): Promise<UpstreamResponse> {
  return new Promise((resolve, reject) => {
    const u = new URL(base + path);
    const req = http.request(
      { agent, host: u.hostname, port: u.port, path: u.pathname + u.search, method, headers: { ...headers, connection: "close", ...(body ? { "content-length": String(Buffer.byteLength(body)) } : {}) }, timeout: timeoutMs },
      (res) => {
        const chunks: Buffer[] = [];
        let n = 0;
        res.on("data", (c: Buffer) => {
          n += c.length;
          if (n > MAX_BYTES) {
            req.destroy(Object.assign(new Error("upstream response too large"), { code: "E_TOO_LARGE" }));
            return;
          }
          chunks.push(c);
        });
        res.on("end", () =>
          resolve({
            status: res.statusCode ?? 502,
            contentType: String(res.headers["content-type"] ?? ""),
            contentDisposition: res.headers["content-disposition"] ? String(res.headers["content-disposition"]) : null,
            body: Buffer.concat(chunks),
          }),
        );
        res.on("error", reject);
        res.on("aborted", () => reject(Object.assign(new Error("aborted"), { code: "ECONNRESET" })));
      },
    );
    req.on("timeout", () => req.destroy(Object.assign(new Error("upstream timeout"), { code: "ETIMEDOUT" })));
    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}

export async function callUpstream(base: string, method: "GET" | "POST", path: string, headers: Record<string, string>, body: string | undefined, timeoutMs = 90_000): Promise<UpstreamResponse> {
  try {
    return await once(base, method, path, headers, body, timeoutMs);
  } catch (e) {
    const code = (e as { code?: string }).code ?? "";
    if (method === "GET" && RETRYABLE.has(code)) return once(base, method, path, headers, body, timeoutMs); // one retry, idempotent only
    throw e;
  }
}
