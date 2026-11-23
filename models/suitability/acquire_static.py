"""Acquire static covariates for Jordan from open, account-free sources into the shared cache.

Layers (all clipped to Jordan, written under COV/<layer>/ and registered in COV/manifest.json):
  dem_cop30      Copernicus GLO-30 DEM (Planetary Computer, anonymous SAS signing)      30 m  EPSG:4326
  soilgrids      ISRIC SoilGrids 2.0 (files.isric.org VRT, CC BY 4.0)                  250 m  EPSG:4326 (reprojected from Homolosine)
  worldclim_prec WorldClim 2.1 monthly precipitation 30 s (1970-2000 normals)           ~1 km  EPSG:4326
  terraclimate   TerraClimate 1991-2020 normals (ppt, pet, tmax, tmin, def, aet)        ~4 km  EPSG:4326
  jrc_gsw        JRC Global Surface Water occurrence                                    30 m   EPSG:4326
Run:  python -m models.suitability.acquire_static <layer> [<layer> ...]
"""
from __future__ import annotations

import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window, from_bounds

from . import config, manifest
from .regions import jordan_bbox_4326

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
TODAY = time.strftime("%Y-%m-%d")

GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="2",
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.vrt,.tiff", GDAL_HTTP_MULTIPLEX="YES",
                VSI_CACHE="TRUE", VSI_CACHE_SIZE="50000000")


def _stac():
    import planetary_computer as pc
    from pystac_client import Client
    return Client.open(PC_STAC, modifier=pc.sign_inplace)


def _write(path: Path, arr, transform, crs="EPSG:4326", nodata=None, **tags):
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(arr)
    if arr.ndim == 2:
        arr = arr[None]
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=arr.shape[0],
                       dtype=arr.dtype, crs=crs, transform=transform, nodata=nodata, tiled=True, blockxsize=256,
                       blockysize=256, compress="deflate", BIGTIFF="IF_SAFER",
                       predictor=3 if arr.dtype.kind == "f" else 2) as dst:
        dst.write(arr)
        if tags:
            dst.update_tags(**{k: str(v) for k, v in tags.items()})


# --------------------------------------------------------------------------- DEM
def _signed(href):
    import planetary_computer as pc
    return pc.sign(href.split("?")[0])


def acquire_dem():
    """Resumable: tile ids already written are listed in a sidecar JSON; every tile read is retried with re-signing."""
    import json
    layer = "dem_cop30"
    out = config.COV / layer / "cop30_jordan_4326.tif"
    side = config.COV / layer / "_done_tiles.json"
    final_flag = config.COV / layer / "_complete.txt"
    if final_flag.exists():
        print("complete", out)
        return out
    minx, miny, maxx, maxy = jordan_bbox_4326(0.05)
    w0, s0 = int(np.floor(minx)), int(np.floor(miny))
    e0, n0 = int(np.ceil(maxx)), int(np.ceil(maxy))
    px = 1.0 / 3600
    W, H = int((e0 - w0) / px), int((n0 - s0) / px)
    cat = _stac()
    items = list(cat.search(collections=["cop-dem-glo-30"], bbox=[minx, miny, maxx, maxy]).items())
    print(len(items), "DEM tiles")
    done = set(json.loads(side.read_text())) if (side.exists() and out.exists()) else set()
    prof = dict(driver="GTiff", height=H, width=W, count=1, dtype="float32", crs="EPSG:4326",
                transform=from_origin(w0, n0, px, px), nodata=-9999.0, tiled=True, blockxsize=512, blockysize=512,
                compress="deflate", predictor=3, BIGTIFF="YES")
    out.parent.mkdir(parents=True, exist_ok=True)
    mode = "r+" if done else "w"
    with rasterio.Env(**GDAL_ENV), rasterio.open(out, mode, **({} if mode == "r+" else prof)) as dst:
        for it in items:
            if it.id in done:
                continue
            href = it.assets["data"].href
            for attempt in range(8):
                try:
                    with rasterio.open(href) as src:
                        a = src.read(1).astype("float32")
                        b = src.bounds
                    break
                except Exception as e:
                    print("   retry", it.id, attempt, repr(e)[:80], flush=True)
                    time.sleep(4 * (attempt + 1)); href = _signed(href)
            else:
                raise RuntimeError(f"DEM tile {it.id} failed")
            col = int(round((b.left - w0) / px)); row = int(round((n0 - b.top) / px))
            hh, ww = a.shape
            rr0, cc0 = max(row, 0), max(col, 0)
            rr1, cc1 = min(row + hh, H), min(col + ww, W)
            if rr1 > rr0 and cc1 > cc0:
                dst.write(a[rr0 - row: rr1 - row, cc0 - col: cc1 - col], 1,
                          window=Window(cc0, rr0, cc1 - cc0, rr1 - rr0))
            done.add(it.id); side.write_text(json.dumps(sorted(done)))
            print("  tile", it.id, a.shape, flush=True)
    final_flag.write_text("ok")
    manifest.add_entry(layer, "https://planetarycomputer.microsoft.com/dataset/cop-dem-glo-30 (Copernicus DEM GLO-30)",
                       "Copernicus DEM licence (free, full & open; attribution: (C) DLR e.V. 2010-2014 and (C) Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the EU and ESA)",
                       "1 arc-second (~30 m)", "EPSG:4326", (w0, s0, e0, n0), TODAY, files=[str(out)],
                       notes="elevation in metres (EGM2008 orthometric), float32, nodata -9999; mosaic of GLO-30 1-degree tiles")
    return out


