"""Background worker: pre-fetches surface METAR observations and gradients.

Refreshes the CONUS and WORLD raw CSV caches so /api/data/surface returns fast.
Also pre-renders high-resolution CONUS gradient overlays for Currents products
so product switches do not require client-side interpolation work.
"""

from __future__ import annotations

import json
import os
import tempfile
import time as _time
from datetime import datetime, timezone

import matplotlib
import numpy as np
from scipy.spatial import cKDTree
from rasterio.features import rasterize as _rasterize
from rasterio.transform import from_bounds as _from_bounds
from shapely.ops import transform as _shapely_transform

from config.geo_config import STATE_BOUNDS
from lib.geo_utils import build_conus_geometry as _build_conus_geometry
from lib.geo_utils import build_world_land_geometry as _build_world_land_geometry

from workers._freshness import is_cache_fresh, mark_run_complete

# Regions to keep warm.  CONUS is the gradient source for all US states;
# WORLD is the gradient source when the user is at the WORLD view.
_PRELOAD_REGIONS: list[str] = ["CONUS", "WORLD"]

# Skip if a successful refresh happened within the last 22 min (75% of 30 min interval)
_FRESH_WINDOW_SEC = 22 * 60

_CACHE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache"
)


def _gradient_root(region: str) -> str:
    region_dir = "WORLD" if region.upper() == "WORLD" else "CONUS"
    return os.path.join(_CACHE_ROOT, "surface", "gradients", region_dir)


# Higher-res fixed CONUS gradient grid. This is rendered worker-side once per cycle.
_GRADIENT_WIDTH = 5120
_GRADIENT_HEIGHT = 2240

# World gradient grid — lower pixel density but covers the full globe.
_GRADIENT_WIDTH_WORLD = 3600
_GRADIENT_HEIGHT_WORLD = 1800

_SURFACE_GRADIENT_PRODUCTS: dict[str, dict] = {
    "temperature": {
        "col": "air_temperature",
        "unit": "degF",
        "anchors": [
            (-60, "#00352C"),
            (-20, "#c4c4d4"),
            (0, "#570057"),
            (32, "#0000ff"),
            (50, "#c4c403"),
            (80, "#c20303"),
            (130, "#000000"),
        ],
    },
    "feels_like": {
        "col": "feels_like",
        "unit": "degF",
        "anchors": [
            (-60, "#00352C"),
            (-20, "#c4c4d4"),
            (0, "#570057"),
            (32, "#0000ff"),
            (50, "#c4c403"),
            (80, "#c20303"),
            (130, "#000000"),
        ],
    },
    "dew_point": {
        "col": "dew_point_temperature",
        "unit": "degF",
        "anchors": [
            (-60, "#00352C"),
            (-20, "#c4c4d4"),
            (0, "#570057"),
            (32, "#0000ff"),
            (50, "#c4c403"),
            (80, "#c20303"),
            (130, "#000000"),
        ],
    },
    "relative_humidity": {
        "col": "relative_humidity",
        "unit": "%",
        "anchors": [
            (0, "#c8a000"),
            (20, "#f5dd72"),
            (40, "#69bb6d"),
            (60, "#0099cc"),
            (80, "#0055aa"),
            (100, "#003377"),
        ],
    },
    "wind_speed": {
        "col": "wind_speed",
        "unit": "kt",
        "anchors": [
            (0, "#b0d4f0"),
            (10, "#70b0e0"),
            (20, "#3090d0"),
            (30, "#f5dd72"),
            (45, "#ff9d2e"),
            (60, "#ff4f4f"),
        ],
    },
    "wind_gust": {
        "col": "peak_wind",
        "unit": "kt",
        "anchors": [
            (0, "#b0d4f0"),
            (10, "#70b0e0"),
            (20, "#3090d0"),
            (30, "#f5dd72"),
            (45, "#ff9d2e"),
            (60, "#ff4f4f"),
        ],
    },
    "altimeter": {
        "col": "altimeter",
        "unit": "inHg",
        "anchors": [
            (29.5, "#5b1a8f"),
            (30.0, "#2a6db3"),
            (30.2, "#2ca58d"),
            (30.4, "#f5dd72"),
            (30.6, "#ff9d2e"),
            (30.8, "#bf2c2c"),
        ],
    },
    "mslp": {
        "col": "mean_sea_level_pressure",
        "unit": "hPa",
        "anchors": [
            (990, "#5b1a8f"),
            (1000, "#2a6db3"),
            (1010, "#2ca58d"),
            (1020, "#f5dd72"),
            (1030, "#ff9d2e"),
            (1040, "#bf2c2c"),
        ],
    },
    "visibility": {
        "col": "visibility",
        "unit": "mi",
        "anchors": [
            (0, "#7f1d1d"),
            (1, "#b45309"),
            (3, "#d97706"),
            (5, "#65a30d"),
            (7, "#16a34a"),
            (10, "#0ea5e9"),
        ],
    },
}


