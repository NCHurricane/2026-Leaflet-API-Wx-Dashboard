import csv
import html
import io
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from dateutil import tz

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import requests
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.patches import Rectangle
from matplotlib.colors import to_rgba

from city_utils import plot_cities
from config.geo_config import STATE_BOUNDS, STATES_FULL
from font_utils import register_montserrat_fonts
from geo_utils import CensusCounties, load_state_geometries
from listing_cache import cached_call

register_montserrat_fonts()

# Match SPC-style heavier hatch strokes.
plt.rcParams["hatch.linewidth"] = 2.0

SPC_BASE = "https://www.spc.noaa.gov"

_DAY12_HAZARDS = {"cat", "torn", "wind",
                  "hail", "sigtorn", "sigwind", "sighail"}
_DAY3_HAZARDS = {"cat", "prob", "sig"}

# Layered UI opacities for these overlays are intentionally fixed.
LAYER_OPACITY_CITIES = 1.0
LAYER_OPACITY_HUD = 1.0

_SPC_OUTPUT_MAX_WIDTH = 12.8
_SPC_OUTPUT_MAX_HEIGHT = 7.2
_SPC_OUTPUT_DPI = 150


def _to_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"", "0", "false", "no", "off"}


def _responsive_text_scale(fig, style_config: Optional[dict] = None) -> float:
    style_config = style_config or {}
    if not _to_bool(style_config.get("responsive_text_enabled", True), True):
        return 1.0

    explicit_scale = style_config.get("responsive_text_scale")
    if explicit_scale is not None:
        try:
            parsed = float(explicit_scale)
            if parsed > 0:
                return parsed
        except (TypeError, ValueError):
            pass

    width_in, height_in = fig.get_size_inches()
    width_ratio = max(1e-6, float(width_in) / _SPC_OUTPUT_MAX_WIDTH)
    height_ratio = max(1e-6, float(height_in) / _SPC_OUTPUT_MAX_HEIGHT)
    raw_scale = (width_ratio * height_ratio) ** 0.5

    try:
        min_scale = float(style_config.get("responsive_text_min_scale", 0.78))
    except (TypeError, ValueError):
        min_scale = 0.78
    try:
        max_scale = float(style_config.get("responsive_text_max_scale", 1.15))
    except (TypeError, ValueError):
        max_scale = 1.15

    if min_scale > max_scale:
        min_scale, max_scale = max_scale, min_scale

    return max(min_scale, min(max_scale, raw_scale))


def _request_text(url: str, timeout: int = 20, retries: int = 3) -> str:
    last_error = None
    for _ in range(max(1, retries)):
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = RuntimeError(
                    f"HTTP {response.status_code} for {url}")
                continue
            response.raise_for_status()
            return response.text
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Unable to fetch {url}: {last_error}")


def _request_json(url: str, timeout: int = 20, retries: int = 3):
    text = _request_text(url, timeout=timeout, retries=retries)
    return requests.models.complexjson.loads(text)


def _cached_text(namespace: str, key: str, url: str, ttl_seconds: int = 90) -> str:
    return cached_call(
        namespace,
        key,
        lambda: _request_text(url),
        ttl_seconds=ttl_seconds,
    )


