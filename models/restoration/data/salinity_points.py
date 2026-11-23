"""Training tables for the salinity (ECe) and sodicity (ESP) models: measured topsoil (0-30 cm) values + covariates.

ECe  = WoSIS 2023 ELCOSP (saturated paste; licences public-domain / CC BY only, NC rows excluded) U Hassani et al. 2020 measured ECe points
       (CC BY 4.0, Mendeley Data v9mgbmtnf2); duplicates between the two removed (same ~1 km cell and ECe within 10 %).
ESP  = Hassani et al. 2020 measured exchangeable Na / CEC points (ESP = ExNa/CEC x 100).  WoSIS has no exchangeable-Na table.
Each location is aggregated to one depth-weighted 0-30 cm value (repeated years/layers at one site never straddle train/test folds: folds are spatial blocks).
Run: python -m models.restoration.data.salinity_points
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from .. import config, features

H = config.RAW / "hassani2020_salinity"
OUT_ECE = config.M2CACHE / "ece_training.csv.gz"
OUT_ESP = config.M2CACHE / "esp_training.csv.gz"


def _agg_topsoil(df: pd.DataFrame, up: str, lo: str, val: str) -> pd.DataFrame:
    df = df.copy()
    df["w"] = (np.minimum(df[lo], 30.0) - np.maximum(df[up], 0.0)).clip(lower=0)
    df = df[(df["w"] > 0) & df[val].notna()]
    df["wv"] = df["w"] * df[val]
    df["key"] = df["lon"].round(5).astype(str) + "_" + df["lat"].round(5).astype(str)
    g = df.groupby("key")
    out = pd.DataFrame({"lon": g["lon"].first(), "lat": g["lat"].first(), val: g["wv"].sum() / g["w"].sum(), "cover_cm": g["w"].sum(), "n_records": g.size()})
    return out[out["cover_cm"] >= 15].reset_index(drop=True)


def load_hassani_ece() -> pd.DataFrame:
    import geopandas as gpd
    g = gpd.read_file(H / "ece_train" / "ECe_input_training_data.shp", columns=["upper_dept", "lower_dept", "Year", "ECe"])
    g["lon"], g["lat"] = g.geometry.x, g.geometry.y
    g = g[(g["ECe"] >= 0) & (g["ECe"] <= 400)]
    out = _agg_topsoil(pd.DataFrame(g.drop(columns="geometry")), "upper_dept", "lower_dept", "ECe")
    out["source"] = "hassani_ece"
    return out.rename(columns={"ECe": "ece"})


def load_hassani_esp() -> pd.DataFrame:
    import geopandas as gpd
    g = gpd.read_file(H / "esp_train" / "ESP_input_training_data.shp", columns=["Upp_dep", "Low_dep", "Ex_Na", "CEC"])
    g["lon"], g["lat"] = g.geometry.x, g.geometry.y
    d = pd.DataFrame(g.drop(columns="geometry"))
    d = d[(d["CEC"] > 1.0) & (d["Ex_Na"] >= 0)]
    d["esp"] = (100.0 * d["Ex_Na"] / d["CEC"]).clip(0, 100)
    out = _agg_topsoil(d, "Upp_dep", "Low_dep", "esp")
    out["source"] = "hassani_esp"
    return out


def dedup_against(base: pd.DataFrame, new: pd.DataFrame, col: str, rel: float = 0.10, deg: float = 0.01) -> tuple[pd.DataFrame, int]:
    from scipy.spatial import cKDTree
    t = cKDTree(base[["lon", "lat"]].to_numpy())
    d, i = t.query(new[["lon", "lat"]].to_numpy(), distance_upper_bound=deg)
    ok = np.isfinite(d)
    dup = np.zeros(len(new), bool)
    bv = base[col].to_numpy()
    nv = new[col].to_numpy()
    dup[ok] = np.abs(nv[ok] - bv[i[ok]]) <= rel * np.maximum(np.abs(bv[i[ok]]), 0.2)
    return new[~dup].reset_index(drop=True), int(dup.sum())


def build():
    config.ensure_dirs()
    features.prepare_global_layers()
    w = pd.read_csv(config.M2CACHE / "wosis_topsoil.csv.gz")
    w = w[w["ece"].notna() & w["licence_class"].isin(["public_domain", "cc_by"])]
    w = w[["profile_id", "lon", "lat", "ece", "dataset_id", "country", "licence_class"]].rename(columns={"dataset_id": "source"})
    w["source"] = "wosis_" + w["source"].astype(str)
    he = load_hassani_ece()
    he_new, ndup = dedup_against(w, he, "ece")
    ece = pd.concat([w, he_new], ignore_index=True)
    print(f"ECe: WoSIS(public/CC-BY) {len(w)} + Hassani {len(he)} (-{ndup} duplicates) = {len(ece)} locations", flush=True)
    esp = load_hassani_esp()
    print(f"ESP: {len(esp)} locations", flush=True)
    summ = {"ece_wosis": int(len(w)), "ece_hassani_raw": int(len(he)), "ece_hassani_duplicates_removed": ndup, "ece_total": int(len(ece)), "esp_total": int(len(esp)),
            "wosis_nc_excluded": int(pd.read_csv(config.M2CACHE / "wosis_topsoil.csv.gz", usecols=["ece", "licence_class"]).query("ece == ece and licence_class == 'cc_by_nc'").shape[0])}
    for name, df, out in (("ece", ece, OUT_ECE), ("esp", esp, OUT_ESP)):
        t0 = time.time()
        f = features.extract(df["lon"].to_numpy(), df["lat"].to_numpy(), with_soil=True)
        for k, v in f.items():
            df[k] = v
        df["block"] = (np.floor(df["lon"] / 5).astype(int)).astype(str) + "_" + (np.floor(df["lat"] / 5).astype(int)).astype(str)
        df.to_csv(out, index=False, compression="gzip")
        print(f"{name}: features extracted for {len(df)} points in {time.time() - t0:.0f}s; NaN share of features: {df[features.FEATURES].isna().mean().round(3).to_dict()}", flush=True)
    summ["built"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    (config.M2CACHE / "salinity_points_summary.json").write_text(json.dumps(summ, indent=2))


if __name__ == "__main__":
    build()
