"""GREEN NOVA AI backend. Run (one worker, loopback only):

    python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-server-header   (cwd = app root)

No /docs, /redoc or /openapi.json. No CORS (same-origin only: browsers never reach this process; the Next.js BFF does).
"""
from __future__ import annotations

import logging
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .adapters.restoration import RestorationAdapter
from .adapters.suitability import SuitabilityAdapter
from .api import router
from .config import Settings, get_settings
from .db import JobDB
from .errors import ApiError
from .jobs import JobManager
from .logging_setup import log, setup_logging
from .regions import load_regions
from .security import SecurityMiddleware, SlidingWindow, ip_hash


@dataclass
class State:
    settings: Settings
    db: JobDB
    suit: SuitabilityAdapter
    rest: RestorationAdapter
    jobs: JobManager
    started: float


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    if str(s.root) not in sys.path:
        sys.path.insert(0, str(s.root))  # so `models.*` imports work whatever the cwd
    logger = setup_logging(s.logs_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        s.runtime.mkdir(parents=True, exist_ok=True)
        db = JobDB(s.db_path)
        suit, rest = SuitabilityAdapter(s), RestorationAdapter(s)
        jobs = JobManager(s, db, suit, rest, logger)
        jobs.start()
        app.state.gn = State(s, db, suit, rest, jobs, time.time())
        log(logger, logging.INFO, "backend started", root_ok=s.root.exists())
        yield
        jobs.stop()
        db.close()

    app = FastAPI(title="green-nova-backend", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(SecurityMiddleware, settings=s, limiter=SlidingWindow())
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.include_router(router)

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse(exc.body(), status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "error")
        return JSONResponse({"error": {"code": code, "message": "Not found." if exc.status_code == 404 else "Request not allowed."}}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("unhandled error on %s", request.url.path)
        return JSONResponse({"error": {"code": "internal_error", "message": "Something went wrong on the server."}}, status_code=500)

    @app.middleware("http")
    async def _access_log(request: Request, call_next):
        t = time.time()
        resp = await call_next(request)
        if request.url.path not in ("/health",):
            log(logger, logging.INFO, "request", method=request.method, path=request.url.path, status=resp.status_code, ms=round((time.time() - t) * 1000, 1), ip=ip_hash(getattr(request.state, "client_ip", "unknown")))
        return resp

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready(request: Request):
        st: State = request.app.state.gn
        problems = []
        try:
            st.db.ping()
        except Exception:  # noqa: BLE001
            problems.append("job store")
        regs = load_regions(st.settings.regions_file)
        if not regs:
            problems.append("region boundaries")
        models = {}
        for r in regs:
            models[r] = {"suitability": st.suit.status(r), "restoration": st.rest.status(r)}
        # 503 only when core infrastructure is broken; a missing model is reported (degraded) and served as 503 per endpoint
        degraded = any(not m[k]["available"] for m in models.values() for k in m)
        body = {"status": "unavailable" if problems else ("degraded" if degraded else "ready"), "problems": problems, "models": models, "queue": {"depth": st.jobs.queue_depth(), "running": bool(st.jobs.current)}}
        return JSONResponse(body, status_code=503 if problems else 200)

    return app


app = create_app()
