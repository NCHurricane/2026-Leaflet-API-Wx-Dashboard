"""Background worker for Satellite prewarming.

Prepares live frame indexes and a small tile set so Satellite Current/Animate
loads quickly from cache.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from config.satellite_config import (
    SATELLITE_PREWARM_NEWEST_FRAMES,
    SATELLITE_PREWARM_CURRENT,
    SATELLITE_PREWARM_MESO,
    SATELLITE_PREWARM_TILE_RADIUS_BY_ZOOM,
    SATELLITE_PREWARM_ZOOMS,
    SATELLITE_PREWARM_ZOOMS_MESO,
)
from satellite import satellite_tile_utils
from workers._freshness import is_cache_fresh, mark_run_complete

import math as _math

_BASE_DIR = Path(__file__).resolve().parent.parent
_CACHE_ROOT = str(_BASE_DIR / "cache")

_SECTOR_CENTER = {
    "CONUS": (37.5, -96.0),
    "FULLDISK": (0.0, -75.0),
    "MESO1": (40.0, -95.0),
    "MESO2": (30.0, -80.0),
}


def _tile_xy(lat: float, lon: float, z: int) -> tuple[int, int]:
    import math

    lat = max(min(float(lat), 85.0511), -85.0511)
    lon = float(lon)
    scale = 2 ** int(z)
    x = int((lon + 180.0) / 360.0 * scale)
    lat_rad = math.radians(lat)
    y = int(
        (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi)
        / 2.0
        * scale
    )
    return max(0, min(scale - 1, x)), max(0, min(scale - 1, y))


def _tile_grid(
    center_x: int,
    center_y: int,
    z: int,
    radius: int,
) -> list[tuple[int, int]]:
    scale = 2 ** int(z)
    rad = max(0, int(radius))
    coords: list[tuple[int, int]] = []
    seen = set()
    for dx in range(-rad, rad + 1):
        for dy in range(-rad, rad + 1):
            x = max(0, min(scale - 1, center_x + dx))
            y = max(0, min(scale - 1, center_y + dy))
            key = (x, y)
            if key in seen:
                continue
            seen.add(key)
            coords.append(key)
    return coords


_CONUS_BOUNDS = {
    "lon_min": -140.0,
    "lon_max": -65.0,
    "lat_min": 21.0,
    "lat_max": 52.0,
}


def _conus_tile_range(z: int) -> list[tuple[int, int]]:
    """Return every (x, y) tile covering the CONUS bounding box at zoom z."""
    scale = 2 ** int(z)
    b = _CONUS_BOUNDS

    def _lon_to_x(lon: float) -> int:
        return int((lon + 180.0) / 360.0 * scale)

    def _lat_to_y(lat: float) -> int:
        lat = max(min(lat, 85.0511), -85.0511)
        lat_rad = _math.radians(lat)
        return int(
            (1.0 - _math.log(_math.tan(lat_rad) + 1.0 / _math.cos(lat_rad)) / _math.pi)
            / 2.0 * scale
        )

    x_min = max(0, _lon_to_x(b["lon_min"]))
    x_max = min(scale - 1, _lon_to_x(b["lon_max"]))
    # lat_to_y is inverted — higher lat = smaller y
    y_min = max(0, _lat_to_y(b["lat_max"]))
    y_max = min(scale - 1, _lat_to_y(b["lat_min"]))

    return [
        (x, y)
        for x in range(x_min, x_max + 1)
        for y in range(y_min, y_max + 1)
    ]


def _sector_tile_range(sector: str, z: int) -> list[tuple[int, int]]:
    """Return tile coords appropriate for the given sector at zoom z."""
    sector_upper = sector.upper()
    scale = 2 ** int(z)
    if sector_upper in ("MESO1", "MESO2"):
        center = _SECTOR_CENTER.get(sector_upper, _SECTOR_CENTER["CONUS"])
        cx, cy = _tile_xy(center[0], center[1], z)
        radius = 2  # 5×5 grid
        return [
            (max(0, min(scale - 1, cx + dx)), max(0, min(scale - 1, cy + dy)))
            for dx in range(-radius, radius + 1)
            for dy in range(-radius, radius + 1)
        ]
    elif sector_upper == "CONUS":
        return _conus_tile_range(z)
    else:
        # FULLDISK or unknown — fall back to 3×3 around center
        center = _SECTOR_CENTER.get(sector_upper, _SECTOR_CENTER["CONUS"])
        cx, cy = _tile_xy(center[0], center[1], z)
        return [
            (max(0, min(scale - 1, cx + dx)), max(0, min(scale - 1, cy + dy)))
            for dx in range(-1, 2)
            for dy in range(-1, 2)
        ]


def _warm_tile_task(
    cache_root: str,
    sat_id: str,
    sector: str,
    product: str,
    provider: str,
    frame_key: str,
    z: int,
    x: int,
    y: int,
) -> bool:
    """Single tile warm job — runs inside ThreadPoolExecutor workers."""
    try:
        path = satellite_tile_utils.ensure_tile_cached(
            cache_root=cache_root,
            sat_id=sat_id,
            sector=sector,
            channel_key=product,
            source=provider,
            frame_key=frame_key,
            z=z,
            x=x,
            y=y,
        )
        return bool(path)
    except Exception:
        return False


def _prewarm_group(config: dict, worker_name: str, force: bool = False) -> None:
    cadence = int(config.get("cadence_minutes", 15))
    fresh_window_sec = max(60, int(cadence * 60 * 0.75))
    if not force and is_cache_fresh(worker_name, fresh_window_sec):
        print(f"[{worker_name}] Cache fresh - skipping run")
        return

    sat_id = str(config.get("sat_id", "goes19"))
    sectors = [str(s) for s in config.get("sectors", ())]
    products = [str(p) for p in config.get("products", ())]
    lookback_hours = int(config.get("lookback_hours", 1))
    max_frames = int(config.get("max_frames", 60))
    newest_limit = int(
        config.get("prewarm_newest_frames", SATELLITE_PREWARM_NEWEST_FRAMES)
    )

    total_frames = 0
    warmed_tiles = 0

    for sector in sectors:
        for product in products:
            try:
                payload = satellite_tile_utils.build_live_frames(
                    cache_root=_CACHE_ROOT,
                    base_dir=str(_BASE_DIR),
                    sat_id=sat_id,
                    sector=sector,
                    channel_key=product,
                    hours=lookback_hours,
                    source="auto",
                    max_frames=max_frames,
                )
            except Exception as exc:
                print(
                    f"[{worker_name}] {sat_id}/{sector}/{product} frame index error: {exc}"
                )
                continue

            frames = payload.get("frames") or []
            total_frames += len(frames)
            provider = str(payload.get("provider") or "aws")

            frames_to_warm = (
                frames[-newest_limit:]
                if newest_limit > 0 and len(frames) > newest_limit
                else frames
            )

            is_meso = str(sector).upper() in ("MESO1", "MESO2")
            zooms = SATELLITE_PREWARM_ZOOMS_MESO if is_meso else SATELLITE_PREWARM_ZOOMS

            # Build a flat task list: every frame × every zoom × every tile in sector
            tasks: list[tuple[str, str, str, str, str, int, int, int]] = []
            for frame in frames_to_warm:
                frame_key = str(frame.get("frame_key") or "").strip()
                if not frame_key:
                    continue
                for z in zooms:
                    for x, y in _sector_tile_range(sector, int(z)):
                        tasks.append((
                            _CACHE_ROOT, sat_id, sector, product,
                            provider, frame_key, int(z), x, y,
                        ))

            if not tasks:
                print(
                    f"[{worker_name}] {sat_id}/{sector}/{product}: no tasks built")
                continue

            print(
                f"[{worker_name}] {sat_id}/{sector}/{product}: "
                f"{len(frames_to_warm)}/{len(frames)} frames, "
                f"{len(tasks)} tiles queued, provider={provider}"
            )

            group_warmed = 0
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = {
                    pool.submit(_warm_tile_task, *task): task
                    for task in tasks
                }
                for fut in as_completed(futures):
                    try:
                        if fut.result():
                            group_warmed += 1
                    except Exception:
                        pass
            warmed_tiles += group_warmed

            print(
                f"[{worker_name}] warmed {sat_id}/{sector}/{product}: "
                f"{len(frames_to_warm)}/{len(frames)} frames, "
                f"{group_warmed}/{len(tasks)} tiles, provider={provider}"
            )

    mark_run_complete(worker_name)
    print(f"[{worker_name}] complete: frames={total_frames}, tiles={warmed_tiles}")


def run_satellite_current_worker(force: bool = False) -> None:
    _prewarm_group(SATELLITE_PREWARM_CURRENT, "satellite_current", force=force)


def run_satellite_meso_worker(force: bool = False) -> None:
    _prewarm_group(SATELLITE_PREWARM_MESO, "satellite_meso", force=force)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Satellite prewarm worker once."
    )
    parser.add_argument("--force", action="store_true",
                        help="Bypass freshness gate.")
    parser.add_argument(
        "--mode",
        choices=["current", "meso"],
        default="current",
        help="Prewarm profile to run.",
    )
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to logs/scheduled/<worker>.log.",
    )
    args = parser.parse_args()

    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log(
            "satellite_meso" if args.mode == "meso" else "satellite_current"
        )

    if args.mode == "meso":
        run_satellite_meso_worker(force=args.force)
    else:
        run_satellite_current_worker(force=args.force)


if __name__ == "__main__":
    main()
