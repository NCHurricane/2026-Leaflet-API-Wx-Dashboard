import os as _os

import certifi as _certifi

# Python on macOS ships with no default CA bundle (ssl cafile=None), so plain
# urllib/pandas HTTPS fetches fail certificate verification. Point OpenSSL at
# certifi's bundle unless the environment already provides one. Must run
# before any module builds an SSL context.
_os.environ.setdefault("SSL_CERT_FILE", _certifi.where())
_os.environ.setdefault("REQUESTS_CA_BUNDLE", _certifi.where())

from datetime import datetime, timezone, timedelta
import json
from typing import Any, Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException
import uvicorn
import time as _time
import os
import threading
from pathlib import Path
from app_core.http import (
    error_payload,
    parse_utc_datetime,
)
from app_core.background_render import spawn_live_render_thread
from app_core.paths import BASE_DIR, CACHE_ROOT as _CACHE_ROOT, ensure_runtime_dirs
from app_core.runtime import initialize_runtime, shutdown_runtime
from app_core.static_assets import CacheStaticFiles
from routes.alerts import router as alerts_router
from routes.archive import router as archive_router
from routes.core import router as core_router
from routes.drought import router as drought_router
from routes.health import router as health_router
from routes.mrms import router as mrms_router
from routes.overlays import create_overlays_router
from routes.pages import router as pages_router
from routes.rtma import router as rtma_router
from routes.satellite_v2 import router as satellite_v2_router
from routes.spc import router as spc_router
from routes.surface import router as surface_router
from services.rtma_service import get_rtma_data

# --- IMPORT YOUR UTILITIES ---

# Defer directory creation and module initialization to startup handler
app = FastAPI(title="NCHurricane Weather API")
app.include_router(health_router)
app.include_router(pages_router)
app.include_router(core_router)
app.include_router(alerts_router)
app.include_router(spc_router)
app.include_router(drought_router)
app.include_router(satellite_v2_router)
app.include_router(surface_router)
app.include_router(mrms_router)
app.include_router(rtma_router)
app.include_router(create_overlays_router(rtma_bootstrap=get_rtma_data))
app.include_router(archive_router)


@app.on_event("startup")
def _run_startup_sequence():
    """Execute the complete startup sequence with initialization."""
    initialize_runtime()


@app.on_event("shutdown")
def _stop_background_workers():
    """Shut down background schedulers and live render pools on app exit."""
    shutdown_runtime()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sound files
app.mount("/sounds", StaticFiles(directory="sounds"), name="sounds")

# Cache directory — worker-written GeoJSON artifacts (gitignored)
ensure_runtime_dirs()
app.mount("/cache", CacheStaticFiles(directory=_CACHE_ROOT), name="cache")

