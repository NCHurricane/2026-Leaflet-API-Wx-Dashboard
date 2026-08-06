"""Tropical cyclone current and archive services."""

from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import threading
import time as _time
from typing import Any

from fastapi import HTTPException

from app_core.paths import BASE_DIR
from app_core.refresh_coordinator import Submission, get_refresh_coordinator
from config.refresh_schedules import (
    GTWO_SCHEDULE,
    TROPICAL_INTERMEDIATE_SCHEDULE,
    TROPICAL_ROUTINE_SCHEDULE,
)

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

_TROPICAL_ARCHIVE_DIR = _TROPICAL_CACHE_DIR / "archive"
_TROPICAL_ARCHIVE_CATALOG = _TROPICAL_ARCHIVE_DIR / "catalog" / "seasons.json"
_TROPICAL_ARCHIVE_STORMS_DIR = _TROPICAL_ARCHIVE_DIR / "storms"
_TROPICAL_ARCHIVE_WARM_PROVIDER = "tropical-archive-warm"
_TROPICAL_ARCHIVE_WARM_WINDOW = 5
_TROPICAL_ARCHIVE_WARM_LOCK = threading.RLock()
_TROPICAL_ARCHIVE_WARM_TARGETS: dict[str, dict[str, object]] = {}


def _run_tropical_worker_once(
    force: bool = False,
    scopes: set[str] | None = None,
) -> dict[str, Any]:
    from workers.tropical_worker import run_tropical_worker

    return run_tropical_worker(force=force, scopes=scopes)


def _run_tropical_archive_worker_once(force: bool = False) -> None:
    from workers.tropical_archive_worker import run_archive_worker

    run_archive_worker(force=force)


def _read_tropical_archive_cache(path: Path) -> dict[str, Any] | None:
    """Read an archive cache file ignoring age."""
    try:
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _read_tropical_cache(path: Path, max_age_seconds: float) -> dict[str, Any] | None:
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


def _read_tropical_cache_any_age(path: Path) -> dict[str, Any] | None:
    """Read the latest worker artifact without making a page request refresh it."""
    return _read_tropical_cache(path, float("inf"))


def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    raw = str(value)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
    return (
        parsed.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None
        else parsed.astimezone(timezone.utc)
    )


def _latest_timestamp(values: list[object]) -> datetime | None:
    parsed = [timestamp for value in values if (timestamp := _parse_timestamp(value))]
    return max(parsed) if parsed else None


def _tropical_scope_state(scope: str) -> tuple[datetime | None, datetime | None]:
    source_values: list[object] = []
    checked_values: list[object] = []
    if scope == "gtwo":
        for basin in _TROPICAL_BASINS:
            basin_dir = _TROPICAL_CACHE_DIR / "basins" / basin
            payload = _read_tropical_cache_any_age(basin_dir / "gtwo.json") or {}
            meta = _read_tropical_cache_any_age(basin_dir / "gtwo.kmz.meta.json") or {}
            source_values.append(payload.get("issued"))
            checked_values.extend((meta.get("checked_at"), meta.get("fetched_at")))
    else:
        summary = _read_tropical_cache_any_age(_TROPICAL_SUMMARY_CACHE) or {}
        for storm in summary.get("storms") or []:
            storm_id = str(storm.get("id") or "").upper()
            if not storm_id:
                continue
            storm_dir = _TROPICAL_CACHE_DIR / "storms" / storm_id
            payload = _read_tropical_cache_any_age(storm_dir / "storm.json") or {}
            meta = _read_tropical_cache_any_age(
                storm_dir / "products" / "TCP.xml.meta.json"
            ) or {}
            source_values.append(payload.get("updated"))
            checked_values.extend((meta.get("checked_at"), meta.get("fetched_at")))
        current_meta = _read_tropical_cache_any_age(
            _TROPICAL_STORMS_CACHE.with_suffix(".json.meta.json")
        ) or {}
        checked_values.extend(
            (current_meta.get("checked_at"), current_meta.get("fetched_at"))
        )
    return _latest_timestamp(source_values), _latest_timestamp(checked_values)


