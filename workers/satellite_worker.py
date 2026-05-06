"""Background worker for Satellite prewarming.

Prepares live frame indexes and a small tile set so Satellite Current/Animate
loads quickly from cache.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from config.satellite_config import (
    SATELLITE_PREWARM_NEWEST_FRAMES,
    SATELLITE_PREWARM_CURRENT,
    SATELLITE_PREWARM_MESO,
    SATELLITE_PREWARM_TILE_RADIUS_BY_ZOOM,
    SATELLITE_PREWARM_ZOOMS,
)
from satellite import satellite_tile_utils
from workers._freshness import is_cache_fresh, mark_run_complete

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
    radius_by_zoom = dict(SATELLITE_PREWARM_TILE_RADIUS_BY_ZOOM)
    radius_by_zoom.update(dict(config.get("tile_radius_by_zoom", {})))

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
            center = _SECTOR_CENTER.get(str(sector).upper(), _SECTOR_CENTER["CONUS"])

            frames_to_warm = (
                frames[-newest_limit:]
                if newest_limit > 0 and len(frames) > newest_limit
                else frames
            )

            for frame in frames_to_warm:
                frame_key = str(frame.get("frame_key") or "").strip()
                if not frame_key:
                    continue
                for z in SATELLITE_PREWARM_ZOOMS:
                    zz = int(z)
                    center_x, center_y = _tile_xy(center[0], center[1], zz)
                    radius = int(radius_by_zoom.get(zz, 0))
                    for x, y in _tile_grid(center_x, center_y, zz, radius):
                        try:
                            tile_path = satellite_tile_utils.ensure_tile_cached(
                                cache_root=_CACHE_ROOT,
                                sat_id=sat_id,
                                sector=sector,
                                channel_key=product,
                                source=provider,
                                frame_key=frame_key,
                                z=zz,
                                x=x,
                                y=y,
                            )
                            if tile_path:
                                warmed_tiles += 1
                        except Exception:
                            continue

            print(
                f"[{worker_name}] warmed {sat_id}/{sector}/{product}: "
                f"{len(frames_to_warm)}/{len(frames)} frames, provider={provider}"
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
    parser.add_argument("--force", action="store_true", help="Bypass freshness gate.")
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
