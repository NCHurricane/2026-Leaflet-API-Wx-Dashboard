"""Background worker: fetches national NWS alerts, enriches geometries, and writes dual-cache artifacts.

Produces:
  - cache/alerts/national_full.geojson (canonical full geometry, used for all interactions)
  - cache/alerts/national_display_low.geojson (simplified variant for low-zoom rendering)
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "alerts"
CACHE_FILE_FULL = CACHE_DIR / "national_full.geojson"
CACHE_FILE_DISPLAY_LOW = CACHE_DIR / "national_display_low.geojson"

# Legacy cache path for backward compatibility (symlink or copy of full)
CACHE_FILE = CACHE_DIR / "national.geojson"


def run_alerts_worker() -> None:
    """Fetch all active US alerts, enrich geometries, and write dual cache artifacts.

    Produces:
      - national_full.geojson: canonical full geometry (no simplification)
      - national_display_low.geojson: simplified variant for low-zoom rendering
      - national.geojson: legacy backward-compatible symlink to full
    """
    worker_start = time.time()
    try:
        from alerts.alerts_utils import (
            fetch_active_alerts_with_source,
            _create_display_low_features,
        )
        from main import _enrich_alert_features_geometry

        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Fetch and enrich full features.
        fetch_start = time.time()
        features, source = fetch_active_alerts_with_source(state=None, source="nws")
        enrich_start = time.time()

        _enrich_alert_features_geometry(features)
        enrich_elapsed = time.time() - enrich_start

        # Write full geometry cache (canonical).
        full_payload = {
            "type": "FeatureCollection",
            "_source": source,
            "_updated": datetime.now(timezone.utc).isoformat(),
            "_geometry_mode": "full",
            "features": features,
        }
        CACHE_FILE_FULL.write_text(json.dumps(full_payload), encoding="utf-8")

        # Create and write simplified display-low variant.
        simplify_start = time.time()
        display_features, simplify_metrics = _create_display_low_features(features)
        simplify_elapsed = time.time() - simplify_start

        display_payload = {
            "type": "FeatureCollection",
            "_source": source,
            "_updated": datetime.now(timezone.utc).isoformat(),
            "_geometry_mode": "display",
            "_simplification_metrics": simplify_metrics,
            "features": display_features,
        }
        CACHE_FILE_DISPLAY_LOW.write_text(json.dumps(display_payload), encoding="utf-8")

        # Write legacy backward-compatible cache (full geometry).
        CACHE_FILE.write_text(json.dumps(full_payload), encoding="utf-8")

        # Emit worker metrics.
        total_elapsed = time.time() - worker_start
        print(
            f"[alerts_worker] Complete in {total_elapsed:.2f}s\n"
            f"  Fetch: {(enrich_start - fetch_start):.2f}s | "
            f"Enrich: {enrich_elapsed:.2f}s | "
            f"Simplify: {simplify_elapsed:.2f}s\n"
            f"  Features: {len(features)} total\n"
            f"  Simplification: {simplify_metrics['simplified_features']} simplified, "
            f"{simplify_metrics['excluded_features']} excluded (preserved full)\n"
            f"  Vertex reduction: {simplify_metrics['vertex_reduction_percent']:.1f}% | "
            f"Before: {simplify_metrics['total_vertices_before']}, "
            f"After: {simplify_metrics['total_vertices_after']}\n"
            f"  Caches: {CACHE_FILE_FULL.name}, {CACHE_FILE_DISPLAY_LOW.name}, "
            f"{CACHE_FILE.name} (legacy)"
        )
    except Exception as exc:
        print(f"[alerts_worker] Error: {exc}")
        import traceback

        traceback.print_exc()
