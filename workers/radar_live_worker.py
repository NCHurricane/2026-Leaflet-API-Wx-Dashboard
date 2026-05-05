"""Background worker for live radar overlays (weather tab).

This worker pulls recent NEXRAD files from NODD (AWS), renders transparent PNG
overlays per configured site/product, and writes metadata using the shared
overlay cache schema.
"""

from __future__ import annotations

import math
import shutil
import zlib
from datetime import datetime, timezone
from pathlib import Path

import cartopy.crs as ccrs
import matplotlib
import numpy as np

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from cache.overlay_cache_utils import (
    frame_key_from_datetime,
    radar_overlay_image_path,
    radar_prune_frames,
    radar_read_processed_keys,
    radar_update_index,
    radar_write_processed_keys,
)
from config.radar_config import (
    LIVE_RADAR_KEEP_FRAMES,
    LIVE_RADAR_LOOKBACK_HOURS,
    LIVE_RADAR_PRODUCTS,
    LIVE_RADAR_SITES,
    LIVE_RADAR_WORKER_INTERVAL_MIN,
)
from workers._freshness import is_cache_fresh, mark_run_complete

_CACHE_ROOT = Path(__file__).resolve().parent.parent / "cache"
_RADAR_ROOT = _CACHE_ROOT / "radar" / "live"
_TMP_RENDER_ROOT = _CACHE_ROOT / "tmp" / "radar_live"

# Skip if a successful run happened within 75% of configured interval.
_FRESH_WINDOW_SEC = max(60, int(LIVE_RADAR_WORKER_INTERVAL_MIN * 60 * 0.75))

# Radar map bounds use 100 nm range rings with 20% padding.
_MAX_RANGE_NM = 100.0
_NM_TO_KM = 1.852
_KM_PER_DEG_LAT = 111.32
_PADDING_FACTOR = 1.20


def _resolve_radar_data_utils():
    from radar import radar_nodd_utils as radar_data_utils

    return radar_data_utils


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


def _read_level3_file(file_path: str):
    import pyart

    try:
        return pyart.io.read_nexrad_level3(file_path)
    except (NotImplementedError, ValueError, AssertionError):
        with open(file_path, "rb") as fh:
            raw = fh.read()
        zlib_start = -1
        for magic in (b"\x78\xda", b"\x78\x9c", b"\x78\x01"):
            zlib_start = raw.find(magic, 0, 128)
            if zlib_start != -1:
                break
        if zlib_start == -1:
            raise
        decompressor = zlib.decompressobj()
        header_block = decompressor.decompress(raw[zlib_start:])
        full_nids = header_block + decompressor.unused_data
        temp_path = Path(file_path).with_suffix(".nids")
        temp_path.write_bytes(full_nids)
        try:
            return pyart.io.read_nexrad_level3(str(temp_path))
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


def _field_for_product(
    level: str, product_code: str, available_fields: list[str]
) -> str | None:
    if not available_fields:
        return None
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


def _discover_radar_files(data_path: Path) -> list[Path]:
    files: list[Path] = []
    ignored_suffixes = (".tmp", ".part", ".json", ".txt", ".md", ".idx", ".lock")
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


def _render_overlay_png(
    radar,
    field_name: str,
    bounds: list[float],
    out_path: Path,
    product_code: str,
) -> bool:
    try:
        import pyart

        fig = plt.figure(figsize=(8, 8), dpi=150)
        ax = fig.add_axes([0.0, 0.0, 1.0, 1.0], projection=ccrs.PlateCarree())
        fig.patch.set_alpha(0.0)
        ax.patch.set_alpha(0.0)
        ax.set_axis_off()
        ax.set_extent(
            [bounds[0], bounds[1], bounds[2], bounds[3]], crs=ccrs.PlateCarree()
        )

        # Ensure no-data/under-threshold bins render transparent so the overlay
        # does not appear as an opaque square when composited in Leaflet.
        field_data = np.ma.array(radar.fields[field_name].get("data"))

        is_velocity = product_code in {"N0G", "N0U", "N1U", "N0S", "NVW", "VEL"}
        if is_velocity:
            # Velocity no-data bins are typically encoded near the extremes.
            invalid = ~np.isfinite(field_data) | (np.abs(field_data) >= 999.0)
        else:
            # Level 3 reflectivity often uses -32 dBZ for no-echo/no-data. Treat
            # these bins as transparent, and keep meaningful echoes visible.
            invalid = ~np.isfinite(field_data) | (field_data <= -31.5)

        radar.fields[field_name]["data"] = np.ma.masked_where(invalid, field_data)

        display = pyart.graph.RadarMapDisplay(radar)
        cmap_name = "NWSVel" if is_velocity else "NWSRef"
        cmap = plt.get_cmap(cmap_name).copy()
        cmap.set_bad((0, 0, 0, 0))
        cmap.set_under((0, 0, 0, 0))
        vmin = -80 if is_velocity else -10
        vmax = 80 if is_velocity else 80
        sweep = _best_sweep(radar, field_name)
        display.plot_ppi_map(
            field_name,
            sweep=sweep,
            ax=ax,
            projection=ccrs.PlateCarree(),
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

        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            str(out_path), format="png", dpi=150, transparent=True, pad_inches=0
        )
        plt.close(fig)
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception as exc:
        print(f"[radar_live_worker] render failed: {type(exc).__name__}: {exc}")
        try:
            plt.close("all")
        except Exception:
            pass
        return False


