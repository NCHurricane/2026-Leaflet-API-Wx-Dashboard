"""Tropical GIS and advisory parsing contracts shared by live and archive paths."""

from __future__ import annotations

import fnmatch
import io
import json
import re
import warnings
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_core.atomic_io import atomic_write_json

try:
    import shapefile
    shapefile.VERBOSE = False
except ImportError:  # pragma: no cover - optional dependency guard
    shapefile = None

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "tropical"

FIVE_DAY_LAYER_KINDS = {
    "cone": "_5day_pgn.shp",
    "forecast_track": "_5day_lin.shp",
    "forecast_points": "_5day_pts.shp",
    "watches_warnings": "_ww_wwlin.shp",
}

FORECAST_WIND_RADII_LAYER_KINDS = {
    "wind_radii": "*_forecastradii.shp",
}

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _json_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    return str(value)

def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(
        path,
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    )

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

def _feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}

def _shapefile_feature_collection_from_zip(zip_path: Path, shp_suffix: str) -> dict[str, Any] | None:
    if shapefile is None:
        return None
    try:
        with zipfile.ZipFile(zip_path) as zf:
            # Support both literal suffixes (_5day_pgn.shp) and wildcard patterns (*_forecastradii.shp)
            pattern = f"*{shp_suffix}" if not shp_suffix.startswith("*") else shp_suffix
            shp_name = next((name for name in zf.namelist() if fnmatch.fnmatch(name.lower(), pattern.lower())), "")
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

def _kml_local(tag: str) -> str:
    """Strip the XML namespace from a KML element tag."""
    return tag.split("}")[-1]

def _kml_find(elem: ET.Element | None, name: str) -> ET.Element | None:
    if elem is None:
        return None
    for child in elem:
        if _kml_local(child.tag) == name:
            return child
    return None

def _kml_findtext(elem: ET.Element | None, name: str) -> str:
    child = _kml_find(elem, name)
    return (child.text or "").strip() if child is not None and child.text else ""

def _kml_first_descendant(elem: ET.Element, name: str) -> ET.Element | None:
    for node in elem.iter():
        if _kml_local(node.tag) == name:
            return node
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

def _kml_geometry(placemark: ET.Element) -> dict[str, Any] | None:
    polygon = _kml_first_descendant(placemark, "Polygon")
    if polygon is not None:
        ring_el = _kml_first_descendant(polygon, "coordinates")
        ring = _parse_kml_coords(ring_el.text if ring_el is not None else "")
        if len(ring) >= 3:
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            return {"type": "Polygon", "coordinates": [ring]}
    line = _kml_first_descendant(placemark, "LineString")
    if line is not None:
        line_el = _kml_first_descendant(line, "coordinates")
        pts = _parse_kml_coords(line_el.text if line_el is not None else "")
        if len(pts) >= 2:
            return {"type": "LineString", "coordinates": pts}
    point = _kml_first_descendant(placemark, "Point")
    if point is not None:
        pt_el = _kml_first_descendant(point, "coordinates")
        pts = _parse_kml_coords(pt_el.text if pt_el is not None else "")
        if pts:
            return {"type": "Point", "coordinates": pts[0]}
    return None

def parse_storm_surge_kml(kml_text: str) -> dict[str, Any] | None:
    """Parse storm surge watch/warning KML: extract all placemarks as GeoJSON polygons."""
    try:
        root = _xml_root(kml_text)
    except ET.ParseError:
        return None

    features: list[dict[str, Any]] = []
    for placemark in (n for n in root.iter() if _kml_local(n.tag) == "Placemark"):
        geometry = _kml_geometry(placemark)
        if geometry is None or geometry.get("type") != "Polygon":
            continue
        name = _kml_findtext(placemark, "name")
        features.append(
            {
                "type": "Feature",
                "properties": {"name": name or "Storm Surge Watch/Warning"},
                "geometry": geometry,
            }
        )
    return _feature_collection(features) if features else None