def _tropical_warnings_in_effect() -> bool:
    summary = _read_tropical_cache_any_age(_TROPICAL_SUMMARY_CACHE) or {}
    for storm in summary.get("storms") or []:
        storm_id = str(storm.get("id") or "").upper()
        payload = _read_tropical_cache_any_age(
            _TROPICAL_CACHE_DIR / "storms" / storm_id / "storm.json"
        ) or {}
        text = str(
            payload.get("products", {}).get("TCP", {}).get("text") or ""
        ).upper()
        if "WATCHES AND WARNINGS" in text and not any(
            marker in text
            for marker in (
                "THERE ARE NO COASTAL WATCHES OR WARNINGS",
                "NO COASTAL WATCHES OR WARNINGS ARE IN EFFECT",
            )
        ):
            return True
    return False


def _submit_tropical_scope(scope: str) -> Submission:
    return get_refresh_coordinator().submit(
        key=("tropical", scope),
        provider="nhc",
        function=lambda: _run_tropical_worker_once(scopes={scope}),
    )


def _maybe_schedule_tropical_refresh() -> dict[str, Submission]:
    """Apply boundary gates plus a ten-minute active-page special probe."""
    now = datetime.now(timezone.utc)
    coordinator = get_refresh_coordinator()
    submissions: dict[str, Submission] = {}
    for scope in ("advisories", "gtwo"):
        key = ("tropical", scope)
        coordinator.record_presence(key=key, provider="nhc")
        source_issued, last_checked = _tropical_scope_state(scope)
        schedule = GTWO_SCHEDULE if scope == "gtwo" else TROPICAL_ROUTINE_SCHEDULE
        due = schedule.refresh_due(
            now=now,
            source_issued_at=source_issued,
            last_checked_at=last_checked,
        )
        if scope == "advisories" and _tropical_warnings_in_effect():
            due = due or TROPICAL_INTERMEDIATE_SCHEDULE.refresh_due(
                now=now,
                source_issued_at=source_issued,
                last_checked_at=last_checked,
            )
        safety_due = (
            last_checked is None
            or (now - last_checked).total_seconds() >= 10 * 60
        )
        if due or safety_due:
            submissions[scope] = _submit_tropical_scope(scope)
    return submissions


def _tropical_refresh_metadata(
    submissions: dict[str, Submission],
) -> dict[str, object]:
    refreshing = any(
        submission.status in {"queued", "running"}
        for submission in submissions.values()
    )
    backed_off = any(
        submission.status == "backoff"
        for submission in submissions.values()
    )
    retry_values = [
        submission.retry_after_seconds
        for submission in submissions.values()
        if submission.retry_after_seconds is not None
    ]
    return {
        "cache_state": (
            "refreshing" if refreshing else "backoff" if backed_off else "current"
        ),
        "refreshing": refreshing,
        "retry_after_seconds": (
            min(retry_values)
            if retry_values
            else 2.0 if refreshing else None
        ),
    }


