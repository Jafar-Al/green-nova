"""Bounded single-flight job queue with persistent state (SQLite) and result files.

- POST creates a job (or returns an identical completed one: cache key = kind + model version + region + params hash).
- At most ONE job runs at a time; at most `max_queue` wait; per-IP active/hourly limits; a global memory guard delays a job until enough RAM is free.
- Results are written to <runtime>/jobs/<id>/result.json and survive restarts. Unfinished jobs from a previous process are marked failed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .adapters.restoration import RestorationAdapter
from .adapters.suitability import SuitabilityAdapter
from .config import Settings
from .contract import is_m1_props
from .db import JobDB, dumps
from .errors import ApiError, ModelUnavailable, NotFound, QueueFull, TooManyRequests, scrub
from .logging_setup import log
from .memguard import available_mb, enough_memory
from .validation import check_polygon_ids, check_region_id

STAGES = {
    "suitability": ["Queued", "Loading the Model 1 result", "Validating against the data contract", "Finalising"],
    "restoration": ["Queued", "Selecting land units", "Running Model 2 feasibility and scenarios", "Validating results", "Finalising"],
}
CLASS5_NOTE = "Class 5 land is excluded by a legal or environmental restriction. It is never treated as restorable; the restriction is reported instead."


class JobCancelled(Exception):
    pass


def iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


class JobManager:
    def __init__(self, settings: Settings, db: JobDB, suit: SuitabilityAdapter, rest: RestorationAdapter, logger: logging.Logger):
        self.s = settings
        self.db = db
        self.suit = suit
        self.rest = rest
        self.log = logger
        self.q: queue.Queue[str] = queue.Queue(maxsize=settings.max_queue)
        self._cancel: set[str] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.current: str | None = None
        settings.jobs_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        n = self.db.interrupt_unfinished()
        if n:
            log(self.log, logging.WARNING, "marked interrupted jobs", count=n)
        self._thread = threading.Thread(target=self._worker, name="gn-job-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def queue_depth(self) -> int:
        return self.q.qsize()

    # ------------------------------------------------------------------ public views
    def view(self, row: dict) -> dict:
        kind = row["kind"]
        stages = STAGES[kind]
        err = None
        if row["state"] == "failed":
            err = {"code": row["error_code"] or "failed", "message": row["error_message"] or "The job failed.", "recoverable": row["error_code"] not in ("model_unavailable",)}
        return {
            "id": row["id"],
            "kind": kind,
            "region_id": row["region_id"],
            "state": row["state"],
            "progress": float(row["progress"]),
            "message": row["message"] or stages[0],
            "stages": stages,
            "created_at": iso(row["created_at"]),
            "finished_at": iso(row["finished_at"]),
            "error": err,
            "demo": False,
            "model_version": row["model_version"],
        }

    def get(self, job_id: str) -> dict:
        row = self.db.get(job_id)
        if not row:
            raise NotFound("Unknown job.", code="unknown_job")
        return row

    def result(self, job_id: str) -> dict:
        row = self.get(job_id)
        if row["state"] != "succeeded":
            raise ApiError("The job has not completed.", code="job_not_complete", status=409)
        p = self.s.jobs_dir / job_id / "result.json"
        if not p.is_file():
            raise ApiError("The result is no longer available. Start the analysis again.", code="result_missing", status=410)
        return json.loads(p.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ submit
    def submit(self, kind: str, region_id: str, polygon_ids: list[str] | None, client: str, client_hash: str) -> tuple[dict, bool]:
        if kind not in STAGES:
            raise ApiError("kind must be 'suitability' or 'restoration'", code="invalid_kind")
        region_id = check_region_id(region_id)
        adapter = self.suit if kind == "suitability" else self.rest
        adapter.require(region_id)  # 503 "not available" until the model's outputs exist
        ids: list[str] = []
        params: dict = {}
        if kind == "restoration":
            self.suit.require(region_id)  # restoration works on Model 1 polygons
            known = set(self.suit.by_id(region_id))
            ids = sorted(check_polygon_ids(polygon_ids, max_n=self.s.max_polygon_ids, known=known, region_id=region_id))
            params = {"polygon_ids": ids}
        version = adapter.version(region_id) or "unversioned"
        key_src = dumps({"kind": kind, "model": adapter.model, "version": version, "region": region_id, "params": params})
        if kind == "restoration":
            key_src += "|m1:" + (self.suit.version(region_id) or "unversioned")
        cache_key = hashlib.sha256(key_src.encode()).hexdigest()

        hit = self.db.find_cached(cache_key)
        if hit and (self.s.jobs_dir / hit["id"] / "result.json").is_file():
            return hit, True

        # abuse limits
        if self.db.active_for_client(client_hash) >= self.s.max_active_jobs_per_ip:
            raise TooManyRequests("You already have jobs running. Wait for them to finish.")
        if self.db.created_since(client_hash, time.time() - 3600) >= self.s.job_rate_per_hour:
            raise TooManyRequests("Job limit reached for this hour.")

        job_id = uuid.uuid4().hex
        now = time.time()
        row = {
            "id": job_id, "kind": kind, "model": adapter.model, "model_version": version, "region_id": region_id,
            "params_json": dumps(params), "cache_key": cache_key, "state": "queued", "progress": 0.0,
            "message": STAGES[kind][0], "client": client_hash, "created_at": now,
        }
        self.db.insert(row)
        try:
            self.q.put_nowait(job_id)
        except queue.Full:
            self.db.update(job_id, state="failed", error_code="queue_full", error_message="The analysis queue is full. Try again in a few minutes.", finished_at=time.time())
            raise QueueFull("The analysis queue is full. Try again in a few minutes.") from None
        log(self.log, logging.INFO, "job queued", job=job_id, kind=kind, region=region_id, n_ids=len(ids))
        return self.db.get(job_id) or row, False

    def cancel(self, job_id: str) -> dict:
        row = self.get(job_id)
        if row["state"] in ("queued", "running"):
            with self._lock:
                self._cancel.add(job_id)
            if row["state"] == "queued":
                self.db.update(job_id, state="cancelled", message="Cancelled", finished_at=time.time())
        return self.get(job_id)

    # ------------------------------------------------------------------ worker
    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._run(job_id)
            except Exception:  # noqa: BLE001 - the worker must survive anything
                self.log.exception("worker crashed on job %s", job_id)
                self.db.update(job_id, state="failed", error_code="internal_error", error_message="The job failed unexpectedly.", finished_at=time.time())
            finally:
                self.current = None

    def _is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancel

    def _run(self, job_id: str) -> None:
        row = self.db.get(job_id)
        if not row or row["state"] != "queued":
            return
        # memory guard: wait (bounded) for enough free RAM before starting
        t0 = time.time()
        while not enough_memory(self.s.min_free_mb):
            if time.time() - t0 > self.s.memory_wait_s or self._stop.is_set():
                a = available_mb()
                log(self.log, logging.WARNING, "memory guard refused job", job=job_id, available_mb=a)
                self.db.update(job_id, state="failed", error_code="insufficient_memory", error_message="Not enough free memory on the server to run this analysis right now. Try again later.", finished_at=time.time())
                return
            self.db.update(job_id, message="Waiting for free memory")
            time.sleep(2)
        self.current = job_id
        started = time.time()
        self.db.update(job_id, state="running", started_at=started, progress=0.02, message=STAGES[row["kind"]][1])
        last = [0.0]
        stages = STAGES[row["kind"]]

        def progress(frac: float, msg: str = "") -> None:
            if self._is_cancelled(job_id):
                raise JobCancelled()
            if time.time() - started > self.s.job_timeout_s:
                raise ApiError("The analysis took too long and was stopped.", code="timeout", status=504)
            now = time.time()
            if now - last[0] >= 0.4 or frac >= 1:
                last[0] = now
                idx = min(len(stages) - 1, 1 + int(max(0.0, min(frac, 0.999)) * (len(stages) - 1)))
                self.db.update(job_id, progress=max(0.02, min(float(frac), 0.99)), message=stages[idx])

        try:
            result = self._execute(row, progress)
            d = self.s.jobs_dir / job_id
            d.mkdir(parents=True, exist_ok=True)
            tmp = d / "result.json.tmp"
            tmp.write_text(json.dumps(result), encoding="utf-8")
            tmp.replace(d / "result.json")
            self.db.update(job_id, state="succeeded", progress=1.0, message="Complete", finished_at=time.time())
            log(self.log, logging.INFO, "job done", job=job_id, kind=row["kind"], seconds=round(time.time() - started, 2))
        except JobCancelled:
            self.db.update(job_id, state="cancelled", message="Cancelled", finished_at=time.time())
        except ApiError as e:
            self.log.warning("job %s failed: %s", job_id, e.message, exc_info=e.__cause__ is not None)
            self.db.update(job_id, state="failed", error_code=e.code, error_message=e.message, finished_at=time.time())
        except Exception:  # noqa: BLE001
            self.log.exception("job %s failed", job_id)
            self.db.update(job_id, state="failed", error_code="internal_error", error_message="The analysis failed unexpectedly.", finished_at=time.time())
        finally:
            with self._lock:
                self._cancel.discard(job_id)

    def _execute(self, row: dict, progress) -> dict:
        region = row["region_id"]
        if row["kind"] == "suitability":
            progress(0.2, "")
            run = self.suit.run(region)  # real model output, validated
            progress(0.7, "")
            return {"job_id": row["id"], "region_id": region, "run": run, "polygon_count": run["polygon_count"], "demo": False}
        params = json.loads(row["params_json"])
        ids = params["polygon_ids"]
        by_id = self.suit.by_id(region)
        rejected, analysable = [], []
        for pid in ids:
            c = by_id[pid]["properties"]["class_code"]
            if c == 5:
                rejected.append({"id": pid, "reason": CLASS5_NOTE})
            elif c in (3, 4):
                analysable.append(pid)
            else:
                rejected.append({"id": pid, "reason": f"Class {c}: restoration analysis applies to class 3 and 4 land."})
        feats: list[dict] = []
        if analysable:
            fc = self.rest.analyse(region, analysable, self.s.models_dir / "suitability" / "outputs" / region, self.s.jobs_dir / row["id"], progress)
            feats = fc["features"]
            got = {f["properties"]["source_polygon_id"] for f in feats}
            for pid in analysable:
                if pid not in got:
                    rejected.append({"id": pid, "reason": "Model 2 returned no valid result for this unit."})
        if analysable and not feats:
            raise ApiError("Model 2 returned no valid results for the selected units.", code="analysis_empty", status=500, model="restoration")
        meta = self.rest.metadata(region)
        meta.setdefault("model_version", self.rest.version(region) or row["model_version"])
        return {
            "job_id": row["id"], "region_id": region, "polygon_ids": ids, "features": feats, "rejected": rejected,
            "metadata": meta, "created_at": iso(row["created_at"]), "demo": False,
        }
