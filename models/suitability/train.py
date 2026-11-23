"""Spatially-validated training of the cultivation-likelihood model (LightGBM) + baselines.

  python -m models.suitability.train prep    # cache rule-engine results for all Jordan cells
  python -m models.suitability.train loro    # leave-governorate-group-out evaluation (nested tuning) -> reports/
  python -m models.suitability.train final   # deployable ensemble + isotonic calibrator -> checkpoints/

Target: OBSERVED cultivation (labels.py). The model never sees vegetation indices or land cover (INTRINSIC features only),
so it estimates how likely land with these terrain/soil/climate conditions is to be cultivated in Jordan today.
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
import time
import warnings

import lightgbm as lgb
import numpy as np
import optuna
import rasterio
from scipy import ndimage as ndi
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

from . import config, features as F, fusion, rules
from .regions import jordan_grid, load_regions

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)
STACK = config.M1CACHE / "stack"
CACHE = config.M1CACHE / "features"
NJOBS = 10
GROUPS = {
    "maan": ["jo-maan"],
    "karak_tafilah": ["jo-karak", "jo-tafilah"],
    "mafraq": ["jo-mafraq"],
    "north_irbid_ajloun_jerash": ["jo-irbid", "jo-ajloun", "jo-jerash"],
    "central_balqa_madaba_amman": ["jo-balqa", "jo-madaba", "jo-amman"],
    "zarqa_aqaba": ["jo-zarqa", "jo-aqaba"],
}
BUFFER_M = 10_000
NPOS, NNEG = 150_000, 450_000


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ------------------------------------------------------------------ metrics
def ece(y, p, bins=15):
    edges = np.linspace(0, 1, bins + 1)
    ids = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    tot, e = len(y), 0.0
    for b in range(bins):
        m = ids == b
        if m.any():
            e += m.sum() / tot * abs(y[m].mean() - p[m].mean())
    return float(e)


def reliability(y, p, bins=10):
    q = np.quantile(p, np.linspace(0, 1, bins + 1))
    q = np.unique(q)
    ids = np.clip(np.digitize(p, q[1:-1]), 0, len(q) - 2)
    return [dict(p_mean=float(p[ids == b].mean()), y_rate=float(y[ids == b].mean()), n=int((ids == b).sum()))
            for b in range(len(q) - 1) if (ids == b).any()]


def prob_metrics(y, p):
    y = y.astype(int)
    if y.min() == y.max():
        return dict(n=int(len(y)), prevalence=float(y.mean()), note="single class")
    pc = np.clip(p, 1e-6, 1 - 1e-6)
    return dict(n=int(len(y)), prevalence=float(y.mean()), auc=float(roc_auc_score(y, p)),
                ap=float(average_precision_score(y, p)), brier=float(brier_score_loss(y, pc)),
                logloss=float(log_loss(y, pc)), ece=ece(y, pc))


def block_bootstrap(y, p, blocks, n=100, seed=0, cap=400_000):
    rng = np.random.default_rng(seed)
    if len(y) > cap:
        s = rng.choice(len(y), cap, replace=False); y, p, blocks = y[s], p[s], blocks[s]
    ub, inv = np.unique(blocks, return_inverse=True)
    order = np.argsort(inv)
    starts = np.searchsorted(inv[order], np.arange(len(ub)))
    ends = np.append(starts[1:], len(inv))
    aucs, aps = [], []
    for _ in range(n):
        pick = rng.integers(0, len(ub), len(ub))
        ii = np.concatenate([order[starts[b]:ends[b]] for b in pick])
        if y[ii].min() == y[ii].max():
            continue
        aucs.append(roc_auc_score(y[ii], p[ii])); aps.append(average_precision_score(y[ii], p[ii]))
    q = lambda a: [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))] if a else None
    return dict(auc_ci95=q(aucs), ap_ci95=q(aps), n_boot=len(aucs))


# ------------------------------------------------------------------ data
class Data:
    pass


def prepare(with_rules=True):
    d = Data()
    grid = jordan_grid()
    d.grid = grid
    adm = F.read_layer_path(config.M1CACHE / "adm1_id.tif")
    d.adm = adm
    d.idx = np.flatnonzero(adm.ravel() > 0)
    d.gov = adm.ravel()[d.idx]
    lab = F.read_layer("label_cult").ravel()
    d.lab = lab[d.idx].astype("int8")
    d.newc = F.read_layer("label_new_crop").ravel()[d.idx] == 1
    d.blocks = F.block_ids(d.idx, grid.width, 300)
    reg = load_regions()
    d.name_to_idx = dict(zip(reg.region_id, reg.adm1_index))
    log("loading intrinsic features", len(d.idx), "cells")
    d.X = F.load_cells(F.INTRINSIC, d.idx)
    d.fnames = list(F.INTRINSIC)
    if with_rules:
        d.rule = rule_cache(d)
    return d


def rule_cache(d):
    p = CACHE / "rules_cache.npz"
    if p.exists():
        z = np.load(p)
        return dict(index=z["index"], cls=z["cls"], sev=z["sev"], restr=z["restr"])
    CACHE.mkdir(parents=True, exist_ok=True)
    idx = d.idx
    restr = F.read_layer("restriction_code").ravel()[idx]
    n = len(idx)
    index = np.empty(n, "float32"); cls = np.empty(n, "uint8"); sev = np.empty((len(rules.FACTORS), n), "uint8")
    step = 1_000_000
    for a in range(0, n, step):
        b = min(a + step, n)
        cov = {}
        sub = idx[a:b]
        for k in F.RULE_INPUTS:
            cov[k] = _layer_cache(k)[sub]
        ev = rules.evaluate({**cov, "restriction_code": np.zeros(b - a, "uint8")})
        index[a:b] = ev["index"]; cls[a:b] = ev["rule_class_nonrestricted"]; sev[:, a:b] = ev["sev"]
        log("rules", b, "/", n)
    np.savez_compressed(p, index=index, cls=cls, sev=sev, restr=restr)
    return dict(index=index, cls=cls, sev=sev, restr=restr)


_LC = {}


def _layer_cache(k):
    if k not in _LC:
        _LC[k] = F.read_layer(k).ravel()
    return _LC[k]


# ------------------------------------------------------------------ model helpers
DEFAULT = dict(objective="binary", learning_rate=0.06, num_leaves=63, min_data_in_leaf=1000, feature_fraction=0.8,
               bagging_fraction=0.8, bagging_freq=1, lambda_l2=10.0, max_bin=127, verbose=-1, num_threads=NJOBS, seed=1)


def sample_train(rows, y, rng, npos=NPOS, nneg=NNEG):
    pos = rows[y[rows] == 1]; neg = rows[y[rows] == 0]
    if len(pos) > npos: pos = rng.choice(pos, npos, replace=False)
    if len(neg) > nneg: neg = rng.choice(neg, nneg, replace=False)
    return np.concatenate([pos, neg])


def fit(X, y, tr, va, params, rounds=600, names=None):
    dtr = lgb.Dataset(X[tr], y[tr], feature_name=names, free_raw_data=True)
    dva = lgb.Dataset(X[va], y[va], reference=dtr)
    b = lgb.train(params, dtr, rounds, valid_sets=[dva], callbacks=[lgb.early_stopping(40, verbose=False)])
    return b


def inner_cv(X, y, rows, blocks, params, k=3, seed=0, rounds=600, names=None, val_cap=300_000):
    """Spatial-block k-fold on `rows`. Returns models, OOF (y, p_raw, blocks) at natural prevalence, mean AP."""
    rng = np.random.default_rng(seed)
    folds = F.assign_folds(blocks[rows], k, seed)
    models, oy, op, ob, aps, its = [], [], [], [], [], []
    for f in range(k):
        trn, val = rows[folds != f], rows[folds == f]
        if len(val) > val_cap: val = rng.choice(val, val_cap, replace=False)
        tr = sample_train(trn, y, rng)
        b = fit(X, y, tr, val, params, rounds, names)
        p = b.predict(X[val], num_iteration=b.best_iteration)
        models.append(b); oy.append(y[val]); op.append(p); ob.append(blocks[val]); its.append(b.best_iteration)
        aps.append(average_precision_score(y[val], p))
    return models, np.concatenate(oy), np.concatenate(op), np.concatenate(ob), float(np.mean(aps)), its


def tune(X, y, rows, blocks, n_trials, names, seed=0, k=3):
    def obj(trial):
        pr = dict(DEFAULT)
        pr.update(num_leaves=trial.suggest_int("num_leaves", 15, 127, log=True),
                  min_data_in_leaf=trial.suggest_int("min_data_in_leaf", 200, 5000, log=True),
                  feature_fraction=trial.suggest_float("feature_fraction", 0.5, 1.0),
                  bagging_fraction=trial.suggest_float("bagging_fraction", 0.5, 1.0),
                  lambda_l2=trial.suggest_float("lambda_l2", 1.0, 100.0, log=True),
                  learning_rate=0.08)
        _, _, _, _, ap, _ = inner_cv(X, y, rows, blocks, pr, k=k, seed=seed, rounds=300, names=names)
        return ap
    st = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
    st.optimize(obj, n_trials=n_trials)
    pr = dict(DEFAULT); pr.update(st.best_params); pr["learning_rate"] = 0.05
    return pr, st.best_value


def iso_fit(y, p):
    ir = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    ir.fit(p, y)
    return ir


def ens_predict(models, X):
    return np.mean([m.predict(X, num_iteration=m.best_iteration) for m in models], axis=0)


def class_table(cls, lab):
    """cultivated share and counts by class on labelled cells."""
    out = {}
    for k in range(1, 6):
        m = cls == k
        out[str(k)] = dict(cells=int(m.sum()), cultivated_share=float((lab[m] == 1).mean()) if m.any() else None,
                           pos_cells=int((lab[m] == 1).sum()))
    return out


# ------------------------------------------------------------------ LORO
def loro(n_trials=8):
    d = prepare()
    y = (d.lab == 1).astype("int8")
    res = {}
    grid = d.grid
    import os
    for gname, members in list(GROUPS.items())[: int(os.environ.get('M1_LORO_GROUPS', '3'))]:
        t0 = time.time()
        gi = [int(d.name_to_idx[m]) for m in members]
        in_g = np.isin(d.gov, gi)
        test = np.flatnonzero(in_g & (d.lab >= 0))
        # spatial buffer around the held-out group
        gmask = np.isin(d.adm, gi)
        dist = ndi.distance_transform_edt(~gmask, sampling=config.RES).ravel()[d.idx]
        pool = np.flatnonzero((~in_g) & (dist > BUFFER_M) & (d.lab >= 0))
        log(gname, "test", len(test), "pos", int(y[test].sum()), "| pool", len(pool), "pos", int(y[pool].sum()))
        if y[test].sum() < 50:
            res[gname] = dict(note="too few positives", test_cells=int(len(test)), test_pos=int(y[test].sum()))
            continue
        best, ap_in = tune(d.X, y, pool, d.blocks, n_trials, d.fnames, seed=7)
        models, oy, op, _, ap_cv, its = inner_cv(d.X, y, pool, d.blocks, best, k=3, seed=11, names=d.fnames)
        iso = iso_fit(oy, op)
        p_raw = ens_predict(models, d.X[test]); p_cal = iso.predict(p_raw)
        # baselines
        rule_idx = d.rule["index"][test]
        clim = [d.fnames.index(n) for n in F.CLIMATE_ONLY]
        bm, _, _, _, _, _ = inner_cv(d.X[:, clim], y, pool, d.blocks, DEFAULT, k=3, seed=11, names=F.CLIMATE_ONLY)
        p_clim = ens_predict(bm, d.X[test][:, clim])
        r = dict(test_cells=int(len(test)), test_pos=int(y[test].sum()), train_cells=int(len(pool)), train_pos=int(y[pool].sum()),
                 best_params={k: (float(v) if isinstance(v, float) else v) for k, v in best.items() if k in
                              ("num_leaves", "min_data_in_leaf", "feature_fraction", "bagging_fraction", "lambda_l2")},
                 inner_cv_ap=ap_cv, best_iters=its)
        r["gbm_calibrated"] = prob_metrics(y[test], p_cal)
        r["gbm_raw"] = prob_metrics(y[test], p_raw)
        r["gbm_calibrated"].update(block_bootstrap(y[test], p_cal, d.blocks[test]))
        r["baseline_rule_index"] = prob_metrics(y[test], rule_idx)
        r["baseline_rule_index"].update(block_bootstrap(y[test], rule_idx, d.blocks[test]))
        r["baseline_climate_only_gbm"] = prob_metrics(y[test], p_clim)
        r["reliability"] = reliability(y[test], p_cal)
        # fusion on test cells
        ev_sev = d.rule["sev"][:, test]
        rule_cls = d.rule["cls"][test]
        zero = np.zeros(len(test), "uint8")
        cultobs = (d.lab[test] == 1)
        fused, reason = fusion.fuse(rule_cls, ev_sev, zero, p_cal, np.zeros(len(test), bool))   # no observed override in the test
        r["classes_rule_only"] = class_table(rule_cls, d.lab[test])
        r["classes_fused_no_obs_override"] = class_table(fused, d.lab[test])
        r["fusion_reason_counts"] = {str(k): int((reason == k).sum()) for k in range(5)}
        # temporal hold-out: new cultivation 2023 vs stable non-cultivated
        nm = d.newc[test]; stable_neg = (d.lab[test] == 0) & ~nm
        if nm.sum() >= 100:
            sel = nm | stable_neg
            r["temporal_new_crop_2023"] = dict(new_cells=int(nm.sum()),
                                               **prob_metrics(nm[sel].astype(int), p_cal[sel]),
                                               rule_index_auc=float(roc_auc_score(nm[sel], rule_idx[sel])))
        res[gname] = r
        log(gname, "AUC gbm %.3f rule %.3f clim %.3f | AP gbm %.3f (prev %.3f) | ECE %.3f | %.0fs" % (
            r["gbm_calibrated"]["auc"], r["baseline_rule_index"]["auc"], r["baseline_climate_only_gbm"]["auc"],
            r["gbm_calibrated"]["ap"], r["gbm_calibrated"]["prevalence"], r["gbm_calibrated"]["ece"], time.time() - t0))
        config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
        (config.REPORT_DIR / "loro_results.json").write_text(json.dumps(res, indent=1))
    return res


# ------------------------------------------------------------------ final fit
def final(n_trials=10, k=5):
    d = prepare()
    y = (d.lab == 1).astype("int8")
    rows = np.flatnonzero(d.lab >= 0)
    log("final fit on", len(rows), "cells; pos", int(y[rows].sum()))
    best, ap_in = tune(d.X, y, rows, d.blocks, n_trials, d.fnames, seed=3, k=3)
    models, oy, op, ob, ap_cv, its = inner_cv(d.X, y, rows, d.blocks, best, k=k, seed=5, names=d.fnames)
    iso = iso_fit(oy, op)
    pc = iso.predict(op)
    # pooled spatial-CV report of the deployable pipeline (OOF; calibrator fit on the same OOF => report raw too)
    rep = dict(oof_raw=prob_metrics(oy, op), oof_calibrated_in_sample=prob_metrics(oy, pc), tuned_ap=ap_in, folds=k,
               best_iters=its, params={kk: (float(v) if isinstance(v, float) else v) for kk, v in best.items()
                                         if kk not in ("verbose", "num_threads")})
    imp = np.mean([m.feature_importance("gain") for m in models], axis=0)
    rep["feature_importance_gain"] = {n: float(v) for n, v in sorted(zip(d.fnames, imp), key=lambda t: -t[1])}
    # thresholds used by fusion (documented): calibrated probability levels
    rep["fusion_thresholds"] = dict(P_HI=fusion.P_HI, P_LO=fusion.P_LO)
    rep["calibrated_precision_at_P_HI"] = float(oy[pc >= fusion.P_HI].mean()) if (pc >= fusion.P_HI).any() else None
    rep["calibrated_rate_below_P_LO"] = float(oy[pc <= fusion.P_LO].mean()) if (pc <= fusion.P_LO).any() else None
    config.CKPT_DIR.mkdir(parents=True, exist_ok=True)
    ck = dict(model_version="m1-0.1.0", features=d.fnames, boosters=[m.model_to_string(num_iteration=m.best_iteration) for m in models],
              iso_x=iso.X_thresholds_.astype("float64"), iso_y=iso.y_thresholds_.astype("float64"),
              fusion=dict(P_HI=fusion.P_HI, P_LO=fusion.P_LO), trained_on="Jordan 100 m grid; observed-cultivation labels (WorldCover 2021 + IO LULC 2021)",
              created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), n_train_cells=int(len(rows)), n_pos=int(y[rows].sum()),
              sklearn_iso=None)
    path = config.CKPT_DIR / "model1_suitability_v0.1.pkl"
    with open(path, "wb") as f:
        pickle.dump(ck, f, protocol=4)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    rep["checkpoint"] = dict(file=path.name, sha256=sha, bytes=path.stat().st_size)
    (config.REPORT_DIR / "final_training.json").write_text(json.dumps(rep, indent=1))
    log("checkpoint", path.name, sha, path.stat().st_size)
    return rep


if __name__ == "__main__":
    cmd = sys.argv[1]
    config.ensure_dirs()
    if cmd == "prep":
        prepare()
    elif cmd == "loro":
        loro(int(sys.argv[2]) if len(sys.argv) > 2 else 8)
    elif cmd == "final":
        final(int(sys.argv[2]) if len(sys.argv) > 2 else 10)
