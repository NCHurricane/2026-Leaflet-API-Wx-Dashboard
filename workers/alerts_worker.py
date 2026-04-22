"""Background worker: fetches national NWS alerts and writes to cache/alerts/national.geojson."""

import json
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "alerts"
CACHE_FILE = CACHE_DIR / "national.geojson"


def run_alerts_worker() -> None:
    """Fetch all active US alerts and write national.geojson to the cache."""
    try:
        from alerts.alerts_utils import fetch_active_alerts_with_source

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        features, source = fetch_active_alerts_with_source(state=None, source="nws")
        payload = {
            "type": "FeatureCollection",
            "_source": source,
            "_updated": datetime.now(timezone.utc).isoformat(),
            "features": features,
        }
        CACHE_FILE.write_text(json.dumps(payload), encoding="utf-8")
        print(f"[alerts_worker] Cached {len(features)} alerts from {source}")
    except Exception as exc:
        print(f"[alerts_worker] Error: {exc}")
