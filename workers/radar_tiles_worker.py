"""Background worker for IEM radar backdrop tile prefetch."""

from __future__ import annotations

import math
import time
import urllib.request
from pathlib import Path

from config.radar_config import LIVE_RADAR_TILE_WORKER_INTERVAL_MIN
from workers._freshness import is_cache_fresh, mark_run_complete

_CACHE_ROOT = Path(__file__).resolve().parent.parent / "cache"
_TILE_SOURCE_URL = (
    "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913"
)
_TILE_CACHE_DIR = _CACHE_ROOT / "radar" / "tiles"
_TILE_ZOOM_MIN = 3
_TILE_ZOOM_MAX = 6
_TILE_MAX_AGE_SEC = 4 * 60
_TILE_FETCH_DELAY = 0.05
_TILE_FETCH_TIMEOUT = 10
_TILE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; WxDashboard/1.0)",
}

_FRESH_WINDOW_SEC = max(60, int(LIVE_RADAR_TILE_WORKER_INTERVAL_MIN * 60 * 0.75))

_CONUS_WEST, _CONUS_EAST = -128.0, -63.0
_CONUS_SOUTH, _CONUS_NORTH = 22.0, 52.0


def _lon_to_tile_x(lon: float, z: int) -> int:
    return int((lon + 180.0) / 360.0 * (1 << z))


def _lat_to_tile_y(lat: float, z: int) -> int:
    lat_r = math.radians(lat)
    return int(
        (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi)
        / 2.0
        * (1 << z)
    )


def _conus_tile_ranges(z: int) -> tuple[int, int, int, int]:
    n = 1 << z
    x_min = max(0, _lon_to_tile_x(_CONUS_WEST, z))
    x_max = min(n - 1, _lon_to_tile_x(_CONUS_EAST, z))
    y_min = max(0, _lat_to_tile_y(_CONUS_NORTH, z))
    y_max = min(n - 1, _lat_to_tile_y(_CONUS_SOUTH, z))
    return x_min, x_max, y_min, y_max


def prefetch_backdrop_tiles() -> int:
    now = time.time()
    fetched = 0
    for z in range(_TILE_ZOOM_MIN, _TILE_ZOOM_MAX + 1):
        x_min, x_max, y_min, y_max = _conus_tile_ranges(z)
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                tile_path = _TILE_CACHE_DIR / str(z) / str(x) / f"{y}.png"
                if (
                    tile_path.exists()
                    and tile_path.stat().st_size > 0
                    and (now - tile_path.stat().st_mtime) < _TILE_MAX_AGE_SEC
                ):
                    continue
                tile_path.parent.mkdir(parents=True, exist_ok=True)
                url = f"{_TILE_SOURCE_URL}/{z}/{x}/{y}"
                try:
                    req = urllib.request.Request(url, headers=_TILE_HEADERS)
                    with urllib.request.urlopen(
                        req, timeout=_TILE_FETCH_TIMEOUT
                    ) as resp:
                        data = resp.read()
                    tmp_path = tile_path.with_suffix(".tmp")
                    tmp_path.write_bytes(data)
                    tmp_path.replace(tile_path)
                    fetched += 1
                    if _TILE_FETCH_DELAY:
                        time.sleep(_TILE_FETCH_DELAY)
                except Exception as exc:
                    print(f"[radar_tiles_worker] tile {z}/{x}/{y} fetch error: {exc}")
    return fetched


def run_radar_tiles_worker(force: bool = False) -> None:
    if not force and is_cache_fresh("radar_tiles", _FRESH_WINDOW_SEC):
        print("[radar_tiles_worker] Cache fresh - skipping run")
        return

    fetched = prefetch_backdrop_tiles()
    print(f"[radar_tiles_worker] completed - fetched tiles: {fetched}")
    mark_run_complete("radar_tiles")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the radar tile worker once.")
    parser.add_argument("--force", action="store_true", help="Bypass freshness gate.")
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to logs/scheduled/radar_tiles.log",
    )
    args = parser.parse_args()

    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("radar_tiles")

    run_radar_tiles_worker(force=args.force)
