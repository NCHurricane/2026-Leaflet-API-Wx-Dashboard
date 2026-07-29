"""Background worker for live radar overlays (weather tab).

This worker pulls recent NEXRAD files from NODD (AWS), renders transparent PNG
overlays per configured site/product, and writes metadata using the shared
overlay cache schema.
"""

from __future__ import annotations

import json
import math
import multiprocessing
import os
import sys
import threading
import time
import zlib
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

# Add project root to path for both module and direct execution
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import cartopy.crs as ccrs
import matplotlib
import numpy as np

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from cache.overlay_cache_utils import (
    datetime_from_frame_key,
    frame_key_from_datetime,
    radar_list_frames,
    radar_overlay_image_path,
    radar_prune_frames,
    radar_read_processed_keys,
    radar_update_index,
    radar_write_processed_keys,
)
from config.radar_config import (
    LIVE_RADAR_KEEP_FRAMES,
    LIVE_RADAR_L2_DEFAULT_ELEVATION,
    LIVE_RADAR_L2_USE_CHUNKS,
    LIVE_RADAR_LOOKBACK_HOURS,
    LIVE_RADAR_MAX_KEEP_FRAMES,
    LIVE_RADAR_PRODUCTS,
    LIVE_RADAR_SITES,
    LIVE_RADAR_WORKER_INTERVAL_MIN,
    live_radar_target_frames,
    normalize_live_radar_lookback_hours,
)
from radar.webgl_artifact import prune_artifacts, write_artifact
from workers._freshness import is_cache_fresh, mark_run_complete

_CACHE_ROOT = Path(__file__).resolve().parent.parent / "cache"
_RADAR_ROOT = _CACHE_ROOT / "radar" / "live"
_TMP_RENDER_ROOT = _CACHE_ROOT / "tmp" / "radar_live"

# L3 products: skip if a successful run happened within 75% of configured interval.
# L2 chunks: no global gate — the task runs every minute and each run is cheap
# (only new chunks are downloaded; complete scans are skipped entirely).
_L3_FRESH_WINDOW_SEC = max(60, int(LIVE_RADAR_WORKER_INTERVAL_MIN * 60 * 0.75))

# Radar map bounds use 250 nm range rings with 20% padding.
# Covers full Level 3 Super-Res extent (460 km).
_MAX_RANGE_NM = 250.0
_NM_TO_KM = 1.852
_KM_PER_DEG_LAT = 111.32
_PADDING_FACTOR = 1.20
_MAX_L2_VOLUME_CONSUMERS = 8
_DISCOVERY_INDEX_VERSION = 1
_L2_SOURCE_LOCKS: dict[str, threading.Lock] = {}
_L2_SOURCE_LOCKS_GUARD = threading.Lock()


def _radar_parallel_worker_count() -> int:
    from config.radar_config import LIVE_RADAR_PARALLEL_WORKERS

    configured = int(LIVE_RADAR_PARALLEL_WORKERS or 0)
    if configured > 0:
        return configured
    return max(1, min(4, os.cpu_count() or 1))


def _l2_source_lock(site: str) -> threading.Lock:
    site_key = str(site).strip().upper()
    with _L2_SOURCE_LOCKS_GUARD:
        return _L2_SOURCE_LOCKS.setdefault(site_key, threading.Lock())


def _radar_render_pool_ping(_value: int) -> int:
    return os.getpid()


class _RadarRenderPoolOwner:
    """Lazily own one bounded multiprocessing pool for a render run."""

    def __init__(self, processes: int):
        self.processes = max(1, int(processes))
        self.creation_count = 0
        self.render_batches = 0
        self.startup_ms = 0.0
        self.warm_ms = 0.0
        self._pool = None
        self._closed = False

    def start(self):
        if self._closed:
            raise RuntimeError("Radar render pool owner is closed")
        if self._pool is None:
            started = time.perf_counter()
            self._pool = multiprocessing.Pool(processes=self.processes)
            self.startup_ms += (time.perf_counter() - started) * 1000.0
            self.creation_count += 1
        return self

    def warm(self) -> list[int]:
        """Start workers and wait for a lightweight task before timed reuse."""
        self.start()
        started = time.perf_counter()
        process_ids = self._pool.map(
            _radar_render_pool_ping,
            range(self.processes),
            chunksize=1,
        )
        self.warm_ms += (time.perf_counter() - started) * 1000.0
        return process_ids

    def starmap(self, function, work_items):
        self.start()
        self.render_batches += 1
        return self._pool.starmap(function, work_items)

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool.join()
            self._pool = None
        self._closed = True

    def terminate(self) -> None:
        if self._pool is not None:
            self._pool.terminate()
            self._pool.join()
            self._pool = None
        self._closed = True


@contextmanager
def _radar_render_pool_owner(processes: int | None = None):
    owner = _RadarRenderPoolOwner(
        _radar_parallel_worker_count() if processes is None else processes
    )
    try:
        yield owner
    except BaseException:
        owner.terminate()
        raise
    else:
        owner.close()


def _resolve_radar_data_utils(product_key: str = ""):
    if LIVE_RADAR_L2_USE_CHUNKS and str(product_key).upper().startswith("L2_"):
        from radar import radar_chunks_utils
        return radar_chunks_utils
    from radar import radar_nodd_utils
    return radar_nodd_utils


def _is_chunks_utils(radar_data_utils) -> bool:
    return "chunks" in getattr(radar_data_utils, "__name__", "")


def _site_coords(site: str) -> tuple[float, float] | None:
    try:
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        info = NEXRAD_LOCATIONS.get(site)
        if not info:
            return None
        lat = info.get("lat")
        lon = info.get("lon")
        if lat is None or lon is None:
            return None
        return float(lat), float(lon)
    except Exception:
        return None


def _site_bounds(site: str) -> list[float] | None:
    coords = _site_coords(site)
    if not coords:
        return None
    site_lat, site_lon = coords
    padded_km = _MAX_RANGE_NM * _NM_TO_KM * _PADDING_FACTOR
    lat_offset = padded_km / _KM_PER_DEG_LAT
    lon_offset = padded_km / (
        _KM_PER_DEG_LAT * max(math.cos(math.radians(site_lat)), 1e-3)
    )
    return [
        site_lon - lon_offset,
        site_lon + lon_offset,
        site_lat - lat_offset,
        site_lat + lat_offset,
    ]


def _parse_dt_from_filename(path: Path) -> datetime | None:
    import re

    name = path.name
    match = re.search(r"(\d{8})_(\d{4,6})", name)
    if not match:
        return None
    date_part, time_part = match.groups()
    if len(time_part) == 4:
        time_part += "00"
    try:
        return datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


# Per-product maximum range (km) for MetPy-decoded Level III products, used to
# compute gate spacing from the decoded gate count. Sourced from MetPy's
# prod_spec_map (metpy/io/nexrad.py). Only products Py-ART cannot read are here;
# precipitation rate (DPR/176) and storm-total accumulation (DTA/172) are read
# natively by Py-ART and do not need the MetPy fallback.
_METPY_PRODUCT_MAX_RANGE_KM = {
    134: 460.0,  # High Resolution VIL (DVL)
    135: 345.0,  # Enhanced Echo Tops (EET)
}


def _read_level3_with_metpy(file_path: str):
    """Decode a Level III product with MetPy and build a Py-ART Radar object.

    Used for digital products Py-ART cannot read natively (VIL, Echo Tops).
    MetPy's product mappers apply the documented scale/offset calibration to
    convert raw codes to physical values.
    """
    import numpy as np
    import pyart
    from metpy.io import Level3File

    level3 = Level3File(file_path)
    prod_code = int(getattr(level3.prod_desc, "prod_code", 0))
    if prod_code not in _METPY_PRODUCT_MAX_RANGE_KM:
        raise ValueError(
            f"MetPy decode unsupported for Level III product {prod_code}"
        )
    block = level3.sym_block[0][0]
    raw = np.array(block["data"])
    mapped = level3.map_data(raw)
    if isinstance(mapped, tuple):  # Echo Tops returns (data, topped_flag)
        mapped = mapped[0]
    data = np.ma.masked_invalid(np.asarray(mapped, dtype=float))

    nrays, ngates = data.shape
    max_range_km = _METPY_PRODUCT_MAX_RANGE_KM[prod_code]
    gate_width_m = (max_range_km * 1000.0) / ngates
    first_gate_m = 0.0
    azimuths = np.asarray(block["start_az"], dtype=float)

    radar = pyart.testing.make_empty_ppi_radar(ngates, nrays, 1)
    # Set the volume time so frame timestamps are correct; otherwise Py-ART's
    # empty-radar default (1989-01-01) makes every frame collide on one key.
    vol_time = level3.metadata.get("vol_time") or level3.metadata.get("prod_time")
    if vol_time is not None:
        radar.time["units"] = "seconds since " + vol_time.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        radar.time["data"] = np.zeros(nrays, dtype=float)
    radar.range["data"] = first_gate_m + np.arange(ngates, dtype=float) * gate_width_m
    radar.azimuth["data"] = azimuths
    radar.elevation["data"] = np.zeros(nrays, dtype=float)
    radar.fixed_angle["data"] = np.array([0.0])
    radar.latitude["data"] = np.array([float(level3.lat)])
    radar.longitude["data"] = np.array([float(level3.lon)])
    radar.altitude["data"] = np.array([float(getattr(level3, "height", 0.0) or 0.0)])
    radar.sweep_start_ray_index["data"] = np.array([0])
    radar.sweep_end_ray_index["data"] = np.array([nrays - 1])
    radar.fields["reflectivity"] = {
        "data": data,
        "units": "",
        "long_name": f"Level III product {prod_code}",
    }
    return radar