app.mount("/css", StaticFiles(directory=os.path.join(BASE_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(BASE_DIR, "js")), name="js")
app.mount("/data", StaticFiles(directory=os.path.join(BASE_DIR, "data")), name="data")
app.mount("/img", StaticFiles(directory=os.path.join(BASE_DIR, "img")), name="img")
app.mount(
    "/fonts", StaticFiles(directory=os.path.join(BASE_DIR, "fonts")), name="fonts"
)

def parse_styles(style_str: Optional[str]):
    parsed_styles = {}
    if style_str:
        try:
            # Handle case where style_str might already be a dict
            if isinstance(style_str, dict):
                raw_styles = style_str
            else:
                raw_styles = json.loads(style_str)
            for k, v in raw_styles.items():
                try:
                    float_v = float(v)
                    parsed_styles[k] = int(float_v) if float_v.is_integer() else float_v
                except (ValueError, TypeError):
                    parsed_styles[k] = v
        except Exception as e:
            print(f"Warning: Could not parse styles: {e}")
            pass

    if "logo_user_size" in parsed_styles:
        try:
            logo_user_size = float(parsed_styles["logo_user_size"])
            if logo_user_size > 2:
                logo_user_size = logo_user_size / 100.0
            if logo_user_size <= 0:
                logo_user_size = 0.08
            parsed_styles["logo_user_size"] = logo_user_size
        except (TypeError, ValueError):
            parsed_styles["logo_user_size"] = 0.08

    return parsed_styles


def _parse_and_validate_styles(style_config: Optional[str]) -> dict:
    parsed_styles = parse_styles(style_config)
    if not isinstance(parsed_styles, dict):
        return {}
    return parsed_styles


def _resolve_extent(
    n: Optional[float], s: Optional[float], e: Optional[float], w: Optional[float]
) -> Optional[tuple]:
    if all(value is not None for value in [n, s, e, w]):
        return (s, n, w, e)
    return None


def infer_data_mode(date_from: Optional[str], date_to: Optional[str]) -> str:
    has_from = bool((date_from or "").strip())
    has_to = bool((date_to or "").strip())
    if has_from and has_to:
        return "archive"
    if not has_from and not has_to:
        return "recent"
    raise HTTPException(
        status_code=400,
        detail=error_payload(
            "Both date_from and date_to must be provided together.",
            code="missing_paired_date",
        ),
    )

def format_utc_for_legacy(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")


RADAR_SITE_ALIASES = {
    "KILM": "KLTX",
    "KRAH": "KRAX",
    "KRNK": "KFCX",
    "KABQ": "KABX",
    "KALY": "KENX",
    "KBOI": "KCBX",
    "KBOU": "KFTG",
    "KBTV": "KCXX",
    "KBYZ": "KBLX",
    "KCAR": "KCBW",
    "KCHS": "KCLX",
    "KCTP": "KCCX",
    "KEKA": "KBHX",
    "KFGF": "KMVX",
    "KFGZ": "KFSX",
    "KFWD": "KFWS",
    "KGID": "KUEX",
    "KGJT": "KGJX",
    "KHUN": "KHTX",
    "KJAN": "KDGX",
    "KKEY": "KBYX",
    "KLBF": "KLNX",
    "KLKN": "KLRX",
    "KLMK": "KLVX",
    "KLOX": "KVTX",
    "KLUB": "KLBB",
    "KMEG": "KNQA",
    "KMFL": "KAMX",
    "KMFR": "KMAX",
    "KMSO": "KMSX",
    "KMTR": "KMUX",
    "KOUN": "KTLX",
    "KPHI": "KDIX",
    "KPIH": "KSFX",
    "KPQR": "KRTX",
    "KPSR": "KIWA",
    "KPUB": "KPUX",
    "KREV": "KRGX",
    "KSEW": "KATX",
    "KSGX": "KNKX",
    "KSLC": "KMTX",
    "KSTO": "KDAX",
    "KTAE": "KTLH",
    "KTOP": "KTWX",
    "KTSA": "KINX",
    "KTWC": "KEMX",
    "KUNR": "KUDX",
    "KVEF": "KESX",
}


def normalize_radar_site_id(site: str) -> str:
    site_id = str(site or "").strip().upper()
    return RADAR_SITE_ALIASES.get(site_id, site_id)


def build_mrms_recent_windows(
    end_time_utc,
    lookback_hours: float,
    enable_clock_skew_fallback: bool = True,
    max_days_back: int = 365,
):
    """Build ordered MRMS recent windows with optional clock-skew fallback."""
    base_hours = max(0.25, float(lookback_hours or 0.25))
    max_back = max(0, int(max_days_back or 0))

    offsets = [0]
    if enable_clock_skew_fallback and max_back > 0:
        # Sparse offsets keep request count low while handling common skew ranges.
        for day_offset in (1, 2, 3, 7, 14, 30, 60, 120, 240, 365):
            if day_offset <= max_back:
                offsets.append(day_offset)

    windows = []
    seen_offsets = set()
    for day_offset in offsets:
        if day_offset in seen_offsets:
            continue
        seen_offsets.add(day_offset)
        candidate_end = end_time_utc - timedelta(days=day_offset)
        candidate_start = candidate_end - timedelta(hours=base_hours)
        windows.append(
            {
                "offset_days": day_offset,
                "start": candidate_start,
                "end": candidate_end,
            }
        )
    return windows


@app.get("/api/radar/sites")
def get_radar_sites():
    try:
        sites_path = os.path.join(BASE_DIR, "radar", "radar_sites.json")
        with open(sites_path, "r", encoding="utf-8") as fh:
            raw_sites = json.load(fh)

        if not isinstance(raw_sites, dict):
            raise ValueError("radar_sites.json is not a key/value object")

        sites = [
            {"label": label, "value": value}
            for label, value in raw_sites.items()
            if isinstance(label, str) and isinstance(value, str)
        ]
        sites.sort(key=lambda entry: entry["label"])

        return {
            "status": "success",
            "sites": sites,
            "count": len(sites),
        }
    except Exception as e:
        print(f"Radar sites endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/radar/site-locations")
def get_radar_site_locations():
    try:
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        valid_prefixes = ("K", "P")
        valid_extras = {"TJUA"}

        sites = []
        seen = set()
        for site_id, info in NEXRAD_LOCATIONS.items():
            if not (site_id.startswith(valid_prefixes) or site_id in valid_extras):
                continue

            normalized_id = normalize_radar_site_id(site_id)
            if normalized_id in seen:
                continue

            lat = info.get("lat")
            lon = info.get("lon")
            if lat is None or lon is None:
                continue

            seen.add(normalized_id)
            sites.append(
                {
                    "site": normalized_id,
                    "lat": float(lat),
                    "lon": float(lon),
                }
            )

        sites.sort(key=lambda entry: entry["site"])
        return {
            "status": "success",
            "sites": sites,
            "count": len(sites),
        }
    except Exception as e:
        print(f"Radar site locations endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _radar_live_catalog():
    from config.radar_config import LIVE_RADAR_PRODUCTS

    return dict(LIVE_RADAR_PRODUCTS)


def _radar_live_sites():
    from config.radar_config import LIVE_RADAR_SITES

    return [normalize_radar_site_id(site) for site in LIVE_RADAR_SITES]


_RADAR_LIVE_FALLBACK_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_RADAR_LIVE_FALLBACK_LOCKS_GUARD = threading.Lock()

# --- NWS Radar station operational status cache (5-minute TTL) ---
_NWS_RADAR_STATUS_CACHE: dict | None = None
_NWS_RADAR_STATUS_CACHE_TS: float = 0.0
_NWS_RADAR_STATUS_CACHE_LOCK = threading.Lock()
_NWS_RADAR_STATUS_TTL_SEC = 300


def _fetch_nws_radar_status() -> dict:
    """Fetch and cache radar station status from NWS API. Returns dict keyed by site ID."""
    import time
    import urllib.request as _ur

    global _NWS_RADAR_STATUS_CACHE, _NWS_RADAR_STATUS_CACHE_TS

    now = time.monotonic()
    with _NWS_RADAR_STATUS_CACHE_LOCK:
        if (
            _NWS_RADAR_STATUS_CACHE is not None
            and (now - _NWS_RADAR_STATUS_CACHE_TS) < _NWS_RADAR_STATUS_TTL_SEC
        ):
            return _NWS_RADAR_STATUS_CACHE

    try:
        req = _ur.Request(
            "https://api.weather.gov/radar/stations",
            headers={
                "User-Agent": "2026-Dashboard/1.0 (github.com/NCHurricane)",
                "Accept": "application/geo+json",
            },
        )
        with _ur.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        print(f"[radar status] NWS fetch failed: {exc}")
        with _NWS_RADAR_STATUS_CACHE_LOCK:
            return _NWS_RADAR_STATUS_CACHE or {}

    status_map: dict = {}
    features = raw.get("features", []) if isinstance(raw, dict) else []
    for feat in features:
        props = feat.get("properties", {}) if isinstance(feat, dict) else {}
        site_id = str(props.get("id") or "").strip().upper()
        if not site_id:
            continue
        rda = props.get("rda") or {}
        rda_props = rda.get("properties") or {}
        latency = props.get("latency") or {}
        status_map[site_id] = {
            "operabilityStatus": rda_props.get("operabilityStatus", ""),
            "status": rda_props.get("status", ""),
            "alarmSummary": rda_props.get("alarmSummary", ""),
            "volumeCoveragePattern": rda_props.get("volumeCoveragePattern", ""),
            "mode": rda_props.get("mode", ""),
            "rdaTimestamp": rda.get("timestamp", ""),
            "levelTwoLastReceived": latency.get("levelTwoLastReceivedTime", ""),
        }

    with _NWS_RADAR_STATUS_CACHE_LOCK:
        _NWS_RADAR_STATUS_CACHE = status_map
        _NWS_RADAR_STATUS_CACHE_TS = now
    return status_map


def _radar_live_site_supported(site: str) -> bool:
    try:
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        site_id = normalize_radar_site_id(site)
        info = NEXRAD_LOCATIONS.get(site_id)
        if not info:
            return False
        return info.get("lat") is not None and info.get("lon") is not None
    except Exception:
        return False


def _radar_live_product_supported(product_key: str) -> bool:
    return str(product_key or "").strip().upper() in _radar_live_catalog()


def _radar_live_fallback_lock(site: str, product_key: str) -> threading.Lock:
    key = (normalize_radar_site_id(site), str(product_key or "").strip().upper())
    with _RADAR_LIVE_FALLBACK_LOCKS_GUARD:
        lock = _RADAR_LIVE_FALLBACK_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _RADAR_LIVE_FALLBACK_LOCKS[key] = lock
        return lock


def _radar_live_render_on_demand(
    site: str,
    product_key: str,
    *,
    latest_only: bool = True,
    backfill_history: bool = True,
    newest_first: bool = False,
    max_render_frames: int | None = None,
) -> int:
    from workers.radar_live_worker import run_radar_live_site_product

    site_id = normalize_radar_site_id(site)
    product_id = str(product_key or "").strip().upper()

    # Render a synchronous on-demand pass.
    lock = _radar_live_fallback_lock(site_id, product_id)
    with lock:
        cached = int(
            run_radar_live_site_product(
                site_id,
                product_id,
                force=True,
                latest_only=latest_only,
                newest_first=newest_first,
                max_render_frames=max_render_frames,
            )
        )

    # Optional background back-fill so the scrubber can animate.
    if not backfill_history:
        return cached

    # Avoid kicking off expensive history work when latest probe found nothing.
    if cached <= 0:
        return cached

    if not latest_only and max_render_frames is None:
        return cached

    def _fill_history():
        try:
            lock = _radar_live_fallback_lock(site_id, product_id)
            with lock:
                run_radar_live_site_product(
                    site_id,
                    product_id,
                    force=True,
                    latest_only=False,
                )
        except Exception as exc:
            print(
                f"[radar_live] history back-fill failed {site_id}/{product_id}: {exc}"
            )

    threading.Thread(
        target=_fill_history, name=f"radar-history-{site_id}-{product_id}", daemon=True
    ).start()
    return cached


def _radar_live_render_in_background(site_id: str, product_key: str) -> bool:
    """Fill the live radar frame window in the background (deduped)."""
    return spawn_live_render_thread(
        ("radar_live", site_id, product_key),
        f"radar-{site_id}-{product_key}",
        lambda: _radar_live_render_on_demand(
            site_id, product_key, latest_only=False, backfill_history=False
        ),
    )


def _radar_live_is_configured(site: str, product_key: str) -> bool:
    return site in set(_radar_live_sites()) and product_key in _radar_live_catalog()


def _radar_live_latest_meta_dt(meta: dict | None) -> datetime | None:
    """Best-effort UTC datetime of a latest-frame meta dict, or None."""
    if not meta:
        return None

    dt = None
    ts = str(meta.get("timestamp") or "").strip()
    if ts:
        try:
            dt = parse_utc_datetime(ts)
        except Exception:
            dt = None

    if dt is None:
        frame_key = str(
            meta.get("frame_key") or meta.get("source_data_key") or ""
        ).strip()
        if frame_key:
            try:
                from cache.overlay_cache_utils import datetime_from_frame_key

                dt = datetime_from_frame_key(frame_key)
            except Exception:
                dt = None

    return dt


def _radar_live_filter_stale_latest_meta(
    meta: dict | None, *, max_age_hours: float
) -> dict | None:
    """Return latest-frame meta only when it is within the live lookback window."""
    dt = _radar_live_latest_meta_dt(meta)
    if dt is None:
        return None

    cutoff_dt = datetime.now(timezone.utc) - timedelta(
        hours=max(0.25, float(max_age_hours or 0.25))
    )
    return meta if dt >= cutoff_dt else None


_RADAR_COLORTABLE_PRODUCTS: dict[str, tuple[float, float]] = {
    "BR": (-30.0, 90.0),
    "BV": (-120.0, 120.0),
}

_TROPICAL_BASINS = {"AL": "Atlantic", "EP": "Eastern Pacific", "CP": "Central Pacific"}
_TROPICAL_PRODUCTS = {
    "TCP": "Public Advisory",
    "TCM": "Forecast Advisory",
    "TCD": "Forecast Discussion",
    "PWS": "Wind Speed Probabilities",
    "TCU": "Tropical Cyclone Update",
}
_TROPICAL_CACHE_DIR = Path(BASE_DIR) / "cache" / "tropical"
_TROPICAL_STORMS_CACHE = _TROPICAL_CACHE_DIR / "current_storms.json"
_TROPICAL_SUMMARY_CACHE = _TROPICAL_CACHE_DIR / "summary.json"
_TROPICAL_CACHE_TTL_SECONDS = 2 * 60 * 60

# Archive (HURDAT2) — immutable data, so cache-forever (no TTL).
_TROPICAL_ARCHIVE_DIR = _TROPICAL_CACHE_DIR / "archive"
_TROPICAL_ARCHIVE_CATALOG = _TROPICAL_ARCHIVE_DIR / "catalog" / "seasons.json"
_TROPICAL_ARCHIVE_STORMS_DIR = _TROPICAL_ARCHIVE_DIR / "storms"


def _run_tropical_worker_once(force: bool = False) -> None:
    from workers.tropical_worker import run_tropical_worker

    run_tropical_worker(force=force)


def _run_tropical_archive_worker_once(force: bool = False) -> None:
    from workers.tropical_archive_worker import run_archive_worker

    run_archive_worker(force=force)


def _read_tropical_archive_cache(path: Path) -> dict[str, Any] | None:
    """Read an archive cache file ignoring age — archive data never goes stale."""
    try:
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _read_tropical_cache(path: Path, max_age_seconds: int) -> dict[str, Any] | None:
    try:
        if not path.is_file():
            return None
        age = _time.time() - path.stat().st_mtime
        if age > max_age_seconds:
            return None
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _write_tropical_cache(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False)
        tmp.replace(path)
    except Exception as exc:
        print(f"[tropical] Cache write failed for {path}: {exc}")


def _fetch_json_url(url: str, timeout_seconds: int = 12) -> dict[str, Any]:
    import urllib.request as ur

    req = ur.Request(
        url,
        headers={
            "User-Agent": "NCHurricane Dashboard/2026 (+https://nchurricane.com)",
            "Accept": "application/json,text/xml;q=0.9,*/*;q=0.8",
        },
    )
    with ur.urlopen(req, timeout=timeout_seconds) as resp:
        raw = resp.read()
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("JSON payload was not an object")
    return decoded


def _fetch_text_url(url: str, timeout_seconds: int = 12) -> str:
    import urllib.request as ur

    req = ur.Request(
        url,
        headers={
            "User-Agent": "NCHurricane Dashboard/2026 (+https://nchurricane.com)",
            "Accept": "application/xml,text/xml,text/plain;q=0.9,*/*;q=0.8",
        },
    )
    with ur.urlopen(req, timeout=timeout_seconds) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _normalize_tropical_storms(payload: dict[str, Any]) -> list[dict[str, Any]]:
    active = payload.get("activeStorms")
    if not isinstance(active, list):
        active = payload.get("data", {}).get("activeStorms") if isinstance(payload.get("data"), dict) else []
    storms = []
    for storm in active if isinstance(active, list) else []:
        if not isinstance(storm, dict):
            continue
        storm_id = str(storm.get("id") or storm.get("stormId") or storm.get("atcfID") or "").upper()
        if len(storm_id) < 8:
            continue
        basin = storm_id[:2]
        if basin not in _TROPICAL_BASINS:
            continue
        merged = dict(storm)
        merged["id"] = storm_id
        merged["basin"] = basin
        merged["basinName"] = _TROPICAL_BASINS[basin]
        storms.append(merged)
    return storms


def _tropical_wallet(storm_id: str) -> int:
    return ((int(storm_id[2:4]) - 1) % 5) + 1


def _tropical_xml_basin_code(storm_id: str) -> str:
    basin = storm_id[:2]
    if basin == "AL":
        return "AT"
    return basin


def _extract_xml_item_text(xml_text: str) -> tuple[str, dict[str, str]]:
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return xml_text, {}

    item = root.find("./channel/item")
    channel = root.find("./channel")
    meta: dict[str, str] = {}
    if channel is not None:
        for key in ("title", "pubDate", "lastBuildDate"):
            val = channel.findtext(key)
            if val:
                meta[key] = val
    if item is not None:
        for key in ("title", "pubDate", "link", "guid"):
            val = item.findtext(key)
            if val:
                meta[key] = val
        desc = item.findtext("description") or ""
        return desc.strip(), meta
    return xml_text, meta


def _parse_tropical_coord(text: str, hemi: str) -> float | None:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return -value if hemi.upper() in {"S", "W"} else value


def _parse_tropical_advisory(text: str) -> dict[str, Any]:
    import re

    parsed: dict[str, Any] = {}
    summary = re.search(r"SUMMARY OF .*?INFORMATION\s*-+\s*(.*?)(?:\n\s*\n|WATCHES AND WARNINGS|DISCUSSION AND OUTLOOK)", text, re.I | re.S)
    block = summary.group(1) if summary else text

    loc = re.search(r"LOCATION\.*\s*([0-9.]+)([NS])\s+([0-9.]+)([EW])", block, re.I)
    if loc:
        parsed["location"] = {
            "lat": _parse_tropical_coord(loc.group(1), loc.group(2)),
            "lon": _parse_tropical_coord(loc.group(3), loc.group(4)),
            "latText": f"{loc.group(1)}{loc.group(2).upper()}",
            "lonText": f"{loc.group(3)}{loc.group(4).upper()}",
        }
    wind = re.search(r"MAXIMUM SUSTAINED WINDS\.*\s*([0-9]+)\s*MPH.*?([0-9]+)\s*KM/H", block, re.I)
    if wind:
        parsed["maxWindMph"] = int(wind.group(1))
        parsed["maxWindKph"] = int(wind.group(2))
    motion = re.search(r"PRESENT MOVEMENT\.*\s*(.*?)\s+AT\s+([0-9]+)\s*MPH.*?([0-9]+)\s*KM/H", block, re.I)
    if motion:
        parsed["motion"] = {
            "text": motion.group(1).strip(),
            "mph": int(motion.group(2)),
            "kph": int(motion.group(3)),
        }
    pressure = re.search(r"MINIMUM CENTRAL PRESSURE\.*\s*([0-9]+)\s*MB", block, re.I)
    if pressure:
        parsed["pressureMb"] = int(pressure.group(1))
    headline = re.findall(r"\.\.\.(.*?)\.\.\.", text)
    if headline:
        parsed["headline"] = " ".join(part.strip() for part in headline[:2] if part.strip())
    return parsed


def _parse_tropical_track(text: str) -> list[dict[str, Any]]:
    import re

    points: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = re.search(
            r"^(INIT|[0-9]{1,3}H)\s+([0-9]{2}/[0-9]{4}Z)\s+([0-9.]+)([NS])\s+([0-9.]+)([EW])\s+([0-9]+)\s+KT",
            line.strip(),
            re.I,
        )
        if not match:
            continue
        points.append(
            {
                "hour": match.group(1).upper(),
                "time": match.group(2),
                "lat": _parse_tropical_coord(match.group(3), match.group(4)),
                "lon": _parse_tropical_coord(match.group(5), match.group(6)),
                "windKt": int(match.group(7)),
            }
        )
    return [p for p in points if p["lat"] is not None and p["lon"] is not None]


def _tropical_product_url(storm_id: str, product: str) -> str:
    basin_code = _tropical_xml_basin_code(storm_id)
    wallet = _tropical_wallet(storm_id)
    return f"https://www.nhc.noaa.gov/xml/{product}{basin_code}{wallet}.xml"


def _fetch_tropical_products(storm_id: str) -> dict[str, Any]:
    products: dict[str, Any] = {}
    for code, label in _TROPICAL_PRODUCTS.items():
        url = _tropical_product_url(storm_id, code)
        try:
            xml_text = _fetch_text_url(url)
            content, meta = _extract_xml_item_text(xml_text)
            if not content:
                continue
            products[code] = {
                "code": code,
                "label": label,
                "url": url,
                "meta": meta,
                "text": content,
            }
        except Exception as exc:
            products[code] = {
                "code": code,
                "label": label,
                "url": url,
                "error": str(exc),
            }
    return products


@app.get("/api/tropical/storms")
def get_tropical_storms(basin: str = "WORLD", force: bool = False):
    """Return cached current NHC active storms for Atlantic, East Pac, and Central Pac."""
    basin_key = basin.strip().upper()
    if basin_key == "EASTERN_PACIFIC":
        basin_key = "EP"
    if basin_key == "CENTRAL_PACIFIC":
        basin_key = "CP"
    if basin_key == "ATLANTIC":
        basin_key = "AL"
    if basin_key not in {"WORLD", "AL", "EP", "CP"}:
        raise HTTPException(status_code=400, detail="Invalid tropical basin.")

    summary = None if force else _read_tropical_cache(
        _TROPICAL_SUMMARY_CACHE, _TROPICAL_CACHE_TTL_SECONDS
    )
    source = "worker-cache"
    if summary is None:
        try:
            _run_tropical_worker_once(force=force)
        except Exception as exc:
            fallback = _read_tropical_cache(_TROPICAL_SUMMARY_CACHE, 7 * 24 * 60 * 60)
            if fallback is None:
                raise HTTPException(
                    status_code=502,
                    detail=f"Tropical cache refresh failed: {exc}",
                )
            summary = fallback
            source = "stale-worker-cache"
        else:
            summary = _read_tropical_cache(
                _TROPICAL_SUMMARY_CACHE, 7 * 24 * 60 * 60
            )
            source = "worker-cache-refresh"

    if summary is None:
        raise HTTPException(status_code=503, detail="Tropical cache is not available.")

    storms = summary.get("storms") if isinstance(summary.get("storms"), list) else []
    if basin_key != "WORLD":
        storms = [storm for storm in storms if storm.get("basin") == basin_key]
    return {
        "status": "success",
        "source": source,
        "basin": basin_key,
        "updated": summary.get("updated"),
        "interval_minutes": summary.get("interval_minutes"),
        "storms": storms,
        "count": len(storms),
        "errors": summary.get("errors", []),
    }


@app.get("/api/tropical/summary")
def get_tropical_summary(force: bool = False):
    """Return the cached tropical worker summary."""
    summary = None if force else _read_tropical_cache(
        _TROPICAL_SUMMARY_CACHE, _TROPICAL_CACHE_TTL_SECONDS
    )
    if summary is None:
        try:
            _run_tropical_worker_once(force=force)
        except Exception as exc:
            fallback = _read_tropical_cache(_TROPICAL_SUMMARY_CACHE, 7 * 24 * 60 * 60)
            if fallback is None:
                raise HTTPException(
                    status_code=502,
                    detail=f"Tropical cache refresh failed: {exc}",
                )
            return fallback
        summary = _read_tropical_cache(_TROPICAL_SUMMARY_CACHE, 7 * 24 * 60 * 60)
    if summary is None:
        raise HTTPException(status_code=503, detail="Tropical cache is not available.")
    return summary


@app.get("/api/tropical/basin/{basin_id}/feeds")
def get_tropical_basin_feeds(basin_id: str):
    """Return cached normalized RSS/GIS feed data for one tropical basin."""
    basin_key = basin_id.strip().upper()
    if basin_key == "ATLANTIC":
        basin_key = "AL"
    elif basin_key == "EASTERN_PACIFIC":
        basin_key = "EP"
    elif basin_key == "CENTRAL_PACIFIC":
        basin_key = "CP"
    if basin_key not in _TROPICAL_BASINS:
        raise HTTPException(status_code=400, detail="Invalid tropical basin.")

    basin_dir = _TROPICAL_CACHE_DIR / "basins" / basin_key
    index_payload = _read_tropical_cache(basin_dir / "index.json", _TROPICAL_CACHE_TTL_SECONDS)
    gis_payload = _read_tropical_cache(basin_dir / "gis.json", _TROPICAL_CACHE_TTL_SECONDS)
    assets_payload = _read_tropical_cache(basin_dir / "assets.json", _TROPICAL_CACHE_TTL_SECONDS)
    gtwo_payload = _read_tropical_cache(basin_dir / "gtwo.json", _TROPICAL_CACHE_TTL_SECONDS)
    if index_payload is None or gis_payload is None or assets_payload is None:
        try:
            _run_tropical_worker_once(force=False)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Tropical basin feed refresh failed: {exc}",
            )
        index_payload = _read_tropical_cache(basin_dir / "index.json", 7 * 24 * 60 * 60)
        gis_payload = _read_tropical_cache(basin_dir / "gis.json", 7 * 24 * 60 * 60)
        assets_payload = _read_tropical_cache(basin_dir / "assets.json", 7 * 24 * 60 * 60)
        gtwo_payload = _read_tropical_cache(basin_dir / "gtwo.json", 7 * 24 * 60 * 60)

    if index_payload is None or gis_payload is None or assets_payload is None:
        raise HTTPException(status_code=404, detail=f"No cached tropical feeds for {basin_key}.")
    return {
        "status": "success",
        "basin": basin_key,
        "index": index_payload,
        "gis": gis_payload,
        "assets": assets_payload,
        "gtwo": gtwo_payload,
    }


@app.get("/api/tropical/storm/{storm_id}")
def get_tropical_storm(storm_id: str):
    """Return cached NHC text products and parsed advisory/track details for one storm."""
    import re

    sid = storm_id.strip().upper()
    if not re.fullmatch(r"(AL|EP|CP)[0-9]{2}[0-9]{4}", sid):
        raise HTTPException(status_code=400, detail="Invalid tropical storm id.")

    storm_cache = _TROPICAL_CACHE_DIR / "storms" / sid / "storm.json"
    payload = _read_tropical_cache(storm_cache, _TROPICAL_CACHE_TTL_SECONDS)
    if payload is None:
        try:
            _run_tropical_worker_once(force=False)
        except Exception as exc:
            fallback = _read_tropical_cache(storm_cache, 7 * 24 * 60 * 60)
            if fallback is None:
                raise HTTPException(
                    status_code=502,
                    detail=f"Tropical storm cache refresh failed: {exc}",
                )
            payload = fallback
        else:
            payload = _read_tropical_cache(storm_cache, 7 * 24 * 60 * 60)

    if payload is None:
        raise HTTPException(status_code=404, detail=f"No cached tropical storm: {sid}")
    return payload


@app.get("/api/tropical/archive/catalog")
def get_tropical_archive_catalog():
    """Return the HURDAT2 season catalog, lazily building it on first request."""
    payload = _read_tropical_archive_cache(_TROPICAL_ARCHIVE_CATALOG)
    if payload is None:
        try:
            _run_tropical_archive_worker_once(force=False)
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Tropical archive build failed: {exc}"
            )
        payload = _read_tropical_archive_cache(_TROPICAL_ARCHIVE_CATALOG)
    if payload is None:
        raise HTTPException(status_code=404, detail="Tropical archive catalog unavailable.")
    return payload


@app.get("/api/tropical/archive/storm/{atcf_id}")
def get_tropical_archive_storm(atcf_id: str):
    """Return one archived storm's best-track payload (build-on-demand, cache-forever)."""
    import re

    sid = atcf_id.strip().upper()
    if not re.fullmatch(r"(AL|EP|CP)[0-9]{2}[0-9]{4}", sid):
        raise HTTPException(status_code=400, detail="Invalid archive storm id.")

    storm_cache = _TROPICAL_ARCHIVE_STORMS_DIR / sid / "storm.json"
    payload = _read_tropical_archive_cache(storm_cache)
    if payload is None:
        try:
            _run_tropical_archive_worker_once(force=False)
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Tropical archive build failed: {exc}"
            )
        payload = _read_tropical_archive_cache(storm_cache)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"No archived storm: {sid}")

    # Phase B: lazily attach archived forecast GIS (cone/radii/WW from the peak
    # advisory) on first open. Best-effort — never fail the request over it.
    # Also re-enrich storms cached before the advisory index existed (no
    # "advisories" key) so the scrubber/mode-toggle gets its data.
    if not payload.get("gis_enriched") or "advisories" not in payload:
        try:
            from workers.tropical_archive_worker import enrich_storm_gis

            if enrich_storm_gis(sid):
                fresh = _read_tropical_archive_cache(storm_cache)
                if fresh is not None:
                    payload = fresh
        except Exception as exc:
            print(f"[tropical-archive] GIS enrichment failed for {sid}: {exc}")
    return payload