# --------------------------------------------------------------------------- SoilGrids
SG_PROPS = {  # prop: (divisor, unit)
    "phh2o": (10.0, "pH (H2O)"),
    "soc": (10.0, "g/kg"),
    "sand": (10.0, "%"),
    "silt": (10.0, "%"),
    "clay": (10.0, "%"),
    "cfvo": (10.0, "vol% coarse fragments"),
    "cec": (10.0, "cmol(c)/kg"),
    "bdod": (100.0, "kg/dm3"),
}
SG_DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm"]
SG_UNC = {"phh2o", "soc", "sand", "clay"}
SG_RES = 0.0022457  # ~250 m


def acquire_soilgrids():
    layer = "soilgrids"
    d = config.COV / layer
    minx, miny, maxx, maxy = jordan_bbox_4326(0.05)
    W = int(np.ceil((maxx - minx) / SG_RES))
    H = int(np.ceil((maxy - miny) / SG_RES))
    tr = from_origin(minx, maxy, SG_RES, SG_RES)
    files = []
    base = "https://files.isric.org/soilgrids/latest/data"
    with rasterio.Env(**GDAL_ENV):
        for prop, (div, unit) in SG_PROPS.items():
            for depth in SG_DEPTHS:
                stats = ["mean"] + (["Q0.05", "Q0.95"] if (prop in SG_UNC and depth in SG_DEPTHS[:3]) else [])
                for st in stats:
                    out = d / f"{prop}_{depth}_{st}.tif"
                    files.append(str(out))
                    if out.exists():
                        continue
                    url = f"{base}/{prop}/{prop}_{depth}_{st}.vrt"
                    for attempt in range(3):
                        try:
                            with rasterio.open(url) as src:
                                with WarpedVRT(src, crs="EPSG:4326", transform=tr, width=W, height=H,
                                               resampling=Resampling.bilinear, src_nodata=src.nodata,
                                               nodata=src.nodata) as v:
                                    a = v.read(1).astype("float32")
                                    nd = src.nodata
                            break
                        except Exception as e:  # network hiccup
                            print("retry", url, e)
                            time.sleep(3 * (attempt + 1))
                    else:
                        raise RuntimeError(f"failed {url}")
                    a = np.where(a == nd, np.nan, a / div).astype("float32")
                    _write(out, a, tr, nodata=np.nan, units=unit, source=url, scale_applied=f"raw/{div}")
                    print("  ", out.name, float(np.nanmean(a)))
    manifest.add_entry(layer, "https://files.isric.org/soilgrids/latest/data/<prop>/<prop>_<depth>_<mean|Q0.05|Q0.95>.vrt (SoilGrids 2.0, Poggio et al. 2021)",
                       "CC BY 4.0 (ISRIC - World Soil Information)", "250 m (Homolosine native; resampled bilinear to ~0.0022457 deg)",
                       "EPSG:4326", (minx, miny, maxx, maxy), TODAY, files=files,
                       notes="Converted to physical units: pH, soc g/kg, sand/silt/clay %, cfvo vol%, cec cmol(c)/kg, bdod kg/dm3. Depths 0-5,5-15,15-30,30-60,60-100 cm; Q0.05/Q0.95 for ph,soc,sand,clay 0-30 cm. Model-predicted (digital soil mapping), not measured per pixel.")
    return files


