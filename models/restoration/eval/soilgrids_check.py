"""Bias / error / interval check of SoilGrids 2.0 (1 km aggregate, 5-15 cm mean) against measured WoSIS topsoil (0-30 cm) in arid domains.

Purpose: SoilGrids supplies pH, SOC and texture for Ma'an (ml_predicted, third-party).  We do NOT retrain these; we measure how wrong SoilGrids is
in arid held-out geography and use the measured RMSE as the 1-sigma uncertainty in the Monte-Carlo engine (honest, empirically calibrated).
CAVEAT (leakage): SoilGrids was trained on WoSIS profiles, so these errors are optimistic for sites that were in its training data.  Depth mismatch
(5-15 cm layer vs 0-30 cm lab mean) adds a little extra error that is included in the RMSE.
Run: python -m models.restoration.eval.soilgrids_check
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .. import config, features
from ..soilml import TEST_BOX


def run():
    w = pd.read_csv(config.M2CACHE / "wosis_topsoil.csv.gz")
    w = w[w["licence_class"].isin(["public_domain", "cc_by"])]
    w["in_box"] = w["lon"].between(*TEST_BOX["lon"]) & w["lat"].between(*TEST_BOX["lat"])
    features.prepare_global_layers()
    f = features.extract(w["lon"].to_numpy(), w["lat"].to_numpy(), with_soil=True, with_terrain=False)
    for k, v in f.items():
        w[k] = v
    out = {}
    pairs = {"ph": ("sg_ph", "ph"), "soc_pct": ("sg_soc", "soc_pct"), "sand": ("sg_sand", "sand"), "clay": ("sg_clay", "clay")}
    sgconv = {"sg_soc": lambda x: x / 10.0 * 1.0}      # features.extract divides dg/kg by 10 -> g/kg ; convert g/kg -> %
    for name, (sg, ob) in pairs.items():
        d = w[[sg, ob, "dm_aridity", "in_box", "country"]].dropna()
        d = d.copy()
        if sg == "sg_soc":
            d[sg] = d[sg] / 10.0          # g/kg -> %
        for tag, m in (("arid_global_dm_lt_10", d["dm_aridity"] < 10), ("semiarid_or_drier_dm_lt_30", d["dm_aridity"] < 30), ("test_box_dm_lt_30", d["in_box"] & (d["dm_aridity"] < 30)),
                       ("jordan", d["country"] == "Jordan")):
            x = d[m]
            if len(x) < 30:
                continue
            e = x[sg] - x[ob]
            out.setdefault(name, {})[tag] = dict(n=int(len(x)), bias=float(e.mean()), mae=float(e.abs().mean()), rmse=float(np.sqrt((e ** 2).mean())),
                                                 r2=float(1 - (e ** 2).sum() / ((x[ob] - x[ob].mean()) ** 2).sum()), obs_mean=float(x[ob].mean()), obs_sd=float(x[ob].std()),
                                                 rel_rmse=float(np.sqrt((e ** 2).mean()) / max(x[ob].mean(), 1e-6)))
    p = config.EVAL_DIR / "soilgrids_check.json"
    p.write_text(json.dumps(out, indent=2))
    print(json.dumps({k: {t: (v["n"], round(v["rmse"], 2), round(v["bias"], 2)) for t, v in d.items()} for k, d in out.items()}, indent=1))
    return out


if __name__ == "__main__":
    run()
