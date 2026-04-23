"""Background worker: pre-fetches surface METAR observations so the first
client request hits warm cache instead of blocking on a live IEM fetch.

Refreshes the CONUS and WORLD raw CSV caches (15-min TTL in surface_utils)
so that ``/api/data/surface`` calls complete almost instantly.
"""

import time as _time

from workers._freshness import is_cache_fresh, mark_run_complete

# Regions to keep warm.  CONUS is the gradient source for all US states;
# WORLD is the gradient source when the user is at the WORLD view.
_PRELOAD_REGIONS: list[str] = ["CONUS", "WORLD"]

# Skip if a successful refresh happened within the last 22 min (75% of 30 min interval)
_FRESH_WINDOW_SEC = 22 * 60


def run_surface_worker(force: bool = False) -> None:
    """Fetch METAR data for each preload region, populating the CSV cache."""
    if not force and is_cache_fresh("surface", _FRESH_WINDOW_SEC):
        print("[surface_worker] Cache fresh — skipping run")
        return
    try:
        from surface import surface_utils
    except Exception as exc:
        print(f"[surface_worker] Import error: {exc}")
        return

    for region in _PRELOAD_REGIONS:
        t0 = _time.perf_counter()
        try:
            df = surface_utils.fetch_metar_data(region)
            elapsed = _time.perf_counter() - t0
            rows = len(df) if df is not None and not df.empty else 0
            print(
                f"[surface_worker] {region}: {rows} stations in {elapsed:.1f}s")
        except Exception as exc:
            print(f"[surface_worker] {region} error: {exc}")
    mark_run_complete("surface")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the surface worker once.")
    parser.add_argument("--force", action="store_true",
                        help="Bypass freshness gate.")
    args = parser.parse_args()
    run_surface_worker(force=args.force)