# --------------------------------------------------------------------------- WorldClim precipitation
def acquire_worldclim_prec():
    layer = "worldclim_prec"
    zpath = config.RAW / "worldclim" / "wc2.1_30s_prec.zip"
    d = config.COV / layer
    minx, miny, maxx, maxy = jordan_bbox_4326(0.05)
    files = []
    with zipfile.ZipFile(zpath) as z:
        names = sorted(n for n in z.namelist() if n.endswith(".tif"))
        for n in names:
            out = d / (Path(n).stem + "_jordan.tif")
            files.append(str(out))
            if out.exists():
                continue
            tmp = config.RAW / "worldclim" / "_tmp" / Path(n).name
            tmp.parent.mkdir(parents=True, exist_ok=True)
            with z.open(n) as fsrc, open(tmp, "wb") as fdst:
                while True:
                    buf = fsrc.read(1 << 24)
                    if not buf:
                        break
                    fdst.write(buf)
            with rasterio.open(tmp) as src:
                win = from_bounds(minx, miny, maxx, maxy, src.transform).round_offsets().round_lengths()
                a = src.read(1, window=win).astype("float32")
                tr = src.window_transform(win)
                nd = src.nodata
            a = np.where(a == nd, np.nan, a) if nd is not None else a
            _write(d / (Path(n).stem + "_jordan.tif"), a, tr, nodata=np.nan, units="mm/month")
            tmp.unlink()
            print("  ", out.name, float(np.nanmean(a)))
    manifest.add_entry(layer, "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_30s_prec.zip (WorldClim 2.1, Fick & Hijmans 2017)",
                       "CC BY 4.0 (WorldClim 2.1; free for non-commercial and commercial use with attribution per worldclim.org/about)",
                       "30 arc-seconds (~1 km)", "EPSG:4326", (minx, miny, maxx, maxy), TODAY, files=files,
                       notes="Monthly precipitation normals 1970-2000, mm/month, float32 NaN nodata. Interpolated from stations (sparse in Ma'an desert) + covariates.")
    return files


# --------------------------------------------------------------------------- TerraClimate (via Planetary Computer zarr)
TC_VARS = ["ppt", "pet", "tmax", "tmin", "def", "aet"]
TC_Y0, TC_Y1 = 2011, 2020          # 10-year window (zarr chunk reads are slow from this machine: ~30-55 s per 12-month chunk)


def _tc_open():
    import xarray as xr
    cat = _stac()
    asset = cat.get_collection("terraclimate").assets["zarr-abfs"]
    kw = dict(asset.extra_fields["xarray:open_kwargs"]); kw.pop("chunks", None)      # dask not installed
    return xr.open_dataset(asset.href, **kw)


def terraclimate_var(var: str, y0=TC_Y0, y1=TC_Y1):
    """Download one variable for y0..y1 over Jordan (+0.1 deg) to a small npz (run one process per variable)."""
    minx, miny, maxx, maxy = jordan_bbox_4326(0.1)
    out = config.COV / "terraclimate" / f"_raw_{var}_{y0}_{y1}.npz"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    ds = _tc_open()
    arrs = []
    for y in range(y0, y1 + 1):
        for attempt in range(6):
            try:
                sub = ds[var].sel(lat=slice(maxy, miny), lon=slice(minx, maxx), time=slice(f"{y}-01-01", f"{y}-12-31")).load()
                break
            except Exception as e:
                print("retry", var, y, repr(e)[:80], flush=True); time.sleep(5 * (attempt + 1)); ds = _tc_open()
        else:
            raise RuntimeError(f"terraclimate {var} {y} failed")
        arrs.append(sub.values.astype("float32")); lat, lon = sub["lat"].values, sub["lon"].values
        print(var, y, "ok", flush=True)
    np.savez_compressed(out, data=np.concatenate(arrs), lat=lat, lon=lon, y0=y0, y1=y1)
    return out


