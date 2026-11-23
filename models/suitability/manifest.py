"""Shared covariate-cache manifest (C:\\GreenNovaData\\cache\\covariates\\manifest.json).

Format: {"entries": [ {layer, source_url, license, resolution, crs, bbox, date, files, notes, added_by} ]}
model1 and model2 both append; writes are atomic and guarded by an O_EXCL lock file.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from . import config


def _lock_path():
    return config.COV / "manifest.lock"


class _Lock:
    def __enter__(self):
        config.COV.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        while True:
            try:
                fd = os.open(str(_lock_path()), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"model1 {os.getpid()} {datetime.now(timezone.utc).isoformat()}".encode())
                os.close(fd)
                return self
            except FileExistsError:
                if time.time() - t0 > 60:
                    # stale lock (>60 s): remove
                    try:
                        os.remove(_lock_path())
                    except OSError:
                        pass
                time.sleep(0.2)

    def __exit__(self, *a):
        try:
            os.remove(_lock_path())
        except OSError:
            pass


def load() -> dict:
    if config.MANIFEST.exists():
        try:
            d = json.loads(config.MANIFEST.read_text(encoding="utf-8"))
            if isinstance(d, list):
                d = {"entries": d}
            d.setdefault("entries", [])
            return d
        except json.JSONDecodeError:
            pass
    return {"entries": []}


def has_layer(layer: str) -> bool:
    return any(e.get("layer") == layer for e in load()["entries"])


def add_entry(layer: str, source_url: str, license: str, resolution: str, crs: str, bbox, date: str,
              files=None, notes: str = "", added_by: str = "model1") -> None:
    entry = dict(layer=layer, source_url=source_url, license=license, resolution=resolution, crs=crs,
                 bbox=list(bbox) if bbox is not None else None, date=date, files=files or [], notes=notes,
                 added_by=added_by, added_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    with _Lock():
        d = load()
        d["entries"] = [e for e in d["entries"] if e.get("layer") != layer] + [entry]
        tmp = config.MANIFEST.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2), encoding="utf-8")
        os.replace(tmp, config.MANIFEST)
