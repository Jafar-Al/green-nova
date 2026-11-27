"""Writers for Model 2 deliverables (COG rasters, polygons.geojson, summary.json, run_metadata.json).  No absolute paths are written anywhere."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.shutil import copy as rio_copy
from rasterio.warp import calculate_default_transform, reproject

from . import config, engine
from .knowledge import crops as K
from .knowledge.sources import SOURCES

STUDIES_USED = {"FAO_IDP29", "FAO56", "FAO_SB55", "FAO_SB39", "FAO_WH91", "MAAS_HOFFMAN_1977", "SWATPLUS_K", "GRAVUER_2019", "HASSANI_2020", "BATJES_2024"}
EVIDENCE_SUMMARY = {
    "observed": ["slope and elevation (Copernicus GLO-30 DEM)", "climate normals and interannual rainfall (TerraClimate 2011-2020, gridded climate product)", "crop/ESP/salinity tolerance tables are literature (see expert_rule)"],
    "ml_predicted": ["ECe and ESP (own LightGBM trained on measured WoSIS/Hassani points, conformal intervals)", "pH, SOC, texture, coarse fragments, bulk density, CEC (SoilGrids 2.0, third party)",
                     "depth to bedrock (SoilGrids 2017, third party, capped 200 cm)"],
    "expert_rule": ["Maas-Hoffman salinity response (FAO IDP29 Table 4), ESP tolerance classes (FAO SB39), pH/SOC/coarse-fragment/texture/depth/slope response curves (assumed shapes)",
                    "relative erosion index (RUSLE-type structure)", "FAO suitability class boundaries on relative yield (S1>=0.8, S2 0.6-0.8, S3 0.4-0.6 [assumed], N<0.4)"],
    "simulated": ["intervention outcomes (leaching, gypsum, organic amendment, terracing, water harvesting)", "post-restoration relative yield, class and water requirement", "feasibility score and interval (Monte-Carlo)"],
}
DATA_SOURCES_SHORT = [
    "WoSIS 2023-12 snapshot (ISRIC; CC BY / public-domain subset) - ECe training labels", "Hassani et al. 2020 (Mendeley Data, CC BY 4.0) - ECe/ESP training points",
    "SoilGrids 2.0 (ISRIC, CC BY 4.0) - pH, SOC, texture, CF, BD, CEC", "SoilGrids 2017 BDRICM (ISRIC) - depth to bedrock", "WorldClim 2.1 bioclim + elevation (CC BY 4.0) - ECe/ESP covariates",
    "TerraClimate 2011-2020 (Abatzoglou et al. 2018) - rainfall, ET0", "Copernicus GLO-30 DEM - slope", "geoBoundaries gbOpen JOR ADM1 (CC BY 2.5) - boundary"]


def rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(config.PROJECT_ROOT.resolve())).replace("\\", "/")
    except Exception:
        return Path(p).name


def write_cog(path: Path, arr: np.ndarray, grid, nodata, tags: dict, dtype: str):
    prof = dict(driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype=dtype, crs=grid.crs, transform=grid.transform, nodata=nodata,
                tiled=True, blockxsize=256, blockysize=256, compress="deflate")
    tmp = Path(str(path) + ".tmp.tif")
    with rasterio.open(tmp, "w", **prof) as dst:
        dst.write(arr.astype(dtype), 1)
        dst.update_tags(**{k: str(v) for k, v in tags.items()})
        dst.build_overviews([2, 4, 8, 16], Resampling.nearest if "int" in dtype else Resampling.average)
    try:
        rio_copy(str(tmp), str(path), driver="COG", COMPRESS="DEFLATE", OVERVIEW_RESAMPLING="NEAREST" if "int" in dtype else "AVERAGE")
    except Exception:
        Path(path).write_bytes(tmp.read_bytes())
    tmp.unlink()


def write_preview_4326(src_path: Path, dst_path: Path, nodata, dtype):
    with rasterio.open(src_path) as s:
        tr, w, h = calculate_default_transform(s.crs, "EPSG:4326", s.width, s.height, *s.bounds, resolution=0.0025)
        a = np.full((h, w), nodata, dtype=dtype)
        reproject(rasterio.band(s, 1), a, dst_transform=tr, dst_crs="EPSG:4326", src_nodata=nodata, dst_nodata=nodata, resampling=Resampling.nearest)
        tags = s.tags()
    with rasterio.open(dst_path, "w", driver="GTiff", height=h, width=w, count=1, dtype=dtype, crs="EPSG:4326", transform=tr, nodata=nodata, tiled=True, blockxsize=256, blockysize=256, compress="deflate") as d:
        d.write(a, 1)
        d.update_tags(**tags, web_preview="EPSG:4326 nearest-neighbour preview of the equal-area COG")


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _caveats(water_cap: float, mc: dict | None, standin: bool, m1: dict | None) -> dict:
    rep, ev = {}, {}
    try:
        rep = json.loads((config.EVAL_DIR / "soil_models_report.json").read_text())
    except Exception:
        pass
    try:
        ev = json.loads((config.EVAL_DIR / "restoration_eval.json").read_text())
    except Exception:
        pass
    skill = {}
    for k, d in rep.items():
        r = d["runs"]["with_soilgrids"]
        h = r.get("heldout_region") or {}
        skill[k] = dict(target=("log10(ECe dS/m)" if k == "ece" else "log1p(ESP %)"), heldout_region="Levant + Arabian peninsula (lon 30-50, lat 20-38)", n_heldout=h.get("n"), n_heldout_blocks=d.get("n_blocks_test"),
                        r2_heldout=r.get("heldout_region", {}).get("r2_t"), r2_heldout_ci95=r.get("heldout_r2_ci95_block_bootstrap"), rmse_heldout_t=h.get("rmse_t"),
                        r2_block_cv=r["cv_oof"].get("r2_t"), conformal_pi90_coverage_cv=r.get("cv_conformal_coverage"), conformal_pi90_coverage_heldout=r.get("heldout_conformal_coverage"),
                        baseline_global_median_r2_heldout=r.get("baseline_global_median_heldout", {}).get("r2_t"),
                        meaning="weak skill on unseen geography: within-region salinity/sodicity pattern is mostly a regional prior with wide intervals")
    sens = {}
    for row in ev.get("E3_sensitivity", {}).get("rows", []):
        if row["name"].startswith("water allocation") or row["name"].startswith("baseline"):
            sens[row["name"]] = dict(mean_score=round(row["mean_score"], 3), class_flip_rate=round(row["class_flip_rate"], 3))
    return dict(
        assumed_water_allocation_m3_ha_yr=water_cap, feasibility_is_conditional_on_water=True, water_source_availability_mapped=False,
        water_supply=(dict(method="Irrigation water is limited to the renewable water generated locally: annual climatic surplus P - AET from TerraClimate 2011-2020 (mean; year-to-year sd is the uncertainty), 1 mm = 10 m3/ha, taken at ~4 km and compared with each scenario's net irrigation requirement. Effective rainfall is already inside the requirement (net of rain), so no water is counted twice and neighbouring cells are never pooled.",
                           evidence="observed climate; supply and deficit are simulated", resolution_m=4000,
                           upper_bound="the surplus is an upper bound of locally capturable water (no capture or conveyance losses)",
                           not_mapped=["groundwater storage and sustainable-abstraction limits", "fossil aquifers (e.g. Disi)", "national water transfers and canals", "treated wastewater plants", "dams and infrastructure distance", "water rights/licences"],
                           reading="High feasibility means the best scenario's water need is met by local renewable water. Where the need exceeds it, feasibility drops and the water deficit (m3/ha/yr) is the amount that would have to come from sources not mapped here.")
                      if water_cap is None else dict(method="uniform what-if allocation (legacy), not geographic")),
        ui_banner="Feasibility is water-aware: it assumes irrigation can use only the renewable water generated locally (climatic surplus P - AET, ~4 km). External water (transfers, fossil groundwater, treated wastewater) is not mapped, so the deficit shown is what would have to come from elsewhere. All outcomes are simulated, none observed.",
        restoration_outcomes_observed=False, soil_model_heldout_skill=skill, sensitivity_to_water_allocation=(sens if water_cap is not None else {}), mc_draws=mc,
        evidence_classes=EVIDENCE_SUMMARY, effective_resolution_m=config.EFFECTIVE_RESOLUTION_M, grid_resolution_m=config.RES,
        climate_window="TerraClimate 2011-2020 (10 years)", current_class_source=("STAND-IN rule map (not Model 1)" if standin else "Model 1 suitability outputs"), model1_run=m1,
        soilgrids_arid_rmse=dict(ph=0.34, soc_pct=0.55, sand_pct=10.8, clay_pct=9.2, note="SOC has no regional skill (R2~0); depth to bedrock capped at 200 cm and uninformative"))


def write_all(out: Path, region_id: str, rt: dict, cell: dict | None, feats: list, E: dict, standin: bool, water_cap: float, seed: int, seconds: float, suit_dir, mc: dict | None = None) -> dict:
    out = Path(out)
    g = rt["grid"]
    res = dict(paths={}, standin=standin)
    m1 = None
    if suit_dir and (Path(suit_dir) / "run_metadata.json").exists():
        try:
            mm = json.loads((Path(suit_dir) / "run_metadata.json").read_text())
            m1 = dict(model_version=mm.get("model_version"), checkpoint_sha256=mm.get("checkpoint_sha256"), created_at=mm.get("created_at"), grid_resolution_m=mm.get("grid_resolution_m"),
                      effective_resolution_m=mm.get("effective_resolution_m"), confidence_method=mm.get("confidence_method"), polygons="models/suitability/outputs/" + region_id + "/polygons.geojson")
        except Exception:
            m1 = None
    caveats = _caveats(water_cap, mc, standin, m1)
    common = dict(model_version=config.MODEL_VERSION, region=region_id, crs=g.crs, resolution_m=g.res, effective_resolution_m=config.EFFECTIVE_RESOLUTION_M["overall"],
                  evidence="simulated", created=time.strftime("%Y-%m-%dT%H:%M:%S"), current_class_basis=("STAND-IN rule map (Model 1 raster not supplied)" if standin else "Model 1 suitability.tif + polygons.geojson"))
    summ = dict(region=region_id, caveats=caveats)
    if cell is not None:
        write_cog(out / "restoration_feasibility.tif", cell["feas"], g, 0, dict(common, description="restoration feasibility: 0 nodata, 1 not_feasible, 2 low, 3 moderate, 4 high (SIMULATED Monte-Carlo success probability cut at 0.15/0.40/0.70)"), "uint8")
        write_cog(out / "post_restoration_suitability.tif", cell["post"], g, 0, dict(common, description="SIMULATED post-restoration suitability class 1-4 under the best evaluated scenario (modal class); not an observed outcome"), "uint8")
        sc = np.where(cell["feas"] > 0, cell["score"], -1.0).astype("float32")
        write_cog(out / "feasibility_score.tif", sc, g, -1.0, dict(common, description="SIMULATED feasibility score 0-1 (Monte-Carlo success probability), -1 nodata"), "float32")
        write_preview_4326(out / "restoration_feasibility.tif", out / "restoration_feasibility_4326.tif", 0, "uint8")
        write_preview_4326(out / "post_restoration_suitability.tif", out / "post_restoration_suitability_4326.tif", 0, "uint8")
        for f in ("restoration_feasibility.tif", "post_restoration_suitability.tif", "feasibility_score.tif", "restoration_feasibility_4326.tif", "post_restoration_suitability_4326.tif"):
            res["paths"][f] = f
        ha = config.HA_PER_CELL
        codes = cell["feas"]
        summ["raster_cells"] = {config.FEAS_LABELS[c]: dict(cells=int((codes == c).sum()), area_ha=round(float((codes == c).sum() * ha), 1), area_dunum=round(float((codes == c).sum() * ha * config.DUNUM_PER_HA), 0),
                                                        share=round(float((codes == c).sum() / max((codes > 0).sum(), 1)), 4)) for c in (1, 2, 3, 4)}
        summ["raster_best_scenario_cells"] = {engine.SCEN_IDS[k]: int((cell["best_scen"] == k + 1).sum()) for k in range(len(engine.SCEN_IDS))}
        summ["raster_post_class_cells"] = {str(c): int((cell["post"] == c).sum()) for c in (1, 2, 3, 4)}
        summ["raster_class5_not_feasible_cells"] = int(cell["restricted"].sum())
    # polygons
    fc = dict(type="FeatureCollection", name=f"model2-{region_id}", features=feats, properties=dict(note="Model 2 restoration potential; all outcomes simulated/expert_rule; see run_metadata.json", **{k: common[k] for k in ("model_version", "region")}))
    (out / "polygons.geojson").write_text(json.dumps(fc, separators=(",", ":")))
    res["paths"]["polygons.geojson"] = "polygons.geojson"
    cls_names = ["not_feasible", "low", "moderate", "high"]
    by = {k: dict(polygon_count=0, area_ha=0.0, area_dunum=0.0) for k in cls_names}
    for f in feats:
        p = f["properties"]
        c = p["feasibility"]["class"]
        by[c]["polygon_count"] += 1
        by[c]["area_ha"] += p["area_ha"]
        by[c]["area_dunum"] += p["area_dunum"]
    tot = sum(v["area_ha"] for v in by.values()) or 1.0
    for v in by.values():
        v["share"] = round(v["area_ha"] / tot, 4)
        v["area_ha"] = round(v["area_ha"], 1)
        v["area_dunum"] = round(v["area_dunum"], 0)
    summ["polygons_by_feasibility"] = by
    lf_count = {}
    for f in feats:
        for lf in f["properties"]["limiting_factors"]:
            if lf["severity"] >= 0.3:
                lf_count[lf["factor"]] = lf_count.get(lf["factor"], 0) + 1
    summ["polygons_with_severe_limiting_factor(>=0.3)"] = dict(sorted(lf_count.items(), key=lambda kv: -kv[1]))
    bs = {}
    for f in feats:
        b = f["properties"]["feasibility_meta"]["best_scenario"]
        bs[b] = bs.get(b, 0) + 1
    summ["polygons_by_best_scenario"] = bs
    summ["headline"] = dict(n_polygons=len(feats), by_class={k: v["polygon_count"] for k, v in by.items()}, area_ha_by_class={k: v["area_ha"] for k, v in by.items()},
                            water_cap_m3_ha_yr=water_cap, current_class_basis=common["current_class_basis"])
    summ["notes"] = ["Areas in equal-area EPSG:6933; 1 dunum = 1,000 m2 = 0.1 ha.", "Class 5 (restricted) polygons are never restorable: reported as not_feasible with limiting factor 'restriction'.",
                     "All feasibility, post-restoration class, water requirement and time-to-effect values are simulated; none is an observed restoration result.",
                     ("Feasibility is conditional on a uniform what-if water allocation (scenario condition), not on mapped water." if water_cap is not None else
                      "Feasibility uses the renewable water generated locally (climatic surplus P - AET, ~4 km); water SOURCES (groundwater limits, fossil aquifers, transfers, wastewater, dams) are not mapped.")]
    summ["source_studies"] = {k: dict(citation=SOURCES[k]["citation"], url=SOURCES[k]["url"], verification=SOURCES[k]["level"], verified_detail=SOURCES[k]["verified"]) for k in sorted(STUDIES_USED)}
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    res["paths"]["summary.json"] = "summary.json"
    # run metadata
    ck = {}
    try:
        meta = json.loads((config.CKPT_DIR / "soil_models_meta.json").read_text())
        for k, v in meta["models"].items():
            ck[k] = dict(file=f"checkpoints/{v['file']}", sha256=v["sha256"], features=v["features"], trained_on_n=v["trained_on_n"])
    except Exception:
        pass
    params = {k: dict(min=float(np.min(v)), max=float(np.max(v)), mean=float(np.mean(v))) for k, v in E["params"].items() if v is not None}
    rm = dict(model_version=config.MODEL_VERSION, region=region_id, created=common["created"], seed=seed, runtime_seconds=round(seconds, 1),
              checkpoints=ck, grid=dict(crs=g.crs, resolution_m=g.res, width=g.width, height=g.height), effective_resolution_m=config.EFFECTIVE_RESOLUTION_M,
              current_class_basis=common["current_class_basis"], model1_inputs=(rel(Path(suit_dir)) if suit_dir else None), caveats=caveats, model1_run=m1,
              evidence_breakdown=EVIDENCE_SUMMARY, label_basis=dict(
                  ece="measured saturated-paste EC (WoSIS ELCOSP + Hassani 2020 points), topsoil 0-30 cm", esp="measured exchangeable Na / CEC (Hassani 2020 points)",
                  restoration_outcomes="NONE observed: no before/after restoration dataset exists in the sources checked; outcomes are simulated from documented relationships",
                  feasibility_classes="Monte-Carlo success probability cut at expert-rule thresholds (0.15/0.40/0.70)"),
              scenarios={k: dict(name=v["name"], crops=v["crops"], interventions=v["interventions"], water_source=v["source"]) for k, v in engine.SCENARIOS.items()},
              parameter_priors_sampled=params, factor_assumptions=engine.FACTOR_ASSUMPTIONS, monte_carlo=dict(note="outer = parameter draws, inner = input-noise draws; feasibility interval over outer draws"),
              water_reference_allocation_m3_ha_yr=water_cap, source_studies={k: dict(citation=SOURCES[k]["citation"], url=SOURCES[k]["url"], verification=SOURCES[k]["level"]) for k in sorted(STUDIES_USED)},
              limitations=["No real restoration outcome data: agreement with rules measures consistency, not real-world success.", "Water SOURCE availability, groundwater depth/quality, aquifer sustainability and treated-wastewater location are not mapped.",
                           "pH/SOC/texture/CF/depth are third-party ML maps with limited arid skill; SOC has no regional skill in the held-out region (R2~0).",
                           "Salinity/sodicity effective resolution ~1 km; climate/water ~4 km; do not read polygon values below that scale as measurements.",
                           "Wind erosion, flash floods, frost and market/economic factors are not modelled."])
    (out / "run_metadata.json").write_text(json.dumps(rm, indent=1))
    res["paths"]["run_metadata.json"] = "run_metadata.json"
    res["summary"] = summ
    return res
