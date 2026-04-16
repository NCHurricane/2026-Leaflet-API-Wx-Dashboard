"""
Pre-renders a static basemap PNG for every available US state and territory.
Run this once, or whenever shared basemap colors change.

Each basemap contains only land and ocean fills rendered at the exact
geographic bounds of the dissolved state or territory outline.

Basemaps are saved as:
    basemap_cache/states/{STATE_ID}/{STATE_ID}.png

Usage:
    python tools/generate_state_basemaps.py
    python tools/generate_state_basemaps.py --states NC PR GU CONUS
    python tools/generate_state_basemaps.py --force
"""

from shapely.ops import unary_union
import numpy as np
import matplotlib.pyplot as plt
import cartopy.io.shapereader as shpreader
import cartopy.feature as cfeature
import cartopy.crs as ccrs
import argparse
import multiprocessing
import os
import sys
import time
import warnings

import matplotlib
matplotlib.use("Agg")


# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATES_SHAPEFILE_DIR = os.path.join(_BASE_DIR, "shapefiles", "states")
BASEMAP_CACHE_ROOT = os.path.join(_BASE_DIR, "basemap_cache", "states")

_LAND_COLOR = "#5C5C5C"
_OCEAN_COLOR = "#152238"
_OUTLINE_COLOR = "#E6E6E6"
_OUTLINE_WIDTH = 0.2
_OUTPUT_DPI = 150
_BASE_FIG_HEIGHT_IN = 7.2
_NE_SCALE = "10m"
_CONUS_EXCLUDED_CODES = {"AK", "HI", "AS", "GU", "MP", "PR", "VI", "CONUS"}
_CONUS_LON_PAD_FRAC = 0.03
_CONUS_MIN_LON_PAD = 1.5
_CONUS_LAT_PAD_FRAC = 0.02
_CONUS_MIN_LAT_PAD = 0.6
_CONUS_TOP_PAD_DEG = 3.5
_CONUS_BOTTOM_PAD_DEG = 0.8


def get_basemap_path(state_id: str) -> str:
    """Return the output path: basemap_cache/states/{STATE}/{STATE}.png"""
    state_code = str(state_id or "").strip().upper()
    return os.path.join(BASEMAP_CACHE_ROOT, state_code, f"{state_code}.png")


def _state_outline_shapefile_path(state_id: str) -> str:
    state_code = str(state_id or "").strip().upper()
    return os.path.join(
        _STATES_SHAPEFILE_DIR,
        state_code,
        f"state_{state_code}.shp",
    )


def _get_available_state_codes():
    """Return sorted state and territory codes backed by dissolved outlines."""
    if not os.path.isdir(_STATES_SHAPEFILE_DIR):
        return []

    codes = []
    for entry in sorted(os.listdir(_STATES_SHAPEFILE_DIR)):
        shp_path = os.path.join(_STATES_SHAPEFILE_DIR,
                                entry, f"state_{entry}.shp")
        if os.path.exists(shp_path):
            codes.append(entry.upper())

    if "CONUS" not in codes:
        codes.append("CONUS")

    return codes


def _load_state_geometry(state_id: str):
    """Load and dissolve the canonical outline geometry for one state or territory."""
    shp_path = _state_outline_shapefile_path(state_id)
    if not os.path.exists(shp_path):
        raise FileNotFoundError(
            f"Missing dissolved outline shapefile: {shp_path}")

    reader = shpreader.Reader(shp_path)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message=".*Possible issue encountered.*")
        warnings.filterwarnings("ignore", message=".*polygon interior holes.*")
        geometries = list(reader.geometries())

    if not geometries:
        raise ValueError(f"No geometries found in {shp_path}")

    geometry = unary_union(geometries)
    if hasattr(geometry, "buffer"):
        geometry = geometry.buffer(0)
    return geometry


def _load_conus_geometry():
    """Build a CONUS geometry by dissolving available lower-48 + DC outlines."""
    candidate_codes = [
        code
        for code in _get_available_state_codes()
        if code not in _CONUS_EXCLUDED_CODES
    ]

    geometries = []
    for code in candidate_codes:
        try:
            geometries.append(_load_state_geometry(code))
        except Exception as exc:
            print(f"  [warn] skipping {code} for CONUS union: {exc}")

    if not geometries:
        raise ValueError(
            "Could not build CONUS geometry from available state outlines")

    geometry = unary_union(geometries)
    if hasattr(geometry, "buffer"):
        geometry = geometry.buffer(0)
    return geometry


def _iter_longitudes(geometry):
    geom_type = getattr(geometry, "geom_type", "")
    if geom_type == "Polygon":
        for lon, _lat in geometry.exterior.coords:
            yield float(lon)
        for interior in geometry.interiors:
            for lon, _lat in interior.coords:
                yield float(lon)
        return

    if geom_type == "MultiPolygon":
        for polygon in geometry.geoms:
            yield from _iter_longitudes(polygon)
        return

    if hasattr(geometry, "geoms"):
        for item in geometry.geoms:
            yield from _iter_longitudes(item)


