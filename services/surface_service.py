"""Surface observation cache, serialization, and overlay helpers."""

from datetime import datetime, timezone
import json
import os
import threading
import time as _time

from fastapi import HTTPException

from app_core.atomic_io import atomic_write_json
from app_core.paths import CACHE_ROOT
from app_core.refresh_coordinator import Submission, get_refresh_coordinator
from config.surface_config import SURFACE_COLOR_ANCHORS
from surface import surface_utils

SURFACE_PRODUCTS = {
    "station_plot": {"col": "air_temperature", "unit": "\u00b0F"},
    "temperature": {"col": "air_temperature", "unit": "\u00b0F"},
    "feels_like": {"col": "feels_like", "unit": "\u00b0F"},
    "dew_point": {"col": "dew_point_temperature", "unit": "\u00b0F"},
    "relative_humidity": {"col": "relative_humidity", "unit": "%"},
    "wind_speed": {"col": "wind_speed", "unit": "kt"},
    "wind_gust": {"col": "peak_wind", "unit": "kt"},
    "altimeter": {"col": "altimeter", "unit": "inHg"},
    "mslp": {"col": "mean_sea_level_pressure", "unit": "hPa"},
    "visibility": {"col": "visibility", "unit": "mi"},
}

_SURFACE_CACHE_TTL_SECONDS = 300
_SURFACE_GRADIENT_TTL_SECONDS = 30 * 60
_SURFACE_SNAPSHOT_TTL_SECONDS = 60
_SURFACE_SNAPSHOT_LOCK = threading.Lock()
_SURFACE_SNAPSHOTS: dict[str, tuple[float, object]] = {}


def _surface_refresh_key(region_upper: str) -> tuple[str, ...]:
    return ("surface", "observations", region_upper)


def _surface_refresh_provider(region_upper: str) -> str:
    return "aviationweather" if region_upper in {"CONUS", "WORLD"} else "iem"


def _surface_gradient_key(
    region_upper: str,
    product_lower: str,
) -> tuple[str, ...]:
    return ("surface", "gradient", region_upper, product_lower)


def _get_cached_surface_snapshot(region_upper: str):
    with _SURFACE_SNAPSHOT_LOCK:
        cached = _SURFACE_SNAPSHOTS.get(region_upper)
        if (
            cached is not None
            and (_time.monotonic() - cached[0]) < _SURFACE_SNAPSHOT_TTL_SECONDS
        ):
            return cached[1]
    return None


def _get_surface_observation_snapshot(region_upper: str):
    """Fetch at most one observation dataframe per region inside one minute."""
    with _SURFACE_SNAPSHOT_LOCK:
        cached = _SURFACE_SNAPSHOTS.get(region_upper)
        now = _time.monotonic()
        if (
            cached is not None
            and (now - cached[0]) < _SURFACE_SNAPSHOT_TTL_SECONDS
        ):
            return cached[1]
        dataframe = surface_utils.fetch_metar_data(region_upper)
        if dataframe is None or bool(getattr(dataframe, "empty", False)):
            raise RuntimeError(
                f"No Surface observations available for {region_upper}"
            )
        _SURFACE_SNAPSHOTS[region_upper] = (_time.monotonic(), dataframe)
        return dataframe


def _interpolate_color(anchors: list, value: float) -> str:
    """Map a numeric value to a hex color via piecewise linear interpolation."""
    if not anchors:
        return "#aaaaaa"
    if value <= anchors[0][0]:
        return anchors[0][1]
    if value >= anchors[-1][0]:
        return anchors[-1][1]
    for i in range(len(anchors) - 1):
        v0, c0 = anchors[i]
        v1, c1 = anchors[i + 1]
        if v0 <= value <= v1:
            frac = (value - v0) / (v1 - v0)
            r0, g0, b0 = int(c0[1:3], 16), int(c0[3:5], 16), int(c0[5:7], 16)
            r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
            r = int(r0 + (r1 - r0) * frac)
            g = int(g0 + (g1 - g0) * frac)
            b = int(b0 + (b1 - b0) * frac)
            return f"#{r:02x}{g:02x}{b:02x}"
    return "#aaaaaa"


