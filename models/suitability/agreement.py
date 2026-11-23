"""Agreement of a delivered full-region output with OBSERVED cultivation (WorldCover-2021 AND IO-LULC-2021 consensus label).

Adds `agreement_with_observed_cultivation` to summary.json and run_metadata.json (maps are not modified).
Run: python -m models.suitability.agreement --region jo-maan --out models/suitability/outputs/jo-maan
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio

from . import config, features as F, rules
from .infer import Model, Runtime


def compute(region_id: str, out_dir, n_neg_sample: int = 200_000, seed: int = 0) -> dict:
    out = Path(out_dir)
    rt = Runtime.get(region_id)
    with rasterio.open(out / "suitability.tif") as s:
        cls = s.read(1)
    if cls.shape != rt.mask.shape:
        raise ValueError("agreement table is defined for full-region outputs only")
    lab = np.asarray(rt.mm[rt.layers["label_cult"]])
    names = {"observed_cultivated": 1, "observed_not_cultivated": 0, "excluded_or_ambiguous_label": -1}
    table = {}
    for nm, v in names.items():
        m = rt.mask & (lab == v)
        n = int(m.sum())
        cnt = {str(k): int((cls[m] == k).sum()) for k in range(1, 6)}
        table[nm] = dict(cells=n, area_ha=n * config.HA_PER_CELL, cells_by_final_class=cnt,
                         share_by_final_class={k: round(c / max(n, 1), 4) for k, c in cnt.items()})
    # mean calibrated ML probability: all observed-cultivated cells vs a random sample of observed-not-cultivated cells
    model = Model.load()
    rng = np.random.default_rng(seed)
    pos = np.flatnonzero((rt.mask & (lab == 1)).ravel())
    neg = np.flatnonzero((rt.mask & (lab == 0)).ravel())
    neg = rng.choice(neg, min(n_neg_sample, len(neg)), replace=False)

    def predict(flat):
        r, c = np.divmod(flat, rt.mask.shape[1])
        lay = {}
        for n in model.features:
            if n == "awc_ptf":
                continue
            lay[n] = np.asarray(rt.mm[rt.layers[n]])[r, c].astype("float32") if False else None
        # read layer-by-layer (memmap fancy indexing per layer)
        for n in model.features:
            if n == "awc_ptf":
                continue
            a = rt.mm[rt.layers[n]]
            v = np.asarray(a[r, c], dtype="float32")
            lay[n] = np.where(np.isfinite(v), v, np.nanmedian(v) if np.isfinite(v).any() else 0.0).astype("float32")
        lay["awc_ptf"] = rules.awc_cm_per_m(lay["sand_0_30"], lay["clay_0_30"], lay["soc_0_30"], lay["cfvo_0_60"])
        X = np.stack([lay[n] for n in model.features], axis=1)
        return model.calibrated_members(X).mean(0), lay

    (pp, lay_pos), (pn, _) = predict(pos), predict(neg)
    # classes WITHOUT the observed-cultivation override (rules, then rules+ML) for the observed-cultivated cells
    ev = rules.evaluate({**lay_pos, "restriction_code": np.zeros(len(pos), "uint8")})
    from . import fusion
    fz, _ = fusion.fuse(ev["rule_class_nonrestricted"], ev["sev"], np.zeros(len(pos), "uint8"), pp, np.zeros(len(pos), bool))
    table["observed_cultivated_without_override"] = dict(
        rule_only_share_by_class={str(k): round(float((ev["rule_class_nonrestricted"] == k).mean()), 4) for k in range(1, 5)},
        rules_plus_ml_share_by_class={str(k): round(float((fz == k).mean()), 4) for k in range(1, 5)},
        note="classes these cells would get if the observed-cultivation override (class<=2) were switched off; this is the non-circular check")
    table["mean_ml_cultivation_probability"] = dict(
        observed_cultivated=round(float(pp.mean()), 4), observed_not_cultivated_sample=round(float(pn.mean()), 4),
        median_observed_cultivated=round(float(np.median(pp)), 4), median_observed_not_cultivated_sample=round(float(np.median(pn)), 4),
        n_cultivated=int(len(pp)), n_not_cultivated_sample=int(len(pn)),
        note="in-sample for Jordan-wide training (Ma'an cells were in the final training set); the leave-governorate-out numbers are the held-out evidence")
    table["note_on_circularity"] = ("The delivered map caps observed-cultivated cells at class 2 BY DESIGN (observed override), so the high class-2 share of "
                                    "observed_cultivated is partly by construction; see observed_cultivated_without_override for the rule/ML-only view.")
    cult = table["observed_cultivated"]["cells_by_final_class"]
    tot = max(table["observed_cultivated"]["cells"], 1)
    table["reading"] = (f"{(cult['1'] + cult['2']) / tot:.1%} of observed-cultivated cells fall in classes 1-2, "
                        f"{(cult['3'] + cult['4']) / tot:.1%} in classes 3-4, {cult['5'] / tot:.1%} in class 5. Labels: WorldCover-2021 AND "
                        f"IO-LULC-2021 cropland agreement at 100 m (land-cover products, not field survey). Class 3/4 membership of observed "
                        f"farms is a limitation: the rules use 1-4 km climate and 1:500,000 soil units and are conservative at farm scale; "
                        f"the 10 ha minimum-mapping-unit sieve also removes small cultivated patches.")
    for fn, key in (("summary.json", "agreement_with_observed_cultivation"), ("run_metadata.json", "agreement_with_observed_cultivation")):
        p = out / fn
        d = json.loads(p.read_text())
        d[key] = table
        p.write_text(json.dumps(d, indent=1))
    return table


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="jo-maan")
    ap.add_argument("--out", default=str(config.OUT_DIR / "jo-maan"))
    a = ap.parse_args()
    print(json.dumps(compute(a.region, a.out), indent=1))
