"""Assemble CONTRACT.md Model-2 polygon properties from engine output + unit state.  Nothing here is templated prose about "the land in general": every
number in a limiting factor / intervention / scenario is computed per unit; only the sentence frames are fixed."""
from __future__ import annotations

import numpy as np

from . import config, engine, erosion, hydro
from .knowledge import crops as K
from .knowledge.interventions import INTERVENTIONS
from .knowledge.sources import SOURCES

BARLEY = K.CROPS["barley"]
SCEN = engine.SCENARIOS


def _r(x, nd=2):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def _interval90(v, lsd, log=True):
    if log:
        return [_r(v * 10 ** (-1.645 * lsd)), _r(v * 10 ** (1.645 * lsd))]
    return [_r(v - 1.645 * lsd), _r(v + 1.645 * lsd)]


def limiting_factors(U: engine.Units, i: int, ctx: dict) -> list:
    """Deterministic (central-state) limiting factors for unit i, severity = 1 - relative yield attributable to that factor for the reference crop (barley)."""
    c = BARLEY
    out = []
    ece, esp, ph, soc = float(U.ece[i]), float(U.esp[i]), float(U.ph[i]), float(U.soc[i])
    sand, clay, cf, depth, slope = float(U.sand[i]), float(U.clay[i]), float(U.cf[i]), float(U.depth[i]), float(U.slope[i])
    one = np.array([1.0])

    def add(factor, sev, rev, ev, detail):
        if sev >= 0.10:
            out.append(dict(factor=factor, severity=_r(min(1.0, sev), 2), reversibility=rev, evidence=ev, detail=detail))

    if U.restricted[i]:
        add("restriction", 1.0, "irreversible", "expert_rule", "Model 1 class 5: legal/environmental restriction. Restoration potential is not assessed; the restriction itself is the limiting factor.")
    s_sal = 1 - float(K.rel_yield_salinity(c, np.array([ece]))[0])
    rev = ("irreversible" if (ece >= 30 or U.salt_flat[i]) else "partially_reversible" if ece > 16 else "reversible")
    add("salinity", s_sal, rev, "ml_predicted",
        f"ECe {_r(ece, 1)} dS/m (90% interval {_interval90(ece, float(U.ece_lsd[i]))}); barley (FAO IDP29 Table 4: threshold {c.a} dS/m, 50% yield at {c.ece[3]} dS/m) retains "
        f"{_r(100 * (1 - s_sal), 0)}% of yield potential; salt-flat flag: {bool(U.salt_flat[i])}")
    s_esp = 1 - float(np.clip(1 - max(esp - 0.5 * 35.0, 0) / 35.0, 0, 1))
    revs = "reversible" if esp <= 30 else "partially_reversible" if esp <= 50 else "irreversible"
    add("sodicity", s_esp, revs, "ml_predicted",
        f"ESP {_r(esp, 1)} % (+/-{_r(1.645 * float(U.esp_sd[i]), 1)} at 90%); sodic above 15 % (FAO SB39); semi-tolerant crops are seriously affected above ~35 %; "
        f"gypsum need to reach ESP 5 % at CEC {_r(float(U.cec[i]), 1)} cmol(c)/kg: {_r(8.609 * max(esp - 5, 0) / 100 * float(U.cec[i]) * float(U.bd[i]) * 0.3, 1)} t/ha pure gypsum (0.3 m)")
    s_ph = 1 - float(engine.ry_ph(np.array([ph]))[0])
    add("alkalinity", s_ph, "partially_reversible", "ml_predicted",
        f"pH(H2O) {_r(ph, 2)} +/-{_r(1.645 * float(U.ph_sd[i]), 2)}; calcareous alkaline soils reduce Fe/Zn/P availability (pH>8.4 penalised) and cannot be acidified permanently at scale")
    s_soc = 1 - float(engine.ry_soc(np.array([soc]))[0])
    add("organic_carbon", s_soc, "reversible", "ml_predicted",
        f"topsoil SOC {_r(soc, 2)} % (uncertainty about +/-{_r(1.645 * 0.55, 2)} % absolute from arid-site validation of the source product); low SOC limits water holding and fertility")
    s_tex = 1 - float(engine.ry_tex(np.array([sand]), np.array([clay]))[0])
    add("texture", s_tex, "partially_reversible", "ml_predicted", f"sand {_r(sand, 0)} %, clay {_r(clay, 0)} % (+/-10 %); extremes lower water-holding or infiltration")
    s_cf = 1 - float(engine.ry_cf(np.array([cf]))[0])
    add("coarse_fragments", s_cf, "partially_reversible", "ml_predicted", f"coarse fragments about {_r(cf, 0)} vol %")
    s_d = 1 - float(engine.ry_depth(c, np.array([depth]))[0])
    revd = "irreversible" if depth < 30 else "partially_reversible" if depth < 60 else "reversible"
    add("soil_depth", s_d, revd, "ml_predicted",
        f"depth to bedrock {_r(depth, 0)} cm (third-party 250 m product capped at 200 cm; not validated locally); barley needs >= {int(c.zr_m[0] * 100)} cm for full rooting (FAO-56 Table 22)")
    s_sl = 1 - float(engine.ry_slope(np.array([slope]), False, 25.0, np.array([depth]))[0])
    revsl = "reversible" if slope <= 10 else "partially_reversible" if slope <= 30 else "irreversible"
    add("slope", s_sl, revsl, "observed", f"mean slope {_r(slope, 1)} deg (Copernicus GLO-30 DEM, 50 m slope aggregated to 250 m)")
    ei, a_rel = erosion.erosion_index(np.array([slope]), np.array([sand]), np.array([max(100 - sand - clay, 0)]), np.array([clay]), np.array([soc]), np.array([ctx["p_mean"][i]]))
    add("erosion", float(ei[0]), "reversible", "expert_rule", f"relative water-erosion index {_r(float(ei[0]), 2)} (RUSLE-type structure, not a soil-loss prediction; wind/flash-flood erosion not modelled)")
    # water: barley seasonal ET vs design rainfall
    kc = hydro.monthly_kc(c)
    wr = float((U.eto_m[:, i] * kc).sum())
    season_p = float((U.ppt_m[:, i] * (kc > 0)).sum() / max(U.ppt_m[:, i].sum(), 1e-3))
    dr = float(U.p67[i]) * season_p
    s_w = 1 - min(1.0, dr / max(wr, 1.0))
    add("water_availability", s_w, "partially_reversible", "observed",
        f"annual rainfall {_r(float(ctx['p_mean'][i]), 0)} mm (2-years-in-3 design value {_r(float(U.p67[i]), 0)} mm) vs barley season ET {_r(wr, 0)} mm; "
        f"rain-fed cultivation covers {_r(100 * min(1.0, dr / max(wr, 1.0)), 0)}% of crop demand; climate aridity cannot be reversed, only compensated by water supply")
    out.sort(key=lambda d: -d["severity"])
    return out


