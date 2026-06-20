"""WPC cache reads, cold-start worker fallback, and response shaping."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from fastapi import HTTPException

from app_core.paths import CACHE_ROOT
from config.wpc_config import WPC_PRODUCTS, get_product

_WPC_CACHE = os.path.join(CACHE_ROOT, "wpc")
_WPC_STATUS = os.path.join(_WPC_CACHE, ".status")
_WPC_STALE_SECONDS = 12 * 60 * 60


def _read_json_file(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _product_status(product: dict) -> dict:
    return _read_json_file(os.path.join(_WPC_STATUS, f"{product['id']}.json"))


def _cache_state(cache_file: str) -> tuple[float | None, bool]:
    if not os.path.exists(cache_file):
        return None, False
    age_seconds = max(0.0, time.time() - os.path.getmtime(cache_file))
    return age_seconds, age_seconds > _WPC_STALE_SECONDS


def _empty_collection(group: str, day: int, product: dict, status: dict) -> dict:
    source_status = status.get("status") or "unavailable"
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
        "empty_message": None,
        "unavailable": True,
        "source_available": False,
        "source_status": source_status,
        "source_error": status.get("error"),
        "stale": False,
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
) -> dict:
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
            "unavailable": False,
            "source_available": status.get("available", True),
            "source_status": status.get("status") or "unknown",
            "source_error": status.get("error"),
            "stale": stale,
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
        "unavailable": False,
        "source_available": status.get("available", True),
        "source_status": status.get("status") or "unknown",
        "source_error": status.get("error"),
        "stale": stale,
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

    if not os.path.exists(cache_file):
        try:
            from workers.wpc_worker import run_wpc_worker

            run_wpc_worker(product_ids={product["id"]})
        except Exception as exc:  # noqa: BLE001 - surface as 503 below
            raise HTTPException(
                status_code=503,
                detail=f"WPC cache not yet available: {exc}",
            )

    if not os.path.exists(cache_file):
        return _empty_collection(group_key, day, product, _product_status(product))

    try:
        with open(cache_file, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))

    cache_age_seconds, stale = _cache_state(cache_file)
    return _shape_collection(
        payload,
        group_key,
        day,
        product,
        _product_status(product),
        cache_age_seconds,
        stale,
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
            cache_age_seconds, stale = _cache_state(cache_file)
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
