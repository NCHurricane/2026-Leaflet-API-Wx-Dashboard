"""Background worker for the Tropical **Archive** (HURDAT2 best-track history).

Phase A scope: Atlantic basin only. Downloads the NHC HURDAT2 Atlantic file,
parses every storm (1851→present), and emits two cached artifacts:

  * ``cache/tropical/archive/catalog/seasons.json`` — a light per-season index.
  * ``cache/tropical/archive/storms/<ATCFID>/storm.json`` — a per-storm payload
    that matches the **live** ``storm.json`` shape (gis_layers.best_track_line /
    best_track_points + track[]), so the existing frontend renderers are reused
    as-is.

Archive data is immutable, so per-storm payloads are cached permanently. The
catalog is rebuilt only when the source HURDAT2 file changes (or on ``--force``).
"""

from __future__ import annotations

import argparse
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path for both module and direct execution
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from typing import Any  # noqa: E402

from app_core.upstream_ledger import urlopen  # noqa: E402
from workers._freshness import mark_run_complete  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "tropical"
ARCHIVE_DIR = CACHE_DIR / "archive"
SOURCE_DIR = ARCHIVE_DIR / "source"
CATALOG_DIR = ARCHIVE_DIR / "catalog"
STORMS_DIR = ARCHIVE_DIR / "storms"
CATALOG_FILE = CATALOG_DIR / "seasons.json"

_USER_AGENT = "NCHurricane Dashboard/2026 (+https://nchurricane.com)"

# HURDAT2 source files. The published filenames carry a revision-date suffix that
# changes each season, so we discover the current name from the listing page
# rather than hardcoding a URL that will 404 after the next reanalysis.
#   * Atlantic file → AL storms.
#   * NE/North-Central Pacific file → EP + CP storms (keyed by ATCF prefix).
_HURDAT_INDEX_URL = "https://www.nhc.noaa.gov/data/hurdat/"
_AL_FILE_RE = re.compile(r"hurdat2-1851-\d{4}-\d+\.txt")
_NEPAC_FILE_RE = re.compile(r"hurdat2-nepac-1949-\d{4}-\d+\.txt")

_BASIN_NAMES = {"AL": "Atlantic", "EP": "Eastern Pacific", "CP": "Central Pacific"}

# Phase B — archived forecast GIS (cone / forecast track+points / watches & warnings
# / wind radii) for modern storms. NHC's 5-day cone GIS archive begins ~2008.
_GIS_MIN_YEAR = 2008
_GIS_ARCHIVE_BASE = "https://www.nhc.noaa.gov/gis/forecast/archive/"
_ARCHIVE_RESULTS_URL = "https://www.nhc.noaa.gov/gis/archive_forecast_results.php?id={id}&year={year}"
_SYNOPTIC_HHMM = {"0000", "0600", "1200", "1800"}
_CYCLONE_STATUS = {"HU", "TS", "TD", "SS", "SD"}
_ADVISORY_CACHE_LOCKS_GUARD = threading.Lock()
_ADVISORY_CACHE_LOCKS: dict[tuple[str, str], threading.Lock] = {}

# HURDAT2 2-letter status codes → short STORMTYPE codes the frontend classifier
# (_tropicalCategoryKey in frontend/pages/tropical/tropical-app.js) understands on best-track features,
# which carry STORMTYPE + SS but no MAXWIND.
_STATUS_TO_STORMTYPE = {
    "HU": "HU",  # Hurricane
    "TS": "TS",  # Tropical storm
    "TD": "TD",  # Tropical depression
    "SS": "SS",  # Subtropical storm
    "SD": "SD",  # Subtropical depression
    "EX": "EX",  # Extratropical
    "LO": "LO",  # Low (not a tropical cyclone)
    "WV": "WV",  # Tropical wave
    "DB": "DB",  # Disturbance
}

# Saffir-Simpson knots → category number, mirroring _tropicalCategoryKeyFromWind.
_SS_THRESHOLDS = ((137, 5), (113, 4), (96, 3), (83, 2), (64, 1))

_MISSING_WIND = -99
_MISSING_PRESSURE = -999


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _saffir_ss(wind_kt: int | None) -> int:
    """Saffir-Simpson category number from sustained wind, or 0 if sub-hurricane."""
    if wind_kt is None:
        return 0
    for threshold, cat in _SS_THRESHOLDS:
        if wind_kt >= threshold:
            return cat
    return 0


def _category_key_from_wind(wind_kt: int | None) -> str:
    """Category key string matching the frontend's _tropicalCategoryKeyFromWind."""
    if wind_kt is None:
        return "OTHER"
    ss = _saffir_ss(wind_kt)
    if ss:
        return str(ss)
    if wind_kt >= 34:
        return "TS"
    return "TD"


def _fix_category_key(status: str, wind_kt: int | None) -> str:
    """Classification key for one best-track fix, matching _tropicalCategoryKey.

    Used both to set the ``SS`` field and to segment the track by intensity so
    segment colors line up with the live renderer.
    """
    if status in ("EX", "LO"):
        return "OTHER"
    ss = _saffir_ss(wind_kt)
    if status == "HU":
        ss = max(ss, 1)  # guard against HU fixes recorded just under 64 kt
    if 1 <= ss <= 5:
        return str(ss)
    if status in ("TS", "SS"):
        return "TS"
    if status in ("TD", "SD", "DB", "WV"):
        return "TD"
    return _category_key_from_wind(wind_kt)