def _fmt_range(a, b):
    return f"{_r(a, 0)}-{_r(b, 0)}"


def interventions_for(U: engine.Units, E: dict, i: int, scen_ids: list, lfs: list) -> list:
    """Interventions of the recommended scenarios, with per-unit numeric expected effects."""
    out, seen = [], set()
    sids = engine.SCEN_IDS
    for sid in scen_ids:
        si = sids.index(sid)
        for iid in SCEN[sid]["interventions"]:
            if iid in seen:
                continue
            seen.add(iid)
            lib = INTERVENTIONS[iid]
            if iid == "leaching_reclamation":
                r = float(E["scen_r"][si, i])
                if r < 0.05 and float(U.ece[i]) < 4:
                    eff = f"initial ECe {_r(float(U.ece[i]), 1)} dS/m is already low; only maintenance leaching fraction needed"
                else:
                    eff = (f"reduce ECe {_r(float(U.ece[i]), 1)} -> {_r(float(E['scen_ece_post'][si, i]), 1)} dS/m (simulated); reclamation leaching depth "
                           f"{_r(r, 2)} m water per m soil = {_r(float(E['scen_reclaim_m3'][si, i]), 0)} m3/ha one-off (C/C0 = exp(-k r), k 1.6-2.3, FAO IDP29 80-90% removal at r=1)")
            elif iid == "gypsum_amendment":
                g = float(E["scen_gypsum_t"][si, i])
                eff = (f"{_r(g, 1)} t/ha gypsum (0.3 m, effectiveness 0.5-0.9 assumed) lowers ESP {_r(float(U.esp[i]), 1)} -> {_r(float(E['scen_esp_post'][si, i]), 1)} %" if g > 0.3
                       else f"not required (ESP {_r(float(U.esp[i]), 1)} % <= 5 % target)")
            elif iid == "drip_irrigation":
                eff = f"gross water about {_fmt_range(E['scen_w_lo'][si, i], E['scen_w_hi'][si, i])} m3/ha/yr (central {_r(float(E['scen_w_mid'][si, i]), 0)}) incl. leaching, 80-92% efficiency"
            elif iid == "water_harvesting":
                eff = f"required catchment:cultivated area ratio about {_r(float(E['scen_ccr'][si, i]), 1)}:1 (limit 6-12:1); rainfall {_r(float(U.p67[i]), 0)} mm in 2 years out of 3"
            elif iid == "organic_amendment":
                eff = f"+0.05-0.40 % SOC over ~5 yr (assumed range) from {_r(float(U.soc[i]), 2)} %; improves water holding and infiltration"
            elif iid == "terracing":
                eff = f"slope {_r(float(U.slope[i]), 1)} deg made cultivable (limit 20-30 deg, depth >= 40 cm); erosion reduced (assumed 50-90 %)"
            elif iid == "salt_tolerant_crops":
                eff = f"crop choice keeps relative yield >= 0.6 at ECe {_r(float(E['scen_ece_post'][si, i]), 1)} dS/m (post-reclamation, simulated)"
            else:
                eff = "enables leachate removal; feasibility decreases with initial ECe (probabilistic, no water-table data)"
            out.append(dict(id=iid, name=lib["name"], description=lib["description"], targets_factor=lib["targets_factor"], expected_effect=eff,
                            evidence=lib["evidence"], source_refs=lib["source_refs"]))
    return out