def _pyart_radar_has_fields(radar) -> bool:
    """True when Py-ART produced at least one usable data field.

    Py-ART can "succeed" on some digital Level III products yet return a radar
    with no fields, in which case the MetPy decoder should be used instead.
    """
    return bool(getattr(radar, "fields", None))


def _read_level3_file(file_path: str):
    import pyart

    try:
        radar = pyart.io.read_nexrad_level3(file_path)
        if _pyart_radar_has_fields(radar):
            return radar
        return _read_level3_with_metpy(file_path)
    except (NotImplementedError, ValueError, AssertionError):
        with open(file_path, "rb") as fh:
            raw = fh.read()
        zlib_start = -1
        for magic in (b"\x78\xda", b"\x78\x9c", b"\x78\x01"):
            zlib_start = raw.find(magic, 0, 128)
            if zlib_start != -1:
                break
        if zlib_start == -1:
            return _read_level3_with_metpy(file_path)
        decompressor = zlib.decompressobj()
        header_block = decompressor.decompress(raw[zlib_start:])
        full_nids = header_block + decompressor.unused_data
        temp_path = Path(file_path).with_suffix(".nids")
        temp_path.write_bytes(full_nids)
        try:
            radar = pyart.io.read_nexrad_level3(str(temp_path))
            if _pyart_radar_has_fields(radar):
                return radar
            return _read_level3_with_metpy(file_path)
        except (NotImplementedError, ValueError, AssertionError):
            return _read_level3_with_metpy(file_path)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


def _read_radar(level: str, file_path: str):
    import pyart

    if str(level) == "Level 3":
        return _read_level3_file(file_path)
    return pyart.io.read_nexrad_archive(file_path)


def _frame_dt_from_radar(radar, file_path: Path) -> datetime | None:
    import pyart

    try:
        raw_dt = pyart.util.datetimes_from_radar(radar)[0]
        if isinstance(raw_dt, np.datetime64):
            unix_ts = (raw_dt - np.datetime64("1970-01-01T00:00:00")) / np.timedelta64(
                1, "s"
            )
            return datetime.fromtimestamp(float(unix_ts), tz=timezone.utc)
        if isinstance(raw_dt, datetime):
            return (
                raw_dt.replace(tzinfo=timezone.utc)
                if raw_dt.tzinfo is None
                else raw_dt.astimezone(timezone.utc)
            )
        if hasattr(raw_dt, "year") and hasattr(raw_dt, "month"):
            return datetime(
                int(raw_dt.year),
                int(raw_dt.month),
                int(raw_dt.day),
                int(raw_dt.hour),
                int(raw_dt.minute),
                int(raw_dt.second),
                tzinfo=timezone.utc,
            )
    except Exception:
        pass
    return _parse_dt_from_filename(file_path)


def _frame_dt_from_radar_file_lazy(file_path: Path) -> datetime | None:
    """Extract frame timestamp from file path without fully reading radar data."""
    dt = _parse_dt_from_filename(file_path)
    if dt:
        return dt
    try:
        radar = _read_radar("Level 3", str(file_path))
        return _frame_dt_from_radar(radar, file_path)
    except Exception:
        return None


def _field_for_product(
    level: str,
    product_code: str,
    available_fields: list[str],
    product_cfg: dict | None = None,
) -> str | None:
    if not available_fields:
        return None
    configured_fields = list((product_cfg or {}).get("field_names") or [])
    for field_name in configured_fields:
        if field_name in available_fields:
            return field_name
    if str(level) == "Level 2":
        l2_map = {
            "REF": "reflectivity",
            "VEL": "velocity",
            "SW": "spectrum_width",
            "ZDR": "differential_reflectivity",
            "RHO": "cross_correlation_ratio",
            "KDP": "specific_differential_phase",
            "PHI": "differential_phase",
        }
        mapped = l2_map.get(str(product_code).upper())
        if mapped and mapped in available_fields:
            return mapped
    if product_code in {"N0G", "N0U", "N1U", "N0S", "NVW"}:
        for candidate in available_fields:
            if "velocity" in candidate.lower():
                return candidate
    return available_fields[0]


def _source_product_code(product_code: str, product_cfg: dict | None = None) -> str:
    configured = str((product_cfg or {}).get("source_product") or "").strip().upper()
    return configured or str(product_code or "").strip().upper()


def _ensure_derived_field(
    radar,
    field_name: str,
    product_cfg: dict | None = None,
) -> str:
    render_cfg = product_cfg or {}
    derived_field = str(render_cfg.get("derived_field") or "").strip().lower()
    if derived_field != "storm_relative_velocity":
        return field_name
    if field_name not in getattr(radar, "fields", {}):
        return field_name

    source_field = radar.fields[field_name]
    source_data = np.ma.array(source_field.get("data"))
    if source_data.ndim != 2:
        return field_name
    source_data = np.ma.masked_where(
        ~np.isfinite(source_data) | (np.abs(source_data) >= 999.0),
        source_data,
    )

    azimuths = np.asarray(getattr(radar, "azimuth", {}).get("data", []), dtype=float)
    if azimuths.size != source_data.shape[0]:
        return field_name

    speed_kt = float(render_cfg.get("storm_motion_speed_kt", 0.0) or 0.0)
    to_degrees = float(render_cfg.get("storm_motion_to_degrees", 0.0) or 0.0)
    speed_ms = speed_kt / 1.94384449
    radial_component_ms = speed_ms * np.cos(np.deg2rad(azimuths - to_degrees))
    derived_data = source_data - radial_component_ms[:, np.newaxis]

    derived_name = "storm_relative_velocity"
    radar.fields[derived_name] = {
        **source_field,
        "data": np.ma.array(derived_data, copy=False),
        "standard_name": "storm_relative_velocity",
        "long_name": "Storm-relative velocity",
        "units": source_field.get("units", "meters_per_second"),
    }
    return derived_name


def _best_sweep(radar, field_name: str) -> int:
    try:
        data = radar.fields[field_name]["data"]
        best_idx = 0
        best_count = -1
        for sweep_idx in range(int(getattr(radar, "nsweeps", 1))):
            sweep_slice = radar.get_slice(sweep_idx)
            sweep_data = data[sweep_slice]
            valid_count = int(
                np.sum(
                    ~sweep_data.mask
                    if hasattr(sweep_data, "mask")
                    else ~np.isnan(sweep_data)
                )
            )
            if valid_count > best_count:
                best_count = valid_count
                best_idx = sweep_idx
        return best_idx
    except Exception:
        return 0


def _fixed_angles(radar) -> list[float]:
    try:
        raw = getattr(radar, "fixed_angle", {}).get("data")
        if raw is None:
            return []
        return [round(float(value), 1) for value in np.asarray(raw).tolist()]
    except Exception:
        return []


def _sweep_valid_count(radar, field_name: str, sweep_idx: int) -> int:
    try:
        data = radar.fields[field_name]["data"][radar.get_slice(sweep_idx)]
        if hasattr(data, "mask"):
            return int(np.sum(~np.ma.getmaskarray(data)))
        return int(np.sum(np.isfinite(data)))
    except Exception:
        return 0


def _select_sweep(
    radar, field_name: str, requested_elevation: str = "auto"
) -> tuple[int, list[float], float | None]:
    fixed_angles = _fixed_angles(radar)
    available = sorted(set(fixed_angles))
    if not fixed_angles:
        return 0, available, None
    if str(requested_elevation or "auto").lower() == "auto":
        target = min(fixed_angles)
    else:
        target = float(requested_elevation)
    nearest = min(fixed_angles, key=lambda angle: abs(angle - target))
    # Split-cut VCPs scan the low tilts twice at the same fixed angle: a
    # surveillance sweep (reflectivity only) and a Doppler sweep (velocity /
    # spectrum width). Among sweeps at the matched angle, pick the one with
    # the most valid data for the field being rendered.
    candidates = [
        index
        for index, angle in enumerate(fixed_angles)
        if abs(angle - nearest) <= 0.1
    ]
    sweep = max(
        candidates, key=lambda index: _sweep_valid_count(radar, field_name, index)
    )
    return sweep, available, fixed_angles[sweep]


