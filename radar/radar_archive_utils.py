"""
Radar Archive Animation Utility
================================
Standalone module for generating radar animations from NODD (AWS/GCP) archive data.
Downloads files to cache/radar/archive/ directory tree, renders frames with per-file
timestamps from pyart, and stitches into MP4.

Uses radar_nodd_utils for the S3/GCS download plumbing and radar_utils for
config loaders & colormaps â€” but has its own independent rendering pipeline.
"""

from config.radar_config import L3_PRODUCTS
from config.alerts_config import ALERT_COLORS
from config.style_config import resolve_radar_style_config
from font_utils import register_montserrat_fonts
from geo_utils import CensusCounties, CensusStates
from listing_cache import load_json_config as _load_json_config_raw
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
import matplotlib.image as mpimg
from dateutil import tz
from metpy.plots import USCOUNTIES
from datetime import datetime, timedelta, timezone
import matplotlib.patheffects as PathEffects
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from shapely.geometry import shape
import numpy as np
import imageio.v2 as imageio
import matplotlib.pyplot as plt
import io
import os
import json
import glob
import math
import re
import shutil
import tarfile
import xml.etree.ElementTree as ET
import time as _time
import matplotlib


matplotlib.use("Agg")

LAYER_SESSION_MANIFEST = "_layer_session.json"
LAYER_SESSION_TTL_HOURS = 12
LAYER_SESSION_MAX_DIRS = 120
_COORD_LABEL_RE = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*°?\s*[NSEW]\s*$", re.IGNORECASE)


def _suppress_geo_labels(ax_obj, fig_obj=None):
    """Hide coordinate ticks/grid labels injected by Cartopy/Py-ART."""
    try:
        ax_obj.tick_params(
            axis="both",
            which="both",
            bottom=False,
            top=False,
            left=False,
            right=False,
            labelbottom=False,
            labelleft=False,
        )
        for tick_label in list(ax_obj.get_xticklabels()) + list(
            ax_obj.get_yticklabels()
        ):
            tick_label.set_visible(False)
    except Exception:
        pass

    text_pool = []
    if fig_obj is not None:
        try:
            text_pool = fig_obj.findobj(
                match=lambda artist: isinstance(artist, matplotlib.text.Text)
            )
        except Exception:
            text_pool = []
    if not text_pool:
        text_pool = list(getattr(ax_obj, "texts", []))

    for txt in text_pool:
        label = txt.get_text() if hasattr(txt, "get_text") else ""
        if _COORD_LABEL_RE.match(str(label or "")):
            txt.set_visible(False)

    try:
        for child in list(ax_obj.get_children()):
            if hasattr(child, "xline_artists") and hasattr(child, "yline_artists"):
                for attr in (
                    "xline_artists",
                    "yline_artists",
                    "xlabel_artists",
                    "ylabel_artists",
                    "top_label_artists",
                    "bottom_label_artists",
                    "left_label_artists",
                    "right_label_artists",
                ):
                    artists = getattr(child, attr, None)
                    if not artists:
                        continue
                    for artist in list(artists):
                        try:
                            artist.set_visible(False)
                        except Exception:
                            pass
    except Exception:
        pass


def _safe_color(value, fallback="#FFFFFF"):
    """Return a matplotlib-safe color, falling back when invalid/empty."""
    try:
        if value is None:
            return fallback
        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                return fallback
            return candidate if matplotlib.colors.is_color_like(candidate) else fallback
        return value if matplotlib.colors.is_color_like(value) else fallback
    except Exception:
        return fallback


def _city_outline_color(text_color: str) -> str:
    """Pick a contrasting outline for city labels so text stays legible."""
    safe_text = _safe_color(text_color, "#d8e700")
    try:
        r, g, b = matplotlib.colors.to_rgb(safe_text)
        # Relative luminance approximation for contrast switching.
        luminance = (0.2126 * r) + (0.7152 * g) + (0.0722 * b)
        return "#ffffff" if luminance < 0.42 else "#000000"
    except Exception:
        return "#000000"


def _safe_radar_site_coords(radar_obj, fallback_station_id=None):
    """
    Return (site_lat, site_lon) extracted from a radar object.

    Modern NEXRAD files carry accurate site metadata.  Older archive files
    (particularly pre-Build-5 / early 1990s data) may encode a default (0, 0)
    when the site field was not populated.  When the extracted coordinates fall
    suspiciously close to (0, 0) â€” i.e. the Gulf of Guinea â€” we fall back to
    pyart's built-in NEXRAD_LOCATIONS lookup table using the known station ID.

    For all current and recent NEXRAD data the coordinates will be valid and
    the fallback is never triggered.
    """
    try:
        r_lat = float(radar_obj.latitude["data"][0])
        r_lon = float(radar_obj.longitude["data"][0])
    except Exception:
        r_lat, r_lon = 0.0, 0.0

    # Validity gate: reject only coordinates within Â±5Â° of (0, 0) â€” the Gulf
    # of Guinea â€” where no NEXRAD site exists.  All legitimate US sites
    # (CONUS, Alaska, Hawaii, Puerto Rico, Guam) lie well outside this box.
    if not (math.isfinite(r_lat) and math.isfinite(r_lon)):
        r_lat, r_lon = 0.0, 0.0  # force into fallback branch below

    if abs(r_lat) > 5.0 or abs(r_lon) > 5.0:
        # Coordinates look real â€” use them unchanged.
        return r_lat, r_lon

    # Coordinates are near (0, 0); try the NEXRAD_LOCATIONS table.
    if fallback_station_id:
        sid = str(fallback_station_id).upper()
        try:
            from pyart.io.nexrad_common import NEXRAD_LOCATIONS

            if sid in NEXRAD_LOCATIONS:
                info = NEXRAD_LOCATIONS[sid]
                fb_lat = float(info["lat"])
                fb_lon = float(info["lon"])
                if math.isfinite(fb_lat) and math.isfinite(fb_lon):
                    print(
                        f"[WARN] Radar file has invalid site coords "
                        f"({r_lat:.4f}, {r_lon:.4f}) for {sid}; "
                        f"using known station location "
                        f"({fb_lat:.4f}, {fb_lon:.4f})"
                    )
                    return fb_lat, fb_lon
        except Exception as _exc:
            print(f"[WARN] NEXRAD_LOCATIONS fallback failed for {sid}: {_exc}")

    return r_lat, r_lon


def _normalize_radar_site_coords(radar_obj, fallback_station_id=None):
    """
    Return valid site coordinates and patch them into the radar object.

    Older archive Level 2 files can report (0, 0) site metadata. We already
    derive safer coordinates via _safe_radar_site_coords(); this helper also
    writes those coordinates back to the radar object so RadarMapDisplay plots
    the sweep at the correct location.
    """
    r_lat, r_lon = _safe_radar_site_coords(radar_obj, fallback_station_id)

    try:
        lat_meta = getattr(radar_obj, "latitude", None)
        if isinstance(lat_meta, dict):
            lat_data = lat_meta.get("data")
            try:
                lat_data[0] = r_lat
            except Exception:
                lat_meta["data"] = np.array([r_lat], dtype=float)
    except Exception:
        pass

    try:
        lon_meta = getattr(radar_obj, "longitude", None)
        if isinstance(lon_meta, dict):
            lon_data = lon_meta.get("data")
            try:
                lon_data[0] = r_lon
            except Exception:
                lon_meta["data"] = np.array([r_lon], dtype=float)
    except Exception:
        pass

    return r_lat, r_lon


# Import GRS colormap functions
try:
    from .radar_colormaps import (
        create_grs_cc_cmap,
        create_grs_bv_cmap,
        create_grs_br_cmap,
        create_grs_zdr_cmap,
        create_grs_vil_cmap,
        create_grs_et_cmap,
        create_grs_sw_cmap,
        create_grs_precip_cmap,
        create_grs_dpa_cmap,
        create_grs_precip_total_cmap,
        create_grs_hca_style,
    )
except ImportError:
    from radar_colormaps import (
        create_grs_cc_cmap,
        create_grs_bv_cmap,
        create_grs_br_cmap,
        create_grs_zdr_cmap,
        create_grs_vil_cmap,
        create_grs_et_cmap,
        create_grs_sw_cmap,
        create_grs_precip_cmap,
        create_grs_dpa_cmap,
        create_grs_precip_total_cmap,
        create_grs_hca_style,
    )

# Import NODD download helpers (shared with live radar)
try:
    from .radar_nodd_utils import (
        get_s3_client,
        list_nexrad_files,
        _enforce_cache_size,
        NEXRAD_LEVEL2_BUCKET,
        NEXRAD_LEVEL3_BUCKET,
        NEXRAD_LEVEL2_GCP_BUCKET,
        NEXRAD_LEVEL3_GCP_BUCKET,
    )
except ImportError:
    from radar_nodd_utils import (
        get_s3_client,
        list_nexrad_files,
        _enforce_cache_size,
        NEXRAD_LEVEL2_BUCKET,
        NEXRAD_LEVEL3_BUCKET,
        NEXRAD_LEVEL2_GCP_BUCKET,
        NEXRAD_LEVEL3_GCP_BUCKET,
    )

# Import alerts utils for overlay
try:
    from alerts import alerts_archive_utils
except ImportError:
    try:
        from ..alerts import alerts_archive_utils
    except ImportError:
        alerts_archive_utils = None

register_montserrat_fonts()

# GCP NODD Level 3 full-day tar archive bucket (1992â€“present)
GCP_L3_ARCHIVE_BUCKET_URL = "https://storage.googleapis.com/gcp-public-data-nexrad-l3/"
_GCP_S3_NS = {"s3": "http://doc.s3.amazonaws.com/2006-03-01"}


# â”€â”€â”€ Config helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _load_json_config(filename, default):
    return _load_json_config_raw(
        os.path.dirname(os.path.abspath(__file__)), filename, default
    )


RADAR_SITES = _load_json_config(
    "radar_sites.json", {"Newport/Morehead City, NC": "KMHX"}
)


def _is_radar_alert_event_allowed(event_name: str) -> bool:
    """Allow tornado/severe thunderstorm and flash flood alerts, excluding watches."""
    name = str(event_name or "").strip()
    if not name:
        return False
    if name.startswith("Tornado"):
        return "Watch" not in name
    if name.startswith("Severe Thunderstorm"):
        return "Watch" not in name
    if name.startswith("Flash Flood"):
        return "Watch" not in name
    if name.startswith("Special Marine"):
        return "Watch" not in name
    return False


_RADAR_STATIC_WARNING_EVENTS = (
    "Tornado",
    "Severe Thunderstorm",
    "Special Marine",
    "Flash Flood",
)


_RADAR_STATIC_WARNING_COLOR_KEYS = {
    "Tornado": "Tornado Warning",
    "Severe Thunderstorm": "Severe Thunderstorm Warning",
    "Special Marine": "Special Marine Warning",
    "Flash Flood": "Flash Flood Warning",
}


def _radar_static_warning_legend_entries():
    return [
        (
            event_name,
            _safe_color(
                ALERT_COLORS.get(_RADAR_STATIC_WARNING_COLOR_KEYS[event_name]),
                "#C0C0C0",
            ),
        )
        for event_name in _RADAR_STATIC_WARNING_EVENTS
    ]


# Keep full-resolution base map layers while avoiding per-frame feature object rebuilds.
_RADAR_NE_SCALE = "10m"
_FEATURE_LAND = cfeature.LAND.with_scale(_RADAR_NE_SCALE)
_FEATURE_LAKES = cfeature.LAKES.with_scale(_RADAR_NE_SCALE)
_FEATURE_RIVERS = cfeature.RIVERS.with_scale(_RADAR_NE_SCALE)
_FEATURE_STATES = cfeature.STATES.with_scale(_RADAR_NE_SCALE)
_FEATURE_ROADS = cfeature.NaturalEarthFeature(
    category="cultural", name="roads", scale=_RADAR_NE_SCALE, facecolor="none"
)
_RADAR_CARTOPY_WARMED = False
_LAKES_GEOMS = ()
_LAKES_BOUNDS = ()
_RIVERS_GEOMS = ()
_RIVERS_BOUNDS = ()
_ROADS_GEOMS = ()
_ROADS_BOUNDS = ()
_STATES_GEOMS = ()
_STATES_BOUNDS = ()


def _materialize_feature_geometries(feature):
    geoms = tuple(feature.geometries())
    bounds = []
    for geom in geoms:
        try:
            bounds.append(geom.bounds)
        except Exception:
            bounds.append((-1e9, -1e9, 1e9, 1e9))
    return geoms, tuple(bounds)


