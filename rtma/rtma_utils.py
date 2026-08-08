from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import cfgrib
import numpy as np
from app_core.atomic_io import atomic_output_path, atomic_write_json
from app_core.grib_decode import serialized_grib_decode
from app_core.upstream_ledger import requests
from config.geo_config import STATE_BOUNDS
from config.surface_config import TEMPERATURE_GRADIENT_ANCHORS
from surface.surface_utils import (
    calc_relative_humidity,
)
import warnings

warnings.filterwarnings("ignore", category=FutureWarning, module="cfgrib")


# NODD S3 public bucket — same path structure as NOMADS, no rate limiting,
# proper 404/403 for missing objects (no HTML error pages).
NODD_RTMA_ROOT = "https://noaa-rtma-pds.s3.amazonaws.com"
REQUEST_TIMEOUT = 30
_RTMA_CITY_CACHE_SCHEMA = 2
_GRIB_DOWNLOAD_LOCKS: dict[str, threading.Lock] = {}
_GRIB_DOWNLOAD_LOCKS_GUARD = threading.Lock()
_DERIVED_CACHE_LOCKS: dict[str, threading.Lock] = {}
_DERIVED_CACHE_LOCKS_GUARD = threading.Lock()

REGION_PREFIXES = {
    "CONUS": "rtma2p5",
    "AK": "akrtma",
    "HI": "hirtma",
    "PR": "prrtma",
}


def _fahrenheit(values: np.ndarray) -> np.ndarray:
    return (values - 273.15) * 9.0 / 5.0 + 32.0


def _hectopascal(values: np.ndarray) -> np.ndarray:
    return values / 100.0


def _mph(values: np.ndarray) -> np.ndarray:
    return values * 2.23694


def _miles(values: np.ndarray) -> np.ndarray:
    return values / 1609.344


_TEMP_LEGEND_ANCHORS = [
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
    (90, "#b91c1c"),
]

_VISIBILITY_ANCHORS = [
    (0, "#7f1d1d"),
    (1, "#b45309"),
    (3, "#d97706"),
    (5, "#65a30d"),
    (7, "#16a34a"),
    (10, "#0ea5e9"),
]

_SURFACE_PRESSURE_ANCHORS = [
    (960, "#5b1a8f"),
    (980, "#2a6db3"),
    (1000, "#2ca58d"),
    (1015, "#f5dd72"),
    (1030, "#ff9d2e"),
    (1045, "#bf2c2c"),
]

_TOTAL_CLOUD_COVER_ANCHORS = [
    (0, "#f8fafc"),
    (20, "#dbeafe"),
    (40, "#93c5fd"),
    (60, "#64748b"),
    (80, "#475569"),
    (100, "#1e293b"),
]

_TEMP_CHANGE_24H_ANCHORS = [
    (-40, "#4c1d95"),
    (-30, "#312e81"),
    (-20, "#1d4ed8"),
    (-10, "#0ea5e9"),
    (0, "#f8fafc"),
    (10, "#f59e0b"),
    (20, "#ef4444"),
    (30, "#b91c1c"),
    (40, "#7f1d1d"),
]


