"""Monte-Carlo restoration-feasibility engine (transparent multi-criteria model; nested uncertainty propagation).

Unit of computation = a land unit (grid cell or polygon aggregate) with central soil/terrain/climate state + uncertainty.
For each (outer parameter draw j, inner input-noise draw i) and each intervention SCENARIO s and CROP c the engine computes a relative yield

    RY = RY_salinity * RY_sodicity * RY_pH * RY_SOC * RY_coarse_fragments * RY_texture * RY_depth * RY_slope * RY_water

(Maas-Hoffman salinity line from FAO_IDP29; ESP tolerance classes from FAO_SB39; remaining response curves are documented expert_rule assumptions,
see FACTOR_ASSUMPTIONS) after applying the scenario's interventions to the soil state:
  leaching reclamation (C/C0 = exp(-k r), k calibrated to FAO_IDP29's 70-80 % / 80-90 % salt removal per unit depth ratio), steady-state ECe from
  irrigation-water ECw and leaching fraction (LR = ECw/(5 ECe - ECw)), gypsum replacement of exchangeable Na (stoichiometry, FAO_SB39 worked example),
  organic-matter amendment (assumed SOC gain range), terracing (slope limit, erosion reduction), water harvesting (C:CA design equation, FAO_WH91).
Success of a draw = best crop RY >= ry_thr (class S1/S2 boundary, FAO_SB55: top of S3 taken as 0.6).  Feasibility score = mean success over all draws
for the best of the scenarios; interval = 5-95 % of the inner-mean success over the OUTER (parameter) draws.  Post-restoration class from the RY of the
best crop (S1>=0.8, S2 0.6-0.8, S3 0.4-0.6, N<0.4; the 0.4 bound is an assumption).
Everything produced here is `simulated` / `expert_rule`; nothing is a measured restoration outcome.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import hydro
from .knowledge import crops as K

RNG_SEED = 20261122

FACTOR_ASSUMPTIONS = {
    "RY_sodicity": "piecewise-linear: 1 up to 0.5 E*, 0.5 at E*, 0 at 1.5 E*; E* = ESP above which yields are seriously affected (FAO_SB39 Table 32: 55/35/10; 6 for extremely sensitive = assumed)",
    "RY_pH": "1 for pH 5.5-8.4; -0.25 RY per pH unit above 8.4; -0.20 per unit below 5.5 (assumed; FAO_SB39 only states pH 8.2 as sodic diagnostic)",
    "RY_SOC": "0.75 + 0.25 min(SOC/0.6 %, 1) (assumed: dryland soils are productive under fertigation at low SOC)",
    "RY_coarse_fragments": "1 up to 15 vol %, linear to 0.5 at 55 %, to 0.2 at 80 % (assumed; FAO_SB55 lists stoniness as class-determining factor, limits not read)",
    "RY_texture": "sand > 85 %: -0.4 per 15 %; clay > 55 %: -0.4 per 45 % (assumed)",
    "RY_depth": "clip((depth-20 cm)/(Zr_min-20 cm),0,1)^0.6 with Zr_min from FAO56 Table 22 (curve assumed); 0 below 20 cm",
    "RY_slope": "non-terraced: 1 up to 3 deg, 0.5 at 10 deg, 0 at 18 deg (assumed); terraced: 1 within the terrace limit (20-30 deg, assumed) and depth >= 40 cm",
    "RY_water": "1 - Ky (1 - supply/demand), Ky = 1 (assumed; FAO-33 Ky not read)",
    "classes": "S1 >= 0.8, S2 0.6-0.8, S3 0.4-0.6, N < 0.4 relative yield (FAO_SB55: tops of S2 and S3 = 80 % / 60 %; 40 % bound assumed)",
}

# ----------------------------------------------------------------------------- scenarios
SCENARIOS = {
    "irr_fresh": dict(
        name="Drip irrigation with fresh groundwater + reclamation leaching, gypsum and organic amendment", ecw=(0.4, 0.9, 1.8),
        source="groundwater_fresh", crops=["barley", "wheat", "alfalfa", "sudan_grass", "tall_wheatgrass", "date_palm", "olive", "almond", "grape", "orange", "tomato"],
        interventions=["drip_irrigation", "leaching_reclamation", "gypsum_amendment", "organic_amendment", "drainage"], terraced=False, wh=False, irrigated=True,
        infrastructure=["production well(s) and pumping", "conveyance pipeline", "filtration + drip network", "drainage outlet/evaporation pond for leachate", "gypsum/compost spreading"],
        years=(1.0, 4.0)),
    "irr_tww": dict(
        name="Treated-wastewater drip irrigation, salt-tolerant crops, leaching and gypsum", ecw=(1.2, 1.8, 2.8),
        source="treated_wastewater", crops=["barley", "wheat", "alfalfa", "sudan_grass", "tall_wheatgrass", "date_palm", "olive"],
        interventions=["drip_irrigation", "leaching_reclamation", "gypsum_amendment", "organic_amendment", "salt_tolerant_crops", "drainage"], terraced=False, wh=False, irrigated=True,
        infrastructure=["connection to a wastewater treatment plant outlet (distance NOT mapped)", "storage reservoir", "filtration + drip network", "drainage for leachate"],
        years=(1.5, 5.0)),
    "irr_brackish": dict(
        name="Brackish-groundwater drip irrigation with salt-tolerant crops (biosaline agriculture)", ecw=(2.5, 4.0, 7.0),
        source="groundwater_brackish", crops=["date_palm", "barley", "tall_wheatgrass", "sudan_grass", "olive"],
        interventions=["drip_irrigation", "leaching_reclamation", "gypsum_amendment", "salt_tolerant_crops", "drainage"], terraced=False, wh=False, irrigated=True,
        infrastructure=["brackish well(s) and pumping", "drip network with anti-clogging filtration", "drainage + evaporation pond for brine/leachate"],
        years=(2.0, 6.0)),
    "rainfed_wh": dict(
        name="Rain-fed cultivation with microcatchment water harvesting and mulch/organic amendment", ecw=None,
        source="rainwater_harvesting", crops=["barley", "olive", "tall_wheatgrass"],
        interventions=["water_harvesting", "organic_amendment", "salt_tolerant_crops"], terraced=False, wh=True, irrigated=False,
        infrastructure=["contour bunds / microcatchments", "runoff catchment area (C:CA > 1)", "spillways for flood years"],
        years=(1.0, 3.0)),
    "terraced_irr": dict(
        name="Bench terraces with soil conservation and drip irrigation (sloping land)", ecw=(0.4, 0.9, 1.8),
        source="groundwater_fresh", crops=["barley", "wheat", "alfalfa", "tall_wheatgrass", "date_palm", "olive", "almond", "grape"],
        interventions=["terracing", "drip_irrigation", "leaching_reclamation", "gypsum_amendment", "organic_amendment", "drainage"], terraced=True, wh=False, irrigated=True,
        infrastructure=["bench terraces with stone/earth risers", "production well(s) and pumping", "drip network", "runoff diversion drains"],
        years=(2.0, 6.0)),
}
SCEN_IDS = list(SCENARIOS)

# parameter priors (assumed unless a source is named)
def sample_params(J: int, rng: np.random.Generator, water_cap: float = 8000.0) -> dict:
    tri = lambda lo, mode, hi: rng.triangular(lo, mode, hi, J)
    return dict(
        tol_f=np.exp(rng.normal(0, 0.20, J)),                 # crop salinity tolerance scale (assumed +-20 %, olive proxy handled separately)
        esp_f=np.exp(rng.normal(0, 0.20, J)),
        eto_f=np.exp(rng.normal(0, 0.10, J)),                 # ETo uncertainty (TerraClimate PM vs Hargreaves differ by ~10-15 %)
        kc_f=rng.uniform(0.9, 1.1, J),
        peff=rng.uniform(0.5, 0.8, J),                        # effective-rainfall fraction (assumed)
        eff_drip=rng.uniform(0.80, 0.92, J),                  # drip application efficiency (assumed)
        k_leach=rng.uniform(1.61, 2.30, J),                   # intermittent/sprinkler/drip: 80-90 % removal at r = 1 (FAO_IDP29)
        r_cap=rng.uniform(1.0, 2.0, J),                       # max feasible leaching depth per unit soil depth (assumed)
        gyp_eff=rng.uniform(0.5, 0.9, J),                     # fraction of applied gypsum Ca effective in replacing Na (assumed)
        gyp_cap=rng.uniform(15.0, 40.0, J),                   # max practical gypsum rate t/ha (assumed)
        dsoc=tri(0.05, 0.15, 0.40),                           # SOC gain (%, 0-30 cm) over ~5 yr from amendments (assumed; GRAVUER_2019 qualitative only)
        wcap=np.exp(rng.normal(np.log(water_cap), 0.15, J)),  # reference water allocation m3/ha/yr per unit: a SCENARIO CONDITION (default 8000, assumed), not an observation
        ccr_max=rng.uniform(6.0, 12.0, J),                    # max catchment:cultivated ratio (FAO_WH91 example 7.2:1 'high'; assumed range)
        k_runoff=tri(0.10, 0.25, 0.50),                       # FAO_WH91: 0.1-0.5
        eff_wh=rng.uniform(0.50, 0.75, J),                    # FAO_WH91: 0.5-0.75
        terr_lim=rng.uniform(20.0, 30.0, J),                  # max terraceable slope, deg (assumed)
        ry_thr=rng.uniform(0.55, 0.65, J),                    # S2/S3 boundary 0.6 (FAO_SB55) +- 0.05
        ecw_u=rng.uniform(0, 1, J),                           # position within each water source's ECw triangular prior
        lr_cap=rng.uniform(0.35, 0.5, J),
        ece_target_yp=rng.choice([0.9, 1.0], J, p=[0.7, 0.3]),
    )


def _tri_ppf(u, lo, mode, hi):
    c = (mode - lo) / (hi - lo)
    return np.where(u < c, lo + np.sqrt(u * (hi - lo) * (mode - lo)), hi - np.sqrt((1 - u) * (hi - lo) * (hi - mode)))


# ----------------------------------------------------------------------------- unit state
@dataclass
class Units:
    """Central state + uncertainty for N units (all 1-D float arrays unless noted)."""
    ece: np.ndarray; ece_lsd: np.ndarray          # dS/m, log10 sd
    esp: np.ndarray; esp_sd: np.ndarray           # %
    ph: np.ndarray; ph_sd: np.ndarray
    soc: np.ndarray; soc_rsd: np.ndarray          # %, relative sd
    sand: np.ndarray; clay: np.ndarray; tex_sd: np.ndarray
    cf: np.ndarray; bd: np.ndarray; cec: np.ndarray     # vol %, g/cm3, cmol(c)/kg
    depth: np.ndarray; depth_lsd: np.ndarray      # cm, log10 sd
    slope: np.ndarray                             # deg
    ppt_m: np.ndarray                             # (12, N) mm/month
    eto_m: np.ndarray                             # (12, N) mm/month
    p67: np.ndarray                               # mm/yr design rainfall (33rd percentile of annual series)
    tmin_cold: np.ndarray                         # degC mean Tmin coldest month
    salt_flat: np.ndarray                         # bool: playa/sabkha-type (very high ECe + flat)
    restricted: np.ndarray                        # bool: Model 1 class 5
    n: int = field(init=False)

    def __post_init__(self):
        self.n = len(self.ece)

    def subset(self, idx):
        d = {}
        for k, v in self.__dict__.items():
            if k == "n":
                continue
            d[k] = v[..., idx] if (isinstance(v, np.ndarray) and v.ndim == 2) else v[idx]
        return Units(**d)


# ----------------------------------------------------------------------------- factor functions (inputs broadcast: (J,I,n))
def ry_sal(crop, ece, tol_f):
    a = crop.a * tol_f
    b = crop.b / tol_f
    return np.clip(1.0 - b / 100.0 * np.maximum(ece - a, 0.0), 0.0, 1.0)


def ry_esp(crop, esp, esp_f):
    e = K.esp_onset(crop) * esp_f
    return np.clip(1.0 - np.maximum(esp - 0.5 * e, 0.0) / e, 0.0, 1.0)


def ry_ph(ph):
    return np.clip(1.0 - 0.25 * np.maximum(ph - 8.4, 0) - 0.20 * np.maximum(5.5 - ph, 0), 0.4, 1.0)


def ry_soc(soc):
    return 0.75 + 0.25 * np.clip(soc / 0.6, 0, 1)


def ry_cf(cf):
    return np.where(cf <= 15, 1.0, np.where(cf <= 55, 1.0 - 0.5 * (cf - 15) / 40.0, np.clip(0.5 - 0.3 * (cf - 55) / 25.0, 0.2, 0.5)))


def ry_tex(sand, clay):
    return np.clip(1.0 - 0.4 * np.maximum(sand - 85, 0) / 15.0 - 0.4 * np.maximum(clay - 55, 0) / 45.0, 0.3, 1.0)


def ry_depth(crop, depth_cm):
    zr = crop.zr_m[0] * 100.0
    return np.clip((depth_cm - 20.0) / (zr - 20.0), 0, 1) ** 0.6


def ry_slope(slope, terraced, terr_lim, depth_cm):
    free = np.clip(1.0 - 0.5 * np.maximum(slope - 3, 0) / 7.0, 0, 1)
    free = np.where(slope > 10, np.clip(0.5 - 0.5 * (slope - 10) / 8.0, 0, 0.5), free)
    if terraced:
        return np.where((slope <= terr_lim) & (depth_cm >= 40.0), 1.0, 0.0)
    return free


# ----------------------------------------------------------------------------- main evaluation
def _ece_target(crop, yp, tol_f):
    """ECe giving yield potential yp (1.0 or 0.9) for the crop (Maas-Hoffman)."""
    a = crop.a * tol_f
    b = crop.b / tol_f
    return a + (1.0 - yp) * 100.0 / b


def evaluate(U: Units, J: int = 16, I: int = 4, seed: int = RNG_SEED, chunk: int = 5000, return_draws: bool = False, params: dict | None = None,
             progress=None, water_cap: float = 8000.0) -> dict:
    """Run the nested Monte-Carlo for all units. Returns per-unit arrays (see keys below)."""
    rng = np.random.default_rng(seed)
    P = params if params is not None else sample_params(J, rng, water_cap)
    n_all = U.n
    S = len(SCEN_IDS)
    out = dict(
        score=np.zeros(n_all, "float32"), lo=np.zeros(n_all, "float32"), hi=np.zeros(n_all, "float32"),
        scen_p=np.zeros((S, n_all), "float32"),                      # success probability per scenario
        scen_ry=np.zeros((S, n_all), "float32"),                     # median RY of the chosen crop
        scen_class_p=np.zeros((S, 4, n_all), "float32"),             # P(post class 1..4)
        scen_w_lo=np.zeros((S, n_all), "float32"), scen_w_mid=np.zeros((S, n_all), "float32"), scen_w_hi=np.zeros((S, n_all), "float32"),
        scen_reclaim_m3=np.zeros((S, n_all), "float32"), scen_gypsum_t=np.zeros((S, n_all), "float32"),
        scen_r=np.zeros((S, n_all), "float32"), scen_ece_post=np.zeros((S, n_all), "float32"), scen_esp_post=np.zeros((S, n_all), "float32"),
        scen_ccr=np.zeros((S, n_all), "float32"),
        scen_crop_best=np.zeros((S, n_all), "int8"), crop_p=np.zeros((len(K.CROPS), n_all), "float32"),
        scen_crop_p=np.zeros((S, len(K.CROPS), n_all), "float16"),
        best_scen=np.zeros(n_all, "int8"),
    )
    crop_ids = list(K.CROPS)
    for c0 in range(0, n_all, chunk):
        idx = np.arange(c0, min(c0 + chunk, n_all))
        r = _eval_chunk(U.subset(idx), P, J, I, np.random.default_rng(seed + c0))
        for k, v in r.items():
            if k in out:
                out[k][..., idx] = v
        if progress:
            progress(min(1.0, (c0 + len(idx)) / n_all), f"feasibility Monte-Carlo {c0 + len(idx)}/{n_all} units")
    out["params"] = P
    out["scenario_ids"] = SCEN_IDS
    out["crop_ids"] = crop_ids
    return out


def _noise(U: Units, J, I, rng):
    n = U.n
    sh = (J, I, n)
    z = lambda: rng.standard_normal(sh).astype("float32")
    ece = U.ece * 10 ** (U.ece_lsd * z())
    esp = np.clip(U.esp + U.esp_sd * z(), 0, 100)
    ph = np.clip(U.ph + U.ph_sd * z(), 3.5, 11)
    soc = np.maximum(U.soc * np.exp(U.soc_rsd * z()), 0.0)
    sand = np.clip(U.sand + U.tex_sd * z(), 0, 100)
    clay = np.clip(U.clay + U.tex_sd * 0.8 * z(), 0, 100 - sand)
    depth = U.depth * 10 ** (U.depth_lsd * z())
    cf = np.clip(U.cf + 5.0 * z(), 0, 90)
    slope = np.clip(U.slope + 0.3 * z(), 0, 60)
    return dict(ece=ece, esp=esp, ph=ph, soc=soc, sand=sand, clay=clay, depth=depth, cf=cf, slope=slope)


def _eval_chunk(U: Units, P: dict, J: int, I: int, rng) -> dict:
    n = U.n
    N = _noise(U, J, I, rng)
    col = lambda a: a.reshape(J, 1, 1)         # outer param -> (J,1,1)
    res = {}
    S = len(SCEN_IDS)
    thr = col(P["ry_thr"])
    succ_any = np.zeros((J, I, n), bool)
    scen_succ = np.zeros((S, J, I, n), bool)
    crop_hit = np.zeros((len(K.CROPS), n), "float32")
    res["scen_crop_p"] = np.zeros((S, len(K.CROPS), n), "float16")
    best_p = np.full(n, -1.0)
    best_s = np.zeros(n, "int8")
    crop_ids = list(K.CROPS)
    for si, sid in enumerate(SCEN_IDS):
        sc = SCENARIOS[sid]
        ry_best = np.zeros((J, I, n), "float32")
        w_best = np.full((J, I, n), np.inf, "float32")
        crop_best = np.zeros((J, I, n), "int8")
        ece_post_b = np.zeros((J, I, n), "float32"); esp_post_b = np.zeros((J, I, n), "float32")
        recl_b = np.zeros((J, I, n), "float32"); gyp_b = np.zeros((J, I, n), "float32"); r_b = np.zeros((J, I, n), "float32")
        ccr_b = np.zeros((J, I, n), "float32")
        for cid in sc["crops"]:
            crop = K.CROPS[cid]
            # ---- climate-driven water demand (outer level -> (J,1,n))
            kc = hydro.monthly_kc(crop)
            etc_m = (U.eto_m[:, None, :] * col(P["eto_f"]).reshape(1, J, 1) * (kc * 1.0).reshape(12, 1, 1) * P["kc_f"].reshape(1, J, 1))   # (12,J,n)
            ppt = U.ppt_m[:, None, :]
            net = np.clip(etc_m - P["peff"].reshape(1, J, 1) * ppt, 0, None).sum(0)[:, None, :]   # (J,1,n) mm/yr
            wr = etc_m.sum(0)[:, None, :]                                                        # seasonal/annual crop ET (mm)
            season_p = (U.ppt_m * (kc > 0).reshape(12, 1)).sum(0) / np.maximum(U.ppt_m.sum(0), 1e-3)
            dr = (U.p67 * season_p)[None, None, :]                                               # design rainfall for the crop season
            soil_ece = N["ece"]
            soil_esp = N["esp"]
            soc = N["soc"]
            r_used = np.zeros((J, I, n), "float32"); gyp = np.zeros((J, I, n), "float32"); recl_mm = np.zeros((J, I, n), "float32")
            ccr = np.zeros((J, I, n), "float32")
            ece_post = soil_ece; esp_post = soil_esp
            if sc["irrigated"]:
                lo, mode, hi = sc["ecw"]
                ecw = _tri_ppf(col(P["ecw_u"]), lo, mode, hi)
                e_t = _ece_target(crop, col(P["ece_target_yp"]), col(P["tol_f"]))
                lr = hydro.leaching_requirement(ecw, e_t)                                        # FAO_IDP29 eq. 9 (inf if unattainable)
                lf_used = np.maximum(np.minimum(np.where(np.isfinite(lr), lr, 1.0), col(P["lr_cap"])), 0.05)   # leaching fraction actually run (<= cap)
                gross_mm = hydro.gross_water_mm(net, col(P["eff_drip"]), lf_used, lr_cap=1.0)    # FAO_IDP29 eq. 7 + Example 3 (losses may cover LR)
                ece_ss = hydro.steady_state_ece(ecw, lf_used)                                    # long-term root-zone ECe under this water + LF
                ece_final_t = np.maximum(ece_ss, 0.3)
                # reclamation leaching of the initial salt load down to ece_final_t: C/C0 = exp(-k r)
                kleach = col(P["k_leach"])
                r_need = np.where(soil_ece > ece_final_t, np.log(np.maximum(soil_ece, 1e-6) / ece_final_t) / kleach, 0.0)
                r_used = np.minimum(r_need, col(P["r_cap"]))
                ece_after = soil_ece * np.exp(-kleach * r_used)
                ece_post = np.where(r_need > r_used, ece_after, ece_final_t)                    # incomplete reclamation vs. steady state of the irrigation water
                recl_mm = r_used * 600.0                                                         # leach a 0.6 m profile (assumed)
                # gypsum for sodicity: X cmol(c)/kg of Na to replace to reach ESP_f = 5 %
                esp_f = 5.0
                x = np.maximum(soil_esp - esp_f, 0) / 100.0 * U.cec
                gr_t_ha = 8.609 * x * U.bd * 0.30                                              # pure gypsum t/ha for 0.3 m (FAO_SB39 stoichiometry)
                applied = np.minimum(gr_t_ha / col(P["gyp_eff"]), col(P["gyp_cap"]))
                dx = applied * col(P["gyp_eff"]) / (8.609 * U.bd * 0.30)                       # cmol(c)/kg Na actually replaced
                esp_post = np.where(U.cec > 0, np.maximum(esp_f, soil_esp - 100.0 * dx / np.maximum(U.cec, 1e-3)), soil_esp)
                esp_post = np.where(soil_esp > esp_f, esp_post, soil_esp)
                gyp = applied
                soc = soc + col(P["dsoc"])
                demand_m3 = gross_mm * 10.0 + recl_mm * 10.0 / 5.0            # one-off reclamation water amortised over 5 yr (assumed)
                frac = np.minimum(1.0, col(P["wcap"]) / np.maximum(demand_m3, 1.0))
                w_here = np.broadcast_to(demand_m3, (J, I, n)).astype("float32")
            else:                                                                                # rainfed + water harvesting
                kmin = hydro.wh_catchment_ratio(wr, dr, col(P["k_runoff"]), col(P["eff_wh"]))
                ccr = np.minimum(kmin, col(P["ccr_max"]))
                harvest = dr * col(P["k_runoff"]) * col(P["eff_wh"]) * col(P["ccr_max"])
                frac = np.minimum(1.0, (dr + harvest) / np.maximum(wr, 1.0))
                frac = np.where(dr > 1.0, frac, 0.0) * np.ones((J, I, n), "float32")
                soc = soc + 0.5 * col(P["dsoc"])
                w_here = np.zeros((J, I, n), "float32")
                recl_mm = np.zeros((J, I, n), "float32")
            ry = (ry_sal(crop, ece_post, col(P["tol_f"])) * ry_esp(crop, esp_post, col(P["esp_f"])) * ry_ph(N["ph"]) * ry_soc(soc) * ry_cf(N["cf"])
                  * ry_tex(N["sand"], N["clay"]) * ry_depth(crop, N["depth"]) * ry_slope(N["slope"], sc["terraced"], col(P["terr_lim"]), N["depth"])
                  * np.clip(1.0 - 1.0 * (1.0 - frac), 0, 1))
            ry = np.where(U.restricted[None, None, :], 0.0, ry)
            if sc["irrigated"]:
                # leaching needs somewhere for the leachate to go (FAO_IDP29 ch.2: drainage). No water-table data exist -> probabilistic
                # drainage feasibility, decreasing with the initial salt load (logistic-type, assumed), halved on flat saline basins (salt flats).
                p_drain = 1.0 / (1.0 + (soil_ece / 20.0) ** 3)
                p_drain = np.where(U.salt_flat[None, None, :], 0.5 * p_drain, p_drain)
                drain_ok = rng.random((J, I, n)) <= p_drain
                ry = np.where((r_used > 0.3) & ~drain_ok, 0.0, ry)
            ry = np.where(U.salt_flat[None, None, :] & (ece_post > 25), 0.0, ry)
            res["scen_crop_p"][si, crop_ids.index(cid)] = (ry >= thr).mean(axis=(0, 1))
            better = ry > ry_best + 1e-6
            ry_best = np.where(better, ry, ry_best)
            w_best = np.where(better, w_here, w_best)
            crop_best = np.where(better, np.int8(crop_ids.index(cid)), crop_best)
            ece_post_b = np.where(better, ece_post, ece_post_b); esp_post_b = np.where(better, esp_post, esp_post_b)
            recl_b = np.where(better, recl_mm * 10.0, recl_b); gyp_b = np.where(better, gyp, gyp_b); r_b = np.where(better, r_used, r_b)
            ccr_b = np.where(better, ccr, ccr_b)
        ok = ry_best >= thr
        scen_succ[si] = ok
        succ_any |= ok
        cls = np.where(ry_best >= 0.8, 1, np.where(ry_best >= 0.6, 2, np.where(ry_best >= 0.4, 3, 4)))
        p_ok = ok.mean(axis=(0, 1))
        res.setdefault("scen_p", np.zeros((S, n), "float32"))[si] = p_ok
        res.setdefault("scen_ry", np.zeros((S, n), "float32"))[si] = np.median(ry_best, axis=(0, 1))
        cp = res.setdefault("scen_class_p", np.zeros((S, 4, n), "float32"))
        for k in range(4):
            cp[si, k] = (cls == (k + 1)).mean(axis=(0, 1))
        srt = np.sort(w_best.reshape(-1, n), axis=0)                # inf (no feasible water figure) sorts last
        cntf = np.isfinite(srt).sum(0)
        ar = np.arange(n)
        wl = []
        for q in (0.10, 0.50, 0.90):
            ii = np.clip(np.round(q * (cntf - 1)).astype(int), 0, srt.shape[0] - 1)
            wl.append(np.where(cntf > 0, srt[ii, ar], 0.0))
        wlo, wmid, whi = wl
        for key, v in (("scen_w_lo", wlo), ("scen_w_mid", wmid), ("scen_w_hi", whi)):
            res.setdefault(key, np.zeros((S, n), "float32"))[si] = np.nan_to_num(v, nan=0.0)
        for key, arr in (("scen_reclaim_m3", recl_b), ("scen_gypsum_t", gyp_b), ("scen_r", r_b), ("scen_ece_post", ece_post_b), ("scen_esp_post", esp_post_b), ("scen_ccr", ccr_b)):
            res.setdefault(key, np.zeros((S, n), "float32"))[si] = np.median(arr, axis=(0, 1))
        cb = crop_best.reshape(-1, n)
        mode = np.zeros(n, "int8")
        counts = np.stack([(cb == k).sum(0) for k in range(len(crop_ids))])
        mode = counts.argmax(0).astype("int8")
        res.setdefault("scen_crop_best", np.zeros((S, n), "int8"))[si] = mode
        cph = np.stack([((cb == k) & ok.reshape(-1, n)).mean(0) for k in range(len(crop_ids))])   # P(crop is the successful best crop)
        crop_hit = np.maximum(crop_hit, cph.astype("float32"))
        pm = p_ok.copy()
        upd = pm > best_p + 1e-9
        best_s = np.where(upd, np.int8(si), best_s); best_p = np.where(upd, pm, best_p)
    inner = succ_any.mean(axis=1)                      # (J, n)
    res["score"] = inner.mean(axis=0)
    res["lo"] = np.percentile(inner, 5, axis=0)
    res["hi"] = np.percentile(inner, 95, axis=0)
    res["crop_p"] = crop_hit
    res["best_scen"] = best_s
    return res


def feasibility_class(score, cuts):
    return np.where(score >= cuts["high"], 4, np.where(score >= cuts["moderate"], 3, np.where(score >= cuts["low"], 2, 1))).astype("uint8")