def _subset_geometries_by_extent(geoms, bounds, min_lat, max_lat, min_lon, max_lon):
    subset = []
    for geom, (gx_min, gy_min, gx_max, gy_max) in zip(geoms, bounds):
        if gx_max < min_lon or gx_min > max_lon or gy_max < min_lat or gy_min > max_lat:
            continue
        subset.append(geom)
    return subset


def warm_radar_cartopy_cache():
    """Pre-warm Cartopy Natural Earth assets used by radar archive rendering."""
    global _RADAR_CARTOPY_WARMED
    global _LAKES_GEOMS, _LAKES_BOUNDS
    global _RIVERS_GEOMS, _RIVERS_BOUNDS
    global _ROADS_GEOMS, _ROADS_BOUNDS
    global _STATES_GEOMS, _STATES_BOUNDS
    if _RADAR_CARTOPY_WARMED:
        return

    t0 = _time.perf_counter()
    try:
        for feature in (
            _FEATURE_LAND,
            _FEATURE_LAKES,
            _FEATURE_RIVERS,
            _FEATURE_STATES,
            _FEATURE_ROADS,
        ):
            try:
                next(iter(feature.geometries()), None)
            except Exception:
                continue

        _LAKES_GEOMS, _LAKES_BOUNDS = _materialize_feature_geometries(_FEATURE_LAKES)
        _RIVERS_GEOMS, _RIVERS_BOUNDS = _materialize_feature_geometries(_FEATURE_RIVERS)
        _ROADS_GEOMS, _ROADS_BOUNDS = _materialize_feature_geometries(_FEATURE_ROADS)
        _STATES_GEOMS, _STATES_BOUNDS = _materialize_feature_geometries(_FEATURE_STATES)
    finally:
        _RADAR_CARTOPY_WARMED = True
        print(
            f"[Perf] radar archive cartopy warmup took {_time.perf_counter() - t0:.2f}s"
        )


# â”€â”€â”€ SRV Calculation â€” imported from radar_utils â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from .radar_utils import calculate_srv as _calculate_srv
    from .radar_utils import compute_radar_extent
except ImportError:
    from radar_utils import calculate_srv as _calculate_srv
    from radar_utils import compute_radar_extent


# â”€â”€â”€ GCP Level 3 Tar Archive (historical fallback, 1992â€“present) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _find_gcp_l3_archive(station: str, year: int, month: int, day: int):
    """
    Look up the full-day Level 3 tar archive in the GCP bucket.

    Returns dict with url, key, size_bytes, extension â€” or None.
    """
    import requests as _req

    prefix = f"{year}/{month:02d}/{day:02d}/{station}/"
    resp = _req.get(
        GCP_L3_ARCHIVE_BUCKET_URL,
        params={"prefix": prefix, "max-keys": "5"},
        timeout=30,
    )
    root = ET.fromstring(resp.text)
    contents = root.findall("s3:Contents", _GCP_S3_NS)
    if not contents:
        return None

    key = contents[0].find("s3:Key", _GCP_S3_NS).text
    size = int(contents[0].find("s3:Size", _GCP_S3_NS).text)

    if key.endswith(".tar.gz"):
        ext = "tar.gz"
    elif key.endswith(".tar.Z"):
        ext = "tar.Z"
    else:
        ext = key.split(".")[-1]

    return {
        "url": f"{GCP_L3_ARCHIVE_BUCKET_URL}{key}",
        "key": key,
        "size_bytes": size,
        "extension": ext,
    }


