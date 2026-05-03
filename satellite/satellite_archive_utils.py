from config.satellite_config import ABI_CHANNELS, RGB_COMPOSITE_KEYS
from config.style_config import resolve_satellite_style_config
from font_utils import register_montserrat_fonts

import io
import json
import os
import re
import time as _time
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import imageio.v2 as imageio
import xarray as xr
import cartopy.crs as ccrs
import cartopy.feature as cfeature

from datetime import datetime, timezone, timedelta
from dateutil import tz
from matplotlib.offsetbox import AnnotationBbox, OffsetImage

from satellite.satellite_nodd_utils import (
    get_s3_client,
    list_goes_files,
    GOES_BUCKET_BY_SAT,
    GOES_GCP_BUCKET_BY_SAT,
    SECTOR_TO_PRODUCT_SUFFIX,
    SECTOR_TO_SCENE_TAG,
    normalize_sector_name,
)
from satellite.satellite_utils import (
    parse_goes_time_from_filename,
    process_composite,
    _load_geocolor_night_background,
    _get_cmi_dataarray,
    _compute_image_extent,
    plot_cities_sat,
    CensusCounties,
)

matplotlib.use("Agg")
register_montserrat_fonts()

_MESO_DEFAULT_FALLBACK_HOURS = 72


def _extract_channel_number(channel_key):
    match = re.search(r"(\d+)", str(channel_key))
    return int(match.group(1)) if match else None


def _parse_utc_datetime(value):
    if not value:
        return None

    raw = str(value).strip().replace("Z", "")
    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=0, minute=0, second=0)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    raise ValueError(f"Unsupported datetime format: {value}")


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


def _extract_scan_token_from_filename(filename):
    match = re.search(r"_s(\d{14})", os.path.basename(str(filename or "")))
    return match.group(1) if match else None


def _download_key(provider, bucket, key, local_path, s3_client=None):
    if provider == "aws":
        s3_client.download_file(bucket, key, local_path)
        return

    requests = __import__("requests")
    from urllib.parse import quote

    encoded_key = quote(key, safe="/")
    url = f"https://storage.googleapis.com/{bucket}/{encoded_key}"
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    with open(local_path, "wb") as file_handle:
        file_handle.write(response.content)


def _nearest_file(time_pairs, target_time, tolerance_seconds):
    if not time_pairs:
        return None

    nearest = min(time_pairs, key=lambda x: abs((x[0] - target_time).total_seconds()))
    delta = abs((nearest[0] - target_time).total_seconds())
    return nearest if delta <= tolerance_seconds else None


# ─── GOES satellite date resolution ────────────────────────────────────────────────
#
# Operational timelines (approximate):
#   GOES-16  GOES-East   Dec 2017 – Feb 12, 2025
#   GOES-19  GOES-East   Feb 12, 2025 – present
#   GOES-18  GOES-West   Jul 10, 2022 – present
#   GOES-17  GOES-West   Feb 2019 – Jul 2022  (available as manual override)
#
# For overlapping periods the auto modes prefer the newer satellite.

_GOES_EAST_CUTOVER = datetime(2025, 2, 12, tzinfo=timezone.utc)
_GOES_WEST_START = datetime(2022, 7, 10, tzinfo=timezone.utc)


def _resolve_sat_for_date(sat_id: str, dt: datetime) -> str:
    """
    Given a logical satellite selector ('goes-east' or 'goes-west') and a
    UTC datetime, return the concrete satellite id ('goes16', 'goes19', etc.).

    If sat_id is already a concrete id (e.g. 'goes16'), return it unchanged.
    """
    key = str(sat_id).lower().replace(" ", "").replace("_", "-")

    if key == "goes-east":
        return "goes19" if dt >= _GOES_EAST_CUTOVER else "goes16"
    if key == "goes-west":
        if dt >= _GOES_WEST_START:
            return "goes18"
        # No GOES-West coverage before GOES-18 in auto mode
        return None

    # Already a concrete satellite id
    return sat_id


def _split_date_range_by_satellite(sat_id: str, start_dt, end_dt):
    """
    Split a date range into segments, each mapped to a single concrete
    satellite.  Returns list of (concrete_sat_id, seg_start, seg_end).
    """
    key = str(sat_id).lower().replace(" ", "").replace("_", "-")

    if key == "goes-east":
        cutover = _GOES_EAST_CUTOVER
        if end_dt < cutover:
            return [("goes16", start_dt, end_dt)]
        if start_dt >= cutover:
            return [("goes19", start_dt, end_dt)]
        # Spans the cutover
        return [
            ("goes16", start_dt, cutover - timedelta(seconds=1)),
            ("goes19", cutover, end_dt),
        ]

    if key == "goes-west":
        cutover = _GOES_WEST_START
        if start_dt >= cutover:
            return [("goes18", start_dt, end_dt)]
        if end_dt < cutover:
            # No GOES-West data before GOES-18 in auto mode
            return []
        # Spans the cutover — only return the GOES-18 portion
        return [("goes18", cutover, end_dt)]

    # Concrete satellite id — no splitting needed
    return [(sat_id, start_dt, end_dt)]


def _downsample_evenly(items, target_count):
    if target_count <= 0 or len(items) <= target_count:
        return items
    if target_count == 1:
        return [items[-1]]

    step = (len(items) - 1) / float(target_count - 1)
    selected = []
    seen = set()
    for i in range(target_count):
        idx = int(round(i * step))
        idx = max(0, min(idx, len(items) - 1))
        if idx not in seen:
            selected.append(items[idx])
            seen.add(idx)

    if selected and selected[-1] is not items[-1]:
        selected[-1] = items[-1]
    return selected


def _build_frame_plan(channel_files, req_bands, max_frames):
    primary_band = req_bands[0]
    primary_series = sorted(channel_files.get(primary_band, []), key=lambda x: x[0])
    if not primary_series:
        return []

    sampled_times = [scan_time for scan_time, _ in primary_series]
    tolerance_seconds = 600

    frames = []
    for target_time in sampled_times:
        frame_files = {}
        missing = False
        for band in req_bands:
            nearest = _nearest_file(
                channel_files.get(band, []), target_time, tolerance_seconds
            )
            if nearest is None:
                missing = True
                break
            frame_files[band] = nearest[1]
        if not missing:
            frames.append((target_time, frame_files))

    if max_frames and max_frames > 0:
        frames = _downsample_evenly(frames, int(max_frames))
    return frames


def _resolve_sat_bucket(sat_id, provider):
    sat_key = str(sat_id).lower()
    bucket_map = GOES_GCP_BUCKET_BY_SAT if provider == "gcp" else GOES_BUCKET_BY_SAT
    bucket = bucket_map.get(sat_key)
    if bucket is None:
        # Try with hyphen format: goes16 -> goes-16
        digits = "".join(filter(str.isdigit, str(sat_id)))
        bucket = bucket_map.get(f"goes-{digits}")
    if bucket is None:
        # Try without hyphen format: goes-16 -> goes16
        digits = "".join(filter(str.isdigit, str(sat_id)))
        bucket = bucket_map.get(f"goes{digits}")
    if bucket is None:
        raise ValueError(f"Unsupported satellite id for {provider.upper()}: {sat_id}")
    return bucket


