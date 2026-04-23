"""One-time preseed tool for the NWS zone-geometry disk cache.

Fetches every public, forecast, and fire-weather zone from api.weather.gov,
caches its geometry, and writes the result to
``cache/alerts/zone_geometry_cache.json`` so the first alerts_worker run after
a clean restart hits the warm disk cache instead of paying the ~60 s cold-start
penalty for re-fetching ~1000+ zones referenced by active alerts.

Run once after install / when zone boundaries change (NWS publishes updates
roughly once or twice a year):

    python tools/preseed_zone_cache.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

# Make sibling packages importable when running from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from alerts.alerts_utils import (  # noqa: E402  (import after sys.path edit)
    _ZONE_GEOM_MAX_WORKERS,
    _fetch_single_zone_geometry,
    _save_zone_disk_cache,
)

NWS_ZONE_LIST_URL = "https://api.weather.gov/zones"
ZONE_TYPES = ("public", "forecast", "fire")
HEADERS = {
    "User-Agent": "(NCHurricane.com Weather Suite, contact@nchurricane.com)"}


def list_zone_urls(zone_type: str) -> list[str]:
    """Return the full list of zone detail URLs for a given zone type."""
    params = {"type": zone_type}
    resp = requests.get(NWS_ZONE_LIST_URL, params=params,
                        headers=HEADERS, timeout=30)
    resp.raise_for_status()
    features = resp.json().get("features", [])
    urls: list[str] = []
    for feat in features:
        props = feat.get("properties") or {}
        url = props.get("@id") or feat.get("id")
        if url:
            urls.append(url)
    return urls


def main() -> int:
    import concurrent.futures

    overall_start = time.time()
    all_urls: list[str] = []

    for ztype in ZONE_TYPES:
        t0 = time.time()
        try:
            urls = list_zone_urls(ztype)
        except Exception as exc:
            print(f"[preseed] Failed to list {ztype} zones: {exc}")
            continue
        print(
            f"[preseed] {ztype:>8} zones listed: {len(urls):4d} in {time.time() - t0:.1f}s")
        all_urls.extend(urls)

    # Dedupe in case the lists overlap.
    all_urls = sorted(set(all_urls))
    print(
        f"[preseed] Fetching geometries for {len(all_urls)} unique zone(s)...")

    fetch_start = time.time()
    workers = min(_ZONE_GEOM_MAX_WORKERS, max(1, len(all_urls)))
    fetched = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for _zid, geom in pool.map(_fetch_single_zone_geometry, all_urls):
            if geom is not None:
                fetched += 1

    _save_zone_disk_cache()
    print(
        f"[preseed] Done — {fetched}/{len(all_urls)} geometries cached "
        f"in {time.time() - fetch_start:.1f}s "
        f"(total wall time {time.time() - overall_start:.1f}s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
