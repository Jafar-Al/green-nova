"""Build the profile-level topsoil (0-30 cm) training table from the WoSIS 2023-12 snapshot (observed lab data).

Input : C:\\GreenNovaData\\raw\\wosis\\WoSIS_2023_December\\wosis_202312_<prop>.tsv  (ELCOSP = EC of saturated paste = ECe, PHAQ, ORGC, SAND, SILT, CLAY, CFVO, BDFIOD)
Output: C:\\GreenNovaData\\cache\\model2\\wosis_topsoil.csv.gz   one row per profile with depth-weighted 0-30 cm means.
Rules : * organic surface layers excluded; * property needs >= 50 % coverage of 0-30 cm; * licence kept per row (NC rows flagged, not silently dropped);
        * exact duplicate (lon,lat,values) profiles collapsed; * values outside physical range dropped.
Run   : python -m models.restoration.data.wosis
"""
from __future__ import annotations

import gc
import json
import sys
import time

import numpy as np
import pandas as pd

from .. import config

SRC = config.RAW / "wosis" / "WoSIS_2023_December"
OUT = config.M2CACHE / "wosis_topsoil.csv.gz"
PROPS = {  # file code -> (output column, unit note, valid range)
    "elcosp": ("ece", "dS/m saturated paste", (0.0, 400.0)),
    "phaq": ("ph", "pH-H2O", (2.5, 11.5)),
    "orgc": ("soc_gkg", "g/kg organic C", (0.0, 600.0)),
    "sand": ("sand", "g/100g", (0.0, 100.0)),
    "silt": ("silt", "g/100g", (0.0, 100.0)),
    "clay": ("clay", "g/100g", (0.0, 100.0)),
    "cfvo": ("cfvo", "cm3/100cm3", (0.0, 100.0)),
    "bdfiod": ("bd", "kg/dm3 oven-dry fine earth", (0.2, 2.2)),
}
TOP = 30.0
USECOLS = ["profile_id", "upper_depth", "lower_depth", "organic_surface", "value_avg", "dataset_id", "country_name",
           "longitude", "latitude", "positional_uncertainty", "region", "continent", "date", "licence"]


def _topsoil_mean(df: pd.DataFrame, col: str) -> pd.DataFrame:
    lo = df["upper_depth"].clip(lower=0).to_numpy(float)
    hi = df["lower_depth"].clip(upper=TOP).to_numpy(float)
    w = np.clip(hi - lo, 0, None)
    df = df.assign(_w=w, _wv=w * df["value_avg"].to_numpy(float))
    g = df.groupby("profile_id", sort=False)
    out = pd.DataFrame({col: g["_wv"].sum() / g["_w"].sum().replace(0, np.nan), f"{col}_cover_cm": g["_w"].sum()})
    out.loc[out[f"{col}_cover_cm"] < 0.5 * TOP, col] = np.nan
    return out


def build() -> pd.DataFrame:
    config.ensure_dirs()
    meta = None
    cols = {}
    for code, (name, unit, (vmin, vmax)) in PROPS.items():
        t0 = time.time()
        f = SRC / f"wosis_202312_{code}.tsv"
        df = pd.read_csv(f, sep="\t", usecols=USECOLS, dtype={"organic_surface": "string", "dataset_id": "string",
                         "country_name": "string", "positional_uncertainty": "string", "region": "string",
                         "continent": "string", "date": "string", "licence": "string"})
        n0 = len(df)
        df = df[(df["organic_surface"] != "t") & df["value_avg"].between(vmin, vmax) & (df["upper_depth"] < TOP)]
        df = df.dropna(subset=["upper_depth", "lower_depth", "value_avg", "longitude", "latitude"])
        m = df.groupby("profile_id", sort=False).agg(dataset_id=("dataset_id", "first"), country=("country_name", "first"),
                                                     lon=("longitude", "first"), lat=("latitude", "first"),
                                                     pos_unc=("positional_uncertainty", "first"), region=("region", "first"),
                                                     continent=("continent", "first"), date=("date", "first"),
                                                     licence=("licence", "first"))
        meta = m if meta is None else pd.concat([meta, m[~m.index.isin(meta.index)]])
        cols[name] = _topsoil_mean(df, name)
        print(f"{code}: {n0} layer rows -> {len(df)} used, {cols[name][name].notna().sum()} profiles with 0-30 cm value ({time.time()-t0:.0f}s)", flush=True)
        del df
        gc.collect()
    out = meta.join(pd.concat([c[[k]] for k, c in cols.items()], axis=1), how="left")
    out["silt"] = out["silt"]
    # derive missing third texture fraction only when two of three are measured (never impute from nothing)
    for a, b, c in (("sand", "clay", "silt"), ("sand", "silt", "clay"), ("silt", "clay", "sand")):
        m = out[c].isna() & out[a].notna() & out[b].notna() & (out[a] + out[b] <= 100.5)
        out.loc[m, c] = (100 - out.loc[m, a] - out.loc[m, b]).clip(lower=0)
    out["soc_pct"] = out["soc_gkg"] / 10.0
    out["texture_sum"] = out[["sand", "silt", "clay"]].sum(axis=1, min_count=3)
    bad_tex = out["texture_sum"].notna() & ((out["texture_sum"] < 90) | (out["texture_sum"] > 110))
    out.loc[bad_tex, ["sand", "silt", "clay"]] = np.nan
    out["licence_class"] = np.select(
        [out["licence"].str.contains("Public Domain", na=False), out["licence"].str.contains("NonCommercial", na=False),
         out["licence"].str.contains("Attribution 3.0|Attribution 4.0", na=False, regex=True)],
        ["public_domain", "cc_by_nc", "cc_by"], default="other")
    out = out.reset_index().rename(columns={"index": "profile_id"})
    # exact duplicates (same coordinates and same measured values)
    key = ["lon", "lat", "ece", "ph", "soc_gkg", "sand", "clay"]
    n_before = len(out)
    out = out.drop_duplicates(subset=key, keep="first")
    print(f"exact duplicate profiles removed: {n_before - len(out)}")
    out.to_csv(OUT, index=False, compression="gzip")
    summ = {"n_profiles": int(len(out)), **{c: int(out[c].notna().sum()) for c in ["ece", "ph", "soc_pct", "sand", "clay", "cfvo", "bd"]},
            "licence_class": out["licence_class"].value_counts().to_dict(), "built": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (config.M2CACHE / "wosis_topsoil_summary.json").write_text(json.dumps(summ, indent=2))
    print(json.dumps(summ, indent=2))
    return out


if __name__ == "__main__":
    build()
