"""Light validators for docs/CONTRACT.md feature properties (mirror of web/src/lib/contract.ts guards).

Model output is validated before it is served: a feature that does not match the contract is dropped and COUNTED (never repaired, never invented).
Unknown extra properties are tolerated (ML agents may add optional fields).
"""
from __future__ import annotations

from typing import Any

EVIDENCE = {"observed", "ml_predicted", "expert_rule", "simulated"}
FACTOR_STATUS = {"favourable", "marginal", "limiting", "restricted"}
FEAS_CLASS = {"high", "moderate", "low", "not_feasible"}
REVERSIBILITY = {"reversible", "partially_reversible", "irreversible"}


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def _unit(v: Any) -> bool:
    return _num(v) and 0 <= v <= 1


def _lonlat(v: Any) -> bool:
    return isinstance(v, (list, tuple)) and len(v) == 2 and _num(v[0]) and _num(v[1]) and abs(v[0]) <= 180 and abs(v[1]) <= 90


def is_m1_props(p: Any) -> bool:
    if not isinstance(p, dict):
        return False
    try:
        if not isinstance(p["id"], str) or p["class_code"] not in (1, 2, 3, 4, 5) or not isinstance(p["class_label"], str):
            return False
        if not _num(p["area_ha"]) or p["area_ha"] < 0 or not _num(p["area_dunum"]) or p["area_dunum"] < 0:
            return False
        if not _unit(p["confidence"]) or not isinstance(p["confidence_method"], str):
            return False
        cp = p["class_probabilities"]
        if not isinstance(cp, dict) or not all(_unit(cp.get(k)) for k in "12345"):
            return False
        f = p["factors"]
        if not isinstance(f, list):
            return False
        for x in f:
            if not (isinstance(x, dict) and isinstance(x.get("name"), str) and x.get("status") in FACTOR_STATUS and x.get("evidence") in EVIDENCE):
                return False
            if not (x.get("value") is None or _num(x.get("value")) or isinstance(x.get("value"), str)):
                return False
        if not _lonlat(p["centroid"]) or not _num(p["effective_resolution_m"]):
            return False
        pr = p["provenance"]
        return isinstance(pr, dict) and isinstance(pr.get("model_version"), str) and isinstance(pr.get("data_sources"), list)
    except KeyError:
        return False


def is_m2_props(p: Any) -> bool:
    if not isinstance(p, dict):
        return False
    try:
        if not isinstance(p["id"], str) or not isinstance(p["source_polygon_id"], str) or p["current_class_code"] not in (2, 3, 4, 5):
            return False
        if not _num(p["area_ha"]) or not _num(p["area_dunum"]):
            return False
        for l in p["limiting_factors"]:
            if not (isinstance(l, dict) and isinstance(l.get("factor"), str) and _unit(l.get("severity")) and l.get("reversibility") in REVERSIBILITY and l.get("evidence") in EVIDENCE):
                return False
        fe = p["feasibility"]
        if not (isinstance(fe, dict) and _unit(fe.get("score")) and fe.get("class") in FEAS_CLASS and _unit(fe.get("confidence"))):
            return False
        iv = fe.get("interval")
        if not (isinstance(iv, list) and len(iv) == 2 and _unit(iv[0]) and _unit(iv[1])):
            return False
        if not isinstance(p["interventions"], list):
            return False
        for s in p["scenarios"]:
            w = s.get("water_requirement_m3_ha_yr")
            if not (isinstance(s, dict) and isinstance(s.get("id"), str) and s.get("post_class_code") in (1, 2, 3, 4, 5) and _unit(s.get("post_class_probability")) and s.get("evidence") == "simulated"):
                return False
            if not (isinstance(w, dict) and all(_num(w.get(k)) for k in ("low", "central", "high"))):
                return False
        return isinstance(p["soil"], dict) and isinstance(p["terrain"], dict) and isinstance(p["climate"], dict) and isinstance(p["provenance"], dict)
    except (KeyError, AttributeError, TypeError):
        return False


def filter_features(fc: Any, guard) -> tuple[list[dict], int]:
    """Return (valid polygon features, number rejected)."""
    if not isinstance(fc, dict) or fc.get("type") != "FeatureCollection" or not isinstance(fc.get("features"), list):
        return [], 1
    ok: list[dict] = []
    bad = 0
    for f in fc["features"]:
        g = f.get("geometry") if isinstance(f, dict) else None
        if isinstance(g, dict) and g.get("type") in ("Polygon", "MultiPolygon") and guard(f.get("properties")):
            ok.append(f)
        else:
            bad += 1
    return ok, bad
