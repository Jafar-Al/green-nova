"""Raster/polygon/summary/metadata writers for Model 1 (called from infer.run_inference)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pyproj
import rasterio
from rasterio import features as rf
from rasterio.enums import Resampling
from rasterio.shutil import copy as rio_copy
from rasterio.warp import reproject
from scipy import ndimage as ndi
from shapely import set_precision
from shapely.geometry import mapping, shape
from shapely.ops import transform

from . import __version__, config, features as F, rules

CONF_METHOD = ("Monte-Carlo agreement: share of 24 draws (SoilGrids/SOTWIS/terrain/climate inputs perturbed by documented "
               "error models, ML ensemble member and fusion thresholds resampled) that reproduce the central class. "
               "It measures robustness to input uncertainty, NOT validated map accuracy.")
LABEL_BASIS = {
    "1": "rule-derived (FAO-style limiting-factor evaluation) + ML cultivation-likelihood evidence; never field-verified",
    "2": "rule-derived + ML evidence; includes land observed under cultivation in 2021 (observed, WorldCover+IO LULC)",
    "3": "rule-derived: reversible/partially reversible severe limitation(s); feasibility NOT assessed here (see Model 2)",
    "4": "rule-derived: irreversible limitation (steepness, stoniness, hyper-aridity <100 mm/yr, gypsic, temperature) or ML-unsupported",
    "5": "observed/mapped restrictions (OpenStreetMap protected/military/quarry/cemetery/built-up/airport/water/heritage); NOT WDPA/cadastre",
}
SOURCES = [
    dict(name="Copernicus DEM GLO-30", role="covariate (slope, terrain)", vintage="2010-2015 acquisitions, 2021 release", resolution_m=30,
         license="Copernicus free and open", url="https://planetarycomputer.microsoft.com/dataset/cop-dem-glo-30"),
    dict(name="ISRIC SoilGrids 2.0", role="covariate (pH, SOC, texture, CEC, coarse fragments) - ML-predicted soil maps", vintage="2020 release",
         resolution_m=250, license="CC BY 4.0", url="https://www.isric.org/explore/soilgrids"),
    dict(name="SOTWIS Jordan v1.0 (ISRIC)", role="covariate (EC, ESP, gypsum, CaCO3, drainage) - legacy 1:500 000 survey units",
         vintage="survey 1996, published 2013", resolution_m=5000, license="CC BY 3.0 per data hub (zip text: non-commercial) - flagged",
         url="https://data.isric.org/geonetwork/srv/api/records/943d57ef-1eaf-4528-8508-9c81c1c2fcd3"),
    dict(name="WorldClim 2.1 precipitation", role="covariate (rainfall)", vintage="1970-2000 normals", resolution_m=1000,
         license="CC BY 4.0", url="https://www.worldclim.org/data/worldclim21.html"),
    dict(name="TerraClimate", role="covariate (PET, deficit, temperature; lapse-rate downscaled)", vintage="2011-2020", resolution_m=4000,
         license="CC0 (per Planetary Computer)", url="https://planetarycomputer.microsoft.com/dataset/terraclimate"),
    dict(name="JRC Global Surface Water", role="covariate (water occurrence)", vintage="1984-2021", resolution_m=30,
         license="Copernicus free and open", url="https://planetarycomputer.microsoft.com/dataset/jrc-gsw"),
    dict(name="ESA WorldCover 2020 v100 / 2021 v200", role="OBSERVED label (cropland) + exclusion (built-up, water)", vintage="2020, 2021",
         resolution_m=10, license="CC BY 4.0", url="https://planetarycomputer.microsoft.com/dataset/esa-worldcover"),
    dict(name="Impact Observatory 10 m annual LULC v02", role="OBSERVED label (cropland)", vintage="2017, 2021, 2023", resolution_m=10,
         license="CC BY 4.0", url="https://planetarycomputer.microsoft.com/dataset/io-lulc-annual-v02"),
    dict(name="OpenStreetMap (Geofabrik Jordan extract)", role="restriction masks (class 5)", vintage="2026-11-21", resolution_m=None,
         license="ODbL 1.0", url="https://download.geofabrik.de/asia/jordan-latest-free.shp.zip"),
    dict(name="geoBoundaries gbOpen JOR ADM1", role="region boundaries", vintage="2006 representation, build 2023", resolution_m=None,
         license="CC BY 2.5", url="https://www.geoboundaries.org/"),
]


def _clean(o):
    """Replace NaN/inf by None and numpy scalars by Python types so the output is strict JSON."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o


