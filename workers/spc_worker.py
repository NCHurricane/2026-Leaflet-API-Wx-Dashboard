"""Background worker: fetches SPC outlook GeoJSON and writes to cache/spc/."""

import json
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "spc"

# Convective hazards to pre-cache per outlook day
_CONVECTIVE_HAZARDS: dict[int, list[str]] = {
    1: ["cat", "torn", "wind", "hail"],
    2: ["cat", "torn", "wind", "hail"],
    3: ["cat", "prob"],
    **{d: ["cat"] for d in range(4, 9)},
}

_FIRE_HAZARDS = ["windrh", "dryt"]


def _write_cache(name: str, payload: dict, source: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not isinstance(payload, dict):
        payload = {}
    out = {
        "_source": source,
        "_updated": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    path = CACHE_DIR / f"{name}.geojson"
    path.write_text(json.dumps(out), encoding="utf-8")


def run_spc_worker() -> None:
    """Fetch all SPC convective + fire weather GeoJSON and write to cache/spc/."""
    from spc.spc_utils import fetch_outlook_geojson, fetch_fire_wx_geojson

    errors = 0

    for day, hazards in _CONVECTIVE_HAZARDS.items():
        for hazard in hazards:
            try:
                payload, source = fetch_outlook_geojson(day, hazard)
                _write_cache(f"{day}_{hazard}", payload, source)
            except Exception as exc:
                errors += 1
                print(f"[spc_worker] {day}_{hazard}: {exc}")

    for day in range(1, 9):
        for hazard in _FIRE_HAZARDS:
            try:
                payload, source = fetch_fire_wx_geojson(day, hazard)
                _write_cache(f"fire_{day}_{hazard}", payload, source)
            except Exception as exc:
                errors += 1
                print(f"[spc_worker] fire_{day}_{hazard}: {exc}")

    print(f"[spc_worker] SPC cache refresh complete ({errors} error(s))")
