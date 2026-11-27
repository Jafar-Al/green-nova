"""Turn the region stack into engine `Units` (grid cells or polygon aggregates) with calibrated uncertainties."""
from __future__ import annotations

import numpy as np
from rasterio import features as rfeatures
from scipy.interpolate import RegularGridInterpolator

from . import config, engine
from .stack import Grid

# empirical 1-sigma of SoilGrids at measured arid sites (eval/soilgrids_check.json, test-box + arid subsets; leakage-optimistic)
SG_SD = dict(ph=0.35, sand=11.0, clay=9.0, soc_abs=0.55)
DEPTH_LSD = 0.15            # log10 sd for third-party depth-to-bedrock (assumed; no local validation data)
CF_SD = 8.0


def interp_climate(climate: dict, lon, lat):
    """Bilinear interpolation of the native-grid climate arrays at points. Returns dict with ppt_m, eto_m (12,N), p67, p_mean, tmin_cold (N)."""
    lat_g = climate["lat"]
    lon_g = climate["lon"]
    order = np.argsort(lat_g)
    pts = np.column_stack([np.clip(lat, lat_g.min(), lat_g.max()), np.clip(lon, lon_g.min(), lon_g.max())])

    def one(a2d):
        return RegularGridInterpolator((lat_g[order], lon_g), a2d[order, :], method="linear", bounds_error=False, fill_value=None)(pts)
    out = {k: np.stack([one(climate[k][m]) for m in range(12)]) for k in ("ppt_m", "eto_m")}
    for k in ("p67", "p_mean", "tmin_cold", "eto_hg_annual", "p_cv", "t_mean", "water_surplus_mm", "water_surplus_sd_mm"):
        if k in climate:
            out[k] = one(climate[k])
    return out


def cell_lonlat(grid: Grid, rows, cols):
    from pyproj import Transformer
    x = grid.x0 + (cols + 0.5) * grid.res
    y = grid.y0 - (rows + 0.5) * grid.res
    return Transformer.from_crs(grid.crs, 4326, always_xy=True).transform(x, y)


def _fill(a, default):
    a = np.asarray(a, dtype="float32")
    return np.where(np.isfinite(a), a, default).astype("float32")


def units_from_values(v: dict, clim: dict, restricted=None, salt_flat=None, extra_unc: dict | None = None) -> engine.Units:
    """v: dict of 1-D arrays (central values); clim from interp_climate; extra_unc: dict of within-unit spatial sd (added in quadrature)."""
    n = len(v["ece"])
    u = extra_unc or {}
    soc = np.maximum(_fill(v["soc_pct"], 0.4), 0.02)
    soc_rsd = np.clip(SG_SD["soc_abs"] / np.maximum(soc, 0.15), 0.3, 1.5).astype("float32")
    sand = _fill(v["sand"], 50.0)
    clay = _fill(v["clay"], 20.0)
    ece = np.maximum(_fill(v["ece"], 3.0), 0.05)
    ece_lsd = np.sqrt(_fill(v["ece_lsd"], 0.3) ** 2 + u.get("ece_lsd", 0.0) ** 2).astype("float32")
    esp = np.clip(_fill(v["esp"], 5.0), 0, 100)
    esp_sd = np.sqrt(_fill(v["esp_sd"], 5.0) ** 2 + u.get("esp_sd", 0.0) ** 2).astype("float32")
    depth = np.clip(_fill(v["depth_cm"], 100.0), 10, 400)
    slope = np.clip(_fill(v["slope_deg"], 2.0), 0, 60)
    if salt_flat is None:
        salt_flat = (ece >= 16) & (slope < 2.0) & (_fill(v.get("tpi5", np.zeros(n)), 0.0) < 0)
    return engine.Units(
        ece=ece, ece_lsd=ece_lsd, esp=esp, esp_sd=esp_sd, ph=_fill(v["ph"], 8.0), ph_sd=np.full(n, SG_SD["ph"], "float32"),
        soc=soc, soc_rsd=soc_rsd, sand=sand, clay=clay, tex_sd=np.full(n, 0.5 * (SG_SD["sand"] + SG_SD["clay"]), "float32"),
        cf=_fill(v["cfvo"], 15.0), bd=np.clip(_fill(v["bd"], 1.4), 0.9, 1.9), cec=np.clip(_fill(v["cec"], 10.0), 1.0, 60.0),
        depth=depth, depth_lsd=np.full(n, DEPTH_LSD, "float32"), slope=slope,
        ppt_m=clim["ppt_m"].astype("float32"), eto_m=clim["eto_m"].astype("float32"), p67=clim["p67"].astype("float32"),
        tmin_cold=clim["tmin_cold"].astype("float32"), salt_flat=np.asarray(salt_flat, bool),
        restricted=np.zeros(n, bool) if restricted is None else np.asarray(restricted, bool),
        wsup=(np.clip(clim["water_surplus_mm"], 0, None) * 10.0).astype("float32") if "water_surplus_mm" in clim else None,       # 1 mm = 10 m3/ha
        wsup_sd=(np.clip(clim["water_surplus_sd_mm"], 0, None) * 10.0).astype("float32") if "water_surplus_sd_mm" in clim else None)


def zonal_stats(layers: dict, grid: Grid, geoms, ids):
    """Area-weighted (cell-centre) mean and sd of each layer inside each polygon (geoms in grid CRS). Sub-cell polygons use the cell under their centroid.
    Returns (means dict of arrays (n_poly,), sds dict, ncells (n_poly,), sub_cell bool)."""
    n = len(geoms)
    lab = rfeatures.rasterize(list(zip(geoms, np.arange(1, n + 1, dtype="uint32"))), out_shape=grid.shape, transform=grid.transform, fill=0, dtype="uint32")
    flat = lab.ravel()
    cnt = np.bincount(flat, minlength=n + 1)[1:].astype("float64")
    means, sds = {}, {}
    for k, a in layers.items():
        a = a.ravel().astype("float64")
        ok = np.isfinite(a) & (flat > 0)
        c = np.bincount(flat[ok], minlength=n + 1)[1:]
        s1 = np.bincount(flat[ok], weights=a[ok], minlength=n + 1)[1:]
        s2 = np.bincount(flat[ok], weights=a[ok] ** 2, minlength=n + 1)[1:]
        with np.errstate(invalid="ignore", divide="ignore"):
            m = s1 / c
            sd = np.sqrt(np.maximum(s2 / c - m ** 2, 0))
        means[k], sds[k] = m, sd
    sub = cnt == 0
    if sub.any():
        for j in np.where(sub)[0]:
            c = geoms[j].centroid
            col = int((c.x - grid.x0) // grid.res)
            row = int((grid.y0 - c.y) // grid.res)
            if 0 <= row < grid.height and 0 <= col < grid.width:
                for k, a in layers.items():
                    means[k][j] = a[row, col]
                    sds[k][j] = 0.0
                cnt[j] = 0
    return means, sds, cnt.astype(int), sub
