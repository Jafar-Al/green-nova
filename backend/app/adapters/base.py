"""Model adapters read the models' REAL output files. Nothing here fabricates or fills in data: missing files => ModelUnavailable (HTTP 503)."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from ..config import Settings
from ..errors import ModelUnavailable, scrub_obj


class BaseAdapter:
    model = ""
    label = ""
    required = ("polygons.geojson",)

    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache: dict[tuple, Any] = {}
        self._lock = threading.Lock()

    def out_dir(self, region: str) -> Path:
        return self.settings.models_dir / self.model_dirname / "outputs" / region

    model_dirname = ""

    # -- availability ---------------------------------------------------------------------------------------------------
    def missing(self, region: str) -> list[str]:
        d = self.out_dir(region)
        return [f for f in self.required if not (d / f).is_file()]

    def available(self, region: str) -> bool:
        return not self.missing(region)

    def metadata(self, region: str) -> dict:
        p = self.out_dir(region) / "run_metadata.json"
        if not p.is_file():
            return {}
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return scrub_obj(m) if isinstance(m, dict) else {}

    def version(self, region: str) -> str | None:
        v = self.metadata(region).get("model_version")
        return str(v) if v else None

    def status(self, region: str) -> dict:
        miss = self.missing(region)
        if miss:
            return {"available": False, "reason": f"{self.label} outputs for this region are not present yet.", "version": None}
        return {"available": True, "reason": None, "version": self.version(region)}

    def require(self, region: str) -> None:
        if self.missing(region):
            raise ModelUnavailable(f"{self.label} is not available for this region yet.", model=self.model)

    # -- cached, validated loading ---------------------------------------------------------------------------------------
    def _stamp(self, p: Path) -> tuple:
        s = p.stat()
        return (str(p), s.st_mtime_ns, s.st_size)

    def load_json_cached(self, p: Path, loader):
        key = self._stamp(p)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        val = loader(json.loads(p.read_text(encoding="utf-8")))
        with self._lock:
            self._cache = {k: v for k, v in self._cache.items() if k[0] != key[0]}
            self._cache[key] = val
        return val
