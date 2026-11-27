"""Fast path: build cache\model2\tc_<region>.npz from model1's cached raw TerraClimate monthly arrays (2011-2020, 120 months) clipped to the region bbox.
Limitation: 10-year window (not 30): monthly climatology and the 33rd-percentile design rainfall come from 10 annual totals."""
from __future__ import annotations
import numpy as np
from .. import config

def build(region_id="jo-maan", pad=0.15):
    d = config.COV / "terraclimate"
    bb = config.REGIONS[region_id]["bbox_4326_fallback"]
    out = {}
    for v in ("ppt", "pet", "tmax", "tmin"):
        z = np.load(d / f"_raw_{v}_2011_2020.npz")
        lat, lon, a = z["lat"], z["lon"], z["data"]
        y0, y1 = int(z["y0"]), int(z["y1"])
        ii = np.where((lat >= bb[1] - pad) & (lat <= bb[3] + pad))[0]
        jj = np.where((lon >= bb[0] - pad) & (lon <= bb[2] + pad))[0]
        sub = a[:, ii][:, :, jj]
        ny = sub.shape[0] // 12
        sub = sub.reshape(ny, 12, len(ii), len(jj))
        out["lat"], out["lon"] = lat[ii], lon[jj]
        out[v] = np.nanmean(sub, axis=0).astype("float32")
        if v == "ppt":
            out["ppt_annual"] = np.nansum(sub, axis=1).astype("float32")
            out["years"] = np.arange(y0, y1 + 1)
    p = config.M2CACHE / f"tc_{region_id}.npz"
    np.savez_compressed(p, **out)
    print("saved", p.name, {k: v.shape for k, v in out.items()})
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--region", default="jo-maan")
    build(ap.parse_args().region)
