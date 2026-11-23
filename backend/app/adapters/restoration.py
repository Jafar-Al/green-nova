"""Model 2 (restoration) adapter: region-wide precomputed layer + on-demand analysis of selected Model 1 polygons."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from ..contract import filter_features, is_m2_props
from ..errors import ApiError, ModelUnavailable
from .base import BaseAdapter

ProgressCb = Callable[[float, str], None]


def _round_geom(g: dict, nd: int = 5) -> dict:
    def r(c):
        return [round(c[0], nd), round(c[1], nd)] if c and isinstance(c[0], (int, float)) else [r(x) for x in c]

    return {"type": g["type"], "coordinates": r(g["coordinates"])}


class RestorationAdapter(BaseAdapter):
    model = "restoration"
    model_dirname = "restoration"
    label = "Model 2 (restoration potential)"

    def runtime_present(self, region: str) -> bool:
        return (self.settings.models_dir / "restoration" / "runtime_data" / region / "stack.npz").is_file()

    def layer(self, region: str) -> dict:
        self.require(region)

        def load(raw):
            feats, bad = filter_features(raw, is_m2_props)
            return {"type": "FeatureCollection", "features": feats, "gn_rejected_features": bad}

        return self.load_json_cached(self.out_dir(region) / "polygons.geojson", load)

    SLIM_PROPS = ("id", "source_polygon_id", "current_class_code", "area_ha", "area_dunum", "feasibility")

    def slim_layer(self, region: str, known_m1_ids: set[str] | None) -> dict:
        """Browser-safe region layer: simplified geometry + a handful of properties (the full file is tens of MB).
        Only features linked to a CURRENT Model 1 polygon are kept (the stand-in run used synthetic ids until Model 2 is rerun on Model 1's polygons).
        Full per-unit detail is served by /v1/land/{id}. Cached by file mtime, so an atomic output swap is picked up automatically."""
        fc = self.layer(region)
        key = ("slim", id(fc), len(known_m1_ids) if known_m1_ids is not None else -1)
        with self._lock:
            hit = self._cache.get(key)
        if hit is not None:
            return hit
        from shapely.geometry import mapping, shape

        feats = []
        total = 0
        for f in fc["features"]:
            p = f["properties"]
            total += 1
            if known_m1_ids is not None and p["source_polygon_id"] not in known_m1_ids:
                continue
            g = shape(f["geometry"]).simplify(0.0005, preserve_topology=True)
            if g.is_empty:
                continue
            gj = mapping(g)
            feats.append({"type": "Feature", "geometry": _round_geom(gj), "properties": {k: p[k] for k in self.SLIM_PROPS if k in p}})
        out = {"type": "FeatureCollection", "features": feats, "gn_total_model2_units": total, "gn_linked_units": len(feats)}
        if total and not feats:
            out["gn_note"] = "Model 2 results do not yet reference the current Model 1 polygons (they are being recomputed)."
        with self._lock:
            self._cache = {k: v for k, v in self._cache.items() if not (k[0] == "slim")}
            self._cache[key] = out
        return out

    def by_source_id(self, region: str) -> dict[str, dict]:
        return {f["properties"]["source_polygon_id"]: f for f in self.layer(region)["features"]}

    def status(self, region: str) -> dict:
        s = super().status(region)
        s["can_run_selection"] = self.runtime_present(region)
        return s

    def analyse(self, region: str, polygon_ids: list[str], suitability_dir: Path, job_dir: Path, progress: ProgressCb) -> dict:
        """Run the real Model 2 engine on the selected Model 1 polygons (CPU, seconds per polygon). Returns the validated FeatureCollection."""
        if not self.runtime_present(region):
            raise ModelUnavailable("Model 2 runtime data is not available for this region.", model=self.model)
        try:
            from models.restoration import infer  # type: ignore
        except Exception as e:  # noqa: BLE001
            raise ModelUnavailable("Model 2 could not be loaded.", model=self.model) from e
        out = job_dir / "out"
        out.mkdir(parents=True, exist_ok=True)
        try:
            infer.run_region(region, suitability_dir=str(suitability_dir), out_dir=str(out), polygon_ids=polygon_ids, progress=progress, raster=False)
        except ApiError:
            raise
        except Exception as e:  # noqa: BLE001 - typed model errors are mapped to a generic user message; detail goes to the log
            raise ApiError("Model 2 could not analyse the selected land units.", code="analysis_failed", status=500, model=self.model) from e
        p = out / "polygons.geojson"
        if not p.is_file():
            raise ApiError("Model 2 produced no result for the selection.", code="analysis_empty", status=500, model=self.model)
        feats, bad = filter_features(json.loads(p.read_text(encoding="utf-8")), is_m2_props)
        return {"type": "FeatureCollection", "features": feats, "gn_rejected_features": bad}
