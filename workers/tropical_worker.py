"""Background worker for NHC tropical cyclone products.

Fetches NHC/CPHC active storm, RSS, GIS, and storm-wallet products into
cache/tropical so the browser and FastAPI routes never poll NHC directly.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import time
import urllib.error
import urllib.request
import warnings
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workers._freshness import is_cache_fresh, mark_run_complete

try:
    import shapefile
    shapefile.VERBOSE = False
except ImportError:  # pragma: no cover - optional dependency guard
    shapefile = None

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "tropical"
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
    },
    "EP": {
        "name": "Eastern Pacific",
        "index_url": "https://www.nhc.noaa.gov/index-ep.xml",
        "gis_url": "https://www.nhc.noaa.gov/gis-ep.xml",
        "rss_suffix": "ep",
        "xml_code": "EP",
        "graphics_code": "EP",
    },
    "CP": {
        "name": "Central Pacific",
        "index_url": "https://www.nhc.noaa.gov/index-cp.xml",
        "gis_url": "https://www.nhc.noaa.gov/gis-cp.xml",
        "rss_suffix": "cp",
        "xml_code": "CP",
        "graphics_code": "CP",
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
_FIVE_DAY_LAYER_KINDS = {
    "cone": "_5day_pgn.shp",
    "forecast_track": "_5day_lin.shp",
    "forecast_points": "_5day_pts.shp",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, separators=(",", ":"), default=_json_default)
    tmp.replace(path)


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
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
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
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    _write_json_atomic(meta_path, meta)
    return text


def _read_raw_text(raw_path: Path, out_path: Path) -> str:
    text = raw_path.read_text(encoding="utf-8")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
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
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_bytes(body)
    tmp.replace(out_path)
    meta["bytes"] = str(len(body))
    _write_json_atomic(meta_path, meta)
    return True


def _strip_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _xml_root(xml_text: str) -> ET.Element:
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        sanitized = re.sub(
            r"&(?!amp;|lt;|gt;|quot;|apos;|#[0-9]+;|#x[0-9A-Fa-f]+;)",
            "&amp;",
            xml_text,
        )
        return ET.fromstring(sanitized)


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


def _feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


def _shapefile_feature_collection_from_zip(zip_path: Path, shp_suffix: str) -> dict[str, Any] | None:
    if shapefile is None:
        return None
    try:
        with zipfile.ZipFile(zip_path) as zf:
            shp_name = next((name for name in zf.namelist() if name.lower().endswith(shp_suffix)), "")
            if not shp_name:
                return None
            stem = shp_name[:-4]
            reader = shapefile.Reader(
                shp=io.BytesIO(zf.read(f"{stem}.shp")),
                shx=io.BytesIO(zf.read(f"{stem}.shx")),
                dbf=io.BytesIO(zf.read(f"{stem}.dbf")),
            )
            features: list[dict[str, Any]] = []
            for shape_record in reader.iterShapeRecords():
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    geometry = shape_record.shape.__geo_interface__
                properties = shape_record.record.as_dict()
                features.append(
                    {
                        "type": "Feature",
                        "properties": properties,
                        "geometry": geometry,
                    }
                )
            return _feature_collection(features)
    except (OSError, KeyError, StopIteration, zipfile.BadZipFile, shapefile.ShapefileException):
        return None


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


def _build_storm_gis_layers(
    storm: dict[str, Any],
    storm_dir: Path,
    force: bool,
    raw_dir: Path | None,
) -> dict[str, Any]:
    storm_id = str(storm["id"]).upper()
    zip_path = _raw_five_day_zip(raw_dir, storm_id) if raw_dir else _cache_live_five_day_zip(storm, storm_dir, force)
    layers: dict[str, Any] = {}
    if not zip_path:
        return layers

    layer_dir = storm_dir / "gis"
    for layer_id, shp_suffix in _FIVE_DAY_LAYER_KINDS.items():
        collection = _shapefile_feature_collection_from_zip(zip_path, shp_suffix)
        if not collection:
            continue
        out_path = layer_dir / f"{layer_id}.geojson"
        payload = {
            "updated": _utc_now_iso(),
            "stormId": storm_id,
            "layer": layer_id,
            "source_path": str(zip_path),
            "geojson": collection,
        }
        _write_json_atomic(out_path, payload)
        layers[layer_id] = {
            "cache_path": str(out_path.relative_to(CACHE_DIR.parent)),
            "feature_count": len(collection["features"]),
            "source_path": str(zip_path),
            "geojson": collection,
        }
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
    basin = _BASINS[storm_id[:2]]
    graphics_id = f"{basin['graphics_code']}{storm_id[2:4]}"
    base = f"https://www.nhc.noaa.gov/storm_graphics/{graphics_id.lower()}"
    file_prefix = f"{graphics_id}{storm_id[4:8]}"
    candidates = [
        ("5-day Cone", f"{file_prefix}_5day_cone_no_line.png"),
        ("5-day Cone + Wind", f"{file_prefix}_5day_cone_no_line_and_wind.png"),
        ("Current Wind Field", f"{file_prefix}_current_wind.png"),
        ("Wind History", f"{file_prefix}_wind_history.png"),
        ("Most Likely Arrival Time", f"{file_prefix}_most_likely_toa_34.png"),
        ("Earliest Reasonable Arrival Time", f"{file_prefix}_earliest_reasonable_toa_34.png"),
    ]
    return [{"label": label, "url": f"{base}/{filename}"} for label, filename in candidates]


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


def _coord(value: str, hemi: str) -> float | None:
    try:
        parsed = float(value)
    except ValueError:
        return None
    return -parsed if hemi.upper() in {"S", "W"} else parsed


def _parse_advisory(text: str) -> dict[str, Any]:
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
            "lat": _coord(loc.group(1), loc.group(2)),
            "lon": _coord(loc.group(3), loc.group(4)),
            "latText": f"{loc.group(1)}{loc.group(2).upper()}",
            "lonText": f"{loc.group(3)}{loc.group(4).upper()}",
        }
    wind = re.search(r"MAXIMUM SUSTAINED WINDS\.*\s*([0-9]+)\s*MPH.*?([0-9]+)\s*KM/H", block, re.I)
    if wind:
        parsed["maxWindMph"] = int(wind.group(1))
        parsed["maxWindKph"] = int(wind.group(2))
    motion = re.search(r"PRESENT MOVEMENT\.*\s*(.*?)\s+AT\s+([0-9]+)\s*MPH.*?([0-9]+)\s*KM/H", block, re.I)
    if motion:
        parsed["motion"] = {"text": motion.group(1).strip(), "mph": int(motion.group(2)), "kph": int(motion.group(3))}
    pressure = re.search(r"MINIMUM CENTRAL PRESSURE\.*\s*([0-9]+)\s*MB", block, re.I)
    if pressure:
        parsed["pressureMb"] = int(pressure.group(1))
    headlines = re.findall(r"\.\.\.(.*?)\.\.\.", text)
    if headlines:
        parsed["headline"] = " ".join(part.strip() for part in headlines[:2] if part.strip())
    return parsed


def _parse_track(text: str) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    lines = text.splitlines()
    for line in lines:
        match = re.search(
            r"^(INIT|[0-9]{1,3}H)\s+([0-9]{2}/[0-9]{4}Z)\s+([0-9.]+)([NS])\s+([0-9.]+)([EW])\s+([0-9]+)\s+KT",
            line.strip(),
            re.I,
        )
        if not match:
            continue
        lat = _coord(match.group(3), match.group(4))
        lon = _coord(match.group(5), match.group(6))
        if lat is None or lon is None:
            continue
        points.append(
            {
                "hour": match.group(1).upper(),
                "time": match.group(2),
                "lat": lat,
                "lon": lon,
                "windKt": int(match.group(7)),
            }
        )
    if points:
        return points

    pending: dict[str, Any] | None = None
    for raw_line in lines:
        line = " ".join(raw_line.strip().split())
        init_match = re.search(
            r"CENTER LOCATED NEAR\s+([0-9.]+)([NS])\s+([0-9.]+)([EW])\s+AT\s+([0-9]{2}/[0-9]{4}Z)",
            line,
            re.I,
        )
        forecast_match = re.search(
            r"^(FORECAST|OUTLOOK) VALID\s+([0-9]{2}/[0-9]{4}Z)\s+([0-9.]+)([NS])\s+([0-9.]+)([EW])",
            line,
            re.I,
        )
        if init_match:
            lat = _coord(init_match.group(1), init_match.group(2))
            lon = _coord(init_match.group(3), init_match.group(4))
            if lat is not None and lon is not None:
                pending = {
                    "hour": "INIT",
                    "time": init_match.group(5),
                    "lat": lat,
                    "lon": lon,
                    "windKt": None,
                }
                points.append(pending)
            continue
        if forecast_match:
            lat = _coord(forecast_match.group(3), forecast_match.group(4))
            lon = _coord(forecast_match.group(5), forecast_match.group(6))
            if lat is not None and lon is not None:
                pending = {
                    "hour": forecast_match.group(1).upper(),
                    "time": forecast_match.group(2),
                    "lat": lat,
                    "lon": lon,
                    "windKt": None,
                }
                points.append(pending)
            continue
        wind_match = re.search(r"MAX (?:SUSTAINED )?WINDS?\s+([0-9]+)\s+KT", line, re.I)
        if pending is not None and wind_match:
            pending["windKt"] = int(wind_match.group(1))
    return points


def _fetch_basin_feeds(force: bool, raw_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    feeds: dict[str, dict[str, Any]] = {}
    for basin_id, basin in _BASINS.items():
        basin_dir = CACHE_DIR / "basins" / basin_id
        if raw_dir is None:
            index_xml = _fetch_text(str(basin["index_url"]), basin_dir / "index.xml", force)
            gis_xml = _fetch_text(str(basin["gis_url"]), basin_dir / "gis.xml", force)
        else:
            index_xml = _read_raw_text(_raw_basin_file(raw_dir, basin_id, "index"), basin_dir / "index.xml")
            gis_xml = _read_raw_text(_raw_basin_file(raw_dir, basin_id, "gis"), basin_dir / "gis.xml")
        index_feed = _parse_rss_feed(index_xml)
        gis_feed = _parse_rss_feed(gis_xml)
        gis_items = gis_feed.get("items") if isinstance(gis_feed.get("items"), list) else []
        gis_assets = _cache_gis_assets(basin_id, gis_items, force) if raw_dir is None else []
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
        feeds[basin_id] = {
            "index_xml": str((basin_dir / "index.xml").relative_to(CACHE_DIR.parent)),
            "index_json": str((basin_dir / "index.json").relative_to(CACHE_DIR.parent)),
            "gis_xml": str((basin_dir / "gis.xml").relative_to(CACHE_DIR.parent)),
            "gis_json": str((basin_dir / "gis.json").relative_to(CACHE_DIR.parent)),
            "assets_json": str((basin_dir / "assets.json").relative_to(CACHE_DIR.parent)),
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


def run_tropical_worker(force: bool = False, raw_dir: Path | str | None = None) -> None:
    """Refresh NHC tropical cyclone cache artifacts."""
    raw_path = Path(raw_dir).resolve() if raw_dir else None
    if raw_path is None and not force and is_cache_fresh("tropical", _FRESH_WINDOW_SEC):
        print("[tropical_worker] Cache fresh - skipping run")
        return

    start = time.time()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    try:
        if raw_path is None:
            current_payload = _fetch_json(_CURRENT_STORMS_URL, CURRENT_STORMS_FILE, force)
        else:
            current_payload = _read_json(raw_path / "CurrentStorms.json")
            if current_payload is not None:
                _write_json_atomic(CURRENT_STORMS_FILE, current_payload)
        if current_payload is None:
            current_payload = {"activeStorms": []}
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"CurrentStorms: {exc}")
        current_payload = _read_json(CURRENT_STORMS_FILE) or {"activeStorms": []}

    try:
        feeds = _fetch_basin_feeds(force, raw_path)
    except (OSError, urllib.error.URLError, ValueError) as exc:
        errors.append(f"basin feeds: {exc}")
        feeds = {}

    storms = _normalize_storms(current_payload)
    storm_payloads: list[dict[str, Any]] = []
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
    mark_run_complete("tropical")
    print(
        f"[tropical_worker] Complete in {time.time() - start:.2f}s "
        f"({len(storms)} active storm(s), {len(errors)} error(s))"
    )
    for err in errors:
        print(f"[tropical_worker] {err}")


if __name__ == "__main__":
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
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to logs/scheduled/tropical.log.",
    )
    args = parser.parse_args()
    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("tropical")
    run_tropical_worker(force=args.force, raw_dir=args.raw_dir)
