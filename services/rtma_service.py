"""RTMA source resolution, rendering, and frame helpers."""

from datetime import timezone
import hashlib
import json
import os

from fastapi import HTTPException

from app_core.paths import BASE_DIR, CACHE_ROOT
from config.geo_config import STATE_BOUNDS
from config.rtma_config import RTMA_STREAM_MAX_HOURS, clamp_stream_hours


def get_rtma_points(
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    source_data_key: str | None = None,
    south: float | None = None,
    west: float | None = None,
    north: float | None = None,
    east: float | None = None,
    stride: int = 30,
) -> dict:
    from rtma.rtma_utils import (
        build_rtma_legend,
        ensure_rtma_city_geojson,
        get_product_config,
        iter_rtma_sources,
        resolve_rtma_source,
        resolve_rtma_source_by_data_key,
    )

    region_key = region.upper()
    if region_key not in STATE_BOUNDS:
        raise HTTPException(status_code=400, detail=f"Unknown RTMA region '{region}'.")

    if product == "temperature_change_24h" and stream != "rtma_hourly":
        raise HTTPException(
            status_code=400,
            detail="RTMA 24-hour temperature change is only available on rtma_hourly.",
        )

    if south is not None and west is not None and north is not None and east is not None:
        bounds_values = (float(south), float(west), float(north), float(east))
    else:
        bounds_values = None

    def _read_points_from_cache(path: str) -> list[dict]:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"RTMA city-point read error: {exc}"
            )

        points: list[dict] = []
        if data.get("v") == 1:
            for row in data.get("points", []):
                if len(row) < 3:
                    continue
                lat, lon, val = float(row[0]), float(row[1]), float(row[2])
                rank = row[3] if len(row) > 3 else None
                if bounds_values is not None:
                    bound_s, bound_w, bound_n, bound_e = bounds_values
                    if (
                        lat < bound_s
                        or lat > bound_n
                        or lon < bound_w
                        or lon > bound_e
                    ):
                        continue
                points.append({"lat": lat, "lon": lon, "value": val, "rank": rank})
            return points

        for feat in data.get("features", []):
            geom = feat.get("geometry") or {}
            if geom.get("type") != "Point":
                continue
            coords = geom.get("coordinates") or []
            if len(coords) < 2:
                continue
            lon = float(coords[0])
            lat = float(coords[1])
            if bounds_values is not None:
                bound_s, bound_w, bound_n, bound_e = bounds_values
                if lat < bound_s or lat > bound_n or lon < bound_w or lon > bound_e:
                    continue
            props = feat.get("properties") or {}
            val = props.get("value")
            if val is None:
                continue
            points.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "value": float(val),
                    "rank": props.get("rank"),
                }
            )
        return points

    try:
        product_cfg = get_product_config(product)
        if source_data_key:
            token = "".join(
                ch if ch.isalnum() or ch in {"-", "_", "."} else "_"
                for ch in source_data_key
            )
            points_dir = os.path.join(CACHE_ROOT, "rtma", "points", region_key, stream)
            cached_geojson_path = os.path.join(
                points_dir, f"{product}__{token}.geojson"
            )
            cached_meta_path = cached_geojson_path.replace(".geojson", "_meta.json")
            if os.path.exists(cached_geojson_path):
                meta = None
                if os.path.exists(cached_meta_path):
                    try:
                        with open(cached_meta_path, "r", encoding="utf-8") as handle:
                            meta = json.load(handle)
                    except Exception:
                        meta = None
                points = _read_points_from_cache(cached_geojson_path)
                return {
                    "points": points,
                    "units": product_cfg.get("units", ""),
                    "full_name": product_cfg.get("label", product),
                    "vmin": product_cfg.get("vmin"),
                    "vmax": product_cfg.get("vmax"),
                    "legend": build_rtma_legend(product_cfg),
                    "timestamp": (meta or {}).get("timestamp")
                    or (meta or {}).get("source_valid_time")
                    or None,
                    "source": source_data_key,
                    "source_data_key": source_data_key,
                    "region": region_key,
                    "stream": stream,
                    "product": product,
                }

            source = resolve_rtma_source_by_data_key(
                region_key,
                stream,
                product,
                source_data_key,
                hours_back=clamp_stream_hours(stream),
            )
        else:
            source = resolve_rtma_source(region_key, stream, product)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    cities_path = os.path.join(BASE_DIR, "data", "us-cities.json")
    if not os.path.exists(cities_path):
        raise HTTPException(status_code=500, detail="Missing data/us-cities.json")

    geojson_path = None
    meta = None
    primary_exc = None

    try:
        geojson_path, meta = ensure_rtma_city_geojson(
            CACHE_ROOT,
            source,
            region_key,
            stream,
            product,
            cities_path,
            source_data_key=source_data_key,
        )
    except Exception as exc:
        primary_exc = exc

    if not geojson_path:
        if source_data_key:
            raise HTTPException(
                status_code=503,
                detail=(
                    "RTMA city-point generation failed for requested frame: "
                    f"data_key={source_data_key}; error={primary_exc}"
                ),
            )
        fallback_exc = None
        tried = 0
        for alt_source in iter_rtma_sources(region_key, stream, product):
            if alt_source.data_key == source.data_key:
                continue
            tried += 1
            if tried > 8:
                break
            try:
                geojson_path, meta = ensure_rtma_city_geojson(
                    CACHE_ROOT,
                    alt_source,
                    region_key,
                    stream,
                    product,
                    cities_path,
                    source_data_key=source_data_key,
                )
                source = alt_source
                break
            except Exception as exc:
                fallback_exc = exc

        if not geojson_path:
            raise HTTPException(
                status_code=503,
                detail=(
                    "RTMA city-point generation failed: "
                    f"primary={primary_exc}; fallback={fallback_exc}"
                ),
            )

    points = _read_points_from_cache(geojson_path)

    return {
        "points": points,
        "units": product_cfg.get("units", ""),
        "full_name": product_cfg.get("label", product),
        "vmin": product_cfg.get("vmin"),
        "vmax": product_cfg.get("vmax"),
        "legend": build_rtma_legend(product_cfg),
        "timestamp": (meta or {}).get("timestamp") or source.valid_time.isoformat(),
        "source": source.data_key,
        "source_data_key": source.data_key,
        "region": region_key,
        "stream": stream,
        "product": product,
    }


