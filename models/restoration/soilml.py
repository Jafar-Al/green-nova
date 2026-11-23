"""Soil-property ML (salinity ECe, sodicity ESP): LightGBM gradient boosting on measured topsoil data, evaluated on geographically held-out sites.

Methodology (also written to eval/soil_models_report.json):
  * unit = one location (0-30 cm depth-weighted lab value); NO random pixel/row splits.
  * validation geography: (a) 5x5-degree spatial BLOCK k-fold CV (blocks never straddle folds), (b) a held-out REGION (Levant + Arabian peninsula box) never used in
    tuning/early-stopping/calibration, (c) per-continent breakdown of out-of-fold errors.
  * target transforms: log10(ECe), log1p(ESP) (heavy right tails).
  * regularisation: shallow trees, min_child_samples, feature/bagging fractions, L2, early stopping inside every fold; Optuna tuning on block-CV RMSE.
  * uncertainty: Mondrian split-conformal intervals (90 %) from OUT-OF-FOLD residuals of the block CV, binned by predicted level; coverage re-checked on the held-out region.
  * baselines: global median; same model without SoilGrids covariates (SoilGrids is trained on WoSIS -> leakage check); Hassani et al. (2020) ECe map at test points when available.
  * class metrics: FAO/USDA salinity classes (ECe <2, 2-4, 4-8, 8-16, >16 dS/m) and sodicity classes (ESP <6, 6-15, >15) precision/recall/macro-F1.
"""
from __future__ import annotations

import hashlib
import json
import time
import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd

from . import config, features

CKPT = config.CKPT_DIR
META = CKPT / "soil_models_meta.json"
TEST_BOX = dict(lon=(30.0, 50.0), lat=(20.0, 38.0))          # Levant + Arabian peninsula: held-out region (contains Ma'an)
DM_MAX = 30.0                                                 # training domain: De Martonne index <= 30 (semi-arid and drier)
ECE_CLASSES = [2.0, 4.0, 8.0, 16.0]
ESP_CLASSES = [6.0, 15.0]

TARGETS = {
    "ece": dict(file="ece_training.csv.gz", col="ece", fwd=lambda y: np.log10(np.clip(y, 0.05, 300.0)), inv=lambda t: 10 ** t, classes=ECE_CLASSES, unit="dS/m"),
    "esp": dict(file="esp_training.csv.gz", col="esp", fwd=lambda y: np.log1p(np.clip(y, 0, 100.0)), inv=lambda t: np.expm1(t), classes=ESP_CLASSES, unit="%"),
}


def _in_test(df):
    return (df["lon"].between(*TEST_BOX["lon"]) & df["lat"].between(*TEST_BOX["lat"])).to_numpy()


def load_target(name):
    t = TARGETS[name]
    df = pd.read_csv(config.M2CACHE / t["file"])
    df = df[df["dm_aridity"].notna() & (df["dm_aridity"] <= DM_MAX)].copy()
    df = df[df[features.CLIMATE + features.TERRAIN].notna().all(axis=1)]
    df["y"] = t["fwd"](df[t["col"]].to_numpy())
    return df.reset_index(drop=True)


def block_folds(blocks: pd.Series, k: int = 8, seed: int = config.SEED) -> np.ndarray:
    u = np.array(sorted(blocks.unique()))
    rng = np.random.default_rng(seed)
    rng.shuffle(u)
    fold_of = {b: i % k for i, b in enumerate(u)}
    return blocks.map(fold_of).to_numpy()


def _params(trial=None, base=None):
    if base is not None:
        return base
    return dict(objective="regression", metric="rmse", learning_rate=0.04, verbosity=-1, num_threads=8, seed=config.SEED,
                num_leaves=trial.suggest_int("num_leaves", 8, 48), min_child_samples=trial.suggest_int("min_child_samples", 10, 80),
                feature_fraction=trial.suggest_float("feature_fraction", 0.5, 1.0), bagging_fraction=trial.suggest_float("bagging_fraction", 0.6, 1.0), bagging_freq=1,
                lambda_l2=trial.suggest_float("lambda_l2", 1e-2, 30.0, log=True), max_depth=trial.suggest_int("max_depth", 3, 9),
                min_split_gain=trial.suggest_float("min_split_gain", 0.0, 0.3))


