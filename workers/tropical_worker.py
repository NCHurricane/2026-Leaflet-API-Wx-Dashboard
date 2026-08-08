"""Background worker for NHC tropical cyclone products.

Fetches NHC/CPHC active storm, RSS, GIS, and storm-wallet products into
cache/tropical so the browser and FastAPI routes never poll NHC directly.
"""

from __future__ import annotations

import logging

import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

# Add project root to path for both module and direct execution
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app_core.atomic_io import (  # noqa: E402
    atomic_write_bytes,
    atomic_write_text,
)
from app_core.upstream_ledger import urlopen  # noqa: E402
from tropical.product_data import (  # noqa: E402
    CACHE_DIR,
    FIVE_DAY_LAYER_KINDS as _FIVE_DAY_LAYER_KINDS,
    FORECAST_WIND_RADII_LAYER_KINDS as _FORECAST_WIND_RADII_LAYER_KINDS,
    _feature_collection,
    _kml_find,
    _kml_findtext,
    _kml_first_descendant,
    _kml_geometry,
    _kml_local,
    _utc_now_iso,
    _write_json_atomic,
    _xml_root,
    extract_gis_layers_from_zip as _extract_gis_layers_from_zip,
    parse_advisory as _parse_advisory,
    parse_initial_wind_extent_kml as _parse_initial_wind_extent_kml,
    parse_peak_surge_kml as _parse_peak_surge_kml,
    parse_storm_surge_kml as _parse_storm_surge_kml,
    parse_track as _parse_track,
)
from workers._freshness import is_cache_fresh, mark_run_complete  # noqa: E402

CURRENT_STORMS_FILE = CACHE_DIR / "current_storms.json"
SUMMARY_FILE = CACHE_DIR / "summary.json"

INTERVAL_MINUTES = 30
_FRESH_WINDOW_SEC = int(INTERVAL_MINUTES * 60 * 0.75)
_USER_AGENT = "NCHurricane Dashboard/2026 (+https://nchurricane.com)"

_CURRENT_STORMS_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"
_BASINS = {
    "AL": {
        "name": "Atlantic",
        "index_url": "https://www.nhc.noaa.gov/index-at.xml",
        "gis_url": "https://www.nhc.noaa.gov/gis-at.xml",
        "rss_suffix": "at",
        "xml_code": "AT",
        "graphics_code": "AT",
        "gtwo_url": "https://www.nhc.noaa.gov/xgtwo/gtwo_atl.kmz",
    },
    "EP": {
        "name": "Eastern Pacific",
        "index_url": "https://www.nhc.noaa.gov/index-ep.xml",
        "gis_url": "https://www.nhc.noaa.gov/gis-ep.xml",
        "rss_suffix": "ep",
        "xml_code": "EP",
        "graphics_code": "EP",
        "gtwo_url": "https://www.nhc.noaa.gov/xgtwo/gtwo_pac.kmz",
    },
    "CP": {
        "name": "Central Pacific",
        "index_url": "https://www.nhc.noaa.gov/index-cp.xml",
        "gis_url": "https://www.nhc.noaa.gov/gis-cp.xml",
        "rss_suffix": "cp",
        "xml_code": "CP",
        "graphics_code": "CP",
        "gtwo_url": "https://www.nhc.noaa.gov/xgtwo/gtwo_cpac.kmz",
    },
}

_STORM_PRODUCTS = {
    "TCP": "Public Advisory",
    "TCM": "Forecast Advisory",
    "TCD": "Forecast Discussion",
    "PWS": "Wind Speed Probabilities",
    "TCU": "Tropical Cyclone Update",
}

_CACHEABLE_GIS_EXTENSIONS = (".zip", ".kmz", ".kml", ".json", ".geojson")

# Best-track (observed history) archive zip — separate download from the 5-day forecast zip.
_BEST_TRACK_LAYER_KINDS = {
    "best_track_line": "_lin.shp",
    "best_track_points": "_pts.shp",
}

# Forecast wind radii (34/50/64 kt) — separate download from the 5-day forecast zip.
# The shapefile names include timestamps, so we use a wildcard suffix.

# Graphical Tropical Weather Outlook (GTWO) KMZ style ids → formation category.
_GTWO_STYLE_CATEGORY = {
    "0": "none",
    "1": "low",
    "2": "medium",
    "3": "high",
    "zerox": "none",
    "lowx": "low",
    "medx": "medium",
    "higx": "high",
}
_GTWO_CATEGORY_COLOR = {
    "none": "#9ca3af",
    "low": "#ffd400",
    "medium": "#ff8c00",
    "high": "#e60000",
}
# Point styleUrls that mark a genuine disturbance "X" (vs. off-season text labels,
# which are Points with an invisible inline style and no styleUrl).
_GTWO_MARKER_STYLES = {"zerox", "lowx", "medx", "higx"}








