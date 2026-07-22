"""Opt-in timing collector used by the Satellite v2 benchmark harness."""

from __future__ import annotations

import json
import os
import threading
import time
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BENCH_ENABLED = os.environ.get("WX_SATELLITE_V2_BENCH", "").strip() == "1"
_CURRENT_TIMING: ContextVar[dict[str, Any] | None] = ContextVar(
    "satellite_v2_bench_timing", default=None
)
_WRITE_LOCK = threading.Lock()


def bench_enabled() -> bool:
    return BENCH_ENABLED


def _run_id() -> str:
    configured = os.environ.get("WX_SATELLITE_V2_BENCH_RUN_ID", "").strip()
    if configured:
        return configured
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def begin_timing(
    cache_root: str | Path,
    context: dict[str, Any],
    initial: dict[str, Any] | None = None,
) -> Token | None:
    if not BENCH_ENABLED:
        return None
    record = dict(initial or {})
    record.update(context)
    record["run_id"] = _run_id()
    record["pid"] = os.getpid()
    scenario = os.environ.get("WX_SATELLITE_V2_BENCH_SCENARIO", "").strip()
    iteration = os.environ.get("WX_SATELLITE_V2_BENCH_ITERATION", "").strip()
    if scenario:
        record["scenario"] = scenario
    if iteration:
        record["iteration"] = int(iteration)
    record["_cache_root"] = str(cache_root)
    record.setdefault("_total_started", time.perf_counter())
    return _CURRENT_TIMING.set(record)


def add_timing_ms(stage: str, elapsed_ms: float) -> None:
    if not BENCH_ENABLED:
        return
    record = _CURRENT_TIMING.get()
    if record is None:
        return
    record[stage] = round(float(record.get(stage, 0.0)) + float(elapsed_ms), 3)


def finish_timing(token: Token | None, **updates: Any) -> None:
    if token is None:
        return
    record = _CURRENT_TIMING.get()
    try:
        if record is None:
            return
        record.update(updates)
        started = float(record.pop("_total_started", time.perf_counter()))
        record["total_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        cache_root = Path(str(record.pop("_cache_root")))
        sink = cache_root / "satellite" / ".bench" / f"{record['run_id']}.jsonl"
        sink.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(record, sort_keys=True, separators=(",", ":"))
        with _WRITE_LOCK:
            with sink.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")
    finally:
        _CURRENT_TIMING.reset(token)