def _normalize_product_selection(products: list[str] | None) -> set[str] | None:
    if not products:
        return None
    selected = {
        str(product).strip().lower() for product in products if str(product).strip()
    }
    if not selected:
        return None
    unknown = sorted(selected - set(_SURFACE_GRADIENT_PRODUCTS.keys()))
    if unknown:
        raise ValueError(
            f"Unknown gradient product(s): {unknown}. "
            f"Valid: {sorted(_SURFACE_GRADIENT_PRODUCTS.keys())}"
        )
    return selected


def _cleanup_stale_gradient_temp_files(region: str = "CONUS") -> None:
    root = _gradient_root(region)
    if not os.path.isdir(root):
        return
    try:
        for name in os.listdir(root):
            if name.endswith(".png.part"):
                try:
                    os.remove(os.path.join(root, name))
                except OSError:
                    pass
    except OSError:
        pass


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hc = str(hex_color).strip().lstrip("#")
    return int(hc[0:2], 16), int(hc[2:4], 16), int(hc[4:6], 16)


def _build_rgba_from_values(
    values: np.ndarray, anchors: list[tuple[float, str]]
) -> np.ndarray:
    anchor_vals = np.array([float(a[0]) for a in anchors], dtype=np.float32)
    rgb = np.array([_hex_to_rgb(a[1]) for a in anchors], dtype=np.float32)

    clipped = np.clip(values, anchor_vals[0], anchor_vals[-1])
    r = np.interp(clipped, anchor_vals, rgb[:, 0])
    g = np.interp(clipped, anchor_vals, rgb[:, 1])
    b = np.interp(clipped, anchor_vals, rgb[:, 2])

    rgba = np.zeros((values.shape[0], values.shape[1], 4), dtype=np.uint8)
    rgba[:, :, 0] = np.clip(r, 0, 255).astype(np.uint8)
    rgba[:, :, 1] = np.clip(g, 0, 255).astype(np.uint8)
    rgba[:, :, 2] = np.clip(b, 0, 255).astype(np.uint8)
    rgba[:, :, 3] = 255
    return rgba


# Maximum allowed deviation from the local neighbor median, per product.
# A station whose value differs from its K-nearest-neighbor median by more
# than this threshold is treated as an outlier and dropped before IDW.
_OUTLIER_THRESHOLDS: dict[str, float] = {
    "temperature": 50.0,  # °F
    "feels_like": 18.0,  # °F  (wider — wind/humidity amplify apparent spread)
    "dew_point": 15.0,  # °F
    "relative_humidity": 25.0,  # %
    "wind_speed": 20.0,  # kt
    "wind_gust": 25.0,  # kt
    # inHg  (synoptic gradients are large; only catch sensor faults)
    "altimeter": 1.0,
    "mslp": 8.0,  # hPa
    "visibility": 5.0,  # mi
}

_OUTLIER_NEIGHBORS = 8  # neighbors used for local median comparison


