"""HTTP routes. Responses are JSON in the shapes web/src/lib/types.ts expects; errors are {"error": {code, message}} with no paths or traces."""
from __future__ import annotations

import io
import json
from pathlib import Path

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse

from .errors import ApiError, ModelUnavailable, NotFound, scrub_obj
from .regions import get_region, load_regions
from .security import ip_hash
from .validation import check_job_id, check_polygon_id, check_region_id, region_of_polygon_id, validate_bbox

router = APIRouter(prefix="/v1")


def _json(obj, status: int = 200) -> Response:
    return Response(content=json.dumps(obj, separators=(",", ":")), status_code=status, media_type="application/json")


def _st(request: Request):
    return request.app.state.gn


@router.get("/regions")
def regions(request: Request):
    st = _st(request)
    out = []
    for r in load_regions(st.settings.regions_file).values():
        s1 = st.suit.status(r.id)
        s2 = st.rest.status(r.id)
        out.append(
            {
                "id": r.id, "country": r.country, "name": r.name, "iso": r.iso, "bbox": list(r.bbox), "boundary_area_km2": r.area_km2,
                "available": bool(s1["available"] or s2["available"]),
                "models": {"suitability": s1, "restoration": s2},
            }
        )
    out.sort(key=lambda x: (not x["available"], x["name"]))
    return _json({"country": "JO", "regions": out})


@router.get("/regions/{region_id}/boundary")
def boundary(request: Request, region_id: str):
    r = get_region(_st(request).settings.regions_file, check_region_id(region_id))
    return _json({"type": "Feature", "geometry": r.feature["geometry"], "properties": {"name": r.name, "id": r.id, "iso": r.iso}})


@router.get("/regions/{region_id}/suitability/run")
def suitability_run(request: Request, region_id: str):
    st = _st(request)
    region_id = check_region_id(region_id)
    get_region(st.settings.regions_file, region_id)
    st.suit.require(region_id)
    return _json(st.suit.run(region_id))


@router.get("/regions/{region_id}/suitability/polygons")
def suitability_polygons(request: Request, region_id: str):
    st = _st(request)
    region_id = check_region_id(region_id)
    get_region(st.settings.regions_file, region_id)
    fc = st.suit.polygons(region_id)
    return _json({"type": "FeatureCollection", "features": fc["features"]})


@router.get("/regions/{region_id}/restoration/layer")
def restoration_layer(request: Request, region_id: str):
    st = _st(request)
    region_id = check_region_id(region_id)
    get_region(st.settings.regions_file, region_id)
    known = set(st.suit.by_id(region_id)) if st.suit.available(region_id) else None
    return _json(st.rest.slim_layer(region_id, known))


@router.post("/jobs")
async def create_job(request: Request):
    st = _st(request)
    try:
        body = await request.json()
    except ValueError:
        raise ApiError("Request body must be JSON.", code="invalid_json") from None
    if not isinstance(body, dict):
        raise ApiError("Request body must be a JSON object.", code="invalid_json")
    extra = set(body) - {"kind", "region_id", "polygon_ids"}
    if extra:
        raise ApiError("Unknown fields in request.", code="invalid_fields")
    ip = request.state.client_ip
    row, cached = st.jobs.submit(str(body.get("kind", "")), str(body.get("region_id", "")), body.get("polygon_ids"), ip, ip_hash(ip))
    v = st.jobs.view(row)
    v["cached"] = cached
    return _json(v, 200 if cached else 202)


@router.get("/jobs/{job_id}")
def get_job(request: Request, job_id: str):
    st = _st(request)
    return _json(st.jobs.view(st.jobs.get(check_job_id(job_id))))


@router.post("/jobs/{job_id}/cancel")
def cancel_job(request: Request, job_id: str):
    st = _st(request)
    return _json(st.jobs.view(st.jobs.cancel(check_job_id(job_id))))


@router.get("/jobs/{job_id}/result")
def job_result(request: Request, job_id: str):
    st = _st(request)
    return _json(scrub_obj(st.jobs.result(check_job_id(job_id))))


@router.get("/land/{polygon_id}")
def land(request: Request, polygon_id: str):
    st = _st(request)
    pid = check_polygon_id(polygon_id)
    region = region_of_polygon_id(pid)
    get_region(st.settings.regions_file, region)
    feat = st.suit.by_id(region).get(pid)
    if not feat:
        raise NotFound("Land unit not found in the current analysis.", code="unknown_polygon")
    c = feat["properties"]["class_code"]
    restoration = None
    note = None
    if st.rest.available(region):
        restoration = st.rest.by_source_id(region).get(pid)
    if restoration is None:
        if c == 5:
            note = "Class 5 land is excluded by a legal or environmental restriction. It is never treated as restorable; the restriction is reported instead."
        elif c in (1, 2):
            note = f"Restoration analysis applies to class 3 and 4 land. This unit is class {c}."
        elif not st.rest.available(region):
            note = "Model 2 (restoration potential) is not available for this region yet."
        else:
            note = "No restoration result exists for this unit in the Model 2 output."
    return _json({"suitability": feat, "restoration": restoration, "restoration_note": note, "demo": False})


@router.get("/land/{polygon_id}/geotiff")
def land_geotiff(request: Request, polygon_id: str, layer: str = Query("suitability", pattern="^(suitability|feasibility|post_restoration)$")):
    """GeoTIFF clip (bounding window, masked to the unit) of a real model raster for one land unit."""
    st = _st(request)
    pid = check_polygon_id(polygon_id)
    region = region_of_polygon_id(pid)
    get_region(st.settings.regions_file, region)
    feat = st.suit.by_id(region).get(pid)
    if not feat:
        raise NotFound("Land unit not found in the current analysis.", code="unknown_polygon")
    files = {
        "suitability": (st.settings.models_dir / "suitability" / "outputs" / region / "suitability.tif", st.suit),
        "feasibility": (st.settings.models_dir / "restoration" / "outputs" / region / "restoration_feasibility.tif", st.rest),
        "post_restoration": (st.settings.models_dir / "restoration" / "outputs" / region / "post_restoration_suitability.tif", st.rest),
    }
    path, adapter = files[layer]
    if not path.is_file():
        raise ModelUnavailable(f"The {layer.replace('_', ' ')} raster is not available yet.", model=adapter.model)
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.mask import mask as rmask
    from rasterio.warp import transform_geom

    try:
        with rasterio.open(path) as src:
            geom = transform_geom("EPSG:4326", src.crs, feat["geometry"]) if src.crs else feat["geometry"]
            data, transform = rmask(src, [geom], crop=True, nodata=src.nodata if src.nodata is not None else 0)
            profile = src.profile.copy()
            profile.update(driver="GTiff", height=data.shape[1], width=data.shape[2], transform=transform, compress="deflate")
            profile.pop("blockxsize", None)
            profile.pop("blockysize", None)
            profile.pop("tiled", None)
            with MemoryFile() as mem:
                with mem.open(**profile) as dst:
                    dst.write(data)
                    dst.update_tags(green_nova_layer=layer, green_nova_polygon=pid)
                blob = mem.read()
    except ValueError:
        raise ApiError("This land unit does not overlap the raster.", code="no_overlap", status=422) from None
    name = f"green-nova-{layer}-{pid}.tif"
    return Response(content=blob, media_type="image/tiff", headers={"Content-Disposition": f'attachment; filename="{name}"'})
