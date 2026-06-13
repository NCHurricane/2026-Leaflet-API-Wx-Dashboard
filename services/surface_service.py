"""Surface observation cache, serialization, and overlay helpers."""

from datetime import datetime, timezone
import json
import os
import threading
import time as _time

from fastapi import HTTPException

from app_core.paths import CACHE_ROOT
from surface import surface_utils

try:
    from config.surface_config import TEMPERATURE_GRADIENT_ANCHORS as _TEMP_ANCHORS
except Exception:
    _TEMP_ANCHORS = [
        (-60, "#00352C"),
        (-20, "#c4c4d4"),
        (0, "#570057"),
        (32, "#0000ff"),
        (50, "#c4c403"),
        (80, "#c20303"),
        (130, "#000000"),
    ]

_WIND_ANCHORS = [
    (0, "#b0d4f0"),
    (10, "#70b0e0"),
    (20, "#3090d0"),
    (30, "#f5dd72"),
    (45, "#ff9d2e"),
    (60, "#ff4f4f"),
]
_RH_ANCHORS = [
    (0, "#c8a000"),
    (20, "#f5dd72"),
    (40, "#69bb6d"),
    (60, "#0099cc"),
    (80, "#0055aa"),
    (100, "#003377"),
]
_PRESSURE_ANCHORS = [
    (990, "#5b1a8f"),
    (1000, "#2a6db3"),
    (1010, "#2ca58d"),
    (1020, "#f5dd72"),
    (1030, "#ff9d2e"),
    (1040, "#bf2c2c"),
]
_VISIBILITY_ANCHORS = [
    (0, "#7f1d1d"),
    (1, "#b45309"),
    (3, "#d97706"),
    (5, "#65a30d"),
    (7, "#16a34a"),
    (10, "#0ea5e9"),
]

SURFACE_PRODUCTS = {
    "station_plot": {"col": "air_temperature", "unit": "\u00b0F", "anchors": "temp"},
    "temperature": {"col": "air_temperature", "unit": "\u00b0F", "anchors": "temp"},
    "feels_like": {"col": "feels_like", "unit": "\u00b0F", "anchors": "temp"},
    "dew_point": {"col": "dew_point_temperature", "unit": "\u00b0F", "anchors": "temp"},
    "relative_humidity": {"col": "relative_humidity", "unit": "%", "anchors": "rh"},
    "wind_speed": {"col": "wind_speed", "unit": "kt", "anchors": "wind"},
    "wind_gust": {"col": "peak_wind", "unit": "kt", "anchors": "wind"},
    "altimeter": {"col": "altimeter", "unit": "inHg", "anchors": "pressure"},
    "mslp": {"col": "mean_sea_level_pressure", "unit": "hPa", "anchors": "pressure"},
    "visibility": {"col": "visibility", "unit": "mi", "anchors": "visibility"},
}

_SURFACE_CACHE_TTL_SECONDS = 300
_surface_refresh_lock = threading.Lock()
_surface_refresh_inflight = set()


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
    anchors_key = meta["anchors"]
    if anchors_key == "temp":
        anchors = _TEMP_ANCHORS
    elif anchors_key == "wind":
        anchors = _WIND_ANCHORS
    elif anchors_key == "pressure":
        anchors = _PRESSURE_ANCHORS
    elif anchors_key == "visibility":
        anchors = _VISIBILITY_ANCHORS
    else:
        anchors = _RH_ANCHORS

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


def _refresh_surface_cache_async(
    region_upper: str, product_lower: str, cache_file: str
) -> None:
    """Refresh stale surface cache in background."""
    cache_key = f"{region_upper}:{product_lower}"
    try:
        df = surface_utils.fetch_metar_data(region_upper)
        stations = build_surface_stations(df, product_lower)
        source_ts = _surface_source_timestamp_iso(df)
        result = {
            "stations": stations,
            "product": product_lower,
            "unit": SURFACE_PRODUCTS[product_lower]["unit"],
            "region": region_upper,
            "count": len(stations),
            "timestamp": source_ts,
            "timestamp_source": "station_valid",
        }
        try:
            with open(cache_file, "w", encoding="utf-8") as fh:
                json.dump(result, fh)
        except Exception:
            pass
    except Exception as exc:
        print(f"[WARN] Surface background refresh failed ({cache_key}): {exc}")
    finally:
        with _surface_refresh_lock:
            _surface_refresh_inflight.discard(cache_key)