def _list_archive_channel_files(
    sat_id, sector, channel_key, start_dt, end_dt, provider
):
    provider = str(provider).lower()
    sector = normalize_sector_name(sector)
    if provider not in {"aws", "gcp"}:
        raise ValueError("provider must be 'aws' or 'gcp'")

    bucket = _resolve_sat_bucket(sat_id, provider)
    sector_suffix = SECTOR_TO_PRODUCT_SUFFIX.get(sector, "C")
    scene_tag = SECTOR_TO_SCENE_TAG.get(sector)
    product_suffix = "M" if scene_tag in {"M1", "M2"} else sector_suffix
    product_prefix = f"ABI-L2-CMIP{product_suffix}"

    req_bands = ABI_CHANNELS[channel_key].get("req", [channel_key])
    s3_client = get_s3_client() if provider == "aws" else None

    channel_keys = {}
    for band in req_bands:
        channel_num = _extract_channel_number(band)
        if channel_num is None:
            channel_keys[band] = []
            continue

        keys = list_goes_files(
            s3_client=s3_client,
            bucket=bucket,
            product_prefix=product_prefix,
            start_dt=start_dt,
            end_dt=end_dt,
            channel_num=channel_num,
            scene_tag=scene_tag,
            provider=provider,
        )
        channel_keys[band] = keys

    return bucket, req_bands, channel_keys


def _download_archive_files(
    sat_id,
    sector,
    channel_key,
    start_dt,
    end_dt,
    base_dir,
    provider="aws",
    progress_callback=None,
    latest_only=False,
):
    bucket, req_bands, channel_keys = _list_archive_channel_files(
        sat_id, sector, channel_key, start_dt, end_dt, provider
    )

    if latest_only:
        channel_keys = {
            band: (keys[-1:] if keys else []) for band, keys in channel_keys.items()
        }

    total_to_process = sum(len(keys) for keys in channel_keys.values())
    if total_to_process == 0:
        return None, req_bands, {}, 0

    save_root = os.path.join(
        base_dir,
        "satellite_archive",
        "satellite_downloads",
        str(provider),
        str(sat_id),
        str(sector),
    )
    os.makedirs(save_root, exist_ok=True)

    s3_client = get_s3_client() if provider == "aws" else None
    processed_count = 0
    download_count = 0
    channel_files = {band: [] for band in req_bands}

    for band in req_bands:
        band_root = os.path.join(save_root, band)
        os.makedirs(band_root, exist_ok=True)

        for key in channel_keys.get(band, []):
            processed_count += 1
            if progress_callback:
                progress_callback(processed_count, total_to_process)

            file_name = os.path.basename(key)
            scan_time = parse_goes_time_from_filename(file_name)
            day_dir = _date_partition_dir(
                band_root, scan_time or datetime.now(timezone.utc)
            )
            os.makedirs(day_dir, exist_ok=True)
            local_path = os.path.join(day_dir, file_name)

            if not os.path.exists(local_path):
                try:
                    _download_key(
                        provider, bucket, key, local_path, s3_client=s3_client
                    )
                    download_count += 1
                except Exception as e:
                    print(
                        f"[WARN] Satellite archive download failed: {type(e).__name__}: {e} | provider={provider} key={key}"
                    )
                    continue

            scan_time = scan_time or parse_goes_time_from_filename(file_name)
            if scan_time is not None:
                channel_files[band].append((scan_time, local_path))

    for band in channel_files:
        channel_files[band].sort(key=lambda x: x[0])

    return save_root, req_bands, channel_files, download_count


# ─── Layer Rendering Helpers for Separated Layer Output ───────────────────────────


def _save_layer_png(fig, path, dpi=150, transparent=False):
    """Save matplotlib figure to PNG with consistent settings."""
    fig.savefig(
        path,
        dpi=dpi,
        bbox_inches="tight",
        pad_inches=0.1,
        transparent=transparent,
    )
    plt.close(fig)


def _create_background_layer(ax, fig, style_config):
    """Render background layer (ocean/land colors) on separate figure."""
    ocean_color = style_config.get("ocean_color", "#152238")
    land_color = style_config.get("land_color", "#5c5c5c")
    coastline_color = style_config.get("coastline_color", "#000000")
    coastline_width = float(style_config.get("coastline_width", 0.8))
    zo = {"water": 0, "land": 0, "borders": 15}
    if style_config:
        for k in zo:
            v = style_config.get(f"zorder_{k}")
            if v is not None:
                zo[k] = int(v)

    ax.add_feature(
        cfeature.OCEAN.with_scale("10m"),
        facecolor=ocean_color,
        edgecolor="none",
        zorder=zo["water"],
    )
    ax.add_feature(
        cfeature.LAND.with_scale("10m"),
        facecolor=land_color,
        edgecolor="none",
        zorder=zo["land"],
    )
    ax.coastlines(
        "10m", color=coastline_color, linewidth=coastline_width, zorder=zo["borders"]
    )


def _create_borders_layer(ax, fig, style_config):
    """Render borders layer (countries/states/etc) on separate figure."""
    show_counties = style_config.get("show_counties", False)
    county_linewidth = float(
        style_config.get("county_linewidth", style_config.get("county_width", 0.3))
    )
    county_color = style_config.get("county_color", "white")
    show_country = style_config.get("show_country", True)
    if isinstance(show_country, str):
        show_country = show_country.lower() not in ("false", "0", "no")
    country_color = style_config.get("country_color", "#ffffff")
    country_width = float(style_config.get("country_width", 1))
    show_states = style_config.get("show_states", True)
    if isinstance(show_states, str):
        show_states = show_states.lower() not in ("false", "0", "no")
    state_color = style_config.get("state_color", "#ffffff")
    state_width = float(style_config.get("state_width", 1))
    show_highways = style_config.get("show_highways", True)
    if isinstance(show_highways, str):
        show_highways = show_highways.lower() not in ("false", "0", "no")
    highway_color = style_config.get("highway_color", "#888888")
    highway_width = float(style_config.get("highway_width", 0.8))
    highway_opacity = float(style_config.get("highway_opacity", 0.6))
    show_lakes = style_config.get("show_lakes", True)
    if isinstance(show_lakes, str):
        show_lakes = show_lakes.lower() not in ("false", "0", "no")
    lake_color = style_config.get("lake_color", "#000000")
    lake_outline_color = style_config.get("lake_outline_color", "#333333")
    lake_outline_width = float(style_config.get("lake_outline_width", 0.5))
    show_rivers = style_config.get("show_rivers", True)
    if isinstance(show_rivers, str):
        show_rivers = show_rivers.lower() not in ("false", "0", "no")
    river_color = style_config.get("river_color", "#000000")
    river_width = float(style_config.get("river_width", 0.5))

    zo = {"counties": 14, "borders": 15}
    if style_config:
        for k in zo:
            v = style_config.get(f"zorder_{k}")
            if v is not None:
                zo[k] = int(v)

    if show_counties:
        census_feature = CensusCounties.get_feature()
        if census_feature:
            ax.add_feature(
                census_feature,
                linewidth=county_linewidth,
                edgecolor=county_color,
                facecolor="none",
                zorder=zo["counties"],
            )
    if show_country:
        ax.add_feature(
            cfeature.BORDERS.with_scale("10m"),
            edgecolor=country_color,
            linewidth=country_width,
            zorder=zo["borders"],
        )
    if show_states:
        ax.add_feature(
            cfeature.STATES.with_scale("10m"),
            edgecolor=state_color,
            linewidth=state_width,
            zorder=zo["borders"],
        )
    if show_highways:
        highways = cfeature.NaturalEarthFeature(
            category="cultural", name="roads", scale="10m", facecolor="none"
        )
        ax.add_feature(
            highways,
            edgecolor=highway_color,
            linewidth=highway_width,
            alpha=highway_opacity,
            zorder=zo["borders"],
        )
    if show_lakes:
        ax.add_feature(
            cfeature.LAKES.with_scale("10m"),
            facecolor=lake_color,
            edgecolor=lake_outline_color,
            linewidth=lake_outline_width,
            zorder=zo["borders"],
        )
    if show_rivers:
        ax.add_feature(
            cfeature.RIVERS.with_scale("10m"),
            edgecolor=river_color,
            linewidth=river_width,
            zorder=zo["borders"],
        )


