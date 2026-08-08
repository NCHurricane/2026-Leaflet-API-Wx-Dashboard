"""Background worker: fetches national NWS alerts, enriches geometries, and writes dual-cache artifacts.

Produces:
  - cache/alerts/national_full.geojson (canonical full geometry, used for all interactions)
  - cache/alerts/national_display_low.geojson (simplified variant for low-zoom rendering)
"""

import logging

import json
import os
import sys
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import ExitStack
from datetime import datetime, timezone
from hashlib import sha256
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
from app_core.atomic_io import atomic_write_json, atomic_write_text  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "alerts"
CACHE_FILE_FULL = CACHE_DIR / "national_full.geojson"
CACHE_FILE_DISPLAY_LOW = CACHE_DIR / "national_display_low.geojson"

# Legacy cache path for backward compatibility (symlink or copy of full)
CACHE_FILE = CACHE_DIR / "national.geojson"
GENERATION_DIR = CACHE_DIR / "generations"
CURRENT_GENERATION_FILE = CACHE_DIR / "current_generation.json"
_GENERATION_RETENTION = 2

# Skip direct worker runs when a successful refresh is inside the NWS-safe
# floor. Coordinator-owned runs separately enforce the same provider budget.
_FRESH_WINDOW_SEC = 35

_PROCESSED_FEATURE_CACHE_MAX_ENTRIES = 2048
_PROCESSED_FEATURE_CACHE: OrderedDict[tuple[str, str, str], dict] = OrderedDict()
_PROCESSED_FEATURE_CACHE_LOCK = threading.Lock()


def _feature_identity(feature: object, raw_json: str) -> str:
    if isinstance(feature, dict):
        props = feature.get("properties") or {}
        alert_id = str(feature.get("id") or props.get("id") or "").strip()
        if alert_id:
            return alert_id
    return sha256(raw_json.encode("utf-8")).hexdigest()