def _radar_cache_product_key(
    product_key: str, elevation: str, product_cfg: dict | None = None
) -> str:
    product_id = str(product_key or "").strip().upper()
    cache_variant = str((product_cfg or {}).get("cache_variant") or "").strip().upper()
    if cache_variant:
        product_id = f"{product_id}__{cache_variant}"
    if not product_id.startswith("L2_"):
        return product_id
    suffix = "AUTO" if elevation == "auto" else elevation.replace(".", "P")
    return f"{product_id}__ELEV_{suffix}"


def _product_cfg_with_storm_motion(
    product_key: str, product_cfg: dict, storm_motion: dict | None = None
) -> dict:
    if str(product_key or "").strip().upper() != "L2_SRV" or not storm_motion:
        return product_cfg
    cfg = dict(product_cfg)
    cfg["storm_motion_speed_kt"] = float(storm_motion["speed_kt"])
    cfg["storm_motion_to_degrees"] = float(storm_motion["motion_to_degrees"])
    cfg["cache_variant"] = str(storm_motion["cache_variant"])
    cfg["motion_source"] = storm_motion.get("source")
    cfg["storm_cell_id"] = storm_motion.get("cell_id")
    return cfg


def _prepare_field_data(field_data, product_code: str, product_cfg: dict | None):
    render_cfg = product_cfg or {}
    data = np.ma.array(field_data)
    value_scale = float(render_cfg.get("value_scale", 1.0))
    if value_scale != 1.0:
        data = data * value_scale

    mask_strategy = str(render_cfg.get("mask") or "").lower()
    is_velocity = mask_strategy == "velocity" or product_code in {
        "N0G",
        "N0U",
        "N1U",
        "N0S",
        "NVW",
        "VEL",
    }
    if is_velocity:
        invalid = ~np.isfinite(data) | (np.abs(data) >= 999.0)
    elif mask_strategy == "nonnegative":
        invalid = ~np.isfinite(data) | (data < 0.0)
    elif mask_strategy == "finite":
        invalid = ~np.isfinite(data)
    else:
        invalid = ~np.isfinite(data) | (data <= -31.5)

    # Optional low-value filter: hide the lightest returns (e.g. reflectivity
    # below a dBZ floor) without affecting the color scaling (vmin/vmax).
    min_value = render_cfg.get("min_value")
    if min_value is not None:
        invalid = invalid | (data < float(min_value))

    return np.ma.masked_where(invalid, data)


def _bearing_distance_from_site(
    site_lat: float, site_lon: float, lat: float, lon: float
) -> tuple[float, float]:
    lat1 = math.radians(float(site_lat))
    lat2 = math.radians(float(lat))
    dlat = lat2 - lat1
    dlon = math.radians(float(lon) - float(site_lon))

    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    )
    distance_m = 6371000.0 * 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    azimuth_deg = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return azimuth_deg, distance_m


def _circular_angle_delta(values, target):
    return np.abs(((np.asarray(values, dtype=float) - float(target) + 180.0) % 360.0) - 180.0)


def _file_key(f: Path, use_mtime: bool) -> str:
    """Return a cache key for a source radar file.

    When use_mtime=True (chunk-assembled files), the mtime is included so
    a partial scan that is later re-assembled with more chunks gets a new key
    and is re-rendered, while a fully assembled stable file keeps the same key.
    """
    if use_mtime:
        try:
            return f"{f.name}:{int(f.stat().st_mtime)}"
        except OSError:
            return f.name
    return f.name


def _radar_source_download_dir(site: str, level: str, source_product_code: str) -> Path:
    level_path = str(level).lower().replace(" ", "")
    storage_product = source_product_code
    if level_path == "level2" and not LIVE_RADAR_L2_USE_CHUNKS:
        from radar.radar_nodd_utils import LEVEL2_SOURCE_SPOOL

        storage_product = LEVEL2_SOURCE_SPOOL
    return _RADAR_ROOT / f"radar_{level_path}_downloads" / storage_product / site


def _radar_source_download_dirs(
    site: str, level: str, source_product_code: str
) -> list[Path]:
    canonical = _radar_source_download_dir(site, level, source_product_code)
    paths = [canonical]
    if _level_code(level) == "L2" and not LIVE_RADAR_L2_USE_CHUNKS:
        legacy = (
            _RADAR_ROOT
            / "radar_level2_downloads"
            / source_product_code
            / site
        )
        if legacy != canonical:
            paths.append(legacy)
    return paths


def _find_source_file_for_frame(
    site: str,
    level: str,
    source_product_code: str,
    frame_key: str,
    source_data_key: str | None = None,
) -> Path | None:
    data_dirs = _radar_source_download_dirs(site, level, source_product_code)
    if source_data_key:
        for data_dir in data_dirs:
            direct = data_dir / str(source_data_key)
            if direct.exists() and direct.is_file():
                return direct
    try:
        target_dt = frame_key_from_datetime(datetime_from_frame_key(frame_key))
    except Exception:
        target_dt = str(frame_key or "")
    candidates = []
    for data_dir in data_dirs:
        try:
            candidates.extend(p for p in data_dir.iterdir() if p.is_file())
        except OSError:
            continue
    if not candidates:
        return None
    frame_key_text = str(frame_key or "")
    if frame_key_text:
        direct_match = next(
            (p for p in candidates if frame_key_text in p.name),
            None,
        )
        if direct_match:
            return direct_match
    for candidate in sorted(candidates, reverse=True):
        try:
            radar = _read_radar(level, str(candidate))
            frame_dt = _frame_dt_from_radar(radar, candidate)
            if frame_dt and frame_key_from_datetime(frame_dt) == target_dt:
                return candidate
        except Exception:
            continue
    return None


@lru_cache(maxsize=16)
def _prepared_sample_grid(
    source_file: str,
    level: str,
    product_id: str,
    product_code: str,
    elevation: str,
    storm_motion_key: str,
) -> dict:
    product_cfg = LIVE_RADAR_PRODUCTS.get(product_id) or {}
    storm_motion = json.loads(storm_motion_key) if storm_motion_key else None
    product_cfg = _product_cfg_with_storm_motion(product_id, product_cfg, storm_motion)

    radar = _read_radar(level, source_file)
    available_fields = list(getattr(radar, "fields", {}).keys())
    field_name = _field_for_product(level, product_code, available_fields, product_cfg)
    if not field_name:
        raise ValueError("Radar field is unavailable for product.")
    field_name = _ensure_derived_field(radar, field_name, product_cfg)
    sweep, _available_elevations, selected_elevation = _select_sweep(
        radar, field_name, elevation
    )
    data = _prepare_field_data(
        radar.fields[field_name].get("data"),
        product_code,
        product_cfg,
    )
    sweep_slice = radar.get_slice(sweep)
    ranges_m = np.asarray(radar.range["data"], dtype=float)
    return {
        "sweep_data": np.ma.array(data[sweep_slice]),
        "azimuths": np.asarray(radar.azimuth["data"][sweep_slice], dtype=float),
        "ranges_m": ranges_m,
        "max_range_m": float(np.nanmax(ranges_m)) if ranges_m.size else 0.0,
        "radar_lat": float(radar.latitude["data"][0]),
        "radar_lon": float(radar.longitude["data"][0]),
        "field_name": field_name,
        "selected_elevation": selected_elevation,
        "units": _units_for_product(product_id, product_code, product_cfg),
        "label": str(product_cfg.get("label") or product_id),
    }


def sample_live_radar_value(
    site: str,
    product_key: str,
    frame_key: str,
    lat: float,
    lon: float,
    *,
    elevation: str = "auto",
    source_data_key: str | None = None,
    storm_motion: dict | None = None,
) -> dict:
    site_id = str(site or "").strip().upper()
    product_id = str(product_key or "L3_N0B").strip().upper()
    product_cfg = LIVE_RADAR_PRODUCTS.get(product_id)
    if not product_cfg:
        return {"status": "error", "detail": f"Unsupported radar product: {product_id}"}

    product_cfg = _product_cfg_with_storm_motion(product_id, product_cfg, storm_motion)
    level = str(product_cfg.get("level") or "Level 3")
    product_code = str(product_cfg.get("product") or "N0B").upper()
    source_product_code = _source_product_code(product_code, product_cfg)
    source_file = _find_source_file_for_frame(
        site_id, level, source_product_code, frame_key, source_data_key
    )
    if source_file is None:
        return {"status": "error", "detail": "Source radar file for frame is unavailable."}

    storm_motion_key = (
        json.dumps(storm_motion, sort_keys=True, separators=(",", ":"))
        if storm_motion
        else ""
    )
    try:
        grid = _prepared_sample_grid(
            str(source_file),
            level,
            product_id,
            product_code,
            elevation,
            storm_motion_key,
        )
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}

    azimuth_deg, distance_m = _bearing_distance_from_site(
        grid["radar_lat"], grid["radar_lon"], float(lat), float(lon)
    )
    ranges_m = grid["ranges_m"]
    if not ranges_m.size or distance_m < 0 or distance_m > grid["max_range_m"]:
        return {
            "status": "no_data",
            "reason": "out_of_range",
            "azimuth_deg": round(azimuth_deg, 1),
            "distance_km": round(distance_m / 1000.0, 1),
        }

    ray_idx = int(np.argmin(_circular_angle_delta(grid["azimuths"], azimuth_deg)))
    gate_idx = int(np.argmin(np.abs(ranges_m - distance_m)))
    value = grid["sweep_data"][ray_idx, gate_idx]
    if np.ma.is_masked(value) or not np.isfinite(float(value)):
        return {
            "status": "no_data",
            "reason": "masked",
            "azimuth_deg": round(azimuth_deg, 1),
            "distance_km": round(distance_m / 1000.0, 1),
            "gate_range_km": round(float(ranges_m[gate_idx]) / 1000.0, 1),
        }

    return {
        "status": "success",
        "site": site_id,
        "product": product_id,
        "frame_key": str(frame_key or ""),
        "source_data_key": source_file.name,
        "value": round(float(value), 2),
        "units": grid["units"],
        "label": grid["label"],
        "field": grid["field_name"],
        "selected_elevation": grid["selected_elevation"],
        "azimuth_deg": round(azimuth_deg, 1),
        "distance_km": round(distance_m / 1000.0, 1),
        "gate_range_km": round(float(ranges_m[gate_idx]) / 1000.0, 1),
    }


