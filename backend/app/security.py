"""Security middleware: headers, body-size limit, per-IP rate limit, client-ip resolution.

The API listens on 127.0.0.1 only and is called by the Next.js BFF. The BFF forwards the real visitor address in X-GN-Client-IP
(taken from CF-Connecting-IP / X-Forwarded-For set by the reverse proxy); that header is honoured ONLY when the TCP peer is loopback.
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import Settings
from .errors import PayloadTooLarge, TooManyRequests

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def client_ip(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    if peer in settings.trusted_proxy_hosts:
        fwd = request.headers.get("x-gn-client-ip", "").strip()
        if fwd and len(fwd) <= 64 and all(c in "0123456789abcdefABCDEF:.%" for c in fwd):
            return fwd
    return peer


def ip_hash(ip: str) -> str:
    """Logs carry a short salted-free hash, never the raw address."""
    return hashlib.sha256(ip.encode()).hexdigest()[:12]


class SlidingWindow:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_s: float, now: float | None = None) -> bool:
        t = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= t - window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(t)
            if len(self._hits) > 20000:  # bound memory under address churn
                for k in [k for k, v in self._hits.items() if not v][:5000]:
                    self._hits.pop(k, None)
            return True


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings, limiter: SlidingWindow):
        super().__init__(app)
        self.settings = settings
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next):
        s = self.settings
        ip = client_ip(request, s)
        request.state.client_ip = ip
        path = request.url.path
        try:
            if path not in ("/health", "/ready"):
                if not self.limiter.allow(f"req:{ip}", s.rate_per_minute, 60):
                    raise TooManyRequests("Too many requests. Please slow down.")
            cl = request.headers.get("content-length")
            if cl is not None:
                try:
                    if int(cl) > s.max_body_bytes:
                        raise PayloadTooLarge("Request body too large.")
                except ValueError:
                    return self._finish(JSONResponse({"error": {"code": "bad_request", "message": "Invalid Content-Length."}}, status_code=400))
            elif request.method in ("POST", "PUT", "PATCH"):
                body = await request.body()
                if len(body) > s.max_body_bytes:
                    raise PayloadTooLarge("Request body too large.")
            resp = await call_next(request)
        except (TooManyRequests, PayloadTooLarge) as e:
            resp = JSONResponse(e.body(), status_code=e.status)
            if isinstance(e, TooManyRequests):
                resp.headers["Retry-After"] = "30"
        return self._finish(resp)

    @staticmethod
    def _finish(resp):
        for k, v in SECURITY_HEADERS.items():
            resp.headers[k] = v
        if "server" in resp.headers:
            del resp.headers["server"]
        return resp
