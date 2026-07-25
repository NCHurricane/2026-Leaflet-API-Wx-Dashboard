"""Optional cache warmer that delegates all work to the running application.

This module never imports or executes direct-writing worker functions. Each
bounded profile calls localhost API routes, so deduplication, provider floors,
backoff, render budgets, and atomic publication remain application-owned.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from workers._freshness import redirect_stdio_to_log


OUTCOMES = {"warmed", "current", "already_running", "backoff", "failed"}


@dataclass(frozen=True)
class WarmerTarget:
    name: str
    path: str


PROFILES: dict[str, tuple[WarmerTarget, ...]] = {
    "core": (
        WarmerTarget("alerts", "/api/data/alerts?geometry_mode=simplified&zoom_bucket=low"),
        WarmerTarget("spc-day1", "/api/data/spc?day=1&hazard=cat"),
        WarmerTarget("wpc-day1", "/api/data/wpc?group=ero&day=1"),
        WarmerTarget("tropical", "/api/tropical/storms?basin=WORLD"),
        WarmerTarget(
            "water-index",
            "/api/water/stations?bbox=-125,24,-66,50&max_sites=1",
        ),
    ),
    "surface": (
        WarmerTarget(
            "surface-temperature",
            "/api/data/surface?region=CONUS&product=temperature",
        ),
        WarmerTarget(
            "surface-gradient-temperature",
            "/api/data/surface-gradient?region=CONUS&product=temperature",
        ),
    ),
}


def _classify_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "current"
    state = str(payload.get("cache_state") or payload.get("status") or "").lower()
    if state == "backoff":
        return "backoff"
    if payload.get("refreshing") or state in {"warming", "refreshing", "queued", "running"}:
        return "already_running"
    return "current"


def _request_target(base_url: str, target: WarmerTarget, timeout: float) -> str:
    url = urljoin(base_url.rstrip("/") + "/", target.path.lstrip("/"))
    request = Request(url, headers={"User-Agent": "Wx-Dashboard-Optional-Warmer/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return "failed"
    return _classify_payload(payload)


def run_profile(
    profile: str,
    *,
    base_url: str = "http://127.0.0.1:8000",
    timeout: float = 30.0,
    wait_seconds: float = 20.0,
    poll_seconds: float = 2.0,
) -> dict[str, Any]:
    targets = PROFILES[profile]
    initial = {
        target.name: _request_target(base_url, target, timeout) for target in targets
    }
    results = dict(initial)
    pending = [
        target for target in targets if initial[target.name] == "already_running"
    ]
    deadline = time.monotonic() + max(0.0, wait_seconds)

    while pending and time.monotonic() < deadline:
        time.sleep(min(max(0.05, poll_seconds), max(0.0, deadline - time.monotonic())))
        next_pending: list[WarmerTarget] = []
        for target in pending:
            outcome = _request_target(base_url, target, timeout)
            if outcome == "current":
                results[target.name] = "warmed"
            else:
                results[target.name] = outcome
                if outcome == "already_running":
                    next_pending.append(target)
        pending = next_pending

    priority = ("failed", "backoff", "warmed", "already_running", "current")
    overall = next(
        outcome for outcome in priority if outcome in set(results.values())
    )
    return {"profile": profile, "outcome": overall, "targets": results}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Warm bounded dashboard profiles through the running API."
    )
    parser.add_argument("--profile", choices=sorted(PROFILES), required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--wait-seconds", type=float, default=20.0)
    parser.add_argument("--log-to-file", action="store_true")
    args = parser.parse_args()
    if args.log_to_file:
        redirect_stdio_to_log(f"optional_warmer_{args.profile}")
    result = run_profile(
        args.profile,
        base_url=args.base_url,
        timeout=args.timeout,
        wait_seconds=args.wait_seconds,
    )
    print(json.dumps(result, sort_keys=True))
    return 1 if result["outcome"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