def _create_cities_layer(ax, fig, curr_ext, style_config):
    """Render cities layer on separate figure."""
    show_places = bool(style_config.get("show_places", False))
    if not show_places:
        return

    font_family = style_config.get("font_family", "Montserrat")
    cities_file = style_config.get("cities_file", "us-cities.json")
    city_density = float(style_config.get("city_density", 5))
    density_scale = city_density / 5.0
    city_collision_w = float(style_config.get("city_collision_w", 0.05))
    city_collision_h = float(style_config.get("city_collision_h", 0.02))
    city_text_size = int(style_config.get("city_text_size", 12))
    city_font_weight = style_config.get("city_font_weight", "black")
    city_font_style = style_config.get("city_font_style", "italic")
    city_box_style = style_config.get("city_box_style", "round,pad=0.2")
    city_halo_width = float(style_config.get("city_halo_width", 2))
    city_halo_color = style_config.get("city_halo_color", "black")
    city_text_alpha = float(style_config.get("city_text_alpha", 0.95))
    city_text_color = style_config.get("city_text_color", "#ffffff")
    city_text_bg_color = style_config.get("city_text_bg_color", "#000000")
    city_text_bg_alpha = float(style_config.get("city_text_bg_alpha", 0.3))

    fig_width = 12.8
    scale_factor = max(fig_width / 12.8, 0.55)
    city_text_size = int(city_text_size * scale_factor)

    zo = {"cities": 30}
    if style_config:
        v = style_config.get("zorder_cities")
        if v is not None:
            zo["cities"] = int(v)

    plot_cities_sat(
        ax,
        curr_ext,
        filename=cities_file,
        density_scale=density_scale,
        collision_w_factor=city_collision_w,
        collision_h_factor=city_collision_h,
        city_text_size=city_text_size,
        z_cities=zo["cities"],
        city_text_color=city_text_color,
        city_text_bg_color=city_text_bg_color,
        city_text_bg_alpha=city_text_bg_alpha,
        font_family=font_family,
        font_weight=city_font_weight,
        font_style=city_font_style,
        box_style=city_box_style,
        halo_width=city_halo_width,
        halo_color=city_halo_color,
        text_alpha=city_text_alpha,
    )


def _create_hud_layer(
    ax,
    fig,
    timestamp_text,
    channel_key,
    sector,
    sat_num,
    region_label,
    custom_extent,
    style_config,
):
    """Render HUD (heads-up display) layers on separate figure."""
    font_family = style_config.get("font_family", "Montserrat")
    hud_left_size = style_config.get("hud_left_size", 10)
    hud_left_x = style_config.get("hud_left_x", 0.03)
    hud_left_y = style_config.get("hud_left_y", 0.97)
    hud_right_size = style_config.get("hud_right_size", 10)
    hud_right_x = style_config.get("hud_right_x", 0.97)
    hud_right_y = style_config.get("hud_right_y", 0.97)
    hud_font_weight = style_config.get("hud_font_weight", "black")
    hud_font_style = style_config.get("hud_font_style", "italic")
    hud_line_spacing = float(style_config.get("hud_line_spacing", 1.15))
    hud_left_text_color = style_config.get("hud_left_text_color", "#ffffff")
    hud_left_bg_color = style_config.get("hud_left_bg_color", "#000000")
    hud_left_edge_color = style_config.get("hud_left_edge_color", "#555555")
    hud_left_alpha = float(style_config.get("hud_left_alpha", 0.7))
    hud_left_box_style = style_config.get("hud_left_box_style", "round,pad=0.5")
    hud_right_text_color = style_config.get("hud_right_text_color", "#ffd700")
    hud_right_bg_color = style_config.get("hud_right_bg_color", "#000000")
    hud_right_edge_color = style_config.get("hud_right_edge_color", "#555555")
    hud_right_alpha = float(style_config.get("hud_right_alpha", 0.7))
    hud_right_box_style = style_config.get("hud_right_box_style", "round,pad=0.4")

    fig_width = 12.8
    scale_factor = max(fig_width / 12.8, 0.55)
    hud_left_size = int(hud_left_size * scale_factor)
    hud_right_size = int(hud_right_size * scale_factor)

    zo = {"hud": 100}
    if style_config:
        v = style_config.get("zorder_hud")
        if v is not None:
            zo["hud"] = int(v)

    region_label_full = str(sector).upper() + (
        " - Target Area" if custom_extent else ""
    )
    hud_stacked = (
        f"GOES-{sat_num}\n{ABI_CHANNELS[channel_key]['name']}\n{region_label_full}"
    )

    ax.annotate(
        hud_stacked,
        xy=(hud_left_x, hud_left_y),
        xycoords="axes fraction",
        fontsize=hud_left_size,
        fontname=font_family,
        fontweight=hud_font_weight,
        fontstyle=hud_font_style,
        color=hud_left_text_color,
        va="top",
        linespacing=hud_line_spacing,
        bbox=dict(
            boxstyle=hud_left_box_style,
            fc=hud_left_bg_color,
            ec=hud_left_edge_color,
            alpha=hud_left_alpha,
        ),
        zorder=zo["hud"],
    )

    ax.annotate(
        timestamp_text,
        xy=(hud_right_x, hud_right_y),
        xycoords="axes fraction",
        fontsize=hud_right_size,
        fontname=font_family,
        fontweight=hud_font_weight,
        fontstyle=hud_font_style,
        color=hud_right_text_color,
        ha="right",
        va="top",
        bbox=dict(
            boxstyle=hud_right_box_style,
            fc=hud_right_bg_color,
            ec=hud_right_edge_color,
            alpha=hud_right_alpha,
        ),
        zorder=zo["hud"],
    )


def _create_logo_layer(ax, fig, logo_file, style_config):
    """Render logo layer on separate figure."""
    logo_user_size = style_config.get("logo_user_size", 0.08)
    logo_user_x = style_config.get("logo_user_x", 0.98)
    logo_user_y = style_config.get("logo_user_y", 0.01)

    fig_width = 12.8
    scale_factor = max(fig_width / 12.8, 0.55)
    logo_user_size = logo_user_size * scale_factor

    zo = {"logos": 100}
    if style_config:
        v = style_config.get("zorder_logos")
        if v is not None:
            zo["logos"] = int(v)

    if logo_file and os.path.exists(logo_file):
        try:
            n_img = mpimg.imread(logo_file)
            ax.add_artist(
                AnnotationBbox(
                    OffsetImage(n_img, zoom=logo_user_size),
                    (logo_user_x, logo_user_y),
                    xycoords="axes fraction",
                    frameon=False,
                    box_alignment=(1, 0),
                    zorder=zo["logos"],
                )
            )
        except Exception as e:
            print(f"[WARN] Could not load user logo: {e}")