def residual_risks(U: engine.Units, E: dict, i: int, sid: str) -> list:
    si = engine.SCEN_IDS.index(sid)
    sc = SCEN[sid]
    risks = []
    if sc["source"] in ("groundwater_fresh", "groundwater_brackish"):
        risks.append("groundwater depletion: fossil/non-renewable aquifer abstraction (aquifer yield and licence not assessed)")
    if sc["source"] == "treated_wastewater":
        risks.append("treated-wastewater availability, distance to treatment plant and crop-use restrictions not assessed; salt and sodium load of effluent")
    if sc["irrigated"]:
        risks.append("secondary salinisation/sodification if leaching or drainage fails")
        if float(E["scen_ece_post"][si, i]) > 4:
            risks.append("residual root-zone salinity above 4 dS/m limits sensitive crops")
        if float(U.cec[i]) > 0 and float(E["scen_gypsum_t"][si, i]) > 5:
            risks.append("sodicity returns if the Ca source stops (gypsum maintenance)")
    if sc["wh"]:
        risks.append("rainfall failure years (annual rain 30-350 % of mean in hyper-arid zones, FAO) and flash-flood damage to bunds")
    if float(U.tmin_cold[i]) < 2.0:
        risks.append("winter frost/chill risk for date palm, citrus, almond and grape (flagged from coldest-month Tmin)")
    if float(U.ph[i]) > 8.2:
        risks.append("calcareous alkaline soil: iron/zinc/phosphorus deficiency (chelates, fertigation)")
    if float(U.depth[i]) < 60:
        risks.append("shallow soil over rock limits rooting and water storage")
    risks.append("wind erosion/dust and flash-flood erosion are not modelled")
    risks.append("soil depth and SOC come from third-party maps with no local validation (SoilGrids deserts: low skill for SOC)")
    return risks