def _clean_spc_text(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", raw)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned


def _format_hud_time(iso_text: str, display_tz=None) -> str:
    raw = str(iso_text or "").strip()
    if not raw:
        return "N/A"
    try:
        stamp = datetime.fromisoformat(raw)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        target_tz = display_tz or timezone.utc
        stamp = stamp.astimezone(target_tz)
        tz_abbr = stamp.strftime("%Z") or "LOCAL"
        return stamp.strftime(f"%b %d %Y %I:%M %p {tz_abbr}")
    except ValueError:
        return raw


def _resolve_display_tz(user_tz: Optional[str]):
    tz_name = str(user_tz or "").strip() or "America/New_York"
    display_tz = tz.gettz(tz_name)
    if display_tz is None:
        display_tz = tz.gettz("America/New_York")
    return display_tz


def _current_outlook_url(day: int, hazard: str) -> str:
    hazard = (hazard or "cat").strip().lower()
    if day in (1, 2):
        if hazard not in _DAY12_HAZARDS:
            hazard = "cat"
        return f"{SPC_BASE}/products/outlook/day{day}otlk_{hazard}.nolyr.geojson"
    if day == 3:
        if hazard not in _DAY3_HAZARDS:
            hazard = "cat"
        return f"{SPC_BASE}/products/outlook/day3otlk_{hazard}.nolyr.geojson"
    if day in (4, 5, 6, 7, 8):
        return f"{SPC_BASE}/products/exper/day4-8/day{day}prob.nolyr.geojson"
    raise ValueError("day must be between 1 and 8")


def _report_csv_url(
    report_date_utc: Optional[datetime],
    report_mode: str,
    report_type: str = "all",
) -> str:
    mode = (report_mode or "filtered").strip().lower()
    type_key = (report_type or "all").strip().lower()
    type_suffix = "" if type_key in {"", "all"} else f"_{type_key}"

    def _suffix_for_mode(mode_name: str) -> str:
        if mode_name == "raw":
            return "_raw"
        if mode_name == "all":
            return ""
        return "_filtered"

    suffix = _suffix_for_mode(mode)

    if report_date_utc is None:
        return f"{SPC_BASE}/climo/reports/yesterday{suffix}{type_suffix}.csv"

    report_day = report_date_utc.astimezone(timezone.utc).date()
    today_utc = datetime.now(timezone.utc).date()
    if report_day == today_utc:
        return f"{SPC_BASE}/climo/reports/today{suffix}{type_suffix}.csv"
    if report_day == (today_utc - timedelta(days=1)):
        return f"{SPC_BASE}/climo/reports/yesterday{suffix}{type_suffix}.csv"

    token = report_date_utc.astimezone(timezone.utc).strftime("%y%m%d")
    if mode == "raw":
        return f"{SPC_BASE}/climo/reports/{token}_rpts_raw{type_suffix}.csv"
    if mode == "all":
        return f"{SPC_BASE}/climo/reports/{token}_rpts{type_suffix}.csv"
    return f"{SPC_BASE}/climo/reports/{token}_rpts_filtered{type_suffix}.csv"


def _coerce_lat_lon(value: str, is_lon: bool = False) -> Optional[float]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    try:
        number = float(raw)
    except ValueError:
        return None

    if "." not in raw and abs(number) > 180:
        number = number / 100.0

    if is_lon and number > 0:
        number = -number

    return number


def fetch_outlook_geojson(day: int, hazard: str):
    url = _current_outlook_url(day, hazard)
    payload = _request_json(url)
    return payload, "SPC GeoJSON"


# ── Fire Weather Outlook helpers ────────────────────────────────────────────
_FIRE_WX_HAZARDS = {"dryt", "windrh"}

# NWS MapServer layer IDs for Day 3-8 fire weather (each day has a group
# layer followed by DryT then WindRH sub-layers).
_FIRE_WX_MAPSERVER = (
    "https://mapservices.weather.noaa.gov/vector/rest/services"
    "/fire_weather/SPC_firewx/MapServer"
)
_FIRE_WX_LAYER_IDS = {
    # day -> {hazard -> layer_id}
    3: {"dryt": 7, "windrh": 8},
    4: {"dryt": 10, "windrh": 11},
    5: {"dryt": 13, "windrh": 14},
    6: {"dryt": 16, "windrh": 17},
    7: {"dryt": 19, "windrh": 20},
    8: {"dryt": 22, "windrh": 23},
}


def _fire_wx_url(day: int, hazard: str) -> str:
    """Build GeoJSON URL for SPC Fire Weather Outlook (Day 1-8)."""
    hazard = (hazard or "windrh").strip().lower()
    if hazard not in _FIRE_WX_HAZARDS:
        hazard = "windrh"
    if day in (1, 2):
        return f"{SPC_BASE}/products/fire_wx/day{day}fw_{hazard}.nolyr.geojson"
    if day in _FIRE_WX_LAYER_IDS:
        layer_id = _FIRE_WX_LAYER_IDS[day][hazard]
        return (
            f"{_FIRE_WX_MAPSERVER}/{layer_id}/query"
            f"?where=1%3D1&outFields=*&f=geojson"
        )
    raise ValueError("Fire weather outlooks require day 1-8")


def fetch_fire_wx_geojson(day: int, hazard: str):
    """Fetch fire weather outlook GeoJSON. Returns (geojson_dict, source_str)."""
    url = _fire_wx_url(day, hazard)
    payload = _request_json(url)
    return payload, "SPC Fire Wx GeoJSON"


def _significant_overlay_url(day: int, hazard: str) -> Optional[str]:
    hazard = (hazard or "").strip().lower()
    if day in (1, 2):
        if hazard == "torn":
            return f"{SPC_BASE}/products/outlook/day{day}otlk_sigtorn.nolyr.geojson"
        if hazard == "wind":
            return f"{SPC_BASE}/products/outlook/day{day}otlk_sigwind.nolyr.geojson"
        if hazard == "hail":
            return f"{SPC_BASE}/products/outlook/day{day}otlk_sighail.nolyr.geojson"
    if day == 3 and hazard == "prob":
        return f"{SPC_BASE}/products/outlook/day3otlk_sig.nolyr.geojson"
    return None


def fetch_significant_geojson(day: int, hazard: str):
    sig_url = _significant_overlay_url(day, hazard)
    if not sig_url:
        return None
    try:
        return _request_json(sig_url)
    except Exception:
        return None


def _parse_lat_lon_block(text: str):
    if not text:
        return []

    match = re.search(
        r"LAT\.\.\.LON\s+(.+?)(?:\n\s*\n|\Z)", text, re.IGNORECASE | re.DOTALL
    )
    if not match:
        return []

    number_tokens = re.findall(r"\d{8}", match.group(1))
    points = []
    for token in number_tokens:
        lat = int(token[:4]) / 100.0
        lon = -(int(token[4:]) / 100.0)
        points.append((lon, lat))

    if len(points) < 3:
        return []

    deduped = []
    for point in points:
        if deduped and point == deduped[-1]:
            continue
        deduped.append(point)

    if len(deduped) >= 3 and deduped[0] != deduped[-1]:
        deduped.append(deduped[0])
    return deduped


def _parse_watch_county_fips_from_wou(wou_text: str):
    if not wou_text:
        return []

    CensusCounties.load()
    statefp_by_usps = {}
    for record in getattr(CensusCounties, "_records_map", {}).values():
        attrs = getattr(record, "attributes", {}) or {}
        usps = str(attrs.get("STUSPS", "")).strip().upper()
        statefp = str(attrs.get("STATEFP", "")).strip()
        if usps and statefp and usps not in statefp_by_usps:
            statefp_by_usps[usps] = statefp

    normalized = re.sub(r"\s+", "", wou_text.upper())
    county_fips = set()

    for match in re.finditer(r"([A-Z]{3}\d{3}(?:-\d{3})*-\d{6}-)", normalized):
        token = match.group(1)
        parts = [p for p in token.split("-") if p]
        if not parts:
            continue

        first = parts[0]
        prefix = first[:3]
        if len(prefix) != 3 or prefix[2] != "C":
            # Only county UGC groups are relevant for county shading.
            continue

        usps = prefix[:2]
        statefp = statefp_by_usps.get(usps)
        if not statefp:
            continue

        county_codes = []
        if len(first) == 6 and first[3:].isdigit():
            county_codes.append(first[3:])

        for part in parts[1:]:
            if len(part) == 6 and part.isdigit():
                break
            if len(part) == 3 and part.isdigit():
                county_codes.append(part)

        for county_code in county_codes:
            county_fips.add(f"{statefp}{county_code}")

    return sorted(county_fips)


def _parse_watch_window_from_wou(wou_text: str):
    text = str(wou_text or "")
    match = re.search(r"\.(\d{6}T\d{4})Z-(\d{6}T\d{4})Z/", text)
    if not match:
        return None, None
    try:
        start_utc = datetime.strptime(match.group(1), "%y%m%dT%H%M").replace(
            tzinfo=timezone.utc
        )
        end_utc = datetime.strptime(match.group(2), "%y%m%dT%H%M").replace(
            tzinfo=timezone.utc
        )
        return start_utc, end_utc
    except Exception:
        return None, None


def _parse_watch_probability_table(wwp_text: str):
    text = str(wwp_text or "")
    probabilities = {}
    if "PROBABILITY TABLE" not in text.upper():
        return probabilities

    patterns = {
        "tor2": r"PROB\s+OF\s+2\s+OR\s+MORE\s+TORNADOES\s*:\s*([^\n\r]+)",
        "tor_strong": r"PROB\s+OF\s+1\s+OR\s+MORE\s+STRONG\s+/EF2-EF5/\s+TORNADOES\s*:\s*([^\n\r]+)",
        "wind10": r"PROB\s+OF\s+10\s+OR\s+MORE\s+SEVERE\s+WIND\s+EVENTS\s*:\s*([^\n\r]+)",
        "wind65": r"PROB\s+OF\s+1\s+OR\s+MORE\s+WIND\s+EVENTS\s*>?=\s*65\s+KNOTS\s*:\s*([^\n\r]+)",
        "hail10": r"PROB\s+OF\s+10\s+OR\s+MORE\s+SEVERE\s+HAIL\s+EVENTS\s*:\s*([^\n\r]+)",
        "hail2": r"PROB\s+OF\s+1\s+OR\s+MORE\s+HAIL\s+EVENTS\s*>?=\s*2\s+INCHES\s*:\s*([^\n\r]+)",
        "combined6": r"PROB\s+OF\s+6\s+OR\s+MORE\s+COMBINED\s+SEVERE\s+HAIL/WIND\s+EVENTS\s*:\s*([^\n\r]+)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            probabilities[key] = str(match.group(1)).strip()

    return probabilities


def _watch_probability_hud_lines(probabilities: dict):
    probs = probabilities or {}
    line1_parts = []
    line2_parts = []
    line3_parts = []

    if probs.get("tor2"):
        line1_parts.append(f"2+ Tor: {probs['tor2']}")
    if probs.get("tor_strong"):
        line1_parts.append(f"EF2+: {probs['tor_strong']}")

    if probs.get("wind65"):
        line2_parts.append(f"Wind65kt: {probs['wind65']}")
    if probs.get("hail2"):
        line2_parts.append(f"Hail2in: {probs['hail2']}")

    if probs.get("combined6"):
        line3_parts.append(f"Combined: {probs['combined6']}")

    lines = []
    if line1_parts:
        lines.append(" | ".join(line1_parts))
    if line2_parts:
        lines.append(" | ".join(line2_parts))
    if line3_parts:
        lines.append(" | ".join(line3_parts))
    return lines


def _parse_md_reference_date(detail_text: str):
    text = re.sub(r"\s+", " ", str(detail_text or "")).strip()
    match = re.search(
        r"\b(?:AM|PM)\s+[A-Z]{2,4}\s+\w{3}\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{4})",
        text,
    )
    if not match:
        return None
    try:
        month = datetime.strptime(match.group(1), "%b").month
        day = int(match.group(2))
        year = int(match.group(3))
        return datetime(year, month, day, tzinfo=timezone.utc)
    except Exception:
        return None


def _parse_md_valid_window(detail_text: str):
    text = re.sub(r"\s+", " ", str(detail_text or "")).strip()
    match = re.search(
        r"\bValid\s+(\d{2})(\d{2})(\d{2})Z\s*-\s*(\d{2})(\d{2})(\d{2})Z",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None, None

    ref_date = _parse_md_reference_date(detail_text)
    if ref_date is None:
        ref_date = datetime.now(timezone.utc)

    try:
        d1, h1, m1 = int(match.group(1)), int(
            match.group(2)), int(match.group(3))
        d2, h2, m2 = int(match.group(4)), int(
            match.group(5)), int(match.group(6))

        start_utc = ref_date.replace(
            day=d1, hour=h1, minute=m1, second=0, microsecond=0
        )
        end_utc = ref_date.replace(
            day=d2, hour=h2, minute=m2, second=0, microsecond=0)
        return start_utc, end_utc
    except Exception:
        return None, None


def _extract_watch_type(detail_text: str, fallback_title: str = "") -> str:
    content = f"{detail_text or ''} {fallback_title or ''}".upper()
    if "TORNADO WATCH" in content:
        return "Tornado Watch"
    if "SEVERE THUNDERSTORM WATCH" in content:
        return "Severe Thunderstorm Watch"
    return "Watch"


def fetch_active_watch_items(ttl_seconds: int = 90):
    listing_url = f"{SPC_BASE}/products/watch/"
    listing_html = _cached_text(
        "spc_watch_listing", "active", listing_url, ttl_seconds)

    watch_ids = []
    seen = set()
    for match in re.finditer(
        r"/products/watch/(?:\d{4}/)?ww(\d{4})\.html", listing_html, re.IGNORECASE
    ):
        watch_id = match.group(1)
        if watch_id in seen:
            continue
        seen.add(watch_id)
        watch_ids.append(watch_id)

    items = []
    for watch_id in watch_ids[:24]:
        detail_url = f"{SPC_BASE}/products/watch/ww{watch_id}.html"
        try:
            detail_text = _cached_text(
                "spc_watch_detail", watch_id, detail_url, ttl_seconds
            )
        except Exception:
            continue

        polygon = _parse_lat_lon_block(detail_text)
        county_fips = []
        issue_utc = None
        expire_utc = None
        watch_probabilities = {}

        wou_match = re.search(
            r'href="((?:/products/watch/)?wou\d{4}\.(?:html|txt))"',
            detail_text,
            re.IGNORECASE,
        )
        if wou_match:
            wou_rel = wou_match.group(1)
            if wou_rel.startswith("http://") or wou_rel.startswith("https://"):
                wou_url = wou_rel
            elif wou_rel.startswith("/"):
                wou_url = f"{SPC_BASE}{wou_rel}"
            else:
                wou_url = f"{SPC_BASE}/products/watch/{wou_rel}"
            try:
                wou_text = _cached_text(
                    "spc_watch_wou", watch_id, wou_url, ttl_seconds)
                county_fips = _parse_watch_county_fips_from_wou(wou_text)
                issue_utc, expire_utc = _parse_watch_window_from_wou(wou_text)
                if not polygon:
                    polygon = _parse_lat_lon_block(wou_text)
            except Exception:
                county_fips = []

        if not polygon and not county_fips:
            continue

        wwp_url = f"{SPC_BASE}/products/watch/wwp{watch_id}.txt"
        try:
            wwp_text = _cached_text(
                "spc_watch_wwp", watch_id, wwp_url, ttl_seconds)
            watch_probabilities = _parse_watch_probability_table(wwp_text)
        except Exception:
            watch_probabilities = {}

        watch_num = str(int(watch_id))
        watch_type = _extract_watch_type(detail_text)
        concerning_match = re.search(
            r"Concerning\.\.\.(.+?)\n", detail_text, re.IGNORECASE
        )
        concerning_text = ""
        if concerning_match:
            concerning_text = _clean_spc_text(concerning_match.group(1))

        label = f"{watch_type} #{watch_num}"
        if concerning_text:
            label = f"{label} - {concerning_text}"

        # Skip expired watches
        if expire_utc and expire_utc < datetime.now(timezone.utc):
            continue

        items.append(
            {
                "id": watch_id,
                "title": f"{watch_type} #{watch_num}",
                "label": label,
                "short_label": f"WW #{watch_num}",
                "polygon": polygon,
                "county_fips": county_fips,
                "issue_utc": issue_utc,
                "expire_utc": expire_utc,
                "probabilities": watch_probabilities,
            }
        )

    return items, "SPC Watches"


def fetch_active_watch_options(ttl_seconds: int = 90):
    listing_url = f"{SPC_BASE}/products/watch/"
    listing_html = _cached_text(
        "spc_watch_listing", "active", listing_url, ttl_seconds)

    items = []
    seen = set()
    for match in re.finditer(
        r'<strong><a\s+href="/products/watch/ww(\d{4})\.html">([^<]+)</a></strong>',
        listing_html,
        re.IGNORECASE,
    ):
        watch_id = match.group(1)
        if watch_id in seen:
            continue
        seen.add(watch_id)

        label = _clean_spc_text(match.group(2)) or f"Watch #{int(watch_id)}"
        items.append(
            {
                "id": watch_id,
                "label": label,
            }
        )

    return items, "SPC Watches"


def fetch_active_md_items(ttl_seconds: int = 90):
    listing_url = f"{SPC_BASE}/products/md/"
    listing_html = _cached_text(
        "spc_md_listing", "active", listing_url, ttl_seconds)

    md_ids = []
    seen = set()
    for match in re.finditer(
        r"/products/md/md(\d{4})\.html", listing_html, re.IGNORECASE
    ):
        md_id = match.group(1)
        if md_id in seen:
            continue
        seen.add(md_id)
        md_ids.append(md_id)

    items = []
    for md_id in md_ids[:32]:
        detail_url = f"{SPC_BASE}/products/md/md{md_id}.html"
        try:
            detail_text = _cached_text(
                "spc_md_detail", md_id, detail_url, ttl_seconds)
        except Exception:
            continue

        polygon = _parse_lat_lon_block(detail_text)
        if not polygon:
            continue

        issue_utc, expire_utc = _parse_md_valid_window(detail_text)

        md_num = str(int(md_id))
        concerning_match = re.search(
            r"Concerning\.\.\.(.+?)\n", detail_text, re.IGNORECASE
        )
        concerning_text = ""
        if concerning_match:
            concerning_text = _clean_spc_text(concerning_match.group(1))

        label = f"Mesoscale Discussion #{md_num}"
        if concerning_text:
            label = f"{label} - {concerning_text}"

        # Skip expired MDs
        if expire_utc and expire_utc < datetime.now(timezone.utc):
            continue

        items.append(
            {
                "id": md_id,
                "label": label,
                "short_label": f"MD #{md_num}",
                "polygon": polygon,
                "issue_utc": issue_utc,
                "expire_utc": expire_utc,
            }
        )

    return items, "SPC Mesoscale Discussions"


def fetch_active_md_options(ttl_seconds: int = 90):
    listing_url = f"{SPC_BASE}/products/md/"
    listing_html = _cached_text(
        "spc_md_listing", "active", listing_url, ttl_seconds)

    items = []
    seen = set()
    for match in re.finditer(
        r'<a\s+href="/products/md/md(\d{4})\.html">\s*Mesoscale Discussion\s*#\s*0*(\d+)\s*</a>',
        listing_html,
        re.IGNORECASE,
    ):
        md_id = match.group(1)
        if md_id in seen:
            continue
        seen.add(md_id)

        md_num = str(int(match.group(2)))
        items.append(
            {
                "id": md_id,
                "label": f"Mesoscale Discussion #{md_num}",
            }
        )

    return items, "SPC Mesoscale Discussions"


def _draw_polygon_items_layer(
    ax,
    items,
    edge_color,
    fill_color,
    fill_alpha,
    linewidth,
    label_size,
    label_color,
):
    for item in items:
        polygon = item.get("polygon") or []
        if len(polygon) < 3:
            continue

        xs = [pt[0] for pt in polygon]
        ys = [pt[1] for pt in polygon]
        ax.fill(
            xs,
            ys,
            facecolor=to_rgba(fill_color, fill_alpha),
            edgecolor=to_rgba(edge_color, 1.0),
            linewidth=linewidth,
            transform=ccrs.PlateCarree(),
            zorder=54,
        )


def _draw_watch_county_items_layer(
    ax,
    items,
    edge_color,
    fill_color,
    fill_alpha,
    linewidth,
    label_size,
    label_color,
):
    CensusCounties.load()
    fips_map = getattr(CensusCounties, "_fips_map", {})

    for item in items:
        county_fips = item.get("county_fips") or []
        county_geoms = [fips_map.get(fips)
                        for fips in county_fips if fips in fips_map]
        county_geoms = [geom for geom in county_geoms if geom is not None]

        if not county_geoms:
            # Fallback to polygon rendering if county list is unavailable.
            _draw_polygon_items_layer(
                ax,
                [item],
                edge_color=edge_color,
                fill_color=fill_color,
                fill_alpha=fill_alpha,
                linewidth=linewidth,
                label_size=label_size,
                label_color=label_color,
            )
            continue

        ax.add_geometries(
            county_geoms,
            crs=ccrs.PlateCarree(),
            facecolor=to_rgba(fill_color, fill_alpha),
            edgecolor=to_rgba(edge_color, 1.0),
            linewidth=linewidth,
            zorder=54,
        )


def _build_spc_item_layers(
    *,
    items,
    layer_prefix,
    group,
    make_fig_ax,
    save_layer,
    edge_color,
    fill_color,
    fill_alpha,
    linewidth,
    label_size,
    label_color,
    default_visible,
    sort_base,
    renderer=None,
):
    layer_paths = {}
    layer_defs = []

    for idx, item in enumerate(items):
        item_id = str(item.get("id") or f"{idx + 1:04d}")
        layer_id = f"{layer_prefix}_{item_id}"

        fig_item, ax_item = make_fig_ax()
        draw_fn = renderer or _draw_polygon_items_layer
        draw_fn(
            ax_item,
            [item],
            edge_color=edge_color,
            fill_color=fill_color,
            fill_alpha=fill_alpha,
            linewidth=linewidth,
            label_size=label_size,
            label_color=label_color,
        )
        layer_paths[layer_id] = save_layer(fig_item, layer_id)
        layer_defs.append(
            {
                "id": layer_id,
                "label": item.get("label") or layer_id,
                "group": group,
                "default_visible": default_visible,
                "default_opacity": 1.0,
                "sort": sort_base + idx,
            }
        )

    return layer_paths, layer_defs


def fetch_reports_rows(
    report_date_utc: Optional[datetime],
    report_mode: str = "filtered",
    report_type: str = "all",
):
    type_key = (report_type or "all").strip().lower()
    text = ""
    last_error = None
    used_typed_url = False
    candidate_dates = [report_date_utc]
    if report_date_utc is not None:
        # "today" files may not be posted yet; fall back to prior day token.
        candidate_dates.append(report_date_utc - timedelta(days=1))

    for candidate_date in candidate_dates:
        candidate_urls = [_report_csv_url(
            candidate_date, report_mode, type_key)]
        if type_key not in {"", "all"}:
            mode_key = (report_mode or "filtered").strip().lower()
            if mode_key == "filtered":
                candidate_urls.append(_report_csv_url(
                    candidate_date, "all", type_key))
            elif mode_key == "all":
                candidate_urls.append(
                    _report_csv_url(candidate_date, "filtered", type_key)
                )
            candidate_urls.append(_report_csv_url(
                candidate_date, report_mode, "all"))

        deduped_urls = []
        seen_urls = set()
        for candidate_url in candidate_urls:
            if candidate_url in seen_urls:
                continue
            seen_urls.add(candidate_url)
            deduped_urls.append(candidate_url)

        for idx, url in enumerate(deduped_urls):
            try:
                text = _request_text(url)
                used_typed_url = idx == 0 and type_key not in {"", "all"}
                break
            except Exception as exc:
                last_error = exc
                continue
        if text:
            break

    if not text:
        raise RuntimeError(
            f"Unable to fetch SPC reports for mode={report_mode}: {last_error}"
        )

    parsed = []

    def _matches_requested_type(event_name: str, requested_type: str) -> bool:
        req = (requested_type or "all").strip().lower()
        if req in {"", "all"}:
            return True
        ev = (event_name or "").strip().lower()
        if req == "torn":
            return "torn" in ev
        if req == "wind":
            return "wind" in ev
        if req == "hail":
            return "hail" in ev
        return True

    reader = csv.reader(io.StringIO(text))
    header_map = {}
    section_event = ""

    def _event_from_second_header(second_col: str) -> str:
        key = str(second_col or "").strip().lower()
        if key == "f_scale":
            return "Tornado"
        if key == "speed":
            return "Wind"
        if key == "size":
            return "Hail"
        return ""

    for row in reader:
        if not row:
            continue

        normalized = [str(col or "").strip() for col in row]
        if not any(normalized):
            continue

        if normalized[0].lower() == "time":
            header_map = {name.lower(): idx for idx,
                          name in enumerate(normalized)}
            section_event = _event_from_second_header(
                normalized[1] if len(normalized) > 1 else ""
            )
            continue

        if not header_map:
            continue

        def _val(field_name: str) -> str:
            idx = header_map.get(field_name.lower())
            if idx is None or idx >= len(normalized):
                return ""
            return normalized[idx]

        lat = _coerce_lat_lon(_val("Lat"), is_lon=False)
        lon = _coerce_lat_lon(_val("Lon"), is_lon=True)
        if lat is None or lon is None:
            continue

        event_name = _val("Type") or _val("Event") or section_event
        if (
            type_key not in {"", "all"}
            and not used_typed_url
            and not _matches_requested_type(event_name, type_key)
        ):
            continue

        magnitude = _val("Magnitude")
        if not magnitude:
            magnitude = _val("Speed") or _val("Size") or _val("F_Scale")

        parsed.append(
            {
                "event": event_name,
                "time": _val("Time"),
                "magnitude": magnitude,
                "location": _val("Location"),
                "county": _val("County"),
                "state": _val("State"),
                "remarks": _val("Comments") or _val("Remarks"),
                "lat": lat,
                "lon": lon,
            }
        )

    return parsed, "SPC Storm Reports CSV"


def _determine_extent(state_code: str, custom_extent: Optional[tuple]):
    if custom_extent:
        s, n, w, e = custom_extent
        return [w, e, s, n], "CONUS"

    code = (state_code or "CONUS").upper()
    bounds = STATE_BOUNDS.get(code, STATE_BOUNDS["CONUS"])
    return [bounds[0], bounds[1], bounds[2], bounds[3]], code


def _spc_projection_for_extent(
    extent,
    region_code: str,
    custom_extent: Optional[tuple] = None,
):
    """Build a Lambert projection centered on the requested view extent."""
    code = str(region_code or "").strip().upper()
    west, east, south, north = [float(value) for value in extent]

    if not custom_extent and code == "CONUS":
        return ccrs.LambertConformal(
            central_longitude=-96.0,
            central_latitude=39.0,
        )

    center_lon = (west + east) * 0.5
    center_lat = (south + north) * 0.5
    return ccrs.LambertConformal(
        central_longitude=center_lon,
        central_latitude=center_lat,
    )


def _fit_extent_to_aspect(
    extent,
    target_aspect: float = 16.0 / 9.0,
    projection=None,
):
    west, east, south, north = [float(value) for value in extent]
    proj = projection or ccrs.PlateCarree()

    corners_ll = np.array(
        [
            [west, south],
            [east, south],
            [east, north],
            [west, north],
        ]
    )
    corners_proj = proj.transform_points(
        ccrs.PlateCarree(),
        corners_ll[:, 0],
        corners_ll[:, 1],
    )
    xs = corners_proj[:, 0]
    ys = corners_proj[:, 1]
    if not (np.isfinite(xs).all() and np.isfinite(ys).all()):
        return [west, east, south, north]

    x_min = float(xs.min())
    x_max = float(xs.max())
    y_min = float(ys.min())
    y_max = float(ys.max())
    width = max(1e-6, x_max - x_min)
    height = max(1e-6, y_max - y_min)

    # Fit extent in projected coordinates so output aspect changes do not squash geography.
    current_aspect = width / height

    if current_aspect < target_aspect:
        target_width = height * target_aspect
        extra_width = max(0.0, target_width - width)
        x_min -= extra_width * 0.5
        x_max += extra_width * 0.5
    else:
        target_height = width / target_aspect
        extra_height = max(0.0, target_height - height)
        y_min -= extra_height * 0.5
        y_max += extra_height * 0.5

    fitted_proj = np.array(
        [
            [x_min, y_min],
            [x_max, y_min],
            [x_max, y_max],
            [x_min, y_max],
        ]
    )
    fitted_ll = ccrs.PlateCarree().transform_points(
        proj,
        fitted_proj[:, 0],
        fitted_proj[:, 1],
    )
    fit_lons = fitted_ll[:, 0]
    fit_lats = fitted_ll[:, 1]
    if not (np.isfinite(fit_lons).all() and np.isfinite(fit_lats).all()):
        return [west, east, south, north]

    return [
        float(fit_lons.min()),
        float(fit_lons.max()),
        float(fit_lats.min()),
        float(fit_lats.max()),
    ]


def _projected_extent_aspect(extent, projection=None) -> float:
    west, east, south, north = [float(value) for value in extent]
    proj = projection or ccrs.PlateCarree()

    corners_ll = np.array(
        [
            [west, south],
            [east, south],
            [east, north],
            [west, north],
        ]
    )
    corners_proj = proj.transform_points(
        ccrs.PlateCarree(),
        corners_ll[:, 0],
        corners_ll[:, 1],
    )
    xs = corners_proj[:, 0]
    ys = corners_proj[:, 1]
    if not (np.isfinite(xs).all() and np.isfinite(ys).all()):
        return _SPC_OUTPUT_MAX_WIDTH / _SPC_OUTPUT_MAX_HEIGHT

    width = max(1e-6, float(xs.max()) - float(xs.min()))
    height = max(1e-6, float(ys.max()) - float(ys.min()))
    return width / height


def _resolve_output_size(
    extent,
    projection=None,
    max_width: float = _SPC_OUTPUT_MAX_WIDTH,
    max_height: float = _SPC_OUTPUT_MAX_HEIGHT,
):
    aspect = max(1e-6, _projected_extent_aspect(extent, projection=projection))
    max_aspect = max_width / max(1e-6, max_height)

    if aspect >= max_aspect:
        width = max_width
        height = width / aspect
    else:
        height = max_height
        width = height * aspect

    return (max(1.0, width), max(1.0, height))


def _display_extent_for_output(
    extent,
    region_code: str,
    custom_extent: Optional[tuple] = None,
    output_size=None,
):
    display_extent = [float(value) for value in extent]
    code = str(region_code or "").strip().upper()

    # Keep shared STATE_BOUNDS unchanged; apply renderer-local padding only where
    # the visual output benefits from extra breathing room.
    if not custom_extent and code == "CONUS":
        display_extent[1] += 4.0

    map_projection = _spc_projection_for_extent(
        display_extent,
        code,
        custom_extent=custom_extent,
    )

    if output_size:
        width = float(output_size[0])
        height = float(output_size[1])
        render_extent = _fit_extent_to_aspect(
            display_extent,
            target_aspect=width / max(1e-6, height),
            projection=map_projection,
        )
    else:
        render_extent = display_extent

    return render_extent, map_projection


def _add_selected_region_outline(
    ax,
    region_code: str,
    edge_color: str,
    edge_alpha: float = 1.0,
    linewidth: float = 4.0,
):
    code = str(region_code or "").strip().upper()
    if not code or code == "CONUS":
        return False

    state_geoms = load_state_geometries()
    geometry = state_geoms.get(code)
    if geometry is None:
        return False

    ax.add_geometries(
        [geometry],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor=to_rgba(edge_color, edge_alpha),
        linewidth=linewidth,
        zorder=92,
    )
    return True


def _add_outlook_polygons(
    ax,
    outlook_geojson,
    alpha: float,
    fill_override: Optional[str] = None,
    edge_override: Optional[str] = None,
):
    legend_entries = []
    features = (
        outlook_geojson.get("features", []) if isinstance(
            outlook_geojson, dict) else []
    )
    for feature in features:
        geometry = feature.get("geometry") or {}
        gtype = geometry.get("type")
        coords = geometry.get("coordinates", [])
        props = feature.get("properties", {})
        edge_color = edge_override or props.get("stroke") or "#ffd700"
        fill_color = fill_override or props.get("fill") or "#ffd700"
        label = str(props.get("LABEL") or props.get("LABEL2") or "").strip()
        dn_value = props.get("DN")

        if fill_color and label:
            legend_entries.append((fill_color, label, dn_value))

        if gtype == "Polygon":
            for ring in coords[:1]:
                if not ring:
                    continue
                xs = [p[0] for p in ring]
                ys = [p[1] for p in ring]
                ax.fill(
                    xs,
                    ys,
                    facecolor=fill_color,
                    edgecolor=edge_color,
                    linewidth=1.0,
                    alpha=alpha,
                    transform=ccrs.PlateCarree(),
                    zorder=30,
                )

    deduped = {}
    for fill_color, label, dn_value in legend_entries:
        key = (fill_color, label)
        try:
            sort_dn = float(dn_value)
        except (TypeError, ValueError):
            sort_dn = 999.0
        if key not in deduped or sort_dn < deduped[key][2]:
            deduped[key] = (fill_color, label, sort_dn)

    return sorted(deduped.values(), key=lambda item: item[2])


def _slugify_layer_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower())
    slug = slug.strip("_")
    return slug or "layer"


def _iter_polygon_rings(geometry: dict):
    gtype = (geometry or {}).get("type")
    coords = (geometry or {}).get("coordinates", [])
    if gtype == "Polygon":
        if coords:
            yield coords
    elif gtype == "MultiPolygon":
        for polygon in coords:
            if polygon:
                yield polygon


def _draw_feature_fill(
    ax,
    feature: dict,
    fill_color: str,
    edge_color: str,
    alpha: float = 1.0,
    zorder: int = 30,
):
    geometry = feature.get("geometry") or {}
    for rings in _iter_polygon_rings(geometry):
        ring = rings[0] if rings else None
        if not ring:
            continue
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        ax.fill(
            xs,
            ys,
            facecolor=fill_color,
            edgecolor=edge_color,
            linewidth=1.0,
            alpha=alpha,
            transform=ccrs.PlateCarree(),
            zorder=zorder,
        )


def _feature_display_label(props: dict) -> str:
    label2 = str((props or {}).get("LABEL2") or "").strip()
    label = str((props or {}).get("LABEL") or "").strip()
    if label2:
        return label2
    if label:
        return label
    return "SPC Outlook"


def _build_outlook_bin_layers(
    outlook_geojson,
    make_fig_ax,
    save_layer,
    hazard: str = "cat",
    fill_override: Optional[str] = None,
    edge_override: Optional[str] = None,
    default_opacity: float = 1.0,
):
    layer_paths = {}
    layer_defs = []
    used_layer_ids = set()

    def _sort_rank_for_label(
        label_text: str, hazard_name: str, fallback_dn: float
    ) -> float:
        label_key = (label_text or "").strip().upper()
        hazard_key = (hazard_name or "cat").strip().lower()

        pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", label_key)
        if pct_match:
            try:
                return float(pct_match.group(1))
            except (TypeError, ValueError):
                pass

        if hazard_key == "cat":
            cat_order = {
                "TSTM": 1.0,
                "GENERAL THUNDERSTORMS": 1.0,
                "MRGL": 2.0,
                "MARGINAL": 2.0,
                "SLGT": 3.0,
                "SLIGHT": 3.0,
                "ENH": 4.0,
                "ENHANCED": 4.0,
                "MDT": 5.0,
                "MODERATE": 5.0,
                "HIGH": 6.0,
            }
            for key, rank in cat_order.items():
                if key in label_key:
                    return rank

        return fallback_dn

    features = (
        outlook_geojson.get("features", []) if isinstance(
            outlook_geojson, dict) else []
    )
    for idx, feature in enumerate(features):
        props = feature.get("properties") or {}
        label = _feature_display_label(props)
        dn_value = props.get("DN")

        try:
            sort_dn = float(dn_value)
        except (TypeError, ValueError):
            sort_dn = 999.0

        layer_id = f"outlook_{_slugify_layer_name(label)}"
        if layer_id in used_layer_ids:
            layer_id = f"{layer_id}_{idx + 1}"
        used_layer_ids.add(layer_id)

        fill_color = fill_override or props.get("fill") or "#ffd700"
        edge_color = edge_override or props.get("stroke") or "#ffd700"

        fig_bin, ax_bin = make_fig_ax()
        _draw_feature_fill(
            ax_bin,
            feature,
            fill_color=fill_color,
            edge_color=edge_color,
            alpha=1.0,
            zorder=30,
        )
        layer_paths[layer_id] = save_layer(fig_bin, layer_id)

        layer_defs.append(
            {
                "id": layer_id,
                "label": label,
                "group": "outlook_bins",
                "default_visible": True,
                "default_opacity": default_opacity,
                "sort": _sort_rank_for_label(label, hazard, sort_dn),
            }
        )

    layer_defs.sort(key=lambda item: item.get("sort", 999.0))
    return layer_paths, layer_defs


def _add_significant_hatching(
    ax,
    sig_geojson,
    hatch_pattern="/",
    hatch_color="#101010",
    hatch_alpha=1.0,
):
    if not isinstance(sig_geojson, dict):
        return False

    features = sig_geojson.get("features", [])
    did_draw = False

    hatch_edge = to_rgba(hatch_color, hatch_alpha)

    def _cig_pattern_from_props(props: dict, base_pattern: str = "/") -> str:
        text = " ".join(
            [
                str((props or {}).get("LABEL") or ""),
                str((props or {}).get("LABEL2") or ""),
                str((props or {}).get("cig") or ""),
                str((props or {}).get("CIG") or ""),
                str((props or {}).get("INTENSITY") or ""),
            ]
        ).upper()

        # Patterns match SPC official CIG graphics:
        # CIG1 = broken diag upper-right to lower-left (sparse /)
        # CIG2 = solid diag upper-left to lower-right (dense \)
        # CIG3 = solid cross-hatch both directions   (dense x)
        if "CIG3" in text or "LEVEL 3" in text or "INTENSITY 3" in text:
            return "xx"
        if "CIG2" in text or "LEVEL 2" in text or "INTENSITY 2" in text:
            return "\\\\\\\\"
        if "CIG1" in text or "LEVEL 1" in text or "INTENSITY 1" in text:
            return "/"
        return "/"

    def _draw_polygon_rings(rings, hatch_for_feature):
        nonlocal did_draw
        for ring in rings[:1]:
            if not ring:
                continue
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            ax.fill(
                xs,
                ys,
                facecolor="none",
                edgecolor=hatch_edge,
                linewidth=0.0,
                hatch=hatch_for_feature,
                transform=ccrs.PlateCarree(),
                zorder=45,
            )
            did_draw = True

    for feature in features:
        props = feature.get("properties") or {}
        hatch_for_feature = _cig_pattern_from_props(props, hatch_pattern)
        geometry = feature.get("geometry") or {}
        gtype = geometry.get("type")
        coords = geometry.get("coordinates", [])

        if gtype == "Polygon":
            _draw_polygon_rings(coords, hatch_for_feature)
        elif gtype == "MultiPolygon":
            for polygon in coords:
                if not polygon:
                    continue
                _draw_polygon_rings(polygon, hatch_for_feature)
        elif gtype == "GeometryCollection":
            geometries = geometry.get("geometries", [])
            for geom in geometries:
                sub_type = geom.get("type")
                sub_coords = geom.get("coordinates", [])
                if sub_type == "Polygon":
                    _draw_polygon_rings(sub_coords, hatch_for_feature)
                elif sub_type == "MultiPolygon":
                    for polygon in sub_coords:
                        if not polygon:
                            continue
                        _draw_polygon_rings(polygon, hatch_for_feature)

    return did_draw


def _add_primary_sig_hatching(
    ax, outlook_geojson, hatch_color="#101010", hatch_alpha=1.0
):
    """Fallback: hatch CIG/SIG polygons embedded in the main outlook layer."""
    if not isinstance(outlook_geojson, dict):
        return False

    did_draw = False
    features = outlook_geojson.get("features", [])

    def _pattern_for(props):
        label = str(props.get("LABEL") or "").strip().upper()
        label2 = str(props.get("LABEL2") or "").strip().upper()

        if "CIG3" in label or "CIG3" in label2:
            return "xx"
        if "CIG2" in label or "CIG2" in label2:
            return "\\\\\\\\"
        if label.startswith("CIG") or "CONDITIONAL INTENSITY" in label2:
            return "/"

        if " SIG" in f" {label}" or "SIGNIFICANT" in label2:
            return "/"

        return ""

    hatch_edge = to_rgba(hatch_color, hatch_alpha)

    def _draw_coords(coords, hatch_pattern):
        nonlocal did_draw
        for ring in coords[:1]:
            if not ring:
                continue
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            ax.fill(
                xs,
                ys,
                facecolor="none",
                edgecolor=hatch_edge,
                linewidth=0.0,
                hatch=hatch_pattern,
                transform=ccrs.PlateCarree(),
                zorder=46,
            )
            did_draw = True

    for feature in features:
        props = feature.get("properties") or {}
        hatch_pattern = _pattern_for(props)
        if not hatch_pattern:
            continue

        geometry = feature.get("geometry") or {}
        gtype = geometry.get("type")
        coords = geometry.get("coordinates", [])

        if gtype == "Polygon":
            _draw_coords(coords, hatch_pattern)
        elif gtype == "MultiPolygon":
            for polygon in coords:
                if not polygon:
                    continue
                _draw_coords(polygon, hatch_pattern)

    return did_draw


def _hatch_angle_from_pattern(hatch_pattern: str) -> float:
    pattern = str(hatch_pattern or "").strip()
    if "\\" in pattern and "/" not in pattern:
        return -55.0
    return 55.0


def _dashify_hatch_layer_png(
    png_path: str,
    hatch_pattern: str = "/",
    dash_px: int = 4,
    gap_px: int = 2,
):
    """Convert continuous hatch pixels into broken dashes in image space.

    This is much lighter than clipping thousands of geometric dashed segments while
    preserving the same diagonal orientation.
    """
    try:
        rgba = plt.imread(png_path)
        if rgba is None or getattr(rgba, "ndim", 0) != 3:
            return

        if rgba.shape[2] == 3:
            alpha_channel = np.ones(
                (rgba.shape[0], rgba.shape[1], 1), dtype=rgba.dtype)
            rgba = np.concatenate([rgba, alpha_channel], axis=2)
        elif rgba.shape[2] < 4:
            return

        alpha = rgba[..., 3]
        active = alpha > 0.001
        if not np.any(active):
            return

        h, w = alpha.shape
        yy, xx = np.indices((h, w), dtype=np.float32)
        theta = np.deg2rad(_hatch_angle_from_pattern(hatch_pattern))

        # Coordinate along hatch-line direction controls dash/gap segmentation.
        along = xx * np.cos(theta) + yy * np.sin(theta)
        dash = max(1.0, float(dash_px))
        gap = max(1.0, float(gap_px))
        period = dash + gap
        keep = np.mod(along, period) < dash

        rgba[..., 3] = np.where(active & keep, alpha, 0.0)
        plt.imsave(png_path, rgba)
    except Exception:
        # If post-processing fails for any reason, keep original hatch layer.
        return


def _categorical_code_from_label(label: str) -> Optional[str]:
    text = str(label or "").strip().upper()
    if "HIGH" in text:
        return "HIGH"
    if "MDT" in text or "MODERATE" in text:
        return "MDT"
    if "ENH" in text or "ENHANCED" in text:
        return "ENH"
    if "SLGT" in text or "SLIGHT" in text:
        return "SLGT"
    if "MRGL" in text or "MARGINAL" in text:
        return "MRGL"
    if "TSTM" in text or "THUNDERSTORM" in text:
        return "TSTM"
    return None


def _build_categorical_legend_rows(legend_entries):
    spc_rows = [
        ("HIGH", "5", "High", "#ff66ff"),
        ("MDT", "4", "Moderate", "#ff4f4f"),
        ("ENH", "3", "Enhanced", "#ff9d2e"),
        ("SLGT", "2", "Slight", "#f5dd72"),
        ("MRGL", "1", "Marginal", "#69bb6d"),
        ("TSTM", "", "T-Storms", "#b5dcb3"),
    ]
    return spc_rows


def _report_type_key(event_text: str) -> str:
    text = str(event_text or "").strip().lower()
    if "torn" in text:
        return "torn"
    if "wind" in text:
        return "wind"
    if "hail" in text:
        return "hail"
    return "other"


def _draw_bottom_reference(
    fig,
    legend_entries,
    show_hatch_note=False,
    text_color="#e2e8f0",
    legend_mode="none",
    watch_item: Optional[dict] = None,
    style_config: Optional[dict] = None,
):
    mode = str(legend_mode or "none").strip().lower()
    if mode not in {"cat", "torn", "wind", "hail", "reports", "watches"}:
        return

    font_scale = _responsive_text_scale(fig, style_config=style_config)

    def fs(size: float, minimum: float = 6.0) -> float:
        return max(minimum, float(size) * font_scale)

    if mode == "watches":
        probs = (watch_item or {}).get("probabilities", {}) or {}
        has_any = any(
            str(probs.get(key, "")).strip()
            for key in [
                "tor2",
                "tor_strong",
                "wind10",
                "wind65",
                "hail10",
                "hail2",
                "combined6",
            ]
        )
        if not has_any:
            return

        def _v(key, fallback="--"):
            value_text = str(probs.get(key, "")).strip()
            return value_text if value_text else fallback

        box_x = 0.0
        box_y = 0.0
        box_w = 1.0
        box_h = 0.14

        container = Rectangle(
            (box_x, box_y),
            box_w,
            box_h,
            transform=fig.transFigure,
            facecolor="#ffffff",
            edgecolor="#111111",
            linewidth=1.0,
        )
        fig.add_artist(container)

        watch_title = str((watch_item or {}).get("title") or "Watch")
        fig.text(
            box_x + (box_w * 0.5),
            box_y + box_h - 0.018,
            f"{watch_title} Probabilities",
            ha="center",
            va="center",
            fontname="Montserrat",
            fontsize=fs(10),
            color="#000000",
            fontweight="bold",
        )

        col_w = box_w / 3.0
        y_header = box_y + box_h - 0.044
        y_line1 = y_header - 0.020
        y_line2 = y_line1 - 0.020

        def _draw_prob_column(idx, heading, line1, line2):
            x_center = box_x + ((idx + 0.5) * col_w)
            fig.text(
                x_center,
                y_header,
                heading,
                ha="center",
                va="center",
                fontname="Montserrat",
                fontsize=fs(10),
                color="#0008FF",
                fontweight="bold",
            )
            fig.text(
                x_center,
                y_line1,
                line1,
                ha="center",
                va="center",
                fontname="Montserrat",
                fontsize=fs(9.0),
                color="#111111",
                fontweight="bold",
            )
            fig.text(
                x_center,
                y_line2,
                line2,
                ha="center",
                va="center",
                fontname="Montserrat",
                fontsize=fs(9.0),
                color="#111111",
                fontweight="bold",
            )

        _draw_prob_column(
            0,
            "Tornado",
            f"2 or More Tornadoes: {_v('tor2')}",
            f"1 or More Strong (EF2-EF5) tornadoes: {_v('tor_strong')}",
        )
        _draw_prob_column(
            1,
            "Wind",
            f"10 or More Severe Wind Events: {_v('wind10')}",
            f"1 or More Wind Events >65 kt: {_v('wind65')}",
        )
        _draw_prob_column(
            2,
            "Hail",
            f"10 or More SevereHail Events: {_v('hail10')}",
            f"1 or More Hail Events >2 in: {_v('hail2')}",
        )

        fig.text(
            box_x + (box_w * 0.5),
            box_y + 0.030,
            f"6 or More Combined Severe Hail/Wind Events: {_v('combined6')}",
            ha="center",
            va="center",
            fontname="Montserrat",
            fontsize=fs(11),
            color="#0008FF",
            fontweight="bold",
        )
        return

    if mode == "reports":
        rows = [
            ("Tornado", "v", "#ff3b30"),
            ("Wind", "$\\equiv$", "#2f7bc5"),
            ("Hail", "o", "#30a24c"),
        ]

        box_x = 0.02
        box_y = 0.02
        item_w = 0.15
        box_w = 1.0 - (2 * box_x)
        box_h = 0.09

        container = Rectangle(
            (box_x, box_y),
            box_w,
            box_h,
            transform=fig.transFigure,
            facecolor="#ffffff",
            edgecolor="#111111",
            linewidth=1.0,
        )
        fig.add_artist(container)

        fig.text(
            box_x + (box_w * 0.5),
            box_y + box_h - 0.02,
            "Storm Reports",
            ha="center",
            va="center",
            fontname="Montserrat",
            fontsize=fs(10),
            color="#000000",
            fontweight="bold",
        )

        from matplotlib.lines import Line2D

        x_cursor = box_x + (box_w - (len(rows) * item_w)) / 2
        y_mid = box_y + 0.028
        for label_text, marker_shape, marker_color in rows:
            fig.add_artist(
                Line2D(
                    [x_cursor + 0.012],
                    [y_mid],
                    transform=fig.transFigure,
                    marker=marker_shape,
                    markersize=7,
                    markerfacecolor=marker_color,
                    markeredgecolor="#111111",
                    markeredgewidth=0.6,
                    linestyle="None",
                    zorder=101,
                )
            )
            fig.text(
                x_cursor + 0.024,
                y_mid,
                label_text,
                ha="left",
                va="center",
                fontname="Montserrat",
                fontsize=fs(9),
                color="#111111",
                fontweight="bold",
            )
            x_cursor += item_w
        return

    if mode in {"torn", "wind", "hail"}:
        if mode == "torn":
            rows = [
                (">= 60%", "#0b5fa5", "#2f7bc5"),
                ("45 - 59%", "#b58ce3", "#9f63d6"),
                ("30 - 44%", "#ef87ef", "#d93be5"),
                ("15 - 29%", "#f5a3a3", "#ff2d2d"),
                ("10 - 14%", "#f5dc79", "#ef9c2d"),
                ("5 - 9%", "#b89082", "#995f49"),
                ("2 - 4%", "#78b77f", "#3b9648"),
            ]
            title_text = "Probability of a Tornado"
        elif mode == "wind":
            rows = [
                (">= 90%", "#66d9e8", "#4aaec9"),
                ("75 - 89%", "#6a89d8", "#4f6ec0"),
                ("60 - 74%", "#b58ce3", "#9f63d6"),
                ("45 - 59%", "#ef87ef", "#d93be5"),
                ("30 - 44%", "#f5a3a3", "#ff2d2d"),
                ("15 - 29%", "#f5dc79", "#ef9c2d"),
                ("5 - 14%", "#b89082", "#995f49"),
            ]
            title_text = "Probability of Severe Wind"
        else:
            rows = [
                (">= 60%", "#0b5fa5", "#2f7bc5"),
                ("45 - 59%", "#b58ce3", "#9f63d6"),
                ("30 - 44%", "#ef87ef", "#d93be5"),
                ("15 - 29%", "#f5a3a3", "#ff2d2d"),
                ("5 - 14%", "#b89082", "#995f49"),
            ]
            title_text = "Probability of Severe Hail"

        box_x = 0.00
        box_y = 0.00
        item_w = 0.13
        box_w = 1.0 - (2 * box_x)
        box_h = 0.13

        container = Rectangle(
            (box_x, box_y),
            box_w,
            box_h,
            transform=fig.transFigure,
            facecolor="#ffffff",
            edgecolor="#111111",
            linewidth=1.0,
        )
        fig.add_artist(container)

        fig.text(
            box_x + (box_w * 0.5),
            box_y + box_h - 0.02,
            title_text,
            ha="center",
            va="center",
            fontname="Montserrat",
            fontsize=fs(11),
            color="#000000",
            fontweight="bold",
        )
        fig.text(
            box_x + (box_w * 0.5),
            box_y + box_h - 0.04,
            "within 25 miles of a point",
            ha="center",
            va="center",
            fontname="Montserrat",
            fontsize=fs(8),
            color="#222222",
        )

        row1_content_w = len(rows) * item_w
        x_cursor = box_x + (box_w - row1_content_w) / 2
        y_mid = box_y + box_h - 0.07
        for label_text, fill_color, edge_color in rows:
            swatch = Rectangle(
                (x_cursor, y_mid - 0.011),
                0.028,
                0.022,
                transform=fig.transFigure,
                facecolor=fill_color,
                edgecolor=edge_color,
                linewidth=1.0,
            )
            fig.add_artist(swatch)
            fig.text(
                x_cursor + 0.034,
                y_mid,
                label_text,
                ha="left",
                va="center",
                fontname="Montserrat",
                fontsize=fs(9),
                color="#111111",
                fontweight="bold",
            )
            x_cursor += item_w

        y2 = box_y + 0.03
        is_hail_mode = mode == "hail"
        intensity_count = 2 if is_hail_mode else 3
        # Center intensity row: "Intensity" label area + N items (stride 0.07) + trailing text
        _intens_row_w = 0.105 + intensity_count * 0.07 + 0.02
        x_intens_row = box_x + (box_w - _intens_row_w) / 2
        fig.text(
            x_intens_row,
            y2,
            "Intensity",
            ha="left",
            va="center",
            fontname="Montserrat",
            fontsize=fs(10),
            color="#000000",
            fontweight="bold",
        )

        if is_hail_mode:
            intensity_items = [
                ("\\\\\\", "2", False),
                ("", "1", True),
            ]
        else:
            intensity_items = [
                ("xx", "3", False),
                ("\\\\\\", "2", False),
                ("", "1", True),
            ]
        x_i = x_intens_row + 0.105
        for hatch_pat, level_text, dashed_slash in intensity_items:
            sample = Rectangle(
                (x_i, y2 - 0.011),
                0.03,
                0.022,
                transform=fig.transFigure,
                facecolor="#f5f5f5",
                edgecolor="#111111",
                linewidth=0.8,
                hatch=hatch_pat,
            )
            fig.add_artist(sample)

            if dashed_slash:
                from matplotlib.lines import Line2D

                # Intensity 1 uses dashed diagonals at the same angle as '/', clipped to sample box.
                for offset in (-0.018, -0.011, -0.004, 0.003, 0.010, 0.017, 0.024):
                    x0 = x_i + offset
                    y0 = y2 - 0.010
                    x1 = x0 + 0.020
                    y1 = y0 + 0.017
                    fig.add_artist(
                        Line2D(
                            [x0, x1],
                            [y0, y1],
                            transform=fig.transFigure,
                            color="#111111",
                            linewidth=1.15,
                            linestyle=(0, (3, 2)),
                            zorder=sample.get_zorder() + 1,
                            clip_on=True,
                            clip_path=sample,
                        )
                    )

            fig.text(
                x_i + 0.035,
                y2,
                level_text,
                ha="left",
                va="center",
                fontname="Montserrat",
                fontsize=fs(9),
                color="#111111",
                fontweight="bold",
            )
            x_i += 0.07
        return

    rows = _build_categorical_legend_rows(legend_entries)
    if not rows:
        return

    box_x = 0.02
    box_y = 0.02
    item_w = 0.145
    box_w = 1.0 - (2 * box_x)
    box_h = 0.062

    container = Rectangle(
        (box_x, box_y),
        box_w,
        box_h,
        transform=fig.transFigure,
        facecolor="#ffffff",
        edgecolor="#111111",
        linewidth=1.0,
    )
    fig.add_artist(container)

    x_cursor = box_x + 0.015
    y_mid = box_y + (box_h * 0.5)
    for _, value_text, label_text, fill_color in rows:
        swatch = Rectangle(
            (x_cursor, y_mid - 0.013),
            0.03,
            0.03,
            transform=fig.transFigure,
            facecolor=fill_color,
            edgecolor=fill_color,
            linewidth=0.8,
        )
        fig.add_artist(swatch)

        if value_text:
            fig.text(
                x_cursor + 0.0155,
                y_mid - 0.001,
                value_text,
                ha="center",
                va="center",
                fontname="Montserrat",
                fontstyle="italic",
                fontsize=fs(12),
                color="#000000",
                fontweight="bold",
            )

        fig.text(
            x_cursor + 0.036,
            y_mid - 0.001,
            label_text,
            ha="left",
            va="center",
            fontname="Montserrat",
            fontstyle="italic",
            fontsize=fs(10),
            color="#000000",
            fontweight="bold",
        )
        x_cursor += item_w


def _add_reports_points(ax, reports_rows, style_config: Optional[dict] = None):
    if not reports_rows:
        return

    style_config = style_config or {}
    reports_alpha = float(style_config.get("reports_alpha", 0.9))
    reports_size = float(style_config.get("reports_size", 75))
    reports_tornado_size = float(
        style_config.get("reports_tornado_size", reports_size * 3.0)
    )

    marker_by_type = {
        "torn": {"marker": "v", "color": "#ff3b30"},
        "wind": {"marker": "$\\equiv$", "color": "#389cff"},
        "hail": {"marker": "o", "color": "#30a24c"},
        "other": {"marker": "?", "color": style_config.get("reports_color", "#00e5ff")},
    }
    marker_size_by_type = {
        "torn": reports_tornado_size,
        "wind": reports_size,
        "hail": reports_size,
        "other": reports_size,
    }

    grouped = {"torn": [], "wind": [], "hail": [], "other": []}
    for row in reports_rows:
        key = _report_type_key(row.get("event", ""))
        grouped[key].append(row)

    for key, rows in grouped.items():
        if not rows:
            continue
        spec = marker_by_type[key]
        lons = [row["lon"] for row in rows]
        lats = [row["lat"] for row in rows]
        ax.scatter(
            lons,
            lats,
            s=marker_size_by_type.get(key, reports_size),
            marker=spec["marker"],
            color=spec["color"],
            edgecolors="#04131f",
            linewidths=0.35,
            alpha=reports_alpha,
            transform=ccrs.PlateCarree(),
            zorder=60,
        )


def _annotate_hud(
    fig,
    ax,
    title_text: str,
    right_text: str,
    style_config: Optional[dict] = None,
    logo_path: Optional[str] = None,
):
    style_config = style_config or {}

    hud_left_size = int(style_config.get("hud_left_size", 15))
    hud_left_x = float(style_config.get("hud_left_x", 0.02))
    hud_left_y = float(style_config.get("hud_left_y", 0.95))
    hud_left_text_color = style_config.get("hud_left_text_color", "#ffffff")
    hud_left_bg_color = style_config.get("hud_left_bg_color", "#000000")
    hud_left_edge_color = style_config.get("hud_left_edge_color", "#555555")
    hud_left_alpha = float(style_config.get("hud_left_alpha", 0.8))

    hud_right_size = int(style_config.get("hud_right_size", 15))
    hud_right_x = float(style_config.get("hud_right_x", 0.98))
    hud_right_y = float(style_config.get("hud_right_y", 0.98))
    hud_right_text_color = style_config.get("hud_right_text_color", "#ffd700")
    hud_right_bg_color = style_config.get("hud_right_bg_color", "#000000")
    hud_right_edge_color = style_config.get("hud_right_edge_color", "#555555")
    hud_right_alpha = float(style_config.get("hud_right_alpha", 0.8))

    text_scale = _responsive_text_scale(fig, style_config=style_config)
    hud_left_size = max(8.0, float(hud_left_size) * text_scale)
    hud_right_size = max(8.0, float(hud_right_size) * text_scale)
    source_font_size = max(6.0, 8.0 * text_scale)

    fig.text(
        hud_left_x,
        hud_left_y,
        title_text,
        ha="left",
        va="top",
        color=hud_left_text_color,
        fontsize=hud_left_size,
        fontname="Montserrat",
        fontweight="black",
        fontstyle="italic",
        bbox={
            "facecolor": hud_left_bg_color,
            "alpha": hud_left_alpha,
            "edgecolor": hud_left_edge_color,
            "boxstyle": "round,pad=0.3",
        },
        zorder=120,
    )
    fig.text(
        hud_right_x,
        hud_right_y,
        right_text,
        ha="right",
        va="top",
        color=hud_right_text_color,
        fontsize=hud_right_size,
        fontname="Montserrat",
        fontweight="black",
        fontstyle="italic",
        bbox={
            "facecolor": hud_right_bg_color,
            "alpha": hud_right_alpha,
            "edgecolor": hud_right_edge_color,
            "boxstyle": "round,pad=0.3",
        },
        zorder=120,
    )

    logo_file = str(logo_path or "").strip()
    if logo_file and os.path.exists(logo_file):
        try:
            logo_user_size = float(style_config.get("logo_user_size", 0.08))
            logo_user_x = float(style_config.get("logo_user_x", 0.98))
            # Keep default above SPC bottom legends unless user overrides.
            logo_user_y = float(style_config.get("logo_user_y", 0.14))

            logo_img = mpimg.imread(logo_file)
            fig.add_artist(
                AnnotationBbox(
                    OffsetImage(logo_img, zoom=logo_user_size),
                    (logo_user_x, logo_user_y),
                    xycoords="figure fraction",
                    frameon=False,
                    box_alignment=(1, 0),
                    zorder=121,
                )
            )
        except Exception:
            pass

    fig.text(
        0.99,
        0.012,
        "SPC/NWS",
        ha="right",
        va="bottom",
        color="#cbd5e1",
        fontsize=source_font_size,
    )


def _normalize_product_id(value: str) -> str:
    text = re.sub(r"\D", "", str(value or "")).strip()
    return text.zfill(4) if text else ""


def _selected_ids_from_style(style_config: Optional[dict], key: str) -> set:
    raw = (style_config or {}).get(key)
    if raw is None:
        return set()

    if isinstance(raw, (list, tuple, set)):
        values = raw
    else:
        values = re.split(r"[,\s]+", str(raw).strip())

    selected = set()
    for value in values:
        normalized = _normalize_product_id(value)
        if normalized:
            selected.add(normalized)
    return selected


def generate_spc_map(
    *,
    output_dir: str,
    logo_file: Optional[str] = None,
    state_code: str = "CONUS",
    day: int = 1,
    hazard: str = "cat",
    include_reports: bool = True,
    report_date_utc: Optional[datetime] = None,
    report_mode: str = "filtered",
    report_type: str = "all",
    user_tz: str = "America/New_York",
    style_config: Optional[dict] = None,
    custom_extent: Optional[tuple] = None,
):
    raise RuntimeError(
        "spc.generate_spc_map is disabled in Phase 0. "
        "Rendering was removed from spc_utils; use unified weather/export pipeline."
    )

    style_config = style_config or {}
    hazard_key = str(hazard or "cat").strip().lower()
    is_reports_only = hazard_key == "reports"
    is_watches_only = hazard_key == "watches"
    is_mds_only = hazard_key in {"md", "mds"}
    show_outlook_layers = not (
        is_reports_only or is_watches_only or is_mds_only)

    show_country = _to_bool(style_config.get("show_country", True), True)
    show_states = _to_bool(style_config.get("show_states", True), True)
    show_counties = _to_bool(style_config.get("show_counties", False), False)
    show_places = _to_bool(style_config.get("show_places", True), True)
    outlook_alpha = 1.0

    # Hardwired base border/coastline styling.
    country_color = "#d0d0d0"
    country_width = 2.0
    country_alpha = 1.0

    state_color = "#1D1D1D"
    state_width = 0.45
    state_alpha = 1.0

    selected_color = "#85baff"

    county_color = "#000000"
    county_width = 0.3
    county_alpha = 1.0

    coastline_color = "#a3b5c7"
    coastline_width = 0.55
    coastline_alpha = 1.0

    outlook_fill_override = None
    outlook_edge_override = None

    hatch_color = style_config.get("spc_hatch_color", "#101010")
    hatch_alpha = float(style_config.get("spc_hatch_alpha", 1.0))
    hatch_pattern = str(style_config.get("spc_sig_hatch_pattern", "/"))
    hatch_dash_px = int(style_config.get("spc_hatch_dash_px", 4))
    hatch_gap_px = int(style_config.get("spc_hatch_gap_px", 4))

    show_watches = _to_bool(style_config.get("spc_show_watches", True), True)
    show_mds = _to_bool(style_config.get("spc_show_mds", True), True)
    watch_render_mode = (
        str(style_config.get("spc_watch_render_mode", "current")).strip().lower()
    )
    watch_edge_color = style_config.get("spc_watch_edge_color", "#ff4f4f")
    watch_fill_color = style_config.get("spc_watch_fill_color", "#ff4f4f")
    watch_fill_alpha = float(style_config.get("spc_watch_fill_alpha", 0.18))
    watch_linewidth = float(style_config.get("spc_watch_linewidth", 2.0))
    watch_label_size = int(style_config.get("spc_watch_label_size", 8))
    watch_label_color = style_config.get("spc_watch_label_color", "#ffe7e7")

    md_edge_color = style_config.get("spc_md_edge_color", "#00d4ff")
    md_fill_color = style_config.get("spc_md_fill_color", "#00d4ff")
    md_fill_alpha = float(style_config.get("spc_md_fill_alpha", 0.15))
    md_linewidth = float(style_config.get("spc_md_linewidth", 1.7))
    md_label_size = int(style_config.get("spc_md_label_size", 8))
    md_label_color = style_config.get("spc_md_label_color", "#e6fbff")

    land_color = style_config.get("land_color", "#CECECE")
    ocean_color = style_config.get("ocean_color", "#234972")
    lakes_color = style_config.get("lakes_color", "#4979AD")

    now_utc = datetime.now(timezone.utc)
    display_tz = _resolve_display_tz(user_tz)
    out_dir = os.path.join(
        output_dir,
        (state_code or "CONUS").upper() if not custom_extent else "CONUS",
        now_utc.strftime("%Y"),
        now_utc.strftime("%m"),
        now_utc.strftime("%d"),
    )
    os.makedirs(out_dir, exist_ok=True)

    token = now_utc.strftime("%Y%m%d_%H%M%S")

    outlook_geojson = {"features": []}
    outlook_source = ""
    if show_outlook_layers:
        outlook_geojson, outlook_source = fetch_outlook_geojson(day, hazard)
    reports_rows = []
    reports_source = ""
    if include_reports:
        reports_rows, reports_source = fetch_reports_rows(
            report_date_utc, report_mode, report_type
        )

    watches_items = []
    mds_items = []
    watches_source = ""
    mds_source = ""
    time_reference = report_date_utc or now_utc
    include_active_spc_products = (
        abs((now_utc - time_reference).total_seconds()) <= 36 * 3600
    )
    if include_active_spc_products:
        try:
            watches_items, watches_source = fetch_active_watch_items()
        except Exception:
            watches_items = []
            watches_source = ""
        try:
            mds_items, mds_source = fetch_active_md_items()
        except Exception:
            mds_items = []
            mds_source = ""

    selected_watch_ids = _selected_ids_from_style(
        style_config, "spc_selected_watch_id")
    if selected_watch_ids:
        watches_items = [
            item
            for item in watches_items
            if _normalize_product_id(item.get("id", "")) in selected_watch_ids
        ]

    selected_md_ids = _selected_ids_from_style(
        style_config, "spc_selected_md_id")
    if selected_md_ids:
        mds_items = [
            item
            for item in mds_items
            if _normalize_product_id(item.get("id", "")) in selected_md_ids
        ]

    extent, resolved_region = _determine_extent(state_code, custom_extent)
    render_extent, map_projection = _display_extent_for_output(
        extent,
        resolved_region,
        custom_extent=custom_extent,
    )
    output_size = _resolve_output_size(
        render_extent, projection=map_projection)
    is_conus_like_view = bool(custom_extent) or str(
        resolved_region).upper() == "CONUS"
    base_feature_resolution = "50m" if is_conus_like_view else "10m"

    # Use resolved region directory once extent logic is finalized
    out_dir = os.path.join(
        output_dir,
        resolved_region,
        now_utc.strftime("%Y"),
        now_utc.strftime("%m"),
        now_utc.strftime("%d"),
    )
    os.makedirs(out_dir, exist_ok=True)

    def _new_fig_ax(transparent=True):
        fig = plt.figure(figsize=output_size, dpi=_SPC_OUTPUT_DPI)
        # Use a full-figure axes so every layer shares identical pixel geometry.
        ax = fig.add_axes([0.0, 0.0, 1.0, 1.0], projection=map_projection)
        ax.set_extent(render_extent, crs=ccrs.PlateCarree())
        ax.set_aspect("equal", adjustable="box")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_axis_off()
        geo_spine = ax.spines.get("geo")
        if geo_spine is not None:
            geo_spine.set_visible(False)
        if transparent:
            fig.patch.set_alpha(0)
            ax.patch.set_alpha(0)
        else:
            fig.patch.set_facecolor(ocean_color)
            ax.set_facecolor(ocean_color)
        return fig, ax

    def _save_layer(fig, layer_name, transparent=True):
        path = os.path.join(out_dir, f"spc_{token}_{layer_name}.png")
        plt.savefig(path, dpi=_SPC_OUTPUT_DPI, transparent=transparent)
        plt.close(fig)
        return path

    layer_paths = {}

    fig_base, ax_base = _new_fig_ax(transparent=False)
    ax_base.set_facecolor(ocean_color)
    ax_base.add_feature(
        cfeature.LAND.with_scale(base_feature_resolution),
        facecolor=land_color,
        zorder=1,
    )
    ax_base.add_feature(
        cfeature.OCEAN.with_scale(base_feature_resolution),
        facecolor=ocean_color,
        zorder=0,
    )
    layer_paths["basemap"] = _save_layer(
        fig_base, "basemap", transparent=False)

    fig_country, ax_country = _new_fig_ax()
    ax_country.add_feature(
        cfeature.BORDERS.with_scale(base_feature_resolution),
        edgecolor=to_rgba(country_color, country_alpha),
        linewidth=country_width,
        zorder=10,
    )
    ax_country.add_feature(
        cfeature.LAKES.with_scale(base_feature_resolution),
        facecolor=lakes_color,
        edgecolor="none",
        zorder=10.5,
    )
    layer_paths["country"] = _save_layer(fig_country, "country")

    fig_states, ax_states = _new_fig_ax()
    ax_states.add_feature(
        cfeature.STATES.with_scale(base_feature_resolution),
        edgecolor=to_rgba(state_color, state_alpha),
        linewidth=state_width,
        zorder=11,
    )
    layer_paths["states"] = _save_layer(fig_states, "states")

    fig_counties, ax_counties = _new_fig_ax()
    county_feature = CensusCounties.get_feature()
    if county_feature is not None:
        ax_counties.add_feature(
            county_feature,
            edgecolor=to_rgba(county_color, county_alpha),
            facecolor="none",
            linewidth=county_width,
            zorder=9,
        )
    layer_paths["counties"] = _save_layer(fig_counties, "counties")

    fig_coast, ax_coast = _new_fig_ax()
    ax_coast.coastlines(
        resolution=base_feature_resolution,
        linewidth=coastline_width,
        color=to_rgba(coastline_color, coastline_alpha),
        zorder=12,
    )
    layer_paths["coastline"] = _save_layer(fig_coast, "coastline")

    legend_entries = []
    outlook_bin_paths = {}
    outlook_bin_defs = []
    sig_geojson = None
    show_sig_hatch = False
    hatch_applied = False
    if show_outlook_layers:
        fig_outlook, ax_outlook = _new_fig_ax()
        legend_entries = _add_outlook_polygons(
            ax_outlook,
            outlook_geojson,
            outlook_alpha,
            fill_override=outlook_fill_override,
            edge_override=outlook_edge_override,
        )
        layer_paths["outlook"] = _save_layer(fig_outlook, "outlook")

        outlook_bin_paths, outlook_bin_defs = _build_outlook_bin_layers(
            outlook_geojson,
            make_fig_ax=_new_fig_ax,
            save_layer=_save_layer,
            hazard=hazard,
            fill_override=outlook_fill_override,
            edge_override=outlook_edge_override,
            default_opacity=outlook_alpha,
        )
        layer_paths.update(outlook_bin_paths)

        sig_geojson = fetch_significant_geojson(day, hazard)
        show_sig_hatch = _to_bool(style_config.get(
            "spc_show_sig_hatch", True), True)
        fig_hatch, ax_hatch = _new_fig_ax()
        if show_sig_hatch and sig_geojson:
            hatch_applied = _add_significant_hatching(
                ax_hatch,
                sig_geojson,
                hatch_pattern=hatch_pattern,
                hatch_color=hatch_color,
                hatch_alpha=hatch_alpha,
            )
        if show_sig_hatch and not hatch_applied:
            hatch_applied = _add_primary_sig_hatching(
                ax_hatch,
                outlook_geojson,
                hatch_color=hatch_color,
                hatch_alpha=hatch_alpha,
            )
        hatch_path = _save_layer(fig_hatch, "hatch")
        if show_sig_hatch and hatch_applied:
            _dashify_hatch_layer_png(
                hatch_path,
                hatch_pattern=hatch_pattern,
                dash_px=hatch_dash_px,
                gap_px=hatch_gap_px,
            )
        layer_paths["hatch"] = hatch_path

    watch_layer_paths = {}
    watch_layer_defs = []
    if watches_items:
        watch_renderer = (
            _draw_watch_county_items_layer if watch_render_mode == "counties" else None
        )
        watch_layer_paths, watch_layer_defs = _build_spc_item_layers(
            items=watches_items,
            layer_prefix="watch",
            group="watches",
            make_fig_ax=_new_fig_ax,
            save_layer=_save_layer,
            edge_color=watch_edge_color,
            fill_color=watch_fill_color,
            fill_alpha=watch_fill_alpha,
            linewidth=watch_linewidth,
            label_size=watch_label_size,
            label_color=watch_label_color,
            default_visible=show_watches,
            sort_base=52,
            renderer=watch_renderer,
        )
        layer_paths.update(watch_layer_paths)

    md_layer_paths = {}
    md_layer_defs = []
    if mds_items:
        md_layer_paths, md_layer_defs = _build_spc_item_layers(
            items=mds_items,
            layer_prefix="md",
            group="mds",
            make_fig_ax=_new_fig_ax,
            save_layer=_save_layer,
            edge_color=md_edge_color,
            fill_color=md_fill_color,
            fill_alpha=md_fill_alpha,
            linewidth=md_linewidth,
            label_size=md_label_size,
            label_color=md_label_color,
            default_visible=show_mds,
            sort_base=70,
        )
        layer_paths.update(md_layer_paths)

    fig_reports, ax_reports = _new_fig_ax()
    _add_reports_points(ax_reports, reports_rows, style_config=style_config)
    layer_paths["reports"] = _save_layer(fig_reports, "reports")

    fig_cities, ax_cities = _new_fig_ax()
    plot_cities(
        ax_cities,
        (render_extent[0], render_extent[1],
         render_extent[2], render_extent[3]),
        filename=style_config.get("cities_file", "us-cities.json"),
        style_config=style_config,
        z_cities=70,
    )
    layer_paths["cities"] = _save_layer(fig_cities, "cities")

    fig_region, ax_region = _new_fig_ax()
    _add_selected_region_outline(
        ax_region,
        resolved_region,
        edge_color=selected_color,
        edge_alpha=state_alpha,
        linewidth=max(1, state_width * 3.0),
    )
    layer_paths["selected_region"] = _save_layer(fig_region, "selected_region")

    valid_until_iso = ""
    issue_iso = ""
    features = (
        outlook_geojson.get("features", []) if isinstance(
            outlook_geojson, dict) else []
    )
    if features:
        first_props = features[0].get("properties", {}) or {}
        valid_until_iso = str(first_props.get("EXPIRE_ISO", ""))
        issue_iso = str(first_props.get("ISSUE_ISO", ""))

    hud_hazard_line = {
        "cat": "Severe Weather",
        "torn": "Tornado",
        "wind": "Severe Wind",
        "hail": "Severe Hail",
        "watches": "Watches",
        "md": "Mesoscale Discussions",
        "mds": "Mesoscale Discussions",
        "reports": "Storm Reports",
    }.get(hazard_key, str(hazard or "").upper())
    hud_product_suffix = (
        "" if (is_reports_only or is_watches_only or is_mds_only) else " Outlook"
    )
    hud_title_line = (
        "Storm Prediction Center"
        if (is_reports_only or is_watches_only or is_mds_only)
        else f"Storm Prediction Center Day {day}"
    )
    if is_watches_only and len(watches_items) == 1:
        hud_hazard_line = watches_items[0].get("title") or hud_hazard_line
    hud_left = f"{hud_title_line}\n{hud_hazard_line}{hud_product_suffix}\n{STATES_FULL.get(resolved_region, resolved_region)}"
    if is_reports_only:
        report_type_key = str(report_type or "all").strip().lower()
        counts = {"torn": 0, "wind": 0, "hail": 0, "other": 0}
        for row in reports_rows:
            key = _report_type_key(row.get("event", ""))
            counts[key] = counts.get(key, 0) + 1

        if report_type_key in {"torn", "wind", "hail"}:
            report_label = {
                "torn": "Tornado",
                "wind": "Wind",
                "hail": "Hail",
            }[report_type_key]
            hud_right = f"{report_label}: {counts.get(report_type_key, 0)}"
        else:
            total_reports = sum(counts.values())
            hud_right = (
                f"Total reports: {total_reports}\n"
                f"Tornado: {counts.get('torn', 0)}\n"
                f"Wind: {counts.get('wind', 0)}\n"
                f"Hail: {counts.get('hail', 0)}\n"
                f"Other: {counts.get('other', 0)}"
            )
    elif is_watches_only or is_mds_only:
        selected_item = None
        if is_watches_only and len(watches_items) == 1:
            selected_item = watches_items[0]
        elif is_mds_only and len(mds_items) == 1:
            selected_item = mds_items[0]

        if selected_item:
            item_issue_utc = selected_item.get("issue_utc")
            item_expire_utc = selected_item.get("expire_utc")
            issue_local = (
                item_issue_utc.astimezone(display_tz)
                if isinstance(item_issue_utc, datetime)
                else None
            )
            expire_local = (
                item_expire_utc.astimezone(display_tz)
                if isinstance(item_expire_utc, datetime)
                else None
            )

            if issue_local and expire_local:
                if is_watches_only:
                    hud_right = (
                        f"Issued: {issue_local.strftime('%I:%M %p %Z')}\n"
                        f"Until: {expire_local.strftime('%I:%M %p %Z')}"
                    )
                else:
                    hud_right = (
                        f"Issued: {issue_local.strftime('%I:%M %p %Z')}\n"
                        f"Valid Until: {expire_local.strftime('%I:%M %p %Z')}"
                    )
            else:
                hud_stamp = time_reference.astimezone(display_tz)
                tz_abbr = hud_stamp.strftime("%Z") or "LOCAL"
                hud_right = hud_stamp.strftime(f"%m/%d/%Y\n%I:%M %p {tz_abbr}")
        else:
            hud_stamp = time_reference.astimezone(display_tz)
            tz_abbr = hud_stamp.strftime("%Z") or "LOCAL"
            hud_right = hud_stamp.strftime(f"%m/%d/%Y\n%I:%M %p {tz_abbr}")
    else:
        hud_right = (
            f"Last Updated: {_format_hud_time(issue_iso, display_tz)}\n"
            f"Valid Until: {_format_hud_time(valid_until_iso, display_tz)}"
        )
    fig_hud, ax_hud = _new_fig_ax()
    _annotate_hud(
        fig_hud,
        ax_hud,
        hud_left,
        hud_right,
        style_config=style_config,
        logo_path=logo_file,
    )
    layer_paths["hud"] = _save_layer(fig_hud, "hud")

    is_categorical = hazard_key == "cat"
    is_tornado_prob = hazard_key == "torn"
    is_wind_prob = hazard_key == "wind"
    is_hail_prob = hazard_key == "hail"
    is_reports_mode = hazard_key == "reports"
    selected_watch_item = (
        watches_items[0] if (is_watches_only and len(
            watches_items) == 1) else None
    )
    legend_mode = (
        "cat"
        if is_categorical
        else (
            "torn"
            if is_tornado_prob
            else (
                "wind"
                if is_wind_prob
                else (
                    "hail"
                    if is_hail_prob
                    else (
                        "reports"
                        if is_reports_mode
                        else ("watches" if is_watches_only else "none")
                    )
                )
            )
        )
    )

    fig_legend, ax_legend = _new_fig_ax()
    _draw_bottom_reference(
        fig_legend,
        legend_entries,
        show_hatch_note=hatch_applied,
        text_color=style_config.get("legend_text_color", "#e2e8f0"),
        legend_mode=legend_mode,
        watch_item=selected_watch_item,
        style_config=style_config,
    )
    layer_paths["legend"] = _save_layer(fig_legend, "legend")

    # Compatibility composite output remains available as image_url fallback.
    fig_comp, ax_comp = _new_fig_ax(transparent=False)
    ax_comp.set_facecolor(ocean_color)
    ax_comp.add_feature(
        cfeature.LAND.with_scale(base_feature_resolution),
        facecolor=land_color,
        zorder=1,
    )
    ax_comp.add_feature(
        cfeature.OCEAN.with_scale(base_feature_resolution),
        facecolor=ocean_color,
        zorder=0,
    )
    if show_country:
        ax_comp.add_feature(
            cfeature.BORDERS.with_scale(base_feature_resolution),
            edgecolor=to_rgba(country_color, country_alpha),
            linewidth=country_width,
            zorder=10,
        )
        ax_comp.add_feature(
            cfeature.LAKES.with_scale(base_feature_resolution),
            facecolor=ocean_color,
            edgecolor="none",
            zorder=10.5,
        )
    if show_states:
        ax_comp.add_feature(
            cfeature.STATES.with_scale(base_feature_resolution),
            edgecolor=to_rgba(state_color, state_alpha),
            linewidth=state_width,
            zorder=91,
        )
    if show_counties and county_feature is not None:
        ax_comp.add_feature(
            county_feature,
            edgecolor=to_rgba(county_color, county_alpha),
            facecolor="none",
            linewidth=county_width,
            zorder=93,
        )
    ax_comp.coastlines(
        resolution=base_feature_resolution,
        linewidth=coastline_width,
        color=to_rgba(coastline_color, coastline_alpha),
        zorder=12,
    )
    if show_outlook_layers:
        _add_outlook_polygons(
            ax_comp,
            outlook_geojson,
            outlook_alpha,
            fill_override=outlook_fill_override,
            edge_override=outlook_edge_override,
        )
        if show_sig_hatch and sig_geojson:
            _add_significant_hatching(
                ax_comp,
                sig_geojson,
                hatch_pattern=hatch_pattern,
                hatch_color=hatch_color,
                hatch_alpha=hatch_alpha,
            )
        if show_sig_hatch:
            _add_primary_sig_hatching(
                ax_comp,
                outlook_geojson,
                hatch_color=hatch_color,
                hatch_alpha=hatch_alpha,
            )
    if watches_items:
        if watch_render_mode == "counties":
            _draw_watch_county_items_layer(
                ax_comp,
                watches_items,
                edge_color=watch_edge_color,
                fill_color=watch_fill_color,
                fill_alpha=watch_fill_alpha,
                linewidth=watch_linewidth,
                label_size=watch_label_size,
                label_color=watch_label_color,
            )
        else:
            _draw_polygon_items_layer(
                ax_comp,
                watches_items,
                edge_color=watch_edge_color,
                fill_color=watch_fill_color,
                fill_alpha=watch_fill_alpha,
                linewidth=watch_linewidth,
                label_size=watch_label_size,
                label_color=watch_label_color,
            )
    if mds_items:
        _draw_polygon_items_layer(
            ax_comp,
            mds_items,
            edge_color=md_edge_color,
            fill_color=md_fill_color,
            fill_alpha=md_fill_alpha,
            linewidth=md_linewidth,
            label_size=md_label_size,
            label_color=md_label_color,
        )
    _add_reports_points(ax_comp, reports_rows, style_config=style_config)
    if show_places:
        plot_cities(
            ax_comp,
            (render_extent[0], render_extent[1],
             render_extent[2], render_extent[3]),
            filename=style_config.get("cities_file", "us-cities.json"),
            style_config=style_config,
            z_cities=94,
        )
    _add_selected_region_outline(
        ax_comp,
        resolved_region,
        edge_color=state_color,
        edge_alpha=state_alpha,
        linewidth=max(4, state_width * 3.0),
    )
    _annotate_hud(
        fig_comp,
        ax_comp,
        hud_left,
        hud_right,
        style_config=style_config,
        logo_path=logo_file,
    )
    _draw_bottom_reference(
        fig_comp,
        legend_entries,
        show_hatch_note=hatch_applied,
        text_color=style_config.get("legend_text_color", "#e2e8f0"),
        legend_mode=legend_mode,
        watch_item=selected_watch_item,
        style_config=style_config,
    )
    fname = f"spc_day{day}_{hazard}_{token}.png"
    save_path = os.path.join(out_dir, fname)
    plt.savefig(save_path, dpi=_SPC_OUTPUT_DPI)
    plt.close(fig_comp)

    sources = [
        s for s in [outlook_source, reports_source, watches_source, mds_source] if s
    ]
    source_label = " + ".join([s for s in sources if s])

    layer_defs = [
        {
            "id": "basemap",
            "label": "Basemap",
            "group": "base",
            "default_visible": True,
            "default_opacity": 1.0,
            "sort": 0,
        },
        {
            "id": "country",
            "label": "Country",
            "group": "base",
            "default_visible": show_country,
            "default_opacity": country_alpha,
            "sort": 10,
        },
        {
            "id": "states",
            "label": "States",
            "group": "base",
            "default_visible": show_states,
            "default_opacity": state_alpha,
            "sort": 91,
        },
        {
            "id": "counties",
            "label": "Counties",
            "group": "base",
            "default_visible": show_counties,
            "default_opacity": county_alpha,
            "sort": 93,
        },
        {
            "id": "coastline",
            "label": "Coastline",
            "group": "base",
            "default_visible": True,
            "default_opacity": coastline_alpha,
            "sort": 13,
        },
        {
            "id": "outlook",
            "label": "Outlook (Combined)",
            "group": "outlook",
            "default_visible": False,
            "default_opacity": outlook_alpha,
            "sort": 20,
        },
        {
            "id": "hatch",
            "label": "Hatch",
            "group": "hatch",
            "default_visible": (not is_reports_only) and hatch_applied,
            "default_opacity": hatch_alpha,
            "sort": 40,
        },
        {
            "id": "reports",
            "label": "Reports",
            "group": "reports",
            "default_visible": include_reports,
            "default_opacity": float(style_config.get("reports_alpha", 0.9)),
            "sort": 50,
        },
        {
            "id": "selected_region",
            "label": "Selected Region",
            "group": "overlay",
            "default_visible": True,
            "default_opacity": 1.0,
            "sort": 92,
        },
        {
            "id": "cities",
            "label": "Cities",
            "group": "cities",
            "default_visible": show_places,
            "default_opacity": LAYER_OPACITY_CITIES,
            "sort": 94,
        },
        {
            "id": "hud",
            "label": "HUD",
            "group": "overlay",
            "default_visible": True,
            "default_opacity": LAYER_OPACITY_HUD,
            "sort": 95,
        },
        {
            "id": "legend",
            "label": "Legend",
            "group": "overlay",
            "default_visible": (
                is_categorical
                or is_tornado_prob
                or is_wind_prob
                or is_hail_prob
                or is_reports_mode
                or (
                    is_watches_only
                    and selected_watch_item is not None
                    and bool((selected_watch_item or {}).get("probabilities", {}))
                )
            ),
            "default_opacity": 1.0,
            "sort": 96,
        },
    ]
    layer_defs.extend(outlook_bin_defs)
    layer_defs.extend(watch_layer_defs)
    layer_defs.extend(md_layer_defs)

    if is_reports_only:
        message = (
            f"Generated SPC storm reports map; reports plotted: {len(reports_rows)}"
        )
    elif is_watches_only:
        mode_text = "counties" if watch_render_mode == "counties" else "watch polygons"
        message = f"Generated SPC watches map ({mode_text}); watches plotted: {len(watches_items)}"
    elif is_mds_only:
        message = (
            f"Generated SPC mesoscale discussion map; MDs plotted: {len(mds_items)}"
        )
    else:
        message = f"Generated SPC map (Day {day} {hazard.upper()})"
    return save_path, message, source_label, layer_paths, layer_defs


def generate_spc_snapshot_from_range(
    *,
    output_dir: str,
    logo_file: Optional[str],
    state_code: str,
    day: int,
    hazard: str,
    start_utc: datetime,
    end_utc: datetime,
    include_reports: bool,
    report_mode: str,
    report_type: str,
    user_tz: str,
    style_config: Optional[dict],
    custom_extent: Optional[tuple],
):
    raise RuntimeError(
        "spc.generate_spc_snapshot_from_range is disabled in Phase 0. "
        "Rendering was removed from spc_utils; use unified weather/export pipeline."
    )

    # For phase 1 archive mode, use the end date as the report date snapshot.
    report_date = end_utc.astimezone(timezone.utc)
    return generate_spc_map(
        output_dir=output_dir,
        logo_file=logo_file,
        state_code=state_code,
        day=day,
        hazard=hazard,
        include_reports=include_reports,
        report_date_utc=report_date,
        report_mode=report_mode,
        report_type=report_type,
        user_tz=user_tz,
        style_config=style_config,
        custom_extent=custom_extent,
    )