def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _request_url(
    url: str,
    cache_meta_path: Path | None = None,
    timeout_seconds: int = 20,
) -> tuple[bytes | None, dict[str, str], int]:
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json,application/xml,text/xml,text/plain,*/*;q=0.8",
    }
    previous_meta = _read_json(cache_meta_path) if cache_meta_path else None
    if previous_meta:
        etag = str(previous_meta.get("etag") or "").strip()
        last_modified = str(previous_meta.get("last_modified") or "").strip()
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

    req = urllib.request.Request(url, headers=headers)
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read()
            meta = {
                "url": url,
                "fetched_at": _utc_now_iso(),
                "etag": resp.headers.get("ETag", ""),
                "last_modified": resp.headers.get("Last-Modified", ""),
                "content_type": resp.headers.get("Content-Type", ""),
            }
            return body, meta, int(resp.status)
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            meta = dict(previous_meta or {})
            meta["checked_at"] = _utc_now_iso()
            return None, meta, 304
        raise


def _fetch_json(url: str, out_path: Path, force: bool) -> dict[str, Any] | None:
    meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")
    body, meta, status = _request_url(url, None if force else meta_path)
    if status == 304:
        _write_json_atomic(meta_path, meta)
        return _read_json(out_path)
    if body is None:
        return _read_json(out_path)
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON payload was not an object: {url}")
    _write_json_atomic(out_path, payload)
    _write_json_atomic(meta_path, meta)
    return payload


def _fetch_text(url: str, out_path: Path, force: bool) -> str:
    meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")
    body, meta, status = _request_url(url, None if force else meta_path)
    if status == 304:
        _write_json_atomic(meta_path, meta)
        try:
            return out_path.read_text(encoding="utf-8")
        except OSError:
            return ""
    if body is None:
        try:
            return out_path.read_text(encoding="utf-8")
        except OSError:
            return ""
    text = body.decode("utf-8", errors="replace")
    atomic_write_text(out_path, text)
    _write_json_atomic(meta_path, meta)
    return text


def _read_raw_text(raw_path: Path, out_path: Path) -> str:
    text = raw_path.read_text(encoding="utf-8")
    atomic_write_text(out_path, text)
    meta = {
        "url": str(raw_path),
        "fetched_at": _utc_now_iso(),
        "source": "local-test-raw",
    }
    _write_json_atomic(out_path.with_suffix(out_path.suffix + ".meta.json"), meta)
    return text


def _fetch_binary(url: str, out_path: Path, force: bool) -> bool:
    meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")
    body, meta, status = _request_url(url, None if force else meta_path, timeout_seconds=45)
    if status == 304:
        _write_json_atomic(meta_path, meta)
        return out_path.exists()
    if body is None:
        return out_path.exists()
    atomic_write_bytes(out_path, body)
    meta["bytes"] = str(len(body))
    _write_json_atomic(meta_path, meta)
    return True


def _strip_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()




def _xml_text(node: ET.Element | None, name: str) -> str:
    if node is None:
        return ""
    return (node.findtext(name) or "").strip()


def _parse_rss_feed(xml_text: str) -> dict[str, Any]:
    try:
        root = _xml_root(xml_text)
    except ET.ParseError as exc:
        return {"channel": {}, "items": [], "error": str(exc)}

    channel = root.find("./channel")
    channel_meta = {
        "title": _xml_text(channel, "title"),
        "description": _xml_text(channel, "description"),
        "link": _xml_text(channel, "link"),
        "pubDate": _xml_text(channel, "pubDate"),
        "lastBuildDate": _xml_text(channel, "lastBuildDate"),
    }
    items: list[dict[str, str]] = []
    for item in root.findall("./channel/item"):
        raw_description = _xml_text(item, "description")
        items.append(
            {
                "title": _xml_text(item, "title"),
                "description": _strip_html(raw_description),
                "description_html": raw_description,
                "pubDate": _xml_text(item, "pubDate"),
                "link": _xml_text(item, "link"),
                "guid": _xml_text(item, "guid"),
                "author": _xml_text(item, "author"),
            }
        )
    return {"channel": channel_meta, "items": items}


def _safe_asset_name(url: str) -> str:
    raw_name = url.rstrip("/").rsplit("/", 1)[-1] or "asset"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name)
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    stem, dot, suffix = name.partition(".")
    if dot:
        return f"{stem}_{digest}.{suffix}"
    return f"{name}_{digest}"


def _is_cacheable_gis_link(url: str) -> bool:
    clean = url.split("?", 1)[0].lower()
    return clean.endswith(_CACHEABLE_GIS_EXTENSIONS)


def _raw_basin_file(raw_dir: Path, basin_id: str, kind: str) -> Path:
    suffix = str(_BASINS[basin_id]["rss_suffix"])
    return raw_dir / "basins" / basin_id / f"{kind}-{suffix}.xml"


def _raw_storm_product_file(raw_dir: Path, storm: dict[str, Any], product: str) -> Path:
    storm_id = str(storm["id"]).upper()
    bin_number = str(storm.get("binNumber") or "").upper()
    if not bin_number:
        bin_number = f"{_BASINS[storm_id[:2]]['xml_code']}{_wallet(storm_id)}"
    return raw_dir / "storms" / storm_id / "products" / f"{product}{bin_number}.xml"


def _collect_raw_gis_assets(raw_dir: Path, storm_id: str) -> list[dict[str, str]]:
    asset_dir = raw_dir / "gis_assets" / storm_id.upper()
    if not asset_dir.is_dir():
        return []
    assets = []
    for path in sorted(asset_dir.iterdir()):
        if not path.is_file():
            continue
        assets.append(
            {
                "title": path.stem,
                "url": str(path),
                "cache_path": str(path.relative_to(raw_dir.parent)),
                "pubDate": "",
                "cached": "true",
                "source": "local-test-raw",
            }
        )
    return assets


















def _gtwo_formation_chances(text: str) -> tuple[int | None, int | None]:
    """Best-effort extraction of 2-day and 7-day formation percentages."""
    two = re.search(
        r"(?:48\s*hour|2\s*[- ]?day|two[- ]?day)[^%\d]{0,40}(\d{1,3})\s*(?:percent|%)",
        text,
        re.I,
    )
    seven = re.search(
        r"(?:7\s*day|seven[- ]?day|168\s*hour)[^%\d]{0,40}(\d{1,3})\s*(?:percent|%)",
        text,
        re.I,
    )
    two_pct = int(two.group(1)) if two else None
    seven_pct = int(seven.group(1)) if seven else None
    return two_pct, seven_pct


def _placemark_description(placemark: ET.Element) -> str:
    desc_el = _kml_find(placemark, "description")
    if desc_el is None:
        return ""
    return _strip_html("".join(desc_el.itertext()))


def _kml_extended_data(placemark: ET.Element) -> dict[str, str]:
    """Return ExtendedData <Data name=...><value>...</value> pairs as a dict."""
    ext = _kml_first_descendant(placemark, "ExtendedData")
    if ext is None:
        return {}
    data: dict[str, str] = {}
    for node in ext.iter():
        if _kml_local(node.tag) != "Data":
            continue
        key = node.get("name") or ""
        value_el = _kml_find(node, "value")
        if key and value_el is not None:
            data[key] = (value_el.text or "").strip()
    return data


def _gtwo_pct(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\d{1,3})", str(value))
    return int(match.group(1)) if match else None


def _parse_gtwo_kml(kml_text: str) -> dict[str, Any]:
    try:
        root = _xml_root(kml_text)
    except ET.ParseError as exc:
        return {
            "notExpected": False,
            "issued": "",
            "error": str(exc),
            "geojson": _feature_collection([]),
            "areas": [],
        }

    document = _kml_first_descendant(root, "Document")
    issued = _kml_findtext(document, "name")
    doc_desc_el = _kml_find(document, "description")
    doc_desc = _strip_html("".join(doc_desc_el.itertext())) if doc_desc_el is not None else ""

    features: list[dict[str, Any]] = []
    for placemark in (n for n in root.iter() if _kml_local(n.tag) == "Placemark"):
        geometry = _kml_geometry(placemark)
        if geometry is None:
            continue
        style_url = _kml_findtext(placemark, "styleUrl").lstrip("#")
        category = _GTWO_STYLE_CATEGORY.get(style_url, "")
        # Drop off-season text-label points (no marker styleUrl); keep genuine
        # disturbance "X" markers so point-only disturbances still render.
        if geometry["type"] == "Point" and style_url not in _GTWO_MARKER_STYLES:
            continue
        name = _kml_findtext(placemark, "name")
        description = _placemark_description(placemark)
        ext = _kml_extended_data(placemark)
        discussion = ext.get("Discussion", "").strip() or description
        two_pct = _gtwo_pct(ext.get("2day_percentage"))
        seven_pct = _gtwo_pct(ext.get("7day_percentage"))
        if two_pct is None and seven_pct is None:
            two_pct, seven_pct = _gtwo_formation_chances(f"{discussion} {name}")
        seven_cat = (ext.get("7day_category") or "").strip().lower()
        if category not in ("low", "medium", "high") and seven_cat in ("low", "medium", "high"):
            category = seven_cat
        disturbance = ext.get("Disturbance", "").strip()
        if not name:
            label = re.match(r"\s*\d+\.\s*(.+?):", discussion)
            if label:
                name = label.group(1).strip()[:90]
            elif disturbance:
                name = f"Disturbance {disturbance}"
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": name,
                    "disturbance": disturbance,
                    "category": category,
                    "color": _GTWO_CATEGORY_COLOR.get(category, "#9ca3af"),
                    "twoDayPct": two_pct,
                    "twoDayCategory": (ext.get("2day_category") or "").strip(),
                    "sevenDayPct": seven_pct,
                    "sevenDayCategory": (ext.get("7day_category") or "").strip(),
                    "discussion": discussion,
                    "styleUrl": style_url,
                },
                "geometry": geometry,
            }
        )

    def _area(feature: dict[str, Any]) -> dict[str, Any]:
        props = feature["properties"]
        return {
            "name": props["name"],
            "disturbance": props.get("disturbance", ""),
            "category": props["category"],
            "color": props["color"],
            "twoDayPct": props["twoDayPct"],
            "twoDayCategory": props.get("twoDayCategory", ""),
            "sevenDayPct": props["sevenDayPct"],
            "sevenDayCategory": props.get("sevenDayCategory", ""),
            "discussion": props["discussion"],
        }

    markers = [f for f in features if f["geometry"]["type"] == "Point"]
    polygons = [f for f in features if f["geometry"]["type"] == "Polygon"]
    areas = [_area(f) for f in (polygons or markers)]
    not_expected = "formation is not expected" in f"{doc_desc} {issued}".lower()

    return {
        "notExpected": not_expected and not areas,
        "issued": issued,
        "geojson": _feature_collection(features),
        "areas": areas,
    }


def _parse_gtwo_kmz(kmz_path: Path) -> dict[str, Any] | None:
    try:
        with zipfile.ZipFile(kmz_path) as zf:
            kml_name = next((n for n in zf.namelist() if n.lower().endswith(".kml")), "")
            if not kml_name:
                return None
            kml_bytes = zf.read(kml_name)
    except (OSError, KeyError, zipfile.BadZipFile):
        return None
    return _parse_gtwo_kml(kml_bytes.decode("utf-8", errors="replace"))






def _parse_initial_wind_extent_kmz(kmz_path: Path) -> dict[str, Any] | None:
    try:
        with zipfile.ZipFile(kmz_path) as zf:
            kml_name = next(
                (n for n in zf.namelist() if n.lower().endswith(".kml")), ""
            )
            if not kml_name:
                return None
            kml_bytes = zf.read(kml_name)
    except (OSError, KeyError, zipfile.BadZipFile):
        return None
    return _parse_initial_wind_extent_kml(kml_bytes.decode("utf-8", errors="replace"))


def _initial_wind_extent_kmz_url(storm: dict[str, Any]) -> str:
    value = storm.get("initialWindExtent")
    return str(value.get("kmzFile") or "").strip() if isinstance(value, dict) else ""


def _cache_live_initial_wind_extent_kmz(storm: dict[str, Any], storm_dir: Path, force: bool) -> Path | None:
    url = _initial_wind_extent_kmz_url(storm)
    if not url:
        return None
    path = storm_dir / "gis_assets" / _safe_asset_name(url)
    try:
        return path if _fetch_binary(url, path, force) else None
    except (OSError, urllib.error.URLError, ValueError):
        return None


def _raw_initial_wind_extent_kmz(raw_dir: Path, storm_id: str) -> Path | None:
    asset_dir = raw_dir / "gis_assets" / storm_id.upper()
    if not asset_dir.is_dir():
        return None
    candidates = sorted(asset_dir.glob("*initialradii*.kmz"))
    return candidates[0] if candidates else None


def _raw_five_day_zip(raw_dir: Path, storm_id: str) -> Path | None:
    asset_dir = raw_dir / "gis_assets" / storm_id.upper()
    if not asset_dir.is_dir():
        return None
    candidates = sorted(asset_dir.glob("*_5day_latest.zip"))
    return candidates[0] if candidates else None


def _storm_gis_zip_url(storm: dict[str, Any]) -> str:
    for key in ("forecastTrack", "trackCone"):
        value = storm.get(key)
        if isinstance(value, dict):
            url = str(value.get("zipFile") or "").strip()
            if url:
                return url
    return ""


def _cache_live_five_day_zip(storm: dict[str, Any], storm_dir: Path, force: bool) -> Path | None:
    url = _storm_gis_zip_url(storm)
    if not url:
        return None
    path = storm_dir / "gis_assets" / _safe_asset_name(url)
    try:
        return path if _fetch_binary(url, path, force) else None
    except (OSError, urllib.error.URLError, ValueError):
        return None


def _best_track_zip_url(storm: dict[str, Any]) -> str:
    value = storm.get("bestTrackGIS")
    return str(value.get("zipFile") or "").strip() if isinstance(value, dict) else ""


def _cache_live_best_track_zip(storm: dict[str, Any], storm_dir: Path, force: bool) -> Path | None:
    url = _best_track_zip_url(storm)
    if not url:
        return None
    path = storm_dir / "gis_assets" / _safe_asset_name(url)
    try:
        return path if _fetch_binary(url, path, force) else None
    except (OSError, urllib.error.URLError, ValueError):
        return None


def _raw_best_track_zip(raw_dir: Path, storm_id: str) -> Path | None:
    asset_dir = raw_dir / "gis_assets" / storm_id.upper()
    if not asset_dir.is_dir():
        return None
    candidates = sorted(asset_dir.glob("*best_track*.zip"))
    return candidates[0] if candidates else None


def _forecast_wind_radii_zip_url(storm: dict[str, Any]) -> str:
    value = storm.get("forecastWindRadiiGIS")
    return str(value.get("zipFile") or "").strip() if isinstance(value, dict) else ""


def _cache_live_forecast_wind_radii_zip(storm: dict[str, Any], storm_dir: Path, force: bool) -> Path | None:
    url = _forecast_wind_radii_zip_url(storm)
    if not url:
        return None
    path = storm_dir / "gis_assets" / _safe_asset_name(url)
    try:
        return path if _fetch_binary(url, path, force) else None
    except (OSError, urllib.error.URLError, ValueError):
        return None


def _raw_forecast_wind_radii_zip(raw_dir: Path, storm_id: str) -> Path | None:
    asset_dir = raw_dir / "gis_assets" / storm_id.upper()
    if not asset_dir.is_dir():
        return None
    candidates = sorted(asset_dir.glob("*fcst*.zip"))
    return candidates[0] if candidates else None


def _storm_surge_kml_url(storm: dict[str, Any]) -> str:
    value = storm.get("stormSurgeWatchWarningGIS")
    return str(value.get("kmlFile") or "").strip() if isinstance(value, dict) else ""


def _cache_live_storm_surge_kml(storm: dict[str, Any], storm_dir: Path, force: bool) -> Path | None:
    url = _storm_surge_kml_url(storm)
    if not url:
        return None
    path = storm_dir / "gis_assets" / _safe_asset_name(url)
    try:
        return path if _fetch_binary(url, path, force) else None
    except (OSError, urllib.error.URLError, ValueError):
        return None


def _raw_storm_surge_kml(raw_dir: Path, storm_id: str) -> Path | None:
    asset_dir = raw_dir / "gis_assets" / storm_id.upper()
    if not asset_dir.is_dir():
        return None
    candidates = sorted(asset_dir.glob("*SS*.kml"))
    return candidates[0] if candidates else None


def _peak_surge_kml_url(storm: dict[str, Any]) -> str:
    value = storm.get("peakSurgeKML")
    return str(value.get("peakSurgeKMLFile") or "").strip() if isinstance(value, dict) else ""


def _cache_live_peak_surge_kml(storm: dict[str, Any], storm_dir: Path, force: bool) -> Path | None:
    url = _peak_surge_kml_url(storm)
    if not url:
        return None
    path = storm_dir / "gis_assets" / _safe_asset_name(url)
    try:
        return path if _fetch_binary(url, path, force) else None
    except (OSError, urllib.error.URLError, ValueError):
        return None


def _raw_peak_surge_kml(raw_dir: Path, storm_id: str) -> Path | None:
    asset_dir = raw_dir / "gis_assets" / storm_id.upper()
    if not asset_dir.is_dir():
        return None
    candidates = sorted(asset_dir.glob("*PeakStormSurge*.kml"))
    return candidates[0] if candidates else None




def _build_storm_gis_layers(
    storm: dict[str, Any],
    storm_dir: Path,
    force: bool,
    raw_dir: Path | None,
) -> dict[str, Any]:
    storm_id = str(storm["id"]).upper()
    layer_dir = storm_dir / "gis"
    layers: dict[str, Any] = {}

    five_day = _raw_five_day_zip(raw_dir, storm_id) if raw_dir else _cache_live_five_day_zip(storm, storm_dir, force)
    if five_day:
        layers.update(_extract_gis_layers_from_zip(five_day, _FIVE_DAY_LAYER_KINDS, storm_id, layer_dir))

    best_track = _raw_best_track_zip(raw_dir, storm_id) if raw_dir else _cache_live_best_track_zip(storm, storm_dir, force)
    if best_track:
        layers.update(_extract_gis_layers_from_zip(best_track, _BEST_TRACK_LAYER_KINDS, storm_id, layer_dir))

    wind_radii = _raw_forecast_wind_radii_zip(raw_dir, storm_id) if raw_dir else _cache_live_forecast_wind_radii_zip(storm, storm_dir, force)
    if wind_radii:
        layers.update(_extract_gis_layers_from_zip(wind_radii, _FORECAST_WIND_RADII_LAYER_KINDS, storm_id, layer_dir))

    storm_surge_kml = _raw_storm_surge_kml(raw_dir, storm_id) if raw_dir else _cache_live_storm_surge_kml(storm, storm_dir, force)
    if storm_surge_kml:
        try:
            kml_text = storm_surge_kml.read_text(encoding="utf-8", errors="replace")
            collection = _parse_storm_surge_kml(kml_text)
            if collection:
                out_path = layer_dir / "storm_surge.geojson"
                payload = {
                    "updated": _utc_now_iso(),
                    "stormId": storm_id,
                    "layer": "storm_surge",
                    "source_path": str(storm_surge_kml),
                    "geojson": collection,
                }
                _write_json_atomic(out_path, payload)
                layers["storm_surge"] = {
                    "cache_path": str(out_path.relative_to(CACHE_DIR.parent)),
                    "feature_count": len(collection.get("features", [])),
                    "source_path": str(storm_surge_kml),
                    "geojson": collection,
                }
        except (OSError, ValueError):
            pass

    peak_surge_kml = _raw_peak_surge_kml(raw_dir, storm_id) if raw_dir else _cache_live_peak_surge_kml(storm, storm_dir, force)
    if peak_surge_kml:
        try:
            kml_text = peak_surge_kml.read_text(encoding="utf-8", errors="replace")
            collection = _parse_peak_surge_kml(kml_text)
            if collection:
                out_path = layer_dir / "peak_surge.geojson"
                payload = {
                    "updated": _utc_now_iso(),
                    "stormId": storm_id,
                    "layer": "peak_surge",
                    "source_path": str(peak_surge_kml),
                    "geojson": collection,
                }
                _write_json_atomic(out_path, payload)
                layers["peak_surge"] = {
                    "cache_path": str(out_path.relative_to(CACHE_DIR.parent)),
                    "feature_count": len(collection.get("features", [])),
                    "source_path": str(peak_surge_kml),
                    "geojson": collection,
                }
        except (OSError, ValueError):
            pass

    initial_wind = (
        _raw_initial_wind_extent_kmz(raw_dir, storm_id)
        if raw_dir
        else _cache_live_initial_wind_extent_kmz(storm, storm_dir, force)
    )
    if initial_wind:
        try:
            collection = _parse_initial_wind_extent_kmz(initial_wind)
            if collection:
                out_path = layer_dir / "initial_wind_extent.geojson"
                payload = {
                    "updated": _utc_now_iso(),
                    "stormId": storm_id,
                    "layer": "initial_wind_extent",
                    "source_path": str(initial_wind),
                    "geojson": collection,
                }
                _write_json_atomic(out_path, payload)
                layers["initial_wind_extent"] = {
                    "cache_path": str(out_path.relative_to(CACHE_DIR.parent)),
                    "feature_count": len(collection.get("features", [])),
                    "source_path": str(initial_wind),
                    "geojson": collection,
                }
        except (OSError, ValueError):
            pass

    return layers


def _cache_gis_assets(
    basin_id: str,
    items: list[dict[str, str]],
    force: bool,
) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []
    asset_dir = CACHE_DIR / "basins" / basin_id / "assets"
    for item in items:
        url = str(item.get("link") or "").strip()
        if not url or not _is_cacheable_gis_link(url):
            continue
        path = asset_dir / _safe_asset_name(url)
        asset = {
            "title": str(item.get("title") or ""),
            "url": url,
            "cache_path": str(path.relative_to(CACHE_DIR.parent)),
            "pubDate": str(item.get("pubDate") or ""),
        }
        try:
            asset["cached"] = "true" if _fetch_binary(url, path, force) else "false"
        except (OSError, urllib.error.URLError, ValueError) as exc:
            asset["cached"] = "false"
            asset["error"] = str(exc)
        assets.append(asset)
    return assets


def _normalize_storms(payload: dict[str, Any]) -> list[dict[str, Any]]:
    active = payload.get("activeStorms")
    if not isinstance(active, list):
        data = payload.get("data")
        active = data.get("activeStorms") if isinstance(data, dict) else []
    storms: list[dict[str, Any]] = []
    for storm in active if isinstance(active, list) else []:
        if not isinstance(storm, dict):
            continue
        storm_id = str(storm.get("id") or storm.get("stormId") or storm.get("atcfID") or "").upper()
        if not re.fullmatch(r"(AL|EP|CP)[0-9]{2}[0-9]{4}", storm_id):
            continue
        basin = storm_id[:2]
        normalized = dict(storm)
        normalized["id"] = storm_id
        normalized["basin"] = basin
        normalized["basinName"] = _BASINS[basin]["name"]
        storms.append(normalized)
    return storms


def _wallet(storm_id: str) -> int:
    return ((int(storm_id[2:4]) - 1) % 5) + 1


def _storm_product_url(storm_id: str, product: str) -> str:
    basin = _BASINS[storm_id[:2]]
    return f"https://www.nhc.noaa.gov/xml/{product}{basin['xml_code']}{_wallet(storm_id)}.xml"


def _storm_graphics(storm_id: str) -> list[dict[str, str]]:
    # NHC storm_graphics URL scheme (mirrors nchurricane.com/active):
    #   folder   = {AT|EP}{NN}   (uppercase; AL/AT -> AT, all else -> EP)
    #   filename = {full ATCF id}_{product}.png   e.g. AL052025_5day_cone_sm2.png
    #   rainfall = {basin}{NN}{YY}{PRODUCT}.gif    e.g. AL0525WPCQPF.gif (same folder)
    # Availability is verified client-side (image probe), so unissued products
    # (surge, rainfall, Spanish key messages, etc.) auto-hide.
    basin_code = storm_id[:2]
    basin_folder = "AT" if basin_code in ("AL", "AT") else "EP"
    storm_num = storm_id[2:4]
    year2 = storm_id[6:8]
    folder = f"{basin_folder}{storm_num}"
    base = f"https://www.nhc.noaa.gov/storm_graphics/{folder}"
    rain_prefix = f"{basin_code}{storm_num}{year2}"
    # Cumulative wind-speed-probability period used for the single-button view.
    wsp_hour = "F120"
    candidates = [
        ("Track", "3-Day Cone", f"{base}/{storm_id}_3day_cone_sm2.png"),
        ("Track", "5-Day Cone", f"{base}/{storm_id}_5day_cone_sm2.png"),
        ("Track", "Key Messages", f"{base}/{storm_id}_key_messages.png"),
        ("Track", "Key Messages (Espanol)", f"{base}/{storm_id}_spanish_key_messages.png"),
        ("Wind", "Wind Field", f"{base}/{storm_id}_current_wind.png"),
        ("Wind", "Wind History", f"{base}/{storm_id}_wind_history.png"),
        ("Wind", "Earliest Arrival", f"{base}/{storm_id}_3day_earliest_reasonable_toa_34.png"),
        ("Wind", "Most Likely Arrival", f"{base}/{storm_id}_3day_most_likely_toa_34.png"),
        ("Wind Prob", "Wind Prob 34 kt", f"{base}/{storm_id}_wind_probs_34_{wsp_hour}_sm2.png"),
        ("Wind Prob", "Wind Prob 50 kt", f"{base}/{storm_id}_wind_probs_50_{wsp_hour}_sm2.png"),
        ("Wind Prob", "Wind Prob 64 kt", f"{base}/{storm_id}_wind_probs_64_{wsp_hour}_sm2.png"),
        ("Surge / Rain", "Peak Storm Surge", f"{base}/{storm_id}_peak_surge.png"),
        ("Surge / Rain", "Rainfall (WPC)", f"{base}/{rain_prefix}WPCQPF.gif"),
        ("Surge / Rain", "Rainfall (Int'l)", f"{base}/{rain_prefix}INTQPF.gif"),
        ("Surge / Rain", "Excessive Rainfall", f"{base}/{rain_prefix}WPCERO.gif"),
    ]
    return [{"group": group, "label": label, "url": url} for group, label, url in candidates]


def _extract_xml_item_text(xml_text: str) -> tuple[str, dict[str, str]]:
    try:
        root = _xml_root(xml_text)
    except ET.ParseError:
        return _strip_html(xml_text), {}
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
        return _strip_html(item.findtext("description") or ""), meta
    return _strip_html(xml_text), meta








def _fetch_basin_feeds(
    force: bool,
    raw_dir: Path | None = None,
    *,
    include_feeds: bool = True,
    include_gtwo: bool = True,
) -> dict[str, dict[str, Any]]:
    feeds: dict[str, dict[str, Any]] = {}
    for basin_id, basin in _BASINS.items():
        basin_dir = CACHE_DIR / "basins" / basin_id
        if include_feeds and raw_dir is None:
            index_xml = _fetch_text(
                str(basin["index_url"]), basin_dir / "index.xml", force
            )
            gis_xml = _fetch_text(
                str(basin["gis_url"]), basin_dir / "gis.xml", force
            )
        elif include_feeds:
            index_xml = _read_raw_text(
                _raw_basin_file(raw_dir, basin_id, "index"),
                basin_dir / "index.xml",
            )
            gis_xml = _read_raw_text(
                _raw_basin_file(raw_dir, basin_id, "gis"),
                basin_dir / "gis.xml",
            )
        else:
            index_feed = _read_json(basin_dir / "index.json") or {}
            gis_feed = _read_json(basin_dir / "gis.json") or {}
            assets_payload = _read_json(basin_dir / "assets.json") or {}
            gis_assets = (
                assets_payload.get("assets")
                if isinstance(assets_payload.get("assets"), list)
                else []
            )
        if include_feeds:
            index_feed = _parse_rss_feed(index_xml)
            gis_feed = _parse_rss_feed(gis_xml)
            gis_items = (
                gis_feed.get("items")
                if isinstance(gis_feed.get("items"), list)
                else []
            )
            gis_assets = (
                _cache_gis_assets(basin_id, gis_items, force)
                if raw_dir is None
                else []
            )
            _write_json_atomic(basin_dir / "index.json", index_feed)
            _write_json_atomic(basin_dir / "gis.json", gis_feed)
            _write_json_atomic(
                basin_dir / "assets.json",
                {
                    "updated": _utc_now_iso(),
                    "basin": basin_id,
                    "assets": gis_assets,
                },
            )
        gtwo_payload: dict[str, Any] | None = None
        if include_gtwo and raw_dir is None:
            gtwo_kmz = basin_dir / "gtwo.kmz"
            if _fetch_binary(str(basin["gtwo_url"]), gtwo_kmz, force):
                gtwo_payload = _parse_gtwo_kmz(gtwo_kmz)
        elif include_gtwo:
            raw_kmz = raw_dir / "basins" / basin_id / f"gtwo-{basin['rss_suffix']}.kmz"
            if raw_kmz.exists():
                gtwo_payload = _parse_gtwo_kmz(raw_kmz)
        else:
            gtwo_payload = _read_json(basin_dir / "gtwo.json")
        if gtwo_payload is None:
            gtwo_payload = {
                "notExpected": False,
                "issued": "",
                "geojson": _feature_collection([]),
                "areas": [],
                "unavailable": True,
            }
        if include_gtwo:
            gtwo_payload["updated"] = _utc_now_iso()
            gtwo_payload["basin"] = basin_id
            _write_json_atomic(basin_dir / "gtwo.json", gtwo_payload)
        feeds[basin_id] = {
            "index_xml": str((basin_dir / "index.xml").relative_to(CACHE_DIR.parent)),
            "index_json": str((basin_dir / "index.json").relative_to(CACHE_DIR.parent)),
            "gis_xml": str((basin_dir / "gis.xml").relative_to(CACHE_DIR.parent)),
            "gis_json": str((basin_dir / "gis.json").relative_to(CACHE_DIR.parent)),
            "assets_json": str((basin_dir / "assets.json").relative_to(CACHE_DIR.parent)),
            "gtwo_json": str((basin_dir / "gtwo.json").relative_to(CACHE_DIR.parent)),
            "gtwo_area_count": len(gtwo_payload.get("areas", [])),
            "index_title": str(index_feed.get("channel", {}).get("title") or ""),
            "gis_title": str(gis_feed.get("channel", {}).get("title") or ""),
            "index_item_count": len(index_feed.get("items", [])),
            "gis_item_count": len(gis_feed.get("items", [])),
            "gis_asset_count": len(gis_assets),
        }
    return feeds


def _fetch_storm(storm: dict[str, Any], force: bool, raw_dir: Path | None = None) -> dict[str, Any]:
    storm_id = str(storm["id"]).upper()
    storm_dir = CACHE_DIR / "storms" / storm_id
    product_payloads: dict[str, dict[str, Any]] = {}
    for code, label in _STORM_PRODUCTS.items():
        url = _storm_product_url(storm_id, code)
        product_path = storm_dir / "products" / f"{code}.xml"
        try:
            if raw_dir is None:
                xml_text = _fetch_text(url, product_path, force)
                source_url = url
                source_path = str(product_path.relative_to(CACHE_DIR.parent))
            else:
                raw_path = _raw_storm_product_file(raw_dir, storm, code)
                xml_text = _read_raw_text(raw_path, product_path)
                source_url = str(raw_path)
                source_path = str(raw_path.relative_to(raw_dir.parent))
            text, meta = _extract_xml_item_text(xml_text)
            product_payloads[code] = {
                "code": code,
                "label": label,
                "url": source_url,
                "cache_path": source_path,
                "meta": meta,
                "text": text,
            }
        except (OSError, urllib.error.URLError, ValueError, ET.ParseError) as exc:
            product_payloads[code] = {"code": code, "label": label, "url": url, "error": str(exc)}

    advisory_text = str(product_payloads.get("TCP", {}).get("text") or "")
    forecast_text = str(product_payloads.get("TCM", {}).get("text") or "")
    gis_layers = _build_storm_gis_layers(storm, storm_dir, force, raw_dir)
    payload = {
        "status": "success",
        "stormId": storm_id,
        "storm": storm,
        "basin": storm_id[:2],
        "basinName": _BASINS[storm_id[:2]]["name"],
        "wallet": _wallet(storm_id),
        "advisory": _parse_advisory(advisory_text) if advisory_text else {},
        "track": _parse_track(forecast_text) if forecast_text else [],
        "products": product_payloads,
        "graphics": _storm_graphics(storm_id),
        "gis_assets": _collect_raw_gis_assets(raw_dir, storm_id) if raw_dir else [],
        "gis_layers": gis_layers,
        "updated": product_payloads.get("TCP", {}).get("meta", {}).get("pubDate"),
        "cached_at": _utc_now_iso(),
    }
    _write_json_atomic(storm_dir / "storm.json", payload)
    return payload


def run_tropical_worker(
    force: bool = False,
    raw_dir: Path | str | None = None,
    storms_file: Path | str | None = None,
    scopes: set[str] | None = None,
) -> dict[str, Any]:
    """Refresh NHC tropical cyclone cache artifacts.

    ``storms_file`` seeds the active-storm list from a local JSON file while still
    fetching each storm's text products, GIS, and basin feeds live from NHC -- useful
    for replaying a past season's storms against the live archive endpoints.
    """
    raw_path = Path(raw_dir).resolve() if raw_dir else None
    storms_path = Path(storms_file).resolve() if storms_file else None
    requested_scopes = {str(scope).strip().lower() for scope in (scopes or ())}
    if not requested_scopes:
        requested_scopes = {"advisories", "gtwo"}
    unknown_scopes = requested_scopes - {"advisories", "gtwo"}
    if unknown_scopes:
        raise ValueError(
            f"Unknown tropical refresh scope(s): {', '.join(sorted(unknown_scopes))}"
        )
    targeted = scopes is not None
    if (raw_path is None and storms_path is None and not force
            and not targeted
            and is_cache_fresh("tropical", _FRESH_WINDOW_SEC)):
        logging.getLogger(__name__).info("[tropical_worker] Cache fresh - skipping run")
        return {"status": "current", "scopes": []}

    start = time.time()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    current_fetch_failed = False

    refresh_advisories = "advisories" in requested_scopes
    refresh_gtwo = "gtwo" in requested_scopes

    try:
        if raw_path is not None:
            current_payload = _read_json(raw_path / "CurrentStorms.json")
            if current_payload is not None:
                _write_json_atomic(CURRENT_STORMS_FILE, current_payload)
        elif storms_path is not None:
            current_payload = _read_json(storms_path)
            if current_payload is not None:
                _write_json_atomic(CURRENT_STORMS_FILE, current_payload)
        elif not refresh_advisories:
            current_payload = _read_json(CURRENT_STORMS_FILE)
        else:
            current_payload = _fetch_json(_CURRENT_STORMS_URL, CURRENT_STORMS_FILE, force)
        if current_payload is None:
            current_payload = {"activeStorms": []}
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"CurrentStorms: {exc}")
        current_fetch_failed = True
        current_payload = _read_json(CURRENT_STORMS_FILE) or {"activeStorms": []}

    try:
        feeds = _fetch_basin_feeds(
            force,
            raw_path,
            include_feeds=refresh_advisories,
            include_gtwo=refresh_gtwo,
        )
    except (OSError, urllib.error.URLError, ValueError) as exc:
        errors.append(f"basin feeds: {exc}")
        feeds = {}

    storms = _normalize_storms(current_payload)
    storm_payloads: list[dict[str, Any]] = []
    if refresh_advisories:
        for storm in storms:
            try:
                storm_payloads.append(_fetch_storm(storm, force, raw_path))
            except (OSError, urllib.error.URLError, ValueError) as exc:
                storm_id = str(storm.get("id") or "unknown")
                errors.append(f"{storm_id}: {exc}")

    summary = {
        "status": "success" if not errors else "partial",
        "updated": _utc_now_iso(),
        "source": str(raw_path) if raw_path else _CURRENT_STORMS_URL,
        "source_mode": "local-test-raw" if raw_path else "nhc-live",
        "interval_minutes": INTERVAL_MINUTES,
        "basins": _BASINS,
        "feeds": feeds,
        "storms": storms,
        "storm_count": len(storms),
        "storm_cache_paths": [
            str((CACHE_DIR / "storms" / str(storm["id"]).upper() / "storm.json").relative_to(CACHE_DIR.parent))
            for storm in storms
        ],
        "errors": errors,
    }
    _write_json_atomic(SUMMARY_FILE, summary)
    if current_fetch_failed and not feeds:
        # Both core fetches failed (e.g. total network/SSL outage): nothing
        # usable was cached, so leave the freshness sentinel untouched and let
        # the next scheduled run retry. Partial successes still mark complete
        # so a few bad storms don't cause NHC request hammering.
        logging.getLogger(__name__).warning("[tropical_worker] Core fetches failed - cache not marked fresh")
    elif not targeted:
        mark_run_complete("tropical")
    else:
        logging.getLogger(__name__).info("[tropical_worker] Targeted refresh complete - global freshness unchanged")
    logging.getLogger(__name__).warning(
        f"[tropical_worker] Complete in {time.time() - start:.2f}s "
        f"({len(storms)} active storm(s), {len(errors)} error(s))"
    )
    for err in errors:
        logging.getLogger(__name__).info(f"[tropical_worker] {err}")
    if current_fetch_failed and refresh_advisories:
        raise RuntimeError("Tropical current-storm refresh failed")
    advisory_times = [
        str(payload.get("updated"))
        for payload in storm_payloads
        if payload.get("updated")
    ]
    gtwo_times = [
        str(
            (_read_json(CACHE_DIR / "basins" / basin_id / "gtwo.json") or {}).get(
                "issued"
            )
            or ""
        )
        for basin_id in _BASINS
    ]
    return {
        "status": "warmed",
        "scopes": sorted(requested_scopes),
        "source_timestamp": max(advisory_times + gtwo_times, default=summary["updated"]),
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Run the NHC tropical cache worker once.")
    parser.add_argument("--force", action="store_true", help="Bypass freshness gate.")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        help=(
            "Read local NHC-style raw test files instead of fetching live data. "
            "Expected basin RSS names are index-at.xml, gis-at.xml, index-ep.xml, etc."
        ),
    )
    parser.add_argument(
        "--storms-file",
        type=Path,
        help=(
            "Seed the active-storm list from a local CurrentStorms.json while still "
            "fetching products/GIS/basin feeds live from NHC. Pair with --force."
        ),
    )
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to cache/logs/scheduled/tropical.log.",
    )
    args = parser.parse_args()
    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("tropical")
    run_tropical_worker(force=args.force, raw_dir=args.raw_dir, storms_file=args.storms_file)