def _safe_float(row, col: str):
    import math

    val = row.get(col)
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else round(f, 1)
    except (TypeError, ValueError):
        return None


def build_surface_stations(df, product: str) -> list:
    """Serialize a surface DataFrame to a JSON-safe station list with per-station colors."""
    import math

    meta = SURFACE_PRODUCTS.get(product)
    if meta is None or df is None or df.empty:
        return []

    col = meta["col"]
    anchors = SURFACE_COLOR_ANCHORS[product]

    if col not in df.columns:
        return []

    stations = []
    for _, row in df.iterrows():
        raw_val = row.get(col)
        if raw_val is None or (isinstance(raw_val, float) and math.isnan(raw_val)):
            continue
        val = float(raw_val)
        color = _interpolate_color(anchors, val)
        station = {
            "id": str(row.get("station_id", "")),
            "name": str(row.get("name", "")),
            "network": str(row.get("network", "ASOS")),
            "lat": float(row.get("latitude", 0)),
            "lon": float(row.get("longitude", 0)),
            "value": round(val, 1),
            "color": color,
            "unit": meta["unit"],
            "temperature": _safe_float(row, "air_temperature"),
            "dew_point": _safe_float(row, "dew_point_temperature"),
            "feels_like": _safe_float(row, "feels_like"),
            "rh": _safe_float(row, "relative_humidity"),
            "wind_speed": _safe_float(row, "wind_speed"),
            "wind_dir": _safe_float(row, "wind_dir"),
            "wind_gust": _safe_float(row, "peak_wind"),
            "visibility": _safe_float(row, "visibility"),
        }
        stations.append(station)
    return stations


def _surface_source_timestamp_iso(df) -> str | None:
    """Return newest UTC observation timestamp from a surface dataframe."""
    if df is None or getattr(df, "empty", True) or "valid" not in df.columns:
        return None

    latest_dt: datetime | None = None
    try:
        valid_values = df["valid"].tolist()
    except Exception:
        return None

    for raw in valid_values:
        if raw is None:
            continue

        dt_val: datetime | None = None
        if isinstance(raw, datetime):
            dt_val = raw
        else:
            text = str(raw).strip()
            if not text or text.lower() in {"nat", "nan", "none"}:
                continue
            try:
                dt_val = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except Exception:
                dt_val = None

        if dt_val is None:
            continue

        if dt_val.tzinfo is None:
            dt_val = dt_val.replace(tzinfo=timezone.utc)
        else:
            dt_val = dt_val.astimezone(timezone.utc)

        if latest_dt is None or dt_val > latest_dt:
            latest_dt = dt_val

    return latest_dt.isoformat() if latest_dt else None


def _refresh_surface_region(
    region_upper: str,
    surface_cache_dir: str,
) -> dict:
    """Fetch one regional observation set and publish every product cache."""
    df = _get_surface_observation_snapshot(region_upper)
    source_ts = _surface_source_timestamp_iso(df)
    published_products = []
    for product, product_config in SURFACE_PRODUCTS.items():
        stations = build_surface_stations(df, product)
        result = {
            "stations": stations,
            "product": product,
            "unit": product_config["unit"],
            "color_anchors": SURFACE_COLOR_ANCHORS[product],
            "region": region_upper,
            "count": len(stations),
            "timestamp": source_ts,
            "timestamp_source": "station_valid",
        }
        cache_file = os.path.join(
            surface_cache_dir,
            f"{region_upper}_{product}.json",
        )
        atomic_write_json(cache_file, result)
        published_products.append(product)
    return {
        "source_timestamp": source_ts,
        "published_products": published_products,
    }