@app.get("/api/tropical/archive/storm/{atcf_id}/advisory/{step}")
def get_tropical_archive_advisory(atcf_id: str, step: str):
    """Return one archived advisory's payload (summary + products + GIS), cached forever."""
    import re

    sid = atcf_id.strip().upper()
    stp = step.strip().upper()
    if not re.fullmatch(r"(AL|EP|CP)[0-9]{2}[0-9]{4}", sid):
        raise HTTPException(status_code=400, detail="Invalid archive storm id.")
    if not re.fullmatch(r"[0-9]{1,3}[A-Z]?", stp):
        raise HTTPException(status_code=400, detail="Invalid advisory step.")

    try:
        from workers.tropical_archive_worker import get_advisory_payload

        payload = get_advisory_payload(sid, stp)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Advisory build failed: {exc}")
    if payload is None:
        raise HTTPException(status_code=404, detail=f"No archived advisory: {sid} #{stp}")
    return payload


@app.get("/api/radar/colortable")
def get_radar_colortable(product: str = "BR"):
    """Return the legend color entries for a radar product colortable."""
    product = product.upper()
    if product not in _RADAR_COLORTABLE_PRODUCTS:
        raise HTTPException(
            status_code=404,
            detail=f"No colortable for product '{product}'. Valid: {list(_RADAR_COLORTABLE_PRODUCTS)}",
        )
    vmin, vmax = _RADAR_COLORTABLE_PRODUCTS[product]
    try:
        from config.radar_colortable_utils import get_legend_json

        entries = get_legend_json(product, vmin, vmax)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"product": product, "vmin": vmin, "vmax": vmax, "entries": entries}


