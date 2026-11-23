"""SQLite job store. Completed jobs and their result files survive restarts; unfinished jobs from a previous process are marked failed."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, model TEXT NOT NULL, model_version TEXT, region_id TEXT NOT NULL,
  params_json TEXT NOT NULL, cache_key TEXT NOT NULL, state TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
  message TEXT NOT NULL DEFAULT '', error_code TEXT, error_message TEXT, client TEXT,
  created_at REAL NOT NULL, started_at REAL, finished_at REAL
);
CREATE INDEX IF NOT EXISTS idx_jobs_cache ON jobs(cache_key, state);
CREATE INDEX IF NOT EXISTS idx_jobs_client ON jobs(client, state);
"""


class JobDB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._c = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._c.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._c.execute("PRAGMA journal_mode=WAL")
            self._c.executescript(SCHEMA)

    def ping(self) -> bool:
        with self._lock:
            return self._c.execute("SELECT 1").fetchone()[0] == 1

    def close(self) -> None:
        with self._lock:
            self._c.close()

    def interrupt_unfinished(self) -> int:
        with self._lock:
            cur = self._c.execute(
                "UPDATE jobs SET state='failed', error_code='interrupted', error_message='The server restarted while this job was running. Start it again.', finished_at=? WHERE state IN ('queued','running')",
                (time.time(),),
            )
            return cur.rowcount

    def insert(self, row: dict[str, Any]) -> None:
        cols = ",".join(row)
        qs = ",".join("?" for _ in row)
        with self._lock:
            self._c.execute(f"INSERT INTO jobs ({cols}) VALUES ({qs})", tuple(row.values()))

    def update(self, job_id: str, **fields: Any) -> None:
        sets = ",".join(f"{k}=?" for k in fields)
        with self._lock:
            self._c.execute(f"UPDATE jobs SET {sets} WHERE id=?", (*fields.values(), job_id))

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            r = self._c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(r) if r else None

    def find_cached(self, cache_key: str) -> dict | None:
        with self._lock:
            r = self._c.execute("SELECT * FROM jobs WHERE cache_key=? AND state='succeeded' ORDER BY finished_at DESC LIMIT 1", (cache_key,)).fetchone()
        return dict(r) if r else None

    def active_for_client(self, client: str) -> int:
        with self._lock:
            return self._c.execute("SELECT COUNT(*) FROM jobs WHERE client=? AND state IN ('queued','running')", (client,)).fetchone()[0]

    def created_since(self, client: str, since: float) -> int:
        with self._lock:
            return self._c.execute("SELECT COUNT(*) FROM jobs WHERE client=? AND created_at>=?", (client, since)).fetchone()[0]

    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._c.execute("SELECT state, COUNT(*) n FROM jobs GROUP BY state").fetchall()
        return {r["state"]: r["n"] for r in rows}


def dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))