def _kickoff_surface_refresh_if_needed(
    region_upper: str,
    surface_cache_dir: str,
) -> Submission:
    """Start at most one background refresh for a regional observation set."""
    return get_refresh_coordinator().submit(
        key=_surface_refresh_key(region_upper),
        provider=_surface_refresh_provider(region_upper),
        function=lambda: _refresh_surface_region(
            region_upper,
            surface_cache_dir,
        ),
    )


def get_surface_data(
    region: str = "NC", product: str = "temperature", force_refresh: bool = False
) -> dict:
    """Return surface observations JSON with stale-while-revalidate caching."""
    region_upper = region.upper().strip()
    product_lower = product.lower().strip()
    if product_lower not in SURFACE_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown product '{product}'. Valid: {list(SURFACE_PRODUCTS.keys())}",
        )

    surface_cache_dir = os.path.join(CACHE_ROOT, "surface")
    os.makedirs(surface_cache_dir, exist_ok=True)
    cache_file = os.path.join(surface_cache_dir, f"{region_upper}_{product_lower}.json")
    get_refresh_coordinator().record_presence(
        key=_surface_refresh_key(region_upper),
        provider=_surface_refresh_provider(region_upper),
    )

    cached: dict | None = None
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)

            if (
                isinstance(loaded, dict)
                and loaded.get("timestamp_source") == "station_valid"
                and loaded.get("timestamp") is not None
            ):
                cached = loaded
                age = _time.time() - os.path.getmtime(cache_file)
                if not force_refresh and age < _SURFACE_CACHE_TTL_SECONDS:
                    return {
                        **cached,
                        "color_anchors": SURFACE_COLOR_ANCHORS[product_lower],
                        "cache_state": "fresh",
                        "refreshing": False,
                        "retry_after_seconds": None,
                    }
        except Exception:
            cached = None

    submission = _kickoff_surface_refresh_if_needed(
        region_upper,
        surface_cache_dir,
    )
    refreshing = submission.status in {"queued", "running"}
    if cached is not None:
        cache_state = (
            "backoff"
            if submission.status == "backoff"
            else "stale_refreshing" if refreshing else "stale"
        )
        return {
            **cached,
            "color_anchors": SURFACE_COLOR_ANCHORS[product_lower],
            "cache_state": cache_state,
            "refreshing": refreshing,
            "retry_after_seconds": submission.retry_after_seconds,
        }

    cache_state = (
        "backoff"
        if submission.status == "backoff"
        else "refreshing" if refreshing else "missing"
    )
    return {
        "stations": [],
        "product": product_lower,
        "unit": SURFACE_PRODUCTS[product_lower]["unit"],
        "color_anchors": SURFACE_COLOR_ANCHORS[product_lower],
        "region": region_upper,
        "count": 0,
        "timestamp": None,
        "timestamp_source": "station_valid",
        "cache_state": cache_state,
        "refreshing": refreshing,
        "retry_after_seconds": submission.retry_after_seconds,
        "capability": "available",
    }