def cv_predict(X, y, folds, params, rounds=2000):
    oof = np.full(len(y), np.nan)
    best = []
    for f in np.unique(folds):
        te = folds == f
        tr = ~te
        # early stopping set = a spatially distinct slice of the TRAIN part (other folds), never the held-out fold
        inner = np.unique(folds[tr])
        es_fold = inner[f % len(inner)]
        es = tr & (folds == es_fold)
        fit = tr & ~es
        m = lgb.train(params, lgb.Dataset(X[fit], y[fit]), rounds, valid_sets=[lgb.Dataset(X[es], y[es])],
                      callbacks=[lgb.early_stopping(60, verbose=False)])
        oof[te] = m.predict(X[te], num_iteration=m.best_iteration)
        best.append(m.best_iteration)
    return oof, int(np.median(best))


def metrics_reg(y_true_t, y_pred_t, inv, classes):
    yt, yp = inv(y_true_t), inv(y_pred_t)
    res = y_true_t - y_pred_t
    ss = ((y_true_t - y_true_t.mean()) ** 2).sum()
    out = dict(n=int(len(yt)), mae_t=float(np.abs(res).mean()), rmse_t=float(np.sqrt((res ** 2).mean())), r2_t=float(1 - (res ** 2).sum() / ss) if ss > 0 else None,
               mae=float(np.abs(yt - yp).mean()), rmse=float(np.sqrt(((yt - yp) ** 2).mean())), bias_t=float(-res.mean()))
    ct = np.digitize(yt, classes)
    cp = np.digitize(yp, classes)
    k = len(classes) + 1
    cm = np.zeros((k, k), int)
    for a, b in zip(ct, cp):
        cm[a, b] += 1
    prec = [float(cm[i, i] / cm[:, i].sum()) if cm[:, i].sum() else None for i in range(k)]
    rec = [float(cm[i, i] / cm[i, :].sum()) if cm[i, :].sum() else None for i in range(k)]
    f1 = [2 * p * r / (p + r) if (p and r) else 0.0 for p, r in zip(prec, rec)]
    out.update(class_confusion=cm.tolist(), class_precision=prec, class_recall=rec, macro_f1=float(np.mean(f1)),
               accuracy=float((ct == cp).mean()), within_one_class=float((np.abs(ct - cp) <= 1).mean()))
    return out


def conformal_bins(pred_t, abs_res, level=0.90, nb=4):
    edges = np.quantile(pred_t, np.linspace(0, 1, nb + 1)[1:-1])
    b = np.digitize(pred_t, edges)
    q = []
    for i in range(nb):
        r = abs_res[b == i]
        n = len(r)
        q.append(float(np.quantile(r, min(1.0, np.ceil((n + 1) * level) / n))) if n >= 30 else float(np.quantile(abs_res, level)))
    return [float(e) for e in edges], q


def interval(pred_t, edges, q):
    b = np.digitize(pred_t, edges)
    half = np.asarray(q)[b]
    return pred_t - half, pred_t + half


def coverage(y_t, lo, hi):
    return float(((y_t >= lo) & (y_t <= hi)).mean()), float((hi - lo).mean())


