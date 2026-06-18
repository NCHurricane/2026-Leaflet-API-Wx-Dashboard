"""Background worker: periodically cleans up cache directories to prevent disk space issues.

Removes cache files older than configured retention periods:
- Satellite: 48 hours
- RTMA: 36 hours
- Radar: 24 hours
- Orphaned temp files: always (*.tmp, *.dzz_*, etc.)

Scheduled to run every 6 hours to keep the cache at a manageable size.
"""

from __future__ import annotations

import os
import sys
import time as _time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path for both module and direct execution
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from workers._freshness import is_cache_fresh, mark_run_complete

# Only run cleanup if cache hasn't been cleaned in the last 5.5 hours
# (so a 6-hour interval doesn't trigger cleanup constantly)
_FRESH_WINDOW_SEC = 5.5 * 60 * 60

_CACHE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache"
)

# Retention policies: (directory, max_age_hours)
_RETENTION_POLICIES = [
    ("satellite", 48),  # Keep 2 days of satellite imagery
    ("rtma", 36),       # Keep 1.5 days of RTMA data
    ("radar", 24),      # Keep 1 day of radar data
    ("mrms", 24),       # Keep 1 day of MRMS data
    ("overlays", 48),   # Keep 2 days of rendered overlays
    ("spc", 7 * 24),    # Keep 7 days of SPC data
    ("tropical", 7 * 24),  # Keep 7 days of tropical data
    ("surface", 7 * 24),   # Keep 7 days of surface gradients
    ("drought", 7 * 24),   # Keep 7 days of drought data
]

# Temp file patterns to always remove
_TEMP_PATTERNS = ["*.tmp", "*.dzz_*", "*.lock"]


def _remove_old_files(directory: str, max_age_hours: int) -> int:
    """Remove files older than max_age_hours from directory.

    Returns: count of files removed
    """
    if not os.path.isdir(directory):
        return 0

    removed_count = 0
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    cutoff_timestamp = cutoff_time.timestamp()

    try:
        for root, dirs, files in os.walk(directory):
            for filename in files:
                filepath = os.path.join(root, filename)
                try:
                    mtime = os.path.getmtime(filepath)
                    if mtime < cutoff_timestamp:
                        os.remove(filepath)
                        removed_count += 1
                except (OSError, FileNotFoundError):
                    # File may have been deleted by another process
                    pass

            # Remove empty directories
            for dirname in dirs:
                dirpath = os.path.join(root, dirname)
                try:
                    if not os.listdir(dirpath):  # Empty directory
                        os.rmdir(dirpath)
                except (OSError, FileNotFoundError):
                    pass
    except Exception as exc:
        print(f"[cache_cleanup] Error in {directory}: {exc}")

    return removed_count


def _remove_temp_files(directory: str, patterns: list[str]) -> int:
    """Remove temp files matching patterns.

    Returns: count of files removed
    """
    if not os.path.isdir(directory):
        return 0

    removed_count = 0
    # Only remove temp/lock files that are clearly orphaned. Live worker
    # overlap locks (cache/.workers/*.lock, held up to ~2h by rolling
    # profiles) and in-flight *.tmp writes must not be deleted.
    cutoff_timestamp = _time.time() - 24 * 3600

    try:
        for root, dirs, files in os.walk(directory):
            for filename in files:
                for pattern in patterns:
                    # Simple pattern matching (not full glob)
                    if pattern.replace("*", "") in filename:
                        filepath = os.path.join(root, filename)
                        try:
                            if os.path.getmtime(filepath) < cutoff_timestamp:
                                os.remove(filepath)
                                removed_count += 1
                        except (OSError, FileNotFoundError):
                            pass
    except Exception as exc:
        print(f"[cache_cleanup] Error removing temps in {directory}: {exc}")

    return removed_count


def run_cache_cleanup_worker(force: bool = False) -> None:
    """Clean up old cache files to prevent disk space exhaustion."""

    if not force and is_cache_fresh("cache_cleanup", _FRESH_WINDOW_SEC):
        print("[cache_cleanup] Cache fresh — skipping cleanup")
        return

    print("[cache_cleanup] Starting cleanup...")
    t0 = _time.perf_counter()

    total_removed = 0

    # Apply retention policies
    for cache_subdir, max_age_hours in _RETENTION_POLICIES:
        cache_path = os.path.join(_CACHE_ROOT, cache_subdir)
        if os.path.isdir(cache_path):
            removed = _remove_old_files(cache_path, max_age_hours)
            if removed > 0:
                print(f"  {cache_subdir}: removed {removed} old files (>{max_age_hours}h)")
                total_removed += removed

    # Remove all temp files across entire cache
    temp_removed = _remove_temp_files(_CACHE_ROOT, _TEMP_PATTERNS)
    if temp_removed > 0:
        print(f"  temp files: removed {temp_removed} orphaned files")
        total_removed += temp_removed

    elapsed = _time.perf_counter() - t0
    print(f"[cache_cleanup] Complete: removed {total_removed} files in {elapsed:.1f}s")

    mark_run_complete("cache_cleanup")


def main() -> None:
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Clean up old cache files to prevent disk exhaustion."
    )
    parser.add_argument(
        "--force", "-f", action="store_true", help="Force cleanup even if cache is fresh"
    )
    args = parser.parse_args()
    run_cache_cleanup_worker(force=args.force)


if __name__ == "__main__":
    main()