def get_surface_gradient(region: str = "CONUS", product: str = "temperature") -> dict:
    """Serve the last complete gradient and target stale/missing work on demand."""
    region_upper = str(region or "CONUS").upper().strip()
    product_lower = str(product or "temperature").lower().strip()

    if product_lower not in SURFACE_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown product '{product}'. Valid: {list(SURFACE_PRODUCTS.keys())}",
        )
    if product_lower == "station_plot":
        raise HTTPException(
            status_code=400,
            detail="station_plot does not have a gradient overlay.",
        )

    source_region = "WORLD" if region_upper == "WORLD" else "CONUS"
    gradient_dir = os.path.join(
        CACHE_ROOT,
        "surface",
        "gradients",
        source_region,
    )
    meta_path = os.path.join(gradient_dir, f"{product_lower}.json")
    meta = _read_surface_gradient_meta(meta_path)
    if meta is not None:
        image_disk = _surface_gradient_image_path(meta)
        if image_disk is not None:
            oldest_mtime = min(
                os.path.getmtime(meta_path),
                os.path.getmtime(image_disk),
            )
            if (_time.time() - oldest_mtime) < _SURFACE_GRADIENT_TTL_SECONDS:
                return _surface_gradient_response(
                    meta,
                    source_region,
                    product_lower,
                    cache_state="fresh",
                    refreshing=False,
                )

    snapshot = _get_cached_surface_snapshot(source_region)
    if snapshot is None:
        surface_cache_dir = os.path.join(CACHE_ROOT, "surface")
        os.makedirs(surface_cache_dir, exist_ok=True)
        submission = _kickoff_surface_refresh_if_needed(
            source_region,
            surface_cache_dir,
        )
        return _surface_gradient_response_for_submission(
            meta,
            source_region,
            product_lower,
            submission,
            refresh_stage="observations",
        )

    submission = get_refresh_coordinator().submit(
        key=_surface_gradient_key(source_region, product_lower),
        provider="surface-gradient",
        function=lambda: _render_surface_gradient(
            snapshot,
            source_region,
            product_lower,
        ),
    )
    return _surface_gradient_response_for_submission(
        meta,
        source_region,
        product_lower,
        submission,
        refresh_stage="gradient",
    )


def _read_surface_gradient_meta(meta_path: str) -> dict | None:
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as fh:
            meta = json.load(fh)
    except Exception:
        return None
    if not isinstance(meta, dict) or _surface_gradient_image_path(meta) is None:
        return None
    return meta


def _surface_gradient_image_path(meta: dict) -> str | None:
    image_url = str(meta.get("image_url") or "")
    if not image_url:
        return None
    rel = image_url.lstrip("/")
    if rel.startswith("cache/"):
        rel = rel[len("cache/") :]
    image_disk = os.path.join(CACHE_ROOT, rel)
    return image_disk if os.path.exists(image_disk) else None


def _render_surface_gradient(
    snapshot,
    region_upper: str,
    product_lower: str,
) -> dict:
    from workers.surface_worker import render_surface_gradient

    return render_surface_gradient(
        snapshot,
        region=region_upper,
        product=product_lower,
        timestamp_iso=_surface_source_timestamp_iso(snapshot),
    )


def _surface_gradient_response(
    meta: dict | None,
    region_upper: str,
    product_lower: str,
    *,
    cache_state: str,
    refreshing: bool,
    retry_after_seconds: float | None = None,
    refresh_stage: str | None = None,
) -> dict:
    return {
        **(meta or {}),
        "region": region_upper,
        "product": product_lower,
        "cache_state": cache_state,
        "refreshing": refreshing,
        "retry_after_seconds": retry_after_seconds,
        "refresh_stage": refresh_stage,
        "capability": "available",
    }


def _surface_gradient_response_for_submission(
    meta: dict | None,
    region_upper: str,
    product_lower: str,
    submission: Submission,
    *,
    refresh_stage: str,
) -> dict:
    refreshing = submission.status in {"queued", "running"}
    if submission.status == "backoff":
        cache_state = "backoff"
    elif refreshing:
        cache_state = "stale_refreshing" if meta is not None else "refreshing"
    else:
        cache_state = "stale" if meta is not None else "missing"
    return _surface_gradient_response(
        meta,
        region_upper,
        product_lower,
        cache_state=cache_state,
        refreshing=refreshing,
        retry_after_seconds=submission.retry_after_seconds,
        refresh_stage=refresh_stage,
    )


def fetch_surface_archive_frames(region: str, frame_times: list, source: str = "iem"):
    return surface_utils.fetch_metar_data_archive_frames(
        region, frame_times, source=source
    )


def fetch_surface_archive_at_time(region: str, ts: datetime, source: str = "iem"):
    return surface_utils.fetch_metar_data_at_time(region, ts, source=source)