def _minimal_longitude_interval(longitudes):
    """Return the narrowest longitudinal interval covering all longitudes."""
    values = [float(lon) for lon in longitudes]
    if not values:
        raise ValueError("Geometry does not contain longitude coordinates")
    if len(values) == 1:
        only = values[0]
        return only, only

    normalized = sorted(((lon + 360.0) % 360.0) for lon in values)
    wrapped = normalized + [normalized[0] + 360.0]

    max_gap = -1.0
    gap_index = 0
    for index in range(len(normalized)):
        gap = wrapped[index + 1] - wrapped[index]
        if gap > max_gap:
            max_gap = gap
            gap_index = index

    west = wrapped[gap_index + 1]
    east = wrapped[gap_index] + 360.0
    if east < west:
        east += 360.0
    return west, east


def _normalize_longitude(lon):
    """Normalize any longitude to the [-180, 180) range."""
    value = float(lon)
    return ((value + 180.0) % 360.0) - 180.0


def _get_geometry_bounds(geometry):
    """Return exact geographic bounds as west, east, south, north."""
    min_lon, min_lat, max_lon, max_lat = geometry.bounds
    west, east = _minimal_longitude_interval(_iter_longitudes(geometry))

    if (east - west) > 300.0:
        west = float(min_lon)
        east = float(max_lon)

    # If the interval is in wrapped 0..360 space, shift back to -180..180.
    if west > 180.0 and east > 180.0:
        west = _normalize_longitude(west)
        east = _normalize_longitude(east)

    return float(west), float(east), float(min_lat), float(max_lat)


def _compute_extent_ratio(south, north, west, east, projection):
    """Compute projected width/height ratio by sampling many points along
    each edge of the extent rectangle.  A 4-corner-only approach
    underestimates projected height for LambertConformal because latitude
    arcs extend beyond corner projections."""
    _N = 50
    _sample_east = east + 360.0 if west > east else east
    edge_lons = np.concatenate([
        np.linspace(west, _sample_east, _N),
        np.full(_N, _sample_east),
        np.linspace(_sample_east, west, _N),
        np.full(_N, west),
    ])
    edge_lats = np.concatenate([
        np.full(_N, south),
        np.linspace(south, north, _N),
        np.full(_N, north),
        np.linspace(north, south, _N),
    ])

    try:
        pts = projection.transform_points(
            ccrs.PlateCarree(), edge_lons, edge_lats,
        )
        xs = pts[:, 0]
        ys = pts[:, 1]
        mask = np.isfinite(xs) & np.isfinite(ys)
        if mask.any():
            width = float(xs[mask].max() - xs[mask].min())
            height = float(ys[mask].max() - ys[mask].min())
            if width > 0.0 and height > 0.0:
                return width / height
    except Exception:
        pass

    lat_span = max(north - south, 1e-6)
    lon_span = max(abs(east - west), 1e-6)
    return lon_span / lat_span


def _expand_extent(
    west,
    east,
    south,
    north,
    lon_frac=0.06,
    lat_frac=0.06,
    min_lon_pad=0.35,
    min_lat_pad=0.25,
):
    """Expand bounds by a percentage of the current lon/lat span."""
    if west > east:
        # Antimeridian-crossing: actual span wraps through 360
        lon_span = max((east + 360.0) - west, 1e-6)
    else:
        lon_span = max(east - west, 1e-6)
    lat_span = max(abs(north - south), 1e-6)

    lon_pad = max(lon_span * lon_frac, float(min_lon_pad))
    lat_pad = max(lat_span * lat_frac, float(min_lat_pad))

    return (
        west - lon_pad,
        east + lon_pad,
        max(-90.0, south - lat_pad),
        min(90.0, north + lat_pad),
    )


