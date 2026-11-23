"""Evaluation of the restoration hybrid beyond the soil-model metrics (those live in soil_models_report.json).

E2  pipeline consistency on held-out geography: measured WoSIS topsoil (ECe, pH, sand, clay, SOC) -> engine feasibility ("observed-state") vs the same
    profiles described only by covariates (held-out-region ECe model + SoilGrids) -> engine feasibility ("predicted-state"). Climate/terrain/ESP/CEC held fixed
    at Ma'an-median values so that only SOIL prediction error is propagated.  This measures CONSISTENCY, not real-world restoration success.
E3  sensitivity analyses on 20k random Ma'an cells (water allocation, class-cut thresholds, RY threshold, ECe uncertainty, leaching/gypsum assumptions).
E5  ETo cross-check: Hargreaves (FAO56 eq. 52) vs TerraClimate Penman-Monteith ET0 over the region.
Run: python -m models.restoration.eval.evaluate
"""
from __future__ import annotations

import json
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

from .. import config, engine, features, infer, soilml, units


def _fixed_units(n, ece, ph, sand, clay, soc, esp, med):
    one = np.ones(n, "float32")
    clim = dict(ppt_m=np.repeat(med["ppt_m"][:, None], n, 1), eto_m=np.repeat(med["eto_m"][:, None], n, 1), p67=med["p67"] * one, tmin_cold=med["tmin_cold"] * one)
    v = dict(ece=ece, ece_lsd=np.full(n, 0.05, "float32"), esp=esp, esp_sd=np.full(n, 2.0, "float32"), ph=ph, soc_pct=soc, sand=sand, clay=clay, cfvo=med["cfvo"] * one, bd=med["bd"] * one,
             cec=med["cec"] * one, depth_cm=200 * one, slope_deg=1.0 * one)
    return v, clim


def holdout_model(name):
    """Retrain with the tuned params on everything OUTSIDE the held-out region (same recipe as soilml.run) and return a predictor."""
    rep = json.loads((config.EVAL_DIR / "soil_models_report.json").read_text())[name]["runs"]["with_soilgrids"]
    T = soilml.TARGETS[name]
    df = soilml.load_target(name)
    t = soilml._in_test(df)
    p = dict(objective="regression", metric="rmse", learning_rate=0.04, verbosity=-1, num_threads=8, seed=config.SEED, bagging_freq=1, **rep["best_params"])
    m = lgb.train(p, lgb.Dataset(df[~t][features.FEATURES].to_numpy("float32"), df[~t]["y"].to_numpy()), rep["n_rounds"])
    conf = rep["conformal"]
    return m, conf, T


