"""Build the self-contained runtime folder used by inference (no network, no raw data):

  <RUNTIME>/model1/<region>/features.f32   float32 memmap (L, H, W) over the region bounding box
  <RUNTIME>/model1/<region>/meta.json      grid, layer names, vintages, sizes (no absolute paths)
  <RUNTIME>/model1/regions/jordan_adm1.geojson
  <RUNTIME>/model1/data_sources.json

Run: python -m models.suitability.package_runtime --region jo-maan
"""
from __future__ import annotations

import argparse
import json
import shutil
import time

import numpy as np
import rasterio
from rasterio.windows import Window

from . import config, features as F
from .grid import Grid, window_grid
from .regions import jordan_grid, load_regions, region_mask

RUNTIME_LAYERS = [n for n in F.INTRINSIC if n != "awc_ptf"] + F.SD_LAYERS + [
    "restriction_code", "label_cult", "cult_frac", "wc2021_built", "wc2021_water", "wc2021_tree", "wc2021_bare"]


def runtime_root():
    """Folder holding the per-region <region>/features.npy windows.

    Override with GREEN_NOVA_M1_RUNTIME (deliberately different from the backend's GREEN_NOVA_RUNTIME, which is the job-store folder)."""
    import os
    from pathlib import Path
    v = os.environ.get("GREEN_NOVA_M1_RUNTIME")
    return Path(v) if v else config.DATA_ROOT / "runtime" / "model1"


def package(region_id: str):
    grid = jordan_grid()
    mask = region_mask(region_id)
    rows, cols = np.where(mask.any(1))[0], np.where(mask.any(0))[0]
    r0, r1, c0, c1 = int(rows.min()), int(rows.max()) + 1, int(cols.min()), int(cols.max()) + 1
    wg = window_grid(grid, r0, r1, c0, c1)
    root = runtime_root() / region_id
    root.mkdir(parents=True, exist_ok=True)
    L = len(RUNTIME_LAYERS)
    mm = np.lib.format.open_memmap(root / "features.npy", mode="w+", dtype="float32", shape=(L, wg.height, wg.width))
    for i, n in enumerate(RUNTIME_LAYERS):
        path = (config.M1CACHE / "adm1_id.tif") if n == "adm1_id" else config.M1CACHE / "stack" / f"{n}.tif"
        with rasterio.open(path) as s:
            a = s.read(1, window=Window(c0, r0, wg.width, wg.height)).astype("float32")
        mm[i] = a
    mm.flush()
    reg_mask = mask[r0:r1, c0:c1]
    np.save(root / "region_mask.npy", np.packbits(reg_mask, axis=None))
    meta = dict(region_id=region_id, grid=wg.to_dict(), layers=RUNTIME_LAYERS, shape=[L, wg.height, wg.width],
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), mask_shape=[wg.height, wg.width],
                full_grid=grid.to_dict(), window_in_full_grid=[r0, r1, c0, c1])
    (root / "meta.json").write_text(json.dumps(meta, indent=1))
    shutil.copy(config.REGIONS_GEOJSON, root.parent / "regions_jordan_adm1.geojson")
    size = sum(p.stat().st_size for p in root.parent.rglob("*") if p.is_file())
    print(region_id, "layers", L, "shape", (wg.height, wg.width), "runtime dir bytes", size)
    return root


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="jo-maan")
    a = ap.parse_args()
    package(a.region)
