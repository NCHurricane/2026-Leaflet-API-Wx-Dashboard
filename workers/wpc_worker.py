"""Background worker for WPC ERO and QPF products.

Fetches each enabled WPC KMZ/KML, parses it to a GeoJSON FeatureCollection,
and writes ``cache/wpc/...`` so the browser and FastAPI routes never poll WPC
directly. Mirrors the tropical worker's ETag/If-Modified-Since fetch and
namespace-stripped KML walk, and the SPC worker's freshness gate.

Run once:  python -m workers.wpc_worker --force
Test mode: python -m workers.wpc_worker --force --raw-dir path/with/ero_day1.kmz
"""

from __future__ import annotations

import argparse
import calendar
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow both `python -m workers.wpc_worker` and direct execution.
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app_core.upstream_ledger import urlopen  # noqa: E402
from workers._freshness import is_cache_fresh, mark_run_complete  # noqa: E402
from config.wpc_config import (  # noqa: E402
    DEFAULT_ERO_COLOR,
    ERO_CATEGORY_LABEL,
    ERO_CATEGORY_RANK,
    ERO_COLORS,
    ERO_DISCUSSION_URL,
    FOP_COLORS,
    MPD_COLORS,
    SIGWX_CATEGORY_LABEL,
    SIGWX_CATEGORY_RANK,
    SIGWX_COLORS,
    WINTER_DISCUSSION_URL,
    WINTER_PROBABILITY_COLORS,
    WPC_BASE_URL,
    WPC_PRODUCTS,
    ero_category_from_name,
    qpf_threshold_from_name,
)

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "wpc"
RAW_DIR = CACHE_DIR / ".raw"
STATUS_DIR = CACHE_DIR / ".status"

INTERVAL_MINUTES = 30
# Skip if a successful refresh happened within 75% of the interval.
_FRESH_WINDOW_SEC = int(INTERVAL_MINUTES * 60 * 0.75)
_USER_AGENT = "NCHurricane Dashboard/2026 (+https://nchurricane.com)"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_product_status(
    product: dict[str, Any],
    *,
    available: bool,
    status: str,
    error: str = "",
    http_status: int | None = None,
) -> None:
    payload: dict[str, Any] = {
        "product": product["id"],
        "checked_at": _utc_now_iso(),
        "available": available,
        "status": status,
    }
    if error:
        payload["error"] = error
    if http_status is not None:
        payload["http_status"] = http_status
    _write_json_atomic(STATUS_DIR / f"{product['id']}.json", payload)