def _maybe_schedule_current_season_refresh(catalog: dict[str, Any]) -> None:
    """Refresh only mutable current-season b-decks while archive is present."""
    now = datetime.now(timezone.utc)
    current_year = str(now.year)
    seasons = catalog.get("seasons") or []
    has_current_season = any(
        str(item.get("year") if isinstance(item, dict) else item) == current_year
        for item in seasons
    )
    if not has_current_season:
        has_current_season = any(
            current_year in years
            for years in (catalog.get("basins") or {}).values()
            if isinstance(years, dict)
        )
    if not has_current_season:
        return
    coordinator = get_refresh_coordinator()
    key = ("tropical", "archive-current-season", current_year)
    coordinator.record_presence(key=key, provider="nhc")
    state = coordinator.describe(key) or {}
    last_success = _parse_timestamp(
        state.get("source_timestamp") or state.get("last_success_at")
    )
    if last_success and not GTWO_SCHEDULE.refresh_due(
        now=now,
        source_issued_at=last_success,
        last_checked_at=last_success,
    ):
        return

    def _refresh() -> dict[str, Any]:
        from workers.tropical_archive_worker import refresh_current_season

        refresh_current_season(now.year)
        return {"source_timestamp": datetime.now(timezone.utc).isoformat()}

    coordinator.submit(
        key=key,
        provider="nhc",
        function=_refresh,
    )


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
    from app_core.upstream_ledger import urlopen

    with urlopen(req, timeout=timeout_seconds) as resp:
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
    from app_core.upstream_ledger import urlopen

    with urlopen(req, timeout=timeout_seconds) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _normalize_tropical_storms(payload: dict[str, Any]) -> list[dict[str, Any]]:
    active = payload.get("activeStorms")
    if not isinstance(active, list):
        active = (
            payload.get("data", {}).get("activeStorms")
            if isinstance(payload.get("data"), dict)
            else []
        )
    storms = []
    for storm in active if isinstance(active, list) else []:
        if not isinstance(storm, dict):
            continue
        storm_id = str(
            storm.get("id") or storm.get("stormId") or storm.get("atcfID") or ""
        ).upper()
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


def _normalize_storm_graphic_urls(payload: dict[str, Any]) -> dict[str, Any]:
    """Upgrade retired standard-cone URLs in existing worker artifacts."""
    replacements = {
        "_3day_cone_no_line_and_wind.png": "_3day_cone_sm2.png",
        "_5day_cone_no_line_and_wind.png": "_5day_cone_sm2.png",
    }
    graphics = payload.get("graphics")
    if not isinstance(graphics, list):
        return payload
    normalized_graphics = []
    changed = False
    for graphic in graphics:
        if not isinstance(graphic, dict):
            normalized_graphics.append(graphic)
            continue
        url = str(graphic.get("url") or "")
        normalized_url = url
        for retired, current in replacements.items():
            normalized_url = normalized_url.replace(retired, current)
        changed = changed or normalized_url != url
        normalized_graphics.append(
            {**graphic, "url": normalized_url} if normalized_url != url else graphic
        )
    return {**payload, "graphics": normalized_graphics} if changed else payload


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
    summary = re.search(
        r"SUMMARY OF .*?INFORMATION\s*-+\s*(.*?)(?:\n\s*\n|WATCHES AND WARNINGS|DISCUSSION AND OUTLOOK)",
        text,
        re.I | re.S,
    )
    block = summary.group(1) if summary else text

    loc = re.search(r"LOCATION\.*\s*([0-9.]+)([NS])\s+([0-9.]+)([EW])", block, re.I)
    if loc:
        parsed["location"] = {
            "lat": _parse_tropical_coord(loc.group(1), loc.group(2)),
            "lon": _parse_tropical_coord(loc.group(3), loc.group(4)),
            "latText": f"{loc.group(1)}{loc.group(2).upper()}",
            "lonText": f"{loc.group(3)}{loc.group(4).upper()}",
        }
    wind = re.search(
        r"MAXIMUM SUSTAINED WINDS\.*\s*([0-9]+)\s*MPH.*?([0-9]+)\s*KM/H",
        block,
        re.I,
    )
    if wind:
        parsed["maxWindMph"] = int(wind.group(1))
        parsed["maxWindKph"] = int(wind.group(2))
    motion = re.search(
        r"PRESENT MOVEMENT\.*\s*(.*?)\s+AT\s+([0-9]+)\s*MPH.*?([0-9]+)\s*KM/H",
        block,
        re.I,
    )
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
        parsed["headline"] = " ".join(
            part.strip() for part in headline[:2] if part.strip()
        )
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