def _display_policy_fingerprint() -> str:
    from config.alerts_config import GEOMETRY_SIMPLIFICATION_SETTINGS

    policy_json = json.dumps(
        {
            "geometry_provenance_policy": "derived-only-v1",
            "settings": GEOMETRY_SIMPLIFICATION_SETTINGS,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(policy_json.encode("utf-8")).hexdigest()


def _get_processed_feature(cache_key: tuple[str, str, str]) -> dict | None:
    with _PROCESSED_FEATURE_CACHE_LOCK:
        entry = _PROCESSED_FEATURE_CACHE.get(cache_key)
        if entry is not None:
            _PROCESSED_FEATURE_CACHE.move_to_end(cache_key)
        return entry


def _put_processed_feature(cache_key: tuple[str, str, str], entry: dict) -> None:
    with _PROCESSED_FEATURE_CACHE_LOCK:
        _PROCESSED_FEATURE_CACHE[cache_key] = entry
        _PROCESSED_FEATURE_CACHE.move_to_end(cache_key)
        while len(_PROCESSED_FEATURE_CACHE) > _PROCESSED_FEATURE_CACHE_MAX_ENTRIES:
            _PROCESSED_FEATURE_CACHE.popitem(last=False)


def _combine_simplification_metrics(entries: list[dict]) -> dict:
    metrics = {
        "total_features": 0,
        "simplified_features": 0,
        "excluded_features": 0,
        "total_vertices_before": 0,
        "total_vertices_after": 0,
    }
    for entry in entries:
        feature_metrics = entry["simplification_metrics"]
        for key in metrics:
            metrics[key] += feature_metrics.get(key, 0)
    before = metrics["total_vertices_before"]
    after = metrics["total_vertices_after"]
    metrics["vertex_reduction_percent"] = (
        round(100.0 * (1.0 - (after / before)), 2) if before else 0.0
    )
    return metrics


def _prepare_feature_artifacts(
    features: list[dict],
    *,
    measurement_fields: dict,
) -> tuple[list[dict], dict, dict]:
    from alerts.alerts_utils import _create_display_low_features
    from services.alerts_service import enrich_alert_features_geometry

    policy_fingerprint = _display_policy_fingerprint()
    entries: list[dict | None] = []
    misses: list[tuple[int, tuple[str, str, str], dict]] = []

    for index, feature in enumerate(features):
        raw_json = json.dumps(feature, sort_keys=True, separators=(",", ":"))
        cache_key = (
            _feature_identity(feature, raw_json),
            sha256(raw_json.encode("utf-8")).hexdigest(),
            policy_fingerprint,
        )
        cached = _get_processed_feature(cache_key)
        entries.append(cached)
        if cached is None:
            misses.append((index, cache_key, feature))

    enrich_start = time.perf_counter()
    if misses:
        enrich_alert_features_geometry(
            [feature for _, _, feature in misses],
            measurement_fields=measurement_fields,
        )
    enrich_seconds = time.perf_counter() - enrich_start

    simplify_start = time.perf_counter()
    with measure_stage(
        "alerts.low_detail_simplification",
        feature_count=len(features),
        changed_feature_count=len(misses),
    ):
        for index, cache_key, feature in misses:
            display_features, metrics = _create_display_low_features([feature])
            entry = {
                "full_json": json.dumps(feature),
                "display_json": (
                    json.dumps(display_features[0]) if display_features else None
                ),
                "simplification_metrics": metrics,
            }
            if not isinstance(feature, dict) or feature.get("geometry"):
                _put_processed_feature(cache_key, entry)
            entries[index] = entry
    simplify_seconds = time.perf_counter() - simplify_start

    prepared_entries = [entry for entry in entries if entry is not None]
    record_measurement(
        stage="alerts.processed_feature_cache",
        duration_seconds=0.0,
        fields={
            "cache_hits": len(features) - len(misses),
            "cache_misses": len(misses),
            "cache_entries": len(_PROCESSED_FEATURE_CACHE),
            "cache_max_entries": _PROCESSED_FEATURE_CACHE_MAX_ENTRIES,
            **measurement_fields,
        },
    )
    return (
        prepared_entries,
        _combine_simplification_metrics(prepared_entries),
        {
            "cache_hits": len(features) - len(misses),
            "cache_misses": len(misses),
            "enrich_seconds": enrich_seconds,
            "simplify_seconds": simplify_seconds,
        },
    )


def _serialize_feature_collection(metadata: dict, feature_json: list[str]) -> str:
    payload = {**metadata, "features": []}
    empty_text = json.dumps(payload)
    return empty_text[:-2] + ", ".join(feature_json) + "]}"


def _publish_generation(
    *,
    generation: str,
    updated: str,
    full_payload_text: str,
    display_payload_text: str,
) -> None:
    generation_path = GENERATION_DIR / generation
    generation_path.mkdir(parents=True, exist_ok=False)
    generation_full = generation_path / "national_full.geojson"
    generation_display = generation_path / "national_display_low.geojson"
    atomic_write_text(generation_full, full_payload_text)
    atomic_write_text(generation_display, display_payload_text)

    # Keep legacy disk paths current for direct consumers. The API reads only
    # the generation manifest once it exists, so it cannot mix these mirrors.
    atomic_write_text(CACHE_FILE_FULL, full_payload_text)
    atomic_write_text(CACHE_FILE_DISPLAY_LOW, display_payload_text)
    atomic_write_text(CACHE_FILE, full_payload_text)
    atomic_write_json(
        CURRENT_GENERATION_FILE,
        {
            "generation": generation,
            "updated": updated,
            "files": {
                "full": str(generation_full.relative_to(CACHE_DIR)).replace("\\", "/"),
                "display_low": str(
                    generation_display.relative_to(CACHE_DIR)
                ).replace("\\", "/"),
                "compatibility": str(
                    generation_full.relative_to(CACHE_DIR)
                ).replace("\\", "/"),
            },
        },
        separators=(",", ":"),
    )

    retained = sorted(
        (path for path in GENERATION_DIR.iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for expired in retained[_GENERATION_RETENTION:]:
        for child in expired.iterdir():
            if child.is_file():
                child.unlink()
        expired.rmdir()


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
        logging.getLogger(__name__).info("[alerts_worker] Cache fresh — skipping run")
        return
    worker_start = time.perf_counter()
    measurement_fields = {
        "run_id": measurement_run_id or uuid.uuid4().hex,
        "process_pass": measurement_pass or "ordinary",
    }
    context = ExitStack()
    context.enter_context(measurement_context(**measurement_fields))
    try:
        from alerts.alerts_utils import fetch_active_alerts_with_source

        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Fetch and enrich full features.
        fetch_start = time.perf_counter()
        features, source = fetch_active_alerts_with_source(
            state=None,
            source="nws",
            strict=True,
        )
        fetch_elapsed = time.perf_counter() - fetch_start

        prepared_entries, simplify_metrics, processed_cache_metrics = (
            _prepare_feature_artifacts(
                features,
                measurement_fields=measurement_fields,
            )
        )
        enrich_elapsed = processed_cache_metrics["enrich_seconds"]

        generation = uuid.uuid4().hex
        updated = datetime.now(timezone.utc).isoformat()

        # Serialize one immutable generation before publishing its pointer.
        with measure_stage("alerts.full_cache.serialize_write"):
            full_payload_text = _serialize_feature_collection(
                {
                    "type": "FeatureCollection",
                    "_source": source,
                    "_updated": updated,
                    "_generation": generation,
                    "_geometry_mode": "full",
                },
                [entry["full_json"] for entry in prepared_entries],
            )

        # Create and write simplified display-low variant.
        display_feature_json = [
            entry["display_json"]
            for entry in prepared_entries
            if entry["display_json"] is not None
        ]
        simplify_elapsed = processed_cache_metrics["simplify_seconds"]

        with measure_stage("alerts.low_detail_cache.serialize_write"):
            display_payload_text = _serialize_feature_collection(
                {
                    "type": "FeatureCollection",
                    "_source": source,
                    "_updated": updated,
                    "_generation": generation,
                    "_geometry_mode": "display",
                    "_simplification_metrics": simplify_metrics,
                },
                display_feature_json,
            )

        with measure_stage("alerts.generation.publish"):
            _publish_generation(
                generation=generation,
                updated=updated,
                full_payload_text=full_payload_text,
                display_payload_text=display_payload_text,
            )

        # Emit worker metrics.
        total_elapsed = time.perf_counter() - worker_start
        summary = {
            **measurement_fields,
            "total_seconds": total_elapsed,
            "fetch_seconds": fetch_elapsed,
            "enrich_seconds": enrich_elapsed,
            "simplify_seconds": simplify_elapsed,
            "feature_count": len(features),
            "changed_feature_count": processed_cache_metrics["cache_misses"],
            "generation": generation,
            "updated": updated,
        }
        record_measurement(
            stage="alerts.worker_total",
            duration_seconds=total_elapsed,
            fields={
                "feature_count": len(features),
                "changed_feature_count": processed_cache_metrics["cache_misses"],
                "reused_feature_count": processed_cache_metrics["cache_hits"],
            },
        )
        logging.getLogger(__name__).info(
            f"[alerts_worker] Complete in {total_elapsed:.2f}s\n"
            f"  Fetch: {fetch_elapsed:.2f}s | "
            f"Enrich: {enrich_elapsed:.2f}s | "
            f"Simplify: {simplify_elapsed:.2f}s\n"
            f"  Features: {len(features)} total | "
            f"{processed_cache_metrics['cache_misses']} changed | "
            f"{processed_cache_metrics['cache_hits']} reused\n"
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
        logging.getLogger(__name__).warning(f"[alerts_worker] Error: {type(exc).__name__}")
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
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
        help="Redirect stdout/stderr to cache/logs/scheduled/alerts.log (for headless task runs).",
    )
    args = parser.parse_args()
    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("alerts")
    if args.measure_twice:
        measure_alerts_worker_twice()
    else:
        run_alerts_worker(force=args.force)
