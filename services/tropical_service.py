"""Tropical cyclone current and archive services."""

from pathlib import Path
import json
import time as _time
from typing import Any

from fastapi import HTTPException

from app_core.paths import BASE_DIR

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
    """Read an archive cache file ignoring age."""
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


def get_tropical_summary_data(force: bool = False) -> dict:
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

    basin_dir = _TROPICAL_CACHE_DIR / "basins" / basin_key
    index_payload = _read_tropical_cache(
        basin_dir / "index.json", _TROPICAL_CACHE_TTL_SECONDS
    )
    gis_payload = _read_tropical_cache(
        basin_dir / "gis.json", _TROPICAL_CACHE_TTL_SECONDS
    )
    assets_payload = _read_tropical_cache(
        basin_dir / "assets.json", _TROPICAL_CACHE_TTL_SECONDS
    )
    gtwo_payload = _read_tropical_cache(
        basin_dir / "gtwo.json", _TROPICAL_CACHE_TTL_SECONDS
    )
    if index_payload is None or gis_payload is None or assets_payload is None:
        try:
            _run_tropical_worker_once(force=False)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Tropical basin feed refresh failed: {exc}",
            )
        index_payload = _read_tropical_cache(
            basin_dir / "index.json", 7 * 24 * 60 * 60
        )
        gis_payload = _read_tropical_cache(basin_dir / "gis.json", 7 * 24 * 60 * 60)
        assets_payload = _read_tropical_cache(
            basin_dir / "assets.json", 7 * 24 * 60 * 60
        )
        gtwo_payload = _read_tropical_cache(basin_dir / "gtwo.json", 7 * 24 * 60 * 60)

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
    }


def get_tropical_storm_data(storm_id: str) -> dict:
    """Return cached NHC products and parsed details for one storm."""
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
        from workers.tropical_archive_worker import get_advisory_payload

        payload = get_advisory_payload(sid, stp)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Advisory build failed: {exc}")
    if payload is None:
        raise HTTPException(
            status_code=404, detail=f"No archived advisory: {sid} #{stp}"
        )
    return payload