def get_rtma_grid(
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    source_data_key: str | None = None,
    stride: int = 2,
) -> dict:
    from rtma.rtma_utils import (
        build_rtma_legend,
        ensure_rtma_grid_json,
        get_product_config,
        iter_rtma_sources,
        resolve_rtma_source,
        resolve_rtma_source_by_data_key,
    )

    region_key = region.upper()
    if region_key not in STATE_BOUNDS:
        raise HTTPException(status_code=400, detail=f"Unknown RTMA region '{region}'.")

    if product == "temperature_change_24h" and stream != "rtma_hourly":
        raise HTTPException(
            status_code=400,
            detail="RTMA 24-hour temperature change is only available on rtma_hourly.",
        )

    stride = max(1, min(stride, 64))

    try:
        product_cfg = get_product_config(product)
        if source_data_key:
            source = resolve_rtma_source_by_data_key(
                region_key,
                stream,
                product,
                source_data_key,
                hours_back=clamp_stream_hours(stream),
            )
        else:
            source = resolve_rtma_source(region_key, stream, product)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    grid_path = None
    meta = None
    primary_exc = None

    try:
        grid_path, meta = ensure_rtma_grid_json(
            CACHE_ROOT, source, region_key, stream, product, stride=stride
        )
    except Exception as exc:
        primary_exc = exc

    if not grid_path:
        tried = 0
        for alt_source in iter_rtma_sources(region_key, stream, product):
            if alt_source.data_key == source.data_key:
                continue
            tried += 1
            if tried > 8:
                break
            try:
                grid_path, meta = ensure_rtma_grid_json(
                    CACHE_ROOT, alt_source, region_key, stream, product, stride=stride
                )
                source = alt_source
                break
            except Exception:
                pass

    if not grid_path:
        raise HTTPException(
            status_code=503,
            detail=f"RTMA grid generation failed: {primary_exc}",
        )

    try:
        with open(grid_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"RTMA grid read error: {exc}")

    return {
        "v": 1,
        "product": product,
        "units": product_cfg.get("units", ""),
        "full_name": product_cfg.get("label", product),
        "vmin": product_cfg.get("vmin"),
        "vmax": product_cfg.get("vmax"),
        "legend": build_rtma_legend(product_cfg),
        "timestamp": (meta or {}).get("timestamp") or source.valid_time.isoformat(),
        "source_data_key": source.data_key,
        "region": region_key,
        "stream": stream,
        "stride": stride,
        "points": data.get("points", []),
    }