def _units_for_product(product_key: str, product_code: str) -> str:
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
) -> int:
    """Render and cache frames for one site/product. Returns number of frames cached."""
    level = str(product_cfg.get("level") or "Level 3")
    level_code = _level_code(level)
    product_code = str(product_cfg.get("product") or "N0B").upper()
    product_label = str(product_cfg.get("label") or product_key)

    provider = "aws"
    kwargs = {}
    if radar_data_utils.__name__.endswith("radar_nodd_utils"):
        kwargs["provider"] = provider

    data_dir, total_files, _downloaded = radar_data_utils.download_radar_data(
        level,
        site,
        product_code,
        float(LIVE_RADAR_LOOKBACK_HOURS),
        str(_RADAR_ROOT),
        latest_only=False,
        **kwargs,
    )

    if not data_dir or int(total_files or 0) <= 0:
        return 0

    data_path = Path(data_dir)
    radar_files = _discover_radar_files(data_path)
    if not radar_files:
        return 0

    bounds = _site_bounds(site)
    if not bounds:
        return 0

    keep_n = max(1, int(LIVE_RADAR_KEEP_FRAMES or 30))
    selected_files = radar_files[-keep_n:]

    # Load dedup tracking for this product.
    processed_keys = radar_read_processed_keys(
        str(_CACHE_ROOT), site, level_code, product_key
    )

    cached = 0
    read_failures = 0
    _TMP_RENDER_ROOT.mkdir(parents=True, exist_ok=True)
    for src_file in selected_files:
        source_key = src_file.name
        if source_key in processed_keys:
            continue

        try:
            radar = _read_radar(level, str(src_file))
        except Exception:
            read_failures += 1
            continue

        available_fields = list(getattr(radar, "fields", {}).keys())
        field_name = _field_for_product(level, product_code, available_fields)
        if not field_name:
            continue

        frame_dt = _frame_dt_from_radar(radar, src_file)
        if frame_dt is None:
            continue

        frame_key = frame_key_from_datetime(frame_dt)
        temp_render = _TMP_RENDER_ROOT / f"{site}_{product_key}_{frame_key}.png"
        if not _render_overlay_png(
            radar=radar,
            field_name=field_name,
            bounds=bounds,
            out_path=temp_render,
            product_code=product_code,
        ):
            continue

        dest_image = Path(
            radar_overlay_image_path(
                str(_CACHE_ROOT), site, level_code, product_key, frame_key
            )
        )
        dest_image.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(temp_render), str(dest_image))

        processed_keys.add(source_key)

        radar_update_index(
            str(_CACHE_ROOT),
            site,
            level_code,
            product_key,
            frame_key,
            bounds=bounds,
            full_name=product_label,
            units=_units_for_product(product_key, product_code),
        )
        cached += 1
        try:
            temp_render.unlink(missing_ok=True)
        except Exception:
            pass

    if read_failures:
        print(
            f"[radar_live_worker] {site}/{product_key} skipped unreadable files: {read_failures}"
        )

    radar_write_processed_keys(
        str(_CACHE_ROOT), site, level_code, product_key, processed_keys, keep_n
    )
    radar_prune_frames(str(_CACHE_ROOT), site, level_code, product_key, keep_n=keep_n)
    return cached


def run_radar_live_worker(force: bool = False) -> None:
    """Render configured site/product live radar overlays into cache."""
    if not force and is_cache_fresh("radar_live", _FRESH_WINDOW_SEC):
        print("[radar_live_worker] Cache fresh - skipping run")
        return

    radar_data_utils = _resolve_radar_data_utils()
    source_label = "NODD-AWS"

    total_cached = 0
    for site in LIVE_RADAR_SITES:
        site_id = str(site).strip().upper()
        if not site_id:
            continue
        for product_key, product_cfg in LIVE_RADAR_PRODUCTS.items():
            try:
                cached = _render_site_product(
                    radar_data_utils,
                    source_label,
                    site_id,
                    str(product_key),
                    product_cfg,
                )
                total_cached += int(cached)
            except Exception as exc:
                print(
                    f"[radar_live_worker] {site_id}/{product_key} failed: {type(exc).__name__}: {exc}"
                )

    print(f"[radar_live_worker] completed - cached frames: {total_cached}")

    mark_run_complete("radar_live")


def run_radar_live_site_product(
    site: str,
    product_key: str,
    force: bool = True,
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

    if not force and is_cache_fresh("radar_live", _FRESH_WINDOW_SEC):
        return 0

    radar_data_utils = _resolve_radar_data_utils()
    cached = _render_site_product(
        radar_data_utils,
        "NODD-AWS",
        site_id,
        normalized_product,
        product_cfg,
    )
    if cached > 0:
        mark_run_complete("radar_live")
    return int(cached)


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