def _fix_ss(status: str, wind_kt: int | None) -> int:
    """SS field for a fix: 1-5 at hurricane strength (incl. HU floor), else 0."""
    ss = _saffir_ss(wind_kt)
    if status == "HU":
        ss = max(ss, 1)
    return ss


_CLASS_LABELS = {
    "5": "Category 5 Hurricane",
    "4": "Category 4 Hurricane",
    "3": "Category 3 Hurricane",
    "2": "Category 2 Hurricane",
    "1": "Category 1 Hurricane",
    "TS": "Tropical Storm",
    "TD": "Tropical Depression",
    "OTHER": "Post/Non-Tropical",
}


# ── Networking & I/O ────────────────────────────────────────────────────────
def _request_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urlopen(req, timeout=60) as resp:  # noqa: S310 (trusted NHC host)
        return resp.read().decode("utf-8", errors="replace")


def _discover_hurdat2_url(pattern: re.Pattern[str], label: str) -> str:
    """Scrape the HURDAT listing for the current file name matching *pattern*."""
    listing = _request_text(_HURDAT_INDEX_URL)
    names = pattern.findall(listing)
    if not names:
        raise ValueError(f"Could not locate a {label} HURDAT2 file in the listing.")
    # Names sort lexically by embedded end-year then revision date; newest last.
    return _HURDAT_INDEX_URL + sorted(set(names))[-1]


def _download_hurdat2_file(
    cached: Path,
    pattern: re.Pattern[str],
    label: str,
    force: bool,
    source_file: Path | None,
) -> Path:
    """Fetch (or reuse) one HURDAT2 text file into the source cache."""
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    if source_file is not None:
        text = Path(source_file).read_text(encoding="utf-8", errors="replace")
        cached.write_text(text, encoding="utf-8")
        return cached
    if cached.exists() and not force:
        return cached
    text = _request_text(_discover_hurdat2_url(pattern, label))
    cached.write_text(text, encoding="utf-8")
    return cached


def download_hurdat2(
    force: bool = False,
    atlantic_file: Path | None = None,
    nepac_file: Path | None = None,
) -> dict[str, Path]:
    """Return source paths keyed by file: ``{"atlantic": ..., "nepac": ...}``.

    Each ``*_file`` arg uses a caller-supplied local file (offline/testing);
    otherwise the cached copy is reused unless ``force`` is set or it is missing.
    """
    return {
        "atlantic": _download_hurdat2_file(
            SOURCE_DIR / "hurdat2-al.txt", _AL_FILE_RE, "Atlantic", force, atlantic_file
        ),
        "nepac": _download_hurdat2_file(
            SOURCE_DIR / "hurdat2-nepac.txt", _NEPAC_FILE_RE, "NE/Central Pacific", force, nepac_file
        ),
    }


# ── HURDAT2 parsing ─────────────────────────────────────────────────────────
def _parse_lat(token: str) -> float | None:
    token = token.strip()
    if not token:
        return None
    value = float(token[:-1])
    return -value if token[-1].upper() == "S" else value


def _parse_lon(token: str) -> float | None:
    token = token.strip()
    if not token:
        return None
    value = float(token[:-1])
    return -value if token[-1].upper() == "W" else value


def _parse_int(token: str, missing: int) -> int | None:
    token = token.strip()
    if not token:
        return None
    value = int(token)
    return None if value == missing else value


def _parse_btk_coord(token: str) -> float | None:
    """Parse an ATCF b-deck coordinate (tenths of a degree, e.g. ``252N`` → 25.2)."""
    token = token.strip()
    if len(token) < 2:
        return None
    hemi = token[-1].upper()
    if hemi not in ("N", "S", "E", "W"):
        return None
    try:
        value = int(token[:-1]) / 10.0
    except ValueError:
        return None
    return -value if hemi in ("S", "W") else value


def parse_hurdat2(path: Path) -> Iterator[dict[str, Any]]:
    """Yield one storm dict per HURDAT2 record group.

    Basin is derived from the ATCF id prefix (AL/EP/CP), so a single NE/Central
    Pacific file yields both EP and CP storms. Storm dict:
    ``{atcf_id, name, year, basin, landfall, rows:[...]}`` where each row is
    ``{ts, status, lat, lon, wind_kt, pres_mb, record_id}``.
    """
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    n = len(lines)
    while i < n:
        header = lines[i].strip()
        i += 1
        if not header:
            continue
        parts = [p.strip() for p in header.split(",")]
        if len(parts) < 3 or not re.fullmatch(r"(AL|EP|CP)\d{2}\d{4}", parts[0]):
            continue
        atcf_id, name, row_count = parts[0], parts[1], int(parts[2])
        basin = atcf_id[:2]
        rows: list[dict[str, Any]] = []
        landfall = False
        for _ in range(row_count):
            if i >= n:
                break
            cells = [c.strip() for c in lines[i].split(",")]
            i += 1
            if len(cells) < 7:
                continue
            record_id = cells[2]
            if record_id.upper() == "L":
                landfall = True
            try:
                ts = datetime.strptime(cells[0] + cells[1], "%Y%m%d%H%M").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue
            rows.append(
                {
                    "ts": ts,
                    "status": cells[3].strip().upper(),
                    "lat": _parse_lat(cells[4]),
                    "lon": _parse_lon(cells[5]),
                    "wind_kt": _parse_int(cells[6], _MISSING_WIND),
                    "pres_mb": _parse_int(cells[7], _MISSING_PRESSURE) if len(cells) > 7 else None,
                    "record_id": record_id,
                }
            )
        if not rows:
            continue
        yield {
            "atcf_id": atcf_id,
            "name": name or "UNNAMED",
            "year": int(atcf_id[-4:]),
            "basin": basin,
            "landfall": landfall,
            "rows": rows,
        }


