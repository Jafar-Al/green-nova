"""TerraClimate 1991-2020 monthly climate for the region bbox (Planetary Computer zarr, anonymous SAS; model2 acquisition, development-time only).

Saves  C:\\GreenNovaData\\cache\\model2\\tc_<region>.npz  with
  lat, lon (cell centres, 1/24 deg ~ 4 km), monthly climatologies (12, ny, nx): ppt, pet, tmax, tmin, srad, ws, vap,
  annual ppt per year (30, ny, nx)  -> used for design rainfall (P at 67 % exceedance, FAO_WH91) and interannual variability.
TerraClimate PET is a FAO-56 Penman-Monteith reference ET (Abatzoglou et al. 2018) -> primary ETo; a Hargreaves ETo (FAO56 eq. 52) is computed
as an independent cross-check in hydro.py.
"""
from __future__ import annotations

import time

import numpy as np

from .. import config

VARS = ["ppt", "pet", "tmax", "tmin", "srad", "ws", "vap"]


def acquire(region_id: str = "jo-maan", y0: int = 1991, y1: int = 2020, pad: float = 0.15) -> str:
    import planetary_computer as pc
    import xarray as xr
    from pystac_client import Client
    bb = config.REGIONS[region_id]["bbox_4326_fallback"]
    minx, miny, maxx, maxy = bb[0] - pad, bb[1] - pad, bb[2] + pad, bb[3] + pad
    cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
    asset = cat.get_collection("terraclimate").assets["zarr-abfs"]
    kw = dict(asset.extra_fields.get("xarray:open_kwargs", {}))
    kw.pop("engine", None)
    kw["chunks"] = None                      # no dask in the shared venv
    if "storage_options" not in kw and "xarray:storage_options" in asset.extra_fields:
        kw["storage_options"] = asset.extra_fields["xarray:storage_options"]
    ds = xr.open_zarr(asset.href, **kw)
    sub = ds.sel(lat=slice(maxy, miny), lon=slice(minx, maxx), time=slice(f"{y0}-01-01", f"{y1}-12-31"))[VARS].load()
    out = {"lat": sub["lat"].values.astype("float64"), "lon": sub["lon"].values.astype("float64")}
    for v in VARS:
        out[v] = sub[v].groupby("time.month").mean("time").values.astype("float32")          # (12, ny, nx)
    out["ppt_annual"] = sub["ppt"].groupby("time.year").sum("time").values.astype("float32")  # (years, ny, nx)
    out["years"] = np.arange(y0, y1 + 1)
    path = config.M2CACHE / f"tc_{region_id}.npz"
    config.ensure_dirs()
    np.savez_compressed(path, **out)
    print(f"saved {path.name}: grid {len(out['lat'])}x{len(out['lon'])}, {time.strftime('%Y-%m-%d')}")
    return str(path)


if __name__ == "__main__":
    acquire()
