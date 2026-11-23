"""Model 1 (suitability) adapter: serves the model's polygons.geojson / run_metadata.json for a region."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from ..contract import filter_features, is_m1_props
from .base import BaseAdapter

CLASS_LABELS = {
    1: "Currently suitable",
    2: "Suitable with limitations",
    3: "Requires reclamation",
    4: "Currently unsuitable",
    5: "Excluded (legal or environmental restriction)",
}


class SuitabilityAdapter(BaseAdapter):
    model = "suitability"
    model_dirname = "suitability"
    label = "Model 1 (land suitability)"

    def polygons(self, region: str) -> dict:
        """Validated FeatureCollection. Invalid features are dropped and counted in `gn_rejected_features`, never repaired."""
        self.require(region)

        def load(raw):
            feats, bad = filter_features(raw, is_m1_props)
            return {"type": "FeatureCollection", "features": feats, "gn_rejected_features": bad}

        return self.load_json_cached(self.out_dir(region) / "polygons.geojson", load)

    def by_id(self, region: str) -> dict[str, dict]:
        fc = self.polygons(region)
        key = ("byid", id(fc))
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        m = {f["properties"]["id"]: f for f in fc["features"]}
        with self._lock:
            self._cache = {k: v for k, v in self._cache.items() if not (k[0] == "byid")}
            self._cache[key] = m
        return m

    def run(self, region: str) -> dict:
        fc = self.polygons(region)
        feats = fc["features"]
        total = sum(f["properties"]["area_ha"] for f in feats)
        stats = []
        for code in (1, 2, 3, 4, 5):
            fs = [f for f in feats if f["properties"]["class_code"] == code]
            ha = sum(f["properties"]["area_ha"] for f in fs)
            dn = sum(f["properties"]["area_dunum"] for f in fs)
            stats.append(
                {
                    "code": code,
                    "label": CLASS_LABELS[code],
                    "polygon_count": len(fs),
                    "area_ha": round(ha, 2),
                    "area_dunum": round(dn, 1),
                    "share": round(ha / total, 4) if total > 0 else 0.0,
                }
            )
        meta = self.metadata(region)
        p = self.out_dir(region) / "polygons.geojson"
        created = meta.get("created_at") or datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
        res = sorted({float(f["properties"]["effective_resolution_m"]) for f in feats})
        return {
            "region_id": region,
            "created_at": created,
            "stats": stats,
            "polygon_count": len(feats),
            "total_area_ha": round(total, 2),
            "total_area_dunum": round(sum(f["properties"]["area_dunum"] for f in feats), 1),
            "metadata": {**meta, "model_version": meta.get("model_version", "unknown"), "effective_resolution_m": meta.get("effective_resolution_m", res[0] if len(res) == 1 else res)},
            "demo": False,
            "rejected_features": fc["gn_rejected_features"],
        }
