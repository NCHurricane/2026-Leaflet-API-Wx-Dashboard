"""Measure one Phase 0 cold-render command without touching operator caches.

The caller is responsible for configuring an isolated cache/output root for
the measured command. This wrapper never deletes or rewrites cache inputs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil


SCENARIOS = {
    "surface-gradient-world",
    "surface-gradient-conus",
    "radar-history",
    "goes-tile",
    "himawari-tile",
    "eumetsat-frame",
}


def _sample_peak_rss(process: psutil.Process, stop: threading.Event) -> int:
    peak = 0
    while not stop.is_set():
        try:
            processes = [process, *process.children(recursive=True)]
            rss = sum(item.memory_info().rss for item in processes if item.is_running())
            peak = max(peak, rss)
        except (psutil.Error, OSError):
            pass
        stop.wait(0.05)
    return peak


def _ledger_totals(path: Path) -> tuple[int, int]:
    request_count = 0
    byte_count = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0, 0
    for line in lines:
        try:
            entry = json.loads(line)
        except (TypeError, ValueError):
            continue
        if entry.get("event") != "upstream_request":
            continue
        request_count += 1
        byte_count += max(0, int(entry.get("bytes") or 0))
    return request_count, byte_count


def measure_command(scenario: str, command: list[str], output: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="wx-phase0-ledger-") as tmp_dir:
        ledger = Path(tmp_dir) / "requests.jsonl"
        env = os.environ.copy()
        env["WX_UPSTREAM_LEDGER"] = "1"
        env["WX_UPSTREAM_LEDGER_PATH"] = str(ledger)

        started = time.perf_counter()
        child = subprocess.Popen(command, env=env)
        process = psutil.Process(child.pid)
        stop = threading.Event()
        peak_box = {"value": 0}

        def _monitor() -> None:
            peak_box["value"] = _sample_peak_rss(process, stop)

        monitor = threading.Thread(target=_monitor, daemon=True)
        monitor.start()
        return_code = child.wait()
        stop.set()
        monitor.join(timeout=1.0)
        elapsed = time.perf_counter() - started
        request_count, downloaded_bytes = _ledger_totals(ledger)

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenario": scenario,
        "return_code": return_code,
        "duration_ms": round(elapsed * 1000.0, 3),
        "peak_rss_bytes": peak_box["value"],
        "upstream_request_count": request_count,
        "downloaded_bytes": downloaded_bytes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("cache/metrics/phase0_render_measurements.jsonl"),
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        parser.error("a command is required after --")

    result = measure_command(args.scenario, command, args.output)
    print(json.dumps(result, indent=2))
    return int(result["return_code"])


if __name__ == "__main__":
    raise SystemExit(main())