# ── Current-season ATCF best-track (b-deck) ─────────────────────────────────
# HURDAT2 is only published after a season closes, so the in-progress season is
# sourced from NHC's live ATCF best-track ("b-deck") files. parse_atcf_btk emits
# the same storm dict shape as parse_hurdat2 so the whole catalog/payload pipeline
# is reused unchanged.
_ATCF_BTK_INDEX_URL = "https://ftp.nhc.noaa.gov/atcf/btk/"
# Numbered cyclones use 01–49; 70+ are internal/test/invest (e.g. 90L) designations.
_ATCF_MAX_STORM_NUM = 49
_ATCF_BTK_SOURCE = "NHC Best Track (preliminary)"


def _discover_btk_files(year: int) -> list[str]:
    """List current-season b-deck filenames for AL/EP/CP numbered cyclones."""
    listing = _request_text(_ATCF_BTK_INDEX_URL)
    pattern = re.compile(rf"b(al|ep|cp)(\d{{2}}){year}\.dat", re.IGNORECASE)
    names: set[str] = set()
    for match in pattern.finditer(listing):
        if int(match.group(2)) <= _ATCF_MAX_STORM_NUM:
            names.add(match.group(0).lower())
    return sorted(names)


def parse_atcf_btk(text: str) -> dict[str, Any] | None:
    """Parse one b-deck file into the parse_hurdat2 storm dict shape.

    b-deck rows repeat each synoptic time once per wind-radii threshold (34/50/64
    kt); only the first row per timestamp carries the fix we need. Returns ``None``
    when the file has no usable BEST rows.
    """
    atcf_id: str | None = None
    name = "UNNAMED"
    by_ts: dict[datetime, dict[str, Any]] = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.split(",")]
        if len(cells) < 11:
            continue
        basin = cells[0].upper()
        if basin not in _BASIN_NAMES or cells[4].upper() != "BEST":
            continue
        try:
            ts = datetime.strptime(cells[2], "%Y%m%d%H").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if atcf_id is None:
            atcf_id = f"{basin}{cells[1]}{ts.year}"
        # Storm name lives near the end of best-track rows (ATCF column 28).
        if len(cells) > 27 and cells[27]:
            candidate = cells[27].strip().upper()
            if candidate and candidate not in ("INVEST", "NONAME", "UNKNOWN", "GENESIS"):
                name = candidate
        if ts in by_ts:
            continue
        by_ts[ts] = {
            "ts": ts,
            "status": cells[10].strip().upper(),
            "lat": _parse_btk_coord(cells[6]),
            "lon": _parse_btk_coord(cells[7]),
            "wind_kt": _parse_int(cells[8], 0),
            "pres_mb": _parse_int(cells[9], 0),
            "record_id": "",
        }
    if not atcf_id or not by_ts:
        return None
    rows = [by_ts[t] for t in sorted(by_ts)]
    return {
        "atcf_id": atcf_id,
        "name": name or "UNNAMED",
        "year": int(atcf_id[-4:]),
        "basin": atcf_id[:2],
        "landfall": False,
        "rows": rows,
    }


def parse_current_season_btk(year: int) -> Iterator[dict[str, Any]]:
    """Yield current-season storm dicts from NHC's live ATCF b-deck files."""
    for filename in _discover_btk_files(year):
        try:
            storm = parse_atcf_btk(_request_text(_ATCF_BTK_INDEX_URL + filename))
        except Exception as exc:  # one bad file must not drop the rest of the season
            print(f"[tropical_archive_worker] b-deck {filename} skipped: {exc}")
            continue
        if storm:
            yield storm


# ── Payload assembly ────────────────────────────────────────────────────────
def _time_label(ts: datetime) -> str:
    return ts.strftime("%b %d %HZ")


def _best_track_features(storm: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """Build per-intensity-segment LineString features + per-fix Point features."""
    rows = [r for r in storm["rows"] if r["lat"] is not None and r["lon"] is not None]
    storm_num = storm["atcf_id"][2:4]
    name = storm["name"]

    point_features: list[dict] = []
    for r in rows:
        status = r["status"]
        wind = r["wind_kt"]
        ss = _fix_ss(status, wind)
        ts: datetime = r["ts"]
        point_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
                "properties": {
                    "STORMNAME": name,
                    "DTG": ts.strftime("%Y%m%d%H"),
                    "YEAR": ts.year,
                    "MONTH": ts.month,
                    "DAY": ts.day,
                    "HHMM": ts.strftime("%H%M"),
                    "MSLP": r["pres_mb"],
                    "BASIN": storm["basin"],
                    "STORMNUM": storm_num,
                    "STORMTYPE": _STATUS_TO_STORMTYPE.get(status, status),
                    "INTENSITY": wind,
                    "SS": ss,
                    "LAT": r["lat"],
                    "LON": r["lon"],
                },
            }
        )

    # Split the track into runs of equal category key; share each boundary fix
    # with the next run so the colored line stays continuous (no gaps). Also break
    # (without a shared fix) wherever the track crosses the antimeridian, so a
    # Pacific storm doesn't draw a line smeared across the whole map.
    line_features: list[dict] = []
    run: list[dict] = []
    run_key: str | None = None
    for r in rows:
        key = _fix_category_key(r["status"], r["wind_kt"])
        crosses_dateline = bool(run) and abs(r["lon"] - run[-1]["lon"]) > 180
        if run_key is None:
            run, run_key = [r], key
        elif crosses_dateline:
            if len(run) >= 2:
                line_features.append(_segment_feature(run, storm_num))
            run, run_key = [r], key
        elif key == run_key:
            run.append(r)
        else:
            run.append(r)  # boundary fix closes this run
            line_features.append(_segment_feature(run, storm_num))
            run, run_key = [r], key
    if len(run) >= 2:
        line_features.append(_segment_feature(run, storm_num))

    return line_features, point_features