def get_tropical_storms_data(basin: str = "WORLD", force: bool = False) -> dict:
    """Return cached current NHC active storms."""
    basin_key = basin.strip().upper()
    if basin_key == "EASTERN_PACIFIC":
        basin_key = "EP"
    if basin_key == "CENTRAL_PACIFIC":
        basin_key = "CP"
    if basin_key == "ATLANTIC":
        basin_key = "AL"
    if basin_key not in {"WORLD", "AL", "EP", "CP"}:
        raise HTTPException(status_code=400, detail="Invalid tropical basin.")

    refresh_submissions = (
        {} if force else _maybe_schedule_tropical_refresh()
    )
    summary = None if force else _read_tropical_cache_any_age(_TROPICAL_SUMMARY_CACHE)
    source = "worker-cache"
    if summary is None:
        try:
            _run_tropical_worker_once(force=force)
        except Exception as exc:
            fallback = _read_tropical_cache_any_age(_TROPICAL_SUMMARY_CACHE)
            if fallback is None:
                raise HTTPException(
                    status_code=502,
                    detail=f"Tropical cache refresh failed: {exc}",
                )
            summary = fallback
            source = "stale-worker-cache"
        else:
            summary = _read_tropical_cache_any_age(_TROPICAL_SUMMARY_CACHE)
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
        **_tropical_refresh_metadata(refresh_submissions),
    }


def get_tropical_basin_feeds_data(basin_id: str) -> dict:
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

    refresh_submissions = _maybe_schedule_tropical_refresh()
    basin_dir = _TROPICAL_CACHE_DIR / "basins" / basin_key
    index_payload = _read_tropical_cache_any_age(basin_dir / "index.json")
    gis_payload = _read_tropical_cache_any_age(basin_dir / "gis.json")
    assets_payload = _read_tropical_cache_any_age(basin_dir / "assets.json")
    gtwo_payload = _read_tropical_cache_any_age(basin_dir / "gtwo.json")
    if index_payload is None or gis_payload is None or assets_payload is None:
        try:
            _run_tropical_worker_once(force=False, scopes={"advisories", "gtwo"})
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Tropical basin feed refresh failed: {exc}",
            )
        index_payload = _read_tropical_cache_any_age(basin_dir / "index.json")
        gis_payload = _read_tropical_cache_any_age(basin_dir / "gis.json")
        assets_payload = _read_tropical_cache_any_age(basin_dir / "assets.json")
        gtwo_payload = _read_tropical_cache_any_age(basin_dir / "gtwo.json")

    if index_payload is None or gis_payload is None or assets_payload is None:
        raise HTTPException(
            status_code=404, detail=f"No cached tropical feeds for {basin_key}."
        )
    return {
        "status": "success",
        "basin": basin_key,
        "index": index_payload,
        "gis": gis_payload,
        "assets": assets_payload,
        "gtwo": gtwo_payload,
        **_tropical_refresh_metadata(refresh_submissions),
    }


def get_tropical_storm_data(storm_id: str) -> dict:
    """Return cached NHC products and parsed details for one storm."""
    import re

    sid = storm_id.strip().upper()
    if not re.fullmatch(r"(AL|EP|CP)[0-9]{2}[0-9]{4}", sid):
        raise HTTPException(status_code=400, detail="Invalid tropical storm id.")

    _maybe_schedule_tropical_refresh()
    storm_cache = _TROPICAL_CACHE_DIR / "storms" / sid / "storm.json"
    payload = _read_tropical_cache_any_age(storm_cache)
    if payload is None:
        try:
            _run_tropical_worker_once(force=False, scopes={"advisories"})
        except Exception as exc:
            fallback = _read_tropical_cache_any_age(storm_cache)
            if fallback is None:
                raise HTTPException(
                    status_code=502,
                    detail=f"Tropical storm cache refresh failed: {exc}",
                )
            payload = fallback
        else:
            payload = _read_tropical_cache_any_age(storm_cache)

    if payload is None:
        raise HTTPException(status_code=404, detail=f"No cached tropical storm: {sid}")
    return _normalize_storm_graphic_urls(payload)


def get_tropical_archive_catalog_data() -> dict:
    """Return the HURDAT2 season catalog."""
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
        raise HTTPException(
            status_code=404, detail="Tropical archive catalog unavailable."
        )
    _maybe_schedule_current_season_refresh(payload)
    return payload


def get_tropical_archive_storm_data(atcf_id: str) -> dict:
    """Return one archived storm best-track payload."""
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


