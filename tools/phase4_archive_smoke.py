#!/usr/bin/env python3
"""Phase 4 archive API smoke checks.

Tests:
  /api/archive/alerts
  /api/archive/spc
  /api/archive/mrms
  /api/archive/result (for MRMS session)

Usage:
  python tools/phase4_archive_smoke.py
  python tools/phase4_archive_smoke.py --base http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"


def _get(
    base: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 45,
) -> Tuple[int, Dict[str, Any]]:
    query = urllib.parse.urlencode(params or {})
    url = f"{base.rstrip('/')}{path}"
    if query:
        url = f"{url}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            payload = json.loads(body) if body else {}
            if not isinstance(payload, dict):
                payload = {"raw": payload}
            return int(resp.status), payload
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            payload = json.loads(body) if body else {}
            if not isinstance(payload, dict):
                payload = {"raw": payload}
        except Exception:
            payload = {"raw": body}
        return int(exc.code), payload
    except urllib.error.URLError as exc:
        return 0, {"error": str(exc)}


def check(label: str, ok: bool, detail: str) -> bool:
    print(f"[{PASS if ok else FAIL}] {label}: {detail}")
    return ok


def _iso_minute(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Phase 4 archive smoke checks.")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--poll-seconds", type=int, default=150)
    args = parser.parse_args()

    base = args.base.rstrip("/")
    failures = 0

    # Basic health
    code, payload = _get(base, "/api/status", timeout=10)
    ok = code == 200 and "Weather System Online" in str(
        payload.get("status", ""))
    if not check("api_status", ok, f"http={code} status={payload.get('status')}"):
        failures += 1

    # Use recent windows likely to have data.
    now_utc = datetime.now(timezone.utc)
    alerts_from = now_utc - timedelta(hours=12)
    alerts_to = now_utc - timedelta(hours=6)

    # 1) Alerts archive
    code, payload = _get(
        base,
        "/api/archive/alerts",
        {
            "date_from": _iso_minute(alerts_from),
            "date_to": _iso_minute(alerts_to),
            "state": "NC",
        },
        timeout=60,
    )
    features = payload.get("features", [])
    ok = code == 200 and isinstance(features, list) and payload.get(
        "type") == "FeatureCollection"
    if not check("archive_alerts_contract", ok, f"http={code} features={len(features) if isinstance(features, list) else 'n/a'}"):
        failures += 1

    # 2) SPC archive (single date snapshot)
    spc_date = (now_utc - timedelta(days=1)).strftime("%Y-%m-%d")
    code, payload = _get(
        base,
        "/api/archive/spc",
        {"day": 1, "hazard": "cat", "date": spc_date},
        timeout=45,
    )
    spc_features = payload.get("features", [])
    ok = code == 200 and isinstance(
        spc_features, list) and payload.get("hazard") == "cat"
    if not check("archive_spc_contract", ok, f"http={code} date={spc_date} features={len(spc_features) if isinstance(spc_features, list) else 'n/a'}"):
        failures += 1

    # 3) MRMS archive request
    mrms_from = now_utc - timedelta(hours=6)
    mrms_to = now_utc - timedelta(hours=5)
    code, payload = _get(
        base,
        "/api/archive/mrms",
        {
            "product": "PrecipRate",
            "date_from": _iso_minute(mrms_from),
            "date_to": _iso_minute(mrms_to),
            "max_frames": 2,
            "south": 33,
            "west": -85,
            "north": 37,
            "east": -75,
        },
        timeout=90,
    )
    status = payload.get("status")
    session_id = payload.get("session_id")
    request_id = payload.get("request_id")
    ok = code == 200 and status in {
        "processing", "success"} and bool(session_id)
    if not check("archive_mrms_request", ok, f"http={code} status={status} session_id={session_id}"):
        failures += 1

    # 4) Poll progress/result if needed
    mrms_frames = payload.get("frames", []) if status == "success" else []
    if ok and status == "processing":
        deadline = time.time() + args.poll_seconds
        final_stage = None
        while time.time() < deadline:
            pcode, p = _get(
                base, f"/api/progress/{urllib.parse.quote(str(request_id or session_id))}", timeout=20)
            if pcode == 200:
                stage = p.get("stage")
                pct = p.get("percent")
                msg = p.get("message")
                print(f"       progress: {pct}% stage={stage} msg={msg}")
                final_stage = stage
                if stage in {"success", "error"} or int(pct or 0) >= 100:
                    break
            time.sleep(1.5)

        rcode, result = _get(base, "/api/archive/result",
                             {"session_id": session_id}, timeout=20)
        mrms_frames = result.get("frames", []) if isinstance(
            result.get("frames"), list) else []
        ok_result = rcode == 200 and result.get(
            "status") == "success" and len(mrms_frames) > 0
        if not check("archive_mrms_result", ok_result, f"http={rcode} stage={final_stage} frames={len(mrms_frames)} status={result.get('status')}"):
            failures += 1
    elif ok:
        # immediate cache hit path
        ok_cached = isinstance(mrms_frames, list) and len(mrms_frames) > 0
        if not check("archive_mrms_result", ok_cached, f"cached_frames={len(mrms_frames)}"):
            failures += 1

    total = 5
    passed = total - failures
    print("\n" + "=" * 60)
    print(f"Phase 4 archive smoke: {passed}/{total} passed" +
          (" — ALL PASS" if failures == 0 else f" — {failures} FAILING"))
    print("=" * 60)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
