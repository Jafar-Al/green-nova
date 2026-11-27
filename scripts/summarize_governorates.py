"""Generate docs/GOVERNORATES.md from the committed model outputs (no number is typed by hand).

    python scripts/summarize_governorates.py            # rewrites docs/GOVERNORATES.md
    python scripts/summarize_governorates.py --print    # prints to stdout instead

Reads models/suitability/outputs/<region>/{summary,run_metadata}.json and models/restoration/outputs/<region>/summary.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
M1 = ROOT / "models" / "suitability" / "outputs"
M2 = ROOT / "models" / "restoration" / "outputs"
# Leave-governorate-out groups that were held out of training for the validation reported in docs/MODEL1_SUITABILITY.md
HELD_OUT_EVIDENCE = {"jo-maan": "Ma'an fold", "jo-karak": "Karak+Tafilah fold", "jo-tafilah": "Karak+Tafilah fold", "jo-mafraq": "Mafraq fold"}


def regions() -> list[tuple[str, str]]:
    feats = json.loads((ROOT / "regions" / "jordan_adm1.geojson").read_text(encoding="utf-8"))["features"]
    return sorted(((f["properties"]["region_id"], f["properties"]["name"]) for f in feats), key=lambda t: t[1])


def pct(x: float, total: float) -> str:
    return f"{100.0 * x / total:.1f}" if total else "n/a"


def water_stats(rid: str):
    """Area-weighted view of what reclamation would take, from Model 2's polygons: the best scenario of each restorable polygon is the one with
    the highest success probability; returns (median central water requirement m3/ha/yr, P10, P90, share of area whose best scenario needs no irrigation)."""
    p = M2 / rid / "polygons.geojson"
    if not p.exists():
        return None
    pts = []  # (water, area)
    for f in json.loads(p.read_text(encoding="utf-8"))["features"]:
        pr = f["properties"]
        if pr["feasibility"]["class"] == "not_feasible" or not pr.get("scenarios"):
            continue
        best = max(pr["scenarios"], key=lambda s: (s["success_probability"], -s["water_requirement_m3_ha_yr"]["central"]))
        pts.append((best["water_requirement_m3_ha_yr"]["central"], pr["area_ha"]))
    if not pts:
        return None
    pts.sort()
    total = sum(a for _, a in pts)

    def wq(q):
        acc = 0.0
        for w, a in pts:
            acc += a
            if acc >= q * total:
                return w
        return pts[-1][0]

    return wq(0.5), wq(0.1), wq(0.9), sum(a for w, a in pts if w <= 0) / total


def build() -> str:
    rows, rows2, rows3, notes = [], [], [], []
    for rid, name in regions():
        s1p, s2p = M1 / rid / "summary.json", M2 / rid / "summary.json"
        if not s1p.exists():
            rows.append(f"| {name} | not assessed | | | | | | |")
            continue
        s1 = json.loads(s1p.read_text())
        tot = s1["total_area_ha"]
        c = {int(k): v["area_ha"] for k, v in s1["classes"].items()}
        suitable = c.get(1, 0) + c.get(2, 0)
        recl = c.get(3, 0) + c.get(4, 0)
        r2 = "not assessed"
        if s2p.exists():
            by = json.loads(s2p.read_text())["headline"]["area_ha_by_class"]
            r2 = f"{pct(by.get('high', 0.0), recl)} / {pct(by.get('moderate', 0.0), recl)} / {pct(by.get('low', 0.0), recl)}"
        rows.append(
            f"| {name} | {tot / 100:,.0f} | {suitable:,.0f} ({pct(suitable, tot)} %) | {c.get(3, 0):,.0f} ({pct(c.get(3, 0), tot)} %) | "
            f"{c.get(4, 0):,.0f} ({pct(c.get(4, 0), tot)} %) | {c.get(5, 0):,.0f} ({pct(c.get(5, 0), tot)} %) | {recl:,.0f} | {r2} |"
        )
        ws = water_stats(rid)
        if ws:
            rows3.append(f"| {name} | {ws[0]:,.0f} ({ws[1]:,.0f} - {ws[2]:,.0f}) | {100 * ws[3]:.1f} % |")
        ag = s1.get("agreement_with_observed_cultivation") or {}
        oc = ag.get("observed_cultivated", {})
        wo = ag.get("observed_cultivated_without_override", {}).get("rules_plus_ml_share_by_class", {})
        pr = ag.get("mean_ml_cultivation_probability", {})
        if oc and wo:
            good = wo.get("1", 0) + wo.get("2", 0)
            rows2.append(
                f"| {name} | {oc['area_ha']:,.0f} | {100 * good:.1f} % / {100 * wo.get('3', 0):.1f} % / {100 * wo.get('4', 0):.1f} % | "
                f"{pr.get('observed_cultivated', float('nan')):.2f} vs {pr.get('observed_not_cultivated_sample', float('nan')):.3f} | {HELD_OUT_EVIDENCE.get(rid, 'none (in-sample)')} |"
            )
        notes.append(f"- **{name}** (`{rid}`): mean Model 1 confidence {s1.get('mean_confidence')} (agreement of 24 Monte-Carlo draws, not accuracy); class 1 = {c.get(1, 0):,.0f} ha")
    t1 = (
        "| Governorate | Area (km2) | Suitable now: classes 1-2 (ha) | Requires reclamation: class 3 (ha) | Currently unsuitable: class 4 (ha) | Excluded: class 5 (ha) | "
        "Not suitable now: classes 3+4 (ha) | Reclamation feasibility of classes 3+4 if water is supplied: high / moderate / low (% of that land) |\n"
        "|---|---:|---:|---:|---:|---:|---:|---|\n" + "\n".join(rows)
    )
    t2 = (
        "| Governorate | Observed cultivated land (ha) | Where the model would place it with the observed-cultivation override OFF: classes 1-2 / 3 / 4 | Mean ML cultivation probability: cultivated vs not-cultivated land | Held-out validation evidence |\n"
        "|---|---:|---|---|---|\n" + "\n".join(rows2)
    )
    t3 = (
        "| Governorate | Water the best scenario needs, m3/ha/yr: area-weighted median (P10 - P90) | Share of restorable land whose best scenario needs no irrigation |\n"
        "|---|---:|---:|\n" + "\n".join(rows3)
    )
    return (
        "# Assessment of the 12 governorates\n\n"
        "_Generated by `scripts/summarize_governorates.py` from the committed outputs. Do not edit by hand._\n\n"
        "Areas are hectares (1 dunum = 0.1 ha = 1,000 m2) measured on an equal-area grid (EPSG:6933; 100 m cells for Model 1, 250 m cells for Model 2). "
        "Boundaries: geoBoundaries gbOpen JOR ADM1 (coarse, 2006 vintage). Every governorate was processed from the same Jordan-wide inputs, "
        "the same Model 1 checkpoint and the same rule engine, and has its own boundary, statistics, polygons and rasters.\n\n"
        "## Land classes and reclamation feasibility\n\n" + t1 + "\n\n"
        "## What reclamation would take (water)\n\n" + t3 + "\n\n"
        "Per restorable polygon the model picks the scenario with the highest simulated success probability and reports its central net water requirement "
        "(simulated, `expert_rule` equations on observed climate, FAO-56). Because feasibility is conditional on water being available, this is the figure that "
        "separates governorates: compare it with the water you can actually supply.\n\n"
        "## Agreement with observed cultivation (consistency check)\n\n" + t2 + "\n\n"
        "## How to read this\n"
        "- **Model 1 (suitability)** partitions every governorate into five classes, so the class columns add up to the governorate area and no land is counted twice.\n"
        "- **Model 2 (restoration potential)** only evaluates land that Model 1 placed in class 3 or 4 (class 5 land is reported as restricted, never restorable). "
        "Its high/moderate/low shares therefore describe the same land as the \"not suitable now\" column and must not be added to the suitable share.\n"
        "- **Feasibility is conditional**: Model 2 assumes a reference irrigation allocation (8,000 m3/ha/yr) and does not map where that water exists. "
        "\"High\" means technically feasible *if the water is supplied*, not that reclamation is economical or that water is available.\n"
        "- **Class 1** (\"currently suitable\", no limitation) is rare or absent because the rule engine treats low rainfall, steep slopes and calcareous/saline soils as limitations; "
        "class 2 (\"suitable with limitations\") is the main potentially cultivable class. Observed cultivated land is lifted to class 2 at most (so the delivered map partly agrees with observed cultivation by construction); "
        "the second table shows the non-circular result with that override switched off.\n"
        "- **Validation**: one checkpoint, trained once on all of Jordan, is applied to every governorate. Only the folds named in the last column were held out of training "
        "(see `docs/MODEL1_SUITABILITY.md`); for the other governorates the model has seen their land-cover labels, so there is no independent accuracy estimate for them.\n"
        "- **Resolution**: effective resolution is about 1 km (Model 1) and 1-4 km (Model 2) regardless of the finer grids.\n\n"
        "## Per-governorate notes\n" + "\n".join(notes) + "\n"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true")
    a = ap.parse_args()
    text = build()
    if a.print:
        print(text)
    else:
        (ROOT / "docs" / "GOVERNORATES.md").write_text(text, encoding="utf-8")
        print("wrote docs/GOVERNORATES.md")