def get_rtma_data(
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    source_data_key: str | None = None,
    south: float = 21.0,
    west: float = -130.0,
    north: float = 52.0,
    east: float = -60.0,
) -> dict:
    from rtma.rtma_utils import (
        _render_rtma_png_standalone,
        ensure_rtma_grib,
        get_product_config,
        iter_rtma_sources,
        resolve_rtma_source,
        resolve_rtma_source_by_data_key,
    )

    region_key = region.upper()
    if region_key not in STATE_BOUNDS:
        raise HTTPException(status_code=400, detail=f"Unknown RTMA region '{region}'.")

    if product == "temperature_change_24h" and stream != "rtma_hourly":
        raise HTTPException(
            status_code=400,
            detail="RTMA 24-hour temperature change is only available on rtma_hourly.",
        )

    try:
        product_cfg = get_product_config(product)
        if source_data_key:
            source = resolve_rtma_source_by_data_key(
                region_key,
                stream,
                product,
                source_data_key,
                hours_back=clamp_stream_hours(stream),
            )
        else:
            source = resolve_rtma_source(region_key, stream, product)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    try:
        grib_path = ensure_rtma_grib(CACHE_ROOT, source)
    except Exception as primary_exc:
        if source_data_key:
            raise HTTPException(
                status_code=503,
                detail=(
                    "RTMA download failed for requested frame: "
                    f"data_key={source_data_key}; error={primary_exc}"
                ),
            )
        grib_path = None
        fallback_exc = None
        tried = 0
        for alt_source in iter_rtma_sources(region_key, stream, product):
            if alt_source.data_key == source.data_key:
                continue
            tried += 1
            if tried > 8:
                break
            try:
                grib_path = ensure_rtma_grib(CACHE_ROOT, alt_source, force_refresh=True)
                source = alt_source
                break
            except Exception as exc:
                fallback_exc = exc

        if not grib_path:
            raise HTTPException(
                status_code=503,
                detail=(
                    "RTMA download failed: "
                    f"primary={primary_exc}; fallback={fallback_exc}"
                ),
            )

    bounds_key = hashlib.md5(
        f"{region_key}_{stream}_{product}_{source.data_key}_{south:.2f}_{west:.2f}_{north:.2f}_{east:.2f}".encode()
    ).hexdigest()[:12]
    product_cache_dir = os.path.join(CACHE_ROOT, "rtma", region_key, stream, product)
    os.makedirs(product_cache_dir, exist_ok=True)
    png_path = os.path.join(product_cache_dir, f"overlay_{bounds_key}.png")

    sidecar_bounds = png_path.replace(".png", "_bounds.json")
    sidecar_meta = png_path.replace(".png", "_meta.json")
    png_stale = not os.path.exists(png_path) or os.path.getmtime(
        png_path
    ) < os.path.getmtime(grib_path)

    if png_stale:
        try:
            png_path, actual_bounds, render_meta = _render_rtma_png_standalone(
                grib_path,
                product,
                [west, east, south, north],
                png_path,
                cache_root=CACHE_ROOT,
                source=source,
                region=region_key,
                stream=stream,
            )
        except Exception as first_exc:
            if source_data_key:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "RTMA render error for requested frame: "
                        f"data_key={source_data_key}; error={first_exc}"
                    ),
                )
            try:
                grib_path = ensure_rtma_grib(CACHE_ROOT, source, force_refresh=True)
                png_path, actual_bounds, render_meta = _render_rtma_png_standalone(
                    grib_path,
                    product,
                    [west, east, south, north],
                    png_path,
                    cache_root=CACHE_ROOT,
                    source=source,
                    region=region_key,
                    stream=stream,
                )
            except Exception as exc:
                retry_exc = exc
                alt_render = None
                alt_exc = None
                tried = 0
                for alt_source in iter_rtma_sources(region_key, stream, product):
                    if alt_source.data_key == source.data_key:
                        continue
                    tried += 1
                    if tried > 8:
                        break
                    try:
                        alt_grib_path = ensure_rtma_grib(
                            CACHE_ROOT, alt_source, force_refresh=True
                        )
                        alt_render = _render_rtma_png_standalone(
                            alt_grib_path,
                            product,
                            [west, east, south, north],
                            png_path,
                            cache_root=CACHE_ROOT,
                            source=alt_source,
                            region=region_key,
                            stream=stream,
                        )
                        source = alt_source
                        break
                    except Exception as inner_exc:
                        alt_exc = inner_exc

                if alt_render is not None:
                    png_path, actual_bounds, render_meta = alt_render
                else:
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "RTMA render error after cache refresh: "
                            f"initial={first_exc}; retry={retry_exc}; fallback={alt_exc}"
                        ),
                    )
    else:
        try:
            with open(sidecar_bounds, "r", encoding="utf-8") as handle:
                actual_bounds = json.load(handle)
        except Exception:
            actual_bounds = [west, east, south, north]
        try:
            with open(sidecar_meta, "r", encoding="utf-8") as handle:
                render_meta = json.load(handle)
        except Exception:
            render_meta = {
                "full_name": product_cfg.get("label", product),
                "units": product_cfg.get("units", ""),
                "vmin": product_cfg.get("vmin"),
                "vmax": product_cfg.get("vmax"),
                "legend": None,
                "timestamp": source.valid_time.isoformat(),
            }

    if product != "wind_direction":
        try:
            from workers.rtma_worker import _render_overlay_for_source

            _render_overlay_for_source(
                CACHE_ROOT,
                source,
                region_key,
                stream,
                product,
                keep_n=30,
            )
        except Exception:
            pass

    rel = os.path.relpath(png_path, CACHE_ROOT).replace("\\", "/")
    return {
        "image_url": f"/cache/{rel}",
        "bounds": actual_bounds,
        "region": region_key,
        "stream": stream,
        "product": product,
        "full_name": render_meta.get("full_name", product_cfg.get("label", product)),
        "units": render_meta.get("units", product_cfg.get("units", "")),
        "vmin": render_meta.get("vmin", product_cfg.get("vmin")),
        "vmax": render_meta.get("vmax", product_cfg.get("vmax")),
        "legend": render_meta.get("legend"),
        "timestamp": render_meta.get("timestamp") or source.valid_time.isoformat(),
        "source_data_key": source.data_key,
    }