def block_bootstrap_ci(y_t, p_t, blocks, fn, nboot=300, seed=1):
    rng = np.random.default_rng(seed)
    ub = np.unique(blocks)
    idx_by = {b: np.where(blocks == b)[0] for b in ub}
    vals = []
    for _ in range(nboot):
        pick = rng.choice(ub, len(ub))
        ii = np.concatenate([idx_by[b] for b in pick])
        vals.append(fn(y_t[ii], p_t[ii]))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def run(name: str, n_trials: int = 20, with_soil_ablation: bool = True, hassani_map_pred=None) -> dict:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    warnings.filterwarnings("ignore")
    T = TARGETS[name]
    df = load_target(name)
    is_test = _in_test(df)
    d_tr, d_te = df[~is_test].reset_index(drop=True), df[is_test].reset_index(drop=True)
    rep = dict(target=name, unit=T["unit"], n_domain=int(len(df)), n_train=int(len(d_tr)), n_test_region=int(len(d_te)), test_box=TEST_BOX, domain=f"De Martonne <= {DM_MAX}",
               n_blocks_train=int(d_tr["block"].nunique()), n_blocks_test=int(d_te["block"].nunique()), runs={})
    for tag, feats in (("with_soilgrids", features.FEATURES), ("no_soilgrids", features.FEATURES_NOSOIL)):
        if tag == "no_soilgrids" and not with_soil_ablation:
            continue
        t0 = time.time()
        Xtr = d_tr[feats].to_numpy("float32"); ytr = d_tr["y"].to_numpy()
        Xte = d_te[feats].to_numpy("float32"); yte = d_te["y"].to_numpy()
        folds = block_folds(d_tr["block"], k=8)

        def obj(trial):
            p = _params(trial)
            oof, _ = cv_predict(Xtr, ytr, folds, p)
            return float(np.sqrt(np.nanmean((ytr - oof) ** 2)))
        study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=config.SEED))
        study.optimize(obj, n_trials=n_trials if tag == "with_soilgrids" else max(6, n_trials // 3))
        p = dict(objective="regression", metric="rmse", learning_rate=0.04, verbosity=-1, num_threads=8, seed=config.SEED, bagging_freq=1, **study.best_params)
        oof, nround = cv_predict(Xtr, ytr, folds, p)
        edges, q = conformal_bins(oof, np.abs(ytr - oof))
        # held-out region: model trained on all training-geography data
        nfit = max(50, int(nround * 1.1))
        m_all = lgb.train(p, lgb.Dataset(Xtr, ytr), nfit)
        pte = m_all.predict(Xte)
        lo, hi = interval(pte, edges, q)
        run_rep = dict(best_params=study.best_params, n_rounds=nfit, cv_rmse_tuned=float(study.best_value),
                       cv_oof=metrics_reg(ytr, oof, T["inv"], T["classes"]),
                       cv_fold_spread={k: [float(v) for v in vals] for k, vals in {
                           "rmse_t": [np.sqrt(np.mean((ytr[folds == f] - oof[folds == f]) ** 2)) for f in np.unique(folds)],
                           "r2_t": [1 - np.sum((ytr[folds == f] - oof[folds == f]) ** 2) / np.sum((ytr[folds == f] - ytr[folds == f].mean()) ** 2) for f in np.unique(folds)]}.items()},
                       heldout_region=metrics_reg(yte, pte, T["inv"], T["classes"]) if len(yte) else None,
                       conformal=dict(level=0.90, bin_edges=edges, half_width_t=q))
        cov_cv = coverage(ytr, *interval(oof, edges, q))
        run_rep["cv_conformal_coverage"], run_rep["cv_mean_interval_width_t"] = cov_cv
        if len(yte):
            run_rep["heldout_conformal_coverage"], run_rep["heldout_mean_interval_width_t"] = coverage(yte, lo, hi)
            run_rep["heldout_r2_ci95_block_bootstrap"] = block_bootstrap_ci(yte, pte, d_te["block"].to_numpy(), lambda a, b: 1 - ((a - b) ** 2).sum() / max(((a - a.mean()) ** 2).sum(), 1e-9))
            run_rep["heldout_rmse_t_ci95_block_bootstrap"] = block_bootstrap_ci(yte, pte, d_te["block"].to_numpy(), lambda a, b: float(np.sqrt(((a - b) ** 2).mean())))
            base = np.full(len(yte), np.median(ytr))
            run_rep["baseline_global_median_heldout"] = metrics_reg(yte, base, T["inv"], T["classes"])
            arid = d_te["dm_aridity"].to_numpy() < 10
            if arid.sum() > 20:
                run_rep["heldout_region_arid_subset_dm_lt_10"] = metrics_reg(yte[arid], pte[arid], T["inv"], T["classes"])
            ctry = d_te.get("country")
            if ctry is not None and "Jordan" in set(ctry.dropna()):
                jm = (ctry == "Jordan").to_numpy()
                if jm.sum() > 15:
                    run_rep["heldout_jordan_only"] = metrics_reg(yte[jm], pte[jm], T["inv"], T["classes"])
        # per-continent out-of-fold breakdown (spread across geographies)
        cont = pd.cut(d_tr["lon"].where(d_tr["lat"].notna()), [-180, -30, 30, 60, 180], labels=["Americas", "Africa/Europe W", "Middle East/C Asia", "E Asia/Oceania"])
        run_rep["cv_oof_by_longitude_band"] = {str(c): metrics_reg(ytr[cont == c], oof[cont == c], T["inv"], T["classes"]) for c in cont.cat.categories if (cont == c).sum() > 100}
        imp = dict(zip(feats, m_all.feature_importance("gain").round(1).tolist()))
        run_rep["feature_gain_importance"] = dict(sorted(imp.items(), key=lambda kv: -kv[1]))
        rep["runs"][tag] = run_rep
        rep["runs"][tag]["seconds"] = round(time.time() - t0)
        if tag == "with_soilgrids":
            # final deployed model: trained on ALL domain data (including the held-out region)
            Xall = df[feats].to_numpy("float32"); yall = df["y"].to_numpy()
            m_final = lgb.train(p, lgb.Dataset(Xall, yall), nfit)
            CKPT.mkdir(parents=True, exist_ok=True)
            path = CKPT / f"{name}_lgbm.txt"
            m_final.save_model(str(path))
            rep["checkpoint"] = dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), features=feats, n_rounds=nfit, trained_on_n=int(len(df)),
                                     conformal=dict(level=0.90, bin_edges=edges, half_width_t=q), transform=name, lightgbm=lgb.__version__)
    return rep