def _cog(path: Path, arr: np.ndarray, grid_transform, crs, nodata, resampling="NEAREST", tags=None):
    arr = arr[None] if arr.ndim == 2 else arr
    tmp = path.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=arr.shape[0], dtype=arr.dtype,
                       crs=crs, transform=grid_transform, nodata=nodata, tiled=True, blockxsize=256, blockysize=256,
                       compress="deflate") as dst:
        dst.write(arr)
        if tags:
            dst.update_tags(**tags)
    rio_copy(tmp, path, driver="COG", compress="DEFLATE", overview_resampling=resampling, blocksize=256)
    tmp.unlink()


def build_outputs(*, model, rt, sub, sub_mask, win, cls, conf, probs, reason, p_ml, sev, out: Path, region_id, mmu_cells, progress,
                  device, mc_draws, geometry_query):
    from .infer import InferenceResult
    H, W = cls.shape
    R0, R1, C0, C1 = win
    # ---------------------------------------------------------------- MMU sieve (class 5 is protected from merging)
    base = np.where(cls == 5, 0, cls).astype("uint8")
    cls_s = rf.sieve(base, size=mmu_cells, connectivity=8, mask=(base > 0))
    cls_s = np.where(cls == 5, 5, cls_s).astype("uint8")
    cls_s[~sub_mask] = 0
    # ---------------------------------------------------------------- rasters
    progress(0.74, "writing GeoTIFFs")
    meta_tags = dict(model_version=model.version, confidence="uint8 0-100 (Monte-Carlo agreement), nodata 255",
                     classes="1 suitable,2 suitable with limitations,3 requires reclamation,4 unsuitable,5 excluded; 0 nodata")
    _cog(out / "suitability.tif", cls_s, sub.transform, sub.crs, 0, "NEAREST", meta_tags)
    _cog(out / "confidence.tif", np.where(cls_s > 0, conf, 255).astype("uint8"), sub.transform, sub.crs, 255, "AVERAGE", meta_tags)
    _cog(out / "class_probabilities.tif", np.where(cls_s[None] > 0, probs, 0).astype("uint8"), sub.transform, sub.crs, None, "AVERAGE",
         dict(bands="percent probability of classes 1..5 (Monte-Carlo frequency)"))
    # web-friendly EPSG:4326 preview of the class raster
    tr4 = pyproj.Transformer.from_crs(sub.crs, 4326, always_xy=True)
    l, b, r, t = sub.bounds
    xs, ys = zip(*[tr4.transform(x, y) for x, y in ((l, b), (l, t), (r, b), (r, t))])
    res4 = 0.001
    w4, h4 = int(np.ceil((max(xs) - min(xs)) / res4)), int(np.ceil((max(ys) - min(ys)) / res4))
    from rasterio.transform import from_origin
    t4 = from_origin(min(xs), max(ys), res4, res4)
    pv = np.zeros((h4, w4), "uint8")
    reproject(cls_s, pv, src_transform=sub.transform, src_crs=sub.crs, dst_transform=t4, dst_crs="EPSG:4326",
              resampling=Resampling.nearest, src_nodata=0, dst_nodata=0)
    _cog(out / "suitability_wgs84.tif", pv, t4, "EPSG:4326", 0, "NEAREST", meta_tags)

    # ---------------------------------------------------------------- polygons (connected components per class)
    progress(0.78, "extracting polygons")
    ids = np.zeros((H, W), "int32")
    off = 0
    struct = np.ones((3, 3), dtype=int)
    for k in range(1, 6):
        lab, n = ndi.label(cls_s == k, structure=struct)
        ids[lab > 0] = lab[lab > 0] + off
        off += n
    n_poly = off
    flat = ids.ravel()
    cnt = np.bincount(flat, minlength=n_poly + 1).astype("float64")
    area_cells = cnt[1:]
    cls_of = np.zeros(n_poly + 1, "uint8")
    cls_of[flat] = cls_s.ravel()          # last write wins; constant per id by construction
    # zonal means of layers
    def zmean(arr2d, weights=None):
        a = arr2d.ravel().astype("float64")
        v = np.isfinite(a)
        s = np.bincount(flat, weights=np.where(v, a, 0.0), minlength=n_poly + 1)
        c = np.bincount(flat, weights=v.astype("float64"), minlength=n_poly + 1)
        return (s / np.maximum(c, 1))[1:]

    progress(0.82, "zonal statistics")
    zl = {}
    for name in F.RULE_INPUTS:
        zl[name] = zmean(rt.mm[rt.layers[name], R0:R1, C0:C1])
    for name in ("cult_frac", "wc2021_built", "ph_sd"):
        zl[name] = zmean(rt.mm[rt.layers[name], R0:R1, C0:C1])
    zl["p_ml"] = zmean(p_ml.astype("float32"))
    zl["conf"] = zmean(np.where(conf == 255, np.nan, conf / 100.0))
    zprob = [zmean(probs[k] / 100.0) for k in range(5)]
    zreason = [zmean((reason == k).astype("float32")) for k in (1, 2, 3)]
    zsev2 = [zmean((sev[i] >= 2).astype("float32")) for i in range(sev.shape[0])]
    restr = rt.mm[rt.layers["restriction_code"], R0:R1, C0:C1].astype("uint8")
    zr = np.stack([np.bincount(flat, weights=(restr.ravel() == c).astype("float64"), minlength=n_poly + 1)[1:] for c in range(1, 9)], 1)
    # rule evaluation on polygon means (values, ratings, severities)
    covp = {k: zl[k].astype("float32") for k in F.RULE_INPUTS}
    covp["restriction_code"] = np.zeros(n_poly, "uint8")
    ev = rules.evaluate(covp)
    R = ev["R"]; sevp = ev["sev"]; valp = ev["values"]

    # ---------------------------------------------------------------- geometry
    progress(0.86, "building GeoJSON")
    to4326 = pyproj.Transformer.from_crs(sub.crs, 4326, always_xy=True).transform
    geoms = {}
    for g, v in rf.shapes(ids, mask=ids > 0, transform=sub.transform, connectivity=8):
        geoms[int(v)] = shape(g)
    order = sorted(geoms, key=lambda i: (cls_of[i], -geoms[i].centroid.y, geoms[i].centroid.x))
    feats = []
    prov = dict(model_version=model.version, label_basis=LABEL_BASIS, data_sources=[s["name"] for s in SOURCES])
    ph_hi, ph_lo = model.p_hi, model.p_lo
    for n_, pid in enumerate(order, start=1):
        i = pid - 1
        c = int(cls_of[pid])
        g6933 = geoms[pid]
        cen = transform(to4326, g6933.centroid)
        g = set_precision(transform(to4326, g6933.simplify(50.0, preserve_topology=True)), 1e-6)
        ha = float(area_cells[i] * config.HA_PER_CELL)
        deficits = np.array([max(0.0, 100.0 - float(R[f, i])) for f in range(len(rules.FACTORS))])
        tot = deficits.sum() if deficits.sum() > 0 else 1.0
        facs = []
        if c == 5:
            tot_r = zr[i].sum()
            top = int(zr[i].argmax()) + 1
            kinds = ", ".join(rules.RESTRICTION_NAMES[j + 1] for j in np.argsort(-zr[i]) if zr[i][j] > 0)
            facs.append(dict(name="legal_environmental_restriction", value=round(float(tot_r / max(area_cells[i], 1)), 3),
                             unit="share of polygon area under mapped restriction", status="restricted", evidence="observed",
                             note=f"mapped restriction type(s): {kinds or rules.RESTRICTION_NAMES[top]} (OpenStreetMap/WorldCover; not the official WDPA/cadastre)",
                             importance=1.0, native_resolution_m=100))
        for f_i, fac in enumerate(rules.FACTORS):
            s = int(sevp[f_i, i]); r = float(R[f_i, i]); v = float(valp[f_i, i])
            facs.append(dict(
                name=fac.key, value=round(v, 3), unit=fac.unit, status=rules.status_from_sev(s),
                evidence=fac.evidence,
                note=(f"{fac.label}: polygon mean {v:.2f} {fac.unit}; rating {r:.0f}/100 (severity {s}); "
                      f"{zsev2[f_i][i] * 100:.0f}% of cells severity>=2; reversibility: {fac.reversibility}; "
                      f"source: {fac.source} (~{fac.native_res_m:.0f} m)" + (f"; {fac.note}" if fac.note else "")),
                importance=round(float(deficits[f_i] / tot), 3), native_resolution_m=fac.native_res_m))
        pml = float(zl["p_ml"][i])
        facs.append(dict(name="ml_cultivation_likelihood", value=round(pml, 4), unit="calibrated probability",
                         status="favourable" if pml >= ph_hi else ("limiting" if pml <= ph_lo else "marginal"), evidence="ml_predicted",
                         note=(f"probability that land with these terrain/soil/climate conditions is cultivated in Jordan today "
                               f"(spatially cross-validated LightGBM ensemble, isotonic-calibrated); NOT a suitability probability"),
                         importance=0.0, native_resolution_m=250))
        cf = float(zl["cult_frac"][i])
        if cf >= 0.05:
            facs.append(dict(name="observed_cultivation_2021", value=round(cf, 3), unit="cropland fraction", status="favourable" if cf >= 0.3 else "marginal",
                             evidence="observed", note="mean of ESA WorldCover 2021 and Impact Observatory 2021 cropland fractions (land-cover products, not field survey)",
                             importance=0.0, native_resolution_m=10))
        props = dict(
            id=f"m1-{region_id.replace('jo-', 'jo-')}-{n_}", class_code=c, class_label=config.CLASS_LABELS[c],
            area_ha=round(ha, 2), area_dunum=round(ha * config.DUNUM_PER_HA, 1),
            confidence=round(float(zl["conf"][i]), 3), confidence_method=CONF_METHOD,
            class_probabilities={str(k + 1): round(float(zprob[k][i]), 3) for k in range(5)},
            factors=facs, centroid=[round(cen.x, 6), round(cen.y, 6)], effective_resolution_m=config.EFFECTIVE_RESOLUTION_M,
            provenance=prov,
            grid_resolution_m=config.RES, mmu_ha=mmu_cells * config.HA_PER_CELL,
            decision_shares=dict(ml_upgrade=round(float(zreason[0][i]), 3), ml_downgrade=round(float(zreason[1][i]), 3),
                                 observed_cultivation_override=round(float(zreason[2][i]), 3)),
            limiting_factor=rules.FACTOR_KEYS[int(ev["limiting"][i])] if c != 5 else "legal_environmental_restriction")
        feats.append(dict(type="Feature", geometry=mapping(g), properties=props))
    gj = dict(type="FeatureCollection", features=feats)
    (out / "polygons.geojson").write_text(json.dumps(_clean(gj), separators=(",", ":"), allow_nan=False), encoding="utf-8")

    # ---------------------------------------------------------------- summary + metadata
    progress(0.95, "summary and metadata")
    classified = float((cls_s > 0).sum())
    summ = {}
    for k in range(1, 6):
        m = cls_s == k
        ha = float(m.sum() * config.HA_PER_CELL)
        summ[str(k)] = dict(label=config.CLASS_LABELS[k], polygon_count=int((cls_of[1:] == k).sum()), area_ha=round(ha, 1),
                            area_dunum=round(ha * config.DUNUM_PER_HA, 1), share=round(float(m.sum() / max(classified, 1)), 5))
    summary = dict(region_id=region_id, query="geometry" if geometry_query else "full_region", classes=summ,
                   total_area_ha=round(classified * config.HA_PER_CELL, 1), total_area_dunum=round(classified * config.HA_PER_CELL * 10, 1),
                   area_basis="cell counts on a 100 m EPSG:6933 equal-area grid (1 cell = 1 ha); 1 dunum = 1,000 m2 = 0.1 ha",
                   mean_confidence=round(float(np.mean(conf[conf != 255]) / 100.0), 4) if (conf != 255).any() else None)
    (out / "summary.json").write_text(json.dumps(_clean(summary), indent=1, allow_nan=False))
    metadata = dict(
        model_version=model.version, package_version=__version__, checkpoint_sha256=model.sha256, region_id=region_id,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), device_requested=device, device_used="cpu",
        working_crs=config.WORK_CRS, grid_resolution_m=config.RES, effective_resolution_m=config.EFFECTIVE_RESOLUTION_M,
        effective_resolution_note="classes 1-4 are driven by climate (1-4 km), SOTWIS 1:500 000 map units and 250 m SoilGrids; the 100 m grid is a sampling grid. Class 5 uses vector restrictions at their mapped precision.",
        raster_files=dict(suitability="uint8, 0=nodata, 1..5 classes (after MMU sieve)", confidence="uint8 0-100, nodata 255",
                          class_probabilities="uint8 percent, 5 bands", suitability_wgs84="EPSG:4326 preview, ~0.001 deg"),
        confidence_method=CONF_METHOD, label_basis=LABEL_BASIS, data_sources=SOURCES,
        acquisition_date_range=dict(sentinel2="not used by v0.1 checkpoint (see docs/MODEL1_SUITABILITY.md)", dem="2010-2015", worldcover="2020-2021",
                                    io_lulc="2017-2023", climate="1970-2000 (WorldClim), 2011-2020 (TerraClimate)", osm="2026-11-21"),
        mc_draws=mc_draws, mmu_ha=mmu_cells * config.HA_PER_CELL, polygon_simplify_tolerance_m=50,
        mc_error_model="SoilGrids pH/SOC/sand/clay N(mu,(Q95-Q05)/3.29); other SoilGrids lognormal 0.25; SOTWIS lognormal 0.5; slope lognormal 0.15; rainfall lognormal 0.20; temperature N(0,1 degC)",
        fusion_thresholds=dict(P_HI=model.p_hi, P_LO=model.p_lo), deterministic=True,
        notes=["Suitability classes are rule-derived (FAO-style) with ML and observed-cultivation evidence; no field-verified 5-class ground truth exists.",
               "Irrigation water availability (groundwater, licences) is NOT modelled; class 4 in <100 mm/yr land means no rainfed option, not that irrigation is impossible.",
               "Restrictions come from OpenStreetMap/WorldCover and are incomplete; always verify legal status before decisions."])
    (out / "run_metadata.json").write_text(json.dumps(_clean(metadata), indent=1, allow_nan=False))
    paths = {k: str(out / v) for k, v in dict(suitability="suitability.tif", confidence="confidence.tif", polygons="polygons.geojson",
                                              summary="summary.json", run_metadata="run_metadata.json",
                                              class_probabilities="class_probabilities.tif", suitability_wgs84="suitability_wgs84.tif").items()}
    return InferenceResult(paths=paths, summary=summary, metadata=metadata)