def _segment_feature(run: list[dict], storm_num: str) -> dict:
    first = run[0]
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[r["lon"], r["lat"]] for r in run],
        },
        "properties": {
            "STORMNUM": storm_num,
            "STORMTYPE": _STATUS_TO_STORMTYPE.get(first["status"], first["status"]),
            "SS": _fix_ss(first["status"], first["wind_kt"]),
        },
    }


def _feature_collection(features: list[dict]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


def _gis_layer(features: list[dict], rel_path: str, source: str = "HURDAT2") -> dict[str, Any]:
    return {
        "cache_path": rel_path,
        "feature_count": len(features),
        "source_path": source,
        "geojson": _feature_collection(features),
    }


def build_storm_payload(storm: dict[str, Any], source: str = "HURDAT2") -> dict[str, Any]:
    """Emit the live storm.json shape for one archived storm."""
    atcf = storm["atcf_id"]
    rows = storm["rows"]
    winds = [r["wind_kt"] for r in rows if r["wind_kt"] is not None]
    peak_wind = max(winds) if winds else None
    peak_key = _category_key_from_wind(peak_wind)
    start_ts: datetime = rows[0]["ts"]
    end_ts: datetime = rows[-1]["ts"]

    line_features, point_features = _best_track_features(storm)
    rel = f"cache/tropical/archive/storms/{atcf}/storm.json"

    track = [
        {
            "hour": "",
            "time": _time_label(r["ts"]),
            "lat": r["lat"],
            "lon": r["lon"],
            "windKt": r["wind_kt"],
        }
        for r in rows
        if r["lat"] is not None and r["lon"] is not None
    ]

    return {
        "status": "success",
        "stormId": atcf,
        "storm": {
            "id": atcf,
            "name": storm["name"],
            "classification": _CLASS_LABELS.get(peak_key, "Tropical Cyclone"),
            "year": storm["year"],
        },
        "basin": storm["basin"],
        "basinName": _BASIN_NAMES.get(storm["basin"], storm["basin"]),
        "advisory": {},
        "track": track,
        "products": {},
        "graphics": [],
        "gis_assets": [],
        "gis_layers": {
            "best_track_line": _gis_layer(line_features, rel, source),
            "best_track_points": _gis_layer(point_features, rel, source),
        },
        "updated": end_ts.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "cached_at": _utc_now_iso(),
        "source": source,
        "startDate": start_ts.date().isoformat(),
        "endDate": end_ts.date().isoformat(),
    }


def _catalog_entry(storm: dict[str, Any]) -> dict[str, Any]:
    rows = storm["rows"]
    winds = [r["wind_kt"] for r in rows if r["wind_kt"] is not None]
    peak_wind = max(winds) if winds else None
    return {
        "id": storm["atcf_id"],
        "name": storm["name"],
        "peakCategory": _category_key_from_wind(peak_wind),
        "peakWindKt": peak_wind,
        "startDate": rows[0]["ts"].date().isoformat(),
        "endDate": rows[-1]["ts"].date().isoformat(),
        "landfall": storm["landfall"],
        # Hint: modern storms likely have archived forecast GIS (fetched on open).
        "hasGis": storm["year"] >= _GIS_MIN_YEAR,
    }


# ── Phase B: archived forecast GIS (lazy, per-storm) ────────────────────────
def _download_zip(url: str, dest: Path) -> bool:
    """Download a binary zip to *dest*. Returns False on 404/HTTP error."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req, timeout=60) as resp:  # noqa: S310 (trusted NHC)
            data = resp.read()
    except urllib.error.HTTPError:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def _list_archive_advisories(atcf_id: str, year: int) -> list[str]:
    """Full (non-intermediate) 5-day advisory numbers present in the GIS archive."""
    url = _ARCHIVE_RESULTS_URL.format(id=atcf_id.lower(), year=year)
    html = _request_text(url)
    advs = re.findall(rf"{re.escape(atcf_id.lower())}_5day_(\d+)\.zip", html)
    return sorted(set(advs))


def _peak_advisory_number(payload: dict[str, Any], advs: list[str]) -> str | None:
    """Pick the archived advisory issued nearest the storm's peak intensity.

    Advisories run every 6 h from genesis, so the count of synoptic cyclone fixes
    up to (and including) the peak-wind fix estimates the advisory number. Clamp
    to what the archive actually has and snap to the nearest available number.
    """
    features = (payload.get("gis_layers", {}).get("best_track_points", {})
                .get("geojson", {}).get("features") or [])
    if not features or not advs:
        return None
    synoptic = [
        f for f in features
        if str(f["properties"].get("HHMM")) in _SYNOPTIC_HHMM
        and str(f["properties"].get("STORMTYPE")) in _CYCLONE_STATUS
    ]
    if not synoptic:
        return None
    peak_idx = max(
        range(len(synoptic)),
        key=lambda i: synoptic[i]["properties"].get("INTENSITY") or 0,
    )
    target = peak_idx + 1  # advisory numbers are 1-based
    nums = sorted(int(a) for a in advs)
    best = min(nums, key=lambda n: abs(n - target))
    # Re-pad to the archive's zero-padded width (e.g. "013").
    width = len(advs[0])
    return str(best).zfill(width)


def enrich_storm_gis(atcf_id: str, force: bool = False) -> bool:
    """Lazily attach archived forecast GIS to one storm's cached payload.

    Returns True when the cached storm.json was (re)written, so the caller can
    reload it. No-op (returns False) for pre-archive storms or when already done.
    """
    import json

    sid = atcf_id.upper()
    storm_json = STORMS_DIR / sid / "storm.json"
    if not storm_json.is_file():
        return False
    payload = json.loads(storm_json.read_text(encoding="utf-8"))
    # Skip only when fully enriched. Storms enriched before the advisory index
    # existed (Phase B) lack "advisories" — re-enrich them to self-heal the cache.
    if payload.get("gis_enriched") and "advisories" in payload and not force:
        return False

    year = int(payload.get("storm", {}).get("year") or sid[-4:])
    # Definitive outcomes mark the payload enriched so we never refetch; transient
    # network failures are left unmarked so a later open retries.
    if year < _GIS_MIN_YEAR:
        payload["advisories"] = []
        payload["hasAdvisories"] = False
        payload["gis_enriched"] = True
        storm_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return True

    # One fetch of the archive results page → both the full-advisory list (for the
    # peak snapshot) and the full+intermediate step list (for the scrubber index).
    results_html = _request_text(_ARCHIVE_RESULTS_URL.format(id=sid.lower(), year=year))
    bid = sid.lower()
    advs = sorted(set(re.findall(rf"{re.escape(bid)}_5day_(\d+)\.zip", results_html)))
    steps = sorted(
        set(re.findall(rf"{re.escape(bid)}_5day_(\d+[A-Z]?)\.zip", results_html)),
        key=_advisory_step_key,
    )
    payload["advisories"] = steps
    payload["hasAdvisories"] = bool(steps)

    adv = _peak_advisory_number(payload, advs)
    if adv is None:
        payload["gis_enriched"] = True
        storm_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return True

    from workers.tropical_worker import (
        _FIVE_DAY_LAYER_KINDS,
        _FORECAST_WIND_RADII_LAYER_KINDS,
        _extract_gis_layers_from_zip,
    )

    gis_dir = STORMS_DIR / sid / "gis"
    layers: dict[str, Any] = {}
    five_day = gis_dir / f"{sid.lower()}_5day_{adv}.zip"
    if _download_zip(f"{_GIS_ARCHIVE_BASE}{sid.lower()}_5day_{adv}.zip", five_day):
        layers.update(_extract_gis_layers_from_zip(five_day, _FIVE_DAY_LAYER_KINDS, sid, gis_dir))
    fcst = gis_dir / f"{sid.lower()}_fcst_{adv}.zip"
    if _download_zip(f"{_GIS_ARCHIVE_BASE}{sid.lower()}_fcst_{adv}.zip", fcst):
        layers.update(_extract_gis_layers_from_zip(fcst, _FORECAST_WIND_RADII_LAYER_KINDS, sid, gis_dir))

    payload.setdefault("gis_layers", {}).update(layers)
    payload["gis_enriched"] = True
    payload["gis_advisory"] = adv if layers else None
    storm_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return True


# ── Phase C: per-advisory scrubber payloads ─────────────────────────────────
_ADVISORY_TEXT_KINDS = (
    ("TCP", "Public Advisory", "public"),
    ("TCM", "Forecast Advisory", "fstadv"),
    ("TCD", "Forecast Discussion", "discus"),
    ("PWS", "Wind Speed Probabilities", "wndprb"),
)
_ISSUED_RE = re.compile(
    r"\d{3,4}\s+(?:AM|PM)\s+[A-Z]{2,4}\s+[A-Z]{3}\s+[A-Z]{3}\s+\d{1,2}\s+\d{4}", re.I
)
_ARCHIVE_TIMEZONE_OFFSETS = {
    "AST": -4,
    "ADT": -3,
    "EST": -5,
    "EDT": -4,
    "CST": -6,
    "CDT": -5,
    "MST": -7,
    "MDT": -6,
    "PST": -8,
    "PDT": -7,
    "HST": -10,
    "HDT": -9,
    "UTC": 0,
    "GMT": 0,
}


def parse_archive_issued_iso(value: object) -> str | None:
    """Normalize an NHC archive issuance line to an offset-aware ISO timestamp."""
    match = re.fullmatch(
        r"(?P<hm>\d{3,4})\s+(?P<ampm>AM|PM)\s+(?P<zone>[A-Z]{2,4})\s+"
        r"[A-Z]{3}\s+(?P<month>[A-Z]{3})\s+(?P<day>\d{1,2})\s+(?P<year>\d{4})",
        str(value or "").strip(),
        re.I,
    )
    if not match:
        return None
    zone = match.group("zone").upper()
    offset_hours = _ARCHIVE_TIMEZONE_OFFSETS.get(zone)
    if offset_hours is None:
        return None
    hm = match.group("hm").zfill(4)
    try:
        local = datetime.strptime(
            f"{hm} {match.group('ampm')} {match.group('month')} "
            f"{match.group('day')} {match.group('year')}",
            "%I%M %p %b %d %Y",
        )
    except ValueError:
        return None
    return local.replace(
        tzinfo=timezone(timedelta(hours=offset_hours))
    ).isoformat()


def _advisory_step_key(step: str) -> tuple[int, str]:
    m = re.fullmatch(r"(\d+)([A-Z]?)", step)
    return (int(m.group(1)), m.group(2) or "") if m else (0, "")


# NHC per-advisory graphics, by era. N is the FULL advisory number (intermediates
# reuse their full advisory's graphic). The frontend probes each URL and hides
# 404s, so we can emit candidates without per-image checks. Graphics only attach
# where the advisory scrubber exists (5-day GIS archive → 2008+).
#   * 2017→present: PNG package at graphics/{ATCFID}/{ATCFID}_{product}_{N}.png
#   * 2008–2016:    GIF package at graphics/{al09}/{ATCFID}{suffix}.GIF
# Pre-2008 storms have no scrubber (no forecast GIS), so no per-advisory graphics.
_GRAPHICS_MIN_YEAR = 2008
_GRAPHICS_PNG_ERA = 2017
_ARCHIVE_GRAPHICS_PNG = (
    ("5day_cone_no_line", "5-Day Cone & Track"),
    ("3day_cone_no_line", "3-Day Cone & Track"),
    ("current_wind", "Current Wind Field"),
    ("wind_history", "Wind History"),
    ("key_messages", "Key Messages"),
    ("most_likely_toa_34", "Most Likely Arrival of TS Winds"),
    ("earliest_reasonable_toa_34", "Earliest Reasonable Arrival of TS Winds"),
    ("wind_probs_34_F120", "Wind Speed Probabilities (34 kt)"),
)
# 2008–2016 GIF templates: {p}=ATCFID (e.g. AL092008), {a3}=3-digit advisory.
_ARCHIVE_GRAPHICS_GIF = (
    ("{p}_5NLW_{a3}_0.GIF", "5-Day Track (no line)"),
    ("{p}_3NLW_{a3}_0.GIF", "3-Day Track (no line)"),
    ("{p}R.{a3}.GIF", "Wind Field"),
    ("{p}S.{a3}.GIF", "Wind Swath"),
    ("{p}T.{a3}.GIF", "Wind Speed Forecast"),
)


def _archive_graphics(sid: str, year: int, adv_num: int) -> list[dict[str, str]]:
    """Candidate per-advisory graphic image URLs (frontend probes + hides 404s)."""
    if year < _GRAPHICS_MIN_YEAR:
        return []
    if year >= _GRAPHICS_PNG_ERA:
        base = f"https://www.nhc.noaa.gov/archive/{year}/graphics/{sid}/"
        return [
            {"group": "NHC Graphics", "label": label, "url": f"{base}{sid}_{prod}_{adv_num}.png"}
            for prod, label in _ARCHIVE_GRAPHICS_PNG
        ]
    folder = _archive_text_folder(sid)  # e.g. AL092008 → "al09"
    a3 = str(adv_num).zfill(3)
    base = f"https://www.nhc.noaa.gov/archive/{year}/graphics/{folder}/"
    return [
        {"group": "NHC Graphics", "label": label, "url": base + tmpl.format(p=sid, a3=a3)}
        for tmpl, label in _ARCHIVE_GRAPHICS_GIF
    ]


def _archive_text_folder(sid: str) -> str:
    """NHC text-archive folder for a storm, e.g. AL092021 → 'al09'."""
    return f"{sid[:2].lower()}{sid[2:4]}"


def _fetch_archive_text(url: str) -> str | None:
    """Fetch an archived .shtml advisory and return its <pre> body as plain text."""
    import html as _html

    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req, timeout=40) as resp:  # noqa: S310 (trusted NHC)
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError):
        return None
    body = re.search(r"<pre>(.*?)</pre>", raw, re.S | re.I)
    text = _html.unescape(re.sub(r"<[^>]+>", "", body.group(1) if body else raw)).strip()
    return text or None


def _fetch_url_text(url: str) -> str | None:
    """Fetch a URL's raw text (e.g. a KML), or None on 404/error."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req, timeout=40) as resp:  # noqa: S310 (trusted NHC)
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError):
        return None