def get_rtma_frames(
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    max_hours: int | None = None,
) -> dict:
    from rtma.rtma_utils import get_product_config, iter_rtma_sources_within_hours

    region_key = region.upper()
    if region_key not in STATE_BOUNDS:
        raise HTTPException(status_code=400, detail=f"Unknown RTMA region '{region}'.")

    if stream not in RTMA_STREAM_MAX_HOURS:
        raise HTTPException(
            status_code=400, detail=f"Unsupported RTMA stream '{stream}'."
        )

    if product == "temperature_change_24h" and stream != "rtma_hourly":
        raise HTTPException(
            status_code=400,
            detail="RTMA 24-hour temperature change is only available on rtma_hourly.",
        )

    try:
        product_cfg = get_product_config(product)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    hours_back = clamp_stream_hours(stream, max_hours)
    try:
        frames_desc = list(
            iter_rtma_sources_within_hours(
                region_key,
                stream,
                product,
                hours_back=hours_back,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    frames = [
        {
            "source_data_key": src.data_key,
            "timestamp": src.valid_time.astimezone(timezone.utc).isoformat(),
            "region": region_key,
            "stream": stream,
            "product": product,
        }
        for src in sorted(frames_desc, key=lambda x: x.valid_time)
    ]

    return {
        "region": region_key,
        "stream": stream,
        "product": product,
        "full_name": product_cfg.get("label", product),
        "units": product_cfg.get("units", ""),
        "max_hours": int(RTMA_STREAM_MAX_HOURS[stream]),
        "hours_back": hours_back,
        "frame_count": len(frames),
        "frames": frames,
    }
