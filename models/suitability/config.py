"""Central configuration: paths, region registry, working grid, class vocabulary.

Everything region-specific lives in REGIONS so further governorates are added by config only.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.environ.get("GREEN_NOVA_DATA") or Path.home() / "GreenNovaData")   # raw data, caches, runtime windows: outside the repo
RAW = DATA_ROOT / "raw"
CACHE = DATA_ROOT / "cache"
COV = CACHE / "covariates"            # shared with model2 (manifest.json lives here)
M1CACHE = CACHE / "model1"            # model1-private derived stacks / labels / features
LOGS = DATA_ROOT / "logs"
LOCKS = DATA_ROOT / "locks"
MANIFEST = COV / "manifest.json"

REGIONS_GEOJSON = PROJECT_ROOT / "regions" / "jordan_adm1.geojson"
MODEL_DIR = PROJECT_ROOT / "models" / "suitability"
CKPT_DIR = MODEL_DIR / "checkpoints"
OUT_DIR = MODEL_DIR / "outputs"
REPORT_DIR = MODEL_DIR / "reports"

# ---------------------------------------------------------------- working grid
# Equal-area working CRS: every cell has exactly RES*RES m2, so areas are exact sums of cells.
WORK_CRS = "EPSG:6933"
RES = 100.0                       # grid cell size in metres
# Honest effective resolution: classes 1-4 are driven by climate (~1 km WorldClim / 4 km TerraClimate),
# SOTWIS map units (1:500 000) and SoilGrids (250 m). The 100 m grid is a sampling grid, not information content.
EFFECTIVE_RESOLUTION_M = 1000
TERRAIN_RES = 25.0                # DEM derivatives are computed at 25 m (Copernicus GLO-30 is ~30 m) then aggregated to RES

# ---------------------------------------------------------------- classes
CLASS_LABELS = {
    1: "Currently suitable",
    2: "Suitable with limitations",
    3: "Requires reclamation",
    4: "Currently unsuitable",
    5: "Excluded (legal/environmental restriction)",
}
NODATA = 0
HA_PER_CELL = (RES * RES) / 10_000.0       # 1.0 for 100 m
DUNUM_PER_HA = 10.0                         # 1 dunum = 1,000 m2 = 0.1 ha

# ---------------------------------------------------------------- regions
# Governorates (ADM1) come from the canonical boundary file (geoBoundaries gbOpen JOR ADM1, 2006 vintage, Wikimedia-derived;
# coarse vertices), so every governorate in regions/jordan_adm1.geojson is a valid region id (e.g. "jo-maan", "jo-irbid").
def _load_registry() -> dict:
    import json
    try:
        feats = json.loads(REGIONS_GEOJSON.read_text(encoding="utf-8"))["features"]
    except (FileNotFoundError, KeyError, ValueError):
        return {"jo-maan": {"name": "Ma'an", "country": "JO", "adm1": "Ma'an", "iso": "JO-MN"}}
    out = {}
    for f in feats:
        p = f.get("properties", {})
        if p.get("region_id"):
            out[p["region_id"]] = {"name": p.get("name"), "country": p.get("country", "JO"), "adm1": p.get("name"), "iso": p.get("iso")}
    return out


REGIONS = _load_registry()
# Training/validation geography = all of Jordan (12 governorates); evaluation targets include jo-maan.
TRAIN_COUNTRY = "JO"


def ensure_dirs() -> None:
    for p in (COV, M1CACHE, LOGS, LOCKS, CKPT_DIR, OUT_DIR, REPORT_DIR):
        p.mkdir(parents=True, exist_ok=True)
