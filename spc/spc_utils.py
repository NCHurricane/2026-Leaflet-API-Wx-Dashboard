import csv
import html
import io
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urljoin

from app_core.upstream_ledger import requests

from lib.geo_utils import CensusCounties
from lib.listing_cache import cached_call

SPC_BASE = "https://www.spc.noaa.gov"
IEM_BASE = "https://mesonet.agron.iastate.edu"
_IEM_TEXT_TIMEOUT_SECONDS = 4
_IEM_TEXT_RETRIES = 1

_DAY12_HAZARDS = {"cat", "torn", "wind",
                  "hail", "cigtorn", "cigwind", "cighail"}
_DAY3_HAZARDS = {"cat", "prob", "sig"}

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
    return _cached_text_custom(
        namespace,
        key,
        url,
        ttl_seconds=ttl_seconds,
        timeout=20,
        retries=3,
    )


def _cached_text_custom(
    namespace: str,
    key: str,
    url: str,
    ttl_seconds: int = 90,
    timeout: int = 20,
    retries: int = 3,
) -> str:
    return cached_call(
        namespace,
        key,
        lambda: _request_text(url, timeout=timeout, retries=retries),
        ttl_seconds=ttl_seconds,
    )


def _cached_json(namespace: str, key: str, url: str, ttl_seconds: int = 90):
    return _cached_json_custom(
        namespace,
        key,
        url,
        ttl_seconds=ttl_seconds,
        timeout=20,
        retries=3,
    )


def _cached_json_custom(
    namespace: str,
    key: str,
    url: str,
    ttl_seconds: int = 90,
    timeout: int = 20,
    retries: int = 3,
):
    return cached_call(
        namespace,
        key,
        lambda: _request_json(url, timeout=timeout, retries=retries),
        ttl_seconds=ttl_seconds,
    )


