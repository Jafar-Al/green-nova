"""Model 2 inference: restoration feasibility for a region, a set of Model 1 polygons, or an arbitrary GeoJSON geometry.

CLI   : python -m models.restoration.infer --region jo-maan --suitability-dir models/suitability/outputs/jo-maan --out <dir> [--polygon-ids a b c] [--geometry file.geojson]
Python: from models.restoration.infer import run_region, analyze_geometry, load_runtime
        res = run_region("jo-maan", suitability_dir=..., out_dir=..., polygon_ids=None, progress=lambda f, msg: ...)

No network, no raw data, no retraining: everything comes from runtime_data/<region>/ (stack.npz + checkpoints/*.txt are used at BUILD time only;
inference uses the pre-computed stack, the crop/intervention tables and parameters in this package).  Deterministic for a given seed.
Output paths are relative to `out_dir`; no absolute local paths are written into any output file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import shapely

from . import assemble, config, engine, outputs, stack, units
from .knowledge import crops as K
from .knowledge.sources import SOURCES


class RestorationError(Exception):
    """Base class for typed inference errors."""


class RuntimeDataMissing(RestorationError):
    pass


class GeometryError(RestorationError):
    pass


Progress = Callable[[float, str], None]
RUNTIME = config.MODEL_DIR / "runtime_data"


def _noop(f, m):
    pass


_RT = {}


def load_runtime(region_id: str = "jo-maan", runtime_dir: Optional[Path] = None) -> dict:
    """Load (once) the region stack. Raises RuntimeDataMissing with a relative path in the message."""
    key = (region_id, str(runtime_dir))
    if key in _RT:
        return _RT[key]
    d = Path(runtime_dir) if runtime_dir else RUNTIME / region_id
    p = d / "stack.npz"
    if not p.exists():
        raise RuntimeDataMissing(f"runtime stack not found: runtime_data/{region_id}/stack.npz")
    grid, mask, layers, climate, meta = stack.load_stack(p)
    _RT[key] = dict(grid=grid, mask=mask, layers=layers, climate=climate, meta=meta, path=p)
    return _RT[key]


# ------------------------------------------------------------------ current-class handling
def standin_class(rt: dict) -> np.ndarray:
    """Documented stand-in for Model 1 (used only when no Model 1 raster is available): class 3 if soil conditions alone would allow S2 or better
    for rain-fed barley once water is supplied, else class 4.  NOT Model 1 output."""
    L = rt["layers"]
    g = rt["grid"]
    m = rt["mask"]
    idx = np.where(m)
    lon, lat = units.cell_lonlat(g, idx[0], idx[1])
    clim = units.interp_climate(rt["climate"], lon, lat)
    v = {k: a[idx] for k, a in L.items()}
    U = units.units_from_values(v, clim)
    c = K.CROPS["barley"]
    ry_soil = (engine.ry_sal(c, U.ece, 1.0) * engine.ry_esp(c, U.esp, 1.0) * engine.ry_ph(U.ph) * engine.ry_soc(U.soc) * engine.ry_cf(U.cf) * engine.ry_tex(U.sand, U.clay)
               * engine.ry_depth(c, U.depth) * engine.ry_slope(U.slope, False, 25.0, U.depth))
    from . import hydro
    kc = hydro.monthly_kc(c)
    wr = (U.eto_m * kc[:, None]).sum(0)
    sp = (U.ppt_m * (kc > 0)[:, None]).sum(0) / np.maximum(U.ppt_m.sum(0), 1e-3)
    frac = np.minimum(1.0, U.p67 * sp / np.maximum(wr, 1.0))
    ry_now = ry_soil * frac
    cls = np.where(ry_now >= 0.8, 1, np.where(ry_now >= 0.6, 2, np.where(ry_soil >= 0.6, 3, 4))).astype("uint8")
    out = np.zeros(g.shape, "uint8")
    out[idx] = cls
    return out


def read_m1_class_raster(suit_dir: Path, grid: stack.Grid) -> Optional[np.ndarray]:
    p = Path(suit_dir) / "suitability.tif"
    if not p.exists():
        return None
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject
    dst = np.zeros(grid.shape, "uint8")
    with rasterio.open(p) as s:
        reproject(rasterio.band(s, 1), dst, dst_transform=grid.transform, dst_crs=grid.crs, src_nodata=0, dst_nodata=0, resampling=Resampling.mode)
    return dst


# ------------------------------------------------------------------ cell raster run
def run_cells(rt: dict, cls_raster: np.ndarray, progress: Progress = _noop, J: int = 16, I: int = 4, water_cap: float = 8000.0, seed: int = config.SEED, classes=(3, 4)):
    g, L = rt["grid"], rt["layers"]
    cand = rt["mask"] & np.isin(cls_raster, list(classes))
    restricted_cells = rt["mask"] & (cls_raster == 5)
    idx = np.where(cand)
    n = len(idx[0])
    if n == 0:
        raise GeometryError("no candidate (class 3-4) cells in the region")
    lon, lat = units.cell_lonlat(g, idx[0], idx[1])
    clim = units.interp_climate(rt["climate"], lon, lat)
    v = {k: a[idx] for k, a in L.items()}
    U = units.units_from_values(v, clim)
    progress(0.05, f"evaluating {n} candidate cells")
    E = engine.evaluate(U, J=J, I=I, seed=seed, water_cap=water_cap, progress=lambda f, m: progress(0.05 + 0.65 * f, m))
    score = np.zeros(g.shape, "float32"); lo = score.copy(); hi = score.copy()
    score[idx], lo[idx], hi[idx] = E["score"], E["lo"], E["hi"]
    fcode = np.zeros(g.shape, "uint8")
    fcode[idx] = engine.feasibility_class(E["score"], config.FEAS_CUTS)
    fcode[restricted_cells] = 1
    # best-scenario modal post-restoration class
    bs = E["best_scen"].astype(int)
    post = np.zeros(g.shape, "uint8")
    cp = E["scen_class_p"][bs, :, np.arange(n)]            # (n,4)
    post[idx] = (cp.argmax(1) + 1).astype("uint8")
    best = np.zeros(g.shape, "uint8")
    best[idx] = (bs + 1).astype("uint8")
    return dict(feas=fcode, score=score, lo=lo, hi=hi, post=post, best_scen=best, idx=idx, n=n, E=E, cand=cand, restricted=restricted_cells)


# ------------------------------------------------------------------ polygon run
def _polys_from_raster(cls_raster, grid, mask, classes=(3, 4)):
    from rasterio import features as rf
    from shapely.geometry import shape
    m = np.isin(cls_raster, classes) & mask
    feats = []
    for geom, val in rf.shapes(cls_raster.astype("uint8"), mask=m, transform=grid.transform):
        feats.append((shape(geom), int(val)))
    return feats


def run_polygons(rt: dict, polys: list, progress: Progress = _noop, J: int = 32, I: int = 6, water_cap: float = 8000.0, seed: int = config.SEED, region_id="jo-maan"):
    """polys: list of dict(id, geom (shapely, EPSG:4326), class_code, source_props). Returns list of GeoJSON-like feature dicts (contract properties)."""
    import geopandas as gpd
    g, L = rt["grid"], rt["layers"]
    gdf = gpd.GeoDataFrame({"pid": [p["id"] for p in polys]}, geometry=[p["geom"] for p in polys], crs=4326)
    gproj = gdf.to_crs(g.crs)
    area_ha = (gproj.geometry.area / 10_000.0).to_numpy()
    progress(0.05, "zonal statistics")
    layers = dict(L)
    means, sds, ncell, sub = units.zonal_stats(layers, g, list(gproj.geometry), [p["id"] for p in polys])
    cent = gproj.geometry.centroid.to_crs(4326)
    lon, lat = cent.x.to_numpy(), cent.y.to_numpy()
    clim = units.interp_climate(rt["climate"], lon, lat)
    extra = dict(ece_lsd=np.nan_to_num(sds["ece_log10"], nan=0.0) if "ece_log10" in sds else 0.0, esp_sd=np.nan_to_num(sds["esp"], nan=0.0))
    # polygon-level: ECe central value = geometric-style mean in log space
    v = {k: means[k] for k in means}
    if "ece_log10" in means:
        v["ece"] = 10 ** means["ece_log10"]
    cls_codes = np.array([p["class_code"] for p in polys])
    U = units.units_from_values(v, clim, restricted=(cls_codes == 5), extra_unc=extra)
    progress(0.15, f"Monte-Carlo feasibility for {len(polys)} polygons")
    E = engine.evaluate(U, J=J, I=I, seed=seed, water_cap=water_cap, progress=lambda f, m: progress(0.15 + 0.6 * f, m))
    ctx = dict(p_mean=clim["p_mean"], current_class=cls_codes)
    feats = []
    for i, p in enumerate(polys):
        props = assemble.build_properties(U, E, i, ctx, config.FEAS_CUTS, water_cap)
        props.update(id=f"m2-{region_id}-{i + 1}", source_polygon_id=p["id"], area_ha=round(float(area_ha[i]), 3), area_dunum=round(float(area_ha[i]) * config.DUNUM_PER_HA, 2))
        props["soil"] = assemble.soil_block(v, i, U)
        el = float(v["elev_m"][i]) if "elev_m" in v and np.isfinite(v["elev_m"][i]) else None
        from . import erosion
        ei, _ = erosion.erosion_index(np.array([U.slope[i]]), np.array([U.sand[i]]), np.array([max(100 - U.sand[i] - U.clay[i], 0)]), np.array([U.clay[i]]), np.array([U.soc[i]]), np.array([clim["p_mean"][i]]))
        props["terrain"] = dict(elevation_m=dict(value=None if el is None else round(el, 0), unit="m", evidence="observed"), slope_deg=dict(value=round(float(U.slope[i]), 2), unit="deg", evidence="observed"),
                                erosion_risk=dict(value=round(float(ei[0]), 3), evidence="expert_rule", note="relative RUSLE-type index 0-1, not t/ha/yr"))
        props["climate"] = dict(rainfall_mm_yr=dict(value=round(float(clim["p_mean"][i]), 0), evidence="observed", note="TerraClimate 2011-2020 mean (~4 km)"),
                                rainfall_2_in_3_years_mm=dict(value=round(float(U.p67[i]), 0), evidence="observed"),
                                temp_mean_c=dict(value=round(float(clim["t_mean"][i]), 1) if "t_mean" in clim else None, evidence="observed"),
                                eto_mm_yr=dict(value=round(float(U.eto_m[:, i].sum()), 0), evidence="observed", note="TerraClimate PM reference ET"))
        props["effective_resolution_m"] = config.EFFECTIVE_RESOLUTION_M["overall"]
        props["sub_cell_polygon"] = bool(sub[i])
        props["n_grid_cells"] = int(ncell[i])
        props["provenance"] = dict(model_version=config.MODEL_VERSION, evidence_summary=outputs.EVIDENCE_SUMMARY, data_sources=outputs.DATA_SOURCES_SHORT,
                                   source_studies=sorted(outputs.STUDIES_USED))
        feats.append(dict(type="Feature", geometry=json.loads(shapely.to_geojson(shapely.set_precision(gdf.geometry.iloc[i], 1e-6))), properties=props))
        if i % 500 == 0:
            progress(0.75 + 0.2 * i / max(1, len(polys)), f"assembling polygon {i}/{len(polys)}")
    return feats, E, U


def load_m1_polygons(suit_dir: Path, polygon_ids=None, classes=(3, 4, 5)):
    import geopandas as gpd
    p = Path(suit_dir) / "polygons.geojson"
    if not p.exists():
        return None
    g = gpd.read_file(p)
    if "class_code" not in g.columns or "id" not in g.columns:
        raise GeometryError("Model 1 polygons.geojson lacks id/class_code")
    g = g[g["class_code"].isin(classes)]
    if polygon_ids:
        g = g[g["id"].isin(list(polygon_ids))]
        if len(g) == 0:
            raise GeometryError("none of the requested polygon ids found among Model 1 class 3-5 polygons")
    return [dict(id=str(r["id"]), geom=r.geometry, class_code=int(r["class_code"])) for _, r in g.to_crs(4326).iterrows()]


def analyze_geometry(geometry: dict, region_id: str = "jo-maan", current_class: int = 4, progress: Progress = _noop, water_cap: float = 8000.0, runtime_dir=None):
    """Feasibility for one arbitrary GeoJSON geometry (EPSG:4326). Returns a contract-shaped Feature dict. Seconds on cached features."""
    from shapely.geometry import shape
    try:
        geom = shape(geometry)
    except Exception as e:  # noqa
        raise GeometryError(f"invalid geometry: {e}")
    if geom.is_empty:
        raise GeometryError("empty geometry")
    rt = load_runtime(region_id, runtime_dir)
    feats, E, U = run_polygons(rt, [dict(id="query", geom=geom, class_code=current_class)], progress=progress, water_cap=water_cap, region_id=region_id)
    return feats[0]


def run_region(region_id: str = "jo-maan", suitability_dir: Optional[str] = None, out_dir: Optional[str] = None, polygon_ids=None, geometry=None, progress: Progress = _noop,
               water_cap: float = 8000.0, runtime_dir=None, seed: int = config.SEED, include_class2: bool = False, raster: bool = True,
               mc_outer: int = 16, mc_inner: int = 4, mc_outer_poly: int = 32, mc_inner_poly: int = 6) -> dict:
    t0 = time.time()
    rt = load_runtime(region_id, runtime_dir)
    out = Path(out_dir) if out_dir else config.OUT_DIR / region_id
    out.mkdir(parents=True, exist_ok=True)
    g = rt["grid"]
    classes = (2, 3, 4, 5) if include_class2 else (3, 4, 5)
    m1_poly = load_m1_polygons(suitability_dir, polygon_ids, classes) if suitability_dir else None
    m1_cls = read_m1_class_raster(Path(suitability_dir), g) if suitability_dir else None
    standin = m1_poly is None or m1_cls is None
    if m1_cls is None:
        progress(0.01, "Model 1 raster not found: using documented stand-in current-class map")
        m1_cls = standin_class(rt)
    result = dict(paths={}, summary={}, standin=standin)
    if geometry is not None:
        gj = json.loads(Path(geometry).read_text()) if isinstance(geometry, (str, Path)) else geometry
        if gj.get("type") == "FeatureCollection":
            gj = gj["features"][0]["geometry"]
        elif gj.get("type") == "Feature":
            gj = gj["geometry"]
        feat = analyze_geometry(gj, region_id, progress=progress, water_cap=water_cap, runtime_dir=runtime_dir)
        (out / "geometry_result.json").write_text(json.dumps(feat))
        result["paths"]["geometry_result"] = "geometry_result.json"
        result["feature"] = feat
        return result
    cell = None
    if raster and polygon_ids is None:
        cell = run_cells(rt, m1_cls, progress=lambda f, m: progress(0.02 + 0.5 * f, m), water_cap=water_cap, seed=seed, J=mc_outer, I=mc_inner,
                         classes=(2, 3, 4) if include_class2 else (3, 4))
    if m1_poly is None:
        feats0 = _polys_from_raster(m1_cls, g, rt["mask"])
        import geopandas as gpd
        from shapely.ops import transform
        from pyproj import Transformer
        tr = Transformer.from_crs(g.crs, 4326, always_xy=True).transform
        m1_poly = [dict(id=f"standin-{k + 1}", geom=transform(tr, geom), class_code=val) for k, (geom, val) in enumerate(feats0)]
        if polygon_ids:
            m1_poly = [p for p in m1_poly if p["id"] in set(polygon_ids)]
    feats, E, U = run_polygons(rt, m1_poly, progress=lambda f, m: progress(0.55 + 0.4 * f, m), water_cap=water_cap, seed=seed, region_id=region_id, J=mc_outer_poly, I=mc_inner_poly)
    mc = dict(raster_outer_param_draws=mc_outer if cell is not None else None, raster_inner_input_draws=mc_inner if cell is not None else None,
              raster_draws_per_cell=(mc_outer * mc_inner) if cell is not None else None, raster_cells_evaluated=int(cell["n"]) if cell is not None else 0,
              polygon_outer_param_draws=mc_outer_poly, polygon_inner_input_draws=mc_inner_poly, polygon_draws_per_polygon=mc_outer_poly * mc_inner_poly, n_polygons=len(feats), seed=seed)
    result = outputs.write_all(out, region_id, rt, cell, feats, E, standin, water_cap, seed, time.time() - t0, suitability_dir, mc=mc)
    progress(1.0, "done")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="GREEN NOVA AI Model 2: agricultural land restoration potential")
    ap.add_argument("--region", default="jo-maan")
    ap.add_argument("--suitability-dir", default=None, help="Model 1 outputs folder (polygons.geojson, suitability.tif)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--polygon-ids", nargs="*", default=None)
    ap.add_argument("--geometry", default=None, help="GeoJSON file (EPSG:4326) of one area to analyse")
    ap.add_argument("--water-cap", type=float, default=8000.0, help="reference water allocation m3/ha/yr (scenario condition)")
    ap.add_argument("--no-raster", action="store_true")
    ap.add_argument("--mc-outer", type=int, default=16)
    ap.add_argument("--mc-inner", type=int, default=4)
    ap.add_argument("--include-class2", action="store_true")
    a = ap.parse_args(argv)

    def prog(f, m):
        print(f"[{100 * f:5.1f}%] {m}", flush=True)
    res = run_region(a.region, a.suitability_dir, a.out, a.polygon_ids, a.geometry, prog, a.water_cap, include_class2=a.include_class2, raster=not a.no_raster, mc_outer=a.mc_outer, mc_inner=a.mc_inner)
    print(json.dumps(res.get("summary", {}).get("headline", {}), indent=1))


if __name__ == "__main__":
    main()