def _format_legend_value(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def _format_display_value(product: str, value: float) -> float | int:
    """Format point values for UI display by product.

    Temperature is shown as whole-degree values; all other RTMA products keep
    one decimal place.
    """
    if product in {"temperature", "apparent_temperature"}:
        if value >= 0:
            return int(np.floor(value + 0.5))
        return int(np.ceil(value - 0.5))
    return round(value, 1)


def _build_anchor_colormap(name: str, anchors: list[tuple[float, str]]):
    from matplotlib.colors import LinearSegmentedColormap

    min_value = float(anchors[0][0])
    max_value = float(anchors[-1][0])
    span = max(max_value - min_value, 1.0)
    return LinearSegmentedColormap.from_list(
        name,
        [((float(value) - min_value) / span, color) for value, color in anchors],
    )


def _resolve_render_colormap(config: dict):
    import matplotlib

    anchors = config.get("color_anchors")
    if anchors:
        return _build_anchor_colormap(config["cmap"], anchors)
    return matplotlib.colormaps[config["cmap"]]


def _build_legend_anchors(config: dict) -> list[dict]:
    anchors = config.get("legend_anchors") or config.get("color_anchors")
    if not anchors:
        return []
    return [
        {
            "value": float(value),
            "label": _format_legend_value(float(value)),
            "color": color,
        }
        for value, color in anchors
    ]


PRODUCTS = {
    "temperature": {
        "label": "Temperature",
        "kind": "analysis",
        "var": "t2m",
        "units": "F",
        "vmin": -60,
        "vmax": 130,
        "cmap": "wx_temperature",
        "color_anchors": TEMPERATURE_GRADIENT_ANCHORS,
        "legend_anchors": _TEMP_LEGEND_ANCHORS,
        "convert": _fahrenheit,
    },
    "temperature_change_24h": {
        "label": "24-Hour Temperature Change",
        "kind": "analysis",
        "var": "t2m",
        "units": "F",
        "vmin": -40,
        "vmax": 40,
        "cmap": "wx_temperature_change_24h",
        "color_anchors": _TEMP_CHANGE_24H_ANCHORS,
        "convert": None,
    },
    "dew_point": {
        "label": "Dew Point",
        "kind": "analysis",
        "var": "d2m",
        "units": "F",
        "vmin": -60,
        "vmax": 130,
        "cmap": "wx_dew_point",
        "color_anchors": TEMPERATURE_GRADIENT_ANCHORS,
        "legend_anchors": _TEMP_LEGEND_ANCHORS,
        "convert": _fahrenheit,
    },
    "surface_pressure": {
        "label": "Surface Pressure",
        "kind": "analysis",
        "var": "sp",
        "units": "hPa",
        "vmin": 960,
        "vmax": 1045,
        "cmap": "wx_surface_pressure",
        "color_anchors": _SURFACE_PRESSURE_ANCHORS,
        "convert": _hectopascal,
    },
    "wind_speed": {
        "label": "Wind Speed",
        "kind": "analysis",
        "var": "si10",
        "units": "mph",
        "vmin": 0,
        "vmax": 80,
        "cmap": "wx_wind_speed",
        "color_anchors": _WIND_ANCHORS,
        "convert": _mph,
    },
    "wind_gust": {
        "label": "Wind Gust",
        "kind": "analysis",
        "var": "i10fg",
        "units": "mph",
        "vmin": 0,
        "vmax": 90,
        "cmap": "wx_wind_gust",
        "color_anchors": _WIND_ANCHORS,
        "convert": _mph,
    },
    "wind_direction": {
        "label": "Wind Direction",
        "kind": "analysis",
        "var": "wdir10",
        "units": "deg",
        "vmin": 0,
        "vmax": 360,
        "cmap": "twilight",
        "convert": None,
    },
    "visibility": {
        "label": "Visibility",
        "kind": "analysis",
        "var": "vis",
        "units": "mi",
        "vmin": 0,
        "vmax": 10,
        "cmap": "wx_visibility",
        "color_anchors": _VISIBILITY_ANCHORS,
        "convert": _miles,
    },
    "total_cloud_cover": {
        "label": "Total Cloud Cover",
        "kind": "analysis",
        "var": "tcc",
        "units": "%",
        "vmin": 0,
        "vmax": 100,
        "cmap": "wx_total_cloud_cover",
        "color_anchors": _TOTAL_CLOUD_COVER_ANCHORS,
        "convert": None,
    },
    "apparent_temperature": {
        "label": "Feels Like (Wind Chill / Heat Index)",
        "kind": "derived",
        "vars": ["t2m", "d2m", "si10"],
        "units": "F",
        "vmin": -60,
        "vmax": 130,
        "cmap": "wx_temperature",
        "color_anchors": TEMPERATURE_GRADIENT_ANCHORS,
        "legend_anchors": _TEMP_LEGEND_ANCHORS,
        "convert": None,
    },
}


@dataclass(frozen=True)
class RtmaSource:
    url: str
    data_key: str
    valid_time: datetime


def get_product_config(product: str) -> dict:
    if product not in PRODUCTS:
        raise ValueError(f"Unsupported RTMA product '{product}'.")
    return PRODUCTS[product]


def _head_exists(url: str) -> bool:
    """Return True only if the URL resolves to an existing object.

    AWS S3 returns a proper 403/404 for missing objects (no HTML error page
    false-positives like NOMADS), so a plain HEAD request is sufficient and
    avoids downloading any file content.
    """
    try:
        response = requests.head(url, allow_redirects=True, timeout=REQUEST_TIMEOUT)
        return response.ok
    except requests.RequestException:
        return False


def _looks_like_grib(path: str) -> bool:
    try:
        if not os.path.exists(path) or os.path.getsize(path) < 16:
            return False
        with open(path, "rb") as handle:
            return handle.read(4) == b"GRIB"
    except OSError:
        return False


def _load_city_points(cities_path: str) -> list[dict]:
    with open(cities_path, "r", encoding="utf-8") as handle:
        rows = json.load(handle)
    out: list[dict] = []
    for row in rows:
        try:
            lat = float(row.get("latitude"))
            lon = float(row.get("longitude"))
        except (TypeError, ValueError):
            continue
        if not np.isfinite(lat) or not np.isfinite(lon):
            continue
        out.append(
            {
                "city": row.get("city", ""),
                "state": row.get("state", ""),
                "rank": row.get("rank"),
                "lat": lat,
                "lon": lon,
            }
        )
    return out


def _filter_city_points_for_region(cities: list[dict], region: str) -> list[dict]:
    bounds = STATE_BOUNDS.get(region.upper())
    if not bounds:
        return cities
    west, east, south, north = bounds
    return [
        city
        for city in cities
        if south <= city["lat"] <= north and west <= city["lon"] <= east
    ]


def _cities_cache_signature(cities_path: str) -> tuple[str, int]:
    return os.path.basename(cities_path), os.path.getsize(cities_path)


def _nearest_index_1d(grid: np.ndarray, values: np.ndarray) -> np.ndarray:
    arr = np.asarray(grid, dtype=float)
    vals = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError("Grid for nearest index must be 1D")
    if arr.size == 0:
        return np.zeros(vals.shape, dtype=int)

    descending = arr[0] > arr[-1]
    if descending:
        arr_use = arr[::-1]
    else:
        arr_use = arr

    pos = np.searchsorted(arr_use, vals)
    pos = np.clip(pos, 1, arr_use.size - 1)
    left = arr_use[pos - 1]
    right = arr_use[pos]
    pick_right = np.abs(right - vals) < np.abs(vals - left)
    idx_use = pos - 1 + pick_right.astype(int)

    if descending:
        return (arr_use.size - 1 - idx_use).astype(int)
    return idx_use.astype(int)


def _sample_city_values(
    data: np.ndarray,
    latitude: np.ndarray,
    longitude: np.ndarray,
    cities: list[dict],
) -> list[dict]:
    if not cities:
        return []

    city_lats = np.asarray([c["lat"] for c in cities], dtype=float)
    city_lons = np.asarray([c["lon"] for c in cities], dtype=float)

    lat_grid = np.asarray(latitude, dtype=float)
    lon_grid = np.asarray(longitude, dtype=float)
    lon_grid = np.where(lon_grid > 180.0, lon_grid - 360.0, lon_grid)

    flat_lat = lat_grid.reshape(-1)
    flat_lon = lon_grid.reshape(-1)
    flat_data = np.asarray(data).reshape(-1)

    # Prefer vectorized nearest-neighbor on rectilinear grids.
    if lat_grid.ndim == 1 and lon_grid.ndim == 1:
        lat_idx = _nearest_index_1d(lat_grid, city_lats)
        lon_idx = _nearest_index_1d(lon_grid, city_lons)
        vals = data[lat_idx, lon_idx]
    else:
        # For projected grids (e.g. Lambert Conformal), latitude/longitude
        # are NOT separable — using edge vectors produces a systematic northward
        # displacement that causes a cold bias.  Use a true 2-D nearest-neighbor
        # via a KDTree so each city maps to the closest grid point in lat/lon space.
        try:
            from scipy.spatial import KDTree  # noqa: PLC0415

            tree = KDTree(np.column_stack([flat_lat, flat_lon]))
            _, indices = tree.query(np.column_stack([city_lats, city_lons]))
            vals = flat_data[indices]
        except Exception:
            # Last-resort scalar fallback; slow but always correct.
            vals = np.array(
                [
                    flat_data[
                        int(np.argmin((flat_lat - clat) ** 2 + (flat_lon - clon) ** 2))
                    ]
                    for clat, clon in zip(city_lats, city_lons)
                ]
            )

    out: list[dict] = []
    for city, raw in zip(cities, vals):
        if np.ma.is_masked(raw):
            continue
        val = float(raw)
        if not np.isfinite(val):
            continue
        out.append(
            {
                "city": city["city"],
                "state": city["state"],
                "rank": city["rank"],
                "lat": city["lat"],
                "lon": city["lon"],
                "value": round(val, 1),
            }
        )
    return out


def _floor_to_interval(now: datetime, minutes: int) -> datetime:
    minute = (now.minute // minutes) * minutes
    return now.replace(minute=minute, second=0, microsecond=0)


def _iter_hourly_cycles(now: datetime, hours_back: int):
    base = now.replace(minute=0, second=0, microsecond=0)
    for offset in range(hours_back + 1):
        yield base - timedelta(hours=offset)


def _iter_rapid_cycles(now: datetime, intervals_back: int):
    base = _floor_to_interval(now, 15)
    for offset in range(intervals_back + 1):
        yield base - timedelta(minutes=15 * offset)


def _file_suffix_variants(
    base_suffix: str,
    region: str,
    conus_variants: list[str] | None = None,
) -> list[str]:
    if region == "CONUS":
        return conus_variants or [f"{base_suffix}.grb2_wexp", f"{base_suffix}.grb2"]
    variants = [f"{base_suffix}_3p0.grb2", f"{base_suffix}.grb2"]
    deduped: list[str] = []
    for variant in variants:
        if variant not in deduped:
            deduped.append(variant)
    return deduped


def _candidate_urls(
    region: str, stream: str, product: str, now: datetime
) -> list[RtmaSource]:
    cfg = get_product_config(product)
    kind = cfg["kind"]
    region_key = region.upper()
    if region_key not in REGION_PREFIXES:
        raise ValueError(f"Unsupported RTMA region '{region}'.")
    if stream not in {"rtma_hourly", "rtma_rapid_update"}:
        raise ValueError(f"Unsupported RTMA stream '{stream}'.")
    if stream == "rtma_rapid_update" and region_key != "CONUS":
        raise ValueError("RTMA rapid-update is only available for CONUS.")

    prefix = REGION_PREFIXES[region_key]
    base_root = NODD_RTMA_ROOT
    candidates: list[RtmaSource] = []

    if kind == "derived":
        # For derived products, get candidates from the first underlying variable
        # Derived fields use multiple variables from the same RTMA GRIB file.
        # All variables share the same GRIB file
        first_var = cfg.get("vars", [])[0]
        for analysis_product in PRODUCTS:
            if PRODUCTS[analysis_product].get("var") == first_var:
                return _candidate_urls(region, stream, analysis_product, now)
        raise ValueError(
            f"Unable to find analysis product for derived product '{product}'."
        )

    if kind == "analysis":
        if stream == "rtma_rapid_update":
            suffix = "2dvaranl_ndfd"
            for cycle in _iter_rapid_cycles(now, 24):
                directory = f"rtma2p5_ru.{cycle:%Y%m%d}"
                stamp = f"t{cycle:%H%M}z"
                file_name = f"rtma2p5_ru.{stamp}.{suffix}.grb2"
                candidates.append(
                    RtmaSource(
                        url=f"{base_root}/{directory}/{file_name}",
                        data_key=f"{directory}_{file_name}",
                        valid_time=cycle,
                    )
                )
            return candidates

        suffix = "2dvaranl_ndfd"
        regional_suffixes = _file_suffix_variants(
            suffix,
            region_key,
            [f"{suffix}.grb2_wexp", f"{suffix}.grb2"],
        )
        for cycle in _iter_hourly_cycles(now, 72):
            directory = f"{prefix}.{cycle:%Y%m%d}"
            stamp = f"t{cycle:%H}z"
            for suffix_variant in regional_suffixes:
                file_name = f"{prefix}.{stamp}.{suffix_variant}"
                candidates.append(
                    RtmaSource(
                        url=f"{base_root}/{directory}/{file_name}",
                        data_key=f"{directory}_{file_name}",
                        valid_time=cycle,
                    )
                )
        return candidates


def resolve_rtma_source(
    region: str, stream: str, product: str, now: datetime | None = None
) -> RtmaSource:
    for candidate in iter_rtma_sources(region, stream, product, now):
        return candidate
    raise FileNotFoundError(
        f"No source file found for region={region}, stream={stream}, product={product}."
    )


def iter_rtma_sources(
    region: str, stream: str, product: str, now: datetime | None = None
):
    base_now = now or datetime.now(timezone.utc)
    for candidate in _candidate_urls(
        region, stream, product, base_now.astimezone(timezone.utc)
    ):
        if _head_exists(candidate.url):
            yield candidate


def iter_rtma_sources_within_hours(
    region: str,
    stream: str,
    product: str,
    hours_back: int,
    now: datetime | None = None,
):
    """Yield all available sources within a lookback window (newest to oldest)."""
    base_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = base_now - timedelta(hours=max(0, int(hours_back)))
    for candidate in _candidate_urls(region, stream, product, base_now):
        if candidate.valid_time < cutoff:
            break
        if _head_exists(candidate.url):
            yield candidate


def resolve_rtma_source_by_data_key(
    region: str,
    stream: str,
    product: str,
    data_key: str,
    now: datetime | None = None,
    hours_back: int = 72,
) -> RtmaSource:
    """Resolve a specific frame by data key inside a bounded lookback window."""
    if not data_key:
        raise ValueError("RTMA data_key is required.")

    # Frontend overlay APIs use canonical frame keys (YYYY_MM_DD_HH_MM_SS)
    # as source_data_key. Support both full GRIB data_key and frame-key inputs.
    frame_dt: datetime | None = None
    try:
        frame_dt = datetime.strptime(data_key, "%Y_%m_%d_%H_%M_%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        frame_dt = None

    for candidate in iter_rtma_sources_within_hours(
        region, stream, product, hours_back=hours_back, now=now
    ):
        if candidate.data_key == data_key:
            return candidate
        if frame_dt is not None and candidate.valid_time == frame_dt:
            return candidate
    raise FileNotFoundError(
        f"No RTMA source found for data_key={data_key}, region={region}, "
        f"stream={stream}, product={product}."
    )


def _sanitize_cache_token(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)


def _grib_download_lock(local_path: str) -> threading.Lock:
    key = os.path.abspath(local_path)
    with _GRIB_DOWNLOAD_LOCKS_GUARD:
        lock = _GRIB_DOWNLOAD_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _GRIB_DOWNLOAD_LOCKS[key] = lock
        return lock


def _derived_cache_lock(output_path: str) -> threading.Lock:
    key = os.path.abspath(output_path)
    with _DERIVED_CACHE_LOCKS_GUARD:
        lock = _DERIVED_CACHE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _DERIVED_CACHE_LOCKS[key] = lock
        return lock


def ensure_rtma_grib(
    cache_root: str,
    source: RtmaSource,
    force_refresh: bool = False,
) -> str:
    cache_dir = os.path.join(cache_root, "rtma", "grib")
    os.makedirs(cache_dir, exist_ok=True)
    digest = hashlib.md5(source.url.encode()).hexdigest()[:16]
    file_name = os.path.basename(source.url)
    if force_refresh:
        unique = int(time.time() * 1000)
        local_path = os.path.join(cache_dir, f"{digest}_{unique}_{file_name}")
    else:
        local_path = os.path.join(cache_dir, f"{digest}_{file_name}")
    with _grib_download_lock(local_path):
        # Another request may have completed this exact source while this
        # caller waited for the per-file acquisition lock.
        if (
            not force_refresh
            and os.path.exists(local_path)
            and os.path.getsize(local_path) > 0
            and _looks_like_grib(local_path)
        ):
            return local_path

        with atomic_output_path(local_path, suffix=".part") as temporary:
            with requests.get(source.url, timeout=120, stream=True) as response:
                response.raise_for_status()
                with temporary.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            handle.write(chunk)
            if not _looks_like_grib(str(temporary)):
                raise ValueError(
                    "Downloaded payload is not a valid GRIB file: "
                    f"{os.path.basename(local_path)} from {source.url}"
                )
        if not _looks_like_grib(local_path):
            try:
                os.remove(local_path)
            except OSError:
                pass
            raise ValueError(
                "Downloaded payload is not a valid GRIB file: "
                f"{os.path.basename(local_path)} from {source.url}"
            )
        return local_path


@lru_cache(maxsize=8)
def _get_grib_datasets_cached(grib_path: str):
    """Cache parsed GRIB datasets by path to avoid repeated cfgrib.open_datasets() calls.

    Keeps up to 8 GRIB files parsed in memory to speed up extraction of multiple
    variables from the same file within a worker run.
    """
    return cfgrib.open_datasets(grib_path, backend_kwargs={"indexpath": ""})


def _extract_dataset(grib_path: str, var_name: str):
    with serialized_grib_decode():
        datasets = _get_grib_datasets_cached(grib_path)
        for dataset in datasets:
            if var_name in dataset.data_vars:
                data_array = dataset[var_name].squeeze(drop=True)
                latitude = np.asarray(dataset["latitude"].values, dtype=float)
                longitude = np.asarray(dataset["longitude"].values, dtype=float)
                data_values = np.asarray(data_array.values, dtype=float)
                if (
                    data_values.ndim == 1
                    and latitude.ndim == 1
                    and longitude.ndim == 1
                    and data_values.size == latitude.size == longitude.size
                ):
                    unique_lat = np.unique(np.round(latitude, 6))
                    unique_lon = np.unique(np.round(longitude, 6))
                    if unique_lat.size * unique_lon.size == data_values.size:
                        rows = unique_lat.size
                        cols = unique_lon.size
                        data_values = data_values.reshape(rows, cols)
                        latitude = latitude.reshape(rows, cols)
                        longitude = longitude.reshape(rows, cols)
                valid_time = dataset.coords.get("valid_time")
                data_time = None
                if valid_time is not None:
                    try:
                        data_time = np.asarray(valid_time.values).reshape(-1)[0]
                    except Exception:
                        data_time = None
                return data_values, latitude, longitude, data_time
    raise ValueError(
        f"Variable '{var_name}' was not found in '{os.path.basename(grib_path)}'."
    )


def _crop_grid(
    data: np.ndarray,
    latitude: np.ndarray,
    longitude: np.ndarray,
    crop_extent: list[float],
):
    west, east, south, north = crop_extent
    lon = np.asarray(longitude, dtype=float)
    lat = np.asarray(latitude, dtype=float)
    lon = np.where(lon > 180.0, lon - 360.0, lon)
    if lat.ndim == 1 and lon.ndim == 1:
        row_idx = np.where((lat >= south) & (lat <= north))[0]
        col_idx = np.where((lon >= west) & (lon <= east))[0]
        if not len(row_idx) or not len(col_idx):
            return data, lat, lon
        row_slice = slice(int(row_idx.min()), int(row_idx.max()) + 1)
        col_slice = slice(int(col_idx.min()), int(col_idx.max()) + 1)
        return data[row_slice, col_slice], lat[row_slice], lon[col_slice]
    mask = (lat >= south) & (lat <= north) & (lon >= west) & (lon <= east)
    if not np.any(mask):
        return data, lat, lon
    row_idx, col_idx = np.where(mask)
    row_slice = slice(int(row_idx.min()), int(row_idx.max()) + 1)
    col_slice = slice(int(col_idx.min()), int(col_idx.max()) + 1)
    data_crop = np.ma.array(data[row_slice, col_slice], copy=True)
    lat_crop = lat[row_slice, col_slice]
    lon_crop = lon[row_slice, col_slice]
    # Null out cells outside the actual geographic crop
    oob = (
        (lat_crop < south) | (lat_crop > north) | (lon_crop < west) | (lon_crop > east)
    )
    data_crop = np.ma.masked_where(oob, data_crop)
    return data_crop, lat_crop, lon_crop


def _serialize_timestamp(value) -> str | None:
    if value is None:
        return None
    try:
        dt = np.datetime64(value, "ns").astype("datetime64[ms]").astype(object)
    except Exception:
        dt = value
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return None


def _resolve_24h_prior_source(
    region: str,
    stream: str,
    source: RtmaSource,
) -> RtmaSource:
    if stream != "rtma_hourly":
        raise ValueError(
            "24-hour temperature change is only available for the rtma_hourly stream."
        )

    target_time = source.valid_time - timedelta(hours=24)
    nearest: RtmaSource | None = None
    nearest_delta: timedelta | None = None

    for candidate in iter_rtma_sources_within_hours(
        region,
        stream,
        "temperature",
        hours_back=30,
        now=source.valid_time,
    ):
        if candidate.valid_time >= source.valid_time:
            continue
        delta = abs(candidate.valid_time - target_time)
        if nearest_delta is None or delta < nearest_delta:
            nearest = candidate
            nearest_delta = delta

    if nearest is None or nearest_delta is None or nearest_delta > timedelta(hours=2):
        raise FileNotFoundError(
            "Unable to locate a suitable RTMA hourly frame near now-24h for "
            f"{source.valid_time.isoformat()}."
        )

    return nearest


def _calculate_apparent_temperature_values(
    temp_f: np.ndarray,
    dew_f: np.ndarray,
    wind_ms: np.ndarray,
) -> np.ma.MaskedArray:
    """Return wind chill, heat index, or air temperature per grid cell."""
    temperature = np.asarray(temp_f, dtype=float)
    dew_point = np.asarray(dew_f, dtype=float)
    wind_mph = np.asarray(wind_ms, dtype=float) * 2.2369362920544
    relative_humidity = calc_relative_humidity(temperature, dew_point)

    apparent = temperature.copy()

    wind_chill = (
        35.74
        + (0.6215 * temperature)
        - (35.75 * np.power(wind_mph, 0.16))
        + (0.4275 * temperature * np.power(wind_mph, 0.16))
    )
    wind_chill_mask = (temperature <= 50.0) & (wind_mph >= 3.0)
    apparent = np.where(wind_chill_mask, wind_chill, apparent)

    simple_heat_index = (
        0.5
        * (
            temperature
            + 61.0
            + ((temperature - 68.0) * 1.2)
            + (relative_humidity * 0.094)
        )
    )
    rothfusz_heat_index = (
        -42.379
        + (2.04901523 * temperature)
        + (10.14333127 * relative_humidity)
        - (0.22475541 * temperature * relative_humidity)
        - (0.00683783 * temperature * temperature)
        - (0.05481717 * relative_humidity * relative_humidity)
        + (0.00122874 * temperature * temperature * relative_humidity)
        + (0.00085282 * temperature * relative_humidity * relative_humidity)
        - (
            0.00000199
            * temperature
            * temperature
            * relative_humidity
            * relative_humidity
        )
    )
    heat_index = np.where(
        simple_heat_index > 80.0,
        rothfusz_heat_index,
        simple_heat_index,
    )
    low_humidity_mask = (
        (relative_humidity < 13.0)
        & (temperature >= 80.0)
        & (temperature <= 112.0)
    )
    low_humidity_adjustment = (
        ((13.0 - relative_humidity) / 4.0)
        * np.sqrt(
            np.maximum(
                0.0,
                (17.0 - np.abs(temperature - 95.0)) / 17.0,
            )
        )
    )
    heat_index = np.where(
        low_humidity_mask,
        heat_index - low_humidity_adjustment,
        heat_index,
    )

    high_humidity_mask = (
        (relative_humidity > 85.0)
        & (temperature >= 80.0)
        & (temperature <= 87.0)
    )
    high_humidity_adjustment = (
        ((relative_humidity - 85.0) / 10.0)
        * ((87.0 - temperature) / 5.0)
    )
    heat_index = np.where(
        high_humidity_mask,
        heat_index + high_humidity_adjustment,
        heat_index,
    )
    apparent = np.where(temperature >= 80.0, heat_index, apparent)
    return np.ma.masked_invalid(apparent)


def _calculate_apparent_temperature(
    grib_path: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calculate a single feels-like field from temperature, dew point, and wind."""
    temp_array, lat, lon, _ = _extract_dataset(grib_path, "t2m")
    dew_array, _, _, _ = _extract_dataset(grib_path, "d2m")
    wind_array, _, _, _ = _extract_dataset(grib_path, "si10")

    temp_f = _fahrenheit(
        np.asarray(getattr(temp_array, "values", temp_array), dtype=float)
    )
    dew_f = _fahrenheit(
        np.asarray(getattr(dew_array, "values", dew_array), dtype=float)
    )
    wind_ms = np.asarray(getattr(wind_array, "values", wind_array), dtype=float)

    apparent = _calculate_apparent_temperature_values(temp_f, dew_f, wind_ms)
    return apparent, lat, lon


def _load_rtma_product_grid(
    cache_root: str,
    source: RtmaSource,
    region: str,
    stream: str,
    product: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    config = get_product_config(product)
    grib_path = ensure_rtma_grib(cache_root, source)

    if product == "temperature_change_24h":
        prior_source = _resolve_24h_prior_source(region, stream, source)
        prior_grib_path = ensure_rtma_grib(cache_root, prior_source)

        cur_data_array, latitude, longitude, valid_time = _extract_dataset(
            grib_path, "t2m"
        )
        prev_data_array, prev_lat, prev_lon, _prev_valid_time = _extract_dataset(
            prior_grib_path, "t2m"
        )

        cur = _fahrenheit(
            np.asarray(getattr(cur_data_array, "values", cur_data_array), dtype=float)
        )
        prev = _fahrenheit(
            np.asarray(getattr(prev_data_array, "values", prev_data_array), dtype=float)
        )

        if cur.shape != prev.shape:
            raise ValueError(
                "RTMA 24h temperature-change grids do not align in shape: "
                f"current={cur.shape}, prior={prev.shape}."
            )
        if (
            np.asarray(latitude).shape != np.asarray(prev_lat).shape
            or np.asarray(longitude).shape != np.asarray(prev_lon).shape
        ):
            raise ValueError(
                "RTMA 24h temperature-change grids do not align in coordinates."
            )

        data = np.ma.masked_invalid(cur - prev)
        timestamp = _serialize_timestamp(valid_time) or source.valid_time.isoformat()
        return (
            data,
            np.asarray(latitude, dtype=float),
            np.asarray(longitude, dtype=float),
            timestamp,
        )

    if config.get("kind") == "derived":
        if product == "apparent_temperature":
            data, latitude, longitude = _calculate_apparent_temperature(grib_path)
        else:
            raise ValueError(f"Unknown derived product: {product}")

        # Extract valid_time from one of the variables
        _, _, _, valid_time = _extract_dataset(grib_path, config["vars"][0])
        timestamp = _serialize_timestamp(valid_time) or source.valid_time.isoformat()
        return (
            data,
            np.asarray(latitude, dtype=float),
            np.asarray(longitude, dtype=float),
            timestamp,
        )

    data_array, latitude, longitude, valid_time = _extract_dataset(
        grib_path, config["var"]
    )
    data = np.asarray(getattr(data_array, "values", data_array), dtype=float)
    if config.get("convert"):
        data = config["convert"](data)
    data = np.ma.masked_invalid(data)
    timestamp = _serialize_timestamp(valid_time) or source.valid_time.isoformat()
    return (
        data,
        np.asarray(latitude, dtype=float),
        np.asarray(longitude, dtype=float),
        timestamp,
    )


def build_rtma_legend(config: dict) -> dict:
    return {
        "kind": "scale",
        "title": config["label"],
        "units": config["units"],
        "display_units": config["units"],
        "vmin": config["vmin"],
        "vmax": config["vmax"],
        "anchors": _build_legend_anchors(config),
        "cmap": config["cmap"],
    }


def rtma_city_geojson_is_cached(
    cache_root: str,
    source: RtmaSource,
    region: str,
    stream: str,
    product: str,
    cities_path: str,
    source_data_key: str | None = None,
) -> bool:
    """Cheap check mirroring ensure_rtma_city_geojson's cache guard, without
    loading any grid data on a miss."""
    product_dir = os.path.join(cache_root, "rtma", "points", region, stream)
    if source_data_key:
        token = _sanitize_cache_token(source_data_key)
        out_name = f"{product}__{token}.geojson"
    else:
        out_name = f"{product}.geojson"
    out_path = os.path.join(product_dir, out_name)
    meta_path = out_path.replace(".geojson", "_meta.json")
    if not (os.path.exists(out_path) and os.path.exists(meta_path)):
        return False
    try:
        with open(meta_path, "r", encoding="utf-8") as handle:
            meta = json.load(handle)
        cities_file, cities_size = _cities_cache_signature(cities_path)
        return (
            meta.get("schema_version") == _RTMA_CITY_CACHE_SCHEMA
            and meta.get("source_data_key") == source.data_key
            and meta.get("source_url") == source.url
            and meta.get("cities_file") == cities_file
            and meta.get("cities_size") == cities_size
        )
    except Exception:
        return False


def ensure_rtma_city_geojson(
    cache_root: str,
    source: RtmaSource,
    region: str,
    stream: str,
    product: str,
    cities_path: str,
    source_data_key: str | None = None,
) -> tuple[str, dict]:
    product_dir = os.path.join(cache_root, "rtma", "points", region, stream)
    out_name = (
        f"{product}__{_sanitize_cache_token(source_data_key)}.geojson"
        if source_data_key
        else f"{product}.geojson"
    )
    out_path = os.path.join(product_dir, out_name)
    with _derived_cache_lock(out_path):
        return _ensure_rtma_city_geojson_unlocked(
            cache_root,
            source,
            region,
            stream,
            product,
            cities_path,
            source_data_key,
        )


def _ensure_rtma_city_geojson_unlocked(
    cache_root: str,
    source: RtmaSource,
    region: str,
    stream: str,
    product: str,
    cities_path: str,
    source_data_key: str | None = None,
) -> tuple[str, dict]:
    product_dir = os.path.join(cache_root, "rtma", "points", region, stream)
    os.makedirs(product_dir, exist_ok=True)
    if source_data_key:
        token = _sanitize_cache_token(source_data_key)
        out_name = f"{product}__{token}.geojson"
    else:
        out_name = f"{product}.geojson"
    out_path = os.path.join(product_dir, out_name)
    meta_path = out_path.replace(".geojson", "_meta.json")
    cities_file, cities_size = _cities_cache_signature(cities_path)

    if os.path.exists(out_path) and os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as handle:
                meta = json.load(handle)
            if (
                meta.get("schema_version") == _RTMA_CITY_CACHE_SCHEMA
                and meta.get("source_data_key") == source.data_key
                and meta.get("source_url") == source.url
                and meta.get("cities_file") == cities_file
                and meta.get("cities_size") == cities_size
            ):
                return out_path, meta
        except Exception:
            pass

    config = get_product_config(product)
    data, latitude, longitude, source_timestamp = _load_rtma_product_grid(
        cache_root,
        source,
        region,
        stream,
        product,
    )

    cities = _filter_city_points_for_region(_load_city_points(cities_path), region)
    city_points = _sample_city_values(data, latitude, longitude, cities)

    if product in {"temperature", "apparent_temperature"}:
        for point in city_points:
            point["value"] = _format_display_value(product, float(point["value"]))

    # Compact format: constant fields go in a single header; per-point data is
    # a flat list of [lat, lon, value, rank, city, state] tuples.
    # Compared to standard GeoJSON this cuts ~60-70% off the file size.
    points_compact = [
        [round(p["lat"], 4), round(p["lon"], 4), p["value"], p["rank"], p["city"], p["state"]]
        for p in city_points
    ]

    compact_doc = {
        "v": _RTMA_CITY_CACHE_SCHEMA,
        "product": product,
        "stream": stream,
        "region": region,
        "units": config["units"],
        "points": points_compact,
    }
    atomic_write_json(out_path, compact_doc, separators=(",", ":"))

    meta = {
        "schema_version": _RTMA_CITY_CACHE_SCHEMA,
        "source_data_key": source.data_key,
        "source_url": source.url,
        "source_valid_time": source.valid_time.isoformat(),
        "product": product,
        "stream": stream,
        "region": region,
        "units": config["units"],
        "timestamp": source_timestamp,
        "feature_count": len(points_compact),
        "cities_file": cities_file,
        "cities_size": cities_size,
    }
    atomic_write_json(meta_path, meta)
    return out_path, meta


def _warp_to_latlon_grid(
    data: np.ndarray,
    lat2d: np.ndarray,
    lon2d: np.ndarray,
) -> tuple["np.ma.MaskedArray", list[float]]:
    """Resample a curvilinear-grid array (e.g. RTMA LCC) onto a regular
    lat/lon grid so it can be placed correctly as a Leaflet image overlay.

    Uses full-resolution inverse-distance interpolation via cKDTree so the
    warped raster aligns with geographic features without frontend nudges.

    Returns (warped_masked_array, [west, east, south, north]).
    """
    from scipy.spatial import cKDTree

    lon2d = np.where(lon2d > 180.0, lon2d - 360.0, lon2d)

    lat_min = float(np.nanmin(lat2d))
    lat_max = float(np.nanmax(lat2d))
    lon_min = float(np.nanmin(lon2d))
    lon_max = float(np.nanmax(lon2d))

    src_rows, src_cols = data.shape
    n_lat, n_lon = src_rows, src_cols
    lat_out = np.linspace(lat_min, lat_max, n_lat)
    lon_out = np.linspace(lon_min, lon_max, n_lon)
    lon_mesh, lat_mesh = np.meshgrid(lon_out, lat_out)

    src_lat = lat2d.ravel()
    src_lon = lon2d.ravel()
    src_val = np.ma.filled(data, np.nan).ravel()

    valid = np.isfinite(src_lat) & np.isfinite(src_lon) & np.isfinite(src_val)
    if not np.any(valid):
        raise ValueError("RTMA warp failed: no valid source points.")

    src_points = np.column_stack([src_lat[valid], src_lon[valid]])
    src_values = src_val[valid]

    tree = cKDTree(src_points)
    query_points = np.column_stack([lat_mesh.ravel(), lon_mesh.ravel()])

    # Use a small neighbor set with inverse-distance weighting for smooth,
    # stable alignment while preserving fine-scale gradients.
    k = min(4, src_points.shape[0])
    dists, idx = tree.query(query_points, k=k, workers=-1)
    if k == 1:
        dists = dists[:, np.newaxis]
        idx = idx[:, np.newaxis]

    neighbors = src_values[idx]
    exact = dists[:, 0] <= 1.0e-12
    weights = 1.0 / np.maximum(dists, 1.0e-12)
    weight_sums = np.sum(weights, axis=1)
    interp = np.sum(weights * neighbors, axis=1) / np.maximum(weight_sums, 1.0e-12)
    if np.any(exact):
        interp[exact] = neighbors[exact, 0]

    dlat = abs(float(lat_out[1] - lat_out[0])) if n_lat > 1 else 0.05
    dlon = abs(float(lon_out[1] - lon_out[0])) if n_lon > 1 else 0.05
    max_gap_deg = max(0.06, 3.5 * max(dlat, dlon))
    outside = dists[:, 0] > max_gap_deg

    warped = interp.reshape(n_lat, n_lon)
    outside_mask = outside.reshape(n_lat, n_lon)
    warped_masked = np.ma.masked_where(outside_mask | ~np.isfinite(warped), warped)

    if n_lon > 1:
        west = float(lon_out[0] - 0.5 * dlon)
        east = float(lon_out[-1] + 0.5 * dlon)
    else:
        west = float(lon_out[0])
        east = float(lon_out[0])
    if n_lat > 1:
        south = float(lat_out[0] - 0.5 * dlat)
        north = float(lat_out[-1] + 0.5 * dlat)
    else:
        south = float(lat_out[0])
        north = float(lat_out[0])

    return warped_masked, [west, east, south, north]


def _render_rtma_png_standalone_unbounded(
    grib_path: str,
    product: str,
    crop_extent: list[float],
    out_path: str,
    cache_root: str | None = None,
    source: RtmaSource | None = None,
    region: str | None = None,
    stream: str | None = None,
    lat_1d: np.ndarray | None = None,
    lon_1d: np.ndarray | None = None,
) -> tuple[str, list[float], dict]:
    """Standalone RTMA PNG renderer using PIL for ~3-5x faster rendering."""
    import json
    from PIL import Image
    import numpy as np
    import matplotlib.colors as mcolors

    config = get_product_config(product)

    # Extract data (same as matplotlib version)
    source_timestamp = None
    if (
        (
            product == "temperature_change_24h"
            or config.get("kind") == "derived"
        )
        and cache_root is not None
        and source is not None
        and region is not None
        and stream is not None
    ):
        data, latitude, longitude, source_timestamp = _load_rtma_product_grid(
            cache_root,
            source,
            region,
            stream,
            product,
        )
        valid_time = source_timestamp
    else:
        data_array, latitude, longitude, valid_time = _extract_dataset(
            grib_path, config["var"]
        )
        data = np.asarray(getattr(data_array, "values", data_array), dtype=float)
        if config.get("convert"):
            data = config["convert"](data)
        data = np.ma.masked_invalid(data)

    data, latitude, longitude = _crop_grid(data, latitude, longitude, crop_extent)

    lat_arr = np.asarray(latitude, dtype=float)
    lon_arr = np.asarray(longitude, dtype=float)
    if lat_arr.ndim == 2:
        data, actual_bounds = _warp_to_latlon_grid(data, lat_arr, lon_arr)
    else:
        lon_arr = np.where(lon_arr > 180.0, lon_arr - 360.0, lon_arr)
        _dlat = abs(float(lat_arr[1] - lat_arr[0])) if lat_arr.size > 1 else 0.01
        _dlon = abs(float(lon_arr[1] - lon_arr[0])) if lon_arr.size > 1 else 0.01
        actual_bounds = [
            float(np.nanmin(lon_arr) - 0.5 * _dlon),
            float(np.nanmax(lon_arr) + 0.5 * _dlon),
            float(np.nanmin(lat_arr) - 0.5 * _dlat),
            float(np.nanmax(lat_arr) + 0.5 * _dlat),
        ]

    from mrms.mrms_utils import warp_array_to_mercator
    from config.mrms_config import MRMS_WARP_MAX_DIM

    # Use pre-computed lat/lon if provided (for batch rendering optimization).
    if lat_1d is None or lon_1d is None:
        if lat_arr.ndim == 2:
            lat_1d = np.linspace(
                float(np.nanmin(lat_arr)), float(np.nanmax(lat_arr)), data.shape[0]
            )
            lon_1d = np.linspace(
                float(np.nanmin(lon_arr)), float(np.nanmax(lon_arr)), data.shape[1]
            )
        else:
            lat_1d = lat_arr
            lon_1d = lon_arr

    data, actual_bounds = warp_array_to_mercator(
        data, lat_1d, lon_1d, max_dim=MRMS_WARP_MAX_DIM
    )

    # Apply colormap and norm using PIL pipeline
    cmap = _resolve_render_colormap(config).copy()
    cmap.set_bad((0, 0, 0, 0))
    norm = mcolors.Normalize(vmin=config["vmin"], vmax=config["vmax"])

    # Normalize data and apply colormap
    masked = np.ma.getmaskarray(data)
    normalized = norm(data)
    rgb = cmap(normalized)

    # Convert to 8-bit RGBA
    rgba = (rgb * 255).astype(np.uint8)

    # Set masked/invalid pixels to transparent (alpha=0)
    invalid = masked | np.isnan(data)
    if np.any(invalid):
        rgba[invalid, 3] = 0

    # Create PIL image from RGBA array
    img = Image.fromarray(rgba, mode="RGBA")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, format="PNG", optimize=False, compress_level=1)

    # Write sidecars
    with open(out_path.replace(".png", "_bounds.json"), "w", encoding="utf-8") as f:
        json.dump(actual_bounds, f)

    meta = {
        "full_name": config["label"],
        "units": config["units"],
        "vmin": config["vmin"],
        "vmax": config["vmax"],
        "legend": build_rtma_legend(config),
        "timestamp": source_timestamp or _serialize_timestamp(valid_time),
    }
    with open(out_path.replace(".png", "_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)

    return out_path, actual_bounds, meta


def _render_rtma_png_standalone(
    grib_path: str,
    product: str,
    crop_extent: list[float],
    out_path: str,
    cache_root: str | None = None,
    source: RtmaSource | None = None,
    region: str | None = None,
    stream: str | None = None,
    lat_1d: np.ndarray | None = None,
    lon_1d: np.ndarray | None = None,
) -> tuple[str, list[float], dict]:
    from app_core.render_budget import heavy_render_slot

    with heavy_render_slot():
        return _render_rtma_png_standalone_unbounded(
            grib_path,
            product,
            crop_extent,
            out_path,
            cache_root=cache_root,
            source=source,
            region=region,
            stream=stream,
            lat_1d=lat_1d,
            lon_1d=lon_1d,
        )
