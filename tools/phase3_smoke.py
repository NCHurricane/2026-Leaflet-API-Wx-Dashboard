#!/usr/bin/env python3
"""Phase 3 (Leaflet/Worker) API smoke checks.

Tests:
  /api/status
  /api/data/alerts
  /api/data/spc
  /api/data/surface
  /api/mrms/set-product   (set-product GET)
  /api/data/mrms          (cold-cache download — may take 5-10s)

Usage:
    python tools/phase3_smoke.py
    python tools/phase3_smoke.py --base http://127.0.0.1:8000
    python tools/phase3_smoke.py --skip-mrms   # skip the S3 download test
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"


def _get(
    base: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
) -> Tuple[int, Dict[str, Any]]:
    query = urllib.parse.urlencode(params or {})
    url = f"{base.rstrip('/')}{path}"
    if query:
        url = f"{url}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            code = int(resp.status)
            payload = json.loads(body) if body else {}
            return code, payload if isinstance(payload, dict) else {"raw": payload}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            payload = json.loads(body) if body else {}
            if not isinstance(payload, dict):
                payload = {"raw": body}
        except Exception:
            payload = {"raw": body}
        return int(exc.code), payload
    except urllib.error.URLError as exc:
        return 0, {"error": str(exc)}


def check(label: str, ok: bool, detail: str) -> bool:
    tag = PASS if ok else FAIL
    print(f"[{tag}] {label}: {detail}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--skip-mrms", action="store_true",
                        help="Skip the MRMS S3 download test (can take 5-10s)")
    parser.add_argument("--mrms-product", default="PrecipRate")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    failures = 0

    # ── 1. API status ─────────────────────────────────────────────────────────
    code, p = _get(base, "/api/status", timeout=10)
    ok = code == 200 and "Weather System Online" in str(p.get("status", ""))
    if not check("api_status", ok, f"http={code} status={p.get('status')}"):
        failures += 1

    # ── 2. Alerts data endpoint ───────────────────────────────────────────────
    code, p = _get(base, "/api/data/alerts", timeout=15)
    features = p.get("features", [])
    ok = code == 200 and isinstance(features, list) and len(features) > 0
    if not check("data_alerts", ok, f"http={code} features={len(features)}"):
        failures += 1

    # ── 3. SPC data endpoint ──────────────────────────────────────────────────
    code, p = _get(base, "/api/data/spc",
                   {"hazard": "cat", "day": 1}, timeout=15)
    features = p.get("features", [])
    ok = code == 200 and isinstance(features, list) and len(features) > 0
    if not check("data_spc", ok, f"http={code} features={len(features)}"):
        failures += 1

    # ── 4. Surface data endpoint ──────────────────────────────────────────────
    code, p = _get(base, "/api/data/surface",
                   {"region": "NC", "product": "temperature"}, timeout=30)
    stations = p.get("stations", [])
    ok = code == 200 and len(stations) > 0
    if not check("data_surface", ok, f"http={code} stations={len(stations)}"):
        failures += 1
    if ok:
        s = stations[0]
        has_fields = all(k in s for k in (
            "id", "lat", "lon", "value", "color"))
        if not check("data_surface_fields", has_fields,
                     f"id={s.get('id')} lat={s.get('lat')} value={s.get('value')} color={s.get('color')}"):
            failures += 1

    # ── 5. MRMS set-product endpoint ──────────────────────────────────────────
    code, p = _get(base, "/api/mrms/set-product",
                   {"product": "PrecipRate"}, timeout=10)
    ok = code == 200 and p.get("active_product") == "PrecipRate"
    if not check("mrms_set_product", ok, f"http={code} active_product={p.get('active_product')}"):
        failures += 1

    # ── 5b. set-product 400 on bad product ────────────────────────────────────
    code, p = _get(base, "/api/mrms/set-product",
                   {"product": "INVALID_XYZ"}, timeout=10)
    ok = code == 400
    if not check("mrms_set_product_invalid", ok, f"http={code} (expected 400)"):
        failures += 1

    # ── 6. MRMS data endpoint ─────────────────────────────────────────────────
    if args.skip_mrms:
        print(f"[{SKIP}] data_mrms: skipped (--skip-mrms)")
        print(f"[{SKIP}] data_mrms_bounds: skipped")
    else:
        print(
            f"       data_mrms: downloading {args.mrms_product} from S3 (first call may take 5-15s)…")
        code, p = _get(base, "/api/data/mrms", {
            "product": args.mrms_product,
            "south": 33.0, "west": -85.0, "north": 37.0, "east": -75.0,
        }, timeout=120)
        required = ("image_url", "bounds", "product", "full_name",
                    "units", "vmin", "vmax", "timestamp")
        has_all = all(k in p for k in required)
        ok = code == 200 and has_all and str(
            p.get("image_url", "")).startswith("/cache/")
        detail = f"http={code} image_url={p.get('image_url')} product={p.get('product')}"
        if "error" in p and not ok:
            detail += f" error={p.get('error')}"
        if not check("data_mrms", ok, detail):
            failures += 1

        if ok:
            b = p.get("bounds", [])
            bounds_ok = isinstance(b, list) and len(b) == 4
            if not check("data_mrms_bounds", bounds_ok, f"bounds={b}"):
                failures += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    total = 7 if args.skip_mrms else 9
    passed = total - failures
    print(f"\n{'='*60}")
    print(f"Phase 3 smoke: {passed}/{total} passed" +
          (" — ALL PASS" if failures == 0 else f" — {failures} FAILING"))
    print(f"{'='*60}")
    return 1 if failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