def e2_consistency(rt, n_max=400):
    t0 = time.time()
    w = pd.read_csv(config.M2CACHE / "wosis_topsoil.csv.gz")
    w = w[w["licence_class"].isin(["public_domain", "cc_by"])]
    w = w[w["lon"].between(*soilml.TEST_BOX["lon"]) & w["lat"].between(*soilml.TEST_BOX["lat"])]
    w = w.dropna(subset=["ece", "ph", "sand", "clay", "soc_pct"]).reset_index(drop=True)
    f = features.extract(w["lon"].to_numpy(), w["lat"].to_numpy(), with_soil=True)
    for k, v in f.items():
        w[k] = v
    w = w[w[features.FEATURES].notna().all(axis=1) & (w["dm_aridity"] < 30)].reset_index(drop=True)
    n = len(w)
    m, conf, T = holdout_model("ece")
    pt = m.predict(w[features.FEATURES].to_numpy("float32"))
    lo_t, hi_t = soilml.interval(pt, conf["bin_edges"], conf["half_width_t"])
    ece_pred = T["inv"](pt)
    lsd = (hi_t - lo_t) / (2 * 1.645)
    L = rt["layers"]
    mk = rt["mask"]
    med = dict(cfvo=float(np.nanmedian(L["cfvo"][mk])), bd=float(np.nanmedian(L["bd"][mk])), cec=float(np.nanmedian(L["cec"][mk])),
               ppt_m=np.nanmedian(rt["climate"]["ppt_m"].reshape(12, -1), 1), eto_m=np.nanmedian(rt["climate"]["eto_m"].reshape(12, -1), 1),
               p67=float(np.nanmedian(rt["climate"]["p67"])), tmin_cold=float(np.nanmedian(rt["climate"]["tmin_cold"])))
    esp = np.full(n, 8.0, "float32")
    # observed-state: measured soil; predicted-state: ML ECe + SoilGrids with calibrated uncertainties
    vo, co = _fixed_units(n, w["ece"].to_numpy("float32"), w["ph"].to_numpy("float32"), w["sand"].to_numpy("float32"), w["clay"].to_numpy("float32"), w["soc_pct"].to_numpy("float32"), esp, med)
    vp, cp = _fixed_units(n, ece_pred.astype("float32"), w["sg_ph"].to_numpy("float32"), w["sg_sand"].to_numpy("float32"), w["sg_clay"].to_numpy("float32"), (w["sg_soc"].to_numpy("float32") / 10.0), esp, med)
    vp["ece_lsd"] = lsd.astype("float32")
    Uo = units.units_from_values(vo, co)
    Up = units.units_from_values(vp, cp)
    Uo.ece_lsd[:] = 0.05
    Eo = engine.evaluate(Uo, J=16, I=4, seed=11)
    Ep = engine.evaluate(Up, J=16, I=4, seed=12)
    so, sp, lo, hi = Eo["score"], Ep["score"], Ep["lo"], Ep["hi"]
    co_ = engine.feasibility_class(so, config.FEAS_CUTS)
    cp_ = engine.feasibility_class(sp, config.FEAS_CUTS)
    k = 4
    cm = np.zeros((k, k), int)
    for a, b in zip(co_ - 1, cp_ - 1):
        cm[a, b] += 1
    prec = [float(cm[i, i] / cm[:, i].sum()) if cm[:, i].sum() else None for i in range(k)]
    rec = [float(cm[i, i] / cm[i, :].sum()) if cm[i, :].sum() else None for i in range(k)]
    inside = float(((so >= lo - 1e-9) & (so <= hi + 1e-9)).mean())
    from scipy.stats import spearmanr
    # reliability: bin predicted score; compare with mean observed-state score
    bins = np.linspace(0, 1, 6)
    rel = []
    for a, b in zip(bins[:-1], bins[1:]):
        mm = (sp >= a) & (sp < b + (1e-9 if b == 1 else 0))
        if mm.sum() >= 5:
            rel.append(dict(bin=[float(a), float(b)], n=int(mm.sum()), mean_pred=float(sp[mm].mean()), mean_obs_state=float(so[mm].mean())))
    out = dict(n_profiles=int(n), test_region=soilml.TEST_BOX, note="climate, ESP, CEC, CF, depth, slope fixed at Ma'an-median/assumed values; only ECe/pH/sand/clay/SOC vary",
               observed_state_class_counts={config.FEAS_LABELS[i + 1]: int((co_ == i + 1).sum()) for i in range(4)}, predicted_state_class_counts={config.FEAS_LABELS[i + 1]: int((cp_ == i + 1).sum()) for i in range(4)},
               confusion_rows_observed_cols_predicted=cm.tolist(), class_precision=prec, class_recall=rec, accuracy=float(np.trace(cm) / cm.sum()), within_one_class=float((np.abs(co_.astype(int) - cp_.astype(int)) <= 1).mean()),
               mean_abs_score_error=float(np.abs(so - sp).mean()), spearman_score=float(spearmanr(so, sp)[0]), interval_covers_observed_state_score=inside, mean_interval_width=float((hi - lo).mean()),
               reliability=rel, seconds=round(time.time() - t0))
    return out