def download_and_extract_l3_product(
    station: str,
    product: str,
    year: int,
    month: int,
    day: int,
    save_dir: str,
    start_hour: int = 0,
    end_hour: int = 24,
    progress_callback=None,
) -> list:
    """
    Download a full-day Level 3 tar archive from the GCP NODD bucket and
    extract only the files matching the requested product code.

    The GCP archive bucket (gcp-public-data-nexrad-l3) stores every Level 3
    product for every NEXRAD site as a single tar per UTC day, dating back
    to 1992.  This is the definitive fallback for historical data that is
    not available as individual files on the AWS/GCP real-time buckets.

    Args:
        station:    NEXRAD station ID (e.g. "KMHX")
        product:    Level 3 product code (e.g. "N0Q", "N0B")
        year, month, day: UTC date of interest
        save_dir:   Local directory to write extracted product files
        start_hour: UTC hour to start (inclusive, 0-23)
        end_hour:   UTC hour to end (exclusive, 1-24)
        progress_callback: Optional callable(downloaded_bytes, total_bytes)

    Returns:
        Sorted list of local file paths for the extracted product files.
    """
    import requests as _req

    os.makedirs(save_dir, exist_ok=True)

    # 1. Locate the tar archive
    archive_info = _find_gcp_l3_archive(station, year, month, day)
    if archive_info is None:
        print(
            f"[WARN] No GCP Level 3 archive found for {station} on "
            f"{year}-{month:02d}-{day:02d}"
        )
        return []

    url = archive_info["url"]
    ext = archive_info["extension"]
    size_mb = archive_info["size_bytes"] / 1e6

    # 2. Download or use cached tar archive
    #    Cache key: station + date â†’ avoids re-downloading when switching
    #    product codes or hour ranges for the same station/day.
    cache_dir = os.path.join(os.path.dirname(save_dir), "_tar_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_filename = f"{station}_{year}{month:02d}{day:02d}.{ext}"
    cache_path = os.path.join(cache_dir, cache_filename)

    if os.path.exists(cache_path):
        print(f"[INFO] Using cached archive: {cache_filename} ({size_mb:.0f} MB)")
        with open(cache_path, "rb") as fh:
            raw_bytes = fh.read()
    else:
        print(f"[INFO] Downloading Level 3 archive: {size_mb:.0f} MB ({ext})")
        resp = _req.get(url, timeout=600, stream=True)
        resp.raise_for_status()
        total_bytes = int(resp.headers.get("content-length", 0))
        chunks = []
        downloaded_bytes = 0
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            chunks.append(chunk)
            downloaded_bytes += len(chunk)
            if progress_callback:
                progress_callback(downloaded_bytes, total_bytes)
        raw_bytes = b"".join(chunks)
        # Persist to cache
        try:
            with open(cache_path, "wb") as fh:
                fh.write(raw_bytes)
            print(f"[INFO] Cached archive: {cache_filename}")
        except OSError as write_err:
            print(f"[WARN] Could not cache archive: {write_err}")

    # 3. Open tar and extract matching product files
    extracted: list[str] = []
    try:
        if ext == "tar.gz":
            tf = tarfile.open(fileobj=io.BytesIO(raw_bytes), mode="r:gz")
        elif ext == "tar.Z":
            # Pre-~2014 archives use Unix compress (.Z / LZW)
            try:
                import unlzw3

                decompressed = unlzw3.unlzw(raw_bytes)
                tf = tarfile.open(fileobj=io.BytesIO(decompressed), mode="r:")
            except ImportError:
                print(
                    "[ERROR] unlzw3 package required for .tar.Z archives. "
                    "Install with: pip install unlzw3"
                )
                return []
        else:
            print(f"[ERROR] Unknown archive extension: {ext}")
            return []

        for member in tf.getmembers():
            if not member.isfile():
                continue

            name = member.name
            parts = name.split("_")
            if len(parts) < 4:
                continue

            # Product code is first 3 chars of the WMO product field
            file_product = parts[2][:3]
            if file_product.upper() != product.upper():
                continue

            # Filter by hour range using the embedded timestamp
            timestamp_str = parts[3]  # YYYYMMDDHHmm
            if len(timestamp_str) >= 10:
                try:
                    hour = int(timestamp_str[8:10])
                    if not (start_hour <= hour < end_hour):
                        continue
                except (ValueError, IndexError):
                    pass

            # Write to save_dir
            local_path = os.path.join(save_dir, name)
            with tf.extractfile(member) as src:
                with open(local_path, "wb") as dst:
                    dst.write(src.read())
            extracted.append(local_path)

        tf.close()

    except Exception as e:
        print(f"[ERROR] Failed to extract archive: {type(e).__name__}: {e}")

    extracted.sort()
    print(f"[INFO] Extracted {len(extracted)} {product} files from GCP tar archive")
    return extracted


# â”€â”€â”€ Archive Download â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# Build 19 (deployed ~2020-2021) renamed many Level 3 product codes.
# When an archive query returns 0 files, try the legacy/modern equivalent.
_BUILD19_FALLBACKS = {
    # New (Build 19+) â†’ Old (pre-Build 19)
    "N0B": "N0Q",  # Base Reflectivity 0.5Â°
    "N1B": "N1Q",  # Base Reflectivity 1.5Â°
    "N2B": "N2Q",  # Base Reflectivity 2.4Â°
    "N3B": "N3Q",  # Base Reflectivity 3.1Â°
    "N0G": "N0U",  # Base Velocity 0.5Â°
    "N1G": "N1U",  # Base Velocity 1.5Â°
    # Old (pre-Build 19) â†’ New (Build 19+)
    "N0Q": "N0B",
    "N1Q": "N1B",
    "N2Q": "N2B",
    "N3Q": "N3B",
    "N0U": "N0G",
    "N1U": "N1G",
}


def _extract_datetime_from_radar_filename(file_name):
    name = os.path.basename(str(file_name or ""))

    m = re.search(r"(\d{8})_(\d{4,6})", name)
    if m:
        date_part, time_part = m.groups()
        if len(time_part) == 4:
            time_part += "00"
        try:
            return datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            pass

    m2 = re.search(r"(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})", name)
    if m2:
        yr, mo, dy, hh, mm, ss = m2.groups()
        try:
            return datetime(
                int(yr),
                int(mo),
                int(dy),
                int(hh),
                int(mm),
                int(ss),
                tzinfo=timezone.utc,
            )
        except ValueError:
            pass

    m3 = re.search(r"_(\d{12})$", name)
    if m3:
        ts = m3.group(1)
        try:
            return datetime(
                int(ts[0:4]),
                int(ts[4:6]),
                int(ts[6:8]),
                int(ts[8:10]),
                int(ts[10:12]),
                tzinfo=timezone.utc,
            )
        except ValueError:
            pass

    return None


def _infer_partition_dt_from_key(key, fallback_dt=None):
    key_norm = str(key or "").replace("\\", "/")
    m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", f"/{key_norm}")
    if m:
        try:
            return datetime(
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                tzinfo=timezone.utc,
            )
        except ValueError:
            pass

    dt = _extract_datetime_from_radar_filename(os.path.basename(key_norm))
    if dt is not None:
        return dt

    if isinstance(fallback_dt, datetime):
        return (
            fallback_dt.replace(tzinfo=timezone.utc)
            if fallback_dt.tzinfo is None
            else fallback_dt.astimezone(timezone.utc)
        )

    return datetime.now(timezone.utc)


def _date_partition_dir(base_dir, dt_obj):
    dt_utc = (
        dt_obj.replace(tzinfo=timezone.utc)
        if isinstance(dt_obj, datetime) and dt_obj.tzinfo is None
        else dt_obj.astimezone(timezone.utc)
        if isinstance(dt_obj, datetime)
        else datetime.now(timezone.utc)
    )
    return os.path.join(
        base_dir,
        dt_utc.strftime("%Y"),
        dt_utc.strftime("%m"),
        dt_utc.strftime("%d"),
    )


def download_archive_data(
    level,
    station_id,
    product,
    date_from,
    date_to,
    base_dir,
    progress_callback=None,
    provider="aws",
    latest_only=False,
):
    """
    Download radar files from NODD for an explicit date range.
    Saves into archive/ subdirectory so it never mixes with live data.
    """
    import importlib
    from urllib.parse import quote

    provider = str(provider).lower()
    level_path = str(level).lower().replace(" ", "")
    save_dir = os.path.join(
        base_dir, "archive", f"radar_{level_path}_downloads", product, station_id
    )
    os.makedirs(save_dir, exist_ok=True)

    start_dt = date_from
    end_dt = date_to

    try:
        s3_client = get_s3_client() if provider == "aws" else None
        keys = list_nexrad_files(
            s3_client=s3_client,
            level=level,
            station_id=station_id,
            product=product,
            start_dt=start_dt,
            end_dt=end_dt,
            provider=provider,
            latest_only=latest_only,
        )
    except Exception as e:
        print(f"[ERROR] Archive list_nexrad_files failed: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        raise

    # If no files found for a Level 3 product, try the Build 19 equivalent
    resolved_product = product
    total_files = len(keys)
    if total_files == 0 and level_path == "level3":
        fallback = _BUILD19_FALLBACKS.get(product.upper())
        if fallback and fallback.upper() != product.upper():
            print(
                f"[INFO] No archive files for {product}, trying "
                f"Build 19 fallback: {fallback}"
            )
            try:
                keys = list_nexrad_files(
                    s3_client=s3_client,
                    level=level,
                    station_id=station_id,
                    product=fallback,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    provider=provider,
                    latest_only=latest_only,
                )
                total_files = len(keys)
                if total_files > 0:
                    resolved_product = fallback
                    print(
                        f"[INFO] Found {total_files} files using "
                        f"fallback product {fallback}"
                    )
                    # Update save_dir for the resolved product
                    save_dir = os.path.join(
                        base_dir,
                        "archive",
                        f"radar_{level_path}_downloads",
                        resolved_product,
                        station_id,
                    )
                    os.makedirs(save_dir, exist_ok=True)
            except Exception as e2:
                print(f"[WARN] Fallback list also failed: {type(e2).__name__}: {e2}")

    # â”€â”€ GCP full-day tar archive fallback (1992â€“present) â”€â”€
    if total_files == 0 and level_path == "level3":
        print("[INFO] No individual files found. Trying GCP full-day tar archive...")

        # Wrap the raw progress_callback so it shows human-readable MB
        # instead of raw byte counts ("Downloading 1048576/1066344038").
        def _tar_progress(downloaded_bytes, total_bytes):
            if not progress_callback or total_bytes <= 0:
                return
            dl_mb = int(downloaded_bytes / 1_000_000)
            tot_mb = int(total_bytes / 1_000_000)
            pct_done = downloaded_bytes / total_bytes
            progress_callback(
                int(pct_done * 100),  # curr
                100,  # total
                message=f"Historical archive: {dl_mb}/{tot_mb} MB",
            )

        try:
            request_day_dir = _date_partition_dir(save_dir, start_dt)
            os.makedirs(request_day_dir, exist_ok=True)
            # Try the originally requested product first
            extracted = download_and_extract_l3_product(
                station=station_id,
                product=product,
                year=start_dt.year,
                month=start_dt.month,
                day=start_dt.day,
                save_dir=request_day_dir,
                start_hour=start_dt.hour,
                end_hour=min(end_dt.hour + 1, 24),
                progress_callback=_tar_progress,
            )
            # If nothing found, try Build 19 fallback product in the tar
            if not extracted:
                tar_fallback = _BUILD19_FALLBACKS.get(product.upper())
                if tar_fallback and tar_fallback.upper() != product.upper():
                    print(
                        f"[INFO] No {product} in tar archive, "
                        f"trying fallback {tar_fallback}..."
                    )
                    tar_save_dir = os.path.join(
                        base_dir,
                        "archive",
                        f"radar_{level_path}_downloads",
                        tar_fallback,
                        station_id,
                    )
                    os.makedirs(tar_save_dir, exist_ok=True)
                    tar_request_day_dir = _date_partition_dir(tar_save_dir, start_dt)
                    os.makedirs(tar_request_day_dir, exist_ok=True)
                    extracted = download_and_extract_l3_product(
                        station=station_id,
                        product=tar_fallback,
                        year=start_dt.year,
                        month=start_dt.month,
                        day=start_dt.day,
                        save_dir=tar_request_day_dir,
                        start_hour=start_dt.hour,
                        end_hour=min(end_dt.hour + 1, 24),
                        progress_callback=_tar_progress,
                    )
                    if extracted:
                        resolved_product = tar_fallback
                        save_dir = tar_save_dir

            total_files = len(extracted)
            if total_files > 0:
                print(f"[INFO] Extracted {total_files} files from GCP tar archive")
                return (
                    save_dir,
                    total_files,
                    total_files,
                    resolved_product,
                    sorted(path for path in extracted if os.path.isfile(path)),
                )
        except Exception as e:
            print(f"[WARN] GCP tar archive fallback failed: {e}")

    if total_files == 0:
        return save_dir, 0, 0, resolved_product, []

    if provider == "gcp":
        bucket = (
            NEXRAD_LEVEL2_GCP_BUCKET
            if level_path == "level2"
            else NEXRAD_LEVEL3_GCP_BUCKET
        )
        requests = importlib.import_module("requests")
    else:
        bucket = (
            NEXRAD_LEVEL2_BUCKET if level_path == "level2" else NEXRAD_LEVEL3_BUCKET
        )
        requests = None

    downloaded = 0
    selected_files = []
    for idx, key in enumerate(keys, start=1):
        if progress_callback:
            progress_callback(idx, total_files)

        filename = os.path.basename(key)
        partition_dt = _infer_partition_dt_from_key(key, fallback_dt=start_dt)
        day_dir = _date_partition_dir(save_dir, partition_dt)
        os.makedirs(day_dir, exist_ok=True)
        local_path = os.path.join(day_dir, filename)

        if os.path.exists(local_path):
            downloaded += 1
            selected_files.append(local_path)
            continue

        try:
            if provider == "gcp":
                encoded_key = quote(key, safe="/")
                url = f"https://storage.googleapis.com/{bucket}/{encoded_key}"
                resp = requests.get(url, timeout=60)
                resp.raise_for_status()
                with open(local_path, "wb") as fh:
                    fh.write(resp.content)
            else:
                s3_client.download_file(bucket, key, local_path)
            downloaded += 1
            selected_files.append(local_path)
        except Exception as e:
            print(
                f"[WARN] Archive download failed: {type(e).__name__}: {e} | key={key}"
            )

    _enforce_cache_size(os.path.join(base_dir, "archive"))
    unique_selected = sorted(
        path for path in {str(path) for path in selected_files} if os.path.isfile(path)
    )
    return save_dir, total_files, downloaded, resolved_product, unique_selected


# â”€â”€â”€ Archive Rendering â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _load_request_file_paths(data_dir):
    """Return all radar files under data_dir, including date-partitioned folders."""
    return sorted(
        path
        for path in glob.glob(os.path.join(data_dir, "**", "*"), recursive=True)
        if os.path.isfile(path) and not os.path.basename(path).startswith("_")
    )


def _downsample_evenly(items, target_count):
    if target_count <= 0 or len(items) <= target_count:
        return items
    if target_count == 1:
        return [items[-1]]

    step = (len(items) - 1) / float(target_count - 1)
    selected = []
    seen = set()
    for index in range(target_count):
        item_index = int(round(index * step))
        item_index = max(0, min(item_index, len(items) - 1))
        if item_index not in seen:
            selected.append(items[item_index])
            seen.add(item_index)

    if selected and selected[-1] != items[-1]:
        selected[-1] = items[-1]
    return selected


def _select_single_frame_file(parsed_files, target_time_utc=None):
    """Pick one frame, preferring the file closest to target_time_utc."""
    if not parsed_files:
        return None

    if target_time_utc is None:
        return parsed_files[len(parsed_files) // 2]

    if isinstance(target_time_utc, datetime):
        target = (
            target_time_utc.replace(tzinfo=timezone.utc)
            if target_time_utc.tzinfo is None
            else target_time_utc.astimezone(timezone.utc)
        )
    else:
        return parsed_files[len(parsed_files) // 2]

    return min(parsed_files, key=lambda item: abs((item[0] - target).total_seconds()))


def _iso_utc(dt_obj: datetime) -> str:
    return dt_obj.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitize_cache_token(value, fallback="na"):
    token = re.sub(r"[^A-Za-z0-9]+", "", str(value or "").upper())
    return token or fallback


def _cache_float_token(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return f"{number:.2f}".replace("-", "m").replace(".", "p")


def _radar_layer_cache_filename(
    station_id,
    product_label,
    scan_dt_utc,
    storm_relative=False,
    sm_speed=0,
    sm_dir=0,
    geometry_token=None,
):
    site_token = _sanitize_cache_token(station_id, fallback="SITE")
    product_token = _sanitize_cache_token(product_label, fallback="PRODUCT")
    scan_token = scan_dt_utc.strftime("%Y%m%d_%H%M%S")
    key = f"{site_token}__{product_token}__{scan_token}"
    if storm_relative:
        key = f"{key}__SRV_{_cache_float_token(sm_speed)}_{_cache_float_token(sm_dir)}"
    if geometry_token:
        key = f"{key}__G_{_sanitize_cache_token(geometry_token, fallback='GEOM')}"
    return f"{key}.png"


def _parse_iso_utc(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except Exception:
        return None


def _layer_manifest_path(layer_dir):
    return os.path.join(layer_dir, LAYER_SESSION_MANIFEST)


def _read_layer_manifest(layer_dir):
    manifest_path = _layer_manifest_path(layer_dir)
    if not os.path.exists(manifest_path):
        return {}
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_layer_manifest(layer_dir, **updates):
    os.makedirs(layer_dir, exist_ok=True)
    now = datetime.now(timezone.utc)
    data = _read_layer_manifest(layer_dir)
    if not data.get("created_utc"):
        data["created_utc"] = _iso_utc(now)
    data["updated_utc"] = _iso_utc(now)
    data.update(updates)

    expires_dt = now + timedelta(hours=LAYER_SESSION_TTL_HOURS)
    data["expires_utc"] = _iso_utc(expires_dt)

    try:
        with open(_layer_manifest_path(layer_dir), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
    except Exception as e:
        print(f"[WARN] Could not write layer manifest for {layer_dir}: {e}")
    return data


def touch_layer_session(layer_dir):
    now = datetime.now(timezone.utc)
    return _write_layer_manifest(layer_dir, last_access_utc=_iso_utc(now))


def _layer_sort_timestamp(layer_dir):
    manifest = _read_layer_manifest(layer_dir)
    for key in ("last_access_utc", "updated_utc", "created_utc"):
        dt_obj = _parse_iso_utc(manifest.get(key))
        if dt_obj is not None:
            return dt_obj
    try:
        return datetime.fromtimestamp(os.path.getmtime(layer_dir), tz=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def cleanup_layer_sessions(
    layers_root,
    ttl_hours=LAYER_SESSION_TTL_HOURS,
    max_dirs=LAYER_SESSION_MAX_DIRS,
):
    """Prune stale layered sessions and cap retained layer directories."""
    if not layers_root or not os.path.isdir(layers_root):
        return {"removed": 0, "removed_dirs": [], "total": 0}

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max(1, int(ttl_hours or LAYER_SESSION_TTL_HOURS)))

    dirs = []
    try:
        for name in os.listdir(layers_root):
            path = os.path.join(layers_root, name)
            if os.path.isdir(path):
                dirs.append(path)
    except Exception:
        return {"removed": 0, "removed_dirs": [], "total": 0}

    removed = 0
    removed_dirs = []
    survivors = []
    for path in dirs:
        ts = _layer_sort_timestamp(path)
        if ts < cutoff:
            try:
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
                removed_dirs.append(path)
                continue
            except Exception:
                pass
        survivors.append((ts, path))

    survivors.sort(key=lambda item: item[0], reverse=True)
    keep_count = max(1, int(max_dirs or LAYER_SESSION_MAX_DIRS))
    for _, path in survivors[keep_count:]:
        try:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
            removed_dirs.append(path)
        except Exception:
            pass

    return {"removed": removed, "removed_dirs": removed_dirs, "total": len(dirs)}


def generate_archive_layers(
    level,
    data_dir,
    product_label,
    logo_file,
    station_id,
    sm_speed,
    sm_dir,
    frames=150,
    custom_extent=None,
    progress_callback=None,
    show_places=False,
    style_config=None,
    selected_files=None,
    latest_only=False,
    target_time_utc=None,
    request_id="",
    user_tz="America/New_York",
):
    """Render layered archive output as split geospatial/UI timestamped PNG layers."""
    import pyart

    warm_radar_cartopy_cache()

    style_config = resolve_radar_style_config(style_config)

    # --- STYLE UNPACKING ---
    # Values come from the resolved config (RADAR_FIXED_STYLE_CONFIG merged
    # with any runtime overrides).  Edit config/style_config.py to change defaults.
    hud_left_size = style_config.get("hud_left_size", 10)
    hud_left_x = style_config.get("hud_left_x", 0.03)
    hud_left_y = style_config.get("hud_left_y", 0.97)
    hud_right_size = style_config.get("hud_right_size", 10)
    hud_right_x = style_config.get("hud_right_x", 0.97)
    hud_right_y = style_config.get("hud_right_y", 0.97)

    logo_user_size = style_config.get("logo_user_size", 0.05)
    logo_user_x = style_config.get("logo_user_x", 0.98)
    logo_user_y = style_config.get("logo_user_y", 0.01)

    show_rings = style_config.get("show_rings", True)
    ring_color = style_config.get("ring_color", "#ffffff")
    ring_width = style_config.get("ring_width", 1.0)
    show_alert_polygons = style_config.get("show_alert_polygons", True)
    alert_line_width = float(style_config.get("radar_alert_width", 4.0))
    alert_alpha = float(style_config.get("radar_alert_alpha", 1.0))
    show_alert_outline = True
    alert_outline_color = "#000000"
    alert_outline_width = alert_line_width
    alert_outline_alpha = min(1.0, alert_alpha + 0.1)
    county_width = style_config.get("county_width", 1.0)
    county_color = style_config.get("county_color", "#000000")
    cbar_title_size = style_config.get("cbar_title_size", 11)
    legend_box_x = 0.00
    legend_box_y = 0.00
    legend_box_w = 1.0
    legend_box_h = 0.14
    cities_file = style_config.get("cities_file", "us-cities.json")
    city_density = float(style_config.get("city_density", 5))
    city_text_size = int(style_config.get("city_text_size", 8))
    city_collision_w = style_config.get("city_collision_w", 0.05)
    city_collision_h = style_config.get("city_collision_h", 0.02)
    density_scale = city_density / 5.0
    expand_top = float(style_config.get("expand_top", 0.0))
    expand_bottom = float(style_config.get("expand_bottom", 0.0))
    expand_left = float(style_config.get("expand_left", 0.0))
    expand_right = float(style_config.get("expand_right", 0.0))

    city_text_color = _safe_color(
        style_config.get("city_text_color", "#d8e700"), "#d8e700"
    )
    city_text_bg_color = _safe_color(
        style_config.get("city_text_bg_color", "#141414"), "#141414"
    )
    city_text_bg_alpha = max(
        0.0, min(1.0, float(style_config.get("city_text_bg_alpha", 0.25)))
    )
    city_text_outline_color = _city_outline_color(city_text_color)

    font_family = style_config.get("font_family", "Montserrat")
    map_bg_color = style_config.get("map_bg_color", "#152238")
    land_color = style_config.get("land_color", "#5C5C5C")

    state_color = style_config.get("state_color", "#ffffff")
    state_width = style_config.get("state_width", 1.5)

    show_highways = style_config.get("show_highways", False)
    highway_color = style_config.get("highway_color", "#888888")
    highway_width = style_config.get("highway_width", 0.8)
    highway_opacity = float(style_config.get("highway_opacity", 0.6))

    hud_left_text_color = style_config.get("hud_left_text_color", "#ffffff")
    hud_left_bg_color = style_config.get("hud_left_bg_color", "#000000")
    hud_left_edge_color = style_config.get("hud_left_edge_color", "#555555")
    hud_left_alpha = float(style_config.get("hud_left_alpha", 0.7))
    hud_right_text_color = style_config.get("hud_right_text_color", "#ffd700")
    hud_right_bg_color = style_config.get("hud_right_bg_color", "#000000")
    hud_right_edge_color = style_config.get("hud_right_edge_color", "#555555")
    hud_right_alpha = float(style_config.get("hud_right_alpha", 0.7))

    show_lakes = style_config.get("show_lakes", True)
    lake_color = style_config.get("lake_color", "#577DBE")
    lake_outline_color = style_config.get("lake_outline_color", "#333333")
    lake_outline_width = style_config.get("lake_outline_width", 0.5)
    show_rivers = style_config.get("show_rivers", False)
    river_color = style_config.get("river_color", "#152238")
    river_width = style_config.get("river_width", 0.5)

    fig_height = 7.2
    fig_width = None
    fig_dpi = 150
    # Reserve enough lower band for colorbar ticks to avoid clipping.
    ui_margin_bottom = float(style_config.get("figure_bottom_margin", 0.10))
    # Use zero side/top padding by default so layered map aligns with site basemap.
    ui_margin_side = float(style_config.get("figure_left_margin", 0.00))
    ui_margin_top = float(style_config.get("figure_top_margin", 0.00))

    # Append footer space by increasing figure height so map panel keeps full size.
    map_panel_height_fraction = max(1e-6, 1.0 - ui_margin_bottom - ui_margin_top)
    fig_height = fig_height / map_panel_height_fraction
    map_axes_pos = [
        ui_margin_side,
        ui_margin_bottom,
        1.0 - 2 * ui_margin_side,
        1.0 - ui_margin_bottom - ui_margin_top,
    ]

    hud_left_size_base = int(hud_left_size)
    hud_right_size_base = int(hud_right_size)
    city_text_size_base = int(city_text_size)
    cbar_title_size_base = int(cbar_title_size)
    logo_user_size_base = float(logo_user_size)

    # Keep base sizes until first frame establishes extent-driven figure width.
    hud_left_size = hud_left_size_base
    hud_right_size = hud_right_size_base
    city_text_size = city_text_size_base
    cbar_title_size = cbar_title_size_base
    logo_user_size = logo_user_size_base

    zo = {
        "land": 0,
        "water": 1,
        "radar_data": 2,
        "range_rings": 5,
        "alert_polygons": 20,
        "counties": 10,
        "states": 10,
        "highways": 11,
        "cities": 12,
        "logos": 100,
        "hud": 150,
    }

    raw_site_name = next(
        (name for name, sid in RADAR_SITES.items() if sid == station_id),
        station_id,
    )
    site_display_name = raw_site_name.replace(" (No Filter)", "")
    site_state_abbr = None
    site_state_match = re.search(r",\s*([A-Z]{2})$", site_display_name)
    if site_state_match:
        site_state_abbr = site_state_match.group(1).upper()
    alert_state_filter = None
    if not custom_extent and station_id.upper() != "CONUS" and site_state_abbr:
        alert_state_filter = site_state_abbr

    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    cities_path = os.path.join(root_dir, "data", cities_file)
    cities_data = []
    if os.path.exists(cities_path):
        try:
            with open(cities_path, "r", encoding="utf-8") as file_handle:
                raw_data = json.load(file_handle)
            if isinstance(raw_data, dict):
                for city_name, city_values in raw_data.items():
                    if isinstance(city_values, list) and len(city_values) >= 2:
                        cities_data.append(
                            {
                                "city": city_name,
                                "latitude": city_values[0],
                                "longitude": city_values[1],
                                "align": city_values[2]
                                if len(city_values) > 2
                                else "left",
                                "rank": 9999,
                            }
                        )
            elif isinstance(raw_data, list):
                cities_data = raw_data
        except Exception as e:
            print(f"Error loading cities: {e}")

    output_dir = data_dir.replace("downloads", "images")
    layers_root = os.path.join(output_dir, "layers")
    radar_root = os.path.join(output_dir, "radar")
    radar_cache_root = os.path.join(output_dir, "radar_cache")
    alerts_root = os.path.join(output_dir, "alerts")
    cities_root = os.path.join(output_dir, "cities")
    hud_right_root = os.path.join(output_dir, "hud_right")
    for root_path in [
        layers_root,
        radar_root,
        radar_cache_root,
        alerts_root,
        cities_root,
        hud_right_root,
    ]:
        os.makedirs(root_path, exist_ok=True)

    cleanup_result = cleanup_layer_sessions(layers_root)
    removed_layer_dirs = cleanup_result.get("removed_dirs")
    if not isinstance(removed_layer_dirs, (list, tuple, set)):
        legacy_removed = cleanup_result.get("removed", [])
        removed_layer_dirs = (
            legacy_removed if isinstance(legacy_removed, (list, tuple, set)) else []
        )

    for removed_layer_dir in removed_layer_dirs:
        removed_key = os.path.basename(str(removed_layer_dir).rstrip("\\/"))
        if not removed_key:
            continue
        for sibling_root in [radar_root, alerts_root, cities_root, hud_right_root]:
            sibling_path = os.path.join(sibling_root, removed_key)
            if os.path.isdir(sibling_path):
                try:
                    shutil.rmtree(sibling_path)
                except OSError:
                    pass

    layer_key = str(request_id or "").strip() or datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S"
    )
    layer_dir = os.path.join(layers_root, layer_key)
    radar_dir = os.path.join(radar_root, layer_key)
    alerts_dir = os.path.join(alerts_root, layer_key)
    cities_dir = os.path.join(cities_root, layer_key)
    hud_right_dir = os.path.join(hud_right_root, layer_key)
    for frame_dir in [layer_dir, radar_dir, alerts_dir, cities_dir, hud_right_dir]:
        os.makedirs(frame_dir, exist_ok=True)
        for old_png in glob.glob(os.path.join(frame_dir, "*.png")):
            try:
                os.remove(old_png)
            except OSError:
                pass

    session_basemap_path = os.path.join(layer_dir, "basemap.png")
    basemap_path = session_basemap_path
    session_counties_overlay_path = os.path.join(layer_dir, "counties_overlay.png")
    counties_overlay_path = session_counties_overlay_path
    session_states_overlay_path = os.path.join(layer_dir, "states_overlay.png")
    states_overlay_path = session_states_overlay_path
    session_rings_overlay_path = os.path.join(layer_dir, "rings_overlay.png")
    rings_overlay_path = session_rings_overlay_path
    static_overlay_path = os.path.join(layer_dir, "static_overlay.png")
    legend_overlay_path = os.path.join(layer_dir, "legend_overlay.png")
    if os.path.exists(session_basemap_path):
        try:
            os.remove(session_basemap_path)
        except OSError:
            pass
    if os.path.exists(static_overlay_path):
        try:
            os.remove(static_overlay_path)
        except OSError:
            pass
    if os.path.exists(legend_overlay_path):
        try:
            os.remove(legend_overlay_path)
        except OSError:
            pass
    if os.path.exists(session_counties_overlay_path):
        try:
            os.remove(session_counties_overlay_path)
        except OSError:
            pass
    if os.path.exists(session_states_overlay_path):
        try:
            os.remove(session_states_overlay_path)
        except OSError:
            pass
    if os.path.exists(session_rings_overlay_path):
        try:
            os.remove(session_rings_overlay_path)
        except OSError:
            pass

    _write_layer_manifest(
        layer_dir,
        request_id=request_id,
        station_id=station_id,
        product_label=product_label,
        level=level,
        user_tz=user_tz,
        status="rendering",
    )

    raw_files = []
    if isinstance(selected_files, (list, tuple, set)):
        raw_files = sorted(
            path
            for path in selected_files
            if isinstance(path, str) and os.path.isfile(path)
        )
    if not raw_files:
        raw_files = _load_request_file_paths(data_dir)
    if not raw_files:
        print("[ERROR] Archive layers: no files in download dir")
        return None

    parsed_files = []
    for file_path in raw_files:
        file_name = os.path.basename(file_path)
        dt = None

        m = re.search(r"(\d{8})_(\d{4,6})", file_name)
        if m:
            date_part, time_part = m.groups()
            if len(time_part) == 4:
                time_part += "00"
            try:
                dt = datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass

        if dt is None:
            m2 = re.search(
                r"(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})", file_name
            )
            if m2:
                yr, mo, dy, hh, mm, ss = m2.groups()
                try:
                    dt = datetime(
                        int(yr),
                        int(mo),
                        int(dy),
                        int(hh),
                        int(mm),
                        int(ss),
                        tzinfo=timezone.utc,
                    )
                except ValueError:
                    pass

        if dt is None:
            m3 = re.search(r"_(\d{12})$", file_name)
            if m3:
                ts = m3.group(1)
                try:
                    dt = datetime(
                        int(ts[0:4]),
                        int(ts[4:6]),
                        int(ts[6:8]),
                        int(ts[8:10]),
                        int(ts[10:12]),
                        tzinfo=timezone.utc,
                    )
                except ValueError:
                    pass

        if dt is not None:
            parsed_files.append((dt, file_path))

    if not parsed_files:
        print("[ERROR] Archive layers: no files with parseable timestamps")
        return None

    parsed_files.sort(key=lambda item: item[0])
    if latest_only:
        single = _select_single_frame_file(parsed_files, target_time_utc)
        selected = [single] if single else []
    else:
        frame_limit = max(1, int(frames or len(parsed_files)))
        selected = _downsample_evenly(parsed_files, frame_limit)

    # Default until first radar frame sets the shared map projection.
    map_projection = ccrs.PlateCarree()
    map_projection_name = "platecarree"

    def _compute_projected_extent_ratio(map_extent):
        """Return map panel width/height ratio in projection space."""
        min_lon, max_lon, min_lat, max_lat = map_extent
        corners_ll = np.array(
            [
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
            ]
        )
        try:
            corners_proj = map_projection.transform_points(
                ccrs.PlateCarree(),
                corners_ll[:, 0],
                corners_ll[:, 1],
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

        lat_span = max(1e-6, max_lat - min_lat)
        lon_span = max(1e-6, min(max_lon - min_lon, 360.0))
        lat_mid = (min_lat + max_lat) * 0.5
        lon_meters = lon_span * max(math.cos(math.radians(lat_mid)), 1e-3)
        return max(lon_meters / lat_span, 1e-3)

    def _refresh_layout_for_extent(map_extent):
        """Set dynamic figure width and text/logo scaling from current map extent."""
        nonlocal fig_width
        nonlocal hud_left_size, hud_right_size
        nonlocal city_text_size, cbar_title_size, logo_user_size

        map_panel_ratio = _compute_projected_extent_ratio(map_extent)
        panel_w = max(map_axes_pos[2], 1e-6)
        panel_h = max(map_axes_pos[3], 1e-6)
        fig_ratio = map_panel_ratio * (panel_h / panel_w)
        fig_width = max(fig_height * fig_ratio, 6.0)

        scale_factor = max(fig_width / 12.0, 0.55)
        hud_left_size = int(hud_left_size_base * scale_factor)
        hud_right_size = int(hud_right_size_base * scale_factor)
        city_text_size = int(city_text_size_base * scale_factor)
        cbar_title_size = int(cbar_title_size_base * scale_factor)
        logo_user_size = logo_user_size_base * scale_factor

    def _active_figsize():
        """Return current archive figure size with a safe square fallback pre-layout."""
        return ((fig_width if fig_width else fig_height), fig_height)

    def _compute_base_map_extent_from_radar(radar_obj):
        nonlocal map_projection, map_projection_name
        if custom_extent:
            min_lat, max_lat, min_lon, max_lon = custom_extent
            center_lat = (min_lat + max_lat) * 0.5
            center_lon = (min_lon + max_lon) * 0.5
        else:
            r_lat, r_lon = _safe_radar_site_coords(radar_obj, station_id)
            min_lat, max_lat, min_lon, max_lon = compute_radar_extent(
                r_lat, r_lon, padding_factor=1.0
            )
            center_lat = r_lat
            center_lon = r_lon

        try:
            map_projection = ccrs.LambertConformal(
                central_longitude=float(center_lon),
                central_latitude=float(center_lat),
            )
            map_projection_name = "local_lcc"
        except Exception:
            map_projection = ccrs.PlateCarree()
            map_projection_name = "platecarree"

        min_lat = max(-89.9, min_lat)
        max_lat = min(89.9, max_lat)
        return [min_lon, max_lon, min_lat, max_lat]

    def _compute_framed_extent(base_extent):
        min_lon, max_lon, min_lat, max_lat = base_extent

        lat_span = max_lat - min_lat
        lon_span = max_lon - min_lon
        min_lat -= lat_span * expand_bottom
        max_lat += lat_span * expand_top
        min_lon -= lon_span * expand_left
        max_lon += lon_span * expand_right

        min_lat = max(-89.9, min_lat)
        max_lat = min(89.9, max_lat)
        return [min_lon, max_lon, min_lat, max_lat]

    def _new_geo_axes(fig_obj, map_extent, facecolor="none"):
        ax_obj = fig_obj.add_axes(map_axes_pos, projection=map_projection)
        ax_obj.set_extent(map_extent, ccrs.PlateCarree())
        ax_obj.set_aspect("equal", adjustable="box")
        ax_obj.set_xticks([])
        ax_obj.set_yticks([])
        ax_obj.set_axis_off()
        if facecolor == "none":
            ax_obj.patch.set_alpha(0.0)
        else:
            ax_obj.set_facecolor(facecolor)
        return ax_obj

    def _draw_cities(ax_obj, min_lon, max_lon, min_lat, max_lat):
        if not (show_places and cities_data):
            return

        def _city_priority(city):
            try:
                return float(city.get("rank"))
            except (TypeError, ValueError):
                return 9999.0

        cities_sorted = sorted(cities_data, key=_city_priority)
        buffer = 0.05
        drawn_bboxes = []
        map_width = max_lon - min_lon
        map_height = max_lat - min_lat
        text_w = map_width * city_collision_w * density_scale
        text_h = map_height * city_collision_h * density_scale

        for city_obj in cities_sorted:
            try:
                city_name = city_obj.get("city", "Unknown")
                lat = float(city_obj.get("latitude"))
                lon = float(city_obj.get("longitude"))
            except (ValueError, TypeError):
                continue
            if not (
                min_lat + buffer <= lat <= max_lat - buffer
                and min_lon + buffer <= lon <= max_lon - buffer
            ):
                continue

            cand_x_min = lon - (text_w / 2.0)
            cand_x_max = lon + (text_w / 2.0)
            cand_y_min = lat - (text_h / 2.0)
            cand_y_max = lat + (text_h / 2.0)

            if any(
                cand_x_min < bx_max
                and cand_x_max > bx_min
                and cand_y_min < by_max
                and cand_y_max > by_min
                for bx_min, bx_max, by_min, by_max in drawn_bboxes
            ):
                continue

            txt = ax_obj.text(
                lon,
                lat,
                city_name.upper(),
                transform=ccrs.PlateCarree(),
                fontsize=city_text_size,
                color=city_text_color,
                fontname=font_family,
                fontweight=style_config.get("city_font_weight", "black"),
                fontstyle=style_config.get("city_font_style", "italic"),
                ha="center",
                va="center",
                zorder=zo["cities"],
                clip_on=True,
                alpha=float(style_config.get("city_text_alpha", 0.95)),
                bbox=dict(
                    facecolor=city_text_bg_color,
                    alpha=city_text_bg_alpha,
                    edgecolor="none",
                    boxstyle=style_config.get("city_box_style", "round,pad=0.2"),
                ),
            )
            txt.set_path_effects(
                [
                    PathEffects.withStroke(
                        linewidth=float(style_config.get("city_halo_width", 1.2)),
                        foreground=city_text_outline_color,
                    )
                ]
            )
            drawn_bboxes.append((cand_x_min, cand_x_max, cand_y_min, cand_y_max))

    tzinfo_user = tz.gettz(user_tz) or tz.gettz("America/New_York")
    frame_entries = []
    total = len(selected)
    radar_map_extent = None
    shared_map_extent = None
    alert_snapshot_cache = {}
    historical_alert_features = None
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    site_basemap_cache_dir = os.path.join(
        project_root, "basemap_cache", "radar", station_id.upper()
    )
    os.makedirs(site_basemap_cache_dir, exist_ok=True)
    site_basemap_cache_path = os.path.join(
        site_basemap_cache_dir, f"{station_id.upper()}.png"
    )
    site_counties_cache_path = os.path.join(
        site_basemap_cache_dir, "counties_overlay.png"
    )
    site_states_cache_path = os.path.join(site_basemap_cache_dir, "states_overlay.png")
    site_rings_cache_path = os.path.join(site_basemap_cache_dir, "rings_overlay.png")
    site_overlay_version_path = os.path.join(
        site_basemap_cache_dir, "overlay_version.txt"
    )
    site_overlay_version = "lcc_fullbleed_pad1p0_v1"
    # Canonical framing (no custom extent or margin expansion) can reuse the site
    # basemap image as a source asset.
    use_site_basemap_cache = (
        not custom_extent
        and expand_top == 0
        and expand_bottom == 0
        and expand_left == 0
        and expand_right == 0
    )

    # Full-bleed site overlay cache requires zero UI margins.
    use_site_overlay_cache = (
        use_site_basemap_cache
        and ui_margin_bottom <= 0.0
        and ui_margin_side <= 0.0
        and ui_margin_top <= 0.0
    )

    if use_site_overlay_cache:
        cached_version = ""
        if os.path.exists(site_overlay_version_path):
            try:
                with open(site_overlay_version_path, "r", encoding="utf-8") as vf:
                    cached_version = vf.read().strip()
            except Exception:
                cached_version = ""

        if cached_version != site_overlay_version:
            for stale_overlay in (
                site_counties_cache_path,
                site_states_cache_path,
                site_rings_cache_path,
            ):
                try:
                    if os.path.exists(stale_overlay):
                        os.remove(stale_overlay)
                except OSError:
                    pass

            try:
                with open(site_overlay_version_path, "w", encoding="utf-8") as vf:
                    vf.write(site_overlay_version)
            except Exception as version_err:
                print(
                    f"[WARN] Could not write site overlay version marker: {version_err}"
                )
    _site_overlay_cache_logged = set()

    alerts_overlay_enabled = show_alert_polygons and alerts_archive_utils is not None
    if show_alert_polygons and not alerts_overlay_enabled:
        print(
            "[WARN] Radar archive alert overlays disabled: alerts archive module unavailable"
        )

    if alerts_overlay_enabled and selected:
        try:
            alert_prefetch_start = selected[0][0] - timedelta(hours=1)
            alert_prefetch_end = selected[-1][0] + timedelta(hours=1)
            historical_alert_features = (
                alerts_archive_utils.prefetch_iem_historical_alert_features(
                    alert_prefetch_start,
                    alert_prefetch_end,
                    state=alert_state_filter,
                )
            )
        except Exception as alert_prefetch_err:
            print(
                "[WARN] Radar archive historical alert prefetch failed: "
                f"{alert_prefetch_err}"
            )
            historical_alert_features = None

    for i, (file_dt, fpath) in enumerate(selected):
        if progress_callback:
            progress_callback(i + 1, total)

        try:
            if level == "Level 3":
                try:
                    radar = pyart.io.read_nexrad_level3(fpath)
                except (NotImplementedError, ValueError):
                    import zlib
                    import tempfile

                    with open(fpath, "rb") as fh:
                        raw = fh.read()
                    zlib_start = -1
                    for magic in [b"\x78\xda", b"\x78\x9c", b"\x78\x01"]:
                        zlib_start = raw.find(magic, 0, 100)
                        if zlib_start != -1:
                            break
                    if zlib_start == -1:
                        raise
                    d = zlib.decompressobj()
                    header_block = d.decompress(raw[zlib_start:])
                    remaining = d.unused_data
                    full_nids = header_block + remaining
                    tmp_path = tempfile.mktemp(suffix=".nids")
                    with open(tmp_path, "wb") as tmp:
                        tmp.write(full_nids)
                    try:
                        radar = pyart.io.read_nexrad_level3(tmp_path)
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass
            else:
                try:
                    radar = pyart.io.read_nexrad_archive(fpath)
                except Exception as read_err:
                    err_text = str(read_err)
                    if "unpack requires a buffer" in err_text:
                        print(
                            "[WARN] Archive layered Level 2 frame unreadable; "
                            f"removing cached file and skipping: {os.path.basename(fpath)}"
                        )
                        try:
                            os.remove(fpath)
                        except OSError:
                            pass
                        continue
                    raise

            _normalize_radar_site_coords(radar, station_id)

            available_fields = list(radar.fields.keys())
            if not available_fields:
                continue
            field_name = (
                available_fields[0] if level == "Level 3" else product_label.lower()
            )

            if "velocity" in product_label.lower() or product_label in {
                "N0G",
                "N0U",
                "NVW",
                "N0S",
            }:
                field_name = _calculate_srv(radar, sm_speed, sm_dir)

            if field_name in radar.fields:
                data = radar.fields[field_name]["data"]
                best_sweep = 0
                max_valid_points = 0
                for sweep_idx in range(radar.nsweeps):
                    sweep_slice = radar.get_slice(sweep_idx)
                    sweep_data = data[sweep_slice]
                    valid_in_sweep = np.sum(
                        ~sweep_data.mask
                        if hasattr(sweep_data, "mask")
                        else ~np.isnan(sweep_data)
                    )
                    if valid_in_sweep > max_valid_points:
                        max_valid_points = valid_in_sweep
                        best_sweep = sweep_idx
                sweep_to_plot = best_sweep
            else:
                sweep_to_plot = 0

            raw_dt = pyart.util.datetimes_from_radar(radar)[0]
            if isinstance(raw_dt, np.datetime64):
                unix_ts = (
                    raw_dt - np.datetime64("1970-01-01T00:00:00")
                ) / np.timedelta64(1, "s")
                dt_utc = datetime.fromtimestamp(float(unix_ts), tz=timezone.utc)
            elif isinstance(raw_dt, datetime):
                dt_utc = (
                    raw_dt.replace(tzinfo=timezone.utc)
                    if raw_dt.tzinfo is None
                    else raw_dt
                )
            elif hasattr(raw_dt, "year") and hasattr(raw_dt, "month"):
                dt_utc = datetime(
                    raw_dt.year,
                    raw_dt.month,
                    raw_dt.day,
                    raw_dt.hour,
                    raw_dt.minute,
                    raw_dt.second,
                    tzinfo=timezone.utc,
                )
            else:
                dt_utc = file_dt
            dt_local = dt_utc.astimezone(tzinfo_user)

            display_product = L3_PRODUCTS.get(product_label, product_label)
            if level == "Level 2":
                level2_names = {
                    "reflectivity": "Base Reflectivity",
                    "velocity": "Base Velocity",
                    "cross_correlation_ratio": "Correlation Coefficient",
                }
                display_product = level2_names.get(
                    field_name, field_name.replace("_", " ").title()
                )
            if field_name == "storm_relative_velocity":
                display_product = "Storm-Relative Velocity"

            norm = None
            category_ticks = None
            category_labels = None
            cc_codes = {"N0M", "NCR"}
            velocity_codes = {"N0G", "N0U", "NVW", "N0S", "NVL"}
            zdr_codes = {"NBU", "N0X"}
            precip_hourly_codes = {"DHR", "DPR", "N1P"}
            precip_accum_codes = {"DPA", "DAA"}
            precip_total_codes = {"DTA", "NRR", "NTP"}
            hca_codes = {"N0H", "HHC", "NAH", "NBH", "N1H", "N2H", "N3H"}

            if "correlation" in field_name.lower() or "CC" in field_name:
                cmap, vmin, vmax = create_grs_cc_cmap(), 0.7, 1.0
            elif (
                "velocity" in field_name.lower()
                or field_name == "storm_relative_velocity"
                or product_label in velocity_codes
            ):
                cmap, vmin, vmax = create_grs_bv_cmap(), -160, 160
            elif (
                "differential_reflectivity" in field_name.lower()
                or "ZDR" in product_label
                or product_label in zdr_codes
            ):
                cmap, vmin, vmax = create_grs_zdr_cmap(), -2.0, 8.0
            elif (
                "vertically_integrated_liquid" in field_name.lower()
                or "DVL" in product_label
            ):
                cmap, vmin, vmax = create_grs_vil_cmap(), 0, 80
            elif "echo_tops" in field_name.lower() or "NET" in product_label:
                cmap, vmin, vmax = create_grs_et_cmap(), 0, 70
            elif "spectrum_width" in field_name.lower() or "N0S" in product_label:
                cmap, vmin, vmax = create_grs_sw_cmap(), 0, 30
            elif product_label in precip_hourly_codes:
                cmap, vmin, vmax = create_grs_precip_cmap(), 0.0, 4.0
            elif product_label in precip_accum_codes:
                cmap, vmin, vmax = create_grs_dpa_cmap(), 0.0, 8.0
            elif product_label in precip_total_codes:
                cmap, vmin, vmax = create_grs_precip_total_cmap(), 0.0, 20.0
            elif product_label in hca_codes:
                cmap, norm, category_ticks, category_labels = create_grs_hca_style()
                vmin, vmax = 0.5, 10.5
            elif product_label in cc_codes:
                cmap, vmin, vmax = create_grs_cc_cmap(), 0.7, 1.0
            else:
                cmap, vmin, vmax = create_grs_br_cmap(), -10, 95

            if radar_map_extent is None or shared_map_extent is None:
                radar_map_extent = _compute_base_map_extent_from_radar(radar)
                shared_map_extent = _compute_framed_extent(radar_map_extent)
                _refresh_layout_for_extent(shared_map_extent)

                if use_site_basemap_cache and os.path.exists(site_basemap_cache_path):
                    try:
                        cached_img = imageio.imread(site_basemap_cache_path)
                        cached_h, cached_w = cached_img.shape[:2]
                        map_w_frac = max(map_axes_pos[2], 1e-6)
                        map_h_frac = max(map_axes_pos[3], 1e-6)
                        fig_width = cached_w / float(fig_dpi * map_w_frac)
                        fig_height = cached_h / float(fig_dpi * map_h_frac)

                        scale_factor = max(fig_width / 12.0, 0.55)
                        hud_left_size = int(hud_left_size_base * scale_factor)
                        hud_right_size = int(hud_right_size_base * scale_factor)
                        city_text_size = int(city_text_size_base * scale_factor)
                        cbar_title_size = int(cbar_title_size_base * scale_factor)
                        logo_user_size = logo_user_size_base * scale_factor

                        print(
                            "[CACHE] using site basemap dimensions "
                            f"{cached_w}x{cached_h} for aligned layered output"
                        )
                    except Exception as cache_size_err:
                        print(
                            "[WARN] Failed to inspect site basemap dimensions: "
                            f"{cache_size_err}"
                        )

                if use_site_overlay_cache:
                    # Site basemap cache is full-bleed. Match that layout so every
                    # overlay shares the same projection and pixel alignment.
                    map_axes_pos = [0.0, 0.0, 1.0, 1.0]
                    _refresh_layout_for_extent(shared_map_extent)

            min_lon, max_lon, min_lat, max_lat = shared_map_extent
            radar_min_lon, radar_max_lon, radar_min_lat, radar_max_lat = (
                radar_map_extent
            )

            if use_site_overlay_cache:
                basemap_path = site_basemap_cache_path
                counties_overlay_path = site_counties_cache_path
                states_overlay_path = site_states_cache_path
                rings_overlay_path = site_rings_cache_path
            else:
                basemap_path = session_basemap_path
                counties_overlay_path = session_counties_overlay_path
                states_overlay_path = session_states_overlay_path
                rings_overlay_path = session_rings_overlay_path

            if (
                not use_site_overlay_cache
                and use_site_basemap_cache
                and os.path.exists(site_basemap_cache_path)
                and not os.path.exists(basemap_path)
            ):
                try:
                    cached_rgba = _to_rgba(imageio.imread(site_basemap_cache_path))
                    cached_h, cached_w = cached_rgba.shape[:2]

                    canvas_w = int(round(_active_figsize()[0] * fig_dpi))
                    canvas_h = int(round(_active_figsize()[1] * fig_dpi))
                    map_w_px = int(round(map_axes_pos[2] * canvas_w))
                    map_h_px = int(round(map_axes_pos[3] * canvas_h))
                    map_left_px = int(round(map_axes_pos[0] * canvas_w))
                    map_bottom_px = int(round(map_axes_pos[1] * canvas_h))

                    if map_w_px == cached_w and map_h_px == cached_h:
                        bg_rgba = matplotlib.colors.to_rgba(
                            _safe_color(map_bg_color, "#f2f2f2")
                        )
                        canvas = np.empty((canvas_h, canvas_w, 4), dtype=np.uint8)
                        canvas[:, :, 0] = int(round(bg_rgba[0] * 255))
                        canvas[:, :, 1] = int(round(bg_rgba[1] * 255))
                        canvas[:, :, 2] = int(round(bg_rgba[2] * 255))
                        canvas[:, :, 3] = 255

                        y_top = max(0, canvas_h - map_bottom_px - map_h_px)
                        x_left = max(0, map_left_px)
                        canvas[
                            y_top : y_top + map_h_px,
                            x_left : x_left + map_w_px,
                            :,
                        ] = cached_rgba

                        imageio.imwrite(basemap_path, canvas)
                        print(
                            "[CACHE] wrapped site basemap into session canvas -> "
                            f"{basemap_path}"
                        )
                    else:
                        print(
                            "[CACHE] site basemap size mismatch for wrapped canvas "
                            f"(cached={cached_w}x{cached_h}, map={map_w_px}x{map_h_px}); "
                            "falling back to rendered basemap"
                        )
                except Exception as wrapped_cache_err:
                    print(
                        "[WARN] Failed to wrap cached basemap into session canvas: "
                        f"{wrapped_cache_err}"
                    )

            if use_site_overlay_cache:
                cache_layers = [
                    ("basemap", basemap_path),
                    ("counties", counties_overlay_path),
                    ("states", states_overlay_path),
                ]
                if show_rings:
                    cache_layers.append(("rings", rings_overlay_path))
                for layer_name, layer_path in cache_layers:
                    if layer_name in _site_overlay_cache_logged:
                        continue
                    status = "hit" if os.path.exists(layer_path) else "miss"
                    print(
                        f"[CACHE] site overlay {status}: {station_id.upper()} {layer_name} -> {layer_path}"
                    )
                    _site_overlay_cache_logged.add(layer_name)

            if not os.path.exists(basemap_path):
                fig_base = plt.figure(figsize=_active_figsize(), dpi=fig_dpi)
                fig_base.patch.set_facecolor(map_bg_color)
                ax_base = _new_geo_axes(
                    fig_base, shared_map_extent, facecolor=map_bg_color
                )

                if use_site_overlay_cache:
                    # Canonical site basemap: land + ocean only (no borders/roads).
                    ax_base.add_feature(
                        _FEATURE_LAND, facecolor=land_color, zorder=zo["land"]
                    )
                else:
                    ax_base.add_feature(
                        _FEATURE_LAND, facecolor=land_color, zorder=zo["land"]
                    )
                    if show_lakes:
                        lake_geoms = _subset_geometries_by_extent(
                            _LAKES_GEOMS,
                            _LAKES_BOUNDS,
                            min_lat,
                            max_lat,
                            min_lon,
                            max_lon,
                        )
                        if lake_geoms:
                            ax_base.add_geometries(
                                lake_geoms,
                                ccrs.PlateCarree(),
                                facecolor=lake_color,
                                edgecolor=lake_outline_color,
                                linewidth=lake_outline_width,
                                zorder=zo["water"],
                            )
                    if show_rivers:
                        river_geoms = _subset_geometries_by_extent(
                            _RIVERS_GEOMS,
                            _RIVERS_BOUNDS,
                            min_lat,
                            max_lat,
                            min_lon,
                            max_lon,
                        )
                        if river_geoms:
                            ax_base.add_geometries(
                                river_geoms,
                                ccrs.PlateCarree(),
                                facecolor="none",
                                edgecolor=river_color,
                                linewidth=river_width,
                                zorder=zo["water"],
                            )
                    if show_highways:
                        road_geoms = _subset_geometries_by_extent(
                            _ROADS_GEOMS,
                            _ROADS_BOUNDS,
                            min_lat,
                            max_lat,
                            min_lon,
                            max_lon,
                        )
                        if road_geoms:
                            ax_base.add_geometries(
                                road_geoms,
                                ccrs.PlateCarree(),
                                facecolor="none",
                                edgecolor=highway_color,
                                linewidth=highway_width,
                                alpha=highway_opacity,
                                zorder=zo["highways"],
                            )
                plt.savefig(
                    basemap_path,
                    format="png",
                    dpi=fig_dpi,
                    transparent=False,
                    bbox_inches=None,
                    pad_inches=0,
                )
                plt.close(fig_base)

            timestamp_key = dt_utc.strftime("%Y%m%d_%H%M%S")
            radar_path = os.path.join(radar_dir, f"{timestamp_key}.png")
            alerts_path = os.path.join(alerts_dir, f"{timestamp_key}.png")
            cities_path = os.path.join(cities_dir, f"{timestamp_key}.png")
            hud_right_path = os.path.join(hud_right_dir, f"{timestamp_key}.png")
            layer_frame_path = os.path.join(layer_dir, f"{timestamp_key}.png")

            radar_cache_path = None
            if not custom_extent:
                cache_geom_token = (
                    f"{map_projection_name}_"
                    f"{int(round(_active_figsize()[0] * fig_dpi))}x"
                    f"{int(round(_active_figsize()[1] * fig_dpi))}"
                )
                radar_cache_name = _radar_layer_cache_filename(
                    station_id=station_id,
                    product_label=product_label,
                    scan_dt_utc=dt_utc,
                    storm_relative=(field_name == "storm_relative_velocity"),
                    sm_speed=sm_speed,
                    sm_dir=sm_dir,
                    geometry_token=cache_geom_token,
                )
                radar_cache_day_dir = _date_partition_dir(radar_cache_root, dt_utc)
                os.makedirs(radar_cache_day_dir, exist_ok=True)
                radar_cache_path = os.path.join(radar_cache_day_dir, radar_cache_name)

            alert_geoms_by_color = {}
            if alerts_overlay_enabled:
                cache_key = dt_utc.strftime("%Y%m%d%H%M")
                if cache_key not in alert_snapshot_cache:
                    try:
                        feature_collection, _ = (
                            alerts_archive_utils.get_historical_alert_polygons_geojson(
                                valid_time=dt_utc,
                                bulk_features=historical_alert_features,
                                state_code=alert_state_filter,
                                category_filter="All Alerts",
                                wfo_code=None,
                                custom_extent=[min_lat, max_lat, min_lon, max_lon],
                                prefer_storm_polygons=True,
                            )
                        )
                        parsed_geoms_by_color = {}
                        for feature in feature_collection.get("features", []):
                            props = (
                                feature.get("properties", {})
                                if isinstance(feature, dict)
                                else {}
                            )
                            event_name = str(props.get("event", "") or "").strip()
                            if not _is_radar_alert_event_allowed(event_name):
                                continue
                            event_color = _safe_color(props.get("color"), "#C0C0C0")
                            try:
                                geom = shape(feature.get("geometry"))
                            except Exception:
                                continue
                            # Extract usable polygons (handle GeometryCollections from make_valid)
                            try:
                                geom = alerts_archive_utils._extract_polygons_from_geometry(
                                    geom
                                )
                            except Exception:
                                pass
                            if geom is None or geom.is_empty:
                                continue
                            parsed_geoms_by_color.setdefault(event_color, []).append(
                                geom
                            )
                        alert_snapshot_cache[cache_key] = parsed_geoms_by_color
                    except Exception as e:
                        print(f"[WARN] Radar archive alert overlay failed: {e}")
                        alert_snapshot_cache[cache_key] = {}

                alert_geoms_by_color = alert_snapshot_cache.get(cache_key, {})

            radar_layer_ready = False
            if radar_cache_path and os.path.exists(radar_cache_path):
                try:
                    expected_w = int(round(_active_figsize()[0] * fig_dpi))
                    expected_h = int(round(_active_figsize()[1] * fig_dpi))
                    cached_rgba = imageio.imread(radar_cache_path)
                    cached_h, cached_w = cached_rgba.shape[:2]
                    if (
                        abs(cached_w - expected_w) <= 2
                        and abs(cached_h - expected_h) <= 2
                    ):
                        shutil.copy2(radar_cache_path, radar_path)
                        radar_layer_ready = True
                    else:
                        print(
                            "[CACHE] radar layer size mismatch "
                            f"(cached={cached_w}x{cached_h}, expected={expected_w}x{expected_h}); re-rendering"
                        )
                except OSError as copy_err:
                    print(
                        f"[WARN] Could not read radar layer cache for {timestamp_key}: {copy_err}"
                    )

            if not radar_layer_ready:
                fig_radar = plt.figure(figsize=_active_figsize(), dpi=fig_dpi)
                fig_radar.patch.set_alpha(0.0)
                ax_radar = _new_geo_axes(fig_radar, radar_map_extent, facecolor="none")
                display = pyart.graph.RadarMapDisplay(radar)
                display.plot_ppi_map(
                    field_name,
                    sweep=sweep_to_plot,
                    vmin=vmin,
                    vmax=vmax,
                    cmap=cmap,
                    norm=norm,
                    embellish=False,
                    add_grid_lines=False,
                    resolution="10m",
                    title_flag=False,
                    colorbar_flag=False,
                    projection=map_projection,
                    ax=ax_radar,
                    min_lat=radar_min_lat,
                    max_lat=radar_max_lat,
                    min_lon=radar_min_lon,
                    max_lon=radar_max_lon,
                    zorder=zo["radar_data"],
                    edgecolors="face",
                    linewidths=0,
                )
                ax_radar.set_extent(radar_map_extent, ccrs.PlateCarree())
                ax_radar.set_xticks([])
                ax_radar.set_yticks([])
                ax_radar.set_axis_off()
                _suppress_geo_labels(ax_radar, fig_radar)
                plt.savefig(
                    radar_path,
                    format="png",
                    dpi=fig_dpi,
                    transparent=True,
                    bbox_inches=None,
                    pad_inches=0,
                )
                plt.close(fig_radar)
                if radar_cache_path:
                    try:
                        shutil.copy2(radar_path, radar_cache_path)
                    except OSError as copy_err:
                        print(
                            f"[WARN] Could not update radar layer cache for {timestamp_key}: {copy_err}"
                        )

            fig_alerts = plt.figure(figsize=_active_figsize(), dpi=fig_dpi)
            fig_alerts.patch.set_alpha(0.0)
            ax_alerts = _new_geo_axes(fig_alerts, shared_map_extent, facecolor="none")
            ax_alerts.set_axis_off()
            if alert_geoms_by_color:
                for color, geoms in alert_geoms_by_color.items():
                    if not geoms:
                        continue
                    if show_alert_outline:
                        ax_alerts.add_geometries(
                            geoms,
                            ccrs.PlateCarree(),
                            facecolor="none",
                            edgecolor=alert_outline_color,
                            linewidth=alert_outline_width,
                            alpha=alert_outline_alpha,
                            zorder=zo["alert_polygons"] - 0.1,
                        )
                    ax_alerts.add_geometries(
                        geoms,
                        ccrs.PlateCarree(),
                        facecolor="none",
                        edgecolor=color,
                        linewidth=alert_line_width,
                        alpha=alert_alpha,
                        zorder=zo["alert_polygons"],
                    )
            plt.savefig(
                alerts_path,
                format="png",
                dpi=fig_dpi,
                transparent=True,
                bbox_inches=None,
                pad_inches=0,
            )
            plt.close(fig_alerts)

            fig_cities = plt.figure(figsize=_active_figsize(), dpi=fig_dpi)
            fig_cities.patch.set_alpha(0.0)
            ax_cities = _new_geo_axes(fig_cities, shared_map_extent, facecolor="none")
            _draw_cities(ax_cities, min_lon, max_lon, min_lat, max_lat)
            plt.savefig(
                cities_path,
                format="png",
                dpi=fig_dpi,
                transparent=True,
                bbox_inches=None,
                pad_inches=0,
            )
            plt.close(fig_cities)

            if not os.path.exists(counties_overlay_path):
                fig_counties = plt.figure(figsize=_active_figsize(), dpi=fig_dpi)
                fig_counties.patch.set_alpha(0.0)
                ax_counties = _new_geo_axes(
                    fig_counties, shared_map_extent, facecolor="none"
                )
                county_feature = None
                try:
                    if site_state_abbr:
                        county_feature = CensusCounties.get_feature_for_state(
                            site_state_abbr
                        )
                    if county_feature is None:
                        county_feature = CensusCounties.get_feature()
                except Exception:
                    county_feature = None

                if county_feature is not None:
                    ax_counties.add_feature(
                        county_feature,
                        linewidth=county_width,
                        edgecolor=county_color,
                        facecolor="none",
                        alpha=1.0,
                        zorder=zo["counties"],
                    )
                else:
                    ax_counties.add_feature(
                        USCOUNTIES.with_scale("5m"),
                        linewidth=county_width,
                        edgecolor=county_color,
                        alpha=1.0,
                        zorder=zo["counties"],
                    )
                os.makedirs(os.path.dirname(counties_overlay_path), exist_ok=True)
                plt.savefig(
                    counties_overlay_path,
                    format="png",
                    dpi=fig_dpi,
                    transparent=True,
                    bbox_inches=None,
                    pad_inches=0,
                )
                plt.close(fig_counties)

            if not os.path.exists(states_overlay_path):
                state_feature = CensusStates.get_feature()
                if state_feature is not None:
                    fig_states = plt.figure(figsize=_active_figsize(), dpi=fig_dpi)
                    fig_states.patch.set_alpha(0.0)
                    ax_states = _new_geo_axes(
                        fig_states, shared_map_extent, facecolor="none"
                    )
                    ax_states.add_feature(
                        state_feature,
                        linewidth=state_width,
                        edgecolor=state_color,
                        facecolor="none",
                        alpha=1.0,
                        zorder=zo["states"],
                    )
                    os.makedirs(os.path.dirname(states_overlay_path), exist_ok=True)
                    plt.savefig(
                        states_overlay_path,
                        format="png",
                        dpi=fig_dpi,
                        transparent=True,
                        bbox_inches=None,
                        pad_inches=0,
                    )
                    plt.close(fig_states)

            if (
                show_rings
                and radar_map_extent
                and not os.path.exists(rings_overlay_path)
            ):
                fig_rings = plt.figure(figsize=_active_figsize(), dpi=fig_dpi)
                fig_rings.patch.set_alpha(0.0)
                ax_ring = _new_geo_axes(fig_rings, radar_map_extent, facecolor="none")
                ring_display = pyart.graph.RadarMapDisplay(radar)
                ring_display.ax = ax_ring
                for distance in [46300, 92600, 185200]:
                    ring_display.plot_range_ring(
                        distance / 1000,
                        color=ring_color,
                        line_style=style_config.get("ring_line_style", "--"),
                        linewidth=ring_width,
                        alpha=float(style_config.get("ring_alpha", 0.5)),
                        zorder=zo["range_rings"],
                    )
                os.makedirs(os.path.dirname(rings_overlay_path), exist_ok=True)
                plt.savefig(
                    rings_overlay_path,
                    format="png",
                    dpi=fig_dpi,
                    transparent=True,
                    bbox_inches=None,
                    pad_inches=0,
                )
                plt.close(fig_rings)

            if not os.path.exists(static_overlay_path):
                fig_static = plt.figure(figsize=_active_figsize(), dpi=fig_dpi)
                fig_static.patch.set_alpha(0.0)

                ax_static_map = fig_static.add_axes(map_axes_pos)
                ax_static_map.set_axis_off()

                hud_left = f"{site_display_name}\n{level}\n{display_product}"
                ax_static_map.annotate(
                    hud_left,
                    xy=(hud_left_x, hud_left_y),
                    xycoords="axes fraction",
                    fontsize=hud_left_size,
                    fontname=font_family,
                    fontweight=style_config.get("hud_font_weight", "black"),
                    fontstyle=style_config.get("hud_font_style", "italic"),
                    color=hud_left_text_color,
                    va="top",
                    ha="left",
                    linespacing=float(style_config.get("hud_line_spacing", 1.15)),
                    bbox=dict(
                        boxstyle=style_config.get(
                            "hud_left_box_style", "round,pad=0.5"
                        ),
                        fc=hud_left_bg_color,
                        ec=hud_left_edge_color,
                        alpha=hud_left_alpha,
                    ),
                    zorder=zo["hud"],
                )

                if os.path.exists(logo_file):
                    n_img = mpimg.imread(logo_file)
                    ax_static_map.add_artist(
                        AnnotationBbox(
                            OffsetImage(n_img, zoom=logo_user_size),
                            (logo_user_x, logo_user_y),
                            xycoords="axes fraction",
                            frameon=False,
                            box_alignment=(1, 0),
                            zorder=zo["logos"],
                        )
                    )

                plt.savefig(
                    static_overlay_path,
                    format="png",
                    dpi=fig_dpi,
                    transparent=True,
                    bbox_inches=None,
                    pad_inches=0,
                )
                plt.close(fig_static)

            if not os.path.exists(legend_overlay_path):
                fig_legend = plt.figure(figsize=_active_figsize(), dpi=fig_dpi)
                fig_legend.patch.set_alpha(0.0)

                # Draw legend in map-relative figure coordinates and clamp to the
                # basemap extent so it never spills outside the map frame.
                map_left, map_bottom, map_width, map_height = map_axes_pos
                rel_x = min(0.98, max(0.0, legend_box_x))
                rel_y = min(0.98, max(0.0, legend_box_y))
                rel_w = min(1.0, max(0.02, legend_box_w))
                rel_h = min(1.0, max(0.03, legend_box_h))

                box_x = map_left + (rel_x * map_width)
                if ui_margin_bottom > 0:
                    # In footer layout, align legend top with map bottom.
                    box_y = max(0.0, map_bottom - (rel_h * map_height))
                else:
                    box_y = map_bottom + (rel_y * map_height)
                box_w = rel_w * map_width
                box_h = rel_h * map_height

                map_right = map_left + map_width
                map_top = map_bottom + map_height
                box_w = max(0.02, min(box_w, map_right - box_x))
                box_h = max(0.02, min(box_h, map_top - box_y))

                legend_panel = matplotlib.patches.Rectangle(
                    (box_x, box_y),
                    box_w,
                    box_h,
                    transform=fig_legend.transFigure,
                    facecolor=style_config.get("legend_panel_bg_color", "white"),
                    edgecolor=style_config.get("legend_panel_edge_color", "none"),
                    alpha=float(style_config.get("legend_panel_bg_alpha", 0.9)),
                    zorder=0,
                )
                fig_legend.add_artist(legend_panel)

                cbar_pad_x = min(box_w * 0.15, 0.02)
                cbar_pad_y = min(box_h * 0.25, 0.015)
                cbar_h = max(0.01, box_h * 0.20)
                cbar_rect = [
                    box_x + cbar_pad_x,
                    box_y + box_h - cbar_h - cbar_pad_y,
                    max(0.02, box_w - (2.0 * cbar_pad_x)),
                    cbar_h,
                ]
                cax = fig_legend.add_axes(cbar_rect)
                cax.set_zorder(zo["hud"] + 10)

                norm_for_bar = (
                    norm
                    if norm is not None
                    else matplotlib.colors.Normalize(vmin=vmin, vmax=vmax)
                )
                scalar = matplotlib.cm.ScalarMappable(norm=norm_for_bar, cmap=cmap)
                scalar.set_array([])
                cbar = fig_legend.colorbar(scalar, cax=cax, orientation="horizontal")
                cbar.set_label("")
                cbar.ax.set_xlabel("")

                cax.set_facecolor(style_config.get("cbar_bg_color", "#f2f2f2"))
                cax.patch.set_alpha(float(style_config.get("cbar_bg_alpha", 0.9)))
                cbar_tick_color = style_config.get("cbar_tick_color", "#000000")
                cbar.ax.tick_params(
                    axis="x",
                    colors=cbar_tick_color,
                    labelsize=int(style_config.get("cbar_tick_labelsize", 10)),
                    pad=int(style_config.get("cbar_tick_pad", 3)),
                    width=float(style_config.get("cbar_tick_width", 0.8)),
                )
                if category_ticks and category_labels:
                    cbar.set_ticks(category_ticks)
                    cbar.set_ticklabels(category_labels)
                    cbar.ax.tick_params(axis="x", labelsize=8, colors=cbar_tick_color)
                for tick in cbar.ax.get_xticklabels():
                    tick.set_fontname(font_family)
                    tick.set_fontweight("bold")
                    tick.set_color(cbar_tick_color)
                cbar.outline.set_edgecolor(
                    style_config.get("cbar_outline_color", "#cbd5e1")
                )
                cbar.outline.set_linewidth(
                    float(style_config.get("cbar_outline_width", 1.0))
                )

                # Draw static alert legend entries below the colorbar.
                alert_legend_height = max(0.02, box_h - cbar_h - (4.5 * cbar_pad_y))
                alert_legend_rect = [
                    box_x + cbar_pad_x,
                    box_y + cbar_pad_y,
                    max(0.02, box_w - (2.0 * cbar_pad_x)),
                    alert_legend_height,
                ]
                alert_ax = fig_legend.add_axes(alert_legend_rect)
                alert_ax.set_xlim(0, 100)
                entries_to_draw = _radar_static_warning_legend_entries()
                n_cols = 4
                alert_ax.set_ylim(0, 2.2)
                alert_ax.axis("off")
                alert_ax.set_zorder(zo["hud"] + 11)

                # Draw alert legend entries
                col_width = 100.0 / float(n_cols)
                label_fontsize = 8
                for idx, (alert_type, alert_color) in enumerate(entries_to_draw):
                    col_idx = idx % n_cols
                    y_pos = 0.65
                    x_origin = (col_idx * col_width) + 1.5
                    safe_color = _safe_color(alert_color, "#C0C0C0")

                    square = matplotlib.patches.Rectangle(
                        (x_origin, y_pos - 0.2),
                        2.5,
                        0.4,
                        transform=alert_ax.transData,
                        facecolor=safe_color,
                        edgecolor="#333333",
                        linewidth=0.5,
                        zorder=zo["hud"] + 12,
                    )
                    alert_ax.add_patch(square)

                    alert_ax.text(
                        x_origin + 4.0,
                        y_pos,
                        alert_type,
                        fontsize=label_fontsize,
                        fontname=font_family,
                        fontweight=style_config.get("alert_legend_font_weight", "bold"),
                        fontstyle=style_config.get("alert_legend_font_style", "italic"),
                        va="center",
                        ha="left",
                        color=style_config.get("alert_legend_text_color", "#000000"),
                        zorder=zo["hud"] + 12,
                    )

                plt.savefig(
                    legend_overlay_path,
                    format="png",
                    dpi=fig_dpi,
                    transparent=True,
                    bbox_inches=None,
                    pad_inches=0,
                )
                plt.close(fig_legend)

            fig_hud_right = plt.figure(figsize=_active_figsize(), dpi=fig_dpi)
            fig_hud_right.patch.set_alpha(0.0)
            ax_hud_right = fig_hud_right.add_axes(map_axes_pos)
            ax_hud_right.set_axis_off()

            hud_right = (
                f"{dt_local.strftime('%m/%d/%Y')}\n{dt_local.strftime('%I:%M %p %Z')}"
            )
            ax_hud_right.annotate(
                hud_right,
                xy=(hud_right_x, hud_right_y),
                xycoords="axes fraction",
                fontsize=hud_right_size,
                fontname=font_family,
                fontweight=style_config.get("hud_font_weight", "black"),
                fontstyle=style_config.get("hud_font_style", "italic"),
                color=hud_right_text_color,
                va="top",
                ha="right",
                bbox=dict(
                    boxstyle=style_config.get("hud_right_box_style", "round,pad=0.4"),
                    fc=hud_right_bg_color,
                    ec=hud_right_edge_color,
                    alpha=hud_right_alpha,
                ),
                zorder=zo["hud"],
            )

            plt.savefig(
                hud_right_path,
                format="png",
                dpi=fig_dpi,
                transparent=True,
                bbox_inches=None,
                pad_inches=0,
            )
            plt.close(fig_hud_right)

            composite_rgba = None
            for source_path in [
                radar_path,
                alerts_path,
                cities_path,
                counties_overlay_path,
                states_overlay_path,
                rings_overlay_path,
                static_overlay_path,
                legend_overlay_path,
                hud_right_path,
            ]:
                if not os.path.exists(source_path):
                    continue
                layer_rgba = _to_rgba(imageio.imread(source_path))
                if composite_rgba is None:
                    composite_rgba = np.zeros_like(layer_rgba)
                composite_rgba = _composite_rgba_full(composite_rgba, layer_rgba)

            if composite_rgba is None:
                continue

            imageio.imwrite(layer_frame_path, composite_rgba)

            frame_entries.append(
                {
                    "index": i,
                    "path": layer_frame_path,
                    "radar_path": radar_path,
                    "alerts_path": alerts_path,
                    "cities_path": cities_path,
                    "counties_path": counties_overlay_path
                    if os.path.exists(counties_overlay_path)
                    else None,
                    "states_path": states_overlay_path
                    if os.path.exists(states_overlay_path)
                    else None,
                    "rings_path": rings_overlay_path
                    if os.path.exists(rings_overlay_path)
                    else None,
                    "legend_path": legend_overlay_path
                    if os.path.exists(legend_overlay_path)
                    else None,
                    "hud_right_path": hud_right_path,
                    "timestamp_utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "timestamp_local": dt_local.strftime("%Y-%m-%d %I:%M %p %Z"),
                }
            )
        except Exception as e:
            print(
                f"[WARN] Archive layered frame error ({os.path.basename(fpath)}): {e}"
            )
            import traceback

            traceback.print_exc()
            continue

    if not frame_entries or not os.path.exists(basemap_path):
        _write_layer_manifest(layer_dir, status="empty", frame_count=0)
        return None

    manifest = _write_layer_manifest(
        layer_dir,
        status="ready",
        frame_count=len(frame_entries),
        basemap_file=os.path.basename(basemap_path),
        basemap_source_path=basemap_path,
        basemap_scope="site" if use_site_overlay_cache else "session",
        counties_file=os.path.basename(counties_overlay_path)
        if os.path.exists(counties_overlay_path)
        else None,
        counties_source_path=counties_overlay_path
        if os.path.exists(counties_overlay_path)
        else None,
        counties_scope="site"
        if (use_site_overlay_cache and os.path.exists(counties_overlay_path))
        else "session",
        states_file=os.path.basename(states_overlay_path)
        if os.path.exists(states_overlay_path)
        else None,
        states_source_path=states_overlay_path
        if os.path.exists(states_overlay_path)
        else None,
        states_scope="site"
        if (use_site_overlay_cache and os.path.exists(states_overlay_path))
        else "session",
        rings_file=os.path.basename(rings_overlay_path)
        if os.path.exists(rings_overlay_path)
        else None,
        rings_source_path=rings_overlay_path
        if os.path.exists(rings_overlay_path)
        else None,
        rings_scope="site"
        if (use_site_overlay_cache and os.path.exists(rings_overlay_path))
        else "session",
        last_access_utc=_iso_utc(datetime.now(timezone.utc)),
    )

    return {
        "basemap_path": basemap_path,
        "static_overlay_path": static_overlay_path
        if os.path.exists(static_overlay_path)
        else None,
        "legend_overlay_path": legend_overlay_path
        if os.path.exists(legend_overlay_path)
        else None,
        "counties_overlay_path": counties_overlay_path
        if os.path.exists(counties_overlay_path)
        else None,
        "states_overlay_path": states_overlay_path
        if os.path.exists(states_overlay_path)
        else None,
        "rings_overlay_path": rings_overlay_path
        if os.path.exists(rings_overlay_path)
        else None,
        "frames": frame_entries,
        "layer_dir": layer_dir,
        "radar_dir": radar_dir,
        "alerts_dir": alerts_dir,
        "cities_dir": cities_dir,
        "hud_right_dir": hud_right_dir,
        "map_extent": list(shared_map_extent) if shared_map_extent else None,
        "map_projection": map_projection_name,
        "ui_margin_bottom": float(ui_margin_bottom),
        "map_axes_pos": [float(v) for v in map_axes_pos],
        "manifest": manifest,
    }


def _as_uint8_image(arr):
    """Normalize image array to uint8 without changing channel order."""
    out = np.asarray(arr)
    if out.dtype == np.uint8:
        return out
    if np.issubdtype(out.dtype, np.floating):
        finite = out[np.isfinite(out)]
        if finite.size and finite.min() >= 0.0 and finite.max() <= 1.0:
            out = out * 255.0
    return np.clip(out, 0, 255).astype(np.uint8)


def _to_rgba(arr):
    img = _as_uint8_image(arr)
    if img.ndim == 2:
        img = np.repeat(img[:, :, None], 3, axis=2)
    if img.ndim != 3:
        raise ValueError(f"Unsupported image rank: {img.ndim}")
    channels = img.shape[2]
    if channels == 4:
        return img
    if channels == 3:
        alpha = np.full((img.shape[0], img.shape[1], 1), 255, dtype=np.uint8)
        return np.concatenate([img, alpha], axis=2)
    if channels == 1:
        rgb = np.repeat(img, 3, axis=2)
        alpha = np.full((img.shape[0], img.shape[1], 1), 255, dtype=np.uint8)
        return np.concatenate([rgb, alpha], axis=2)
    raise ValueError(f"Unsupported channel count: {channels}")


def _composite_rgba(base_rgba, overlay_rgba):
    """Alpha composite overlay over base and return uint8 RGB frame."""
    h = min(base_rgba.shape[0], overlay_rgba.shape[0])
    w = min(base_rgba.shape[1], overlay_rgba.shape[1])
    base = base_rgba[:h, :w, :].astype(np.float32) / 255.0
    over = overlay_rgba[:h, :w, :].astype(np.float32) / 255.0

    b_rgb = base[:, :, :3]
    b_a = base[:, :, 3:4]
    o_rgb = over[:, :, :3]
    o_a = over[:, :, 3:4]

    out_a = o_a + b_a * (1.0 - o_a)
    out_rgb = np.where(
        out_a > 0,
        (o_rgb * o_a + b_rgb * b_a * (1.0 - o_a)) / np.maximum(out_a, 1e-6),
        0.0,
    )

    return np.clip(out_rgb * 255.0, 0, 255).astype(np.uint8)


def _composite_rgba_full(base_rgba, overlay_rgba):
    """Alpha composite overlay over base and return uint8 RGBA frame."""
    h = min(base_rgba.shape[0], overlay_rgba.shape[0])
    w = min(base_rgba.shape[1], overlay_rgba.shape[1])
    base = base_rgba[:h, :w, :].astype(np.float32) / 255.0
    over = overlay_rgba[:h, :w, :].astype(np.float32) / 255.0

    b_rgb = base[:, :, :3]
    b_a = base[:, :, 3:4]
    o_rgb = over[:, :, :3]
    o_a = over[:, :, 3:4]

    out_a = o_a + b_a * (1.0 - o_a)
    out_rgb = np.where(
        out_a > 0,
        (o_rgb * o_a + b_rgb * b_a * (1.0 - o_a)) / np.maximum(out_a, 1e-6),
        0.0,
    )

    out = np.concatenate([out_rgb, out_a], axis=2)
    return np.clip(out * 255.0, 0, 255).astype(np.uint8)
