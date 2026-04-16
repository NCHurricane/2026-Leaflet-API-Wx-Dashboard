"""
Pre-renders a static basemap PNG for every NEXRAD radar station.
Run this once, or whenever style/border settings change.

Each basemap contains the static geographic layers (land, lakes, rivers,
highways, state borders) rendered at the exact 100 nm radar extent for that
station (no padding beyond the range rings).

Basemaps are saved as:
    basemap_cache/radar/{STATION_ID}/{STATION_ID}.png

Usage:
    python radar/generate_radar_basemaps.py
    python radar/generate_radar_basemaps.py --stations KMHX KLTX KRAX
    python radar/generate_radar_basemaps.py --force
"""

from radar.radar_utils import compute_radar_extent
import argparse
import multiprocessing
import os
import sys
import time

import matplotlib
import matplotlib.pyplot as plt
import cartopy.feature as cfeature
import cartopy.crs as ccrs
import numpy as np

matplotlib.use("Agg")

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Output root: basemap_cache/radar/
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASEMAP_CACHE_ROOT = os.path.join(_BASE_DIR, "basemap_cache", "radar")

# Default style values matching radar_utils defaults
_LAND_COLOR = "#5C5C5C"
_OCEAN_COLOR = "#152238"
_LAKE_COLOR = "#152238"
_LAKE_OUTLINE_COLOR = "#333333"
_LAKE_OUTLINE_WIDTH = 0.5
_RIVER_COLOR = "#152238"
_RIVER_WIDTH = 0.5
_HIGHWAY_COLOR = "#888888"
_HIGHWAY_WIDTH = 0.8
_HIGHWAY_OPACITY = 0.6
_STATE_COLOR = "#ffffff"
_STATE_WIDTH = 0.5
_MAP_BG_COLOR = "#152238"

# Cartopy feature scale
_NE_SCALE = "10m"
_OUTPUT_DPI = 150
_BASE_FIG_HEIGHT_IN = 7.2

# No padding — basemap covers exactly the 100 nm radar range
_PADDING_FACTOR = 1.0


def get_basemap_path(station_id: str) -> str:
    """Return the output path: basemap_cache/radar/{SITE}/{SITE}.png"""
    return os.path.join(BASEMAP_CACHE_ROOT, station_id.upper(), f"{station_id.upper()}.png")


def _get_nexrad_locations():
    """Return dict of station_id -> (lat, lon) from pyart."""
    from pyart.io.nexrad_common import NEXRAD_LOCATIONS

    return {sid: (info["lat"], info["lon"]) for sid, info in NEXRAD_LOCATIONS.items()}


def _compute_extent_ratio(min_lat, max_lat, min_lon, max_lon, projection):
    corners_ll = [
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
    ]
    try:
        corners_ll = np.array(corners_ll)
        corners_proj = projection.transform_points(
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

    lat_span = max(max_lat - min_lat, 1e-6)
    lon_span = max(min(abs(max_lon - min_lon), 360.0), 1e-6)
    return lon_span / lat_span


def render_radar_basemap(station_id: str, lat: float, lon: float, force: bool = False):
    """Render and save a basemap PNG for a single NEXRAD station.

    Saves to basemap_cache/radar/{station_id}/{station_id}.png
    Returns the path to the saved PNG, or None on error.
    """
    out_path = get_basemap_path(station_id)

    if not force and os.path.exists(out_path):
        print(f"  [skip] {station_id} — cache hit")
        return out_path

    t0 = time.time()

    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    min_lat, max_lat, min_lon, max_lon = compute_radar_extent(
        lat, lon, padding_factor=_PADDING_FACTOR)

    proj = ccrs.LambertConformal(central_longitude=lon, central_latitude=lat)
    ratio = _compute_extent_ratio(min_lat, max_lat, min_lon, max_lon, proj)
    fig_width = max(_BASE_FIG_HEIGHT_IN * ratio, 4.0)
    fig = plt.figure(figsize=(fig_width, _BASE_FIG_HEIGHT_IN), dpi=_OUTPUT_DPI)
    ax = fig.add_axes([0, 0, 1, 1], projection=proj)
    ax.set_extent([min_lon, max_lon, min_lat, max_lat], crs=ccrs.PlateCarree())
    ax.set_aspect("equal", adjustable="box")

    # Background fill (ocean / map background)
    ax.set_facecolor(_MAP_BG_COLOR)
    fig.patch.set_facecolor(_MAP_BG_COLOR)

    # Land only — no outlines, borders, highways, rivers, or lakes
    ax.add_feature(
        cfeature.LAND.with_scale(_NE_SCALE),
        facecolor=_LAND_COLOR,
        edgecolor="none",
        zorder=1,
    )

    # Ocean
    ax.add_feature(
        cfeature.OCEAN.with_scale(_NE_SCALE),
        facecolor=_OCEAN_COLOR,
        edgecolor="none",
        zorder=0,
    )

    plt.savefig(out_path, dpi=_OUTPUT_DPI, pad_inches=0)
    plt.close(fig)

    elapsed = time.time() - t0
    print(
        f"  [done] {station_id} ({lat:.2f}, {lon:.2f}) -> {out_path}  [{elapsed:.1f}s]")
    return out_path


def _render_worker(args):
    """Top-level wrapper for multiprocessing.Pool — must be picklable."""
    sid, lat, lon, force = args
    try:
        render_radar_basemap(sid, lat, lon, force=force)
        return sid, True, None
    except Exception as e:
        return sid, False, str(e)


def main():
    parser = argparse.ArgumentParser(
        description="Pre-render radar basemaps for all NEXRAD stations."
    )
    parser.add_argument(
        "--stations",
        nargs="*",
        default=None,
        help="Space-separated list of station IDs (e.g. KMHX KLTX KRAX). Omit for all.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-render even if a cached basemap already exists.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel worker processes (default: CPU count).",
    )
    args = parser.parse_args()

    locations = _get_nexrad_locations()

    if args.stations:
        targets = {
            s.upper(): locations[s.upper()]
            for s in args.stations
            if s.upper() in locations
        }
        missing = [s for s in args.stations if s.upper() not in locations]
        if missing:
            print(
                f"[WARN] Unknown stations (not in pyart): {', '.join(missing)}")
    else:
        targets = locations

    workers = args.workers or min(multiprocessing.cpu_count(), len(targets))
    print(
        f"Rendering radar basemaps for {len(targets)} station(s) -> {BASEMAP_CACHE_ROOT}")
    print(f"Using {workers} parallel worker(s)\n")
    t_all = time.time()

    job_args = [(sid, lat, lon, args.force)
                for sid, (lat, lon) in sorted(targets.items())]

    ok, failed = 0, []
    with multiprocessing.Pool(processes=workers) as pool:
        for result in pool.imap_unordered(_render_worker, job_args):
            sid, success, err = result
            if success:
                ok += 1
            else:
                print(f"  [FAIL] {sid}: {err}")
                failed.append(sid)

    print(
        f"\nDone. {ok} rendered, {len(failed)} failed in {time.time() - t_all:.1f}s")
    if failed:
        print(f"Failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