def acquire_terraclimate(y0=TC_Y0, y1=TC_Y1):
    layer = "terraclimate"
    d = config.COV / layer
    raws = {v: np.load(terraclimate_var(v, y0, y1)) for v in TC_VARS}       # downloads any missing variable sequentially
    lat, lon = raws["ppt"]["lat"], raws["ppt"]["lon"]
    res = abs(float(lon[1] - lon[0]))
    tr = from_origin(float(lon.min()) - res / 2, float(lat.max()) + res / 2, res, res)
    ny = y1 - y0 + 1
    mon = {v: raws[v]["data"].reshape(ny, 12, *raws[v]["data"].shape[1:]) for v in TC_VARS}    # (year, month, lat, lon)
    files = []

    def put(name, arr, units):
        out = d / f"{name}.tif"
        _write(out, arr.astype("float32"), tr, nodata=np.nan, units=units)
        files.append(str(out))

    ann = lambda v: mon[v].sum(1)                                  # annual sums per year
    put("ppt_annual_mean", ann("ppt").mean(0), f"mm/yr ({y0}-{y1} mean)")
    put("ppt_annual_cv", ann("ppt").std(0) / (ann("ppt").mean(0) + 1e-6), "coefficient of variation of annual ppt")
    put("pet_annual_mean", ann("pet").mean(0), "mm/yr")
    put("def_annual_mean", ann("def").mean(0), "mm/yr climatic water deficit")
    put("aet_annual_mean", ann("aet").mean(0), "mm/yr")
    put("tmax_mean", mon["tmax"].mean((0, 1)), "degC")
    put("tmin_mean", mon["tmin"].mean((0, 1)), "degC")
    put("tmin_coldest_month", mon["tmin"].mean(0).min(0), "degC coldest-month mean of daily min")
    put("tmax_hottest_month", mon["tmax"].mean(0).max(0), "degC hottest-month mean of daily max")
    minx, miny, maxx, maxy = jordan_bbox_4326(0.1)
    manifest.add_entry(layer, "https://planetarycomputer.microsoft.com/dataset/terraclimate (TerraClimate, Abatzoglou et al. 2018) zarr-abfs",
                       "CC0-1.0 per Planetary Computer catalog entry (verify at source; TerraClimate data public domain/CC0)",
                       "1/24 degree (~4 km)", "EPSG:4326", (minx, miny, maxx, maxy), TODAY, files=files,
                       notes=f"{y0}-{y1} (10-yr) means derived by model1: annual means of ppt, pet, def, aet; tmax/tmin means; interannual CV of annual ppt. Spatial pattern is a downscale of WorldClim; native ~4 km.")
    return files


# --------------------------------------------------------------------------- JRC Global Surface Water
def acquire_gsw():
    layer = "jrc_gsw"
    out = config.COV / layer / "gsw_occurrence_jordan_4326.tif"
    if out.exists():
        return out
    minx, miny, maxx, maxy = jordan_bbox_4326(0.05)
    cat = _stac()
    items = list(cat.search(collections=["jrc-gsw"], bbox=[minx, miny, maxx, maxy]).items())
    print(len(items), "GSW tiles", [i.id for i in items])
    px = 0.00025
    W, H = int(np.ceil((maxx - minx) / px)), int(np.ceil((maxy - miny) / px))
    tr = from_origin(minx, maxy, px, px)
    mosaic = np.zeros((H, W), dtype="uint8")
    with rasterio.Env(**GDAL_ENV):
        for it in items:
            href = it.assets["occurrence"].href
            with rasterio.open(href) as src:
                with WarpedVRT(src, crs="EPSG:4326", transform=tr, width=W, height=H, resampling=Resampling.nearest,
                               nodata=255) as v:
                    a = v.read(1)
                a = np.where(a == 255, 0, a)
                mosaic = np.maximum(mosaic, a)
    _write(out, mosaic, tr, nodata=None, units="% of months with water 1984-2021")
    manifest.add_entry(layer, "https://planetarycomputer.microsoft.com/dataset/jrc-gsw (JRC Global Surface Water v1.4, Pekel et al. 2016) occurrence",
                       "Copernicus open data licence (free and open, attribution JRC/Google)", "30 m", "EPSG:4326",
                       (minx, miny, maxx, maxy), TODAY, files=[str(out)], notes="Water occurrence 0-100 %, uint8; 0 = never/no data. Reprojected nearest to 0.00025 deg.")
    return out


FUNCS = {"dem": acquire_dem, "soilgrids": acquire_soilgrids, "worldclim": acquire_worldclim_prec,
         "terraclimate": acquire_terraclimate, "gsw": acquire_gsw}
FUNCS.update({f"tc_{v}": (lambda v=v: terraclimate_var(v)) for v in TC_VARS})

if __name__ == "__main__":
    config.ensure_dirs()
    for name in sys.argv[1:] or FUNCS:
        print("==", name)
        FUNCS[name]()
