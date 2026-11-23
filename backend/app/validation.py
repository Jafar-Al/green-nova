"""Input validation. Everything that reaches a model or the filesystem goes through here."""
from __future__ import annotations

import math
import re
from typing import Any, Iterable

from .errors import ApiError

REGION_RE = re.compile(r"^[a-z]{2}-[a-z0-9]{2,30}$")
M1_ID_RE = re.compile(r"^m1-([a-z]{2}-[a-z0-9]{2,30})-(\d{1,7})$")
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def check_region_id(v: Any) -> str:
    if not isinstance(v, str) or not REGION_RE.match(v):
        raise ApiError("region_id is not a valid region id", code="invalid_region")
    return v


def check_polygon_id(v: Any) -> str:
    if not isinstance(v, str) or not M1_ID_RE.match(v):
        raise ApiError("polygon id must look like m1-<region>-<n>", code="invalid_polygon_id")
    return v


def region_of_polygon_id(pid: str) -> str:
    m = M1_ID_RE.match(pid)
    if not m:
        raise ApiError("polygon id must look like m1-<region>-<n>", code="invalid_polygon_id")
    return m.group(1)


def check_job_id(v: Any) -> str:
    if not isinstance(v, str) or not JOB_ID_RE.match(v):
        raise ApiError("invalid job id", code="invalid_job_id")
    return v


def check_polygon_ids(ids: Any, *, max_n: int, known: Iterable[str] | None = None, region_id: str | None = None) -> list[str]:
    """Unique, well-formed ids, bounded count, all matched against the known set when one is given. Unknown ids are rejected, never guessed."""
    if not isinstance(ids, list) or not ids:
        raise ApiError("polygon_ids must be a non-empty list", code="invalid_polygon_ids")
    if len(ids) > max_n:
        raise ApiError(f"at most {max_n} polygon ids per request", code="too_many_polygon_ids")
    out: list[str] = []
    seen: set[str] = set()
    for i in ids:
        pid = check_polygon_id(i)
        if region_id and region_of_polygon_id(pid) != region_id:
            raise ApiError("polygon id belongs to a different region", code="invalid_polygon_ids")
        if pid not in seen:
            seen.add(pid)
            out.append(pid)
    if known is not None:
        ks = known if isinstance(known, (set, frozenset)) else set(known)
        unknown = [p for p in out if p not in ks]
        if unknown:
            raise ApiError(f"{len(unknown)} polygon id(s) are not part of the current analysis", code="unknown_polygon_ids")
    return out


def _count_vertices(coords: Any) -> int:
    if not isinstance(coords, list):
        return 0
    if coords and isinstance(coords[0], (int, float)):
        return 1
    return sum(_count_vertices(c) for c in coords)


def _walk_positions(coords: Any):
    if isinstance(coords, list) and coords and isinstance(coords[0], (int, float)):
        yield coords
    elif isinstance(coords, list):
        for c in coords:
            yield from _walk_positions(c)


def ring_area_km2(ring: list[list[float]]) -> float:
    """Spherical (authalic radius) area of one lon/lat ring in km2 - bounds checking only, not for reporting."""
    r = 6371.0072
    s = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        s += math.radians(x1 - x0) * (2 + math.sin(math.radians(y0)) + math.sin(math.radians(y1)))
    return abs(s) * r * r / 2


def validate_geometry(geom: Any, *, region_bbox: tuple[float, float, float, float], max_vertices: int, max_area_km2: float) -> dict:
    """Polygon / MultiPolygon only, bounded vertex count and area, finite coordinates, entirely inside the region bbox."""
    if not isinstance(geom, dict) or geom.get("type") not in ("Polygon", "MultiPolygon"):
        raise ApiError("geometry must be a GeoJSON Polygon or MultiPolygon", code="invalid_geometry")
    coords = geom.get("coordinates")
    if not isinstance(coords, list) or not coords:
        raise ApiError("geometry has no coordinates", code="invalid_geometry")
    if _count_vertices(coords) > max_vertices:
        raise ApiError(f"geometry has more than {max_vertices} vertices", code="geometry_too_complex")
    w, s, e, n = region_bbox
    for p in _walk_positions(coords):
        if len(p) < 2 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in p[:2]):
            raise ApiError("geometry contains an invalid coordinate", code="invalid_geometry")
        if not (w <= p[0] <= e and s <= p[1] <= n):
            raise ApiError("geometry must lie inside the region", code="geometry_outside_region")
    polys = [coords] if geom["type"] == "Polygon" else coords
    area = 0.0
    for poly in polys:
        if not poly or not isinstance(poly[0], list) or len(poly[0]) < 4:
            raise ApiError("polygon rings need at least 4 positions", code="invalid_geometry")
        area += ring_area_km2(poly[0]) - sum(ring_area_km2(h) for h in poly[1:])
    if area > max_area_km2:
        raise ApiError(f"geometry larger than {max_area_km2:g} km2", code="geometry_too_large")
    if area <= 0:
        raise ApiError("geometry has no area", code="invalid_geometry")
    return geom


def validate_bbox(v: Any, *, region_bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    try:
        w, s, e, n = (float(x) for x in v)
    except (TypeError, ValueError):
        raise ApiError("bbox must be west,south,east,north", code="invalid_bbox") from None
    if not all(math.isfinite(x) for x in (w, s, e, n)) or w >= e or s >= n:
        raise ApiError("bbox is not a valid box", code="invalid_bbox")
    rw, rs, re_, rn = region_bbox
    if w < rw or s < rs or e > re_ or n > rn:
        raise ApiError("bbox must lie inside the region", code="geometry_outside_region")
    return (w, s, e, n)
