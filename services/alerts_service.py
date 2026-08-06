"""Alert cache and geometry enrichment helpers."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from fastapi import HTTPException
from shapely.geometry import mapping, shape

from app_core.upstream_ledger import record_measurement, urlopen

from app_core.paths import CACHE_ROOT
from app_core.refresh_coordinator import Submission, get_refresh_coordinator
from config.alerts_config import GEOMETRY_ENDPOINT_DEFAULTS

_LSR_QUERY_URL = (
    "https://mapservices.weather.noaa.gov/vector/rest/services/"
    "obs/nws_local_storm_reports/MapServer/0/query"
)
_LSR_CACHE_TTL_SECONDS = 5 * 60
_LSR_CACHE_MAX_ENTRIES = 24
_LSR_CACHE: dict[tuple, tuple[float, dict]] = {}
_LSR_CACHE_LOCK = Lock()
_ENRICHED_GEOMETRY_CACHE_MAX_ENTRIES = 1024
_ENRICHED_GEOMETRY_CACHE: OrderedDict[str, dict] = OrderedDict()
_ENRICHED_GEOMETRY_CACHE_LOCK = Lock()
_ALERTS_CACHE_DIR = Path(CACHE_ROOT) / "alerts"
_ALERTS_GENERATION_MANIFEST = _ALERTS_CACHE_DIR / "current_generation.json"
_ALERTS_CACHE_TTL_SECONDS = 35.0
_ALERTS_REFRESH_KEY = ("alerts", "national")
_ALERTS_REFRESH_PROVIDER = "nws-alerts"


def _get_enriched_geometry(cache_key: str) -> Optional[dict]:
    if not cache_key:
        return None
    with _ENRICHED_GEOMETRY_CACHE_LOCK:
        geometry = _ENRICHED_GEOMETRY_CACHE.get(cache_key)
        if geometry is not None:
            _ENRICHED_GEOMETRY_CACHE.move_to_end(cache_key)
        return geometry


def _put_enriched_geometry(cache_key: str, geometry: dict) -> None:
    if not cache_key or not geometry:
        return
    with _ENRICHED_GEOMETRY_CACHE_LOCK:
        _ENRICHED_GEOMETRY_CACHE[cache_key] = geometry
        _ENRICHED_GEOMETRY_CACHE.move_to_end(cache_key)
        while len(_ENRICHED_GEOMETRY_CACHE) > _ENRICHED_GEOMETRY_CACHE_MAX_ENTRIES:
            _ENRICHED_GEOMETRY_CACHE.popitem(last=False)


def _lsr_iso_time(value) -> Optional[str]:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            return None
    text = str(value or "").strip()
    return text or None


def _normalize_lsr_feature(feature: dict) -> Optional[dict]:
    geometry = feature.get("geometry")
    if not geometry:
        return None
    props = feature.get("properties") or {}
    object_id = props.get("objectid")
    magnitude = str(props.get("magnitude") or "").strip()
    units = str(props.get("units") or "").strip()
    return {
        "type": "Feature",
        "id": f"lsr-{object_id}" if object_id is not None else None,
        "geometry": geometry,
        "properties": {
            "event": str(props.get("descript") or "Local Storm Report").strip(),
            "time": _lsr_iso_time(props.get("lsr_validtime"))
            or str(props.get("valid_time") or "").strip()
            or None,
            "location": str(props.get("loc_desc") or "").strip(),
            "state": str(props.get("state") or "").strip(),
            "magnitude": magnitude,
            "units": units,
            "magnitude_label": " ".join(part for part in (magnitude, units) if part),
            "remarks": str(props.get("remarks") or "").strip(),
            "wfo_id": str(props.get("wfo_id") or "").strip(),
            "wfo": str(props.get("wfo") or "").strip(),
            "source": "NOAA/NWS Local Storm Reports",
        },
    }


def get_local_storm_reports(
    *,
    west: Optional[float] = None,
    east: Optional[float] = None,
    south: Optional[float] = None,
    north: Optional[float] = None,
    hours: Optional[int] = None,
) -> dict:
    bounds = None
    if None not in {west, east, south, north}:
        try:
            w, e = sorted((float(west), float(east)))
            s, n = sorted((float(south), float(north)))
            bounds = (w, e, s, n)
        except (TypeError, ValueError):
            bounds = None

    window_hours = max(1, min(int(hours), 72)) if hours is not None else 24
    bounds_part = tuple(round(value, 2) for value in bounds) if bounds else ("national",)
    cache_key = (*bounds_part, window_hours)
    now = time.monotonic()
    with _LSR_CACHE_LOCK:
        cached = _LSR_CACHE.get(cache_key)
        if cached and now - cached[0] < _LSR_CACHE_TTL_SECONDS:
            return cached[1]

    cutoff_ms = int(
        (datetime.now(timezone.utc) - timedelta(hours=window_hours)).timestamp() * 1000
    )
    features: list[dict] = []
    offset = 0
    page_size = 1000
    while True:
        params = {
            "where": "1=1",
            "outFields": (
                "objectid,wfo_id,wfo,lsr_validtime,descript,loc_desc,state,"
                "magnitude,units,remarks,valid_time"
            ),
            "returnGeometry": "true",
            "outSR": "4326",
            "resultOffset": str(offset),
            "resultRecordCount": str(page_size),
            "f": "geojson",
        }
        if bounds:
            w, e, s, n = bounds
            params.update(
                {
                    "geometry": f"{w},{s},{e},{n}",
                    "geometryType": "esriGeometryEnvelope",
                    "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                }
            )

        req = urllib.request.Request(
            f"{_LSR_QUERY_URL}?{urllib.parse.urlencode(params)}",
            headers={"User-Agent": "NCHurricane Dashboard/2026 (+https://nchurricane.com)"},
        )
        try:
            with urlopen(req, timeout=20) as response:
                page = json.load(response)
        except Exception as exc:
            if cached:
                stale_payload = dict(cached[1])
                stale_payload["_stale"] = True
                stale_payload["_error"] = str(exc)
                return stale_payload
            raise HTTPException(
                status_code=503,
                detail=f"NOAA Local Storm Reports unavailable: {exc}",
            )

        page_features = page.get("features") or []
        features.extend(page_features)
        if len(page_features) < page_size:
            break
        offset += len(page_features)
        if offset >= 10000:
            break

    normalized: list[dict] = []
    for feature in features:
        valid_ms = (feature.get("properties") or {}).get("lsr_validtime")
        if isinstance(valid_ms, (int, float)) and valid_ms < cutoff_ms:
            continue
        if (n := _normalize_lsr_feature(feature)) is not None:
            normalized.append(n)
    payload = {
        "type": "FeatureCollection",
        "features": normalized,
        "count": len(normalized),
        "_source": "NOAA/NWS Local Storm Reports MapServer",
        "_updated": datetime.now(timezone.utc).isoformat(),
        "_window_hours": window_hours,
    }
    with _LSR_CACHE_LOCK:
        if len(_LSR_CACHE) >= _LSR_CACHE_MAX_ENTRIES:
            oldest_key = min(_LSR_CACHE, key=lambda key: _LSR_CACHE[key][0])
            _LSR_CACHE.pop(oldest_key, None)
        _LSR_CACHE[cache_key] = (now, payload)
    return payload


def enrich_alert_features_geometry(
    features: list[dict], *, measurement_fields: Optional[dict[str, Any]] = None
) -> None:
    """Fill missing alert geometries using a bounded process-local cache."""
    try:
        from alerts.alerts_utils import (
            CensusCounties,
            _GEOMETRY_PROVENANCE_KEY,
            _GEOMETRY_PROVENANCE_NATIVE,
            _GEOMETRY_PROVENANCE_SAME,
            _GEOMETRY_PROVENANCE_ZONE,
            _prefetch_zone_geometries,
            _resolve_zone_geometry,
        )

        def _feature_cache_key(feat: dict) -> str:
            if not isinstance(feat, dict):
                return ""
            props = feat.get("properties") or {}
            key_data = json.dumps(
                {
                    "zones": sorted(props.get("affectedZones") or []),
                    "same": sorted((props.get("geocode") or {}).get("SAME") or []),
                },
                sort_keys=True,
            )
            return hashlib.sha256(key_data.encode()).hexdigest()

        _prefetch_zone_geometries(features)

        needs_counties = any(
            not feat.get("geometry")
            and (feat.get("properties") or {}).get("geocode", {}).get("SAME")
            for feat in features
            if isinstance(feat, dict)
        )
        if needs_counties:
            CensusCounties.load()

        union_metrics = {"seconds": 0.0, "alerts": 0, "cache_hits": 0, "cache_misses": 0}
        union_metrics_lock = Lock()

        def _enrich_single_feature(feat: dict) -> tuple[dict, Any, str]:
            if not isinstance(feat, dict):
                return feat, None, ""

            cache_key = _feature_cache_key(feat)

            cached_geom = _get_enriched_geometry(cache_key)
            if cached_geom:
                with union_metrics_lock:
                    union_metrics["cache_hits"] += 1
                feat[_GEOMETRY_PROVENANCE_KEY] = (
                    _GEOMETRY_PROVENANCE_ZONE
                    if (feat.get("properties") or {}).get("affectedZones")
                    else _GEOMETRY_PROVENANCE_SAME
                )
                return feat, cached_geom, cache_key

            raw_geom = feat.get("geometry")
            has_valid_geom = False
            if raw_geom:
                try:
                    g = shape(raw_geom)
                    has_valid_geom = g is not None and not g.is_empty
                except Exception:
                    has_valid_geom = False
            if has_valid_geom:
                feat[_GEOMETRY_PROVENANCE_KEY] = _GEOMETRY_PROVENANCE_NATIVE
                return feat, None, cache_key

            props = feat.get("properties") or {}
            final_geom = None
            if cache_key:
                with union_metrics_lock:
                    union_metrics["cache_misses"] += 1

            zone_urls = props.get("affectedZones") or []
            if zone_urls:
                union_started = time.perf_counter()
                final_geom = _resolve_zone_geometry(zone_urls)
                with union_metrics_lock:
                    union_metrics["seconds"] += time.perf_counter() - union_started
                    union_metrics["alerts"] += 1

            if (final_geom is None or final_geom.is_empty) and needs_counties:
                same_codes = (props.get("geocode") or {}).get("SAME") or []
                if same_codes:
                    fips_codes = [
                        c[1:] for c in same_codes if isinstance(c, str) and len(c) == 6
                    ]
                    if fips_codes:
                        final_geom = CensusCounties.get_geometry_for_fips(fips_codes)

            return feat, final_geom, cache_key

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(_enrich_single_feature, features))

        record_measurement(
            stage="alerts.per_alert_zone_union",
            duration_seconds=union_metrics["seconds"],
            fields={
                "alert_count": union_metrics["alerts"],
                **(measurement_fields or {}),
            },
        )
        for feat, final_geom, cache_key in results:
            if final_geom is not None:
                try:
                    if isinstance(final_geom, dict):
                        feat["geometry"] = final_geom
                    elif not final_geom.is_empty:
                        geom_dict = mapping(final_geom)
                        feat["geometry"] = geom_dict
                        if cache_key:
                            _put_enriched_geometry(cache_key, geom_dict)
                    props = feat.get("properties") or {}
                    feat[_GEOMETRY_PROVENANCE_KEY] = (
                        _GEOMETRY_PROVENANCE_ZONE
                        if props.get("affectedZones")
                        else _GEOMETRY_PROVENANCE_SAME
                    )
                except Exception:
                    pass
        record_measurement(
            stage="alerts.enriched_geometry.memory_cache",
            duration_seconds=0.0,
            fields={
                "cache_hits": union_metrics["cache_hits"],
                "cache_misses": union_metrics["cache_misses"],
                "cache_entries": len(_ENRICHED_GEOMETRY_CACHE),
                "cache_max_entries": _ENRICHED_GEOMETRY_CACHE_MAX_ENTRIES,
                **(measurement_fields or {}),
            },
        )

    except Exception as exc:
        print(f"[WARN] Alert geometry enrichment skipped: {exc}")


def _refresh_alerts_cache() -> dict:
    from workers.alerts_worker import run_alerts_worker

    summary = run_alerts_worker(force=True)
    if summary is None:
        raise RuntimeError("Alerts refresh did not publish a generation")
    return {
        "source_timestamp": summary.get("updated"),
        "generation": summary.get("generation"),
    }


def _start_alerts_refresh() -> Submission:
    return get_refresh_coordinator().submit(
        key=_ALERTS_REFRESH_KEY,
        provider=_ALERTS_REFRESH_PROVIDER,
        function=_refresh_alerts_cache,
    )


def _safe_generation_path(relative_path: object) -> Path | None:
    if not isinstance(relative_path, str) or not relative_path.strip():
        return None
    candidate = (_ALERTS_CACHE_DIR / relative_path).resolve()
    try:
        candidate.relative_to(_ALERTS_CACHE_DIR.resolve())
    except ValueError:
        return None
    return candidate


def _resolve_alerts_cache_file(use_low_detail: bool) -> tuple[Path | None, str | None, Path | None]:
    try:
        manifest = json.loads(_ALERTS_GENERATION_MANIFEST.read_text(encoding="utf-8"))
        files = manifest.get("files") or {}
        relative_path = files.get("display_low" if use_low_detail else "full")
        cache_file = _safe_generation_path(relative_path)
        generation = str(manifest.get("generation") or "").strip() or None
        if cache_file is not None and cache_file.is_file():
            return cache_file, generation, _ALERTS_GENERATION_MANIFEST
    except (OSError, json.JSONDecodeError, AttributeError):
        pass

    fallback = _ALERTS_CACHE_DIR / (
        "national_display_low.geojson" if use_low_detail else "national_full.geojson"
    )
    if not fallback.is_file():
        fallback = _ALERTS_CACHE_DIR / "national.geojson"
    return (fallback if fallback.is_file() else None), None, (
        fallback if fallback.is_file() else None
    )


def get_alerts_data(
    *,
    state: Optional[str] = None,
    geometry_mode: Optional[str] = None,
    zoom_bucket: Optional[str] = None,
    west: Optional[float] = None,
    east: Optional[float] = None,
    south: Optional[float] = None,
    north: Optional[float] = None,
) -> dict:
    mode = (
        str(geometry_mode or GEOMETRY_ENDPOINT_DEFAULTS["geometry_mode"])
        .lower()
        .strip()
    )
    bucket = str(zoom_bucket or GEOMETRY_ENDPOINT_DEFAULTS["zoom_bucket"]).lower().strip()

    if mode not in {"full", "display"}:
        mode = GEOMETRY_ENDPOINT_DEFAULTS["geometry_mode"]
    if bucket not in {"low", "high"}:
        bucket = GEOMETRY_ENDPOINT_DEFAULTS["zoom_bucket"]

    # Zoom owns the payload contract. Below z8, serve the national simplified
    # derived geometry; at z8+, serve bbox-filtered canonical geometry.
    use_low_detail = bucket == "low"
    mode = "display" if use_low_detail else "full"
    coordinator = get_refresh_coordinator()
    coordinator.record_presence(
        key=_ALERTS_REFRESH_KEY,
        provider=_ALERTS_REFRESH_PROVIDER,
    )
    cache_file, generation, freshness_file = _resolve_alerts_cache_file(
        use_low_detail
    )
    if cache_file is None:
        submission = _start_alerts_refresh()
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Alerts cache is warming",
                "cache_state": (
                    "backoff"
                    if submission.status == "backoff"
                    else "refreshing"
                    if submission.status in {"queued", "running"}
                    else "missing"
                ),
                "refreshing": submission.status in {"queued", "running"},
                "retry_after_seconds": submission.retry_after_seconds,
                "capability": "available",
            },
        )

    try:
        with cache_file.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if generation and data.get("_generation") != generation:
        raise HTTPException(status_code=503, detail="Alerts generation is changing")

    cache_age_seconds = max(
        0.0,
        time.time() - (freshness_file or cache_file).stat().st_mtime,
    )
    stale = cache_age_seconds >= _ALERTS_CACHE_TTL_SECONDS
    submission = _start_alerts_refresh() if stale else None
    refreshing = bool(
        submission and submission.status in {"queued", "running"}
    )
    if submission and submission.status == "backoff":
        cache_state = "backoff"
    elif stale and refreshing:
        cache_state = "stale_refreshing"
    elif stale:
        cache_state = "stale"
    else:
        cache_state = "fresh"

    features = data.get("features", [])

    if state:
        state_upper = state.upper().strip()

        def _matches(feat: dict) -> bool:
            props = feat.get("properties") or {}
            for zone in props.get("affectedZones") or []:
                if f"/{state_upper}" in str(zone):
                    return True
            return state_upper in str(props.get("areaDesc") or "")

        features = [f for f in features if _matches(f)]

    if (
        bucket == "high"
        and west is not None
        and east is not None
        and south is not None
        and north is not None
    ):
        try:
            w = float(west)
            e = float(east)
            s = float(south)
            n = float(north)
            if w > e:
                w, e = e, w
            if s > n:
                s, n = n, s

            features = [f for f in features if _feature_overlaps_bbox(f, w, e, s, n)]
        except Exception:
            pass

    simplified_count = 0
    if mode == "display" and bucket == "low":
        simplified_count = sum(1 for f in features if f.get("_simplified") is True)

    response_features = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        clean_feature = dict(feat)
        clean_feature.pop("_simplified", None)
        clean_feature.pop("_geometry_provenance", None)
        response_features.append(clean_feature)

    return {
        "type": "FeatureCollection",
        "features": response_features,
        "_source": data.get("_source", "NWS"),
        "_updated": data.get("_updated"),
        "_generation": data.get("_generation") or generation,
        "count": len(response_features),
        "_geometry_mode": mode,
        "_zoom_bucket": bucket,
        "_simplified_feature_count": simplified_count,
        "_simplification_metrics": data.get("_simplification_metrics", {}),
        "cache_state": cache_state,
        "refreshing": refreshing,
        "source_timestamp": data.get("_updated"),
        "cache_age_seconds": round(cache_age_seconds, 3),
        "retry_after_seconds": (
            submission.retry_after_seconds if submission else None
        ),
        "capability": "available",
    }


def _iter_coords(node):
    if isinstance(node, (list, tuple)):
        if len(node) >= 2 and all(isinstance(v, (int, float)) for v in node[:2]):
            yield float(node[0]), float(node[1])
        else:
            for child in node:
                yield from _iter_coords(child)


def _feature_overlaps_bbox(feat: dict, w: float, e: float, s: float, n: float) -> bool:
    geom = (feat or {}).get("geometry") or {}
    coords = geom.get("coordinates")
    if not coords:
        return False
    min_x = float("inf")
    max_x = float("-inf")
    min_y = float("inf")
    max_y = float("-inf")
    seen = False
    for x, y in _iter_coords(coords):
        seen = True
        if x < min_x:
            min_x = x
        if x > max_x:
            max_x = x
        if y < min_y:
            min_y = y
        if y > max_y:
            max_y = y
    if not seen:
        return False
    return not (max_x < w or min_x > e or max_y < s or min_y > n)
