"""Background worker: fetches SPC outlook GeoJSON and writes to cache/spc/."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "spc"

# Convective hazards to pre-cache per outlook day
_CONVECTIVE_HAZARDS: dict[int, list[str]] = {
    1: ["cat", "torn", "wind", "hail", "cigtorn", "cigwind", "cighail"],
    2: ["cat", "torn", "wind", "hail", "cigtorn", "cigwind", "cighail"],
    3: ["cat", "prob"],
    **{d: ["cat"] for d in range(4, 9)},
}

# Fire weather hazards: Days 1-2 use dryt/windrh, Days 3-8 use categorical/probabilistic
_FIRE_WX_HAZARDS_12 = ["windrh", "dryt"]
_FIRE_WX_HAZARDS_38 = ["drytcat", "drytprob", "windrhcat", "windrhprob"]


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
    from spc.spc_utils import (
        fetch_outlook_geojson,
        fetch_fire_wx_geojson,
    )

    start = time.time()
    errors = 0

    for day, hazards in _CONVECTIVE_HAZARDS.items():
        for hazard in hazards:
            try:
                payload, source = fetch_outlook_geojson(day, hazard)
                _write_cache(f"{day}_{hazard}", payload, source)
            except Exception as exc:
                errors += 1
                print(f"[spc_worker] {day}_{hazard}: {exc}")

    # Fire weather Days 1-2
    for day in range(1, 3):
        for hazard in _FIRE_WX_HAZARDS_12:
            try:
                payload, source = fetch_fire_wx_geojson(day, hazard)
                _write_cache(f"fire_{day}_{hazard}", payload, source)
            except Exception as exc:
                errors += 1
                print(f"[spc_worker] fire_{day}_{hazard}: {exc}")

    # Fire weather Days 3-8
    for day in range(3, 9):
        for hazard in _FIRE_WX_HAZARDS_38:
            try:
                payload, source = fetch_fire_wx_geojson(day, hazard)
                _write_cache(f"fire_{day}_{hazard}", payload, source)
            except Exception as exc:
                errors += 1
                print(f"[spc_worker] fire_{day}_{hazard}: {exc}")

    print(
        f"[spc_worker] SPC cache refresh complete in {time.time() - start:.2f}s "
        f"({errors} error(s))"
    )