def parse_peak_surge_kml(kml_text: str) -> dict[str, Any] | None:
    """Parse peak storm surge KML: extract all geometry (polygons, lines, points) with peak_surge_range + color."""
    try:
        root = _xml_root(kml_text)
    except ET.ParseError:
        return None

    features: list[dict[str, Any]] = []
    for placemark in (n for n in root.iter() if _kml_local(n.tag) == "Placemark"):
        geometry = _kml_geometry(placemark)
        if geometry is None:
            continue
        geom_type = geometry.get("type", "")
        # Keep Polygons (surge zones), LineStrings (boundaries), and Points (breakpoints)
        if geom_type not in ("Polygon", "LineString", "Point"):
            continue

        name = _kml_findtext(placemark, "name")
        desc = _kml_findtext(placemark, "description")

        # Parse JSON description to extract peak_surge_range and color (for polygons/lines)
        peak_range = ""
        color = "#9ca3af"  # default gray
        feature_type = "breakpoint" if geom_type == "Point" else geom_type.lower()

        if desc:
            try:
                desc_json = json.loads(desc)
                peak_range = desc_json.get("peak_surge_range", "")
                color = desc_json.get("color", "#9ca3af")
            except (json.JSONDecodeError, ValueError):
                # For points, description is just the location name
                pass

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": name or "Peak Storm Surge",
                    "peak_surge_range": peak_range,
                    "color": color,
                    "feature_type": feature_type,
                },
                "geometry": geometry,
            }
        )
    return _feature_collection(features) if features else None

_INITIAL_WIND_COLORS = {
    "34": "#facc15",  # 34 kt (gale)
    "50": "#fb923c",  # 50 kt (storm)
    "64": "#ef4444",  # 64 kt (hurricane)
}

def parse_initial_wind_extent_kml(kml_text: str) -> dict[str, Any] | None:
    try:
        root = _xml_root(kml_text)
    except ET.ParseError:
        return None
    features: list[dict[str, Any]] = []
    for placemark in (n for n in root.iter() if _kml_local(n.tag) == "Placemark"):
        geometry = _kml_geometry(placemark)
        if geometry is None or geometry.get("type") != "Polygon":
            continue
        name = (_kml_findtext(placemark, "name") or "").strip()
        if name not in _INITIAL_WIND_COLORS:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "windField": name,
                    "label": f"{name} kt wind extent",
                    "color": _INITIAL_WIND_COLORS[name],
                },
                "geometry": geometry,
            }
        )
    return _feature_collection(features) if features else None

def extract_gis_layers_from_zip(
    zip_path: Path,
    kinds: dict[str, str],
    storm_id: str,
    layer_dir: Path,
) -> dict[str, Any]:
    layers: dict[str, Any] = {}
    for layer_id, shp_suffix in kinds.items():
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

def _coord(value: str, hemi: str) -> float | None:
    try:
        parsed = float(value)
    except ValueError:
        return None
    return -parsed if hemi.upper() in {"S", "W"} else parsed

def parse_advisory(text: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    summary = re.search(
        r"SUMMARY OF .*?INFORMATION\s*-+\s*(.*?)(?:\n\s*\n|WATCHES AND WARNINGS|DISCUSSION AND OUTLOOK)",
        text,
        re.I | re.S,
    )
    block = summary.group(1) if summary else text
    loc = re.search(r"LOCATION\.*\s*([0-9.]+)([NS])\s+([0-9.]+)([EW])(.*?)(?=\n[A-Z\s]+\.\.\.|$)", block, re.I | re.S)
    if loc:
        # Extract coordinate and description text
        coord_lat = _coord(loc.group(1), loc.group(2))
        coord_lon = _coord(loc.group(3), loc.group(4))
        desc_text = loc.group(5).strip() if loc.group(5) else ""
        # Clean up description text (remove extra whitespace, join lines)
        desc_text = " ".join(desc_text.split())
        parsed["location"] = {
            "lat": coord_lat,
            "lon": coord_lon,
            "latText": f"{loc.group(1)}{loc.group(2).upper()}",
            "lonText": f"{loc.group(3)}{loc.group(4).upper()}",
            "text": desc_text,
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

def parse_track(text: str) -> list[dict[str, Any]]:
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
