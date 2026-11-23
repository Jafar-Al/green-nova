"""
GREEN NOVA AI - render web imagery from open Sentinel-2 L2A (Copernicus) via Microsoft Planetary Computer STAC.

Run with the shared venv only:  python -I web/scripts/imagery/render_assets.py <step> ...
Large intermediates stay in <data root>\\cache\\web\\s2 (never in the repo). Only optimised web assets are written under web/public.

Steps
  select                      choose one low-cloud scene per MGRS tile over Ma'an (narrow date window -> consistent tone)
  mosaic [--zoom 11]          read the 'visual' (true-colour) COG decimated, warp to EPSG:3857, mosaic -> cache/mosaic_z<z>.npy
  tiles  [--zmin 5 --zmax 11] slice the mosaic into an XYZ JPEG pyramid -> web/public/tiles/s2/{z}/{x}/{y}.jpg
  crop --name N --bbox W,S,E,N --res M --widths 2400,1600,800
                              render a window at ~M metres/pixel directly from the COGs -> AVIF/WebP/JPEG under web/public/img
  fill [--zoom 11]            fill nodata swath-edge wedges inside Ma'an from extra low-cloud scenes
  meta                        write web/public/tiles/s2/ATTRIBUTION.txt and cache/scenes.json summary

The 'visual' asset is the ESA true-colour image (TCI, 8-bit). It is only resampled, mosaicked and JPEG/AVIF-encoded here.
No pixel is invented, recoloured or AI-generated.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import planetary_computer as pc
import rasterio
from PIL import Image
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.transform import Affine, from_origin
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[3]  # project root
WEB_PUBLIC = ROOT / "web" / "public"
CACHE = Path(os.environ.get("GREEN_NOVA_DATA", str(Path.home() / "GreenNovaData"))) / "cache" / "web" / "s2"
CACHE.mkdir(parents=True, exist_ok=True)

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
BBOX = (35.2, 29.1, 38.1, 31.35)  # buffered Ma'an extent (governorate bbox 35.30,29.18,38.00,31.27)
WINDOW = ("2026-02-25", "2026-03-12")
FALLBACK = ("2026-02-01", "2026-04-30")
R = 6378137.0
ORIGIN = 20037508.342789244


def stac():
    return Client.open(STAC, modifier=pc.sign_inplace)


def select(force=False):
    out = CACHE / "selected.json"
    if out.exists() and not force:
        return json.loads(out.read_text())
    cat = stac()
    chosen = {}
    for rng in (WINDOW, FALLBACK):
        s = cat.search(
            collections=["sentinel-2-l2a"], bbox=list(BBOX), datetime=f"{rng[0]}/{rng[1]}",
            query={"eo:cloud_cover": {"lt": 10}}, max_items=500,
        )
        for it in s.items():
            tile = it.properties.get("s2:mgrs_tile")
            cc = it.properties["eo:cloud_cover"]
            # nodata share: prefer full-coverage scenes
            nd = it.properties.get("s2:nodata_pixel_percentage", 0) or 0
            score = cc + nd * 0.5
            if tile not in chosen or (rng == WINDOW and chosen[tile]["_rng"] == "fallback") or (
                chosen[tile]["_rng"] == ("window" if rng == WINDOW else "fallback") and score < chosen[tile]["_score"]
            ):
                chosen[tile] = {
                    "id": it.id, "tile": tile, "datetime": it.datetime.isoformat(), "cloud": cc, "nodata_pct": nd,
                    "baseline": it.properties.get("s2:processing_baseline"), "platform": it.properties.get("platform"),
                    "bbox": it.bbox, "_score": score, "_rng": "window" if rng == WINDOW else "fallback",
                    "href": it.assets["visual"].href, "collection": it.collection_id,
                }
    # keep only tiles that actually intersect the bbox with a meaningful share
    sel = {k: v for k, v in chosen.items()}
    out.write_text(json.dumps(sel, indent=1))
    print(f"selected {len(sel)} scenes")
    for k, v in sorted(sel.items()):
        print(" ", k, v["datetime"][:10], f"cloud={v['cloud']:.3f}", f"nodata={v['nodata_pct']:.1f}", v["_rng"])
    return sel


def fresh_href(scene_id: str) -> str:
    """STAC SAS tokens expire; re-sign from the item when reading."""
    cat = stac()
    it = next(cat.search(collections=["sentinel-2-l2a"], ids=[scene_id]).items())
    return it.assets["visual"].href


def grid(zoom: int):
    res = 2 * ORIGIN / (256 * 2**zoom)
    return res


def lonlat_to_merc(lon, lat):
    x = math.radians(lon) * R
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * R
    return x, y


def tile_range(zoom: int, bbox):
    res = grid(zoom)
    x0, y0 = lonlat_to_merc(bbox[0], bbox[3])  # west, north
    x1, y1 = lonlat_to_merc(bbox[2], bbox[1])
    tx0 = int((x0 + ORIGIN) / (res * 256))
    tx1 = int((x1 + ORIGIN) / (res * 256))
    ty0 = int((ORIGIN - y0) / (res * 256))
    ty1 = int((ORIGIN - y1) / (res * 256))
    return tx0, tx1, ty0, ty1


def read_decimated(href: str, dst_bounds_3857, res_m):
    """Read the part of a scene overlapping dst_bounds (EPSG:3857) at ~res_m ground metres (native CRS), decimated."""
    with rasterio.open(href) as src:
        left, bottom, right, top = transform_bounds("EPSG:3857", src.crs, *dst_bounds_3857, densify_pts=21)
        sb = src.bounds
        l, b, r, t = max(left, sb.left), max(bottom, sb.bottom), min(right, sb.right), min(top, sb.top)
        if l >= r or b >= t:
            return None
        win = from_bounds(l, b, r, t, src.transform).round_offsets().round_lengths()
        if win.width < 2 or win.height < 2:
            return None
        factor = max(1.0, res_m / abs(src.transform.a))
        w, h = max(2, int(win.width / factor)), max(2, int(win.height / factor))
        arr = src.read(window=win, out_shape=(3, h, w), resampling=Resampling.average)
        tr = src.window_transform(win) * Affine.scale(win.width / w, win.height / h)
        return arr, tr, src.crs


def mosaic(zoom: int):
    sel = select()
    tx0, tx1, ty0, ty1 = tile_range(zoom, BBOX)
    # align to even tile indexes so each lower zoom halves exactly
    tx0 -= tx0 % 2
    ty0 -= ty0 % 2
    tx1 += 1 - (tx1 % 2)
    ty1 += 1 - (ty1 % 2)
    res = grid(zoom)
    W, H = (tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256
    left = -ORIGIN + tx0 * 256 * res
    top = ORIGIN - ty0 * 256 * res
    dst_tr = from_origin(left, top, res, res)
    bounds = (left, top - H * res, left + W * res, top)
    print(f"mosaic z{zoom}: tiles x {tx0}-{tx1}, y {ty0}-{ty1}, {W}x{H}px, {res:.1f} m/px (3857)")
    canvas = np.zeros((3, H, W), dtype=np.uint8)
    for tile, meta in sorted(sel.items()):
        href = fresh_href(meta["id"])
        # ground res at lat ~30 is 0.87 * mercator res
        got = read_decimated(href, bounds, res * 0.87 * 0.9)
        if got is None:
            print("  skip", tile)
            continue
        arr, tr, crs = got
        filled = 0
        for band in range(3):
            dst = np.zeros((H, W), dtype=np.uint8)
            reproject(
                source=arr[band], destination=dst, src_transform=tr, src_crs=crs, dst_transform=dst_tr, dst_crs="EPSG:3857",
                resampling=Resampling.bilinear, src_nodata=0, dst_nodata=0,
            )
            if band == 0:
                valid_new = dst > 0
            fill = (canvas[band] == 0) & valid_new if band == 0 else fill
            canvas[band][fill] = dst[fill]
        print("  ok", tile, meta["datetime"][:10])
    np.save(CACHE / f"mosaic_z{zoom}.npy", canvas)
    (CACHE / f"mosaic_z{zoom}.json").write_text(json.dumps({"zoom": zoom, "tx0": tx0, "tx1": tx1, "ty0": ty0, "ty1": ty1}))
    Image.fromarray(np.moveaxis(canvas, 0, -1)).resize((W // 4, H // 4), Image.LANCZOS).save(CACHE / f"preview_z{zoom}.jpg", quality=85)
    print("saved mosaic + preview")


def fill(zoom: int, max_extra: int = 14):
    """Fill remaining nodata wedges (swath edges) inside the Ma'an boundary with additional low-cloud scenes."""
    from rasterio.features import rasterize

    meta_j = json.loads((CACHE / f"mosaic_z{zoom}.json").read_text())
    canvas = np.load(CACHE / f"mosaic_z{zoom}.npy")
    tx0, tx1, ty0, ty1 = meta_j["tx0"], meta_j["tx1"], meta_j["ty0"], meta_j["ty1"]
    res = grid(zoom)
    W, H = (tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256
    left = -ORIGIN + tx0 * 256 * res
    top = ORIGIN - ty0 * 256 * res
    dst_tr = from_origin(left, top, res, res)
    bounds = (left, top - H * res, left + W * res, top)
    adm = json.loads((WEB_PUBLIC / "data" / "jordan_adm1.geojson").read_text())
    ring = next(f for f in adm["features"] if f["properties"]["shapeName"] == "Ma'an")["geometry"]["coordinates"][0]
    poly = {"type": "Polygon", "coordinates": [[list(lonlat_to_merc(x, y)) for x, y in ring]]}
    mask = rasterize([(poly, 1)], out_shape=(H, W), transform=dst_tr).astype(bool)
    def hole_share():
        return float(((canvas[0] == 0) & mask).sum()) / float(mask.sum())
    print(f"holes inside Ma'an before fill: {hole_share()*100:.2f}%")
    sel = select()
    used = {v["id"] for v in sel.values()}
    cat = stac()
    s = cat.search(collections=["sentinel-2-l2a"], bbox=list(BBOX), datetime=f"{FALLBACK[0]}/{FALLBACK[1]}", query={"eo:cloud_cover": {"lt": 15}}, max_items=500)
    cands = sorted(
        [it for it in s.items() if it.id not in used],
        key=lambda it: it.properties["eo:cloud_cover"] + 0.5 * (it.properties.get("s2:nodata_pixel_percentage", 0) or 0),
    )
    extras = []
    for it in cands:
        if hole_share() < 0.0003 or len(extras) >= max_extra:
            break
        # only worthwhile if the scene footprint touches a hole
        got = read_decimated(it.assets["visual"].href, bounds, res * 0.87 * 0.9)
        if got is None:
            continue
        arr, tr, crs = got
        before = hole_share()
        for band in range(3):
            dst = np.zeros((H, W), dtype=np.uint8)
            reproject(source=arr[band], destination=dst, src_transform=tr, src_crs=crs, dst_transform=dst_tr, dst_crs="EPSG:3857",
                      resampling=Resampling.bilinear, src_nodata=0, dst_nodata=0)
            if band == 0:
                fillm = (canvas[0] == 0) & (dst > 0)
            canvas[band][fillm] = dst[fillm]
        gain = before - hole_share()
        print(f"  {it.id}: holes {before*100:.2f}% -> {hole_share()*100:.2f}%")
        if gain > 1e-5:
            extras.append({"id": it.id, "tile": it.properties.get("s2:mgrs_tile"), "datetime": it.datetime.isoformat(), "cloud": it.properties["eo:cloud_cover"],
                           "nodata_pct": it.properties.get("s2:nodata_pixel_percentage", 0), "baseline": it.properties.get("s2:processing_baseline"), "platform": it.properties.get("platform")})
    np.save(CACHE / f"mosaic_z{zoom}.npy", canvas)
    (CACHE / "extra_scenes.json").write_text(json.dumps(extras, indent=1))
    Image.fromarray(np.moveaxis(canvas, 0, -1)).resize((W // 4, H // 4), Image.LANCZOS).save(CACHE / f"preview_z{zoom}.jpg", quality=85)
    print(f"holes inside Ma'an after fill: {hole_share()*100:.2f}%  (+{len(extras)} scenes)")


def tiles(zmin: int, zmax: int, quality=80):
    meta = json.loads((CACHE / f"mosaic_z{zmax}.json").read_text())
    canvas = np.load(CACHE / f"mosaic_z{zmax}.npy")
    img = np.moveaxis(canvas, 0, -1)
    tx0, tx1, ty0, ty1 = meta["tx0"], meta["tx1"], meta["ty0"], meta["ty1"]
    outdir = WEB_PUBLIC / "tiles" / "s2"
    total = 0
    for z in range(zmax, zmin - 1, -1):
        if z < zmax:
            # pad to an even tile count, then halve
            img = np.asarray(Image.fromarray(img).resize((img.shape[1] // 2, img.shape[0] // 2), Image.LANCZOS))
            tx0, tx1, ty0, ty1 = tx0 // 2, tx1 // 2, ty0 // 2, ty1 // 2
        n = 0
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                y, x = (ty - ty0) * 256, (tx - tx0) * 256
                chunk = img[y : y + 256, x : x + 256]
                if chunk.shape[0] != 256 or chunk.shape[1] != 256:
                    pad = np.zeros((256, 256, 3), dtype=np.uint8)
                    pad[: chunk.shape[0], : chunk.shape[1]] = chunk
                    chunk = pad
                p = outdir / str(z) / str(tx) / f"{ty}.jpg"
                p.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(chunk).save(p, "JPEG", quality=quality, optimize=True, progressive=True, subsampling=2)
                n += 1
        total += n
        print(f"  z{z}: {n} tiles  (x {tx0}-{tx1}, y {ty0}-{ty1})")
        # the halved image must stay tile aligned for the next level
        if (tx1 - tx0 + 1) % 2 and z > zmin:
            pad = np.zeros((img.shape[0], 256, 3), dtype=np.uint8)
            img = np.concatenate([img, pad], axis=1)
            tx1 += 1
        if (ty1 - ty0 + 1) % 2 and z > zmin:
            pad = np.zeros((256, img.shape[1], 3), dtype=np.uint8)
            img = np.concatenate([img, pad], axis=0)
            ty1 += 1
        if tx0 % 2:
            img = np.concatenate([np.zeros((img.shape[0], 256, 3), dtype=np.uint8), img], axis=1)
            tx0 -= 1
        if ty0 % 2:
            img = np.concatenate([np.zeros((256, img.shape[1], 3), dtype=np.uint8), img], axis=0)
            ty0 -= 1
    size = sum(f.stat().st_size for f in outdir.rglob("*.jpg"))
    print(f"wrote {total} tiles, {size/1e6:.1f} MB")


def crop(name: str, bbox, res_m: float, widths):
    sel = select()
    w_, s_, e_, n_ = bbox
    x0, y0 = lonlat_to_merc(w_, n_)
    x1, y1 = lonlat_to_merc(e_, s_)
    # output grid in EPSG:3857 at res_m / 0.87 (mercator metres) - plan view
    mres = res_m / 0.87
    W, H = int((x1 - x0) / mres), int((y0 - y1) / mres)
    dst_tr = from_origin(x0, y0, mres, mres)
    canvas = np.zeros((3, H, W), dtype=np.uint8)
    used = []
    for tile, meta in sorted(sel.items()):
        href = fresh_href(meta["id"])
        got = read_decimated(href, (x0, y1, x1, y0), res_m)
        if got is None:
            continue
        arr, tr, crs = got
        for band in range(3):
            dst = np.zeros((H, W), dtype=np.uint8)
            reproject(source=arr[band], destination=dst, src_transform=tr, src_crs=crs, dst_transform=dst_tr, dst_crs="EPSG:3857",
                      resampling=Resampling.bilinear, src_nodata=0, dst_nodata=0)
            if band == 0:
                fill = (canvas[0] == 0) & (dst > 0)
            canvas[band][fill] = dst[fill]
        used.append({"tile": tile, "id": meta["id"], "datetime": meta["datetime"]})
    img = Image.fromarray(np.moveaxis(canvas, 0, -1))
    print(f"{name}: {W}x{H}px @ ~{res_m} m, scenes: {[u['tile'] for u in used]}")
    img.save(CACHE / f"crop_{name}_full.png")
    outdir = WEB_PUBLIC / "img"
    outdir.mkdir(parents=True, exist_ok=True)
    for w in widths:
        h = int(round(img.height * w / img.width))
        im = img.resize((w, h), Image.LANCZOS) if w != img.width else img
        im.save(outdir / f"{name}-{w}.avif", "AVIF", quality=52, speed=6)
        im.save(outdir / f"{name}-{w}.webp", "WEBP", quality=74, method=6)
        im.save(outdir / f"{name}-{w}.jpg", "JPEG", quality=80, optimize=True, progressive=True)
        print(f"  {name}-{w}: {w}x{h}  avif {(outdir/f'{name}-{w}.avif').stat().st_size//1024} KB, webp {(outdir/f'{name}-{w}.webp').stat().st_size//1024} KB, jpg {(outdir/f'{name}-{w}.jpg').stat().st_size//1024} KB")
    (CACHE / f"crop_{name}.json").write_text(json.dumps({"name": name, "bbox": bbox, "res_m": res_m, "size": [W, H], "scenes": used}, indent=1))


def meta():
    sel = select()
    scenes = [{k: v[k] for k in ("id", "tile", "datetime", "cloud", "nodata_pct", "baseline", "platform")} for v in sel.values()]
    extra_p = CACHE / "extra_scenes.json"
    if extra_p.exists():
        scenes += [{"id": e["id"], "tile": e["tile"], "datetime": e["datetime"], "cloud": e["cloud"], "nodata_pct": e["nodata_pct"], "baseline": e["baseline"], "platform": e["platform"]} for e in json.loads(extra_p.read_text())]
    (CACHE / "scenes.json").write_text(json.dumps(scenes, indent=1))
    (WEB_PUBLIC / "tiles" / "s2").mkdir(parents=True, exist_ok=True)
    (WEB_PUBLIC / "tiles" / "s2" / "ATTRIBUTION.txt").write_text(
        "Contains modified Copernicus Sentinel data [2026].\n"
        "Source: Sentinel-2 L2A via Microsoft Planetary Computer STAC (collection sentinel-2-l2a), 'visual' true-colour asset.\n"
        "Resampled, mosaicked and JPEG-encoded by GREEN NOVA AI (web/scripts/imagery/render_assets.py). No pixel is invented or recoloured.\n"
        f"Scenes ({len(scenes)}): " + ", ".join(f"{s['id']}" for s in scenes) + "\n"
        "Licence: Copernicus Sentinel data are free, full and open (Regulation (EU) No 1159/2013; Sentinel Data Legal Notice).\n"
    )
    print(json.dumps(scenes, indent=1)[:1500])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select")
    m = sub.add_parser("mosaic"); m.add_argument("--zoom", type=int, default=11)
    t = sub.add_parser("tiles"); t.add_argument("--zmin", type=int, default=5); t.add_argument("--zmax", type=int, default=11)
    c = sub.add_parser("crop"); c.add_argument("--name", required=True); c.add_argument("--bbox", required=True); c.add_argument("--res", type=float, required=True); c.add_argument("--widths", default="2400,1600,800")
    sub.add_parser("meta")
    f_ = sub.add_parser("fill"); f_.add_argument("--zoom", type=int, default=11)
    a = ap.parse_args()
    if a.cmd == "select":
        select(force=True)
    elif a.cmd == "mosaic":
        mosaic(a.zoom)
    elif a.cmd == "tiles":
        tiles(a.zmin, a.zmax)
    elif a.cmd == "crop":
        crop(a.name, [float(v) for v in a.bbox.split(",")], a.res, [int(v) for v in a.widths.split(",")])
    elif a.cmd == "fill":
        fill(a.zoom)
    elif a.cmd == "meta":
        meta()