def build_advisory_payload(atcf_id: str, step: str) -> dict[str, Any] | None:
    """Build the live-detail payload for one archived advisory (text + GIS).

    ``step`` is a GIS-style advisory id: ``"013"`` (full) or ``"014A"`` (3-hourly
    intermediate). Intermediates have their own public advisory (``public_a``) and
    GIS, but inherit the full advisory's forecast/discussion text.
    """
    from workers.tropical_worker import (
        _FIVE_DAY_LAYER_KINDS,
        _FORECAST_WIND_RADII_LAYER_KINDS,
        _extract_gis_layers_from_zip,
        _parse_advisory,
        _parse_initial_wind_extent_kml,
        _parse_peak_surge_kml,
        _parse_storm_surge_kml,
        _parse_track,
    )

    sid = atcf_id.upper()
    step = step.upper()
    m = re.fullmatch(r"(\d+)([A-Z]?)", step)
    if not m:
        return None
    num, suffix = m.group(1), m.group(2)
    year = int(sid[-4:])
    bid = sid.lower()
    base = f"https://www.nhc.noaa.gov/archive/{year}/{_archive_text_folder(sid)}/"

    public_url = (
        f"{base}{bid}.public_{suffix.lower()}.{num}.shtml" if suffix
        else f"{base}{bid}.public.{num}.shtml"
    )
    text_urls = {
        "TCP": public_url,
        "TCM": f"{base}{bid}.fstadv.{num}.shtml",
        "TCD": f"{base}{bid}.discus.{num}.shtml",
        "PWS": f"{base}{bid}.wndprb.{num}.shtml",
    }
    texts = {code: _fetch_archive_text(url) for code, url in text_urls.items()}

    advisory = _parse_advisory(texts["TCP"]) if texts["TCP"] else {}
    track = _parse_track(texts["TCM"]) if texts["TCM"] else []
    issued_match = _ISSUED_RE.search(texts["TCP"] or "")
    issued = issued_match.group(0) if issued_match else ""

    products: dict[str, Any] = {}
    for code, label, _kind in _ADVISORY_TEXT_KINDS:
        if texts.get(code):
            products[code] = {
                "code": code,
                "label": label,
                "url": text_urls[code],
                "text": texts[code],
            }

    gis_dir = STORMS_DIR / sid / "advisories" / step / "gis"
    layers: dict[str, Any] = {}
    five = gis_dir / f"{bid}_5day_{step}.zip"
    if _download_zip(f"{_GIS_ARCHIVE_BASE}{bid}_5day_{step}.zip", five):
        layers.update(_extract_gis_layers_from_zip(five, _FIVE_DAY_LAYER_KINDS, sid, gis_dir))
    fcst = gis_dir / f"{bid}_fcst_{step}.zip"
    if _download_zip(f"{_GIS_ARCHIVE_BASE}{bid}_fcst_{step}.zip", fcst):
        layers.update(_extract_gis_layers_from_zip(fcst, _FORECAST_WIND_RADII_LAYER_KINDS, sid, gis_dir))

    # Storm Surge Watch/Warning + Peak Storm Surge are separate KML products (only
    # issued for U.S.-coast-threatening advisories), not part of the 5-day zip.
    # For intermediate advisories (10A, 11A), try intermediate first, then fall back to parent.
    ssww = _fetch_url_text(f"https://www.nhc.noaa.gov/gis/wsurge/forecasts/{sid}_WatchWarningSS_{step}adv.kml")
    peak = _fetch_url_text(f"https://www.nhc.noaa.gov/gis/peakSurge/{sid}_PeakStormSurge_{step}adv.kml")

    # If intermediate advisory doesn't have surge files, use parent full advisory's
    if not ssww and not peak and step.endswith('A'):
        parent_step = step[:-1]
        ssww = _fetch_url_text(f"https://www.nhc.noaa.gov/gis/wsurge/forecasts/{sid}_WatchWarningSS_{parent_step}adv.kml")
        peak = _fetch_url_text(f"https://www.nhc.noaa.gov/gis/peakSurge/{sid}_PeakStormSurge_{parent_step}adv.kml")

    if ssww:
        coll = _parse_storm_surge_kml(ssww)
        if coll and coll.get("features"):
            layers["storm_surge"] = {"cache_path": "", "feature_count": len(coll["features"]), "source_path": "NHC wsurge", "geojson": coll}
    if peak:
        coll = _parse_peak_surge_kml(peak)
        if coll and coll.get("features"):
            layers["peak_surge"] = {"cache_path": "", "feature_count": len(coll["features"]), "source_path": "NHC peakSurge", "geojson": coll}

    # Initial Wind Extent (cone outline) — try intermediate first, fall back to parent
    iwe = _fetch_url_text(f"https://www.nhc.noaa.gov/gis/forecast/{sid}_initialwindextent_{step}adv.kml")
    if not iwe and step.endswith('A'):
        parent_step = step[:-1]
        iwe = _fetch_url_text(f"https://www.nhc.noaa.gov/gis/forecast/{sid}_initialwindextent_{parent_step}adv.kml")
    if iwe:
        coll = _parse_initial_wind_extent_kml(iwe)
        if coll and coll.get("features"):
            layers["initial_wind_extent"] = {"cache_path": "", "feature_count": len(coll["features"]), "source_path": "NHC initialwindextent", "geojson": coll}

    return {
        "status": "success",
        "stormId": sid,
        "basin": sid[:2],
        "basinName": _BASIN_NAMES.get(sid[:2], sid[:2]),
        "advisoryStep": step,
        "advisoryNum": num,
        "intermediate": bool(suffix),
        "issued": issued,
        "issued_at": parse_archive_issued_iso(issued),
        "advisory": advisory,
        "track": track,
        "products": products,
        "graphics": _archive_graphics(sid, year, int(num)),
        "gis_layers": layers,
        "source": "NHC Archive",
        "updated": _utc_now_iso(),
        "cached_at": _utc_now_iso(),
    }


