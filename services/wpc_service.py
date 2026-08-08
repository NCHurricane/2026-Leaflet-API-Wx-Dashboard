"""WPC cache reads, cold-start worker fallback, and response shaping."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from fastapi import HTTPException

from app_core.http import parse_optional_utc_datetime
from app_core.paths import CACHE_ROOT
from app_core.refresh_coordinator import Submission, get_refresh_coordinator
from config.refresh_schedules import wpc_schedule_for
from config.wpc_config import WPC_PRODUCTS, get_product

_WPC_CACHE = os.path.join(CACHE_ROOT, "wpc")
_WPC_STATUS = os.path.join(_WPC_CACHE, ".status")
def _refresh_product(product_id: str) -> dict:
    from workers.wpc_worker import run_wpc_worker

    run_wpc_worker(product_ids={product_id})
    status = _product_status({"id": product_id})
    if status.get("status") == "error":
        raise RuntimeError("WPC targeted refresh failed")
    return {"source_timestamp": status.get("checked_at")}


def _start_product_refresh(product_id: str) -> Submission:
    return get_refresh_coordinator().submit(
        key=("wpc", "product", product_id),
        provider="wpc",
        function=lambda: _refresh_product(product_id),
    )


def _read_json_file(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _product_status(product: dict) -> dict:
    return _read_json_file(os.path.join(_WPC_STATUS, f"{product['id']}.json"))


def _cache_state(
    cache_file: str,
    product: dict,
    status: dict,
    payload: dict | None = None,
) -> tuple[float | None, bool]:
    if not os.path.exists(cache_file):
        return None, False
    age_seconds = max(0.0, time.time() - os.path.getmtime(cache_file))
    if product.get("group") == "mpd":
        return age_seconds, age_seconds >= 90.0
    payload = payload or _read_json_file(cache_file)
    last_checked_at = (
        parse_optional_utc_datetime(status.get("checked_at"))
        if status.get("status") != "error"
        else None
    )
    stale = wpc_schedule_for(product).refresh_due(
        now=datetime.now(timezone.utc),
        source_issued_at=parse_optional_utc_datetime(payload.get("updated")),
        last_checked_at=last_checked_at,
    )
    return age_seconds, stale


def _empty_collection(
    group: str,
    day: int,
    product: dict,
    status: dict,
    refresh_submission: Submission | None = None,
) -> dict:
    refresh_status = refresh_submission.status if refresh_submission else None
    refreshing = refresh_status in {"queued", "running"}
    source_status = status.get("status") or (
        "warming" if refreshing else "unavailable"
    )
    return {
        "type": "FeatureCollection",
        "features": [],
        "count": 0,
        "_source": "WPC",
        "_updated": None,
        "group": group,
        "day": day,
        "product": product["id"],
        "product_label": product["label"],
        "empty_message": (
            f"{product['label']} is warming…" if refreshing else None
        ),
        "issued_text": None,
        "valid_text": None,
        "no_significant_weather": False,
        "unavailable": not refreshing,
        "source_available": refreshing,
        "source_status": source_status,
        "source_error": status.get("error"),
        "stale": False,
        "cache_state": (
            "refreshing"
            if refreshing
            else refresh_status
            if refresh_status
            else "unavailable"
        ),
        "refreshing": refreshing,
        "retry_after_seconds": (
            refresh_submission.retry_after_seconds if refresh_submission else None
        ),
        "cache_age_seconds": None,
    }


def _shape_collection(
    payload: dict,
    group: str,
    day: int,
    product: dict,
    status: dict,
    cache_age_seconds: float | None,
    stale: bool,
    refresh_submission: Submission | None = None,
) -> dict:
    refresh_status = refresh_submission.status if refresh_submission else None
    refreshing = refresh_status in {"queued", "running"}
    if refresh_status == "backoff":
        cache_state = "backoff"
    elif stale and refreshing:
        cache_state = "stale_refreshing"
    elif stale:
        cache_state = "stale"
    else:
        cache_state = "fresh"
    retry_after_seconds = (
        refresh_submission.retry_after_seconds if refresh_submission else None
    )
    if payload.get("image_url"):
        return {
            "type": "WpcImageOverlay",
            "count": 1,
            "_source": "WPC",
            "_updated": payload.get("updated"),
            "_source_url": payload.get("source_url"),
            "group": group,
            "day": day,
            "product": product["id"],
            "product_label": product["label"],
            "image_url": payload.get("image_url"),
            "bounds": payload.get("bounds"),
            "forecast_hour": payload.get("forecast_hour"),
            "issued_text": payload.get("issued_text"),
            "valid_text": payload.get("valid_text"),
            "no_significant_weather": bool(payload.get("no_significant_weather")),
            "unavailable": False,
            "source_available": status.get("available", True),
            "source_status": status.get("status") or "unknown",
            "source_error": status.get("error"),
            "stale": stale,
            "cache_state": cache_state,
            "refreshing": refreshing,
            "retry_after_seconds": retry_after_seconds,
            "cache_age_seconds": cache_age_seconds,
        }
    geojson = payload.get("geojson") if isinstance(payload, dict) else None
    if not isinstance(geojson, dict):
        geojson = {"type": "FeatureCollection", "features": []}
    features = geojson.get("features") or []
    if group == "mpd":
        now = datetime.now(timezone.utc)
        active_features = []
        for feature in features:
            valid_end = feature.get("properties", {}).get("valid_end")
            try:
                expires = datetime.fromisoformat(valid_end) if valid_end else None
            except (TypeError, ValueError):
                expires = None
            if expires is None or expires > now:
                active_features.append(feature)
        features = active_features
    return {
        "type": "FeatureCollection",
        "features": features,
        "count": len(features),
        "_source": "WPC",
        "_updated": payload.get("updated"),
        "_source_url": payload.get("source_url"),
        "group": group,
        "day": day,
        "product": product["id"],
        "product_label": product["label"],
        "empty_message": payload.get("empty_message") if not features else None,
        "issued_text": payload.get("issued_text"),
        "valid_text": payload.get("valid_text"),
        "no_significant_weather": bool(payload.get("no_significant_weather")),
        "unavailable": False,
        "source_available": status.get("available", True),
        "source_status": status.get("status") or "unknown",
        "source_error": status.get("error"),
        "stale": stale,
        "cache_state": cache_state,
        "refreshing": refreshing,
        "retry_after_seconds": retry_after_seconds,
        "cache_age_seconds": cache_age_seconds,
    }


def get_wpc_layer(
    group: str = "ero",
    day: int = 1,
    product_id: str | None = None,
) -> dict:
    """Return a WPC product GeoJSON FeatureCollection from the worker cache."""
    group_key = (group or "ero").strip().lower()
    product = get_product(group_key, day, product_id)
    if product is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown WPC product: group={group_key}, day={day}, "
                f"product={product_id or 'default'}"
            ),
        )

    cache_file = os.path.join(_WPC_CACHE, product["cache_path"].replace("/", os.sep))
    get_refresh_coordinator().record_presence(
        key=("wpc", "product", product["id"]),
        provider="wpc",
    )

    refresh_submission = None
    if not os.path.exists(cache_file):
        refresh_submission = _start_product_refresh(product["id"])

    if not os.path.exists(cache_file):
        return _empty_collection(
            group_key,
            day,
            product,
            _product_status(product),
            refresh_submission,
        )

    try:
        with open(cache_file, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))

    status = _product_status(product)
    cache_age_seconds, stale = _cache_state(
        cache_file,
        product,
        status,
        payload,
    )
    if stale and refresh_submission is None:
        refresh_submission = _start_product_refresh(product["id"])
    return _shape_collection(
        payload,
        group_key,
        day,
        product,
        status,
        cache_age_seconds,
        stale,
        refresh_submission,
    )


def get_wpc_catalog() -> dict:
    """Return available WPC groups/days for frontend control population."""
    groups = []
    for group_key, products in WPC_PRODUCTS.items():
        product_entries = []
        for product in products:
            cache_file = os.path.join(
                _WPC_CACHE, product["cache_path"].replace("/", os.sep)
            )
            status = _product_status(product)
            cache_age_seconds, stale = _cache_state(
                cache_file,
                product,
                status,
            )
            cache_exists = os.path.exists(cache_file)
            product_entries.append(
                {
                    "id": product["id"],
                    "label": product["label"],
                    "days": list(product.get("days", (product.get("day"),))),
                    "seasonal": product.get("seasonal", False),
                    "available": cache_exists,
                    "source_available": status.get("available"),
                    "source_status": status.get("status") or "unknown",
                    "stale": stale,
                    "cache_age_seconds": cache_age_seconds,
                }
            )
        groups.append({"group": group_key, "products": product_entries})
    return {"groups": groups}
