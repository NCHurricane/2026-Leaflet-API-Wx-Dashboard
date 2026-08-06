"""Scratch-only benchmark and golden baseline CLI for live NEXRAD rendering."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence


_SCENARIOS = (
    "api-hit",
    "render-one",
    "empty-cache-response",
    "backfill-12",
    "no-op-worker",
    "l2-product-separate",
    "l2-product-batch",
)
_FRESH_PROCESS_SCENARIOS = {
    "render-one",
    "empty-cache-response",
    "backfill-12",
    "l2-product-separate",
    "l2-product-batch",
}
_PACKAGE_NAMES = (
    "arm_pyart",
    "Cartopy",
    "matplotlib",
    "numpy",
    "Pillow",
    "psutil",
)
_BASELINE_ROWS = {
    ("KGSP", "L2_REF"): 1,
    ("KGSP", "L2_VEL"): 2,
    ("KGSP", "L2_SRV"): 3,
    ("KGSP", "L2_ZDR"): 4,
    ("KGSP", "L3_N0B"): 5,
    ("KGSP", "L3_N0G"): 6,
    ("KFCX", "L3_DPR"): 7,
    ("KFCX", "L2_REF"): 8,
}


def _utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    if os.environ.get("WX_RADAR_BENCH") != "1":
        raise RuntimeError("Radar benchmark timing requires WX_RADAR_BENCH=1")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def _safe_scratch_root(cache_root: Path, run_id: str) -> Path:
    run_name = Path(str(run_id)).name
    if run_name != str(run_id) or run_name in {"", ".", ".."}:
        raise ValueError("Unsafe Radar benchmark run id")
    bench_root = (cache_root.resolve() / "radar" / ".bench").resolve()
    scratch = (bench_root / run_name).resolve()
    if scratch.parent != bench_root:
        raise ValueError("Radar benchmark scratch root escaped cache/radar/.bench")
    return scratch


def _source_manifest(path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    stat = path.stat()
    digest = _sha256(path)
    return {
        "source_path": str(path),
        "source_key": path.name,
        "source_size": int(stat.st_size),
        "source_sha256": digest,
        "source_mtime_ns": int(stat.st_mtime_ns),
        "download_check_ms": (time.perf_counter() - started) * 1000.0,
    }


def _png_contract(path: Path) -> dict[str, Any]:
    from PIL import Image

    with Image.open(path) as source:
        image = source.convert("RGBA")
        rgba = image.tobytes()
        alpha = image.getchannel("A")
        histogram = alpha.histogram()
        return {
            "output_path": str(path),
            "png_size": path.stat().st_size,
            "png_sha256": _sha256(path),
            "rgba_sha256": hashlib.sha256(rgba).hexdigest(),
            "width": image.width,
            "height": image.height,
            "nontransparent_pixels": image.width * image.height - histogram[0],
            "rgba_bbox": list(alpha.getbbox()) if alpha.getbbox() else None,
        }


def _rss_tree_bytes() -> int | None:
    try:
        import psutil

        process = psutil.Process()
        total = int(process.memory_info().rss)
        for child in process.children(recursive=True):
            try:
                total += int(child.memory_info().rss)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return total
    except Exception:
        return None


@contextmanager
def _working_set_sample() -> Iterator[dict[str, int | None]]:
    samples: dict[str, int | None] = {
        "working_set_before": _rss_tree_bytes(),
        "working_set_peak": None,
        "working_set_after": None,
    }
    stop = threading.Event()

    def sample() -> None:
        while not stop.wait(0.02):
            current = _rss_tree_bytes()
            if current is None:
                continue
            peak = samples["working_set_peak"]
            samples["working_set_peak"] = current if peak is None else max(peak, current)

    thread = threading.Thread(target=sample, name="radar-bench-rss", daemon=True)
    thread.start()
    try:
        yield samples
    finally:
        stop.set()
        thread.join(timeout=1.0)
        samples["working_set_after"] = _rss_tree_bytes()
        values = [
            value
            for value in (
                samples["working_set_before"],
                samples["working_set_peak"],
                samples["working_set_after"],
            )
            if value is not None
        ]
        samples["working_set_peak"] = max(values) if values else None


def _product_context(
    site: str,
    product: str,
    elevation: str,
) -> dict[str, Any]:
    from config.radar_config import LIVE_RADAR_PRODUCTS
    from workers import radar_live_worker as worker

    site_key = str(site).strip().upper()
    product_key = str(product).strip().upper()
    product_cfg = LIVE_RADAR_PRODUCTS.get(product_key)
    if product_cfg is None:
        raise ValueError(f"Unknown live Radar product: {product_key}")
    product_cfg = dict(product_cfg)
    level = str(product_cfg.get("level") or "Level 3")
    product_code = str(product_cfg.get("product") or "N0B").upper()
    bounds = worker._site_bounds(site_key)
    if not bounds:
        raise ValueError(f"Unknown Radar site coordinates: {site_key}")
    cache_product_key = worker._radar_cache_product_key(
        product_key, elevation, product_cfg
    )
    return {
        "site": site_key,
        "product": product_key,
        "product_cfg": product_cfg,
        "level": level,
        "level_code": worker._level_code(level),
        "product_code": product_code,
        "source_product_code": worker._source_product_code(
            product_code, product_cfg
        ),
        "bounds": bounds,
        "cache_product_key": cache_product_key,
        "elevation": elevation,
    }


@contextmanager
def _worker_scratch(scratch: Path) -> Iterator[Path]:
    from workers import radar_live_worker as worker

    cache_root = scratch / "cache"
    original = (worker._CACHE_ROOT, worker._RADAR_ROOT, worker._TMP_RENDER_ROOT)
    worker._CACHE_ROOT = cache_root
    worker._RADAR_ROOT = scratch / "source"
    worker._TMP_RENDER_ROOT = scratch / "tmp"
    try:
        yield cache_root
    finally:
        worker._CACHE_ROOT, worker._RADAR_ROOT, worker._TMP_RENDER_ROOT = original


def _link_sources(sources: Sequence[Path], destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    linked = []
    for index, source in enumerate(sources):
        name = source.name
        target = destination / name
        if target.exists():
            target = destination / f"{index:03d}_{name}"
        try:
            os.link(source, target)
        except OSError:
            shutil.copyfile(source, target)
        linked.append(target)
    return linked


class _PinnedData:
    __name__ = "radar.bench_pinned_data"

    def __init__(self, source_dir: Path):
        self.source_dir = source_dir
        self.list_ms = 0.0
        self.download_check_ms = 0.0

    def reset_timings(self) -> None:
        self.list_ms = 0.0
        self.download_check_ms = 0.0

    def download_radar_data(self, *_args, **_kwargs):
        started = time.perf_counter()
        files = [path for path in self.source_dir.iterdir() if path.is_file()]
        self.list_ms += (time.perf_counter() - started) * 1000.0
        started = time.perf_counter()
        files = [path for path in files if path.stat().st_size > 0]
        self.download_check_ms += (time.perf_counter() - started) * 1000.0
        return str(self.source_dir), len(files), 0


def _render_one(
    context: dict[str, Any],
    source: Path,
    scratch: Path,
) -> dict[str, Any]:
    from app_core.overlay_cache import (
        frame_key_from_datetime,
        radar_overlay_image_path,
        radar_update_index,
    )
    from workers import radar_live_worker as worker

    record = _source_manifest(source)
    total_started = time.perf_counter()
    with _working_set_sample() as memory:
        started = time.perf_counter()
        radar = worker._read_radar(context["level"], str(source))
        record["read_ms"] = (time.perf_counter() - started) * 1000.0

        started = time.perf_counter()
        fields = list(getattr(radar, "fields", {}).keys())
        field_name = worker._field_for_product(
            context["level"],
            context["product_code"],
            fields,
            context["product_cfg"],
        )
        record["field_ms"] = (time.perf_counter() - started) * 1000.0
        if not field_name:
            raise RuntimeError(f"No renderable field in pinned source {source}")

        started = time.perf_counter()
        field_name = worker._ensure_derived_field(
            radar, field_name, context["product_cfg"]
        )
        record["derive_ms"] = (time.perf_counter() - started) * 1000.0

        frame_dt = worker._frame_dt_from_radar(radar, source)
        if frame_dt is None:
            raise RuntimeError(f"No timestamp in pinned source {source}")
        frame_key = frame_key_from_datetime(frame_dt)

        started = time.perf_counter()
        sweep, available, selected = worker._select_sweep(
            radar, field_name, context["elevation"]
        )
        record["sweep_ms"] = (time.perf_counter() - started) * 1000.0

        temp_path = scratch / "tmp" / f"{frame_key}.png"
        render_timings: dict[str, float] = {}
        if not worker._render_overlay_png(
            radar=radar,
            field_name=field_name,
            bounds=context["bounds"],
            out_path=temp_path,
            product_code=context["product_code"],
            product_cfg=context["product_cfg"],
            sweep=sweep,
            timings=render_timings,
        ):
            raise RuntimeError(f"Radar render failed for {source}")
        record["field_ms"] += render_timings.pop("field_ms", 0.0)
        record["sweep_ms"] += render_timings.pop("sweep_ms", 0.0)
        record.update(render_timings)

        with _worker_scratch(scratch) as cache_root:
            started = time.perf_counter()
            destination = Path(
                radar_overlay_image_path(
                    str(cache_root),
                    context["site"],
                    context["level_code"],
                    context["cache_product_key"],
                    frame_key,
                )
            )
            worker._finalize_rendered_png(temp_path, destination)
            record["finalize_ms"] = (time.perf_counter() - started) * 1000.0

            from radar.webgl_artifact import feature_config, write_artifact

            if context["product"] in feature_config()["products"]:
                started = time.perf_counter()
                artifact = write_artifact(
                    cache_root,
                    context["site"],
                    frame_key,
                    selected,
                    radar,
                    field_name,
                    sweep,
                    context["product_cfg"],
                    context["product"],
                )
                record["webgl_artifact_ms"] = (
                    time.perf_counter() - started
                ) * 1000.0
                record["webgl_artifact_bytes"] = (
                    artifact.stat().st_size if artifact is not None else 0
                )

            started = time.perf_counter()
            radar_update_index(
                str(cache_root),
                context["site"],
                context["level_code"],
                context["cache_product_key"],
                frame_key,
                bounds=context["bounds"],
                full_name=context["product_cfg"].get("label", context["product"]),
                units=worker._units_for_product(
                    context["product"],
                    context["product_code"],
                    context["product_cfg"],
                ),
                data_key=source.name,
                available_elevations=available,
                selected_elevation=selected,
            )
            record["index_ms"] = (time.perf_counter() - started) * 1000.0

        record.update(_png_contract(destination))
        record.update(
            {
                "frame_key": frame_key,
                "field": field_name,
                "sweep": sweep,
                "available_elevations": available,
                "selected_elevation": selected,
                "bounds": context["bounds"],
                "cache_key": context["cache_product_key"],
                "product_code": context["product_code"],
                "source_product_code": context["source_product_code"],
                "units": worker._units_for_product(
                    context["product"],
                    context["product_code"],
                    context["product_cfg"],
                ),
                "palette": context["product_cfg"].get("palette"),
                "mask": context["product_cfg"].get("mask"),
                "vmin": context["product_cfg"].get("vmin"),
                "vmax": context["product_cfg"].get("vmax"),
            }
        )
    record.update(memory)
    record["total_ms"] = (time.perf_counter() - total_started) * 1000.0
    return record


def _worker_scenario(
    scenario: str,
    context: dict[str, Any],
    sources: Sequence[Path],
    scratch: Path,
) -> dict[str, Any]:
    from workers import radar_live_worker as worker

    if scenario == "backfill-12":
        needed = 12
    elif scenario in {"l2-product-separate", "l2-product-batch"}:
        needed = 1
    elif scenario == "empty-cache-response":
        from services.radar_service import _RADAR_EMPTY_CACHE_RESPONSE_SYNC_FRAMES

        needed = _RADAR_EMPTY_CACHE_RESPONSE_SYNC_FRAMES
    else:
        needed = min(3, len(sources))
    selected = list(sources[-needed:])
    source_dir = scratch / "pinned"
    _link_sources(selected, source_dir)
    provider = _PinnedData(source_dir)
    radar_service = None
    if scenario == "api-hit":
        from services import radar_service as radar_service_module

        radar_service = radar_service_module
    common = dict(
        radar_data_utils=provider,
        source_label="Pinned-Disk",
        site=context["site"],
        product_key=context["product"],
        product_cfg=context["product_cfg"],
        elevation=context["elevation"],
        lookback_hours=12,
    )
    record: dict[str, Any] = {}

    with _worker_scratch(scratch) as cache_root, _working_set_sample() as memory:
        if scenario in {"api-hit", "no-op-worker"}:
            worker._render_site_product(
                **common,
                newest_first=True,
                max_render_frames=min(3, len(selected)),
            )
            provider.reset_timings()

        pool_context = (
            worker._radar_render_pool_owner()
            if scenario == "backfill-12"
            else nullcontext(None)
        )
        with pool_context as render_pool:
            if render_pool is not None:
                process_ids = render_pool.warm()
                record.update(
                    {
                        "reused_pool": True,
                        "pool_processes": render_pool.processes,
                        "pool_creation_count": render_pool.creation_count,
                        "pool_startup_ms": render_pool.startup_ms,
                        "pool_warm_ms": render_pool.warm_ms,
                        "pool_ready_processes": len(set(process_ids)),
                    }
                )

            started = time.perf_counter()
            if scenario == "api-hit":
                assert radar_service is not None
                original_cache_root = radar_service.CACHE_ROOT
                original_background = radar_service._radar_live_render_in_background
                radar_service.CACHE_ROOT = str(cache_root)
                radar_service._radar_live_render_in_background = (
                    lambda *_args, **_kwargs: False
                )
                try:
                    latest_started = time.perf_counter()
                    latest = radar_service.get_radar_live_latest_data(
                        site=context["site"],
                        product=context["product"],
                        elevation=context["elevation"],
                    )
                    record["latest_ms"] = (
                        time.perf_counter() - latest_started
                    ) * 1000.0
                    frames_started = time.perf_counter()
                    frames = radar_service.get_radar_live_frames_data(
                        site=context["site"],
                        product=context["product"],
                        elevation=context["elevation"],
                        hours=12,
                    )
                    record["frames_ms"] = (
                        time.perf_counter() - frames_started
                    ) * 1000.0
                finally:
                    radar_service.CACHE_ROOT = original_cache_root
                    radar_service._radar_live_render_in_background = original_background
                record["response_ms"] = (time.perf_counter() - started) * 1000.0
                record["frame_count"] = frames.get("frame_count", 0)
                record["frame_key"] = latest.get("frame_key")
            elif scenario == "empty-cache-response":
                from services.radar_service import (
                    _RADAR_EMPTY_CACHE_RESPONSE_SYNC_FRAMES,
                )

                record["rendered_frames"] = worker._render_site_product(
                    **common,
                    newest_first=True,
                    max_render_frames=_RADAR_EMPTY_CACHE_RESPONSE_SYNC_FRAMES,
                )
                record["response_ms"] = (time.perf_counter() - started) * 1000.0
            elif scenario == "backfill-12":
                record["rendered_frames"] = worker._render_site_product(
                    **common,
                    render_pool=render_pool,
                )
                record["pool_render_batches"] = render_pool.render_batches
            elif scenario == "no-op-worker":
                original_discover = worker._discover_radar_files
                discovery_scan_count = 0

                def counted_discover(data_path):
                    nonlocal discovery_scan_count
                    discovery_scan_count += 1
                    return original_discover(data_path)

                worker._discover_radar_files = counted_discover
                try:
                    record["rendered_frames"] = worker._render_site_product(**common)
                finally:
                    worker._discover_radar_files = original_discover
                record["discovery_scan_count"] = discovery_scan_count
                record["discovery_reused"] = discovery_scan_count == 0
            elif scenario in {"l2-product-separate", "l2-product-batch"}:
                from config.radar_config import (
                    LIVE_RADAR_L2_DEFAULT_ELEVATION,
                    LIVE_RADAR_PRODUCTS,
                )

                products = [
                    (product_key, dict(product_cfg))
                    for product_key, product_cfg in LIVE_RADAR_PRODUCTS.items()
                    if worker._level_code(product_cfg.get("level", "Level 3")) == "L2"
                ]
                original_read = worker._read_radar
                decode_count = 0

                def counted_read(level, source_path):
                    nonlocal decode_count
                    decode_count += 1
                    return original_read(level, source_path)

                worker._read_radar = counted_read
                try:
                    if scenario == "l2-product-batch":
                        rendered, failed = worker._render_site_l2_products(
                            provider,
                            context["site"],
                            products,
                            elevation=LIVE_RADAR_L2_DEFAULT_ELEVATION,
                        )
                    else:
                        rendered = 0
                        failed = 0
                        for product_key, product_cfg in products:
                            try:
                                rendered += worker._render_site_product(
                                    provider,
                                    "Pinned-Disk",
                                    context["site"],
                                    product_key,
                                    product_cfg,
                                    elevation=LIVE_RADAR_L2_DEFAULT_ELEVATION,
                                )
                            except Exception:
                                failed += 1
                finally:
                    worker._read_radar = original_read
                record.update(
                    {
                        "rendered_frames": rendered,
                        "failed_products": failed,
                        "product_count": len(products),
                        "decode_count": decode_count,
                    }
                )
            else:
                raise ValueError(
                    f"Unsupported worker benchmark scenario: {scenario}"
                )
            record["total_ms"] = (time.perf_counter() - started) * 1000.0
            record["list_ms"] = provider.list_ms
            record["download_check_ms"] = provider.download_check_ms
    record.update(memory)
    record["source_count"] = len(selected)
    record["source_files"] = [
        {
            "source_key": path.name,
            "source_size": path.stat().st_size,
            "source_sha256": _sha256(path),
            "source_mtime_ns": path.stat().st_mtime_ns,
        }
        for path in selected
    ]
    return record


def _run_scenario(
    scenario: str,
    context: dict[str, Any],
    sources: Sequence[Path],
    scratch: Path,
) -> dict[str, Any]:
    if scenario == "render-one":
        return _render_one(context, sources[-1], scratch)
    return _worker_scenario(scenario, context, sources, scratch)


def _git_details(repo_root: Path) -> tuple[str, list[str]]:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return sha, dirty


def _environment_manifest(
    repo_root: Path,
    context: dict[str, Any],
    worker_state_note: str,
) -> dict[str, Any]:
    git_sha, dirty_files = _git_details(repo_root)
    packages = {}
    for name in _PACKAGE_NAMES:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    try:
        import psutil

        ram_bytes = int(psutil.virtual_memory().total)
    except Exception:
        ram_bytes = None
    from config.radar_config import LIVE_RADAR_L2_USE_CHUNKS, LIVE_RADAR_PARALLEL_WORKERS

    return {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha,
        "dirty_files": dirty_files,
        "python": sys.version,
        "packages": packages,
        "cpu": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "ram_bytes": ram_bytes,
        "platform": platform.platform(),
        "live_radar_l2_use_chunks": bool(LIVE_RADAR_L2_USE_CHUNKS),
        "live_radar_parallel_workers": LIVE_RADAR_PARALLEL_WORKERS,
        "worker_state_note": worker_state_note,
        "benchmark": context,
    }


def _summary_markdown(
    context: dict[str, Any],
    records: list[dict[str, Any]],
) -> str:
    metrics = sorted(
        {
            key
            for record in records
            for key, value in record.items()
            if key.endswith("_ms") and isinstance(value, (int, float))
        }
    )
    lines = [
        f"# Radar benchmark {context['run_id']}",
        "",
        f"- Target: `{context['site']}/{context['product']}`",
        f"- Scenario: `{context['scenario']}`",
        f"- Samples: {len(records)}",
        "",
        "| metric | p50 ms | p95 ms | samples |",
        "|---|---:|---:|---:|",
    ]
    for metric in metrics:
        values = [float(record[metric]) for record in records if metric in record]
        lines.append(
            f"| `{metric}` | {_percentile(values, 0.50):.3f} | "
            f"{_percentile(values, 0.95):.3f} | {len(values)} |"
        )
    memory_metrics = (
        "working_set_before",
        "working_set_peak",
        "working_set_after",
    )
    lines.extend(
        [
            "",
            "| working set | p50 MiB | p95 MiB | samples |",
            "|---|---:|---:|---:|",
        ]
    )
    for metric in memory_metrics:
        values = [
            float(record[metric]) / (1024.0 * 1024.0)
            for record in records
            if isinstance(record.get(metric), (int, float))
        ]
        lines.append(
            f"| `{metric}` | {_percentile(values, 0.50):.3f} | "
            f"{_percentile(values, 0.95):.3f} | {len(values)} |"
        )
    return "\n".join(lines) + "\n"


def _golden_payload(
    context: dict[str, Any],
    records: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    required = (
        "source_key",
        "source_sha256",
        "source_size",
        "png_size",
        "png_sha256",
        "rgba_sha256",
        "width",
        "height",
        "nontransparent_pixels",
        "rgba_bbox",
        "frame_key",
        "bounds",
        "cache_key",
        "selected_elevation",
        "available_elevations",
        "units",
        "palette",
        "mask",
        "vmin",
        "vmax",
    )
    contracts = [
        {key: record.get(key) for key in required}
        for record in records
        if record.get("png_sha256")
    ]
    if not contracts:
        raise RuntimeError("Golden capture requires a render-one record")
    first = contracts[0]
    if any(contract != first for contract in contracts[1:]):
        raise RuntimeError("Repeated Radar golden renders did not match")
    return {
        "site": context["site"],
        "product": context["product"],
        "elevation": context["elevation"],
        "contract": first,
    }


def _golden_path(golden_dir: Path, context: dict[str, Any]) -> Path:
    row = _BASELINE_ROWS.get((context["site"], context["product"]), 999)
    return golden_dir / f"{row:02d}-{context['site']}-{context['product']}.json"


def _update_matrix(output_dir: Path) -> None:
    manifests = []
    for path in output_dir.glob("*-manifest.json"):
        if path.name == "matrix-manifest.json":
            continue
        manifests.append(json.loads(path.read_text(encoding="utf-8")))
    if not manifests:
        return
    runs = [manifest["benchmark"] for manifest in manifests]
    runs.sort(
        key=lambda run: (
            _BASELINE_ROWS.get((run["site"], run["product"]), 999),
            _SCENARIOS.index(run["scenario"]),
            run["run_id"],
        )
    )
    matrix = {
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_runs": runs,
    }
    (output_dir / "matrix-manifest.json").write_text(
        json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        "# Radar benchmark matrix",
        "",
        "| target | scenario | samples | total p50 ms | total p95 ms | peak RSS p95 MiB |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for run in runs:
        raw_path = Path(run["raw_jsonl"])
        records = _read_jsonl(raw_path)
        (output_dir / f"{run['run_id']}-summary.md").write_text(
            _summary_markdown(run, records), encoding="utf-8"
        )
        totals = [float(record["total_ms"]) for record in records]
        peaks = [
            float(record["working_set_peak"]) / (1024.0 * 1024.0)
            for record in records
            if isinstance(record.get("working_set_peak"), (int, float))
        ]
        lines.append(
            f"| `{run['site']}/{run['product']}` | `{run['scenario']}` | "
            f"{len(records)} | {_percentile(totals, 0.50):.3f} | "
            f"{_percentile(totals, 0.95):.3f} | "
            f"{_percentile(peaks, 0.95):.3f} |"
        )
    (output_dir / "baseline-summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True)
    parser.add_argument("--product", required=True)
    parser.add_argument(
        "--source",
        type=Path,
        action="append",
        required=True,
        help="Pinned local NODD source file; repeat for backfill-12.",
    )
    parser.add_argument("--elevation", default="auto")
    parser.add_argument("--scenario", choices=_SCENARIOS, required=True)
    parser.add_argument("--repeat", type=int)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--golden", choices=("capture", "compare"))
    parser.add_argument("--golden-dir", type=Path)
    parser.add_argument("--worker-state-note", default="")
    parser.add_argument("--run-id")
    parser.add_argument("--_child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_iteration", type=int, default=1, help=argparse.SUPPRESS)
    return parser


def _child_command(
    args: argparse.Namespace,
    run_id: str,
    iteration: int,
    cache_root: Path,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "radar.bench",
        "--site",
        args.site,
        "--product",
        args.product,
        "--elevation",
        args.elevation,
        "--scenario",
        args.scenario,
        "--repeat",
        "1",
        "--cache-root",
        str(cache_root),
        "--run-id",
        run_id,
        "--_child",
        "--_iteration",
        str(iteration),
    ]
    for source in args.source:
        command.extend(("--source", str(source.resolve())))
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.repeat is None:
        args.repeat = 5 if args.scenario in _FRESH_PROCESS_SCENARIOS else 10
    if args.repeat < 1:
        raise SystemExit("--repeat must be at least 1")
    sources = [path.resolve() for path in args.source]
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        raise SystemExit(f"Pinned Radar source files are missing: {missing}")
    if args.scenario == "backfill-12" and len(sources) < 12:
        raise SystemExit("backfill-12 requires at least 12 --source files")
    if args.golden and args.scenario != "render-one":
        raise SystemExit("--golden requires --scenario render-one")
    if args.golden and args.golden_dir is None:
        raise SystemExit("--golden-dir is required with --golden")

    from app_core.paths import BASE_PATH, CACHE_ROOT

    cache_root = (args.cache_root or Path(CACHE_ROOT)).resolve()
    run_id = args.run_id or _utc_run_id()
    scratch = _safe_scratch_root(cache_root, run_id)
    if scratch.exists() and not args._child:
        raise RuntimeError(f"Radar benchmark run id already exists: {run_id}")
    scratch.mkdir(parents=True, exist_ok=args._child)
    raw_jsonl = scratch / "results.jsonl"
    os.environ["WX_RADAR_BENCH"] = "1"
    os.environ["WX_RADAR_BENCH_RUN_ID"] = run_id
    os.environ["WX_RADAR_BENCH_SCENARIO"] = args.scenario

    context = _product_context(
        args.site,
        args.product,
        str(args.elevation).strip().lower(),
    )
    context.update(
        {
            "run_id": run_id,
            "scenario": args.scenario,
            "repeat": args.repeat,
            "sources": [str(path) for path in sources],
            "raw_jsonl": str(raw_jsonl),
        }
    )

    if args._child:
        iteration_scratch = scratch / f"iteration-{args._iteration:02d}"
        iteration_scratch.mkdir()
        record = _run_scenario(
            args.scenario,
            context,
            sources,
            iteration_scratch,
        )
        record.update(
            {
                "run_id": run_id,
                "iteration": args._iteration,
                "scenario": args.scenario,
                "site": context["site"],
                "product": context["product"],
                "elevation": context["elevation"],
            }
        )
        _append_jsonl(raw_jsonl, record)
        return 0

    if args.scenario in _FRESH_PROCESS_SCENARIOS:
        for iteration in range(1, args.repeat + 1):
            subprocess.run(
                _child_command(args, run_id, iteration, cache_root),
                cwd=BASE_PATH,
                check=True,
            )
    else:
        for iteration in range(1, args.repeat + 1):
            iteration_scratch = scratch / f"iteration-{iteration:02d}"
            iteration_scratch.mkdir()
            record = _run_scenario(
                args.scenario,
                context,
                sources,
                iteration_scratch,
            )
            record.update(
                {
                    "run_id": run_id,
                    "iteration": iteration,
                    "scenario": args.scenario,
                    "site": context["site"],
                    "product": context["product"],
                    "elevation": context["elevation"],
                }
            )
            _append_jsonl(raw_jsonl, record)

    records = _read_jsonl(raw_jsonl)
    manifest = _environment_manifest(
        Path(BASE_PATH),
        context,
        args.worker_state_note
        or "Not inspected automatically; record scheduled warmer state explicitly.",
    )
    (scratch / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (scratch / "summary.md").write_text(
        _summary_markdown(context, records), encoding="utf-8"
    )

    if args.golden:
        golden_dir = args.golden_dir.resolve()
        golden_path = _golden_path(golden_dir, context)
        current = _golden_payload(context, records)
        if args.golden == "capture":
            golden_path.parent.mkdir(parents=True, exist_ok=True)
            golden_path.write_text(
                json.dumps(current, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            expected = json.loads(golden_path.read_text(encoding="utf-8"))
            if current != expected:
                raise RuntimeError(f"Radar golden comparison failed: {golden_path}")

    if args.output_dir:
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{run_id}-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_dir / f"{run_id}-summary.md").write_text(
            _summary_markdown(context, records), encoding="utf-8"
        )
        _update_matrix(output_dir)

    print(f"Radar benchmark raw results: {raw_jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
