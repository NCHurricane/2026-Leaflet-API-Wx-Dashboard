"""Background worker: fetches national NWS alerts, enriches geometries, and writes dual-cache artifacts.

Produces:
  - cache/alerts/national_full.geojson (canonical full geometry, used for all interactions)
  - cache/alerts/national_display_low.geojson (simplified variant for low-zoom rendering)
"""

import json
import os
import sys
import threading
import time
import uuid
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path for both module and direct execution
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from workers._freshness import is_cache_fresh, mark_run_complete  # noqa: E402
from app_core.upstream_ledger import (  # noqa: E402
    measure_stage,
    measurement_context,
    record_measurement,
)

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "alerts"
CACHE_FILE_FULL = CACHE_DIR / "national_full.geojson"
CACHE_FILE_DISPLAY_LOW = CACHE_DIR / "national_display_low.geojson"

# Legacy cache path for backward compatibility (symlink or copy of full)
CACHE_FILE = CACHE_DIR / "national.geojson"

# Skip the run if a sentinel touch indicates a recent successful refresh.
# Threshold = 75% of the 60s scheduler interval, so an external Task Scheduler
# invocation will preempt the in-process tick (and vice versa).
_FRESH_WINDOW_SEC = 20


def run_alerts_worker(
    force: bool = False,
    *,
    measurement_run_id: str | None = None,
    measurement_pass: str | None = None,
) -> dict | None:
    """Fetch all active US alerts, enrich geometries, and write dual cache artifacts.

    Produces:
      - national_full.geojson: canonical full geometry (no simplification)
      - national_display_low.geojson: simplified variant for low-zoom rendering
      - national.geojson: legacy backward-compatible symlink to full
    """
    if not force and is_cache_fresh("alerts", _FRESH_WINDOW_SEC):
        print("[alerts_worker] Cache fresh — skipping run")
        return
    worker_start = time.perf_counter()
    measurement_fields = {
        "run_id": measurement_run_id or uuid.uuid4().hex,
        "process_pass": measurement_pass or "ordinary",
    }
    context = ExitStack()
    context.enter_context(measurement_context(**measurement_fields))
    try:
        from alerts.alerts_utils import (
            fetch_active_alerts_with_source,
            _create_display_low_features,
        )
        from services.alerts_service import enrich_alert_features_geometry

        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Fetch and enrich full features.
        fetch_start = time.perf_counter()
        features, source = fetch_active_alerts_with_source(state=None, source="nws")
        enrich_start = time.perf_counter()

        enrich_alert_features_geometry(features, measurement_fields=measurement_fields)
        enrich_elapsed = time.perf_counter() - enrich_start

        # Write full geometry cache (canonical).
        full_payload = {
            "type": "FeatureCollection",
            "_source": source,
            "_updated": datetime.now(timezone.utc).isoformat(),
            "_geometry_mode": "full",
            "features": features,
        }
        with measure_stage("alerts.full_cache.serialize_write"):
            full_payload_text = json.dumps(full_payload)
            CACHE_FILE_FULL.write_text(full_payload_text, encoding="utf-8")

        # Create and write simplified display-low variant.
        simplify_start = time.perf_counter()
        with measure_stage(
            "alerts.low_detail_simplification", feature_count=len(features)
        ):
            display_features, simplify_metrics = _create_display_low_features(features)
        simplify_elapsed = time.perf_counter() - simplify_start

        display_payload = {
            "type": "FeatureCollection",
            "_source": source,
            "_updated": datetime.now(timezone.utc).isoformat(),
            "_geometry_mode": "display",
            "_simplification_metrics": simplify_metrics,
            "features": display_features,
        }
        with measure_stage("alerts.low_detail_cache.serialize_write"):
            CACHE_FILE_DISPLAY_LOW.write_text(
                json.dumps(display_payload), encoding="utf-8"
            )

        # Write legacy backward-compatible cache (full geometry).
        with measure_stage("alerts.legacy_cache.write"):
            CACHE_FILE.write_text(full_payload_text, encoding="utf-8")

        # Emit worker metrics.
        total_elapsed = time.perf_counter() - worker_start
        summary = {
            **measurement_fields,
            "total_seconds": total_elapsed,
            "fetch_seconds": enrich_start - fetch_start,
            "enrich_seconds": enrich_elapsed,
            "simplify_seconds": simplify_elapsed,
            "feature_count": len(features),
        }
        record_measurement(
            stage="alerts.worker_total",
            duration_seconds=total_elapsed,
            fields={"feature_count": len(features)},
        )
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
        mark_run_complete("alerts")
        return summary
    except Exception as exc:
        print(f"[alerts_worker] Error: {exc}")
        import traceback

        traceback.print_exc()
        return None
    finally:
        context.close()


def measure_alerts_worker_twice() -> list[dict]:
    """Run forced cold/warm process passes and sample process RSS."""
    import psutil

    run_id = uuid.uuid4().hex
    summaries: list[dict] = []
    process = psutil.Process(os.getpid())
    for process_pass in ("cold_process", "warm_process"):
        stop_sampling = threading.Event()
        peak_rss = {"bytes": process.memory_info().rss}

        def _sample_rss() -> None:
            while not stop_sampling.wait(0.05):
                try:
                    peak_rss["bytes"] = max(
                        peak_rss["bytes"], process.memory_info().rss
                    )
                except psutil.Error:
                    return

        sampler = threading.Thread(target=_sample_rss, daemon=True)
        sampler.start()
        try:
            summary = run_alerts_worker(
                force=True,
                measurement_run_id=run_id,
                measurement_pass=process_pass,
            )
        finally:
            stop_sampling.set()
            sampler.join(timeout=1.0)
        if summary is None:
            continue
        summary["peak_rss_bytes"] = peak_rss["bytes"]
        summaries.append(summary)
        record_measurement(
            stage="alerts.process_peak_rss",
            duration_seconds=0.0,
            fields={
                "run_id": run_id,
                "process_pass": process_pass,
                "peak_rss_bytes": peak_rss["bytes"],
            },
        )
    print(json.dumps({"alerts_measurement_runs": summaries}, indent=2))
    return summaries


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the alerts worker once.")
    parser.add_argument("--force", action="store_true", help="Bypass freshness gate.")
    parser.add_argument(
        "--measure-twice",
        action="store_true",
        help="Run forced cold/warm passes in this process and emit Phase 0 metrics.",
    )
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to logs/scheduled/alerts.log (for headless task runs).",
    )
    args = parser.parse_args()
    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("alerts")
    if args.measure_twice:
        measure_alerts_worker_twice()
    else:
        run_alerts_worker(force=args.force)