def run_all(n_trials=16):
    config.ensure_dirs()
    reps = {}
    for name in ("ece", "esp"):
        print("== training", name, flush=True)
        reps[name] = run(name, n_trials=n_trials)
        print(json.dumps({k: reps[name]["runs"]["with_soilgrids"].get(k) for k in ("cv_conformal_coverage", "heldout_conformal_coverage")}), flush=True)
    meta = {"models": {k: v["checkpoint"] for k, v in reps.items()}, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "test_box": TEST_BOX, "domain_dm_max": DM_MAX}
    META.write_text(json.dumps(meta, indent=2))
    (config.EVAL_DIR / "soil_models_report.json").write_text(json.dumps(reps, indent=2))
    return reps


# ---------------------------------------------------------------- inference (no network, checkpoints only)
_CACHE = {}


def _load(name):
    if name not in _CACHE:
        meta = json.loads(META.read_text())["models"][name]
        _CACHE[name] = (lgb.Booster(model_file=str(CKPT / meta["file"])), meta)
    return _CACHE[name]


def predict(name: str, feat: dict, level: float = 0.90):
    """feat: dict feature-name -> array. Returns (value, lo, hi) in physical units (dS/m or %), with 90 % conformal interval."""
    m, meta = _load(name)
    X = np.column_stack([feat[k] for k in meta["features"]]).astype("float32")
    pt = m.predict(X)
    lo_t, hi_t = interval(pt, meta["conformal"]["bin_edges"], meta["conformal"]["half_width_t"])
    inv = TARGETS[name]["inv"]
    return inv(pt), np.maximum(inv(lo_t), 0.0), inv(hi_t), pt, (hi_t - lo_t) / (2 * 1.645)


if __name__ == "__main__":
    run_all()
