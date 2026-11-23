import http from "node:http";
import type { AddressInfo } from "node:net";
import { afterEach, describe, expect, it } from "vitest";
import { callUpstream } from "../bff/upstream";

let server: http.Server | null = null;
afterEach(() => new Promise<void>((r) => (server ? server.close(() => r()) : r())));

const listen = (handler: http.RequestListener) =>
  new Promise<string>((resolve) => {
    server = http.createServer(handler).listen(0, "127.0.0.1", () => resolve(`http://127.0.0.1:${(server!.address() as AddressInfo).port}`));
  });

describe("BFF upstream (non-pooled, retry-once for GET)", () => {
  it("retries an idempotent GET once when the socket is reset", async () => {
    let calls = 0;
    const base = await listen((req, res) => {
      calls++;
      if (calls === 1) return void req.socket.destroy(); // simulates a stale keep-alive socket
      res.writeHead(200, { "content-type": "application/json" }).end('{"ok":true}');
    });
    const r = await callUpstream(base, "GET", "/v1/x", {}, undefined, 5000);
    expect(r.status).toBe(200);
    expect(r.body.toString()).toBe('{"ok":true}');
    expect(calls).toBe(2);
  });

  it("does NOT retry a POST (non-idempotent job creation)", async () => {
    let calls = 0;
    const base = await listen((req) => {
      calls++;
      req.socket.destroy();
    });
    await expect(callUpstream(base, "POST", "/v1/jobs", { "content-type": "application/json" }, "{}", 5000)).rejects.toBeTruthy();
    expect(calls).toBe(1);
  });

  it("sends Connection: close and returns large bodies intact", async () => {
    const big = "x".repeat(6 * 1024 * 1024);
    let conn = "";
    const base = await listen((req, res) => {
      conn = String(req.headers.connection);
      res.writeHead(200, { "content-type": "application/json" }).end(big);
    });
    const r = await callUpstream(base, "GET", "/v1/big", {}, undefined, 10000);
    expect(r.body.length).toBe(big.length);
    expect(conn).toBe("close");
  });
});