def build_properties(U: engine.Units, E: dict, i: int, ctx: dict, feas_cuts: dict, water_cap: float) -> dict:
    sids = engine.SCEN_IDS
    score, lo, hi = float(E["score"][i]), float(E["lo"][i]), float(E["hi"][i])
    cls = "high" if score >= feas_cuts["high"] else "moderate" if score >= feas_cuts["moderate"] else "low" if score >= feas_cuts["low"] else "not_feasible"
    if U.restricted[i]:
        cls, score, lo, hi = "not_feasible", 0.0, 0.0, 0.0
    lfs = limiting_factors(U, i, ctx)
    order = sorted(range(len(sids)), key=lambda s: (-float(E["scen_p"][s, i]), float(E["scen_w_mid"][s, i])))
    keep = [s for s in order if float(E["scen_p"][s, i]) >= 0.05][:3] or order[:1]
    scen_out = []
    crop_ids = list(K.CROPS)
    for s in keep:
        sid = sids[s]
        sc = SCEN[sid]
        probs = [float(E["scen_class_p"][s, k, i]) for k in range(4)]
        pc = int(np.argmax(probs)) + 1
        cp = E["scen_crop_p"][s, :, i].astype(float)
        cats = []
        for ci, cid in enumerate(crop_ids):
            if cid in sc["crops"] and cp[ci] >= 0.5 and K.CATEGORY_LABELS[K.CROPS[cid].category] not in cats:
                cats.append(K.CATEGORY_LABELS[K.CROPS[cid].category])
        crops_ok = [K.CROPS[cid].name for ci, cid in enumerate(crop_ids) if cid in sc["crops"] and cp[ci] >= 0.5]
        t_lo = sc["years"][0] + (0.5 if float(E["scen_r"][s, i]) > 0.3 else 0.0)
        t_hi = sc["years"][1] + (1.0 if float(E["scen_gypsum_t"][s, i]) > 5 else 0.0) + (1.0 if float(E["scen_r"][s, i]) > 1.0 else 0.0)
        scen_out.append(dict(
            id=f"{sid}", name=sc["name"], intervention_ids=list(sc["interventions"]), post_class_code=pc, post_class_probability=_r(probs[pc - 1], 3),
            post_class_probabilities={str(k + 1): _r(p, 3) for k, p in enumerate(probs)},
            success_probability=_r(float(E["scen_p"][s, i]), 3),
            water_requirement_m3_ha_yr=dict(low=_r(float(E["scen_w_lo"][s, i]), 0), central=_r(float(E["scen_w_mid"][s, i]), 0), high=_r(float(E["scen_w_hi"][s, i]), 0)),
            reclamation_water_m3_ha_one_off=_r(float(E["scen_reclaim_m3"][s, i]), 0), gypsum_t_ha=_r(float(E["scen_gypsum_t"][s, i]), 1),
            water_sources=[sc["source"]], infrastructure=list(sc["infrastructure"]), crop_categories=cats, viable_crops=crops_ok,
            time_to_effect_years=dict(low=_r(t_lo, 1), high=_r(t_hi, 1)), residual_risks=residual_risks(U, E, i, sid), evidence="simulated"))
    best_sid = sids[keep[0]]
    top_ints = interventions_for(U, E, i, [sids[s] for s in keep[:2]], lfs)
    return dict(
        current_class_code=int(ctx.get("current_class", 4)[i]) if hasattr(ctx.get("current_class", 4), "__len__") else int(ctx.get("current_class", 4)),
        limiting_factors=lfs,
        feasibility=dict(score=_r(score, 3), **{"class": cls}, confidence=_r(max(0.0, 1.0 - (hi - lo)), 3), interval=[_r(lo, 3), _r(hi, 3)]),
        feasibility_meta=dict(
            confidence_method="1 - width of the 5-95 % interval of the Monte-Carlo success probability over parameter draws (NOT a calibrated probability of real-world success)",
            score_definition=("probability, over input-uncertainty x parameter draws, that at least one evaluated scenario brings the best crop to relative yield >= 0.6 (FAO class S2 or better)"
                              f" under a reference water allocation of {int(water_cap)} m3/ha/yr per unit (a scenario condition, not an observation)"),
            evidence="simulated", best_scenario=best_sid),
        interventions=top_ints, scenarios=scen_out)


def soil_block(v: dict, i: int, U: engine.Units) -> dict:
    def item(val, unit, ev, unc=None, nd=2):
        d = dict(value=_r(val, nd), unit=unit, evidence=ev)
        if unc is not None:
            d["uncertainty"] = unc
        return d
    ece, esp = float(U.ece[i]), float(U.esp[i])
    return {
        "ph": item(float(U.ph[i]), "pH (H2O)", "ml_predicted", dict(sd=0.35, basis="SoilGrids 2.0 vs WoSIS measured, arid held-out sites (RMSE)")),
        "ec_ds_m": item(ece, "dS/m (saturated paste, 0-30 cm)", "ml_predicted", dict(interval90=_interval90(ece, float(U.ece_lsd[i])), method="Mondrian split-conformal, block-CV residuals")),
        "esp_pct": item(esp, "% exchangeable sodium", "ml_predicted", dict(sd=_r(float(U.esp_sd[i]), 1))),
        "soc_pct": item(float(U.soc[i]), "% organic carbon (0-30 cm)", "ml_predicted", dict(sd=0.55, basis="SoilGrids vs WoSIS arid RMSE; low skill in deserts")),
        "sand_pct": item(float(U.sand[i]), "%", "ml_predicted", dict(sd=11.0)),
        "silt_pct": item(max(100 - float(U.sand[i]) - float(U.clay[i]), 0), "%", "ml_predicted", dict(sd=10.0)),
        "clay_pct": item(float(U.clay[i]), "%", "ml_predicted", dict(sd=9.0)),
        "depth_cm": item(float(U.depth[i]), "cm to bedrock (capped 200)", "ml_predicted", dict(log10_sd=0.15, basis="assumed; no local validation")),
        "coarse_fragments_vol_pct": item(float(U.cf[i]), "vol %", "ml_predicted"),
        "bulk_density_g_cm3": item(float(U.bd[i]), "g/cm3", "ml_predicted"),
        "cec_cmolc_kg": item(float(U.cec[i]), "cmol(c)/kg", "ml_predicted"),
    }
