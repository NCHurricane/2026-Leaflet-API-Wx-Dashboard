#!/usr/bin/env python3
"""Phase 5 export API smoke checks.

Flow:
1) Build a small MRMS archive session
2) Export one HD frame via /api/export/frame
3) Export HD animation via /api/export/animation and poll progress/result

Usage:
  python tools/phase5_export_smoke.py
  python tools/phase5_export_smoke.py --base http://127.0.0.1:8010
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"


def _req(
    method: str,
    base: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 60,
) -> Tuple[int, Dict[str, Any]]:
    query = urllib.parse.urlencode(params or {})
    url = f"{base.rstrip('/')}{path}"
    if query:
        url = f"{url}?{query}"

    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url, data=data, method=method, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
            if not isinstance(payload, dict):
                payload = {"raw": payload}
            return int(resp.status), payload
    except urllib.error.HTTPError as exc:
        body_txt = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            payload = json.loads(body_txt) if body_txt else {}
            if not isinstance(payload, dict):
                payload = {"raw": payload}
        except Exception:
            payload = {"raw": body_txt}
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
        description="Run Phase 5 export smoke checks")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--poll-seconds", type=int, default=180)
    args = parser.parse_args()

    base = args.base.rstrip("/")
    failures = 0

    now = datetime.now(timezone.utc)
    date_from = _iso_minute(now - timedelta(hours=6))
    date_to = _iso_minute(now - timedelta(hours=5))

    # 1) Build archive session
    code, p = _req(
        "GET",
        base,
        "/api/archive/mrms",
        params={
            "product": "PrecipRate",
            "date_from": date_from,
            "date_to": date_to,
            "max_frames": 2,
            "south": 33,
            "west": -85,
            "north": 37,
            "east": -75,
        },
        timeout=90,
    )
    sid = p.get("session_id")
    rid = p.get("request_id")
    ok = code == 200 and p.get("status") in {
        "processing", "success"} and bool(sid)
    if not check("archive_mrms_start", ok, f"http={code} status={p.get('status')} session={sid}"):
        failures += 1

    # wait until archive ready
    if ok and p.get("status") == "processing":
        deadline = time.time() + args.poll_seconds
        while time.time() < deadline:
            c2, prog = _req(
                "GET", base, f"/api/progress/{urllib.parse.quote(str(rid or sid))}", timeout=20)
            if c2 == 200 and (prog.get("stage") in {"success", "error"} or int(prog.get("percent", 0)) >= 100):
                break
            time.sleep(1.5)

    code, p = _req("GET", base, "/api/archive/result",
                   params={"session_id": sid}, timeout=25)
    frames = p.get("frames", []) if isinstance(p.get("frames"), list) else []
    ok = code == 200 and p.get("status") == "success" and len(frames) > 0
    if not check("archive_mrms_ready", ok, f"http={code} status={p.get('status')} frames={len(frames)}"):
        failures += 1

    if not ok:
        print("\nArchive session did not complete; aborting export checks.")
        return 1

    # 2) Export single frame
    code, p = _req(
        "POST",
        base,
        "/api/export/frame",
        body={"session_id": sid, "frame_index": 0},
        timeout=60,
    )
    ok = code == 200 and p.get("status") == "success" and str(
        p.get("image_url", "")).startswith("/cache/")
    if not check("export_frame", ok, f"http={code} image_url={p.get('image_url')}"):
        failures += 1

    # 3) Export animation
    req_id = f"phase5_export_{int(time.time())}"
    code, p = _req(
        "POST",
        base,
        "/api/export/animation",
        body={
            "session_id": sid,
            "start_index": min(1, len(frames) - 1),
            "end_index": min(1, len(frames) - 1),
            "fps": 6,
            "request_id": req_id,
        },
        timeout=60,
    )
    ok = code == 200 and p.get("status") in {"processing", "success"}
    if not check("export_animation_start", ok, f"http={code} status={p.get('status')} request_id={p.get('request_id')}"):
        failures += 1

    if ok:
        deadline = time.time() + args.poll_seconds
        while time.time() < deadline:
            c2, prog = _req(
                "GET", base, f"/api/progress/{urllib.parse.quote(req_id)}", timeout=20)
            if c2 == 200:
                if prog.get("stage") in {"success", "error"} or int(prog.get("percent", 0)) >= 100:
                    break
            time.sleep(1.5)

        code, p = _req("GET", base, "/api/export/result",
                       params={"request_id": req_id}, timeout=30)
        ok = code == 200 and p.get("status") == "success" and str(
            p.get("video_url", "")).startswith("/cache/") and int(p.get("fps", 0)) == 6 and int(p.get("frame_count", 0)) == 1
        if not check("export_animation_result", ok, f"http={code} status={p.get('status')} video_url={p.get('video_url')}"):
            failures += 1

    total = 5
    passed = total - failures
    print("\n" + "=" * 60)
    print(f"Phase 5 export smoke: {passed}/{total} passed" +
          (" — ALL PASS" if failures == 0 else f" — {failures} FAILING"))
    print("=" * 60)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