def _filter_spatial_outliers(
    lons: np.ndarray,
    lats: np.ndarray,
    vals: np.ndarray,
    product: str,
    cos_lat: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Drop stations whose value deviates from the local neighbor median
    by more than the product-specific threshold.
    Returns filtered (lons, lats, vals).
    """
    threshold = _OUTLIER_THRESHOLDS.get(product)
    if threshold is None or len(vals) < _OUTLIER_NEIGHBORS + 1:
        return lons, lats, vals

    sx = lons * cos_lat * 111.0
    sy = lats * 111.0
    tree = cKDTree(np.column_stack([sx, sy]))

    k = min(_OUTLIER_NEIGHBORS, len(vals) - 1)
    _, idxs = tree.query(np.column_stack(
        [sx, sy]), k=k + 1)  # +1 includes self
    # idxs[:, 0] is the point itself; skip it
    neighbor_idxs = idxs[:, 1:]
    neighbor_vals = vals[neighbor_idxs]  # (N, k)
    local_medians = np.median(neighbor_vals, axis=1)

    keep = np.abs(vals - local_medians) <= threshold
    n_dropped = int((~keep).sum())
    if n_dropped:
        print(
            f"[surface_worker] outlier filter {product}: "
            f"dropped {n_dropped}/{len(vals)} stations"
        )
    return lons[keep], lats[keep], vals[keep]


def _lat_to_merc_y(lat_deg: np.ndarray) -> np.ndarray:
    lat_rad = np.radians(np.clip(lat_deg, -85.0, 85.0))
    return np.log(np.tan(np.pi / 4.0 + lat_rad / 2.0))


def _merc_y_to_lat(merc_y: np.ndarray) -> np.ndarray:
    return np.degrees(2.0 * np.arctan(np.exp(merc_y)) - np.pi / 2.0)


def _interpolate_surface_grid(
    lon: np.ndarray, lat: np.ndarray, values: np.ndarray, region: str = "CONUS"
) -> tuple[np.ndarray, list[float]] | tuple[None, None]:
    """IDW interpolation matching the JS _idwInterpolate / _interpolateGridValues
    algorithm.  CONUS uses a high-res grid with a nearly-flat IDW power for
    smooth pre-rendered overlays.  WORLD uses a globe-sized grid with a sharper
    IDW power matching the JS _gradientNeighborConfig() WORLD values.
    Grid latitudes are sampled in Mercator space to match Leaflet's projection.
    """
    if region.upper() == "WORLD":
        west, east, south, north = STATE_BOUNDS["WORLD"]
        width, height = _GRADIENT_WIDTH_WORLD, _GRADIENT_HEIGHT_WORLD
        # IDW parameters — must match JS _gradientNeighborConfig() WORLD values
        MAX_NEIGHBORS = 16
        MAX_INFLUENCE_KM = 1200
        IDW_POWER = 2.5
    else:
        west, east, south, north = STATE_BOUNDS["CONUS"]
        width, height = _GRADIENT_WIDTH, _GRADIENT_HEIGHT
        # IDW parameters — must match JS _gradientNeighborConfig() CONUS values
        MAX_NEIGHBORS = 14
        MAX_INFLUENCE_KM = 1200
        IDW_POWER = 0.1
    NEAR_STATION_KM = 0.0

    # Build grid longitudes (linear) and latitudes (Mercator-sampled).
    grid_lons = np.linspace(west, east, width, dtype=np.float64)
    north_merc = float(_lat_to_merc_y(np.asarray(north, dtype=np.float64)))
    south_merc = float(_lat_to_merc_y(np.asarray(south, dtype=np.float64)))
    merc_ys = np.linspace(north_merc, south_merc, height, dtype=np.float64)
    grid_lats = _merc_y_to_lat(merc_ys)  # shape (height,)

    # Project stations to approximate km space (cosLat scaling at mean lat).
    mean_lat = float(np.mean(lat))
    cos_lat = max(0.2, np.cos(np.radians(mean_lat)))
    sx = lon * cos_lat * 111.0
    sy = lat * 111.0
    tree = cKDTree(np.column_stack([sx, sy]))

    # Project all grid points to the same space.
    glon_grid, glat_grid = np.meshgrid(grid_lons, grid_lats)  # (H, W)
    gx = glon_grid * cos_lat * 111.0
    gy = glat_grid * 111.0
    query_pts = np.column_stack([gx.ravel(), gy.ravel()])  # (H*W, 2)

    k = min(MAX_NEIGHBORS, len(lon))
    dists, idxs = tree.query(query_pts, k=k)

    if k == 1:
        # Edge case: single station
        dists = dists[:, np.newaxis]
        idxs = idxs[:, np.newaxis]

    # Points within NEAR_STATION_KM: use that station's value directly.
    near_mask = dists[:, 0] <= NEAR_STATION_KM

    # IDW: weight = 1 / dist^power, zeroed beyond MAX_INFLUENCE_KM.
    within = dists <= MAX_INFLUENCE_KM
    safe_dists = np.where(dists > 0.0, dists, 1e-6)
    weights = np.where(within, 1.0 / (safe_dists**IDW_POWER), 0.0)

    vals_at_neighbors = values[idxs]  # (N_pts, k)
    sum_weights = weights.sum(axis=1)
    sum_wv = (weights * vals_at_neighbors).sum(axis=1)
    safe_denom = np.where(sum_weights > 0.0, sum_weights, 1.0)
    result = np.where(sum_weights > 0.0, sum_wv / safe_denom, np.nan)

    # Override with near-station exact value.
    result = np.where(near_mask, vals_at_neighbors[:, 0], result)

    # Fallback NaN → nearest neighbor value.
    nan_mask = ~np.isfinite(result)
    if nan_mask.any():
        result[nan_mask] = vals_at_neighbors[nan_mask, 0]

    grid = result.reshape(height, width).astype(np.float32)
    return grid, [west, east, south, north]


def _write_json_atomic(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", delete=False, encoding="utf-8", dir=os.path.dirname(path), suffix=".part"
    ) as fh:
        json.dump(payload, fh, separators=(",", ":"))
        tmp_path = fh.name
    os.replace(tmp_path, path)


def _write_gradient_cache(
    product: str,
    rgba: np.ndarray,
    bounds: list[float],
    timestamp_iso: str,
    station_count: int,
    unit: str,
    region: str = "CONUS",
) -> None:
    matplotlib.use("Agg")
    from matplotlib import image as mpl_image

    gradient_root = _gradient_root(region)
    os.makedirs(gradient_root, exist_ok=True)
    png_path = os.path.join(gradient_root, f"{product}.png")
    meta_path = os.path.join(gradient_root, f"{product}.json")

    with tempfile.NamedTemporaryFile(
        "wb", delete=False, dir=gradient_root, suffix=".png"
    ) as fh:
        tmp_png = fh.name
    mpl_image.imsave(tmp_png, rgba)
    os.replace(tmp_png, png_path)

    rel = os.path.relpath(png_path, _CACHE_ROOT).replace("\\", "/")
    meta = {
        "region": region.upper(),
        "product": product,
        "bounds": bounds,
        "image_url": f"/cache/{rel}",
        "timestamp": timestamp_iso,
        "station_count": station_count,
        "grid": {"width": _GRADIENT_WIDTH_WORLD if region.upper() == "WORLD" else _GRADIENT_WIDTH,
                 "height": _GRADIENT_HEIGHT_WORLD if region.upper() == "WORLD" else _GRADIENT_HEIGHT},
        "unit": unit,
    }
    _write_json_atomic(meta_path, meta)


def _build_surface_gradients(df, selected_products: set[str] | None = None, region: str = "CONUS") -> None:
    if df is None or df.empty:
        print(f"[surface_worker] gradient [{region}]: no source data")
        return

    _cleanup_stale_gradient_temp_files(region)

    df_work = df.copy()
    for col in ("longitude", "latitude"):
        if col not in df_work.columns:
            print(f"[surface_worker] gradient: missing column {col}")
            return
        df_work[col] = np.asarray(df_work[col], dtype=np.float64)

    valid_ts = datetime.now(timezone.utc)

    for product, cfg in _SURFACE_GRADIENT_PRODUCTS.items():
        if selected_products is not None and product not in selected_products:
            continue
        t0 = _time.perf_counter()
        try:
            col = cfg["col"]
            if col not in df_work.columns:
                print(
                    f"[surface_worker] gradient {product}: missing source column {col}"
                )
                continue

            vals = np.asarray(df_work[col], dtype=np.float64)
            lons = np.asarray(df_work["longitude"], dtype=np.float64)
            lats = np.asarray(df_work["latitude"], dtype=np.float64)

            mask = np.isfinite(vals) & np.isfinite(lons) & np.isfinite(lats)
            vals = vals[mask]
            lons = lons[mask]
            lats = lats[mask]

            if vals.size < 20:
                print(
                    f"[surface_worker] gradient {product}: too few points ({vals.size})"
                )
                continue

            mean_lat = float(np.mean(lats))
            cos_lat = max(0.2, np.cos(np.radians(mean_lat)))

            if vals.size < 20:
                print(
                    f"[surface_worker] gradient {product}: too few points after outlier filter ({vals.size})"
                )
                continue

            grid, bounds = _interpolate_surface_grid(
                lons, lats, vals, region=region)
            if grid is None or bounds is None:
                print(
                    f"[surface_worker] gradient {product}: interpolation failed")
                continue

            rgba = _build_rgba_from_values(grid, cfg["anchors"])

            # Clip gradients to land boundaries so overlays do not bleed into
            # oceans. Keep masking in Mercator Y to match grid sampling.
            region_upper = region.upper()
            mask_geom = None
            mask_label = region_upper
            if region_upper == "CONUS":
                mask_geom = _build_conus_geometry()
                mask_label = "CONUS"
            elif region_upper == "WORLD":
                mask_geom = _build_world_land_geometry()
                mask_label = "WORLD land"

            if mask_geom is not None:
                try:
                    west_b, east_b, south_b, north_b = bounds
                    north_merc = float(
                        _lat_to_merc_y(np.asarray(north_b, dtype=np.float64))
                    )
                    south_merc = float(
                        _lat_to_merc_y(np.asarray(south_b, dtype=np.float64))
                    )

                    def _lonlat_to_lon_mercy(x, y, z=None):
                        merc_y = _lat_to_merc_y(
                            np.asarray(y, dtype=np.float64))
                        if z is None:
                            return x, merc_y
                        return x, merc_y, z

                    mask_geom_merc = _shapely_transform(
                        _lonlat_to_lon_mercy, mask_geom
                    )
                    transform = _from_bounds(
                        west_b,
                        south_merc,
                        east_b,
                        north_merc,
                        grid.shape[1],
                        grid.shape[0],
                    )
                    land_mask = _rasterize(
                        [(mask_geom_merc, 1)],
                        out_shape=grid.shape,
                        transform=transform,
                        fill=0,
                        dtype=np.uint8,
                    )
                    rgba[:, :, 3] = np.where(land_mask == 1, 255, 0)
                except Exception as _mask_err:
                    print(
                        f"[surface_worker] gradient {product}: "
                        f"{mask_label} mask failed (continuing without clip): {_mask_err}"
                    )

            _write_gradient_cache(
                product=product,
                rgba=rgba,
                bounds=bounds,
                timestamp_iso=valid_ts.isoformat(),
                station_count=int(vals.size),
                unit=str(cfg["unit"]),
                region=region,
            )
            elapsed = _time.perf_counter() - t0
            print(
                f"[surface_worker] gradient [{region}] {product}: {int(vals.size)} points in {elapsed:.1f}s"
            )
        except Exception as exc:
            print(f"[surface_worker] gradient {product} error: {exc}")


def run_surface_worker(force: bool = False, products: list[str] | None = None) -> None:
    """Fetch METAR data and pre-render CONUS and WORLD gradient caches."""
    if not force and is_cache_fresh("surface", _FRESH_WINDOW_SEC):
        print("[surface_worker] Cache fresh — skipping run")
        return

    try:
        selected_products = _normalize_product_selection(products)
    except ValueError as exc:
        print(f"[surface_worker] {exc}")
        return

    if selected_products:
        print(
            f"[surface_worker] gradient filter active: {sorted(selected_products)}")

    try:
        from surface import surface_utils
    except Exception as exc:
        print(f"[surface_worker] Import error: {exc}")
        return

    region_dfs: dict[str, object] = {}
    for region in _PRELOAD_REGIONS:
        t0 = _time.perf_counter()
        try:
            df = surface_utils.fetch_metar_data(region)
            elapsed = _time.perf_counter() - t0
            rows = len(df) if df is not None and not df.empty else 0
            print(
                f"[surface_worker] {region}: {rows} stations in {elapsed:.1f}s")
            if df is not None and not df.empty:
                region_dfs[region] = df
        except Exception as exc:
            print(f"[surface_worker] {region} error: {exc}")

    for reg in ("CONUS", "WORLD"):
        df = region_dfs.get(reg)
        if df is not None and not df.empty:
            _build_surface_gradients(
                df, selected_products=selected_products, region=reg)
        else:
            print(f"[surface_worker] gradient [{reg}]: skipped (no dataframe)")

    mark_run_complete("surface")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the surface worker once.")
    parser.add_argument("--force", action="store_true",
                        help="Bypass freshness gate.")
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to logs/scheduled/surface.log (for headless task runs).",
    )
    parser.add_argument(
        "--product",
        action="append",
        choices=sorted(_SURFACE_GRADIENT_PRODUCTS.keys()),
        help=(
            "Render only selected gradient product(s). "
            "Repeat flag to include multiple products."
        ),
    )
    args = parser.parse_args()
    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("surface")
    run_surface_worker(force=args.force, products=args.product)
