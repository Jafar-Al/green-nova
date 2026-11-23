"""Model 1 inference: region / sub-area -> suitability.tif, confidence.tif, polygons.geojson, summary.json, run_metadata.json.

CLI : python -m models.suitability.infer --region jo-maan --out <dir> [--geometry <geojson>] [--device cuda|cpu]
API : run_inference(region_id, out_dir, geometry=None, device="cpu", progress=None, ...) -> InferenceResult

No network access; all inputs come from the packaged runtime folder (see package_runtime.py) and the checkpoint.
Outputs never contain absolute local paths. Deterministic: counter-based Monte-Carlo noise keyed on global cell ids.
LightGBM inference is CPU-only; `device="cuda"` is accepted and recorded but the GBM runs on CPU (no GPU is needed).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import __version__, config, features as F, fusion, rules

ProgressCallback = Callable[[float, str], None]
CKPT_NAME = "model1_suitability_v0.1.pkl"
CHUNK_ROWS = 80


class Model1Error(Exception):
    """Base class for typed Model 1 errors."""


class RegionNotFoundError(Model1Error):
    pass


class RuntimeDataMissingError(Model1Error):
    pass


class InvalidGeometryError(Model1Error):
    pass


class CheckpointError(Model1Error):
    pass


@dataclass
class InferenceResult:
    paths: dict
    summary: dict
    metadata: dict
    timings: dict = field(default_factory=dict)


# ----------------------------------------------------------------------------- helpers
def peak_rss_mb() -> Optional[float]:
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = PMC(); pmc.cb = ctypes.sizeof(PMC)
        k32, ps = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        ps.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        ps.GetProcessMemoryInfo.restype = wintypes.BOOL
        if not ps.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            return None
        return round(pmc.PeakWorkingSetSize / 2 ** 20, 1)
    except Exception:
        return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def runtime_root() -> Path:
    from .package_runtime import runtime_root as rr
    return rr()


class Model:
    """Loaded once, serves many calls (thread-safe for predict: LightGBM boosters are read-only)."""
    _cache: dict = {}

    def __init__(self, path: Path):
        import lightgbm as lgb
        try:
            with open(path, "rb") as f:
                ck = pickle.load(f)
        except Exception as e:  # noqa
            raise CheckpointError(f"cannot load checkpoint {path.name}: {type(e).__name__}") from e
        self.ck = ck
        self.version = ck["model_version"]
        self.sha256 = sha256_file(path)
        self.features = ck["features"]
        self.boosters = [lgb.Booster(model_str=s) for s in ck["boosters"]]
        self.iso_x, self.iso_y = ck["iso_x"], ck["iso_y"]
        self.p_hi, self.p_lo = ck["fusion"]["P_HI"], ck["fusion"]["P_LO"]
        fusion.P_HI, fusion.P_LO = self.p_hi, self.p_lo

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Model":
        path = Path(path) if path else config.CKPT_DIR / CKPT_NAME
        if not path.exists():
            raise CheckpointError(f"checkpoint {path.name} not found in checkpoints directory")
        key = str(path)
        if key not in cls._cache:
            cls._cache[key] = cls(path)
        return cls._cache[key]

    def calibrated_members(self, X: np.ndarray) -> np.ndarray:
        raw = np.stack([b.predict(X, num_threads=min(8, os.cpu_count() or 1)) for b in self.boosters])
        return np.interp(raw, self.iso_x, self.iso_y).astype("float32")


class Runtime:
    """Memory-mapped packaged features for one region."""
    _cache: dict = {}

    def __init__(self, region_id: str):
        root = runtime_root() / region_id
        if not (root / "meta.json").exists():
            raise RuntimeDataMissingError(f"runtime data for region '{region_id}' not packaged (run package_runtime)")
        self.meta = json.loads((root / "meta.json").read_text())
        self.layers = {n: i for i, n in enumerate(self.meta["layers"])}
        self.mm = np.load(root / "features.npy", mmap_mode="r")
        h, w = self.meta["mask_shape"]
        self.mask = np.unpackbits(np.load(root / "region_mask.npy"))[: h * w].reshape(h, w).astype(bool)
        from .grid import Grid
        self.grid = Grid.from_dict(self.meta["grid"])
        self.full_grid = Grid.from_dict(self.meta["full_grid"])
        self.r0, _, self.c0, _ = self.meta["window_in_full_grid"]

    @classmethod
    def get(cls, region_id: str) -> "Runtime":
        if region_id not in cls._cache:
            cls._cache[region_id] = cls(region_id)
        return cls._cache[region_id]

    def layer(self, name, r0, r1):
        return np.asarray(self.mm[self.layers[name], r0:r1])


def _geometry_mask(rt: Runtime, geometry: dict):
    """Rasterise a GeoJSON geometry/feature/FeatureCollection (EPSG:4326) onto the runtime window; returns mask, window."""
    import pyproj
    from rasterio import features as rf
    from shapely.geometry import shape
    from shapely.ops import transform, unary_union
    try:
        g = geometry
        if g.get("type") == "FeatureCollection":
            geoms = [shape(f["geometry"]) for f in g["features"]]
        elif g.get("type") == "Feature":
            geoms = [shape(g["geometry"])]
        else:
            geoms = [shape(g)]
        geom = unary_union(geoms)
    except Exception as e:  # noqa
        raise InvalidGeometryError("geometry is not valid GeoJSON") from e
    if geom.is_empty or not geom.is_valid:
        geom = geom.buffer(0)
        if geom.is_empty:
            raise InvalidGeometryError("geometry is empty or invalid")
    tr = pyproj.Transformer.from_crs(4326, config.WORK_CRS, always_xy=True).transform
    g6933 = transform(tr, geom)
    m = rf.rasterize([(g6933, 1)], out_shape=rt.mask.shape, transform=rt.grid.transform, fill=0, dtype="uint8",
                     all_touched=True).astype(bool)
    m &= rt.mask
    if not m.any():
        raise InvalidGeometryError("geometry does not intersect the region")
    return m


def _nan_to(a, v):
    return np.where(np.isfinite(a), a, v)


# ----------------------------------------------------------------------------- main
def run_inference(region_id: str, out_dir, geometry: Optional[dict] = None, device: str = "cpu",
                  progress: Optional[ProgressCallback] = None, mc_draws: int = 24, mmu_cells: int = 10,
                  checkpoint: Optional[Path] = None, write_preview: bool = True) -> InferenceResult:
    t_start = time.time()
    cb = progress or (lambda f, m: None)
    if region_id not in config.REGIONS:
        raise RegionNotFoundError(f"unknown region '{region_id}'; known: {sorted(config.REGIONS)}")
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    cb(0.0, "loading checkpoint and runtime data")
    model = Model.load(checkpoint)
    rt = Runtime.get(region_id)
    mask = rt.mask if geometry is None else _geometry_mask(rt, geometry)
    rows = np.where(mask.any(1))[0]
    R0, R1 = int(rows.min()), int(rows.max()) + 1
    cols = np.where(mask.any(0))[0]
    C0, C1 = int(cols.min()), int(cols.max()) + 1
    H, W = R1 - R0, C1 - C0
    wg = rt.grid
    from .grid import Grid, window_grid
    sub = window_grid(wg, R0, R1, C0, C1)                        # grid of the processed window
    sub_mask = mask[R0:R1, C0:C1]
    cls_r = np.zeros((H, W), "uint8"); conf_r = np.full((H, W), 255, "uint8")
    probs_r = np.zeros((5, H, W), "uint8"); reason_r = np.zeros((H, W), "uint8")
    p_r = np.full((H, W), np.nan, "float16"); sev_r = np.zeros((len(rules.FACTORS), H, W), "uint8")
    ids_full = None
    need = list(dict.fromkeys(F.RULE_INPUTS + [n for n in model.features if n != "awc_ptf"] + F.SD_LAYERS +
                              ["restriction_code", "label_cult", "cult_frac"]))
    t_ml = t_mc = 0.0
    n_cells = int(sub_mask.sum())
    done = 0
    for a in range(0, H, CHUNK_ROWS):
        b = min(a + CHUNK_ROWS, H)
        m = sub_mask[a:b]
        if not m.any():
            continue
        sel = np.flatnonzero(m.ravel())
        lay = {n: rt.mm[rt.layers[n], R0 + a:R0 + b, C0:C1].ravel()[sel].astype("float32") for n in need}
        for k_ in ("sotwis_ec", "sotwis_esp", "sotwis_gypsum", "sotwis_caco3", "sotwis_awc"):
            lay[k_] = _nan_to(lay[k_], 0.0)
        lay["sotwis_drainage"] = _nan_to(lay["sotwis_drainage"], 5).astype("float32")
        for k_ in need:
            if np.isnan(lay[k_]).any():
                lay[k_] = _nan_to(lay[k_], np.nanmedian(lay[k_]) if np.isfinite(lay[k_]).any() else 0.0)
        lay["awc_ptf"] = rules.awc_cm_per_m(lay["sand_0_30"], lay["clay_0_30"], lay["soc_0_30"], lay["cfvo_0_60"])
        X = np.stack([lay[n] for n in model.features], axis=1)
        t0 = time.time()
        pm = model.calibrated_members(X)
        t_ml += time.time() - t0
        # global cell ids for deterministic noise (row-major on the FULL Jordan grid)
        rr = (sel // W) + R0 + a + rt.r0
        cc = (sel % W) + C0 + rt.c0
        ids = rr.astype("uint64") * np.uint64(rt.full_grid.width) + cc.astype("uint64")
        restr = lay["restriction_code"].astype("uint8")
        cult_obs = lay["label_cult"] == 1
        sd = {k: lay[k] for k in F.SD_LAYERS}
        t0 = time.time()
        probs, central, reason, ev = fusion.mc_class_probs(lay, sd, pm, restr, cult_obs, ids, K=mc_draws)
        t_mc += time.time() - t0
        conf = np.take_along_axis(probs, (central.astype("int64") - 1)[None], 0)[0]
        flat = (slice(a, b), slice(None))
        tmp = np.zeros(m.size, "uint8"); tmp[sel] = central; cls_r[flat] = tmp.reshape(m.shape)
        tmp = np.full(m.size, 255, "uint8"); tmp[sel] = np.round(conf * 100).astype("uint8"); conf_r[flat] = tmp.reshape(m.shape)
        for k in range(5):
            tmp = np.zeros(m.size, "uint8"); tmp[sel] = np.round(probs[k] * 100).astype("uint8"); probs_r[k, a:b] = tmp.reshape(m.shape)
        tmp = np.zeros(m.size, "uint8"); tmp[sel] = reason; reason_r[flat] = tmp.reshape(m.shape)
        tmp = np.full(m.size, np.nan, "float16"); tmp[sel] = pm.mean(0).astype("float16"); p_r[flat] = tmp.reshape(m.shape)
        for k in range(len(rules.FACTORS)):
            tmp = np.zeros(m.size, "uint8"); tmp[sel] = ev["sev"][k]; sev_r[k, a:b] = tmp.reshape(m.shape)
        done += len(sel)
        cb(0.05 + 0.65 * done / n_cells, f"classified {done:,} of {n_cells:,} cells")
    from .polygons import build_outputs
    cb(0.72, "writing rasters")
    res = build_outputs(model=model, rt=rt, sub=sub, sub_mask=sub_mask, win=(R0, R1, C0, C1), cls=cls_r, conf=conf_r,
                        probs=probs_r, reason=reason_r, p_ml=p_r, sev=sev_r, out=out, region_id=region_id,
                        mmu_cells=mmu_cells, progress=cb, device=device, mc_draws=mc_draws, geometry_query=geometry is not None)
    res.timings.update(dict(total_s=round(time.time() - t_start, 1), ml_predict_s=round(t_ml, 1), monte_carlo_s=round(t_mc, 1),
                            cells=n_cells, peak_rss_mb=peak_rss_mb()))
    meta_p = out / "run_metadata.json"
    md = json.loads(meta_p.read_text()); md["runtime"] = res.timings; meta_p.write_text(json.dumps(md, indent=1))
    res.metadata = md
    cb(1.0, "done")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="GREEN NOVA Model 1 - agricultural land suitability inference")
    ap.add_argument("--region", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--geometry", help="GeoJSON file (EPSG:4326) restricting the analysis to a sub-area")
    ap.add_argument("--device", choices=["cuda", "cpu"], default="cpu")
    ap.add_argument("--mc-draws", type=int, default=24)
    a = ap.parse_args(argv)
    geom = json.loads(Path(a.geometry).read_text()) if a.geometry else None
    pr = lambda f, m: print(f"[{f * 100:5.1f}%] {m}", flush=True)
    r = run_inference(a.region, a.out, geom, a.device, pr, a.mc_draws)
    print(json.dumps({"paths": r.paths, "timings": r.timings}, indent=1))


if __name__ == "__main__":
    main()