def render_state_basemap(state_id: str, force: bool = False):
    """Render and save a basemap PNG for one state or territory."""
    state_code = str(state_id or "").strip().upper()
    out_path = get_basemap_path(state_code)

    if not force and os.path.exists(out_path):
        print(f"  [skip] {state_code} - cache hit")
        return out_path

    t0 = time.time()
    if state_code == "CONUS":
        geometry = _load_conus_geometry()
    else:
        geometry = _load_state_geometry(state_code)
    west, east, south, north = _get_geometry_bounds(geometry)
    if state_code == "CONUS":
        # Add modest horizontal breathing room for full-CONUS framing.
        west, east, south, north = _expand_extent(
            west,
            east,
            south,
            north,
            lon_frac=_CONUS_LON_PAD_FRAC,
            lat_frac=_CONUS_LAT_PAD_FRAC,
            min_lon_pad=_CONUS_MIN_LON_PAD,
            min_lat_pad=_CONUS_MIN_LAT_PAD,
        )
        south = max(-90.0, south - _CONUS_BOTTOM_PAD_DEG)
        north = min(90.0, north + _CONUS_TOP_PAD_DEG)
    else:
        west, east, south, north = _expand_extent(west, east, south, north)

    if west > east:
        # Antimeridian-crossing extent (e.g. Alaska):
        # wrap east by +360 before averaging, then normalize.
        center_lon = _normalize_longitude(
            west + ((east + 360.0 - west) / 2.0)
        )
    else:
        center_lon = _normalize_longitude(west + ((east - west) / 2.0))
    center_lat = south + ((north - south) / 2.0)

    if state_code == "CONUS":
        # Match alerts CONUS rendering anchor projection.
        projection = ccrs.PlateCarree()
    else:
        projection = ccrs.LambertConformal(
            central_longitude=center_lon,
            central_latitude=center_lat,
        )

    ratio = _compute_extent_ratio(south, north, west, east, projection)
    fig_width = max(_BASE_FIG_HEIGHT_IN * ratio, 4.0)

    _set_east = east + 360.0 if west > east else east
    fig = plt.figure(figsize=(fig_width, _BASE_FIG_HEIGHT_IN), dpi=_OUTPUT_DPI)
    ax = fig.add_axes([0, 0, 1, 1], projection=projection)
    ax.set_extent([west, _set_east, south, north], crs=ccrs.PlateCarree())
    if state_code == "CONUS":
        # Fill the frame for CONUS to avoid large side ocean bands.
        ax.set_aspect("auto")
    else:
        ax.set_aspect("equal", adjustable="box")

    ax.add_feature(
        cfeature.OCEAN.with_scale(_NE_SCALE),
        facecolor=_OCEAN_COLOR,
        edgecolor="none",
        zorder=0,
    )
    ax.add_feature(
        cfeature.LAND.with_scale(_NE_SCALE),
        facecolor=_LAND_COLOR,
        edgecolor="none",
        zorder=1,
    )
    # CONUS outline can introduce an extra visible seam line in products that
    # already draw counties/states overlays. Keep state/territory outlines only.
    if state_code != "CONUS":
        ax.add_geometries(
            [geometry],
            ccrs.PlateCarree(),
            facecolor="none",
            edgecolor=_OUTLINE_COLOR,
            linewidth=_OUTLINE_WIDTH,
            zorder=2,
        )

    # Transparent background so data layer composites cleanly
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.savefig(out_path, dpi=_OUTPUT_DPI, pad_inches=0, transparent=True)
    plt.close(fig)

    elapsed = time.time() - t0
    print(f"  [done] {state_code} -> {out_path}  [{elapsed:.1f}s]")
    return out_path


def _render_worker(args):
    """Top-level wrapper for multiprocessing.Pool - must be picklable."""
    state_id, force = args
    try:
        render_state_basemap(state_id, force=force)
        return state_id, True, None
    except Exception as exc:
        return state_id, False, str(exc)


def main():
    parser = argparse.ArgumentParser(
        description="Pre-render state and territory basemaps from dissolved outlines."
    )
    parser.add_argument(
        "--states",
        nargs="*",
        default=None,
        help="Space-separated list of state/territory codes, including CONUS (e.g. NC PR GU CONUS). Omit for all available outlines.",
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

    available_codes = _get_available_state_codes()
    if not available_codes:
        raise FileNotFoundError(
            f"No dissolved state outlines found under {_STATES_SHAPEFILE_DIR}"
        )

    if args.states:
        requested_codes = [code.upper() for code in args.states]
        targets = [code for code in requested_codes if code in available_codes]
        missing = [
            code for code in requested_codes if code not in available_codes]
        if missing:
            print(
                f"[WARN] Unknown or unavailable state codes: {', '.join(missing)}")
    else:
        targets = available_codes

    if not targets:
        raise ValueError("No valid state or territory targets were provided")

    workers = args.workers or min(multiprocessing.cpu_count(), len(targets))
    print(
        f"Rendering state basemaps for {len(targets)} region(s) -> {BASEMAP_CACHE_ROOT}"
    )
    print(f"Using {workers} parallel worker(s)\n")
    t_all = time.time()

    job_args = [(state_id, args.force) for state_id in sorted(targets)]

    ok = 0
    failed = []
    with multiprocessing.Pool(processes=workers) as pool:
        for state_id, success, err in pool.imap_unordered(_render_worker, job_args):
            if success:
                ok += 1
            else:
                print(f"  [FAIL] {state_id}: {err}")
                failed.append(state_id)

    print(
        f"\nDone. {ok} rendered, {len(failed)} failed in {time.time() - t_all:.1f}s")
    if failed:
        print(f"Failed: {', '.join(sorted(failed))}")


if __name__ == "__main__":
    main()
