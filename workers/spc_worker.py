"""Background worker: fetches SPC outlook GeoJSON and writes to cache/spc/."""

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path for both module and direct execution
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app_core.atomic_io import atomic_write_json  # noqa: E402
from workers._freshness import is_cache_fresh, mark_run_complete  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "spc"

# Skip if a successful refresh happened within the last 22 min (75% of 30 min interval)
_FRESH_WINDOW_SEC = 22 * 60

# Convective hazards to pre-cache per outlook day
_CONVECTIVE_HAZARDS: dict[int, list[str]] = {
    1: ["cat", "torn", "wind", "hail", "cigtorn", "cigwind", "cighail"],
    2: ["cat", "torn", "wind", "hail", "cigtorn", "cigwind", "cighail"],
    3: ["cat", "prob"],
    **{d: ["cat"] for d in range(4, 9)},
}

# Fire weather hazards: Days 1-2 use dryt/windrh, Days 3-8 use categorical/probabilistic
_FIRE_WX_HAZARDS_12 = ["windrh", "dryt"]
_FIRE_WX_HAZARDS_38 = ["drytcat", "drytprob", "windrhcat", "windrhprob"]


def _source_issue_iso(payload: dict) -> str | None:
    for feature in payload.get("features") or []:
        properties = feature.get("properties") or {}
        for field in ("ISSUE_ISO", "issue_iso", "issued", "issue"):
            value = properties.get(field)
            if value:
                return str(value)
    return None


def _write_cache(name: str, payload: dict, source: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not isinstance(payload, dict):
        payload = {}
    out = {
        "_source": source,
        "_updated": datetime.now(timezone.utc).isoformat(),
        "_issued": _source_issue_iso(payload),
        **payload,
    }
    path = CACHE_DIR / f"{name}.geojson"
    atomic_write_json(path, out)


def run_spc_worker(
    force: bool = False,
    product_ids: set[str] | None = None,
) -> dict:
    """Fetch selected SPC outlooks, or the legacy complete matrix."""
    if not force and not product_ids and is_cache_fresh("spc", _FRESH_WINDOW_SEC):
        print("[spc_worker] Cache fresh — skipping run")
        return {"status": "current", "products": []}
    from concurrent.futures import ThreadPoolExecutor
    from spc.spc_utils import (
        fetch_outlook_geojson,
        fetch_fire_wx_geojson,
    )

    start = time.time()

    # Build list of all fetch tasks (cache_name, fetch_func, day, hazard)
    tasks = []

    # Convective outlooks
    for day, hazards in _CONVECTIVE_HAZARDS.items():
        for hazard in hazards:
            tasks.append((f"{day}_{hazard}", fetch_outlook_geojson, day, hazard))

    # Fire weather Days 1-2
    for day in range(1, 3):
        for hazard in _FIRE_WX_HAZARDS_12:
            tasks.append((f"fire_{day}_{hazard}", fetch_fire_wx_geojson, day, hazard))

    # Fire weather Days 3-8
    for day in range(3, 9):
        for hazard in _FIRE_WX_HAZARDS_38:
            tasks.append((f"fire_{day}_{hazard}", fetch_fire_wx_geojson, day, hazard))
    if product_ids:
        requested = {str(product_id).strip().lower() for product_id in product_ids}
        tasks = [task for task in tasks if task[0] in requested]
        unknown = requested - {task[0] for task in tasks}
        if unknown:
            raise ValueError(f"Unknown SPC product id(s): {', '.join(sorted(unknown))}")

    def _fetch_and_cache(task):
        """Fetch one outlook and write to cache. Returns (cache_name, success, error_msg)."""
        cache_name, fetch_func, day, hazard = task
        try:
            payload, source = fetch_func(day, hazard)
            _write_cache(cache_name, payload, source)
            return cache_name, True, None
        except Exception as exc:
            return cache_name, False, str(exc)

    # Parallelize fetches across available cores (6 workers for network I/O)
    errors = 0
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(_fetch_and_cache, tasks))

    # Collect errors for reporting
    for cache_name, success, error_msg in results:
        if not success:
            errors += 1
            print(f"[spc_worker] {cache_name}: {error_msg}")

    print(
        f"[spc_worker] SPC cache refresh complete in {time.time() - start:.2f}s "
        f"({errors} error(s))"
    )
    if errors == len(tasks):
        print("[spc_worker] All fetches failed — cache not marked fresh")
    elif not product_ids:
        mark_run_complete("spc")
    else:
        print("[spc_worker] Targeted refresh complete — global freshness unchanged")
    if errors:
        raise RuntimeError(f"{errors} of {len(tasks)} SPC product refreshes failed")
    return {
        "status": "warmed",
        "products": [task[0] for task in tasks],
        "source_timestamp": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the SPC worker once.")
    parser.add_argument("--force", action="store_true",
                        help="Bypass freshness gate.")
    parser.add_argument("--log-to-file", action="store_true",
                        help="Redirect stdout/stderr to cache/logs/scheduled/spc.log (for headless task runs).")
    args = parser.parse_args()
    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log
        redirect_stdio_to_log("spc")
    run_spc_worker(force=args.force)