_RADAR_FRAME_LAYERS = {
    0: "nexrad-n0q-m20m",
    1: "nexrad-n0q-m15m",
    2: "nexrad-n0q-m10m",
    3: "nexrad-n0q-m05m",
    4: "nexrad-n0q",
}


@app.get("/api/radar/tiles/{z}/{x}/{y}")
def get_radar_alert_tiles(z: str, x: str, y: str, frame: int = 4):
    """Proxy IEM NEXRAD reflectivity tiles. frame 0=oldest (-20m), 4=current."""
    try:
        import urllib.request as ur
        layer = _RADAR_FRAME_LAYERS.get(frame, "nexrad-n0q")
        url = f"https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/{layer}/{z}/{x}/{y}.png"
        req = ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with ur.urlopen(req, timeout=10) as resp:
            data = resp.read()
            # Tile URLs carry a v={last-modified token} that changes whenever
            # IEM publishes new data, so for a given URL the content is fixed:
            # let the browser cache it hard instead of re-fetching every 120s.
            return Response(
                content=data,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=3600, immutable"},
            )
    except Exception as e:
        print(f"[radar tiles] Tile fetch error: {e}")
        raise HTTPException(status_code=404, detail="Tile not found")


@app.head("/api/radar/tiles/{z}/{x}/{y}")
def head_radar_alert_tiles(z: str, x: str, y: str):
    """HEAD request for IEM NEXRAD radar tiles."""
    return Response(media_type="image/png")


