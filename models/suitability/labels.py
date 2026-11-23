"""Observed-cultivation labels (OBSERVED, derived from two independent land-cover products; not field-verified).

cult_frac = mean(WorldCover-2021 crop fraction, Impact-Observatory-2021 crop fraction) per 100 m cell.
label  1  : both products call the cell mostly cropland  (wc >= POS_WC and io >= POS_IO)
label  0  : both products see (almost) no cropland in 2021 and WorldCover 2020 agrees (wc21, io21, wc20 <= NEG)
label -1  : ambiguous (disagreement / partial cover) -> excluded from training and from metrics
Also: `new_crop` (temporal hold-out): IO-2023 cropland that was NOT cropland in IO-2017/2021, WorldCover 2020/2021.
Excluded from all label sets: cells with a legal/environmental restriction code or built-up/water fractions (class 5 logic).
Run: python -m models.suitability.labels
"""
from __future__ import annotations

import json

import numpy as np

from . import config
from .grid import read_tif, write_tif
from .regions import jordan_grid

STACK = config.M1CACHE / "stack"
POS_WC, POS_IO, NEG = 0.5, 0.3, 0.05


def _r(name):
    return read_tif(STACK / f"{name}.tif", 1)


def build():
    grid = jordan_grid()
    wc21, wc20, io21, io17, io23 = (_r(n) for n in ("wc2021_crop", "wc2020_crop", "io2021_crop", "io2017_crop", "io2023_crop"))
    built, water = _r("wc2021_built"), _r("wc2021_water")
    restr = read_tif(STACK / "restriction_code.tif", 1)
    domain = read_tif(config.M1CACHE / "adm1_id.tif", 1) > 0
    ok = domain & (restr == 0) & ~(built > 0.3) & ~(water > 0.3) & np.isfinite(wc21) & np.isfinite(io21)
    cult = np.nanmean(np.stack([wc21, io21]), axis=0).astype("float32")
    lab = np.full(grid.shape, -1, "int8")
    neg = (wc21 <= NEG) & (io21 <= NEG) & (np.nan_to_num(wc20, nan=0.0) <= NEG)
    pos = (wc21 >= POS_WC) & (io21 >= POS_IO)
    lab[neg] = 0
    lab[pos] = 1
    lab[~ok] = -1
    write_tif(STACK / "label_cult.tif", lab, grid, nodata=-1, dtype="int8")
    write_tif(STACK / "cult_frac.tif", cult, grid, nodata=float("nan"), dtype="float32")
    newc = (io23 >= 0.5) & (np.nan_to_num(io17) < 0.1) & (np.nan_to_num(io21) < 0.1) \
        & (np.nan_to_num(wc20) < 0.1) & (np.nan_to_num(wc21) < 0.1) & ok
    write_tif(STACK / "label_new_crop.tif", newc.astype("uint8"), grid, nodata=255, dtype="uint8")

    # agreement diagnostics between the two label sources (binary at 0.5), inside the evaluable domain
    a, b = (wc21 >= 0.5)[ok], (io21 >= 0.5)[ok]
    po = float((a == b).mean()); pe = float(a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean()))
    adm = read_tif(config.M1CACHE / "adm1_id.tif", 1)
    per_gov = {}
    for i in range(1, int(adm.max()) + 1):
        m = (adm == i) & ok
        per_gov[int(i)] = dict(cells=int(m.sum()), pos=int((lab[m] == 1).sum()), neg=int((lab[m] == 0).sum()),
                               amb=int((lab[m] == -1).sum()), wc_crop_ha=float(np.nansum(wc21[m])), io_crop_ha=float(np.nansum(io21[m])))
    stats = dict(n_cells=int(ok.sum()), wc_pos_share=float(a.mean()), io_pos_share=float(b.mean()),
                 agreement=po, cohen_kappa=(po - pe) / (1 - pe + 1e-12),
                 both_pos=int((a & b).sum()), wc_only=int((a & ~b).sum()), io_only=int((~a & b).sum()),
                 label_pos=int((lab == 1).sum()), label_neg=int((lab == 0).sum()), label_amb=int(((lab == -1) & ok).sum()),
                 new_crop_cells=int(newc.sum()), per_governorate=per_gov,
                 thresholds=dict(POS_WC=POS_WC, POS_IO=POS_IO, NEG=NEG))
    (STACK / "label_stats.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    build()