def generate_satellite_archive_animation(
    sat_id,
    sector,
    channel_key,
    date_from,
    date_to,
    fps,
    frames,
    logo_file,
    style_config=None,
    progress_callback=None,
    download_progress=None,
    custom_extent=None,
    show_places=False,
    provider="aws",
    user_tz=None,
    latest_only=False,
    view_mode="video",
):
    style_config = resolve_satellite_style_config(style_config)

    start_dt = _parse_utc_datetime(date_from)
    end_dt = _parse_utc_datetime(date_to)
    if start_dt is None or end_dt is None:
        raise ValueError(
            "Both date_from and date_to are required for satellite archive."
        )
    if end_dt < start_dt:
        raise ValueError("date_to cannot be earlier than date_from.")

    request_start_code = start_dt.strftime("%Y%m%d_%H%M")
    request_end_code = end_dt.strftime("%Y%m%d_%H%M")

    # Include full day when date_to is date-only in incoming value.
    if str(date_to).strip() and len(str(date_to).strip()) == 10:
        end_dt = end_dt.replace(hour=23, minute=59)

    base_dir = os.path.dirname(os.path.abspath(__file__))

    def _download_segments(seg_list):
        all_bands = None
        merged_files = {}
        downloaded_any = False
        for seg_sat, seg_start, seg_end in seg_list:
            seg_data_dir, seg_bands, seg_files, _seg_dl = _download_archive_files(
                sat_id=seg_sat,
                sector=sector,
                channel_key=channel_key,
                start_dt=seg_start,
                end_dt=seg_end,
                base_dir=base_dir,
                provider=provider,
                progress_callback=download_progress,
                latest_only=latest_only,
            )
            if seg_data_dir is None:
                continue
            downloaded_any = True
            if all_bands is None:
                all_bands = seg_bands
            for band in seg_bands:
                if band not in merged_files:
                    merged_files[band] = []
                for scan_time, path in seg_files.get(band, []):
                    merged_files[band].append((scan_time, path, seg_sat))
        return downloaded_any, all_bands, merged_files

    # ── Resolve logical satellite selector to concrete sat ids ──
    segments = _split_date_range_by_satellite(sat_id, start_dt, end_dt)
    if not segments:
        return (
            None,
            None,
            (
                f"No satellite data available for {sat_id} in the selected date range. "
                f"GOES-West coverage begins Jul 10, 2022 (GOES-18)."
            ),
        )

    any_downloaded, all_req_bands, merged_channel_files = _download_segments(segments)

    # Meso sectors can be inactive for extended periods.
    # If no files were found, widen the search window automatically.
    normalized_sector = normalize_sector_name(sector)
    if not any_downloaded and normalized_sector in {"Meso1", "Meso2"}:
        fallback_hours = int(
            style_config.get("meso_fallback_hours", _MESO_DEFAULT_FALLBACK_HOURS)
        )
        fallback_start = end_dt - timedelta(hours=max(1, fallback_hours))
        if fallback_start < start_dt:
            fallback_segments = _split_date_range_by_satellite(
                sat_id, fallback_start, end_dt
            )
            if fallback_segments:
                any_downloaded, all_req_bands, merged_channel_files = (
                    _download_segments(fallback_segments)
                )

    if not any_downloaded or all_req_bands is None:
        if normalized_sector in {"Meso1", "Meso2"}:
            return (
                None,
                None,
                "No satellite archive files found for selected range. "
                "Meso sectors are event-driven and may be inactive during this period.",
            )
        return None, None, "No satellite archive files found for selected range."

    # Sort merged channel files by time
    for band in merged_channel_files:
        merged_channel_files[band].sort(key=lambda x: x[0])

    # Build channel_files without the sat tag for frame planning
    channel_files = {
        band: [(t, p) for t, p, _s in entries]
        for band, entries in merged_channel_files.items()
    }

    # Build a time→sat_id lookup from the primary band
    req_bands = all_req_bands
    primary_band = req_bands[0]
    time_to_sat = {}
    for scan_time, _path, seg_sat in merged_channel_files.get(primary_band, []):
        time_to_sat[scan_time] = seg_sat

    frame_plan = _build_frame_plan(
        channel_files=channel_files,
        req_bands=req_bands,
        max_frames=int(frames) if frames else 0,
    )

    if not frame_plan:
        return None, None, "No complete frames available (missing required band data)."

    # --- STYLE UNPACKING (match live satellite) ---
    show_places = bool(style_config.get("show_places", show_places))
    font_family = style_config.get("font_family", "Montserrat")
    hud_left_size = style_config.get("hud_left_size", 10)
    hud_left_x = style_config.get("hud_left_x", 0.03)
    hud_left_y = style_config.get("hud_left_y", 0.97)

    hud_right_size = style_config.get("hud_right_size", 10)
    hud_right_x = style_config.get("hud_right_x", 0.97)
    hud_right_y = style_config.get("hud_right_y", 0.97)

    logo_user_size = style_config.get("logo_user_size", 0.08)
    logo_user_x = style_config.get("logo_user_x", 0.98)
    logo_user_y = style_config.get("logo_user_y", 0.01)

    cbar_size = float(style_config.get("cbar_size", 0.75))
    cbar_horizontal_size = float(
        style_config.get("cbar_size_horizontal", min(cbar_size, 0.35))
    )
    cbar_horizontal_fraction = float(
        style_config.get("cbar_fraction_horizontal", 0.045)
    )
    cbar_title_size = style_config.get("cbar_title_size", 14)
    cbar_tick_labelsize = style_config.get("cbar_tick_labelsize", 10)
    cbar_tick_color = style_config.get("cbar_tick_color", "black")
    cbar_tick_weight = style_config.get("cbar_tick_weight", "bold")
    cbar_outline_color = style_config.get("cbar_outline_color", "#555555")

    cities_file = style_config.get("cities_file", "us-cities.json")
    city_density = float(style_config.get("city_density", 5))
    density_scale = city_density / 5.0
    city_collision_w = float(style_config.get("city_collision_w", 0.05))
    city_collision_h = float(style_config.get("city_collision_h", 0.02))
    city_text_size = int(style_config.get("city_text_size", 12))
    city_font_weight = style_config.get("city_font_weight", "black")
    city_font_style = style_config.get("city_font_style", "italic")
    city_box_style = style_config.get("city_box_style", "round,pad=0.2")
    city_halo_width = float(style_config.get("city_halo_width", 2))
    city_halo_color = style_config.get("city_halo_color", "black")
    city_text_alpha = float(style_config.get("city_text_alpha", 0.95))

    show_counties = style_config.get("show_counties", False)
    county_linewidth = float(
        style_config.get("county_linewidth", style_config.get("county_width", 0.3))
    )
    county_color = style_config.get("county_color", "white")

    expand_top = float(style_config.get("map_margin_top", 0.0))
    expand_bottom = float(style_config.get("map_margin_bottom", 0.0))
    expand_left = float(style_config.get("map_margin_left", 0.0))
    expand_right = float(style_config.get("map_margin_right", 0.0))

    # City text styling
    city_text_color = style_config.get("city_text_color", "#ffffff")
    city_text_bg_color = style_config.get("city_text_bg_color", "#000000")
    city_text_bg_alpha = float(style_config.get("city_text_bg_alpha", 0.3))

    night_bg_lon_offset = float(style_config.get("night_bg_lon_offset", 0.0))
    night_bg_lat_offset = float(style_config.get("night_bg_lat_offset", 0.0))
    night_bg_zoom = float(style_config.get("night_bg_zoom", 100.0))
    night_bg_source_pref = str(style_config.get("night_bg_source_pref", "tiff_first"))

    # Base map styling
    map_bg_color = style_config.get("map_bg_color", "#000000")
    land_color = style_config.get("land_color", "#5c5c5c")
    ocean_color = style_config.get("ocean_color", "#152238")
    coastline_width = float(style_config.get("coastline_width", 0.8))
    coastline_color = style_config.get("coastline_color", "#000000")

    # Country borders
    show_country = style_config.get("show_country", True)
    if isinstance(show_country, str):
        show_country = show_country.lower() not in ("false", "0", "no")
    country_color = style_config.get("country_color", "#ffffff")
    country_width = float(style_config.get("country_width", 1))

    # State borders
    show_states = style_config.get("show_states", True)
    if isinstance(show_states, str):
        show_states = show_states.lower() not in ("false", "0", "no")
    state_color = style_config.get("state_color", "#ffffff")
    state_width = float(style_config.get("state_width", 1))

    # Highway styling
    show_highways = style_config.get("show_highways", True)
    if isinstance(show_highways, str):
        show_highways = show_highways.lower() not in ("false", "0", "no")
    highway_color = style_config.get("highway_color", "#888888")
    highway_width = float(style_config.get("highway_width", 0.8))
    highway_opacity = float(style_config.get("highway_opacity", 0.6))

    # HUD text & box styling
    hud_left_text_color = style_config.get("hud_left_text_color", "#ffffff")
    hud_left_bg_color = style_config.get("hud_left_bg_color", "#000000")
    hud_left_edge_color = style_config.get("hud_left_edge_color", "#555555")
    hud_left_alpha = float(style_config.get("hud_left_alpha", 0.7))
    hud_font_weight = style_config.get("hud_font_weight", "black")
    hud_font_style = style_config.get("hud_font_style", "italic")
    hud_line_spacing = float(style_config.get("hud_line_spacing", 1.15))
    hud_left_box_style = style_config.get("hud_left_box_style", "round,pad=0.5")
    hud_right_box_style = style_config.get("hud_right_box_style", "round,pad=0.4")
    hud_right_text_color = style_config.get("hud_right_text_color", "#ffd700")
    hud_right_bg_color = style_config.get("hud_right_bg_color", "#000000")
    hud_right_edge_color = style_config.get("hud_right_edge_color", "#555555")
    hud_right_alpha = float(style_config.get("hud_right_alpha", 0.7))

    figure_left_margin = float(style_config.get("figure_left_margin", 0.0))
    figure_right_margin = float(style_config.get("figure_right_margin", 0.0))
    figure_top_margin = float(style_config.get("figure_top_margin", 0.0))
    figure_bottom_margin = float(style_config.get("figure_bottom_margin", 0.0))

    # Lakes & River Styling
    show_lakes = style_config.get("show_lakes", True)
    if isinstance(show_lakes, str):
        show_lakes = show_lakes.lower() not in ("false", "0", "no")
    lake_color = style_config.get("lake_color", "#000000")
    lake_outline_color = style_config.get("lake_outline_color", "#333333")
    lake_outline_width = float(style_config.get("lake_outline_width", 0.5))
    show_rivers = style_config.get("show_rivers", True)
    if isinstance(show_rivers, str):
        show_rivers = show_rivers.lower() not in ("false", "0", "no")
    river_color = style_config.get("river_color", "#000000")
    river_width = float(style_config.get("river_width", 0.5))

    fig_width = 12.8
    scale_factor = max(fig_width / 12.8, 0.55)
    hud_left_size = int(hud_left_size * scale_factor)
    hud_right_size = int(hud_right_size * scale_factor)
    city_text_size = int(city_text_size * scale_factor)
    cbar_title_size = int(cbar_title_size * scale_factor)
    logo_user_size = logo_user_size * scale_factor

    zo = {
        "land": 0,
        "water": 0,
        "sat_image": 1,
        "counties": 14,
        "borders": 15,
        "cities": 30,
        "hud": 100,
        "logos": 100,
    }
    if style_config:
        for key in zo:
            value = style_config.get(f"zorder_{key}")
            if value is not None:
                zo[key] = int(value)

    output_dir = os.path.join(
        base_dir,
        "satellite_archive",
        "satellite_images",
        str(sat_id),
        str(sector),
        str(channel_key),
        start_dt.strftime("%Y"),
        start_dt.strftime("%m"),
        start_dt.strftime("%d"),
    )
    frame_dir = output_dir
    os.makedirs(output_dir, exist_ok=True)

    # Determine if sat_id is a logical selector (auto mode)
    _is_logical = str(sat_id).lower().replace(" ", "").replace("_", "-") in (
        "goes-east",
        "goes-west",
    )

    _is_scrubber = str(view_mode).lower() == "scrubber"

    frames = []
    scrubber_manifest = []
    rendered_frame_paths = []
    rendered_frame_names = set()
    total = len(frame_plan)
    display_tz = tz.gettz(user_tz) if user_tz else tz.gettz("America/New_York")
    preloaded_night_bg = None
    preloaded_night_bg_signature = None

    # Composite at reduced resolution — 2× the output canvas longest dimension
    # gives excellent quality while avoiding 60M-pixel math on 6000×10000 grids.
    _output_dpi = 150
    _canvas_long = int(max(12.8, 7.2) * _output_dpi)  # 1920
    _composite_max_size = _canvas_long * 2  # 3840

    # --- Figure-reuse state (created on first frame, updated on subsequent) ---
    fig = None
    ax = None
    sat_img_artist = None
    sat_ir_artist = None
    hud_right_ann = None
    hud_left_ann = None
    prev_hud_left_text = None

    def _draw_static_overlays(_ax, _fig):
        """Draw all static map overlays (borders, cities, colorbar, logo). HUD annotations are dynamic in archive mode."""
        if show_places:
            curr_ext = _ax.get_extent(crs=ccrs.PlateCarree())
            plot_cities_sat(
                _ax,
                curr_ext,
                filename=cities_file,
                density_scale=density_scale,
                collision_w_factor=city_collision_w,
                collision_h_factor=city_collision_h,
                city_text_size=city_text_size,
                z_cities=zo["cities"],
                city_text_color=city_text_color,
                city_text_bg_color=city_text_bg_color,
                city_text_bg_alpha=city_text_bg_alpha,
                font_family=font_family,
                font_weight=city_font_weight,
                font_style=city_font_style,
                box_style=city_box_style,
                halo_width=city_halo_width,
                halo_color=city_halo_color,
                text_alpha=city_text_alpha,
            )

        _ax.add_feature(
            cfeature.OCEAN.with_scale("10m"),
            facecolor=ocean_color,
            edgecolor="none",
            zorder=zo["water"],
        )
        _ax.add_feature(
            cfeature.LAND.with_scale("10m"),
            facecolor=land_color,
            edgecolor="none",
            zorder=zo["land"],
        )
        _ax.coastlines(
            "10m",
            color=coastline_color,
            linewidth=coastline_width,
            zorder=zo["borders"],
        )

        if show_counties:
            census_feature = CensusCounties.get_feature()
            if census_feature:
                _ax.add_feature(
                    census_feature,
                    linewidth=county_linewidth,
                    edgecolor=county_color,
                    facecolor="none",
                    zorder=zo["counties"],
                )

        if show_country:
            _ax.add_feature(
                cfeature.BORDERS.with_scale("10m"),
                edgecolor=country_color,
                linewidth=country_width,
                zorder=zo["borders"],
            )
        if show_states:
            _ax.add_feature(
                cfeature.STATES.with_scale("10m"),
                edgecolor=state_color,
                linewidth=state_width,
                zorder=zo["borders"],
            )
        if show_highways:
            highways = cfeature.NaturalEarthFeature(
                category="cultural", name="roads", scale="10m", facecolor="none"
            )
            _ax.add_feature(
                highways,
                edgecolor=highway_color,
                linewidth=highway_width,
                alpha=highway_opacity,
                zorder=zo["borders"],
            )
        if show_lakes:
            _ax.add_feature(
                cfeature.LAKES.with_scale("10m"),
                facecolor=lake_color,
                edgecolor=lake_outline_color,
                linewidth=lake_outline_width,
                zorder=zo["borders"],
            )
        if show_rivers:
            _ax.add_feature(
                cfeature.RIVERS.with_scale("10m"),
                edgecolor=river_color,
                linewidth=river_width,
                zorder=zo["borders"],
            )

        if channel_key not in RGB_COMPOSITE_KEYS and channel_key != "Sandwich":
            sm = plt.cm.ScalarMappable(
                cmap=ABI_CHANNELS[channel_key]["cmap"],
                norm=ABI_CHANNELS[channel_key].get("norm"),
            )

            ticks = None
            tick_labels = None
            if "IR" in ABI_CHANNELS[channel_key]["name"]:
                ir_norm = ABI_CHANNELS[channel_key].get("norm")
                if ir_norm is not None and ir_norm.vmax > 380:
                    # Fire detection 3.9 µm — 164–400 K
                    ticks = [173, 213, 253, 273, 313, 353, 393]
                    tick_labels = [
                        "-100C",
                        "-60C",
                        "-20C",
                        "0C",
                        "+40C",
                        "+80C",
                        "+120C",
                    ]
                elif ir_norm is not None and ir_norm.vmin <= 175:
                    # Wide-range IR colormaps (CIRA 160–330 K, MetPy 170–330 K)
                    ticks = [173, 193, 213, 233, 253, 273, 293, 313]
                    tick_labels = [
                        "-100C",
                        "-80C",
                        "-60C",
                        "-40C",
                        "-20C",
                        "0C",
                        "+20C",
                        "+40C",
                    ]
                else:
                    ticks = [193, 213, 233, 253, 273, 303]
                    tick_labels = ["-80C", "-60C", "-40C", "-20C", "0C", "+30C"]
            elif "WV" in ABI_CHANNELS[channel_key]["name"]:
                ticks = [198, 218, 238, 258, 273]
                tick_labels = ["-75C", "-55C", "-35C", "-15C", "0C"]

            cb = _fig.colorbar(
                sm,
                ax=_ax,
                orientation="horizontal",
                shrink=cbar_horizontal_size,
                fraction=cbar_horizontal_fraction,
                pad=0.03,
                ticks=ticks,
            )

            cb.set_label("")
            cb.ax.set_xlabel("")

            cb.ax.tick_params(
                axis="x", colors=cbar_tick_color, labelsize=cbar_tick_labelsize
            )
            if tick_labels:
                cb.ax.set_xticklabels(tick_labels)
            for tick in cb.ax.get_xticklabels():
                tick.set_fontname(font_family)
                tick.set_fontweight(cbar_tick_weight)
            cb.outline.set_edgecolor(cbar_outline_color)

        # User Logo
        if logo_file and os.path.exists(logo_file):
            try:
                n_img = mpimg.imread(logo_file)
                _ax.add_artist(
                    AnnotationBbox(
                        OffsetImage(n_img, zoom=logo_user_size),
                        (logo_user_x, logo_user_y),
                        xycoords="axes fraction",
                        frameon=False,
                        box_alignment=(1, 0),
                        zorder=zo["logos"],
                    )
                )
            except Exception as e:
                print(f"[WARN] Could not load user logo: {e}")

    for i, (scan_time, files_to_open) in enumerate(frame_plan):
        if progress_callback:
            progress_callback(i + 1, total)

        current_ds = {}
        try:
            current_ds = {
                band: xr.open_dataset(path) for band, path in files_to_open.items()
            }
            sample = _get_cmi_dataarray(current_ds[req_bands[0]])

            if channel_key == "GeoColorBlkMar":
                geo_bg_target = (
                    _get_cmi_dataarray(current_ds["Channel02"])
                    if "Channel02" in current_ds
                    else sample
                )
                current_signature = (
                    int(geo_bg_target.shape[0]),
                    int(geo_bg_target.shape[1]),
                    round(float(geo_bg_target.x.min().item()), 6),
                    round(float(geo_bg_target.x.max().item()), 6),
                    round(float(geo_bg_target.y.min().item()), 6),
                    round(float(geo_bg_target.y.max().item()), 6),
                    round(float(night_bg_lon_offset), 2),
                    round(float(night_bg_lat_offset), 2),
                    round(float(night_bg_zoom), 2),
                    str(night_bg_source_pref or "tiff_first").strip().lower(),
                )
                if (
                    preloaded_night_bg is None
                    or preloaded_night_bg_signature != current_signature
                ):
                    print(
                        f"[GeoColor BG] Preloading night background for archive frame {i}..."
                    )
                    preloaded_night_bg = _load_geocolor_night_background(
                        geo_bg_target,
                        night_bg_lon_offset=night_bg_lon_offset,
                        night_bg_lat_offset=night_bg_lat_offset,
                        night_bg_zoom=night_bg_zoom,
                        night_bg_source_pref=night_bg_source_pref,
                    )
                    preloaded_night_bg_signature = current_signature
                    print(
                        f"[GeoColor BG] Night background cached ({preloaded_night_bg.shape})"
                    )
                else:
                    print(
                        f"[GeoColor BG] Reusing cached night background for archive frame {i}"
                    )

            data = process_composite(
                current_ds,
                channel_key,
                sample.metpy.cartopy_crs,
                night_bg_lon_offset=night_bg_lon_offset,
                night_bg_lat_offset=night_bg_lat_offset,
                night_bg_zoom=night_bg_zoom,
                night_bg_source_pref=night_bg_source_pref,
                preloaded_night_bg=preloaded_night_bg,
                max_size=_composite_max_size,
            )

            img_extent = _compute_image_extent(sample)

            # Compute per-frame HUD content
            dt_local = scan_time.astimezone(display_tz)
            timestamp_text = dt_local.strftime("%m/%d/%Y\n%I:%M %p %Z")
            primary_source_file = files_to_open.get(req_bands[0])
            scan_token = _extract_scan_token_from_filename(primary_source_file)
            if not scan_token:
                scan_token = scan_time.strftime("%Y%j%H%M%S") + "00"
            frame_name = f"{scan_token}.png"
            if frame_name in rendered_frame_names:
                frame_name = f"{scan_token}_{i:03d}.png"
            rendered_frame_names.add(frame_name)
            frame_path = os.path.join(frame_dir, frame_name)
            frame_sat = time_to_sat.get(scan_time, sat_id) if _is_logical else sat_id
            sat_num = "".join(filter(str.isdigit, str(frame_sat)))
            region_label = str(sector).upper() + (
                " - Target Area" if custom_extent else ""
            )
            hud_stacked = (
                f"GOES-{sat_num}\n{ABI_CHANNELS[channel_key]['name']}\n{region_label}"
            )

            _frame_start = _time.perf_counter()

            _anim_dpi = 150

            if fig is None:
                # === FIRST FRAME: Create figure + all static overlays ===
                fig = plt.figure(figsize=(12.8, 7.2), dpi=_anim_dpi)
                fig.subplots_adjust(
                    left=figure_left_margin,
                    right=1.0 - figure_right_margin,
                    bottom=figure_bottom_margin,
                    top=1.0 - figure_top_margin,
                )
                ax = fig.add_subplot(1, 1, 1, projection=sample.metpy.cartopy_crs)
                ax.set_facecolor(map_bg_color)

                if custom_extent:
                    try:
                        ax.set_extent(
                            [
                                custom_extent[2],
                                custom_extent[3],
                                custom_extent[0],
                                custom_extent[1],
                            ],
                            crs=ccrs.PlateCarree(),
                        )
                    except ValueError as e:
                        print(
                            f"[WARN] Invalid archive custom extent frame {i}: {type(e).__name__}: {e}; falling back to global"
                        )
                        ax.set_global()
                else:
                    # Guard against NaN/Inf extent values (e.g. Full Disk geostationary)
                    if all(np.isfinite(v) for v in img_extent):
                        try:
                            ax.set_extent(img_extent, crs=sample.metpy.cartopy_crs)
                        except ValueError as e:
                            print(
                                f"[WARN] Invalid archive projected extent frame {i}: {type(e).__name__}: {e}; falling back to global"
                            )
                            ax.set_global()
                    else:
                        ax.set_global()

                x_min, x_max = ax.get_xlim()
                y_min, y_max = ax.get_ylim()
                x_span = x_max - x_min
                y_span = y_max - y_min
                ax.set_xlim(x_min - x_span * expand_left, x_max + x_span * expand_right)
                ax.set_ylim(y_min - y_span * expand_bottom, y_max + y_span * expand_top)

                # Plot satellite data (store artist reference for future updates)
                if channel_key in RGB_COMPOSITE_KEYS:
                    sat_img_artist = ax.imshow(
                        data,
                        extent=img_extent,
                        origin="upper",
                        interpolation="bicubic",
                        zorder=zo["sat_image"],
                    )
                elif channel_key == "Sandwich":
                    sat_img_artist = ax.imshow(
                        data["vis"],
                        cmap="Greys_r",
                        extent=img_extent,
                        origin="upper",
                        interpolation="bicubic",
                        zorder=zo["sat_image"],
                    )
                    sat_ir_artist = ax.imshow(
                        data["ir"],
                        extent=img_extent,
                        origin="upper",
                        interpolation="bicubic",
                        zorder=zo["sat_image"] + 1,
                    )
                else:
                    target_norm = ABI_CHANNELS[channel_key].get("norm")
                    interpolation_mode = (
                        "nearest"
                        if str(channel_key).startswith("Channel13")
                        else "bicubic"
                    )
                    sat_img_artist = ax.imshow(
                        data,
                        cmap=ABI_CHANNELS[channel_key]["cmap"],
                        norm=target_norm,
                        extent=img_extent,
                        origin="upper",
                        interpolation=interpolation_mode,
                        zorder=zo["sat_image"],
                    )

                # Draw all static overlays (borders, cities, colorbar, logo)
                _draw_static_overlays(ax, fig)

                # HUD left annotation (dynamic in archive - satellite can change per frame)
                hud_left_ann = ax.annotate(
                    hud_stacked,
                    xy=(hud_left_x, hud_left_y),
                    xycoords="axes fraction",
                    fontsize=hud_left_size,
                    fontname=font_family,
                    fontweight=hud_font_weight,
                    fontstyle=hud_font_style,
                    color=hud_left_text_color,
                    va="top",
                    linespacing=hud_line_spacing,
                    bbox=dict(
                        boxstyle=hud_left_box_style,
                        fc=hud_left_bg_color,
                        ec=hud_left_edge_color,
                        alpha=hud_left_alpha,
                    ),
                    zorder=zo["hud"],
                )
                prev_hud_left_text = hud_stacked

                # HUD right annotation (dynamic - timestamp changes per frame)
                hud_right_ann = ax.annotate(
                    timestamp_text,
                    xy=(hud_right_x, hud_right_y),
                    xycoords="axes fraction",
                    fontsize=hud_right_size,
                    fontname=font_family,
                    fontweight=hud_font_weight,
                    fontstyle=hud_font_style,
                    color=hud_right_text_color,
                    ha="right",
                    va="top",
                    bbox=dict(
                        boxstyle=hud_right_box_style,
                        fc=hud_right_bg_color,
                        ec=hud_right_edge_color,
                        alpha=hud_right_alpha,
                    ),
                    zorder=zo["hud"],
                )
            else:
                # === SUBSEQUENT FRAMES: Update only dynamic content ===
                if channel_key in RGB_COMPOSITE_KEYS:
                    sat_img_artist.set_data(data)
                elif channel_key == "Sandwich":
                    sat_img_artist.set_data(data["vis"])
                    sat_ir_artist.set_data(data["ir"])
                else:
                    sat_img_artist.set_data(data)

                # Update HUD left if satellite changed
                if hud_stacked != prev_hud_left_text:
                    hud_left_ann.set_text(hud_stacked)
                    prev_hud_left_text = hud_stacked

                # Update HUD right timestamp
                hud_right_ann.set_text(timestamp_text)

            # Capture frame via savefig → BytesIO → imread
            if _is_scrubber:
                # Scrubber mode: save every frame as individual PNG
                fig.savefig(
                    frame_path, dpi=_anim_dpi, bbox_inches="tight", pad_inches=0.1
                )
                rendered_frame_paths.append(frame_path)
                ts_utc = scan_time.strftime("%Y-%m-%dT%H:%M:%SZ")
                ts_local = dt_local.strftime("%m/%d/%Y %I:%M %p %Z")

                # Extract frame base name and save individual layers
                frame_base = os.path.splitext(frame_name)[0]
                layers_dict = {}

                # Try rendering layers per-frame, gracefully skip on any error
                try:
                    # Background layer (ocean/land)
                    bg_fig = plt.figure(figsize=(12.8, 7.2), dpi=_anim_dpi)
                    bg_fig.subplots_adjust(
                        left=figure_left_margin,
                        right=1.0 - figure_right_margin,
                        bottom=figure_bottom_margin,
                        top=1.0 - figure_top_margin,
                    )
                    bg_ax = bg_fig.add_subplot(
                        1, 1, 1, projection=sample.metpy.cartopy_crs
                    )
                    bg_ax.set_facecolor(map_bg_color)
                    bg_ax.set_xlim(*ax.get_xlim())
                    bg_ax.set_ylim(*ax.get_ylim())
                    _create_background_layer(bg_ax, bg_fig, style_config)
                    bg_path = os.path.join(frame_dir, f"{frame_base}_bg.png")
                    _save_layer_png(bg_fig, bg_path, dpi=_anim_dpi)
                    layers_dict["background"] = os.path.basename(bg_path)
                except Exception as e:
                    print(f"[WARN] BG layer frame {i}: {e}")

                try:
                    # Satellite data layer
                    sat_fig = plt.figure(figsize=(12.8, 7.2), dpi=_anim_dpi)
                    sat_fig.subplots_adjust(
                        left=figure_left_margin,
                        right=1.0 - figure_right_margin,
                        bottom=figure_bottom_margin,
                        top=1.0 - figure_top_margin,
                    )
                    sat_ax = sat_fig.add_subplot(
                        1, 1, 1, projection=sample.metpy.cartopy_crs
                    )
                    sat_fig.patch.set_alpha(0)
                    sat_ax.patch.set_alpha(0)
                    sat_ax.set_xlim(*ax.get_xlim())
                    sat_ax.set_ylim(*ax.get_ylim())
                    if channel_key in RGB_COMPOSITE_KEYS:
                        sat_ax.imshow(
                            data,
                            extent=img_extent,
                            origin="upper",
                            interpolation="bicubic",
                            zorder=zo["sat_image"],
                        )
                    elif channel_key == "Sandwich":
                        sat_ax.imshow(
                            data["vis"],
                            cmap="Greys_r",
                            extent=img_extent,
                            origin="upper",
                            interpolation="bicubic",
                            zorder=zo["sat_image"],
                        )
                        sat_ax.imshow(
                            data["ir"],
                            extent=img_extent,
                            origin="upper",
                            interpolation="bicubic",
                            zorder=zo["sat_image"] + 1,
                        )
                    else:
                        target_norm = ABI_CHANNELS[channel_key].get("norm")
                        interp_mode = (
                            "nearest"
                            if str(channel_key).startswith("Channel13")
                            else "bicubic"
                        )
                        sat_ax.imshow(
                            data,
                            cmap=ABI_CHANNELS[channel_key]["cmap"],
                            norm=target_norm,
                            extent=img_extent,
                            origin="upper",
                            interpolation=interp_mode,
                            zorder=zo["sat_image"],
                        )
                    sat_path = os.path.join(frame_dir, f"{frame_base}_sat.png")
                    _save_layer_png(sat_fig, sat_path, dpi=_anim_dpi, transparent=True)
                    layers_dict["satellite"] = os.path.basename(sat_path)
                except Exception as e:
                    print(f"[WARN] Satellite layer frame {i}: {e}")

                try:
                    # Borders layer
                    brd_fig = plt.figure(figsize=(12.8, 7.2), dpi=_anim_dpi)
                    brd_fig.subplots_adjust(
                        left=figure_left_margin,
                        right=1.0 - figure_right_margin,
                        bottom=figure_bottom_margin,
                        top=1.0 - figure_top_margin,
                    )
                    brd_ax = brd_fig.add_subplot(
                        1, 1, 1, projection=sample.metpy.cartopy_crs
                    )
                    brd_fig.patch.set_alpha(0)
                    brd_ax.patch.set_alpha(0)
                    brd_ax.set_xlim(*ax.get_xlim())
                    brd_ax.set_ylim(*ax.get_ylim())
                    _create_borders_layer(brd_ax, brd_fig, style_config)
                    brd_path = os.path.join(frame_dir, f"{frame_base}_borders.png")
                    _save_layer_png(brd_fig, brd_path, dpi=_anim_dpi, transparent=True)
                    layers_dict["borders"] = os.path.basename(brd_path)
                except Exception as e:
                    print(f"[WARN] Borders layer frame {i}: {e}")

                try:
                    # Cities layer
                    city_fig = plt.figure(figsize=(12.8, 7.2), dpi=_anim_dpi)
                    city_fig.subplots_adjust(
                        left=figure_left_margin,
                        right=1.0 - figure_right_margin,
                        bottom=figure_bottom_margin,
                        top=1.0 - figure_top_margin,
                    )
                    city_ax = city_fig.add_subplot(
                        1, 1, 1, projection=sample.metpy.cartopy_crs
                    )
                    city_fig.patch.set_alpha(0)
                    city_ax.patch.set_alpha(0)
                    city_ax.set_xlim(*ax.get_xlim())
                    city_ax.set_ylim(*ax.get_ylim())
                    curr_ext = city_ax.get_extent(crs=ccrs.PlateCarree())
                    _create_cities_layer(city_ax, city_fig, curr_ext, style_config)
                    city_path = os.path.join(frame_dir, f"{frame_base}_cities.png")
                    _save_layer_png(
                        city_fig, city_path, dpi=_anim_dpi, transparent=True
                    )
                    layers_dict["cities"] = os.path.basename(city_path)
                except Exception as e:
                    print(f"[WARN] Cities layer frame {i}: {e}")

                try:
                    # HUD layer
                    hud_fig = plt.figure(figsize=(12.8, 7.2), dpi=_anim_dpi)
                    hud_fig.subplots_adjust(
                        left=figure_left_margin,
                        right=1.0 - figure_right_margin,
                        bottom=figure_bottom_margin,
                        top=1.0 - figure_top_margin,
                    )
                    hud_ax = hud_fig.add_subplot(
                        1, 1, 1, projection=sample.metpy.cartopy_crs
                    )
                    hud_fig.patch.set_alpha(0)
                    hud_ax.patch.set_alpha(0)
                    hud_ax.set_xlim(*ax.get_xlim())
                    hud_ax.set_ylim(*ax.get_ylim())
                    _create_hud_layer(
                        hud_ax,
                        hud_fig,
                        timestamp_text,
                        channel_key,
                        sector,
                        sat_num,
                        region_label,
                        custom_extent,
                        style_config,
                    )
                    hud_path = os.path.join(frame_dir, f"{frame_base}_hud.png")
                    _save_layer_png(hud_fig, hud_path, dpi=_anim_dpi, transparent=True)
                    layers_dict["hud"] = os.path.basename(hud_path)
                except Exception as e:
                    print(f"[WARN] HUD layer frame {i}: {e}")

                try:
                    # Logo layer
                    logo_fig = plt.figure(figsize=(12.8, 7.2), dpi=_anim_dpi)
                    logo_fig.subplots_adjust(
                        left=figure_left_margin,
                        right=1.0 - figure_right_margin,
                        bottom=figure_bottom_margin,
                        top=1.0 - figure_top_margin,
                    )
                    logo_ax = logo_fig.add_subplot(
                        1, 1, 1, projection=sample.metpy.cartopy_crs
                    )
                    logo_fig.patch.set_alpha(0)
                    logo_ax.patch.set_alpha(0)
                    logo_ax.set_xlim(*ax.get_xlim())
                    logo_ax.set_ylim(*ax.get_ylim())
                    _create_logo_layer(logo_ax, logo_fig, logo_file, style_config)
                    logo_path = os.path.join(frame_dir, f"{frame_base}_logo.png")
                    _save_layer_png(
                        logo_fig, logo_path, dpi=_anim_dpi, transparent=True
                    )
                    layers_dict["logo"] = os.path.basename(logo_path)
                except Exception as e:
                    print(f"[WARN] Logo layer frame {i}: {e}")

                scrubber_manifest.append(
                    {
                        "index": i,
                        "path": frame_path,
                        "timestamp_utc": ts_utc,
                        "timestamp_local": ts_local,
                        "layers": layers_dict,
                    }
                )
            else:
                buf = io.BytesIO()
                fig.savefig(
                    buf,
                    format="png",
                    dpi=_anim_dpi,
                    bbox_inches="tight",
                    pad_inches=0.1,
                )
                buf.seek(0)
                frame_data = imageio.imread(buf)
                if frame_data.shape[-1] == 4:
                    frame_data = frame_data[:, :, :3]
                frames.append(frame_data)
                fig.savefig(
                    frame_path, dpi=_anim_dpi, bbox_inches="tight", pad_inches=0.1
                )
                rendered_frame_paths.append(frame_path)

            _frame_elapsed = _time.perf_counter() - _frame_start
            print(
                f"[Perf] Archive frame {i}/{total}: {_frame_elapsed:.2f}s {'(setup)' if i == 0 else '(update)'}"
            )
        except Exception as e:
            print(
                f"[WARN] Satellite archive frame skipped ({i}): {type(e).__name__}: {e}"
            )
        finally:
            for ds in current_ds.values():
                try:
                    ds.close()
                except Exception:
                    pass

    # Clean up reused figure
    if fig is not None:
        plt.close(fig)

    if not frames and not scrubber_manifest:
        return None, None, "No renderable archive frames produced."

    # ── Scrubber mode: return manifest dict instead of movie/preview paths ──
    if _is_scrubber:
        if not scrubber_manifest:
            return None, None, "No renderable archive frames produced."

        frames_ref_path = None
        try:
            manifest_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            manifest_name = f"scrubber_manifest_{request_start_code}_{request_end_code}_{manifest_stamp}.json"
            frames_ref_path = os.path.join(output_dir, manifest_name)
            manifest_payload = {
                "created_utc": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "request_start_code": request_start_code,
                "request_end_code": request_end_code,
                "frame_files": [
                    os.path.basename(entry["path"]) for entry in scrubber_manifest
                ],
            }
            with open(frames_ref_path, "w", encoding="utf-8") as manifest_file:
                json.dump(manifest_payload, manifest_file, indent=2)
        except Exception as manifest_error:
            print(f"[WARN] Could not write scrubber manifest: {manifest_error}")

        return (
            {
                "mode": "scrubber",
                "frames": scrubber_manifest,
                "frame_dir": frame_dir,
                "frames_ref": frames_ref_path or frame_dir,
                "output_dir": output_dir,
                "total": len(scrubber_manifest),
                "fps": int(fps),
                "message": f"{len(scrubber_manifest)} archive frames generated.",
            },
            None,
            f"{len(scrubber_manifest)} archive frames generated.",
        )

    if len(frames) == 1:
        static_path = rendered_frame_paths[-1] if rendered_frame_paths else None
        if not static_path or not os.path.exists(static_path):
            return None, None, "No renderable archive frames produced."
        return None, static_path, "1 archive frame generated."

    try:
        from video_utils import save_animation

        start_code = frame_plan[0][0].strftime("%Y%m%d_%H%M")
        end_code = frame_plan[-1][0].strftime("%Y%m%d_%H%M")
        movie_path = os.path.join(output_dir, f"{start_code}-{end_code}_archive.mp4")
        save_animation(movie_path, frames, fps=int(fps))
        preview_path = rendered_frame_paths[-1] if rendered_frame_paths else None
        return movie_path, preview_path, f"{len(frames)} archive frames generated."
    except Exception as e:
        return None, None, f"Error creating archive animation: {e}"