def e3_sensitivity(rt, n=20000, seed=5):
    g, L = rt["grid"], rt["layers"]
    idx = np.where(rt["mask"] & np.isfinite(L["ph"]))
    rng = np.random.default_rng(seed)
    sel = rng.choice(len(idx[0]), n, replace=False)
    rr, cc = idx[0][sel], idx[1][sel]
    lon, lat = units.cell_lonlat(g, rr, cc)
    clim = units.interp_climate(rt["climate"], lon, lat)
    v = {k: a[rr, cc] for k, a in L.items()}

    def run(U=None, **kw):
        U = U or units.units_from_values(v, clim)
        return engine.evaluate(U, J=16, I=4, seed=7, **kw)
    base = run()
    s0 = base["score"]
    c0 = engine.feasibility_class(s0, config.FEAS_CUTS)
    from scipy.stats import spearmanr

    def rec(name, E, cuts=None):
        s = E["score"]
        c = engine.feasibility_class(s, cuts or config.FEAS_CUTS)
        return dict(name=name, mean_score=float(s.mean()), mean_shift=float((s - s0).mean()), spearman_vs_base=float(spearmanr(s0, s)[0]), class_flip_rate=float((c != c0).mean()),
                    class_share={config.FEAS_LABELS[i]: float((c == i).mean()) for i in (1, 2, 3, 4)})
    rows = [rec("baseline (water 8000 m3/ha/yr)", base)]
    for wc in (3000.0, 5000.0, 12000.0, 20000.0):
        rows.append(rec(f"water allocation {int(wc)} m3/ha/yr", run(water_cap=wc)))
    for nm, cuts in (("class cuts -0.1", {k: x - 0.1 for k, x in config.FEAS_CUTS.items()}), ("class cuts +0.1", {k: x + 0.1 for k, x in config.FEAS_CUTS.items()})):
        rows.append(rec(nm, base, cuts))
    P = engine.sample_params(16, np.random.default_rng(7))
    for thr in (0.5, 0.7):
        Q = {k: np.copy(x) for k, x in P.items()}
        Q["ry_thr"][:] = thr
        rows.append(rec(f"RY success threshold {thr}", run(params=Q)))
    U = units.units_from_values(v, clim)
    U2 = units.units_from_values(v, clim)
    U2.ece_lsd = U2.ece_lsd * 0.5
    rows.append(rec("ECe uncertainty x0.5", run(U=U2)))
    U3 = units.units_from_values(v, clim)
    U3.ece = U3.ece * 2.0
    rows.append(rec("ECe central value x2", run(U=U3)))
    U4 = units.units_from_values(v, clim)
    U4.esp = np.minimum(U4.esp * 2.0, 100.0)
    rows.append(rec("ESP central value x2", run(U=U4)))
    Q = {k: np.copy(x) for k, x in P.items()}
    Q["r_cap"][:] = 0.7
    rows.append(rec("max leaching depth ratio 0.7 (less water for reclamation)", run(params=Q)))
    Q = {k: np.copy(x) for k, x in P.items()}
    Q["gyp_cap"][:] = 8.0
    rows.append(rec("gypsum cap 8 t/ha", run(params=Q)))
    Q = {k: np.copy(x) for k, x in P.items()}
    Q["eto_f"][:] = 1.2
    rows.append(rec("ETo +20 %", run(params=Q)))
    return dict(n_cells=n, rows=rows)


def e5_eto(rt):
    C = rt["climate"]
    pm, hg = C["eto_pm_annual"], C["eto_hg_annual"]
    ok = np.isfinite(pm) & np.isfinite(hg)
    r = hg[ok] / pm[ok]
    return dict(n_cells=int(ok.sum()), hargreaves_over_penman_monteith=dict(mean=float(r.mean()), p5=float(np.percentile(r, 5)), p95=float(np.percentile(r, 95))),
                pm_annual_mm=dict(median=float(np.median(pm[ok])), p5=float(np.percentile(pm[ok], 5)), p95=float(np.percentile(pm[ok], 95))))


def main():
    rt = infer.load_runtime("jo-maan")
    out = dict(created=time.strftime("%Y-%m-%dT%H:%M:%S"), model_version=config.MODEL_VERSION)
    out["E5_eto_crosscheck"] = e5_eto(rt)
    print("E5 done", flush=True)
    out["E2_pipeline_consistency_heldout_region"] = e2_consistency(rt)
    print("E2 done", flush=True)
    (config.EVAL_DIR / "restoration_eval.json").write_text(json.dumps(out, indent=1))
    out["E3_sensitivity"] = e3_sensitivity(rt)
    (config.EVAL_DIR / "restoration_eval.json").write_text(json.dumps(out, indent=1))
    print("E3 done", flush=True)


if __name__ == "__main__":
    main()