def _request_url(
    url: str,
    cache_meta_path: Path | None = None,
    timeout_seconds: int = 45,
) -> tuple[bytes | None, dict[str, str], int]:
    """Fetch with conditional ETag/If-Modified-Since. Returns (body, meta, status)."""
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/vnd.google-earth.kmz,application/xml,*/*;q=0.8",
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


def _fetch_binary(url: str, out_path: Path, force: bool) -> bool:
    """Download to out_path with conditional caching. Returns True if file exists."""
    meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")
    body, meta, status = _request_url(url, None if force else meta_path)
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


# --- KML helpers (namespace-stripped, mirroring tropical_worker) ------------


def _kml_local(tag: str) -> str:
    return tag.split("}")[-1]


def _kml_find(elem: ET.Element | None, name: str) -> ET.Element | None:
    if elem is None:
        return None
    for child in elem:
        if _kml_local(child.tag) == name:
            return child
    return None


def _parse_kml_coords(text: str) -> list[list[float]]:
    coords: list[list[float]] = []
    for token in (text or "").split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                coords.append([float(parts[0]), float(parts[1])])
            except ValueError:
                continue
    return coords


def _boundary_ring(boundary: ET.Element | None) -> list[list[float]]:
    if boundary is None:
        return []
    coords_el = None
    for node in boundary.iter():
        if _kml_local(node.tag) == "coordinates":
            coords_el = node
            break
    ring = _parse_kml_coords(coords_el.text if coords_el is not None else "")
    if len(ring) >= 3 and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def _polygon_coordinates(polygon_el: ET.Element) -> list[list[list[float]]] | None:
    """Return GeoJSON Polygon rings ([outer, *holes]) for one KML <Polygon>."""
    outer = _boundary_ring(_kml_find(polygon_el, "outerBoundaryIs"))
    if len(outer) < 4:
        return None
    rings = [outer]
    for child in polygon_el:
        if _kml_local(child.tag) == "innerBoundaryIs":
            hole = _boundary_ring(child)
            if len(hole) >= 4:
                rings.append(hole)
    return rings


def _placemark_multipolygon(placemark: ET.Element) -> dict[str, Any] | None:
    """Collect every <Polygon> under a Placemark into Polygon/MultiPolygon."""
    polygons: list[list[list[list[float]]]] = []
    for node in placemark.iter():
        if _kml_local(node.tag) == "Polygon":
            rings = _polygon_coordinates(node)
            if rings:
                polygons.append(rings)
    if not polygons:
        return None
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


# --- ERO parsing ------------------------------------------------------------


def _kml_from_kmz(kmz_path: Path) -> str | None:
    try:
        with zipfile.ZipFile(kmz_path) as zf:
            kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
            if not kml_names:
                return None
            return zf.read(kml_names[0]).decode("utf-8", errors="replace")
    except (OSError, zipfile.BadZipFile):
        return None


def _parse_ero_kml(kml_text: str) -> list[dict[str, Any]]:
    """Parse an ERO KML body into GeoJSON features (one per risk Placemark)."""
    root = ET.fromstring(kml_text)
    features: list[dict[str, Any]] = []
    for placemark in (n for n in root.iter() if _kml_local(n.tag) == "Placemark"):
        name_el = _kml_find(placemark, "name")
        name = (name_el.text or "").strip() if name_el is not None else ""
        category = ero_category_from_name(name)
        if not category:
            continue
        geometry = _placemark_multipolygon(placemark)
        if geometry is None:
            continue
        features.append(
            {
                "type": "Feature",
                "id": f"wpc-ero-{category.lower()}",
                "geometry": geometry,
                "properties": {
                    "category": category,
                    "label": ERO_CATEGORY_LABEL.get(category, name),
                    "name": name,
                    "color": ERO_COLORS.get(category, DEFAULT_ERO_COLOR),
                    "rank": ERO_CATEGORY_RANK.get(category, 0),
                },
            }
        )
    features.sort(key=lambda f: f["properties"]["rank"])
    return features


def _abgr_to_hex(abgr: str) -> str | None:
    """Convert a KML ABGR color ('ff008b00') to '#RRGGBB'."""
    value = (abgr or "").strip()
    if len(value) != 8:
        return None
    return f"#{value[6:8]}{value[4:6]}{value[2:4]}".upper()


def _resolve_style_colors(root: ET.Element) -> dict[str, str]:
    """Map each <Style id> to its PolyStyle (or LineStyle) fill color hex."""
    colors: dict[str, str] = {}
    for style in (n for n in root.iter() if _kml_local(n.tag) == "Style"):
        style_id = style.get("id") or ""
        if not style_id:
            continue
        color_el = None
        for sub in ("PolyStyle", "LineStyle"):
            block = _kml_find(style, sub)
            if block is not None:
                color_el = _kml_find(block, "color")
                if color_el is not None and color_el.text:
                    break
        hex_color = _abgr_to_hex(color_el.text) if color_el is not None else None
        if hex_color:
            colors[style_id] = hex_color
    return colors


def _placemark_style_id(placemark: ET.Element) -> str:
    return (_kml_findtext_local(placemark, "styleUrl") or "").lstrip("#")


def _kml_findtext_local(elem: ET.Element, name: str) -> str:
    child = _kml_find(elem, name)
    return (child.text or "").strip() if child is not None and child.text else ""


def _parse_qpf_kml(kml_text: str) -> list[dict[str, Any]]:
    """Parse a QPF contour KML into GeoJSON features (one per accumulation bin)."""
    root = ET.fromstring(kml_text)
    style_colors = _resolve_style_colors(root)
    features: list[dict[str, Any]] = []
    for placemark in (n for n in root.iter() if _kml_local(n.tag) == "Placemark"):
        name = _kml_findtext_local(placemark, "name")
        threshold = qpf_threshold_from_name(name)
        if threshold is None:
            continue
        geometry = _placemark_multipolygon(placemark)
        if geometry is None:
            continue
        color = style_colors.get(_placemark_style_id(placemark), "#888888")
        features.append(
            {
                "type": "Feature",
                "id": f"wpc-qpf-{threshold}",
                "geometry": geometry,
                "properties": {
                    "threshold": threshold,
                    "label": f"≥ {threshold:g} in",
                    "name": name,
                    "color": color,
                    "rank": threshold,
                },
            }
        )
    features.sort(key=lambda f: f["properties"]["rank"])
    return features


_WINTER_STYLE_PROBABILITY = {
    "poly_slight": 10,
    "poly_mod": 40,
    "poly_high": 70,
}


def _parse_winter_kml(kml_text: str) -> list[dict[str, Any]]:
    """Parse one WPC winter threshold KML into probability polygons."""
    root = ET.fromstring(kml_text)
    style_colors = _resolve_style_colors(root)
    features: list[dict[str, Any]] = []
    for index, placemark in enumerate(
        n for n in root.iter() if _kml_local(n.tag) == "Placemark"
    ):
        style_id = _placemark_style_id(placemark)
        probability = _WINTER_STYLE_PROBABILITY.get(style_id)
        if probability is None:
            continue
        geometry = _placemark_multipolygon(placemark)
        if geometry is None:
            continue
        name = _kml_findtext_local(placemark, "name")
        features.append(
            {
                "type": "Feature",
                "id": f"wpc-winter-{probability}-{index}",
                "geometry": geometry,
                "properties": {
                    "probability": probability,
                    "label": f"≥ {probability}%",
                    "name": name,
                    "color": style_colors.get(
                        style_id,
                        WINTER_PROBABILITY_COLORS[probability],
                    ),
                    "rank": probability,
                },
            }
        )
    features.sort(key=lambda feature: feature["properties"]["rank"])
    return features


_FOP_CATEGORY_RANK = {
    "POSSIBLE": 1,
    "LIKELY": 2,
    "OCCURRING": 3,
}


def _parse_fop_kml(kml_text: str) -> list[dict[str, Any]]:
    """Parse the five-day River Flood Outlook categorical polygons."""
    root = ET.fromstring(kml_text)
    style_colors = _resolve_style_colors(root)
    features: list[dict[str, Any]] = []
    for placemark in (n for n in root.iter() if _kml_local(n.tag) == "Placemark"):
        name = _kml_findtext_local(placemark, "name")
        category = name.strip().upper()
        if category not in FOP_COLORS:
            continue
        geometry = _placemark_multipolygon(placemark)
        if geometry is None:
            continue
        features.append(
            {
                "type": "Feature",
                "id": f"wpc-fop-{category.lower()}",
                "geometry": geometry,
                "properties": {
                    "category": category,
                    "label": name,
                    "name": name,
                    "color": style_colors.get(
                        _placemark_style_id(placemark),
                        FOP_COLORS[category],
                    ),
                    "rank": _FOP_CATEGORY_RANK[category],
                },
            }
        )
    features.sort(key=lambda feature: feature["properties"]["rank"])
    return features


def _mpd_fields(description: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, value in re.findall(
        r"<td>\s*([^<]+?)\s*</td>\s*<td>\s*(.*?)\s*</td>",
        description or "",
        flags=re.IGNORECASE | re.DOTALL,
    ):
        clean_key = html.unescape(re.sub(r"<[^>]+>", "", key)).strip()
        clean_value = html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
        if clean_key:
            fields[clean_key] = clean_value
    return fields


def _mpd_category(mpd_type: str) -> str:
    value = (mpd_type or "").lower()
    if "unlikely" in value:
        return "UNLIKELY"
    if "likely" in value:
        return "LIKELY"
    return "POSSIBLE"


def _month_candidate(year: int, month: int, offset: int) -> tuple[int, int]:
    month_index = year * 12 + month - 1 + offset
    return month_index // 12, month_index % 12 + 1


def _mpd_valid_time(code: str, issue_time: str) -> str | None:
    match = re.fullmatch(r"(\d{2})(\d{2})(\d{2})", (code or "").strip())
    issue_match = re.search(
        r"\b([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{4})\b",
        issue_time or "",
    )
    if not match or not issue_match:
        return None
    issue_date = datetime.strptime(
        " ".join(issue_match.groups()),
        "%b %d %Y",
    ).replace(tzinfo=timezone.utc)
    day, hour, minute = (int(part) for part in match.groups())
    candidates: list[datetime] = []
    for offset in (-1, 0, 1):
        year, month = _month_candidate(issue_date.year, issue_date.month, offset)
        if day > calendar.monthrange(year, month)[1]:
            continue
        candidates.append(datetime(year, month, day, hour, minute, tzinfo=timezone.utc))
    if not candidates:
        return None
    closest = min(candidates, key=lambda value: abs((value - issue_date).total_seconds()))
    return closest.isoformat()


def _parse_mpd_kml(kml_text: str, mpd_id: str) -> list[dict[str, Any]]:
    root = ET.fromstring(kml_text)
    features: list[dict[str, Any]] = []
    for placemark in (n for n in root.iter() if _kml_local(n.tag) == "Placemark"):
        geometry = _placemark_multipolygon(placemark)
        if geometry is None:
            continue
        description = _kml_findtext_local(placemark, "description")
        fields = _mpd_fields(description)
        number = str(fields.get("MPDNumber") or mpd_id).lstrip("0") or "0"
        mpd_type = fields.get("MPDType") or "Heavy rainfall, Flash flooding possible"
        category = _mpd_category(mpd_type)
        valid_start = _mpd_valid_time(fields.get("ValidStart", ""), fields.get("IssueTime", ""))
        valid_end = _mpd_valid_time(fields.get("ValidEndTi", ""), fields.get("IssueTime", ""))
        features.append(
            {
                "type": "Feature",
                "id": f"wpc-mpd-{number}",
                "geometry": geometry,
                "properties": {
                    "category": category,
                    "color": MPD_COLORS[category],
                    "label": f"MPD #{int(number):04d} — Flash flooding {category.lower()}",
                    "mpd_number": int(number),
                    "mpd_type": mpd_type,
                    "issue_time": fields.get("IssueTime"),
                    "valid_start": valid_start,
                    "valid_end": valid_end,
                    "wfo": fields.get("WFO"),
                    "rfc": fields.get("RFC"),
                    "discussion_url": fields.get("MPD"),
                    "area_square_miles": fields.get("Area"),
                },
            }
        )
    return features


def _active_mpd_ids(index_html: str) -> list[str]:
    ids = re.findall(
        r"metwatch_mpd_multi\.php\?md=(\d{4})&(?:amp;)?yr=\d{4}",
        index_html or "",
        flags=re.IGNORECASE,
    )
    return list(dict.fromkeys(ids))


def _discussion_text(page_html: str) -> str:
    match = re.search(r"<pre[^>]*>([\s\S]*?)</pre>", page_html or "", re.IGNORECASE)
    if not match:
        return ""
    text = html.unescape(re.sub(r"<[^>]+>", "", match.group(1)))
    return re.sub(r"\r\n?", "\n", text).strip()


def _ero_discussion_for_day(text: str, day: int) -> str:
    if day >= 4:
        # WPC combines Days 4 and 5 under a single "Day 4 and Day 5" heading.
        match = re.search(
            r"(?ms)^Day 4 and Day 5\s*$([\s\S]*?)(?=\Z)",
            text or "",
        )
        return f"Day 4 and Day 5\n{match.group(1).strip()}" if match else ""
    match = re.search(
        rf"(?ms)^Day {day}\s*$([\s\S]*?)(?=^Day {day + 1}\s*$|^Day 4 and Day 5\s*$|\Z)",
        text or "",
    )
    return f"Day {day}\n{match.group(1).strip()}" if match else ""


def _fetch_discussion(
    url: str,
    raw_name: str,
    force: bool,
    raw_dir: Path | None,
) -> str:
    if raw_dir is not None:
        page_path = raw_dir / raw_name
        if not page_path.exists():
            return ""
    else:
        page_path = RAW_DIR / raw_name
        if not _fetch_binary(url, page_path, force):
            return ""
    try:
        return _discussion_text(page_path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ""


def _write_layer(
    cache_path: str,
    *,
    product: dict[str, Any],
    features: list[dict[str, Any]],
    source_url: str,
    empty_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = {
        "updated": _utc_now_iso(),
        "product": product["id"],
        "group": product["group"],
        "day": product.get("day"),
        "days": product.get("days", [product.get("day")]),
        "source_url": source_url,
        "geojson": {"type": "FeatureCollection", "features": features},
    }
    if not features and empty_message:
        payload["empty_message"] = empty_message
    if metadata:
        payload.update(metadata)
    _write_json_atomic(CACHE_DIR / cache_path, payload)


def _parse_surface_label(popup_html: str) -> str:
    """Extract a plain-text label from a WPC popupContent HTML string."""
    text = re.sub(r"<[^>]+>", "", popup_html or "")
    sentence = text.split("<br")[0].split("\n")[0].strip()
    # Strip trailing date info after 'Issued by WPC:'
    sentence = re.sub(r"\s*Issued by WPC:.*", "", sentence, flags=re.IGNORECASE)
    return sentence.strip()


def _parse_geojson_single(raw: str, product: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a single-Feature WPC mapdata JSON (qpfD1.json style)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if data.get("type") != "Feature":
        return []

    geometry = data.get("geometry") or {}
    coords = geometry.get("coordinates") or []
    # Empty geometry sentinel: [[]] or [[[]]]
    flat = [c for ring in coords for c in ring] if coords else []
    if not flat or all(len(c) == 0 for c in flat):
        return []

    properties = data.get("properties") or {}
    color = product.get("color", "#888888")
    label = _parse_surface_label(properties.get("popupContent", ""))

    return [
        {
            "type": "Feature",
            "id": f"{product['id']}-0",
            "geometry": geometry,
            "properties": {
                **properties,
                "color": color,
                "label": label or product["label"],
            },
        }
    ]


def _parse_geojson_fc(raw: str, product: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a FeatureCollection WPC mapdata GeoJSON (ERODay1.geojson style)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    features_in = data.get("features") or []
    features: list[dict[str, Any]] = []
    for index, feature in enumerate(features_in):
        if feature.get("type") != "Feature":
            continue
        props = feature.get("properties") or {}
        color = (
            props.get("fill")
            or props.get("stroke")
            or product.get("color", "#888888")
        )
        label = (
            props.get("LABEL2")
            or props.get("OUTLOOK")
            or props.get("LABEL")
            or props.get("label")
            or ""
        )
        category = props.get("LABEL") or props.get("dn") or ""
        features.append(
            {
                "type": "Feature",
                "id": f"{product['id']}-{index}",
                "geometry": feature.get("geometry"),
                "properties": {
                    **props,
                    "color": color,
                    "label": label,
                    "category": str(category),
                },
            }
        )
    return features


def _process_surface_layer(
    product: dict[str, Any],
    force: bool,
    raw_dir: Path | None,
) -> tuple[int, str]:
    fmt = product.get("format", "png")

    if fmt == "png":
        filename = Path(product["url"]).name
        if raw_dir is not None:
            source_path = raw_dir / filename
            if not source_path.exists():
                return 0, f"raw file missing: {filename}"
            image_bytes = source_path.read_bytes()
            cache_path = CACHE_DIR / product["cache_path"]
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
            tmp.write_bytes(image_bytes)
            tmp.replace(cache_path)
        else:
            png_path = CACHE_DIR / "surface" / filename
            if not _fetch_binary(product["url"], png_path, force):
                return 0, f"{product['id']}: download failed"
            cache_path = png_path  # only used for meta below

        meta_path = (CACHE_DIR / product["cache_path"]).with_suffix(".meta.json")
        meta = _read_json(meta_path) or {}
        payload = {
            "updated": meta.get("last_modified") or meta.get("fetched_at") or _utc_now_iso(),
            "product": product["id"],
            "group": product["group"],
            "days": product["days"],
            "source_url": product["url"],
            "image_url": f"/cache/wpc/surface/{filename}",
            "bounds": product["bounds"],
            "forecast_hour": product.get("forecast_hour"),
        }
        _write_json_atomic(CACHE_DIR / product["cache_path"], payload)
        return 1, ""

    # Vector formats: geojson_single or geojson_fc
    source_filename = Path(product["url"]).name
    if raw_dir is not None:
        source_path = raw_dir / source_filename
        if not source_path.exists():
            return 0, f"raw file missing: {source_filename}"
    else:
        source_path = RAW_DIR / source_filename
        if not _fetch_binary(product["url"], source_path, force):
            return 0, f"{product['id']}: download failed"

    try:
        raw = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, f"{product['id']}: unreadable file"

    if fmt == "geojson_single":
        features = _parse_geojson_single(raw, product)
    else:
        features = _parse_geojson_fc(raw, product)

    _write_layer(
        product["cache_path"],
        product=product,
        features=features,
        source_url=product["url"],
    )
    return len(features), ""


def _parse_sigwx_kml(kml_text: str) -> list[dict[str, Any]]:
    """Parse a WPC SigWx KML into GeoJSON features (flooding/severe/zr/snow)."""
    root = ET.fromstring(kml_text)
    features: list[dict[str, Any]] = []
    for index, placemark in enumerate(
        n for n in root.iter() if _kml_local(n.tag) == "Placemark"
    ):
        style_id = _placemark_style_id(placemark)
        if style_id not in SIGWX_COLORS:
            continue
        geometry = _placemark_multipolygon(placemark)
        if geometry is None:
            continue
        features.append(
            {
                "type": "Feature",
                "id": f"wpc-sigwx-{style_id}-{index}",
                "geometry": geometry,
                "properties": {
                    "category": style_id,
                    "label": SIGWX_CATEGORY_LABEL.get(style_id, style_id),
                    "color": SIGWX_COLORS[style_id],
                    "rank": SIGWX_CATEGORY_RANK.get(style_id, 0),
                },
            }
        )
    features.sort(key=lambda f: f["properties"]["rank"])
    return features


def _parse_sigwx_metadata(kml_text: str) -> dict[str, Any]:
    """Extract authoritative issuance text and the explicit no-areas marker."""
    root = ET.fromstring(kml_text)
    snippet = next(
        (node for node in root.iter() if _kml_local(node.tag) == "Snippet"),
        None,
    )
    snippet_text = (
        re.sub(r"\s+", " ", "".join(snippet.itertext())).strip()
        if snippet is not None
        else ""
    )
    issued_match = re.search(
        r"\b(Issued\s*:?\s*.*?)(?=\s+Valid\b|\Z)",
        snippet_text,
        flags=re.IGNORECASE,
    )
    valid_match = re.search(
        r"\b(Valid\s+.*)\Z",
        snippet_text,
        flags=re.IGNORECASE,
    )
    overlay_names = [
        re.sub(r"\s+", " ", "".join(child.itertext())).strip()
        for overlay in root.iter()
        if _kml_local(overlay.tag) == "GroundOverlay"
        for child in overlay
        if _kml_local(child.tag) == "name"
    ]
    return {
        "issued_text": issued_match.group(1).strip() if issued_match else None,
        "valid_text": valid_match.group(1).strip() if valid_match else None,
        "no_significant_weather": any(
            name.casefold().startswith("no areas of significant weather")
            for name in overlay_names
        ),
    }


_GROUP_PARSERS = {
    "ero": _parse_ero_kml,
    "fop": _parse_fop_kml,
    "qpf": _parse_qpf_kml,
    "sigwx": _parse_sigwx_kml,
    "winter": _parse_winter_kml,
}


def _process_mpd_layer(
    product: dict[str, Any],
    force: bool,
    raw_dir: Path | None,
) -> tuple[int, str]:
    if raw_dir is not None:
        index_path = raw_dir / "mpd_active.html"
        if not index_path.exists():
            return 0, "raw file missing: mpd_active.html"
    else:
        index_path = RAW_DIR / "mpd_active.html"
        if not _fetch_binary(product["url"], index_path, force):
            return 0, "mpd_active: index download failed"

    try:
        index_html = index_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, "mpd_active: unreadable index"

    active_ids = _active_mpd_ids(index_html)
    features: list[dict[str, Any]] = []
    failed_ids: list[str] = []
    for mpd_id in active_ids:
        raw_name = f"MPD_{mpd_id}_final.kmz"
        if raw_dir is not None:
            source_path = raw_dir / raw_name
            if not source_path.exists():
                failed_ids.append(mpd_id)
                continue
        else:
            source_path = RAW_DIR / "mpd" / raw_name
            source_url = f"{product['kml_base_url']}/{raw_name}"
            try:
                if not _fetch_binary(source_url, source_path, force):
                    failed_ids.append(mpd_id)
                    continue
            except urllib.error.HTTPError:
                failed_ids.append(mpd_id)
                continue
        kml_text = _kml_from_kmz(source_path)
        parsed = _parse_mpd_kml(kml_text, mpd_id) if kml_text else []
        if not parsed:
            failed_ids.append(mpd_id)
            continue
        discussion_url = str(parsed[0].get("properties", {}).get("discussion_url") or "")
        valid_start = str(parsed[0].get("properties", {}).get("valid_start") or "")
        try:
            issue_year = datetime.fromisoformat(valid_start).year
        except ValueError:
            issue_year = datetime.now(timezone.utc).year
        modal_url = (
            f"{WPC_BASE_URL}/metwatch/metwatch_mpd_multi.php"
            f"?md={mpd_id}&yr={issue_year}"
        )
        detail_text = ""
        if discussion_url:
            detail_name = f"mcd{mpd_id}.html"
            if raw_dir is not None:
                detail_path = raw_dir / detail_name
            else:
                detail_path = RAW_DIR / "mpd" / detail_name
                try:
                    if not _fetch_binary(discussion_url, detail_path, force):
                        failed_ids.append(mpd_id)
                        continue
                except urllib.error.HTTPError:
                    failed_ids.append(mpd_id)
                    continue
            try:
                detail_text = _discussion_text(
                    detail_path.read_text(encoding="utf-8", errors="replace")
                )
            except OSError:
                detail_text = ""
        if not detail_text:
            failed_ids.append(mpd_id)
            continue
        for feature in parsed:
            properties = feature["properties"]
            category = str(properties.get("category") or "POSSIBLE")
            number = int(properties.get("mpd_number") or int(mpd_id))
            properties.update(
                {
                    "event": f"Mesoscale Precipitation Discussion #{number:04d}",
                    "headline": properties.get("mpd_type"),
                    "short_label": f"MPD #{number:04d}",
                    "description": detail_text,
                    "sent": properties.get("valid_start"),
                    "expires": properties.get("valid_end"),
                    "source_url": modal_url,
                    "senderName": "NWS Weather Prediction Center",
                    "severity": f"Flash Flooding {category.title()}",
                    "urgency": "Immediate",
                    "certainty": category.title(),
                    "parameters": {
                        "flashFloodDetection": [category.title()],
                    },
                }
            )
        features.extend(parsed)

    if failed_ids:
        return 0, f"mpd_active: failed to load MPD(s) {', '.join(failed_ids)}"

    now = datetime.now(timezone.utc)
    active_features = []
    for feature in features:
        valid_end = feature.get("properties", {}).get("valid_end")
        try:
            expires = datetime.fromisoformat(valid_end) if valid_end else None
        except ValueError:
            expires = None
        if expires is None or expires > now:
            active_features.append(feature)
    active_features.sort(
        key=lambda feature: feature.get("properties", {}).get("mpd_number", 0),
        reverse=True,
    )
    _write_layer(
        product["cache_path"],
        product=product,
        features=active_features,
        source_url=product["url"],
        empty_message=product.get("empty_message"),
    )
    return len(active_features), ""


def _process_layer(
    product: dict[str, Any], force: bool, raw_dir: Path | None
) -> tuple[int, str]:
    """Fetch+parse one registry product. Returns (feature_count, error_or_empty)."""
    group = product["group"]
    if group == "mpd":
        return _process_mpd_layer(product, force, raw_dir)
    if group == "surface":
        return _process_surface_layer(product, force, raw_dir)
    parser = _GROUP_PARSERS.get(group)
    if parser is None:
        return 0, f"{group}: no parser"

    source_format = product.get("format", "kmz")
    raw_name = f"{product['id']}.{source_format}"
    if raw_dir is not None:
        source_path = raw_dir / raw_name
        if not source_path.exists():
            return 0, f"raw file missing: {raw_name}"
    else:
        source_path = RAW_DIR / raw_name
        if not _fetch_binary(product["url"], source_path, force):
            return 0, f"{product['id']}: download failed"

    if source_format == "kml":
        try:
            kml_text = source_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            kml_text = None
    else:
        kml_text = _kml_from_kmz(source_path)
    if not kml_text:
        return 0, f"{product['id']}: no readable KML"

    features = parser(kml_text)
    layer_metadata = _parse_sigwx_metadata(kml_text) if group == "sigwx" else None
    discussion_text = ""
    discussion_url = ""
    if group == "ero":
        discussion_url = ERO_DISCUSSION_URL
        all_discussion = _fetch_discussion(
            discussion_url,
            "ero_discussion.html",
            force,
            raw_dir,
        )
        day = int(product.get("day") or 1)
        discussion_text = _ero_discussion_for_day(all_discussion, day)
    elif group == "winter":
        discussion_url = WINTER_DISCUSSION_URL
        discussion_text = _fetch_discussion(
            discussion_url,
            "winter_discussion.html",
            force,
            raw_dir,
        )
    if group in {"ero", "winter"}:
        if not discussion_text:
            return 0, f"{product['id']}: discussion unavailable"
        for feature in features:
            feature["properties"].update(
                {
                    "discussion_text": discussion_text,
                    "discussion_url": discussion_url,
                }
            )
    _write_layer(
        product["cache_path"],
        product=product,
        features=features,
        source_url=product["url"],
        empty_message=product.get("empty_message"),
        metadata=layer_metadata,
    )
    return len(features), ""


def run_wpc_worker(
    force: bool = False,
    raw_dir: Path | None = None,
    product_ids: set[str] | None = None,
) -> None:
    """Refresh all enabled WPC ERO, QPF, and winter layers."""
    if not force and not product_ids and is_cache_fresh("wpc", _FRESH_WINDOW_SEC):
        print("[wpc_worker] Cache fresh — skipping run")
        return

    start = time.time()
    errors: list[str] = []
    total = 0
    any_success = False

    for group, products in WPC_PRODUCTS.items():
        for product in products:
            if product_ids and product["id"] not in product_ids:
                continue
            try:
                count, err = _process_layer(product, force=force, raw_dir=raw_dir)
            except urllib.error.HTTPError as exc:
                status = "unavailable" if exc.code == 404 else "error"
                _write_product_status(
                    product,
                    available=False,
                    status=status,
                    error=str(exc),
                    http_status=exc.code,
                )
                errors.append(f"{product['id']}: HTTP {exc.code}")
                continue
            except Exception as exc:  # noqa: BLE001 - log and continue per product
                _write_product_status(
                    product,
                    available=False,
                    status="error",
                    error=str(exc),
                )
                errors.append(f"{product['id']}: {exc}")
                continue
            if err:
                _write_product_status(
                    product,
                    available=False,
                    status="error",
                    error=err,
                )
                errors.append(err)
                continue
            _write_product_status(
                product,
                available=True,
                status="ok",
            )
            any_success = True
            total += count
            print(f"[wpc_worker] {product['id']}: {count} feature(s)")

    if any_success and not product_ids:
        mark_run_complete("wpc")
    elif any_success:
        print("[wpc_worker] Targeted refresh complete — global freshness unchanged")
    else:
        print("[wpc_worker] No layer succeeded — cache not marked fresh")

    print(
        f"[wpc_worker] Complete in {time.time() - start:.2f}s "
        f"({total} feature(s), {len(errors)} error(s))"
    )
    for err in errors:
        print(f"[wpc_worker] {err}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the WPC cache worker once.")
    parser.add_argument("--force", action="store_true", help="Bypass freshness gate.")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        help="Read local registry-named KMZ/KML files instead of fetching live.",
    )
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to cache/logs/scheduled/wpc.log.",
    )
    args = parser.parse_args()
    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("wpc")
    run_wpc_worker(force=args.force, raw_dir=args.raw_dir)