def get_tropical_archive_advisory_data(atcf_id: str, step: str) -> dict:
    """Return one archived advisory payload."""
    import re

    sid = atcf_id.strip().upper()
    stp = step.strip().upper()
    if not re.fullmatch(r"(AL|EP|CP)[0-9]{2}[0-9]{4}", sid):
        raise HTTPException(status_code=400, detail="Invalid archive storm id.")
    if not re.fullmatch(r"[0-9]{1,3}[A-Z]?", stp):
        raise HTTPException(status_code=400, detail="Invalid advisory step.")

    try:
        from workers.tropical_archive_worker import (
            get_advisory_payload,
            parse_archive_issued_iso,
        )

        advisory_cache = (
            _TROPICAL_ARCHIVE_STORMS_DIR / sid / "advisories" / f"{stp}.json"
        )
        if advisory_cache.is_file():
            payload = get_advisory_payload(sid, stp)
        else:
            with get_refresh_coordinator().provider_budget("nhc"):
                payload = get_advisory_payload(sid, stp)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Advisory build failed: {exc}")
    if payload is None:
        raise HTTPException(
            status_code=404, detail=f"No archived advisory: {sid} #{stp}"
        )
    if not payload.get("issued_at"):
        issued_at = parse_archive_issued_iso(payload.get("issued"))
        if issued_at:
            payload = {**payload, "issued_at": issued_at}
    return payload


def _tropical_archive_warm_key(sid: str) -> tuple[str, ...]:
    return ("tropical", "archive-advisory-warm", sid)


def _tropical_archive_advisory_steps(sid: str) -> list[str]:
    storm_cache = _TROPICAL_ARCHIVE_STORMS_DIR / sid / "storm.json"
    payload = _read_tropical_archive_cache(storm_cache)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"No archived storm: {sid}")
    return [
        str(step).strip().upper()
        for step in payload.get("advisories") or []
        if str(step).strip()
    ]


def _tropical_archive_window_steps(
    steps: list[str], anchor: str | None
) -> list[str]:
    if not steps:
        return []
    anchor_step = str(anchor or "").strip().upper()
    anchor_index = steps.index(anchor_step) if anchor_step in steps else 0
    indices: list[int] = []
    # Adjacent frames warm before the displayed anchor, avoiding duplicate cold
    # work with the foreground request that opens the selected storm.
    radius = 1
    while len(indices) < min(_TROPICAL_ARCHIVE_WARM_WINDOW - 1, len(steps) - 1):
        for offset in (radius, -radius):
            index = anchor_index + offset
            if 0 <= index < len(steps) and index not in indices:
                indices.append(index)
            if len(indices) >= min(
                _TROPICAL_ARCHIVE_WARM_WINDOW - 1, len(steps) - 1
            ):
                break
        radius += 1
    indices.append(anchor_index)
    return [steps[index] for index in indices]


def _tropical_archive_target_steps(
    steps: list[str], *, full: bool, anchor: str | None
) -> list[str]:
    window = _tropical_archive_window_steps(steps, anchor)
    if not full:
        return window
    return window + [step for step in steps if step not in window]


def _tropical_archive_advisory_is_cached(sid: str, step: str) -> bool:
    return (
        _TROPICAL_ARCHIVE_STORMS_DIR / sid / "advisories" / f"{step}.json"
    ).is_file()


def _tropical_archive_warm_status(sid: str) -> dict[str, object]:
    steps = _tropical_archive_advisory_steps(sid)
    with _TROPICAL_ARCHIVE_WARM_LOCK:
        target = dict(_TROPICAL_ARCHIVE_WARM_TARGETS.get(sid) or {})
    full = bool(target.get("full"))
    anchor = str(target.get("anchor") or (steps[0] if steps else ""))
    targets = _tropical_archive_target_steps(steps, full=full, anchor=anchor)
    cached = sum(
        1 for step in targets if _tropical_archive_advisory_is_cached(sid, step)
    )
    total = len(targets)
    state = get_refresh_coordinator().describe(_tropical_archive_warm_key(sid)) or {}
    complete = total == 0 or cached >= total
    status = "complete" if complete else str(state.get("status") or "idle")
    return {
        "status": status,
        "storm_id": sid,
        "mode": "full" if full else "window",
        "cached": cached,
        "total": total,
        "complete": complete,
        "retry_after_seconds": state.get("retry_after_seconds"),
        "error_type": state.get("error_type"),
    }


