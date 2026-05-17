#!/usr/bin/env python3
"""Satellite v2 API contract smoke check.

Usage:
    python tools/satellite_v2_smoke.py
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from typing import Any


def _request_json(base_url: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=120) as response:
        body = response.read().decode("utf-8", errors="replace")
        return json.loads(body)


def _request_headers(base_url: str, path: str, params: dict[str, Any]) -> dict[str, str]:
    url = f"{base_url.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=120) as response:
        response.read(1)
        return {str(key): str(value) for key, value in response.headers.items()}


def run(base_url: str) -> int:
    status = _request_json(base_url, "/api/satellite-v2/status", {})
    if status.get("status") != "success":
        print(f"FAIL status: {status}")
        return 1

    catalog = _request_json(
        base_url,
        "/api/satellite-v2/catalog",
        {
            "sat_id": "goes19",
            "sector": "CONUS",
            "channel": "Channel13",
            "hours": 1,
            "max_frames": 12,
        },
    )
    frames = catalog.get("frames") or []
    if catalog.get("status") not in {"success", "stale"}:
        print(f"FAIL catalog status: {catalog.get('status')}")
        return 1
    if not isinstance(frames, list):
        print("FAIL catalog frames is not a list")
        return 1
    if frames and not all(frame.get("frame_key") for frame in frames):
        print("FAIL catalog contains frame without frame_key")
        return 1
    if "{frame_key}" not in str(catalog.get("tile_url_template") or ""):
        print("FAIL catalog tile_url_template is missing {frame_key}")
        return 1

    tile_checked = False
    if frames:
        frame = frames[-1]
        sample_tiles = frame.get("sample_tiles") or {}
        if sample_tiles:
            first_zoom = sorted(sample_tiles, key=lambda value: int(value))[0]
            sample = sample_tiles[first_zoom]
            headers = _request_headers(
                base_url,
                f"/api/satellite-v2/tile/{sample['z']}/{sample['x']}/{sample['y']}",
                {
                    "sat_id": "goes19",
                    "sector": "CONUS",
                    "channel": "Channel13",
                    "frame_key": frame["frame_key"],
                },
            )
            tile_checked = headers.get("X-Satellite-V2-Cache") == "HIT"

    print(
        json.dumps(
            {
                "ok": True,
                "status_catalogs": status.get("catalog_count"),
                "catalog_status": catalog.get("status"),
                "frame_count": len(frames),
                "catalog_source": catalog.get("catalog_source"),
                "tile_checked": tile_checked,
            },
            indent=2,
        )
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    raise SystemExit(run(args.base_url))


if __name__ == "__main__":
    main()