@app.get("/api/radar/tiles/freshness")
def get_radar_tiles_freshness():
    """Return Last-Modified header for current IEM nexrad-n0q tile (CONUS sample)."""
    try:
        import urllib.request as ur
        url = "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q/4/4/6.png"
        req = ur.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
        with ur.urlopen(req, timeout=8) as resp:
            return {"last_modified": resp.headers.get("Last-Modified", "")}
    except Exception as e:
        print(f"[radar tiles] Freshness check error: {e}")
        return {"last_modified": ""}


@app.get("/api/radar/status")
def get_radar_status():
    """Return NWS radar station operational status for all sites, cached 5 minutes."""
    try:
        status = _fetch_nws_radar_status()
        return {
            "status": "success",
            "stations": status,
            "count": len(status),
        }
    except Exception as exc:
        print(f"[radar status] Endpoint error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/radar/live/sites")
def get_radar_live_sites():
    """Return radar sites with configured live-cache flag for weather.html Radar tab."""
    try:
        configured = set(_radar_live_sites())
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        valid_prefixes = ("K", "P")
        valid_extras = {"TJUA"}

        sites = []
        seen = set()
        for site_id, info in NEXRAD_LOCATIONS.items():
            if not (site_id.startswith(valid_prefixes) or site_id in valid_extras):
                continue
            normalized_id = normalize_radar_site_id(site_id)
            if normalized_id in seen:
                continue
            lat = info.get("lat")
            lon = info.get("lon")
            if lat is None or lon is None:
                continue
            seen.add(normalized_id)
            sites.append(
                {
                    "site": normalized_id,
                    "lat": float(lat),
                    "lon": float(lon),
                    "configured": normalized_id in configured,
                }
            )

        sites.sort(key=lambda entry: (0 if entry["configured"] else 1, entry["site"]))
        return {
            "status": "success",
            "sites": sites,
            "configured_sites": sorted(configured),
            "products": _radar_live_catalog(),
            "count": len(sites),
        }
    except Exception as e:
        print(f"Radar live sites endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/radar/live/latest")