def get_advisory_payload(atcf_id: str, step: str, force: bool = False) -> dict[str, Any] | None:
    """Return a cached per-advisory payload, building + caching it on first request."""
    import json

    sid = atcf_id.upper()
    step = step.upper()
    if not re.fullmatch(r"\d+[A-Z]?", step):
        return None
    cache = STORMS_DIR / sid / "advisories" / f"{step}.json"
    with _ADVISORY_CACHE_LOCKS_GUARD:
        advisory_lock = _ADVISORY_CACHE_LOCKS.setdefault(
            (sid, step), threading.Lock()
        )
    with advisory_lock:
        if cache.is_file() and not force:
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        payload = build_advisory_payload(sid, step)
        if payload is None:
            return None
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix(cache.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        temporary.replace(cache)
        return payload


# ── Worker entry ────────────────────────────────────────────────────────────
def run_archive_worker(
    force: bool = False,
    atlantic_file: Path | None = None,
    nepac_file: Path | None = None,
) -> None:
    """Download HURDAT2 (AL + EP/CP), build the catalog, emit per-storm payloads."""
    import json

    start = time.time()
    sources = download_hurdat2(force=force, atlantic_file=atlantic_file, nepac_file=nepac_file)

    catalog: dict[str, dict[str, list[dict]]] = {}
    storm_count = 0
    for path in sources.values():
        for storm in parse_hurdat2(path):
            year = str(storm["year"])
            catalog.setdefault(storm["basin"], {}).setdefault(year, []).append(
                _catalog_entry(storm)
            )

            storm_dir = STORMS_DIR / storm["atcf_id"]
            storm_dir.mkdir(parents=True, exist_ok=True)
            payload = build_storm_payload(storm)
            (storm_dir / "storm.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            storm_count += 1

    # Fold in the in-progress season from NHC's live ATCF b-decks (HURDAT2 lags a
    # year). Isolated so a network hiccup never breaks the historical archive.
    current_year = datetime.now(timezone.utc).year
    try:
        for storm in parse_current_season_btk(current_year):
            year = str(storm["year"])
            catalog.setdefault(storm["basin"], {}).setdefault(year, []).append(
                _catalog_entry(storm)
            )
            storm_dir = STORMS_DIR / storm["atcf_id"]
            storm_dir.mkdir(parents=True, exist_ok=True)
            (storm_dir / "storm.json").write_text(
                json.dumps(
                    build_storm_payload(storm, source=_ATCF_BTK_SOURCE),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            storm_count += 1
    except Exception as exc:  # current-season fetch is best-effort
        print(f"[tropical_archive_worker] current-season b-decks skipped: {exc}")

    # Stable basin order (AL, EP, CP) for a predictable dropdown.
    ordered = {b: catalog[b] for b in ("AL", "EP", "CP") if b in catalog}
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    catalog_payload = {
        "basins": ordered,
        "basinNames": _BASIN_NAMES,
        "updated": _utc_now_iso(),
        "source": "HURDAT2",
        "storm_count": storm_count,
    }
    CATALOG_FILE.write_text(
        json.dumps(catalog_payload, ensure_ascii=False), encoding="utf-8"
    )
    mark_run_complete("tropical_archive")
    seasons = sum(len(s) for s in ordered.values())
    print(
        f"[tropical_archive_worker] Complete in {time.time() - start:.2f}s "
        f"({storm_count} storms; basins {list(ordered)}; {seasons} basin-seasons)"
    )


def refresh_current_season(year: int | None = None) -> int:
    """Refresh only the in-progress season from b-decks; leave history untouched.

    Updates the current-year per-basin catalog entries and the current-season
    per-storm ``storm.json`` payloads, without re-parsing HURDAT2 or rewriting the
    thousands of historical payloads (which would wipe their lazily-cached GIS/
    advisory enrichment). No-op (returns 0) when the full catalog hasn't been
    built yet — the lazy full build handles first-time creation.
    """
    import json

    if not CATALOG_FILE.is_file():
        return 0
    target_year = year or datetime.now(timezone.utc).year

    # A discovery/fetch failure must not wipe valid current-season data, so collect
    # the whole season up front and abort on error rather than mutating the catalog.
    try:
        storms = list(parse_current_season_btk(target_year))
    except Exception as exc:
        print(f"[tropical_archive_worker] current-season refresh skipped: {exc}")
        return 0

    try:
        catalog_payload = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[tropical_archive_worker] catalog unreadable, refresh skipped: {exc}")
        return 0
    basins = catalog_payload.get("basins") or {}

    fresh_year: dict[str, list[dict]] = {}
    for storm in storms:
        fresh_year.setdefault(storm["basin"], []).append(_catalog_entry(storm))
        storm_dir = STORMS_DIR / storm["atcf_id"]
        storm_dir.mkdir(parents=True, exist_ok=True)
        (storm_dir / "storm.json").write_text(
            json.dumps(build_storm_payload(storm, source=_ATCF_BTK_SOURCE), ensure_ascii=False),
            encoding="utf-8",
        )

    year_key = str(target_year)
    for basin in ("AL", "EP", "CP"):
        year_map = basins.setdefault(basin, {})
        if basin in fresh_year:
            year_map[year_key] = fresh_year[basin]
        else:
            year_map.pop(year_key, None)  # season has no storms (yet) in this basin
    catalog_payload["basins"] = {b: basins[b] for b in ("AL", "EP", "CP") if basins.get(b)}
    catalog_payload["updated"] = _utc_now_iso()
    CATALOG_FILE.write_text(json.dumps(catalog_payload, ensure_ascii=False), encoding="utf-8")
    mark_run_complete("tropical_archive")
    print(f"[tropical_archive_worker] current-season refresh: {len(storms)} storm(s) for {year_key}")
    return len(storms)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the tropical archive (HURDAT2) cache.")
    parser.add_argument("--force", action="store_true", help="Re-download the source files.")
    parser.add_argument(
        "--atlantic-file",
        type=Path,
        help="Use a local HURDAT2 Atlantic text file instead of fetching it.",
    )
    parser.add_argument(
        "--nepac-file",
        type=Path,
        help="Use a local HURDAT2 NE/Central Pacific text file instead of fetching it.",
    )
    parser.add_argument(
        "--refresh-current",
        action="store_true",
        help="Refresh only the in-progress season from ATCF b-decks (skips the full "
        "HURDAT2 rebuild; leaves historical payloads and their enrichment intact).",
    )
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to logs/scheduled/tropical_archive.log.",
    )
    args = parser.parse_args()
    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("tropical_archive")
    if args.refresh_current:
        refresh_current_season()
    else:
        run_archive_worker(
            force=args.force, atlantic_file=args.atlantic_file, nepac_file=args.nepac_file
        )
