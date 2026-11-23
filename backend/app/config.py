"""Runtime configuration (environment driven, no secrets).

Layout when deployed:  <ROOT> = <app root>  containing backend/, models/, regions/  (uvicorn cwd = ROOT).
Data root GREEN_NOVA_DATA (<data root>) holds raw data and the runtime dir (jobs DB, results, logs).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _path(name: str, default: Path) -> Path:
    v = os.environ.get(name)
    return Path(v) if v else default


@dataclass(frozen=True)
class Settings:
    root: Path = field(default_factory=lambda: _path("GREEN_NOVA_APP_ROOT", Path(__file__).resolve().parents[2]))
    data_root: Path = field(default_factory=lambda: _path("GREEN_NOVA_DATA", Path.home() / "GreenNovaData"))
    runtime: Path = field(default_factory=lambda: _path("GREEN_NOVA_RUNTIME", _path("GREEN_NOVA_DATA", Path.home() / "GreenNovaData") / "runtime"))

    # request limits
    max_body_bytes: int = field(default_factory=lambda: _int("GN_MAX_BODY_BYTES", 256 * 1024))
    max_polygon_ids: int = field(default_factory=lambda: _int("GN_MAX_POLYGON_IDS", 500))
    max_geometry_vertices: int = field(default_factory=lambda: _int("GN_MAX_GEOMETRY_VERTICES", 5000))
    max_geometry_area_km2: float = field(default_factory=lambda: float(os.environ.get("GN_MAX_GEOMETRY_AREA_KM2", "40000")))

    # rate limiting (per client ip)
    rate_per_minute: int = field(default_factory=lambda: _int("GN_RATE_PER_MINUTE", 240))
    job_rate_per_hour: int = field(default_factory=lambda: _int("GN_JOB_RATE_PER_HOUR", 30))
    max_active_jobs_per_ip: int = field(default_factory=lambda: _int("GN_MAX_ACTIVE_JOBS_PER_IP", 2))

    # job queue: at most ONE heavy job runs at a time; the queue is bounded
    max_queue: int = field(default_factory=lambda: _int("GN_MAX_QUEUE", 6))
    job_timeout_s: int = field(default_factory=lambda: _int("GN_JOB_TIMEOUT_S", 1800))
    # memory guard: a job only starts when at least this much physical RAM is available
    min_free_mb: int = field(default_factory=lambda: _int("GN_MIN_FREE_MB", 2500))
    memory_wait_s: int = field(default_factory=lambda: _int("GN_MEMORY_WAIT_S", 120))

    # only requests from loopback may set X-GN-Client-IP (the Next BFF does)
    trusted_proxy_hosts: tuple[str, ...] = ("127.0.0.1", "::1", "localhost", "testclient")

    @property
    def models_dir(self) -> Path:
        return self.root / "models"

    @property
    def regions_file(self) -> Path:
        return self.root / "regions" / "jordan_adm1.geojson"

    @property
    def db_path(self) -> Path:
        return self.runtime / "jobs.sqlite"

    @property
    def jobs_dir(self) -> Path:
        return self.runtime / "jobs"

    @property
    def logs_dir(self) -> Path:
        return self.runtime / "logs"


def get_settings() -> Settings:
    return Settings()