def _run_tropical_archive_warm(sid: str) -> dict[str, object]:
    from workers.tropical_archive_worker import get_advisory_payload

    coordinator = get_refresh_coordinator()
    while True:
        steps = _tropical_archive_advisory_steps(sid)
        with _TROPICAL_ARCHIVE_WARM_LOCK:
            target = dict(_TROPICAL_ARCHIVE_WARM_TARGETS.get(sid) or {})
        targets = _tropical_archive_target_steps(
            steps,
            full=bool(target.get("full")),
            anchor=str(target.get("anchor") or (steps[0] if steps else "")),
        )
        for step in targets:
            if _tropical_archive_advisory_is_cached(sid, step):
                continue
            with coordinator.provider_budget("nhc"):
                payload = get_advisory_payload(sid, step)
            if payload is None:
                raise RuntimeError(f"Archive advisory unavailable: {sid} #{step}")
            # Yield between frames so a foreground scrub request waiting on the
            # same provider budget can take the next slot.
            _time.sleep(0.1)

        with _TROPICAL_ARCHIVE_WARM_LOCK:
            upgraded_to_full = bool(
                (_TROPICAL_ARCHIVE_WARM_TARGETS.get(sid) or {}).get("full")
            )
        if upgraded_to_full and len(targets) < len(steps):
            continue
        status = _tropical_archive_warm_status(sid)
        return {
            **status,
            "source_timestamp": datetime.now(timezone.utc).isoformat(),
        }


def start_tropical_archive_warm_data(
    atcf_id: str,
    mode: str = "window",
    anchor: str | None = None,
) -> dict[str, object]:
    import re

    sid = atcf_id.strip().upper()
    requested_mode = str(mode or "window").strip().lower()
    if not re.fullmatch(r"(AL|EP|CP)[0-9]{2}[0-9]{4}", sid):
        raise HTTPException(status_code=400, detail="Invalid archive storm id.")
    if requested_mode not in {"window", "full"}:
        raise HTTPException(status_code=400, detail="Invalid archive warm mode.")
    steps = _tropical_archive_advisory_steps(sid)
    anchor_step = str(anchor or (steps[0] if steps else "")).strip().upper()
    if steps and anchor_step not in steps:
        raise HTTPException(status_code=400, detail="Invalid archive warm anchor.")

    with _TROPICAL_ARCHIVE_WARM_LOCK:
        target = _TROPICAL_ARCHIVE_WARM_TARGETS.setdefault(
            sid,
            {"full": False, "anchor": anchor_step},
        )
        target["anchor"] = anchor_step
        if requested_mode == "full":
            target["full"] = True

    status = _tropical_archive_warm_status(sid)
    if status["complete"]:
        return status
    coordinator = get_refresh_coordinator()
    submission = coordinator.submit(
        key=_tropical_archive_warm_key(sid),
        provider=_TROPICAL_ARCHIVE_WARM_PROVIDER,
        function=lambda: _run_tropical_archive_warm(sid),
        lease_seconds=15 * 60,
    )
    response = _tropical_archive_warm_status(sid)
    if submission.status not in {"queued", "running"} and not response["complete"]:
        response["status"] = submission.status
    return {
        **response,
        "accepted": submission.accepted,
        "submission_status": submission.status,
    }


def get_tropical_archive_warm_status_data(atcf_id: str) -> dict[str, object]:
    import re

    sid = atcf_id.strip().upper()
    if not re.fullmatch(r"(AL|EP|CP)[0-9]{2}[0-9]{4}", sid):
        raise HTTPException(status_code=400, detail="Invalid archive storm id.")
    return _tropical_archive_warm_status(sid)