def _kickoff_surface_refresh_if_needed(
    region_upper: str, product_lower: str, cache_file: str
) -> None:
    """Start at most one background refresh per region/product cache key."""
    cache_key = f"{region_upper}:{product_lower}"
    with _surface_refresh_lock:
        if cache_key in _surface_refresh_inflight:
            return
        _surface_refresh_inflight.add(cache_key)
    threading.Thread(
        target=_refresh_surface_cache_async,
        args=(region_upper, product_lower, cache_file),
        name=f"surface-refresh-{region_upper}-{product_lower}",
        daemon=True,
    ).start()


def get_surface_data(region: str = "NC", product: str = "temperature") -> dict:
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

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as fh:
                cached = json.load(fh)

            if (
                cached.get("timestamp_source") == "station_valid"
                and cached.get("timestamp") is not None
            ):
                age = _time.time() - os.path.getmtime(cache_file)
                if age >= _SURFACE_CACHE_TTL_SECONDS:
                    _kickoff_surface_refresh_if_needed(
                        region_upper, product_lower, cache_file
                    )
                return cached
        except Exception:
            pass

    try:
        df = surface_utils.fetch_metar_data(region_upper)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Surface data unavailable: {exc}")

    stations = build_surface_stations(df, product_lower)
    source_ts = _surface_source_timestamp_iso(df)
    result = {
        "stations": stations,
        "product": product_lower,
        "unit": SURFACE_PRODUCTS[product_lower]["unit"],
        "region": region_upper,
        "count": len(stations),
        "timestamp": source_ts,
        "timestamp_source": "station_valid",
    }

    try:
        with open(cache_file, "w", encoding="utf-8") as fh:
            json.dump(result, fh)
    except Exception:
        pass

    return result


def get_surface_gradient(region: str = "CONUS", product: str = "temperature") -> dict:
    """Return cached worker-generated surface gradient metadata."""
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

    if not os.path.exists(meta_path):
        raise HTTPException(
            status_code=404,
            detail=(
                f"No cached surface gradient for region={source_region}, "
                f"product={product_lower}. Worker may not have run yet."
            ),
        )

    try:
        with open(meta_path, "r", encoding="utf-8") as fh:
            meta = json.load(fh)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to read gradient meta: {exc}"
        )

    image_url = str(meta.get("image_url") or "")
    if not image_url:
        raise HTTPException(
            status_code=500, detail="Gradient metadata is missing image_url."
        )

    rel = image_url.lstrip("/")
    if rel.startswith("cache/"):
        rel = rel[len("cache/") :]
    image_disk = os.path.join(CACHE_ROOT, rel)
    if not os.path.exists(image_disk):
        raise HTTPException(
            status_code=404,
            detail="Cached gradient image is missing on disk. Worker refresh pending.",
        )

    return meta


def get_colormap_data(product: str = "temperature") -> dict:
    """Return colormap anchor points for a given surface product."""
    product_lower = product.lower().strip()
    if product_lower not in SURFACE_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown product '{product}'. Valid: {list(SURFACE_PRODUCTS.keys())}",
        )
    meta = SURFACE_PRODUCTS[product_lower]
    if meta["anchors"] == "temp":
        anchors = _TEMP_ANCHORS
    elif meta["anchors"] == "wind":
        anchors = _WIND_ANCHORS
    elif meta["anchors"] == "pressure":
        anchors = _PRESSURE_ANCHORS
    elif meta["anchors"] == "visibility":
        anchors = _VISIBILITY_ANCHORS
    else:
        anchors = _RH_ANCHORS
    return {
        "product": product_lower,
        "unit": meta["unit"],
        "anchors": [{"value": a[0], "color": a[1]} for a in anchors],
    }


def fetch_surface_archive_frames(region: str, frame_times: list, source: str = "iem"):
    return surface_utils.fetch_metar_data_archive_frames(
        region, frame_times, source=source
    )


def fetch_surface_archive_at_time(region: str, ts: datetime, source: str = "iem"):
    return surface_utils.fetch_metar_data_at_time(region, ts, source=source)