def get_radar_live_latest(
    site: str = "KMHX", product: str = "L3_N0B", force: bool = False
):
    """Return latest live radar frame from cache."""
    from cache.overlay_cache_utils import radar_read_latest_frame
    from config.radar_config import (
        LIVE_RADAR_LOOKBACK_HOURS,
        LIVE_RADAR_WORKER_INTERVAL_MIN,
    )

    site_id = normalize_radar_site_id(site)
    product_key = str(product or "L3_N0B").strip().upper()
    configured = _radar_live_is_configured(site_id, product_key)
    level_code = "L2" if product_key.startswith("L2_") else "L3"
    freshness_hours = max(0.25, float(LIVE_RADAR_LOOKBACK_HOURS or 3.0))

    if not _radar_live_product_supported(product_key):
        raise HTTPException(
            status_code=404,
            detail=f"Live radar product is not supported: {product_key}.",
        )
    if not _radar_live_site_supported(site_id):
        raise HTTPException(
            status_code=404,
            detail=f"Live radar site is not supported: {site_id}.",
        )

    meta = _radar_live_filter_stale_latest_meta(
        radar_read_latest_frame(_CACHE_ROOT, site_id, level_code, product_key),
        max_age_hours=freshness_hours,
    )
    fallback_cached = 0
    if force and meta:
        # The frontend sends force=1 on every poll for unconfigured sites. A
        # cached frame newer than the worker cadence means a forced re-render
        # cannot produce anything newer — skip the synchronous probe + render.
        meta_dt = _radar_live_latest_meta_dt(meta)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=float(LIVE_RADAR_WORKER_INTERVAL_MIN or 5) + 1.0
        )
        if meta_dt is not None and meta_dt >= recent_cutoff:
            force = False
    if force:
        try:
            fallback_cached = _radar_live_render_on_demand(
                site_id,
                product_key,
                latest_only=True,
                backfill_history=True,
            )
        except Exception as exc:
            print(
                f"[radar_live_fallback] forced latest {site_id}/{product_key} failed: "
                f"{type(exc).__name__}: {exc}"
            )
        meta = _radar_live_filter_stale_latest_meta(
            radar_read_latest_frame(_CACHE_ROOT, site_id, level_code, product_key),
            max_age_hours=freshness_hours,
        )

    if not meta:
        try:
            fallback_cached = _radar_live_render_on_demand(
                site_id,
                product_key,
                latest_only=True,
                backfill_history=True,
            )
        except Exception as exc:
            print(
                f"[radar_live_fallback] latest {site_id}/{product_key} failed: "
                f"{type(exc).__name__}: {exc}"
            )
        meta = _radar_live_filter_stale_latest_meta(
            radar_read_latest_frame(_CACHE_ROOT, site_id, level_code, product_key),
            max_age_hours=freshness_hours,
        )

    # Cold-start edge case: latest-only probe may miss while broader frame render succeeds.
    # Render the newest frame first so Current can paint immediately, then
    # continue full history in the background for scrubber readiness.
    if not meta:
        try:
            fallback_cached = max(
                fallback_cached,
                _radar_live_render_on_demand(
                    site_id,
                    product_key,
                    latest_only=False,
                    backfill_history=True,
                    newest_first=True,
                    max_render_frames=1,
                ),
            )
        except Exception as exc:
            print(
                f"[radar_live_fallback] full latest {site_id}/{product_key} failed: "
                f"{type(exc).__name__}: {exc}"
            )
        meta = _radar_live_filter_stale_latest_meta(
            radar_read_latest_frame(_CACHE_ROOT, site_id, level_code, product_key),
            max_age_hours=freshness_hours,
        )
    if not meta:
        raise HTTPException(
            status_code=404,
            detail="No live radar frame cached yet within lookback window.",
        )

    image_url = (meta.get("render") or {}).get("image_url")
    if not image_url:
        raise HTTPException(
            status_code=404, detail="Latest live radar image is missing."
        )

    return {
        "status": "success",
        "source": (
            "live_cache_forced"
            if force and fallback_cached > 0
            else "live_cache_fallback"
            if fallback_cached > 0
            else "live_cache"
        ),
        "history_filling": fallback_cached > 0,
        "configured": configured,
        "site": site_id,
        "product": product_key,
        "timestamp": meta.get("timestamp"),
        "source_data_key": meta.get("source_data_key", ""),
        "image_url": image_url,
        "bounds": meta.get("bounds"),
        "full_name": meta.get("full_name", product_key),
        "units": meta.get("units", ""),
    }


