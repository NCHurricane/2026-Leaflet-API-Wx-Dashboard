"""Alert cache, geometry enrichment, and selector compatibility helpers."""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException
from shapely.geometry import mapping, shape

from app_core.paths import CACHE_ROOT
from config.alerts_config import (
    ALERT_COLORS,
    DEFAULT_COLOR,
    GEOMETRY_ENDPOINT_DEFAULTS,
    HAZARD_CATEGORIES,
    HAZARD_CATEGORY_ALIASES,
)


def enrich_alert_features_geometry(features: list[dict]) -> None:
    """Fill missing alert geometries using parallel enrichment with geometry caching."""
    try:
        from alerts.alerts_utils import (
            CensusCounties,
            _prefetch_zone_geometries,
            _resolve_zone_geometry,
        )

        geom_cache = {}
        try:
            cache_path = Path(CACHE_ROOT) / "alerts" / "enriched_geom_cache.json"
            if cache_path.exists():
                geom_cache = json.load(cache_path.open())
        except Exception:
            pass

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
            return hashlib.md5(key_data.encode()).hexdigest()

        _prefetch_zone_geometries(features)

        needs_counties = any(
            not feat.get("geometry")
            and (feat.get("properties") or {}).get("geocode", {}).get("SAME")
            for feat in features
            if isinstance(feat, dict)
        )
        if needs_counties:
            CensusCounties.load()

        def _enrich_single_feature(feat: dict) -> tuple[dict, Any, str]:
            if not isinstance(feat, dict):
                return feat, None, ""

            cache_key = _feature_cache_key(feat)

            if cache_key and cache_key in geom_cache:
                cached_geom = geom_cache[cache_key]
                if cached_geom:
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
                return feat, None, cache_key

            props = feat.get("properties") or {}
            final_geom = None

            zone_urls = props.get("affectedZones") or []
            if zone_urls:
                final_geom = _resolve_zone_geometry(zone_urls)

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

        for feat, final_geom, cache_key in results:
            if final_geom is not None:
                try:
                    if isinstance(final_geom, dict):
                        feat["geometry"] = final_geom
                    elif not final_geom.is_empty:
                        geom_dict = mapping(final_geom)
                        feat["geometry"] = geom_dict
                        if cache_key:
                            geom_cache[cache_key] = geom_dict
                except Exception:
                    pass

        try:
            cache_path = Path(CACHE_ROOT) / "alerts" / "enriched_geom_cache.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(geom_cache), encoding="utf-8")
        except Exception:
            pass

    except Exception as exc:
        print(f"[WARN] Alert geometry enrichment skipped: {exc}")


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

    if mode == "display" and bucket == "low":
        cache_file = os.path.join(CACHE_ROOT, "alerts", "national_display_low.geojson")
    else:
        cache_file = os.path.join(CACHE_ROOT, "alerts", "national_full.geojson")

    if not os.path.exists(cache_file):
        cache_file = os.path.join(CACHE_ROOT, "alerts", "national.geojson")

    if not os.path.exists(cache_file):
        try:
            from workers.alerts_worker import run_alerts_worker

            run_alerts_worker()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Alerts cache not yet available: {exc}",
            )

    try:
        with open(cache_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

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

    if west is not None and east is not None and south is not None and north is not None:
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
        response_features.append(clean_feature)

    return {
        "type": "FeatureCollection",
        "features": response_features,
        "_source": data.get("_source", "NWS"),
        "_updated": data.get("_updated"),
        "count": len(response_features),
        "_geometry_mode": mode,
        "_zoom_bucket": bucket,
        "_simplified_feature_count": simplified_count,
        "_simplification_metrics": data.get("_simplification_metrics", {}),
    }


def get_alert_polygons(
    *, region: str = "CONUS", hazard: str = "All Alerts", wfo: Optional[str] = None
) -> dict:
    region_upper = (region or "CONUS").strip().upper()
    state = None if region_upper in {"", "CONUS", "WORLD"} else region_upper
    payload = get_alerts_data(state=state)
    features = payload.get("features") or []

    hazard_name = HAZARD_CATEGORY_ALIASES.get(hazard, hazard)
    allowed_events = HAZARD_CATEGORIES.get(hazard_name)
    if allowed_events is not None:
        allowed = {str(event).lower() for event in allowed_events}
        features = [
            f
            for f in features
            if str((f.get("properties") or {}).get("event") or "").lower() in allowed
        ]

    wfo_code = (wfo or "").strip().upper()
    if wfo_code:
        features = [f for f in features if _feature_matches_wfo(f, wfo_code)]

    feature_collection = {
        "type": "FeatureCollection",
        "features": [_selector_feature(f) for f in features if f.get("geometry")],
    }

    return {
        "feature_collection": feature_collection,
        "count": len(feature_collection["features"]),
        "_source": payload.get("_source", "NWS"),
        "_updated": payload.get("_updated"),
        "region": region_upper,
        "hazard": hazard_name,
        "wfo": wfo_code or None,
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


def _feature_matches_wfo(feat: dict, wfo_code: str) -> bool:
    props = feat.get("properties") or {}
    sender_code = str(props.get("senderCode") or "").upper()
    if sender_code and wfo_code in sender_code:
        return True
    params = props.get("parameters") or {}
    if isinstance(params, dict):
        for key in ["WMOidentifier", "AWIPSidentifier", "NWSidentifier"]:
            value = params.get(key)
            if value and wfo_code in str(value).upper():
                return True
    for zone in props.get("affectedZones") or []:
        if f"/{wfo_code}" in str(zone).upper():
            return True
    return False


def _selector_feature(feat: dict) -> dict:
    props = dict(feat.get("properties") or {})
    event = str(props.get("event") or "Alert")
    props.setdefault("color", ALERT_COLORS.get(event, DEFAULT_COLOR))
    props.setdefault("headline", props.get("headline") or event)
    return {
        "type": "Feature",
        "geometry": feat.get("geometry"),
        "properties": props,
    }
