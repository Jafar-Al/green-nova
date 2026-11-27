"""Model 2 (restoration potential) configuration: paths, region registry, grid, vocabularies.

Honesty note on resolution: the working grid is 250 m (SoilGrids native), but the decisive inputs are coarser:
climate / water demand ~4 km (TerraClimate), salinity/sodicity ~1 km (Hassani et al. 2020), slope 30 m.
`EFFECTIVE_RESOLUTION_M` therefore records the *coarsest decisive input per attribute*, never the grid spacing.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.environ.get("GREEN_NOVA_DATA") or Path.home() / "GreenNovaData")   # raw data, caches: outside the repo
RAW = DATA_ROOT / "raw"
CACHE = DATA_ROOT / "cache"
COV = CACHE / "covariates"              # shared with model1 (manifest.json lives here)
M2CACHE = CACHE / "model2"              # model2-private derived stacks / training tables
LOGS = DATA_ROOT / "logs"
LOCKS = DATA_ROOT / "locks"
MANIFEST = COV / "manifest.json"

MODEL_DIR = PROJECT_ROOT / "models" / "restoration"
KNOWLEDGE_DIR = MODEL_DIR / "knowledge"
CKPT_DIR = MODEL_DIR / "checkpoints"
OUT_DIR = MODEL_DIR / "outputs"
EVAL_DIR = MODEL_DIR / "eval"
M1_OUT_DIR = PROJECT_ROOT / "models" / "suitability" / "outputs"
REGIONS_GEOJSON = PROJECT_ROOT / "regions" / "jordan_adm1.geojson"

MODEL_VERSION = "restoration-0.1.0"
SEED = 20261122

# ---------------------------------------------------------------- working grid
WORK_CRS = "EPSG:6933"          # equal-area; Ma'an (~30 N) sits on the standard parallel, so distortion is ~0
RES = 250.0                     # metres; SoilGrids native
HA_PER_CELL = RES * RES / 10_000.0
DUNUM_PER_HA = 10.0             # 1 dunum = 1,000 m2 = 0.1 ha (Jordanian metric dunum)

# decisive-input resolutions (metres) used to state honest effective resolution per attribute
EFFECTIVE_RESOLUTION_M = {
    "soil_ph_soc_texture": 250,     # SoilGrids 2.0 nominal (true information content is coarser in data-poor deserts)
    "salinity_sodicity": 1000,      # Hassani et al. 2020 ~1 km
    "terrain_slope": 30,            # Copernicus GLO-30
    "climate_water_demand": 4000,   # TerraClimate ~4 km
    "overall": 4000,                # feasibility is driven by the water term; do not claim better
}

# ---------------------------------------------------------------- vocabularies (CONTRACT.md)
EVIDENCE = ("observed", "ml_predicted", "expert_rule", "simulated")
M1_CLASS_LABELS = {1: "Currently suitable", 2: "Suitable with limitations", 3: "Requires reclamation",
                   4: "Currently unsuitable", 5: "Excluded (legal/environmental restriction)"}
FEAS_CODES = {"not_feasible": 1, "low": 2, "moderate": 3, "high": 4}
FEAS_LABELS = {v: k for k, v in FEAS_CODES.items()}

def _load_registry() -> dict:
    """Governorates from the canonical boundary file; `bbox_4326_fallback` (lon/lat) is their bounding box."""
    import json

    def bounds(coords, acc):
        if coords and isinstance(coords[0], (int, float)):
            acc[0], acc[1] = min(acc[0], coords[0]), min(acc[1], coords[1])
            acc[2], acc[3] = max(acc[2], coords[0]), max(acc[3], coords[1])
        else:
            for c in coords:
                bounds(c, acc)
        return acc

    try:
        feats = json.loads(REGIONS_GEOJSON.read_text(encoding="utf-8"))["features"]
    except (FileNotFoundError, KeyError, ValueError):
        return {"jo-maan": {"name": "Ma'an", "country": "JO", "adm1": "Ma'an", "iso": "JO-MN",
                            "bbox_4326_fallback": (35.301, 29.184, 38.003, 31.274)}}
    out = {}
    for f in feats:
        p = f.get("properties", {})
        if p.get("region_id") and f.get("geometry"):
            bb = bounds(f["geometry"]["coordinates"], [1e9, 1e9, -1e9, -1e9])
            out[p["region_id"]] = {"name": p.get("name"), "country": p.get("country", "JO"), "adm1": p.get("name"), "iso": p.get("iso"),
                                   "bbox_4326_fallback": tuple(round(v, 4) for v in bb)}
    return out


REGIONS = _load_registry()

# Feasibility class cut-offs on the Monte-Carlo success probability (expert_rule; sensitivity-tested in eval).
FEAS_CUTS = {"high": 0.70, "moderate": 0.40, "low": 0.15}

# Monte-Carlo budget (outer = parameter draws, inner = input-uncertainty draws)
MC_OUTER = 40
MC_INNER = 8


def ensure_dirs() -> None:
    for p in (COV, M2CACHE, LOGS, LOCKS, CKPT_DIR, OUT_DIR, EVAL_DIR, KNOWLEDGE_DIR):
        p.mkdir(parents=True, exist_ok=True)