def _discovery_index_path(site: str, level_code: str, product_key: str) -> Path:
    """Return path to the radar file discovery index for a site/level/product."""
    return (
        _CACHE_ROOT
        / "radar"
        / site.upper()
        / level_code.upper()
        / product_key.upper()
        / ".discovery_index.json"
    )


def _read_discovery_index(
    site: str, level_code: str, product_key: str
) -> dict:
    """Load the discovery index, or return empty dict if not found."""
    try:
        path = _discovery_index_path(site, level_code, product_key)
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, dict):
                return payload
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _write_discovery_index(
    site: str, level_code: str, product_key: str, index: dict
) -> None:
    """Write the discovery index atomically."""
    tmp = None
    try:
        path = _discovery_index_path(site, level_code, product_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(
            f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(index, fh, separators=(",", ":"))
        os.replace(str(tmp), str(path))
    except Exception:
        pass
    finally:
        try:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _discover_radar_files(data_path: Path) -> list[Path]:
    files: list[Path] = []
    ignored_suffixes = (".tmp", ".part", ".json", ".txt", ".md", ".idx", ".lock")
    if not data_path.exists():
        return files
    for entry in data_path.iterdir():
        if not entry.is_file():
            continue
        name_lower = entry.name.lower()
        if name_lower.endswith(ignored_suffixes):
            continue
        if name_lower.endswith("_mdm"):
            continue
        try:
            if entry.stat().st_size <= 0:
                continue
        except OSError:
            continue
        files.append(entry)
    return sorted(files, key=lambda p: p.name)


def _files_from_discovery_index(
    data_path: Path,
    index: dict,
    dir_mtime_ns: int,
) -> list[Path] | None:
    if index.get("version") != _DISCOVERY_INDEX_VERSION:
        return None
    if index.get("dir_mtime_ns") != dir_mtime_ns:
        return None
    names = index.get("files")
    if not isinstance(names, list):
        return None

    files = []
    for raw_name in names:
        name = str(raw_name or "")
        if not name or Path(name).name != name:
            return None
        candidate = data_path / name
        try:
            if not candidate.is_file() or candidate.stat().st_size <= 0:
                return None
        except OSError:
            return None
        files.append(candidate)
    return sorted(files, key=lambda path: path.name)


def _discover_radar_files_cached(
    data_path: Path,
    site: str,
    level_code: str,
    product_key: str,
) -> tuple[list[Path], bool]:
    try:
        dir_mtime_ns = data_path.stat().st_mtime_ns
    except OSError:
        return [], False

    index = _read_discovery_index(site, level_code, product_key)
    cached = _files_from_discovery_index(data_path, index, dir_mtime_ns)
    if cached is not None:
        return cached, True

    files = _discover_radar_files(data_path)
    _write_discovery_index(
        site,
        level_code,
        product_key,
        {
            "version": _DISCOVERY_INDEX_VERSION,
            "dir_mtime_ns": dir_mtime_ns,
            "files": [path.name for path in files],
        },
    )
    return files, False


def _finalize_rendered_png(temp_path: Path | str, destination: Path | str) -> Path:
    """Atomically move a completed same-volume render into the public cache."""
    source = Path(temp_path)
    target = Path(destination)
    try:
        source_stat = source.stat()
    except OSError as exc:
        raise RuntimeError(f"Radar temporary render is unavailable: {source}") from exc
    if not source.is_file() or source_stat.st_size <= 0:
        raise RuntimeError(f"Radar temporary render is empty: {source}")

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target_device = target.parent.stat().st_dev
    except OSError as exc:
        raise RuntimeError(
            f"Radar destination directory is unavailable: {target.parent}"
        ) from exc
    if source_stat.st_dev != target_device:
        raise OSError(
            f"Radar atomic finalization requires one volume: {source} -> {target}"
        )

    os.replace(str(source), str(target))
    return target


def _compute_extent_ratio(bounds: list[float], projection=None) -> float:
    """Return map width/height ratio in projection coordinates.

    bounds: [min_lon, max_lon, min_lat, max_lat]
    projection: cartopy CRS to transform corners into. Defaults to a simple
        cosine-corrected PlateCarree ratio when not provided.
    """
    min_lon, max_lon, min_lat, max_lat = bounds

    if projection is not None:
        corners_ll = np.array(
            [
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
            ]
        )
        try:
            corners_proj = projection.transform_points(
                ccrs.PlateCarree(), corners_ll[:, 0], corners_ll[:, 1]
            )
            xs = corners_proj[:, 0]
            ys = corners_proj[:, 1]
            if np.isfinite(xs).all() and np.isfinite(ys).all():
                width = float(xs.max() - xs.min())
                height = float(ys.max() - ys.min())
                if width > 0 and height > 0:
                    return width / height
        except Exception:
            pass

    lat_span = max(max_lat - min_lat, 1e-6)
    lon_span = max(max_lon - min_lon, 1e-6)
    lat_mid = (min_lat + max_lat) * 0.5
    lon_meters = lon_span * max(math.cos(math.radians(lat_mid)), 1e-3)
    return max(lon_meters / lat_span, 1e-3)


def _figure_size_for_extent(
    bounds: list[float], base_height: float = 7.2, projection=None
) -> tuple[float, float]:
    """Compute figure size from bounds. Returns (width, height) in inches.

    bounds: [min_lon, max_lon, min_lat, max_lat]
    base_height: height in inches (default 7.2 matches radar_utils)
    projection: cartopy CRS used for aspect ratio in projection coordinates.
    """
    ratio = _compute_extent_ratio(bounds, projection=projection)
    fig_height = base_height
    fig_width = max(fig_height * ratio, 4.0)
    return fig_width, fig_height


def _render_overlay_png(
    radar,
    field_name: str,
    bounds: list[float],
    out_path: Path,
    product_code: str,
    product_cfg: dict | None = None,
    sweep: int | None = None,
    profile: bool = False,
    timings: dict[str, float] | None = None,
    render_cache: dict | None = None,
) -> bool:
    if render_cache is not None:
        if sweep is None:
            raise ValueError("Reusable Radar rendering requires an explicit sweep")
        return _render_overlay_png_reusing_mesh(
            radar=radar,
            field_name=field_name,
            bounds=bounds,
            out_path=out_path,
            product_code=product_code,
            product_cfg=product_cfg or {},
            sweep=int(sweep),
            render_cache=render_cache,
        )

    from config.radar_config import LIVE_RADAR_FIGURE_SIZE_INCHES, LIVE_RADAR_RENDER_DPI

    try:
        import pyart

        record_timings = profile or timings is not None
        t_start = time.perf_counter() if record_timings else None

        base_size = float((product_cfg or {}).get("figure_size_inches") or LIVE_RADAR_FIGURE_SIZE_INCHES or 20)
        dpi = int(LIVE_RADAR_RENDER_DPI or 200)
        # Render in Web Mercator (EPSG:3857) so Leaflet (which also uses
        # Web Mercator) can composite the overlay without reprojection
        # distortion that compresses latitude bands.
        map_projection = ccrs.epsg(3857)
        fig_width, fig_height = _figure_size_for_extent(
            bounds, base_height=base_size, projection=map_projection
        )
        fig = plt.figure(figsize=(fig_width, fig_height), dpi=dpi)

        ax = fig.add_axes([0.0, 0.0, 1.0, 1.0], projection=map_projection)
        fig.patch.set_alpha(0.0)
        ax.patch.set_alpha(0.0)
        ax.set_axis_off()
        ax.set_extent(
            [bounds[0], bounds[1], bounds[2], bounds[3]], crs=ccrs.PlateCarree()
        )
        t_fig = time.perf_counter() if record_timings else None

        # Ensure no-data/under-threshold bins render transparent so the overlay
        # does not appear as an opaque square when composited in Leaflet.
        render_cfg = product_cfg or {}
        is_velocity = (
            str(render_cfg.get("mask") or "").lower() == "velocity"
            or product_code in {"N0G", "N0U", "N1U", "N0S", "NVW", "VEL"}
        )
        radar.fields[field_name]["data"] = _prepare_field_data(
            radar.fields[field_name].get("data"),
            product_code,
            render_cfg,
        )
        t_mask = time.perf_counter() if record_timings else None

        display = pyart.graph.RadarMapDisplay(radar)
        from config.radar_colortable_utils import get_radar_colortable as _get_ct

        _pal_key = str(render_cfg.get("palette") or ("BV" if is_velocity else "BR"))
        _vmin = float(render_cfg.get("vmin", -120.0 if is_velocity else -30.0))
        _vmax = float(render_cfg.get("vmax", 120.0 if is_velocity else 90.0))
        _ct = _get_ct(_pal_key, _vmin, _vmax)
        cmap = _ct["cmap"]
        vmin = _vmin
        vmax = _vmax
        sweep = _best_sweep(radar, field_name) if sweep is None else int(sweep)
        t_sweep = time.perf_counter() if record_timings else None

        display.plot_ppi_map(
            field_name,
            sweep=sweep,
            ax=ax,
            projection=map_projection,
            min_lon=bounds[0],
            max_lon=bounds[1],
            min_lat=bounds[2],
            max_lat=bounds[3],
            embellish=False,
            add_grid_lines=False,
            colorbar_flag=False,
            title_flag=False,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            edgecolors="face",
            linewidths=0,
        )
        t_plot = time.perf_counter() if record_timings else None

        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            str(out_path),
            format="png",
            dpi=dpi,
            transparent=True,
            pad_inches=0,
            # Lossless; level 1 encodes ~3-4x faster than the default 6 at the
            # cost of larger files, which is fine for a local disk cache.
            pil_kwargs={"compress_level": 1},
        )
        t_save = time.perf_counter() if record_timings else None

        plt.close(fig)
        t_close = time.perf_counter() if record_timings else None

        if timings is not None and t_start is not None:
            timings.update(
                {
                    "figure_ms": (t_fig - t_start) * 1000.0,
                    "field_ms": (t_mask - t_fig) * 1000.0,
                    "sweep_ms": (t_sweep - t_mask) * 1000.0,
                    "plot_ms": (t_plot - t_sweep) * 1000.0,
                    "encode_ms": (t_save - t_plot) * 1000.0,
                    "close_ms": (t_close - t_save) * 1000.0,
                    "render_ms": (t_close - t_start) * 1000.0,
                }
            )

        if profile and t_start:
            print(f"[PROFILE] Render {out_path.name}:")
            print(f"  Figure setup: {(t_fig - t_start)*1000:.1f}ms")
            print(f"  Data masking: {(t_mask - t_fig)*1000:.1f}ms")
            print(f"  Sweep select: {(t_sweep - t_mask)*1000:.1f}ms")
            print(f"  PPI plot: {(t_plot - t_sweep)*1000:.1f}ms")
            print(f"  Save PNG: {(t_save - t_plot)*1000:.1f}ms")
            print(f"  Close fig: {(t_close - t_save)*1000:.1f}ms")
            print(f"  TOTAL: {(t_close - t_start)*1000:.1f}ms")

        return out_path.exists() and out_path.stat().st_size > 0
    except Exception as exc:
        print(f"[radar_live_worker] render failed: {type(exc).__name__}: {exc}")
        try:
            plt.close("all")
        except Exception:
            pass
        return False


def _render_overlay_png_reusing_mesh(
    radar,
    field_name: str,
    bounds: list[float],
    out_path: Path,
    product_code: str,
    product_cfg: dict,
    sweep: int,
    render_cache: dict,
) -> bool:
    """Reuse one same-volume QuadMesh for products sharing a selected sweep."""
    from config.radar_config import LIVE_RADAR_FIGURE_SIZE_INCHES, LIVE_RADAR_RENDER_DPI

    cache_key = None
    figure = None
    try:
        import pyart

        base_size = float(
            product_cfg.get("figure_size_inches")
            or LIVE_RADAR_FIGURE_SIZE_INCHES
            or 20
        )
        dpi = int(LIVE_RADAR_RENDER_DPI or 200)
        map_projection = ccrs.epsg(3857)
        fig_width, fig_height = _figure_size_for_extent(
            bounds, base_height=base_size, projection=map_projection
        )

        is_velocity = (
            str(product_cfg.get("mask") or "").lower() == "velocity"
            or product_code in {"N0G", "N0U", "N1U", "N0S", "NVW", "VEL"}
        )
        radar.fields[field_name]["data"] = _prepare_field_data(
            radar.fields[field_name].get("data"),
            product_code,
            product_cfg,
        )
        from config.radar_colortable_utils import get_radar_colortable as _get_ct

        palette_key = str(
            product_cfg.get("palette") or ("BV" if is_velocity else "BR")
        )
        vmin = float(
            product_cfg.get("vmin", -120.0 if is_velocity else -30.0)
        )
        vmax = float(product_cfg.get("vmax", 120.0 if is_velocity else 90.0))
        cmap = _get_ct(palette_key, vmin, vmax)["cmap"]

        cache_key = (int(sweep), float(fig_width), float(fig_height), dpi)
        cached = render_cache.get(cache_key)
        if cached is None:
            figure = plt.figure(figsize=(fig_width, fig_height), dpi=dpi)
            ax = figure.add_axes(
                [0.0, 0.0, 1.0, 1.0], projection=map_projection
            )
            figure.patch.set_alpha(0.0)
            ax.patch.set_alpha(0.0)
            ax.set_axis_off()
            ax.set_extent(
                [bounds[0], bounds[1], bounds[2], bounds[3]],
                crs=ccrs.PlateCarree(),
            )
            display = pyart.graph.RadarMapDisplay(radar)
            display.plot_ppi_map(
                field_name,
                sweep=int(sweep),
                ax=ax,
                projection=map_projection,
                min_lon=bounds[0],
                max_lon=bounds[1],
                min_lat=bounds[2],
                max_lat=bounds[3],
                embellish=False,
                add_grid_lines=False,
                colorbar_flag=False,
                title_flag=False,
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
                edgecolors="face",
                linewidths=0,
            )
            cached = {
                "figure": figure,
                "display": display,
                "mesh": display.plots[-1],
            }
            render_cache[cache_key] = cached
        else:
            # Geometry, projection, extent, DPI, and sweep are unchanged.
            # Only the masked field values and their configured color mapping
            # differ between same-volume product consumers.
            display = cached["display"]
            mesh = cached["mesh"]
            plot_data = display._get_data(
                field_name,
                int(sweep),
                None,
                True,
                None,
            )
            mesh.set_array(plot_data)
            mesh.set_cmap(cmap)
            mesh.set_clim(vmin, vmax)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        cached["figure"].savefig(
            str(out_path),
            format="png",
            dpi=dpi,
            transparent=True,
            pad_inches=0,
            pil_kwargs={"compress_level": 1},
        )
        return True
    except Exception as exc:
        cached = render_cache.pop(cache_key, None)
        figure_to_close = cached["figure"] if cached is not None else figure
        if figure_to_close is not None:
            try:
                plt.close(figure_to_close)
            except Exception:
                pass
        print(
            f"[radar_live_worker] Reusable Radar render failed for "
            f"{out_path.name}: {exc}"
        )
        return False


def _close_reusable_overlay_cache(render_cache: dict) -> None:
    for cached in render_cache.values():
        try:
            plt.close(cached["figure"])
        except Exception:
            pass
    render_cache.clear()


def _render_single_frame_worker(
    src_file_path: str,
    level: str,
    product_code: str,
    bounds: list[float],
    temp_render_path: str,
    product_cfg: dict,
    elevation: str,
    site: str,
) -> tuple[bool, str, str, list[float], float | None]:
    """Worker function for parallel frame rendering. Returns (success, source_key, frame_key or error)."""
    try:
        src_file = Path(src_file_path)
        source_key = src_file.name

        radar = _read_radar(level, str(src_file))
        available_fields = list(getattr(radar, "fields", {}).keys())
        field_name = _field_for_product(
            level, product_code, available_fields, product_cfg
        )
        if not field_name:
            return (False, source_key, "no_field", [], None)
        field_name = _ensure_derived_field(radar, field_name, product_cfg)

        frame_dt = _frame_dt_from_radar(radar, src_file)
        if frame_dt is None:
            return (False, source_key, "no_timestamp", [], None)

        frame_key = frame_key_from_datetime(frame_dt)
        sweep, available_elevations, selected_elevation = _select_sweep(
            radar, field_name, elevation
        )
        success = _render_overlay_png(
            radar=radar,
            field_name=field_name,
            bounds=bounds,
            out_path=Path(temp_render_path),
            product_code=product_code,
            product_cfg=product_cfg,
            sweep=sweep,
            profile=False,
        )

        if success:
            _publish_webgl_artifact(
                site,
                product_code,
                frame_key,
                selected_elevation,
                radar,
                field_name,
                sweep,
                product_cfg,
            )
            return (
                True,
                source_key,
                frame_key,
                available_elevations,
                selected_elevation,
            )
        else:
            return (False, source_key, "render_failed", [], None)
    except Exception as exc:
        return (False, src_file_path, f"error: {type(exc).__name__}", [], None)


def _publish_webgl_artifact(
    site: str,
    product_code: str,
    frame_key: str,
    selected_elevation: str | float | None,
    radar,
    field_name: str,
    sweep: int,
    product_cfg: dict,
) -> Path | None:
    """Publish the optional L2 REF artifact without affecting PNG success."""
    if str(product_code).upper() != "REF":
        return None
    try:
        return write_artifact(
            _CACHE_ROOT,
            site,
            frame_key,
            selected_elevation,
            radar,
            field_name,
            sweep,
            product_cfg,
        )
    except Exception as exc:
        print(
            f"[radar_live_worker] WebGL artifact skipped for "
            f"{site}/{frame_key}: {type(exc).__name__}: {exc}"
        )
        return None


def _consume_decoded_l2_volume(
    radar,
    src_file: Path,
    bounds: list[float],
    product_requests: list[dict],
) -> list[dict]:
    """Render bounded product consumers from one already-decoded Level II volume."""
    frame_dt = _frame_dt_from_radar(radar, src_file)
    if frame_dt is None:
        return [
            {
                "success": False,
                "product_key": request["product_key"],
                "error": "no_timestamp",
            }
            for request in product_requests
        ]

    frame_key = frame_key_from_datetime(frame_dt)
    available_fields = list(getattr(radar, "fields", {}).keys())
    results = []
    reusable_render_cache = {}
    for request in product_requests:
        product_key = request["product_key"]
        product_code = request["product_code"]
        product_cfg = request["product_cfg"]
        try:
            field_name = _field_for_product(
                "Level 2", product_code, available_fields, product_cfg
            )
            if not field_name:
                raise ValueError("Radar field is unavailable for product.")
            field_name = _ensure_derived_field(radar, field_name, product_cfg)
            sweep, available_elevations, selected_elevation = _select_sweep(
                radar, field_name, request["elevation"]
            )
            original_field_data = radar.fields[field_name].get("data")
            try:
                render_kwargs = {
                    "radar": radar,
                    "field_name": field_name,
                    "bounds": bounds,
                    "out_path": Path(request["temp_render_path"]),
                    "product_code": product_code,
                    "product_cfg": product_cfg,
                    "sweep": sweep,
                }
                success = _render_overlay_png(
                    **render_kwargs,
                    profile=False,
                    render_cache=reusable_render_cache,
                )
                if success:
                    _publish_webgl_artifact(
                        request.get("site", ""),
                        product_code,
                        frame_key,
                        selected_elevation,
                        radar,
                        field_name,
                        sweep,
                        product_cfg,
                    )
            finally:
                radar.fields[field_name]["data"] = original_field_data
            if not success:
                raise RuntimeError("render_failed")
            results.append(
                {
                    "success": True,
                    "product_key": product_key,
                    "frame_key": frame_key,
                    "available_elevations": available_elevations,
                    "selected_elevation": selected_elevation,
                    "temp_render_path": request["temp_render_path"],
                }
            )
        except Exception as exc:
            results.append(
                {
                    "success": False,
                    "product_key": product_key,
                    "error": f"{type(exc).__name__}: {exc}",
                    "temp_render_path": request["temp_render_path"],
                }
            )
    _close_reusable_overlay_cache(reusable_render_cache)
    return results


def _render_l2_volume_products_worker(
    src_file_path: str,
    bounds: list[float],
    product_requests: list[dict],
) -> tuple[str, list[dict]]:
    """Decode one Level II source once and isolate each product consumer."""
    src_file = Path(src_file_path)
    try:
        radar = _read_radar("Level 2", str(src_file))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        return (
            src_file.name,
            [
                {
                    "success": False,
                    "product_key": request["product_key"],
                    "error": error,
                }
                for request in product_requests
            ],
        )
    return (
        src_file.name,
        _consume_decoded_l2_volume(radar, src_file, bounds, product_requests),
    )


def _units_for_product(
    product_key: str, product_code: str, product_cfg: dict | None = None
) -> str:
    configured_units = str((product_cfg or {}).get("units") or "").strip()
    if configured_units:
        return configured_units
    token = (str(product_key).upper(), str(product_code).upper())
    if any("VEL" in item for item in token) or token[1] in {
        "N0G",
        "N0U",
        "N1U",
        "N0S",
        "NVW",
    }:
        return "kt"
    if token[1] in {"DTA", "DPA", "DAA", "DHR", "DPR", "N1P", "NTP", "NRR"}:
        return "in"
    return "dBZ"


def _level_code(level: str) -> str:
    """Map a product-level string ('Level 2' / 'Level 3') to a short code ('L2'/'L3')."""
    return "L2" if "2" in str(level) else "L3"


def _render_site_product(
    radar_data_utils,
    source_label: str,
    site: str,
    product_key: str,
    product_cfg: dict,
    latest_only: bool = False,
    newest_first: bool = False,
    max_render_frames: int | None = None,
    elevation: str = "auto",
    use_mtime_key: bool = False,
    lookback_hours: float | None = None,
    render_pool=None,
) -> int:
    """Render and cache frames for one site/product. Returns number of frames cached."""
    level = str(product_cfg.get("level") or "Level 3")
    level_code = _level_code(level)
    product_code = str(product_cfg.get("product") or "N0B").upper()
    source_product_code = _source_product_code(product_code, product_cfg)
    product_label = str(product_cfg.get("label") or product_key)
    cache_product_key = _radar_cache_product_key(product_key, elevation, product_cfg)

    provider = "aws"
    kwargs = {}
    if radar_data_utils.__name__.endswith("radar_nodd_utils"):
        kwargs["provider"] = provider
        kwargs["newest_first"] = newest_first
        kwargs["max_new_files"] = max_render_frames

    requested_lookback = normalize_live_radar_lookback_hours(
        LIVE_RADAR_LOOKBACK_HOURS if lookback_hours is None else lookback_hours
    )
    source_context = (
        _l2_source_lock(site)
        if level_code == "L2"
        and radar_data_utils.__name__.endswith("radar_nodd_utils")
        else nullcontext()
    )
    with source_context:
        data_dir, total_files, _downloaded = radar_data_utils.download_radar_data(
            level,
            site,
            source_product_code,
            requested_lookback,
            str(_RADAR_ROOT),
            latest_only=latest_only,
            **kwargs,
        )

    if not data_dir or int(total_files or 0) <= 0:
        return 0

    data_path = Path(data_dir)

    radar_files, _discovery_reused = _discover_radar_files_cached(
        data_path,
        site,
        level_code,
        product_key,
    )

    if not radar_files:
        return 0

    bounds = _site_bounds(site)
    if not bounds:
        return 0

    target_n = live_radar_target_frames(requested_lookback)
    existing_count = len(
        radar_list_frames(str(_CACHE_ROOT), site, level_code, cache_product_key)
    )
    keep_n = min(
        int(LIVE_RADAR_MAX_KEEP_FRAMES),
        max(int(LIVE_RADAR_KEEP_FRAMES or 30), target_n, existing_count),
    )
    selected_files = radar_files[-(1 if latest_only else target_n):]
    if newest_first:
        selected_files = list(reversed(selected_files))

    # Load dedup tracking for this product.
    processed_keys = radar_read_processed_keys(
        str(_CACHE_ROOT), site, level_code, cache_product_key
    )

    cached = 0
    read_failures = 0
    _TMP_RENDER_ROOT.mkdir(parents=True, exist_ok=True)

    # Filter out already-processed files. Chunk-assembled files use mtime in the
    # key so a partial scan that is re-assembled (new mtime) gets re-rendered.
    unprocessed_files = [
        f for f in selected_files
        if _file_key(f, use_mtime_key) not in processed_keys
    ]
    if max_render_frames is not None:
        unprocessed_files = unprocessed_files[: max(1, int(max_render_frames))]
    if not unprocessed_files:
        return 0

    # Determine if we should use parallel rendering
    num_workers = _radar_parallel_worker_count()
    use_parallel = len(unprocessed_files) > 1 and num_workers != 1

    if use_parallel:
        print(
            f"[radar_live_worker] {site}/{product_key}: "
            f"rendering {len(unprocessed_files)} frames in parallel ({num_workers} workers)"
        )

        # Prepare work items for parallel processing.
        # file_key_map lets us use the correct processed_keys entry (which may
        # include mtime for chunk-assembled files) after the pool returns.
        work_items = []
        file_key_map: dict[str, str] = {}  # src_file.name → processed_keys entry
        for src_file in unprocessed_files:
            frame_dt = _frame_dt_from_radar_file_lazy(src_file)
            if not frame_dt:
                read_failures += 1
                continue
            file_key_map[src_file.name] = _file_key(src_file, use_mtime_key)
            frame_key = frame_key_from_datetime(frame_dt)
            temp_render_path = str(
                _TMP_RENDER_ROOT / f"{site}_{cache_product_key}_{frame_key}.png"
            )
            work_items.append(
                (
                    str(src_file),
                    level,
                    product_code,
                    bounds,
                    temp_render_path,
                    product_cfg,
                    elevation,
                    site,
                )
            )

        # Render in parallel. Scheduled/background owners can retain the same
        # bounded pool across batches; direct callers still get one local pool.
        if render_pool is None:
            with _radar_render_pool_owner(num_workers) as owned_pool:
                results = owned_pool.starmap(_render_single_frame_worker, work_items)
        else:
            results = render_pool.starmap(_render_single_frame_worker, work_items)

        # Process results
        frame_data = {}
        for success, source_key, result_info, available_elevations, selected_elevation in results:
            if success:
                frame_key = result_info
                temp_render_path = str(
                    _TMP_RENDER_ROOT / f"{site}_{cache_product_key}_{frame_key}.png"
                )
                frame_data[source_key] = (
                    frame_key,
                    temp_render_path,
                    available_elevations,
                    selected_elevation,
                )
            else:
                read_failures += 1

        # Atomically publish files and update the index serially.
        for source_key, (
            frame_key,
            temp_render_path,
            available_elevations,
            selected_elevation,
        ) in frame_data.items():
            try:
                dest_image = Path(
                    radar_overlay_image_path(
                        str(_CACHE_ROOT), site, level_code, cache_product_key, frame_key
                    )
                )
                _finalize_rendered_png(temp_render_path, dest_image)

                processed_keys.add(file_key_map.get(source_key, source_key))
                radar_update_index(
                    str(_CACHE_ROOT),
                    site,
                    level_code,
                    cache_product_key,
                    frame_key,
                    bounds=bounds,
                    full_name=product_label,
                    units=_units_for_product(product_key, product_code, product_cfg),
                    data_key=source_key,
                    available_elevations=available_elevations,
                    selected_elevation=selected_elevation,
                )
                if product_key == "L2_REF":
                    prune_artifacts(_CACHE_ROOT, site, selected_elevation, keep_n)
                cached += 1
            except Exception as exc:
                print(f"[radar_live_worker] Failed to finalize {frame_key}: {exc}")
            finally:
                try:
                    Path(temp_render_path).unlink(missing_ok=True)
                except Exception:
                    pass
    else:
        # Sequential rendering (original behavior)
        profile_first_frame = True
        for src_file in unprocessed_files:
            source_key = _file_key(src_file, use_mtime_key)
            t_frame_start = time.time()

            try:
                t_read_start = time.time()
                radar = _read_radar(level, str(src_file))
                t_read = time.time() - t_read_start
            except Exception:
                read_failures += 1
                continue

            available_fields = list(getattr(radar, "fields", {}).keys())
            field_name = _field_for_product(
                level, product_code, available_fields, product_cfg
            )
            if not field_name:
                continue
            field_name = _ensure_derived_field(radar, field_name, product_cfg)

            frame_dt = _frame_dt_from_radar(radar, src_file)
            if frame_dt is None:
                continue

            frame_key = frame_key_from_datetime(frame_dt)
            temp_render = (
                _TMP_RENDER_ROOT / f"{site}_{cache_product_key}_{frame_key}.png"
            )
            sweep, available_elevations, selected_elevation = _select_sweep(
                radar, field_name, elevation
            )

            should_profile = profile_first_frame and latest_only
            if not _render_overlay_png(
                radar=radar,
                field_name=field_name,
                bounds=bounds,
                out_path=temp_render,
                product_code=product_code,
                product_cfg=product_cfg,
                sweep=sweep,
                profile=should_profile,
            ):
                continue
            _publish_webgl_artifact(
                site,
                product_code,
                frame_key,
                selected_elevation,
                radar,
                field_name,
                sweep,
                product_cfg,
            )

            try:
                t_finalize_start = time.time()
                dest_image = Path(
                    radar_overlay_image_path(
                        str(_CACHE_ROOT),
                        site,
                        level_code,
                        cache_product_key,
                        frame_key,
                    )
                )
                _finalize_rendered_png(temp_render, dest_image)
                t_finalize = time.time() - t_finalize_start

                t_index_start = time.time()
                processed_keys.add(source_key)
                radar_update_index(
                    str(_CACHE_ROOT),
                    site,
                    level_code,
                    cache_product_key,
                    frame_key,
                    bounds=bounds,
                    full_name=product_label,
                    units=_units_for_product(
                        product_key, product_code, product_cfg
                    ),
                    data_key=source_key,
                    available_elevations=available_elevations,
                    selected_elevation=selected_elevation,
                )
                t_index = time.time() - t_index_start

                t_frame_total = time.time() - t_frame_start
                if should_profile:
                    print(f"[PROFILE] Frame {frame_key} ({site}/{product_key}):")
                    print(f"  Read radar file: {t_read*1000:.1f}ms")
                    print("  Render to PNG: (see above)")
                    print(f"  Atomic finalize: {t_finalize*1000:.1f}ms")
                    print(f"  Update index: {t_index*1000:.1f}ms")
                    print(f"  FRAME TOTAL: {t_frame_total*1000:.1f}ms")
                    profile_first_frame = False

                if product_key == "L2_REF":
                    prune_artifacts(_CACHE_ROOT, site, selected_elevation, keep_n)
                cached += 1
            except Exception as exc:
                processed_keys.discard(source_key)
                print(
                    f"[radar_live_worker] Failed to finalize {frame_key}: {exc}"
                )
            finally:
                try:
                    temp_render.unlink(missing_ok=True)
                except Exception:
                    pass

    if read_failures:
        print(
            f"[radar_live_worker] {site}/{product_key} skipped unreadable files: {read_failures}"
        )

    radar_write_processed_keys(
        str(_CACHE_ROOT), site, level_code, cache_product_key, processed_keys, keep_n
    )
    radar_prune_frames(
        str(_CACHE_ROOT), site, level_code, cache_product_key, keep_n=keep_n
    )
    return cached


def _render_site_l2_products(
    radar_data_utils,
    site: str,
    products: list[tuple[str, dict]],
    *,
    elevation: str,
    render_pool=None,
) -> tuple[int, int]:
    """Download/list once and decode each Level II frame once for all products."""
    if not products:
        return 0, 0
    if len(products) > _MAX_L2_VOLUME_CONSUMERS:
        raise ValueError(
            f"Level II product batch exceeds {_MAX_L2_VOLUME_CONSUMERS} consumers"
        )

    requested_lookback = normalize_live_radar_lookback_hours(
        LIVE_RADAR_LOOKBACK_HOURS
    )
    first_cfg = products[0][1]
    source_product_code = _source_product_code(
        str(first_cfg.get("product") or "REF"), first_cfg
    )
    with _l2_source_lock(site):
        data_dir, total_files, _downloaded = radar_data_utils.download_radar_data(
            "Level 2",
            site,
            source_product_code,
            requested_lookback,
            str(_RADAR_ROOT),
            latest_only=False,
            provider="aws",
            newest_first=False,
            max_new_files=None,
        )
    if not data_dir or int(total_files or 0) <= 0:
        return 0, 0

    data_path = Path(data_dir)
    radar_files, _discovery_reused = _discover_radar_files_cached(
        data_path,
        site,
        "L2",
        "_VOLUME",
    )
    bounds = _site_bounds(site)
    if not radar_files or not bounds:
        return 0, 0

    target_n = live_radar_target_frames(requested_lookback)
    selected_files = radar_files[-target_n:]
    states: dict[str, dict] = {}
    for product_key, product_cfg in products:
        product_code = str(product_cfg.get("product") or "REF").upper()
        cache_product_key = _radar_cache_product_key(
            product_key, elevation, product_cfg
        )
        existing_count = len(
            radar_list_frames(str(_CACHE_ROOT), site, "L2", cache_product_key)
        )
        keep_n = min(
            int(LIVE_RADAR_MAX_KEEP_FRAMES),
            max(int(LIVE_RADAR_KEEP_FRAMES or 30), target_n, existing_count),
        )
        states[product_key] = {
            "product_cfg": product_cfg,
            "product_code": product_code,
            "product_label": str(product_cfg.get("label") or product_key),
            "cache_product_key": cache_product_key,
            "processed_keys": radar_read_processed_keys(
                str(_CACHE_ROOT), site, "L2", cache_product_key
            ),
            "keep_n": keep_n,
            "cached": 0,
        }

    work_items = []
    for src_file in selected_files:
        source_key = _file_key(src_file, False)
        requests = []
        for product_key, state in states.items():
            if source_key in state["processed_keys"]:
                continue
            cache_product_key = state["cache_product_key"]
            requests.append(
                {
                    "site": site,
                    "product_key": product_key,
                    "product_code": state["product_code"],
                    "product_cfg": state["product_cfg"],
                    "elevation": elevation,
                    "temp_render_path": str(
                        _TMP_RENDER_ROOT
                        / f"{site}_{cache_product_key}_{src_file.name}.png"
                    ),
                }
            )
        if requests:
            work_items.append((str(src_file), bounds, requests))
    if not work_items:
        return 0, 0

    _TMP_RENDER_ROOT.mkdir(parents=True, exist_ok=True)
    num_workers = _radar_parallel_worker_count()
    if len(work_items) > 1 and num_workers != 1:
        if render_pool is None:
            with _radar_render_pool_owner(num_workers) as owned_pool:
                batch_results = owned_pool.starmap(
                    _render_l2_volume_products_worker, work_items
                )
        else:
            batch_results = render_pool.starmap(
                _render_l2_volume_products_worker, work_items
            )
    else:
        batch_results = [
            _render_l2_volume_products_worker(*work_item) for work_item in work_items
        ]

    failed_products = set()
    for source_key, product_results in batch_results:
        for result in product_results:
            product_key = result["product_key"]
            state = states[product_key]
            temp_render_path = result.get("temp_render_path")
            try:
                if not result.get("success"):
                    failed_products.add(product_key)
                    continue
                frame_key = result["frame_key"]
                dest_image = Path(
                    radar_overlay_image_path(
                        str(_CACHE_ROOT),
                        site,
                        "L2",
                        state["cache_product_key"],
                        frame_key,
                    )
                )
                _finalize_rendered_png(temp_render_path, dest_image)
                state["processed_keys"].add(source_key)
                radar_update_index(
                    str(_CACHE_ROOT),
                    site,
                    "L2",
                    state["cache_product_key"],
                    frame_key,
                    bounds=bounds,
                    full_name=state["product_label"],
                    units=_units_for_product(
                        product_key,
                        state["product_code"],
                        state["product_cfg"],
                    ),
                    data_key=source_key,
                    available_elevations=result["available_elevations"],
                    selected_elevation=result["selected_elevation"],
                )
                if product_key == "L2_REF":
                    prune_artifacts(
                        _CACHE_ROOT,
                        site,
                        result["selected_elevation"],
                        state["keep_n"],
                    )
                state["cached"] += 1
            except Exception as exc:
                failed_products.add(product_key)
                print(
                    f"[radar_live_worker] Failed to finalize "
                    f"{site}/{product_key}/{result.get('frame_key')}: {exc}"
                )
            finally:
                if temp_render_path:
                    try:
                        Path(temp_render_path).unlink(missing_ok=True)
                    except Exception:
                        pass

    total_cached = 0
    for product_key, state in states.items():
        radar_write_processed_keys(
            str(_CACHE_ROOT),
            site,
            "L2",
            state["cache_product_key"],
            state["processed_keys"],
            state["keep_n"],
        )
        radar_prune_frames(
            str(_CACHE_ROOT),
            site,
            "L2",
            state["cache_product_key"],
            keep_n=state["keep_n"],
        )
        total_cached += int(state["cached"])
    return total_cached, len(failed_products)


def _run_radar_live_worker_unbounded(
    force: bool = False,
    *,
    render_pool=None,
) -> None:
    """Render configured site/product live radar overlays into cache.

    L2 products (chunks): run every invocation — the task fires every minute
    and each run is cheap (only new chunks downloaded, complete scans skipped).

    L3 products (NODD): gated by radar_live_l3 freshness so they only
    re-download/re-render on the original 5-minute cadence even though the
    task fires more often.
    """
    run_l3 = force or not is_cache_fresh("radar_live_l3", _L3_FRESH_WINDOW_SEC)

    total_cached = 0
    total_failed = 0
    for site in LIVE_RADAR_SITES:
        site_id = str(site).strip().upper()
        if not site_id:
            continue
        l2_products = [
            (str(product_key), product_cfg)
            for product_key, product_cfg in LIVE_RADAR_PRODUCTS.items()
            if _level_code(str(product_cfg.get("level") or "Level 3")) == "L2"
        ]
        l2_batched = False
        if l2_products:
            l2_utils = _resolve_radar_data_utils(l2_products[0][0])
            if not _is_chunks_utils(l2_utils):
                l2_batched = True
                try:
                    cached, failed = _render_site_l2_products(
                        l2_utils,
                        site_id,
                        l2_products,
                        elevation=LIVE_RADAR_L2_DEFAULT_ELEVATION,
                        render_pool=render_pool,
                    )
                    total_cached += int(cached)
                    total_failed += int(failed)
                except Exception as exc:
                    total_failed += len(l2_products)
                    print(
                        f"[radar_live_worker] {site_id}/Level II batch failed: "
                        f"{type(exc).__name__}: {exc}"
                    )

        for product_key, product_cfg in LIVE_RADAR_PRODUCTS.items():
            level = str(product_cfg.get("level") or "Level 3")
            is_l2 = "2" in str(level)

            if is_l2 and l2_batched:
                continue
            if not is_l2 and not run_l3:
                continue

            radar_data_utils = _resolve_radar_data_utils(str(product_key))
            use_mtime = _is_chunks_utils(radar_data_utils)
            source_label = "NODD-Chunks" if use_mtime else "NODD-AWS"

            try:
                cached = _render_site_product(
                    radar_data_utils,
                    source_label,
                    site_id,
                    str(product_key),
                    product_cfg,
                    elevation=LIVE_RADAR_L2_DEFAULT_ELEVATION if is_l2 else "auto",
                    use_mtime_key=use_mtime,
                    render_pool=render_pool,
                )
                total_cached += int(cached)
            except Exception as exc:
                total_failed += 1
                print(
                    f"[radar_live_worker] {site_id}/{product_key} failed: "
                    f"{type(exc).__name__}: {exc}"
                )

    print(f"[radar_live_worker] completed - cached frames: {total_cached}")

    if total_failed and not total_cached:
        print("[radar_live_worker] All renders failed - cache not marked fresh")
    else:
        mark_run_complete("radar_live")
        if run_l3:
            mark_run_complete("radar_live_l3")


def run_radar_live_worker(force: bool = False) -> None:
    from app_core.render_budget import heavy_render_slot

    with heavy_render_slot():
        with _radar_render_pool_owner() as render_pool:
            _run_radar_live_worker_unbounded(
                force=force,
                render_pool=render_pool,
            )


def _run_radar_live_site_product_unbounded(
    site: str,
    product_key: str,
    force: bool = True,
    latest_only: bool = False,
    newest_first: bool = False,
    max_render_frames: int | None = None,
    elevation: str = "auto",
    storm_motion: dict | None = None,
    lookback_hours: float | None = None,
    render_pool=None,
) -> int:
    """Render and cache frames for a single live radar site/product pair.

    This is used by API cache-miss fallback paths. Product validation remains
    restricted to configured LIVE_RADAR_PRODUCTS keys.
    """
    site_id = str(site or "").strip().upper()
    normalized_product = str(product_key or "").strip().upper()
    if not site_id:
        raise ValueError("site is required")
    if not normalized_product:
        raise ValueError("product_key is required")

    product_cfg = LIVE_RADAR_PRODUCTS.get(normalized_product)
    if not product_cfg:
        raise ValueError(f"Unknown live radar product: {normalized_product}")
    product_cfg = _product_cfg_with_storm_motion(
        normalized_product, product_cfg, storm_motion
    )

    level = str(product_cfg.get("level") or "Level 3")
    is_l2 = "2" in str(level)

    # L3 respects freshness gate; L2 chunks always run (cheap per-call cost)
    if not force and not is_l2 and is_cache_fresh("radar_live_l3", _L3_FRESH_WINDOW_SEC):
        return 0

    radar_data_utils = _resolve_radar_data_utils(normalized_product)
    use_mtime = _is_chunks_utils(radar_data_utils)
    cached = _render_site_product(
        radar_data_utils,
        "NODD-Chunks" if use_mtime else "NODD-AWS",
        site_id,
        normalized_product,
        product_cfg,
        latest_only=latest_only,
        newest_first=newest_first,
        max_render_frames=max_render_frames,
        elevation=elevation,
        use_mtime_key=use_mtime,
        lookback_hours=lookback_hours,
        render_pool=render_pool,
    )
    if cached > 0:
        mark_run_complete("radar_live")
    return int(cached)


def run_radar_live_site_product(
    site: str,
    product_key: str,
    force: bool = True,
    latest_only: bool = False,
    newest_first: bool = False,
    max_render_frames: int | None = None,
    elevation: str = "auto",
    storm_motion: dict | None = None,
    lookback_hours: float | None = None,
) -> int:
    from app_core.render_budget import heavy_render_slot

    with heavy_render_slot():
        with _radar_render_pool_owner() as render_pool:
            return _run_radar_live_site_product_unbounded(
                site,
                product_key,
                force=force,
                latest_only=latest_only,
                newest_first=newest_first,
                max_render_frames=max_render_frames,
                elevation=elevation,
                storm_motion=storm_motion,
                lookback_hours=lookback_hours,
                render_pool=render_pool,
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the radar live worker once.")
    parser.add_argument("--force", action="store_true", help="Bypass freshness gate.")
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to logs/scheduled/radar_live.log",
    )
    args = parser.parse_args()

    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("radar_live")

    run_radar_live_worker(force=args.force)
