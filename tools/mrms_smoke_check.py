#!/usr/bin/env python3
"""MRMS regression smoke checks for local FastAPI server.

Usage:
    python tools/mrms_smoke_check.py

Optional examples:
    python tools/mrms_smoke_check.py --base-url http://127.0.0.1:8000
    python tools/mrms_smoke_check.py --archive-days-back 365
    python tools/mrms_smoke_check.py --archive-from 2025-04-03T12:00 --archive-to 2025-04-03T13:00
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str


def _request_json(
    base_url: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 120,
) -> Tuple[int, Dict[str, Any]]:
    query = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{query}"

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = int(response.status)
            payload = json.loads(body) if body else {}
            if not isinstance(payload, dict):
                payload = {"raw": payload}
            return status, payload
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            payload = json.loads(body) if body else {}
            if not isinstance(payload, dict):
                payload = {"raw": payload}
        except Exception:
            payload = {"raw": body}
        payload.setdefault("http_error", str(exc))
        return int(exc.code), payload


def _new_request_id(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000)}"


def _default_archive_window(days_back: int) -> Tuple[str, str]:
    now = datetime.now(timezone.utc)
    end = (now - timedelta(days=max(1, days_back))
           ).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=1)
    return start.strftime("%Y-%m-%dT%H:%M"), end.strftime("%Y-%m-%dT%H:%M")


def run_checks(args: argparse.Namespace) -> List[CheckResult]:
    results: List[CheckResult] = []

    archive_from = args.archive_from
    archive_to = args.archive_to
    if not archive_from or not archive_to:
        archive_from, archive_to = _default_archive_window(
            args.archive_days_back)

    base = args.base_url.rstrip("/")

    def record(name: str, ok: bool, details: str) -> None:
        results.append(CheckResult(name=name, ok=ok, details=details))

    # 1) API status
    code, payload = _request_json(base, "/api/status", timeout=args.timeout)
    status_ok = code == 200 and payload.get(
        "status") == "Weather System Online"
    record("api_status", status_ok,
           f"http={code} payload_status={payload.get('status')}")

    # 2) Current endpoint should not 422 and should return JSON contract
    current_req = _new_request_id("mrms-current")
    code, payload = _request_json(
        base,
        "/api/mrms/current",
        {
            "request_id": current_req,
            "product": args.product,
            "region": "CONUS",
            "frames": 1,
            "fps": 10,
            "show_places": "true",
            "user_tz": args.user_tz,
            "lookback": 0.25,
            "clock_skew_fallback": "true",
            "clock_skew_max_days": args.clock_skew_max_days,
        },
        timeout=args.timeout,
    )
    current_status = str(payload.get("status", "")).lower()
    current_ok = code == 200 and current_status in {
        "success", "error", "warning"}
    fallback_used = payload.get("clock_skew_fallback_used")
    fallback_days = payload.get("clock_skew_offset_days")
    record(
        "current_contract",
        current_ok,
        (
            f"http={code} status={current_status or 'missing'} "
            f"fallback_used={fallback_used} fallback_days={fallback_days} "
            f"message={payload.get('message')}"
        ),
    )

    # 3) Layered archive generation
    archive_req = _new_request_id("mrms-archive")
    code, payload = _request_json(
        base,
        "/api/mrms/archive",
        {
            "request_id": archive_req,
            "product": args.product,
            "date_from": archive_from,
            "date_to": archive_to,
            "region": "CONUS",
            "frames": 20,
            "fps": 8,
            "show_places": "true",
            "user_tz": args.user_tz,
            "view_mode": "layers",
        },
        timeout=args.timeout,
    )
    archive_ok = (
        code == 200
        and payload.get("status") == "success"
        and payload.get("output_mode") == "layers"
        and payload.get("layers_path")
        and int(payload.get("frame_count") or 0) >= 1
    )
    layers_path = str(payload.get("layers_path") or "")
    record(
        "archive_layers",
        archive_ok,
        (
            f"http={code} status={payload.get('status')} output_mode={payload.get('output_mode')} "
            f"frame_count={payload.get('frame_count')} layers_path={layers_path}"
        ),
    )

    # 4) Single-frame archive check
    single_req = _new_request_id("mrms-single")
    code_single, payload_single = _request_json(
        base,
        "/api/mrms/archive",
        {
            "request_id": single_req,
            "product": args.product,
            "date_from": archive_from,
            "date_to": archive_from,
            "region": "CONUS",
            "frames": 1,
            "fps": 8,
            "show_places": "true",
            "user_tz": args.user_tz,
            "view_mode": "layers",
        },
        timeout=args.timeout,
    )
    single_ok = (
        code_single == 200
        and payload_single.get("status") == "success"
        and payload_single.get("output_mode") == "layers"
        and int(payload_single.get("frame_count") or 0) == 1
    )
    record(
        "archive_single_frame",
        single_ok,
        (
            f"http={code_single} status={payload_single.get('status')} "
            f"frame_count={payload_single.get('frame_count')}"
        ),
    )

    # 5) Export from layered session
    if layers_path:
        code_export, payload_export = _request_json(
            base,
            "/api/mrms/archive/export-animation",
            {
                "layers_path": layers_path,
                "fps": 8,
            },
            timeout=args.timeout,
        )
        export_ok = (
            code_export == 200
            and payload_export.get("status") == "success"
            and payload_export.get("output_mode") == "video"
            and payload_export.get("image_url")
        )
        record(
            "archive_export",
            export_ok,
            (
                f"http={code_export} status={payload_export.get('status')} "
                f"output_mode={payload_export.get('output_mode')} image_url={payload_export.get('image_url')}"
            ),
        )
    else:
        record("archive_export", False,
               "layers_path missing from archive response")

    # 6) Custom extent + export
    custom_req = _new_request_id("mrms-custom")
    code_custom, payload_custom = _request_json(
        base,
        "/api/mrms/archive",
        {
            "request_id": custom_req,
            "product": args.product,
            "date_from": archive_from,
            "date_to": archive_to,
            "region": "CONUS",
            "n": 36,
            "s": 33,
            "e": -75,
            "w": -82,
            "frames": 20,
            "fps": 8,
            "show_places": "true",
            "user_tz": args.user_tz,
            "view_mode": "layers",
        },
        timeout=args.timeout,
    )
    custom_layers = str(payload_custom.get("layers_path") or "")
    custom_ok = (
        code_custom == 200
        and payload_custom.get("status") == "success"
        and payload_custom.get("output_mode") == "layers"
        and custom_layers
    )
    record(
        "archive_custom_extent",
        custom_ok,
        (
            f"http={code_custom} status={payload_custom.get('status')} "
            f"output_mode={payload_custom.get('output_mode')} layers_path={custom_layers}"
        ),
    )

    if custom_layers:
        code_custom_export, payload_custom_export = _request_json(
            base,
            "/api/mrms/archive/export-animation",
            {
                "layers_path": custom_layers,
                "fps": 8,
            },
            timeout=args.timeout,
        )
        custom_export_ok = (
            code_custom_export == 200
            and payload_custom_export.get("status") == "success"
            and payload_custom_export.get("output_mode") == "video"
            and payload_custom_export.get("image_url")
        )
        record(
            "archive_custom_export",
            custom_export_ok,
            (
                f"http={code_custom_export} status={payload_custom_export.get('status')} "
                f"output_mode={payload_custom_export.get('output_mode')} image_url={payload_custom_export.get('image_url')}"
            ),
        )
    else:
        record("archive_custom_export", False,
               "custom layers_path missing from response")

    # 7) Progress cleanup sanity: request should be idle after synchronous return
    progress_code, progress_payload = _request_json(
        base,
        f"/api/progress/{urllib.parse.quote(archive_req, safe='')}",
        timeout=max(20, min(args.timeout, 120)),
    )
    progress_ok = (
        progress_code == 200
        and str(progress_payload.get("stage", "")).lower() == "idle"
    )
    record(
        "progress_cleanup",
        progress_ok,
        f"http={progress_code} stage={progress_payload.get('stage')} percent={progress_payload.get('percent')}",
    )

    print(f"Archive test window (UTC): {archive_from} -> {archive_to}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MRMS API smoke checks.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--product", default="QPE_01H")
    parser.add_argument("--user-tz", default="America/New_York")
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--archive-from", default="")
    parser.add_argument("--archive-to", default="")
    parser.add_argument("--archive-days-back", type=int, default=365)
    parser.add_argument("--clock-skew-max-days", type=int, default=365)
    args = parser.parse_args()

    results = run_checks(args)

    print("\nMRMS Smoke Check Results")
    print("=" * 80)
    fail_count = 0
    for result in results:
        prefix = "PASS" if result.ok else "FAIL"
        if not result.ok:
            fail_count += 1
        print(f"[{prefix}] {result.name}: {result.details}")

    print("=" * 80)
    if fail_count:
        print(f"Summary: {fail_count} failing check(s) out of {len(results)}")
        return 1

    print(f"Summary: all {len(results)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