@app.get("/api/radar/live/frames")
def get_radar_live_frames(site: str = "KMHX", product: str = "L3_N0B", hours: int = 2):
    """Return live radar frames list for scrubber playback."""
    from cache.overlay_cache_utils import radar_list_frames

    site_id = normalize_radar_site_id(site)
    product_key = str(product or "L3_N0B").strip().upper()
    configured = _radar_live_is_configured(site_id, product_key)
    level_code = "L2" if product_key.startswith("L2_") else "L3"

    if not _radar_live_product_supported(product_key):
        raise HTTPException(
            status_code=404,
            detail=f"Live radar product is not supported: {product_key}.",
        )
    if not _radar_live_site_supported(site_id):
        raise HTTPException(
            status_code=404,
            detail=f"Live radar site is not supported: {site_id}.",
        )

    from config.cache_config import (
        OVERLAY_EMPTY_CACHE_SYNC_FRAMES,
        OVERLAY_STALE_SERVE_WINDOW_MIN,
    )

    def _within(frame_list, cutoff):
        out = []
        for frame in frame_list:
            ts = frame.get("timestamp")
            if ts:
                try:
                    dt = parse_utc_datetime(ts)
                except Exception:
                    dt = None
            else:
                dt = None
            if dt and dt < cutoff:
                continue
            out.append(frame)
        return out

    def _render_newest_sync():
        # Render just the newest frames synchronously so the first paint is
        # not blank; the rest of the window fills in the background.
        try:
            return _radar_live_render_on_demand(
                site_id,
                product_key,
                latest_only=False,
                backfill_history=False,
                newest_first=True,
                max_render_frames=OVERLAY_EMPTY_CACHE_SYNC_FRAMES,
            )
        except Exception as exc:
            print(
                f"[radar_live_fallback] frames {site_id}/{product_key} failed: "
                f"{type(exc).__name__}: {exc}"
            )
            return 0

    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours or 2)))
    frames = radar_list_frames(_CACHE_ROOT, site_id, level_code, product_key)
    fallback_cached = 0
    refreshing = False

    if not frames:
        fallback_cached = _render_newest_sync()
        frames = radar_list_frames(_CACHE_ROOT, site_id, level_code, product_key)
        if frames:
            refreshing = _radar_live_render_in_background(site_id, product_key)

    filtered = _within(frames, cutoff_dt) if frames else []

    if not filtered and frames:
        # Cache holds only stale frames (typical after a server restart):
        # serve any within the grace window immediately as scrubber fill-ins
        # and refresh in the background, instead of blocking this request on
        # a full-window synchronous render.
        grace_min = OVERLAY_STALE_SERVE_WINDOW_MIN.get("radar_live", 15)
        filtered = _within(frames, cutoff_dt - timedelta(minutes=grace_min))
        if filtered:
            refreshing = _radar_live_render_in_background(site_id, product_key)
        else:
            fallback_cached = max(fallback_cached, _render_newest_sync())
            frames = radar_list_frames(_CACHE_ROOT, site_id, level_code, product_key)
            filtered = _within(frames, cutoff_dt)
            if filtered:
                refreshing = _radar_live_render_in_background(site_id, product_key)

    return {
        "status": "success",
        "source": "live_cache_fallback" if fallback_cached > 0 else "live_cache",
        "configured": configured,
        "site": site_id,
        "product": product_key,
        "frame_count": len(filtered),
        "refreshing": refreshing,
        "frames": filtered,
    }

if __name__ == "__main__":
    # On Windows, Uvicorn's reload subprocess can intermittently emit
    # multiprocessing named-pipe errors during startup. Keep reload opt-in.
    use_reload = os.environ.get("WX_DASHBOARD_RELOAD", "0").strip() in {
        "1",
        "true",
        "yes",
        "on",
    }
    # Pass reload-related options ONLY when reload is enabled — otherwise
    # uvicorn warns "Current configuration will not reload as not all
    # conditions are met" because reload_includes/excludes are ignored.
    run_kwargs = {
        "host": "0.0.0.0",
        "port": 8000,
        "reload": use_reload,
        "timeout_graceful_shutdown": 5,
    }
    if use_reload:
        run_kwargs["reload_includes"] = ["*.py"]
        run_kwargs["reload_excludes"] = [
            "radar/*",
            "satellite/*",
            "surface/*",
            "alerts/*",
            "__pycache__/*",
        ]
    uvicorn.run("main:app", **run_kwargs)
