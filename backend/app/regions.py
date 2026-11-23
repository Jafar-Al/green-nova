"""Region catalogue from the canonical boundary file regions/jordan_adm1.geojson (owned by model1)."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .errors import NotFound


def slug(name: str) -> str:
    return re.sub(r"[^a-z]+", "", name.lower())


@dataclass(frozen=True)
class Region:
    id: str
    country: str
    name: str
    iso: str | None
    bbox: tuple[float, float, float, float]
    feature: dict
    area_km2: float


def _ring_area_km2(ring) -> float:
    r = 6371.0072
    s = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        s += math.radians(x1 - x0) * (2 + math.sin(math.radians(y0)) + math.sin(math.radians(y1)))
    return abs(s) * r * r / 2


def _bbox(geom: dict) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for k in c:
                walk(k)

    walk(geom["coordinates"])
    return (min(xs), min(ys), max(xs), max(ys))


@lru_cache(maxsize=4)
def _load(path_str: str, mtime: float) -> dict[str, Region]:
    data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    out: dict[str, Region] = {}
    for f in data.get("features", []):
        p = f.get("properties", {})
        name = p.get("shapeName") or p.get("name") or ""
        if not name or not f.get("geometry"):
            continue
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        area = sum(_ring_area_km2(poly[0]) - sum(_ring_area_km2(h) for h in poly[1:]) for poly in polys)
        rid = f"jo-{slug(name)}"
        out[rid] = Region(rid, "JO", name, p.get("shapeISO"), _bbox(g), f, round(area))
    return out


def load_regions(path: Path) -> dict[str, Region]:
    if not path.exists():
        return {}
    return _load(str(path), path.stat().st_mtime)


def get_region(path: Path, region_id: str) -> Region:
    r = load_regions(path).get(region_id)
    if not r:
        raise NotFound("Unknown region.", code="unknown_region")
    return r