def _clean_spc_text(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return ""
    pre_blocks = re.findall(
        r"<pre\b[^>]*>(.*?)</pre>", raw, re.IGNORECASE | re.DOTALL)
    if pre_blocks:
        raw = "\n\n".join(pre_blocks)
    else:
        raw = re.sub(
            r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.IGNORECASE | re.DOTALL
        )
        raw = re.sub(
            r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.IGNORECASE | re.DOTALL
        )
        raw = re.sub(
            r"<noscript\b[^>]*>.*?</noscript>",
            " ",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
    cleaned = re.sub(r"<[^>]+>", " ", raw)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned


def _clean_spc_bulletin_text(text: str) -> str:
    """Clean SPC bulletin text while preserving line/paragraph structure."""
    raw = str(text or "")
    if not raw:
        return ""

    pre_blocks = re.findall(
        r"<pre\b[^>]*>(.*?)</pre>", raw, re.IGNORECASE | re.DOTALL
    )
    if pre_blocks:
        raw = "\n\n".join(pre_blocks)
    else:
        raw = re.sub(
            r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.IGNORECASE | re.DOTALL
        )
        raw = re.sub(
            r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.IGNORECASE | re.DOTALL
        )
        raw = re.sub(
            r"<noscript\b[^>]*>.*?</noscript>",
            " ",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
        raw = re.sub(r"</p\s*>", "\n\n", raw, flags=re.IGNORECASE)
        raw = re.sub(r"</div\s*>", "\n", raw, flags=re.IGNORECASE)
        raw = re.sub(r"</li\s*>", "\n", raw, flags=re.IGNORECASE)

    cleaned = re.sub(r"<[^>]+>", "", raw)
    cleaned = html.unescape(cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = "\n".join(line.rstrip() for line in cleaned.split("\n"))
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned




def _current_outlook_url(day: int, hazard: str) -> str:
    hazard = (hazard or "cat").strip().lower()
    if day in (1, 2):
        if hazard not in _DAY12_HAZARDS:
            hazard = "cat"
        return f"{SPC_BASE}/products/outlook/day{day}otlk_{hazard}.lyr.geojson"
    if day == 3:
        if hazard not in _DAY3_HAZARDS:
            hazard = "cat"
        return f"{SPC_BASE}/products/outlook/day3otlk_{hazard}.nolyr.geojson"
    if day in (4, 5, 6, 7, 8):
        return f"{SPC_BASE}/products/exper/day4-8/day{day}prob.lyr.geojson"
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
    return payload, "NWS SPC GeoJSON"


def _outlook_detail_page_url(day: int) -> str:
    if day in (1, 2, 3):
        return f"{SPC_BASE}/products/outlook/day{day}otlk.html"
    if day in (4, 5, 6, 7, 8):
        return f"{SPC_BASE}/products/exper/day4-8/"
    raise ValueError("day must be between 1 and 8")


def _extract_outlook_bulletin(page_html: str, day: int) -> str:
    pre_blocks = re.findall(
        r"<pre\b[^>]*>(.*?)</pre>",
        str(page_html or ""),
        re.IGNORECASE | re.DOTALL,
    )
    if day <= 3:
        heading = re.compile(
            rf"\bDay\s+{day}\s+(?:Convective|Severe Thunderstorm)\s+Outlook\b",
            re.IGNORECASE,
        )
    else:
        heading = re.compile(r"\bDay\s+4-8\s+Convective Outlook\b", re.IGNORECASE)

    for block in pre_blocks:
        cleaned = _clean_spc_bulletin_text(block)
        if heading.search(cleaned):
            return cleaned
    return ""


def _outlook_impacts_table_url(page_html: str, page_url: str, day: int, hazard: str):
    hazard_key = (hazard or "cat").strip().lower()
    if hazard_key.startswith("cig"):
        hazard_key = hazard_key[3:]

    if day in (1, 2):
        suffix = "" if hazard_key == "cat" else hazard_key
        prefix = f"ac{day}{suffix}_"
    elif day == 3:
        suffix = "prob" if hazard_key == "prob" else ""
        prefix = f"ac3{suffix}_"
    else:
        return None

    links = re.findall(
        r"""["']([^"']+_SItable\.html)["']""",
        str(page_html or ""),
        re.IGNORECASE,
    )
    for link in links:
        basename = link.rsplit("/", 1)[-1].lower()
        if basename.startswith(prefix.lower()):
            return urljoin(page_url, link)
    return None


def _parse_outlook_impacts_table(table_html: str) -> list[dict]:
    rows = []
    for row_html in re.findall(
        r"<tr\b[^>]*>(.*?)</tr>",
        str(table_html or ""),
        re.IGNORECASE | re.DOTALL,
    ):
        cells = [
            _clean_spc_text(cell)
            for cell in re.findall(
                r"<td\b[^>]*>(.*?)</td>",
                row_html,
                re.IGNORECASE | re.DOTALL,
            )
        ]
        if len(cells) < 4 or "risk" in cells[0].lower():
            continue
        centers = [
            center.strip(" .")
            for center in re.split(r"\.{3,}", cells[3])
            if center.strip(" .")
        ]
        rows.append(
            {
                "risk": cells[0],
                "area_sq_mi": cells[1],
                "population": cells[2],
                "population_centers": centers,
            }
        )
    return rows


def fetch_outlook_modal_details(day: int, hazard: str, ttl_seconds: int = 300):
    hazard_key = (hazard or "cat").strip().lower()
    if hazard_key.startswith("cig"):
        hazard_key = hazard_key[3:]
    page_url = _outlook_detail_page_url(day)
    page_html = _cached_text_custom(
        "spc_outlook_detail",
        f"day{day}",
        page_url,
        ttl_seconds=ttl_seconds,
        timeout=_IEM_TEXT_TIMEOUT_SECONDS,
        retries=_IEM_TEXT_RETRIES,
    )
    detail = {
        "text": _extract_outlook_bulletin(page_html, day),
        "impacts": [],
        "source_url": page_url,
    }

    table_url = _outlook_impacts_table_url(page_html, page_url, day, hazard_key)
    if table_url:
        try:
            table_html = _cached_text_custom(
                "spc_outlook_impacts",
                f"day{day}:{hazard_key}",
                table_url,
                ttl_seconds=ttl_seconds,
                timeout=_IEM_TEXT_TIMEOUT_SECONDS,
                retries=_IEM_TEXT_RETRIES,
            )
            detail["impacts"] = _parse_outlook_impacts_table(table_html)
        except Exception:
            detail["impacts"] = []
    return detail




# ── Fire Weather Outlook helpers ────────────────────────────────────────────
# Days 1-2 fire weather hazards: dry thunderstorm + wind/RH
_FIRE_WX_HAZARDS_12 = {"dryt", "windrh"}
# Days 3-8 fire weather hazards: categorical and probabilistic for each type
_FIRE_WX_HAZARDS_38 = {"drytcat", "drytprob", "windrhcat", "windrhprob"}


def _fire_wx_url(day: int, hazard: str) -> str:
    """Build GeoJSON URL for SPC Fire Weather Outlook (Day 1-8)."""
    hazard = (hazard or "windrh").strip().lower()
    if day in (1, 2):
        if hazard not in _FIRE_WX_HAZARDS_12:
            hazard = "windrh"
        return f"{SPC_BASE}/products/fire_wx/day{day}fw_{hazard}.lyr.geojson"
    if day in range(3, 9):
        if hazard not in _FIRE_WX_HAZARDS_38:
            hazard = "windrhprob"  # default to windrhprob
        return f"{SPC_BASE}/products/exper/fire_wx/day{day}fw_{hazard}.lyr.geojson"
    raise ValueError("Fire weather outlooks require day 1-8")


def fetch_fire_wx_geojson(day: int, hazard: str):
    """Fetch fire weather outlook GeoJSON. Returns (geojson_dict, source_str)."""
    url = _fire_wx_url(day, hazard)
    payload = _request_json(url)
    return payload, "SPC Fire Wx GeoJSON"


def _fire_outlook_page_url(day: int) -> str:
    if day in (1, 2):
        return f"{SPC_BASE}/products/fire_wx/fwdy{day}.html"
    if day in range(3, 9):
        return f"{SPC_BASE}/products/exper/fire_wx/"
    raise ValueError("Fire weather outlooks require day 1-8")


def _extract_fire_outlook_bulletin(page_html: str, day: int) -> str:
    heading = (
        re.compile(rf"\bDay\s+{day}\s+Fire Weather Outlook\b", re.IGNORECASE)
        if day <= 2
        else re.compile(r"\bDay\s+3-8\s+Fire Weather Outlook\b", re.IGNORECASE)
    )
    for block in re.findall(
        r"<pre\b[^>]*>(.*?)</pre>",
        str(page_html or ""),
        re.IGNORECASE | re.DOTALL,
    ):
        cleaned = _clean_spc_bulletin_text(block)
        if heading.search(cleaned):
            return cleaned
    return ""


def _extract_embedded_impacts_table(page_html: str) -> list[dict]:
    for table_html in re.findall(
        r"<table\b[^>]*>(.*?)</table>",
        str(page_html or ""),
        re.IGNORECASE | re.DOTALL,
    ):
        normalized = _clean_spc_text(table_html).lower()
        if "area (sq. mi.)" not in normalized or "population centers" not in normalized:
            continue
        rows = _parse_outlook_impacts_table(f"<table>{table_html}</table>")
        if rows:
            return rows
    return []


def fetch_fire_outlook_modal_details(day: int, hazard: str, ttl_seconds: int = 300):
    page_url = _fire_outlook_page_url(day)
    page_html = _cached_text_custom(
        "spc_fire_outlook_detail",
        f"day{day}",
        page_url,
        ttl_seconds=ttl_seconds,
        timeout=_IEM_TEXT_TIMEOUT_SECONDS,
        retries=_IEM_TEXT_RETRIES,
    )
    return {
        "text": _extract_fire_outlook_bulletin(page_html, day),
        "impacts": _extract_embedded_impacts_table(page_html) if day <= 3 else [],
        "source_url": page_url,
    }




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


def _parse_watch_probability_page(probability_html: str):
    text = _clean_spc_text(probability_html)
    probabilities = {}
    patterns = {
        "tor2": r"Probability of 2 or more tornadoes\s+(.+?\(\s*\d+%\s*\))",
        "tor_strong": (
            r"Probability of 1 or more strong \(EF2-EF5\) tornadoes"
            r"\s+(.+?\(\s*\d+%\s*\))"
        ),
        "wind10": (
            r"Probability of 10 or more severe wind events"
            r"\s+(.+?\(\s*\d+%\s*\))"
        ),
        "wind65": (
            r"Probability of 1 or more wind events > 65 knots"
            r"\s+(.+?\(\s*\d+%\s*\))"
        ),
        "hail10": (
            r"Probability of 10 or more severe hail events"
            r"\s+(.+?\(\s*\d+%\s*\))"
        ),
        "hail2": (
            r"Probability of 1 or more hailstones > 2 inches"
            r"\s+(.+?\(\s*\d+%\s*\))"
        ),
        "combined6": (
            r"Probability of 6 or more combined severe hail/wind events"
            r"\s+(.+?\(\s*(?:>?\s*)?\d+%\s*\))"
        ),
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            probabilities[key] = re.sub(r"\s+", " ", match.group(1)).strip()
    return probabilities


def _extract_watch_public_text(detail_html: str, watch_id: str) -> str:
    pre_blocks = re.findall(
        r"<pre\b[^>]*>(.*?)</pre>",
        str(detail_html or ""),
        re.IGNORECASE | re.DOTALL,
    )
    watch_number = str(int(watch_id)) if str(watch_id).isdigit() else str(watch_id)
    header_pattern = re.compile(
        rf"(?:Severe\s+Thunderstorm|Tornado)\s+Watch\s+Number\s+0*"
        rf"{re.escape(watch_number)}\b",
        re.IGNORECASE,
    )
    for block in pre_blocks:
        cleaned = _clean_spc_bulletin_text(block)
        if header_pattern.search(cleaned):
            return cleaned
    return ""


def _fetch_watch_modal_details(watch_id: str, ttl_seconds: int = 90):
    detail_url = f"{SPC_BASE}/products/watch/ww{watch_id}.html"
    probability_url = f"{SPC_BASE}/products/watch/ww{watch_id}_prob.html"
    full_text = ""
    probabilities = {}

    try:
        detail_html = _cached_text_custom(
            "spc_watch_detail",
            watch_id,
            detail_url,
            ttl_seconds=ttl_seconds,
            timeout=_IEM_TEXT_TIMEOUT_SECONDS,
            retries=_IEM_TEXT_RETRIES,
        )
        full_text = _extract_watch_public_text(detail_html, watch_id)
    except Exception:
        pass

    try:
        probability_html = _cached_text_custom(
            "spc_watch_probability",
            watch_id,
            probability_url,
            ttl_seconds=ttl_seconds,
            timeout=_IEM_TEXT_TIMEOUT_SECONDS,
            retries=_IEM_TEXT_RETRIES,
        )
        probabilities = _parse_watch_probability_page(probability_html)
    except Exception:
        pass

    return full_text, probabilities




_IEM_WATCH_GEOJSON_URL = f"{IEM_BASE}/api/1/spc_watch_outline.geojson"
_IEM_MCD_GEOJSON_URL = f"{IEM_BASE}/api/1/nws/spc_mcd.geojson"
_SPC_MD_RSS_URL = f"{SPC_BASE}/products/spcmdrss.xml"


def _md_id_from_text_or_link(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return ""
    link_match = re.search(r"/md(\d{4})\.html", raw, re.IGNORECASE)
    if link_match:
        return link_match.group(1)
    title_match = re.search(
        r"\bMesoscale\s+Discussion\s*#?\s*0*(\d{1,4})\b", raw, re.IGNORECASE
    )
    if title_match:
        try:
            return str(int(title_match.group(1))).zfill(4)
        except Exception:
            return ""
    return ""


def _build_spc_md_rss_text_map(ttl_seconds: int = 90) -> dict:
    """Map md_id -> full-text narrative from SPC MD RSS feed."""
    try:
        rss_text = _cached_text("spc_md_rss", "active",
                                _SPC_MD_RSS_URL, ttl_seconds)
    except Exception:
        return {}

    try:
        root = ET.fromstring(rss_text)
    except Exception:
        return {}

    mapped = {}
    for item in root.findall("./channel/item"):
        title = item.findtext("title") or ""
        desc = item.findtext("description") or ""
        link = item.findtext("link") or ""
        guid = item.findtext("guid") or ""
        md_id = (
            _md_id_from_text_or_link(link)
            or _md_id_from_text_or_link(guid)
            or _md_id_from_text_or_link(title)
            or _md_id_from_text_or_link(desc)
        )
        if not md_id:
            continue
        cleaned = _clean_spc_bulletin_text(desc)
        if cleaned:
            mapped[md_id] = {"text": cleaned, "link": link.strip()}
    return mapped


def _fetch_spc_md_detail_text(md_id: str, ttl_seconds: int = 90) -> str:
    detail_url = f"{SPC_BASE}/products/md/md{md_id}.html"
    try:
        detail_html = _cached_text(
            "spc_md_detail", md_id, detail_url, ttl_seconds)
    except Exception:
        return ""
    return _clean_spc_bulletin_text(detail_html)


def _extract_polygon_from_geom(geom: dict) -> list:
    """Return a flat [[lon, lat], ...] ring from a GeoJSON geometry."""
    geom_type = geom.get("type") if geom else ""
    coords = geom.get("coordinates") or [] if geom else []
    if geom_type == "Polygon" and coords:
        return coords[0]
    if geom_type == "MultiPolygon" and coords:
        return coords[0][0]
    return []


def _fetch_wou_county_fips(watch_num: int, ttl_seconds: int = 300) -> list:
    """Fetch and parse county FIPS codes from the SPC WOU text for one watch.

    Results are cached per watch number for *ttl_seconds* (default 5 min) so
    repeat calls within the same watch cycle are free.  Returns a sorted list
    of 5-digit FIPS strings, or an empty list on any error.
    """
    watch_id = f"{watch_num:04d}"
    url = f"{SPC_BASE}/products/watch/wou{watch_id}.html"
    try:
        wou_text = _cached_text("spc_wou_county", watch_id, url, ttl_seconds)
        return _parse_watch_county_fips_from_wou(wou_text)
    except Exception:
        return []


def fetch_active_watch_items(ttl_seconds: int = 90, with_counties: bool = False):
    """Fetch active SPC watches from IEM GeoJSON — single fast request.

    When *with_counties* is True, the WOU text for each watch is fetched in
    parallel (up to 8 workers) and county FIPS codes are populated.  This adds
    a small latency on the first call but results are cached per watch number.
    """
    data = _cached_json(
        "iem_watch_outline", "active", _IEM_WATCH_GEOJSON_URL, ttl_seconds
    )
    features = data.get("features") or []
    now = datetime.now(timezone.utc)
    items = []

    for feat in features:
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}

        watch_num_raw = props.get("num")
        if watch_num_raw is None:
            continue
        try:
            watch_num = int(watch_num_raw)
        except (TypeError, ValueError):
            continue
        watch_id = f"{watch_num:04d}"

        type_code = str(props.get("type") or "").upper()
        if type_code == "TOR":
            watch_type = "Tornado Watch"
        elif type_code == "SVR":
            watch_type = "Severe Thunderstorm Watch"
        else:
            watch_type = f"Watch ({type_code})" if type_code else "Watch"

        def _parse_iso(s: str):
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
            except Exception:
                return None

        issue_utc = _parse_iso(str(props.get("utc_issued") or ""))
        expire_utc = _parse_iso(str(props.get("utc_expired") or ""))

        if expire_utc and expire_utc < now:
            continue

        polygon = _extract_polygon_from_geom(geom)
        if not polygon:
            continue

        label = f"{watch_type} #{watch_num}"
        detail_url = f"https://www.spc.noaa.gov/products/watch/ww{watch_id}.html"

        items.append(
            {
                "id": watch_id,
                "title": watch_type,
                "label": label,
                "short_label": f"WW #{watch_num}",
                "type": watch_type,
                "polygon": polygon,
                "county_fips": [],  # populated below if with_counties=True
                "issue_utc": issue_utc,
                "expire_utc": expire_utc,
                "probabilities": {},
                "full_text": "",
                "detail_url": detail_url,
            }
        )

    if items:
        def _fetch_modal_details(item: dict) -> tuple:
            full_text, probabilities = _fetch_watch_modal_details(
                item["id"],
                ttl_seconds=ttl_seconds,
            )
            return item["id"], full_text, probabilities

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(_fetch_modal_details, item): item["id"]
                for item in items
            }
            details_by_id = {}
            for future in as_completed(futures):
                try:
                    watch_id_key, full_text, probabilities = future.result()
                except Exception:
                    continue
                details_by_id[watch_id_key] = {
                    "full_text": full_text,
                    "probabilities": probabilities,
                }

        for item in items:
            details = details_by_id.get(item["id"], {})
            item["full_text"] = details.get("full_text") or ""
            item["probabilities"] = details.get("probabilities") or {}

    if with_counties and items:
        # Fetch all WOU texts in parallel; map watch_id -> fips list.
        def _fetch(item: dict) -> tuple:
            return item["id"], _fetch_wou_county_fips(int(item["id"]))

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_fetch, item): item["id"] for item in items}
            fips_by_id: dict = {}
            for future in as_completed(futures):
                watch_id_key, fips = future.result()
                fips_by_id[watch_id_key] = fips

        for item in items:
            item["county_fips"] = fips_by_id.get(item["id"], [])

    return items, "SPC Watches (IEM)"




def fetch_active_md_items(ttl_seconds: int = 90):
    """Fetch active SPC MDs from IEM GeoJSON — single fast request."""
    data = _cached_json("iem_mcd_outline", "active",
                        _IEM_MCD_GEOJSON_URL, ttl_seconds)
    features = data.get("features") or []
    now = datetime.now(timezone.utc)
    rss_text_map = _build_spc_md_rss_text_map(ttl_seconds=ttl_seconds)
    items = []

    for feat in features:
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}

        md_num_raw = props.get("num")
        if md_num_raw is None:
            continue
        try:
            md_num = int(md_num_raw)
        except (TypeError, ValueError):
            continue
        md_id = f"{md_num:04d}"

        def _parse_iso(s: str):
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
            except Exception:
                return None

        issue_utc = _parse_iso(str(props.get("issue") or ""))
        expire_utc = _parse_iso(str(props.get("expire") or ""))

        if expire_utc and expire_utc < now:
            continue

        polygon = _extract_polygon_from_geom(geom)
        if not polygon:
            continue

        concerning = str(props.get("concerning") or "").strip()
        label = f"Mesoscale Discussion #{md_num}"
        if concerning:
            label = f"{label} - {concerning}"

        detail_url = f"https://www.spc.noaa.gov/products/md/md{md_id}.html"
        rss_text = str((rss_text_map.get(md_id) or {}).get("text") or "")
        full_text = rss_text or _fetch_spc_md_detail_text(
            md_id, ttl_seconds=ttl_seconds)

        items.append(
            {
                "id": md_id,
                "title": f"Mesoscale Discussion #{md_num}",
                "label": label,
                "short_label": f"MD #{md_num}",
                "polygon": polygon,
                "issue_utc": issue_utc,
                "expire_utc": expire_utc,
                "full_text": full_text,
                "detail_url": detail_url,
            }
        )

    source = "SPC Mesoscale Discussions (IEM + SPC RSS text)"
    if not rss_text_map:
        source = "SPC Mesoscale Discussions (IEM + SPC HTML text fallback)"
    return items, source




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
