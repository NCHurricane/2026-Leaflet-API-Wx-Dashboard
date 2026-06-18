"""SPC cache and active product helpers."""

from datetime import datetime, timedelta, timezone
import json
import os

from fastapi import HTTPException

from app_core.paths import CACHE_ROOT


def _latest_item_issue_iso(items: list[dict]) -> str | None:
    issue_times = []
    for item in items:
        if not isinstance(item, dict):
            continue
        issue_time = item.get("issue_utc")
        if not isinstance(issue_time, datetime):
            continue
        if issue_time.tzinfo is None:
            issue_time = issue_time.replace(tzinfo=timezone.utc)
        issue_times.append(issue_time)
    if not issue_times:
        return None
    return max(issue_times).astimezone(timezone.utc).isoformat()


def _latest_report_iso(
    rows: list[dict],
    report_date_utc: datetime | None,
) -> str | None:
    if report_date_utc is None:
        return None
    timestamps = []
    report_date = report_date_utc.astimezone(timezone.utc).date()
    for row in rows:
        raw_time = str(row.get("time") or "").strip().replace(":", "")
        if not raw_time.isdigit() or len(raw_time) not in {3, 4}:
            continue
        raw_time = raw_time.zfill(4)
        hour = int(raw_time[:2])
        minute = int(raw_time[2:])
        if hour > 23 or minute > 59:
            continue
        timestamps.append(
            datetime(
                report_date.year,
                report_date.month,
                report_date.day,
                hour,
                minute,
                tzinfo=timezone.utc,
            )
        )
    if not timestamps:
        return None
    return max(timestamps).isoformat()


def get_spc_outlook(day: int = 1, hazard: str = "cat") -> dict:
    """Return SPC outlook GeoJSON from worker cache."""
    hazard_lower = hazard.strip().lower()
    is_fire = hazard_lower in {
        "windrh",
        "dryt",
        "windrhcat",
        "windrhprob",
        "drytcat",
        "drytprob",
    }
    cache_name = f"fire_{day}_{hazard_lower}" if is_fire else f"{day}_{hazard_lower}"
    cache_file = os.path.join(CACHE_ROOT, "spc", f"{cache_name}.geojson")

    if not os.path.exists(cache_file):
        try:
            from workers.spc_worker import run_spc_worker

            run_spc_worker()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"SPC cache not yet available: {exc}",
            )

    if not os.path.exists(cache_file):
        return {
            "type": "FeatureCollection",
            "features": [],
            "_source": "SPC",
            "_updated": None,
            "count": 0,
        }

    try:
        with open(cache_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    data["count"] = len(data.get("features") or [])
    if is_fire:
        try:
            from spc.spc_utils import fetch_fire_outlook_modal_details

            data["_outlook_detail"] = fetch_fire_outlook_modal_details(day, hazard)
        except Exception:
            data["_outlook_detail"] = {
                "text": "",
                "impacts": [],
                "source_url": "",
            }
    else:
        try:
            from spc.spc_utils import fetch_outlook_modal_details

            data["_outlook_detail"] = fetch_outlook_modal_details(day, hazard)
        except Exception:
            data["_outlook_detail"] = {
                "text": "",
                "impacts": [],
                "source_url": "",
            }
    return data


def get_spc_reports(
    day: str = "today",
    report_mode: str = "filtered",
    report_type: str = "all",
) -> dict:
    """Return SPC storm reports as GeoJSON points for today/yesterday."""
    from spc.spc_utils import fetch_reports_rows

    day_key = (day or "today").strip().lower()
    now_utc = datetime.now(timezone.utc)
    report_date_utc = None
    if day_key == "today":
        report_date_utc = now_utc
    elif day_key == "yesterday":
        report_date_utc = now_utc - timedelta(days=1)
    elif day_key:
        try:
            parsed = datetime.strptime(day_key, "%Y-%m-%d")
            report_date_utc = parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="day must be 'today', 'yesterday', or YYYY-MM-DD",
            )

    try:
        rows, source = fetch_reports_rows(
            report_date_utc=report_date_utc,
            report_mode=report_mode,
            report_type=report_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"SPC reports unavailable: {exc}")

    features = []
    for idx, row in enumerate(rows or []):
        lat = row.get("lat")
        lon = row.get("lon")
        if lat is None or lon is None:
            continue
        features.append(
            {
                "type": "Feature",
                "id": f"spc-report-{idx}",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "event": row.get("event") or "Storm Report",
                    "time": row.get("time") or "",
                    "magnitude": row.get("magnitude") or "",
                    "location": row.get("location") or "",
                    "county": row.get("county") or "",
                    "state": row.get("state") or "",
                    "remarks": row.get("remarks") or "",
                    "report_day": day_key,
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "count": len(features),
        "_source": source,
        "_updated": _latest_report_iso(rows or [], report_date_utc),
        "report_day": day_key,
        "report_mode": (report_mode or "filtered").strip().lower(),
        "report_type": (report_type or "all").strip().lower(),
    }


def get_spc_active(
    product: str = "watches",
    watch_mode: str = "polygon",
    watch_types: str = "all",
) -> dict:
    """Return active SPC Watches/MDs as GeoJSON with rich popup properties."""
    from lib.geo_utils import CensusCounties
    from spc.spc_utils import fetch_active_md_items, fetch_active_watch_items

    product_key = (product or "watches").strip().lower()
    if product_key not in {"watches", "mds", "md"}:
        raise HTTPException(
            status_code=400,
            detail="product must be one of: watches, mds",
        )

    if product_key in {"md", "mds"}:
        try:
            items, source = fetch_active_md_items()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"SPC MDs unavailable: {exc}")

        features = []
        included_items = []
        for md in items or []:
            polygon = md.get("polygon") or []
            if len(polygon) < 3:
                continue
            included_items.append(md)

            issue_iso = md.get("issue_utc")
            expire_iso = md.get("expire_utc")
            issue_iso = issue_iso.isoformat() if issue_iso else ""
            expire_iso = expire_iso.isoformat() if expire_iso else ""

            features.append(
                {
                    "type": "Feature",
                    "id": f"spc-md-{md.get('id')}",
                    "geometry": {"type": "Polygon", "coordinates": [polygon]},
                    "properties": {
                        "id": str(md.get("id") or ""),
                        "event": md.get("title")
                        or md.get("label")
                        or "Mesoscale Discussion",
                        "headline": md.get("label")
                        or md.get("title")
                        or "Mesoscale Discussion",
                        "short_label": md.get("short_label") or "",
                        "description": md.get("full_text") or "",
                        "sent": issue_iso,
                        "expires": expire_iso,
                        "source_url": md.get("detail_url") or "",
                        "severity": "Severe",
                    },
                }
            )

        return {
            "type": "FeatureCollection",
            "features": features,
            "count": len(features),
            "_source": source,
            "_updated": _latest_item_issue_iso(included_items),
            "product": "mds",
        }

    watch_mode_key = (watch_mode or "polygon").strip().lower()
    if watch_mode_key not in {"polygon", "counties"}:
        raise HTTPException(
            status_code=400, detail="watch_mode must be polygon or counties"
        )

    watch_type_tokens = {
        token.strip().lower()
        for token in str(watch_types or "all").split(",")
        if token.strip()
    }
    if not watch_type_tokens:
        watch_type_tokens = {"all"}

    show_all = "all" in watch_type_tokens
    include_tor = (
        show_all or "tor" in watch_type_tokens or "tornado" in watch_type_tokens
    )
    include_svr = (
        show_all or "svr" in watch_type_tokens or "severe" in watch_type_tokens
    )

    if watch_mode_key == "counties":
        CensusCounties.load()

    try:
        items, source = fetch_active_watch_items(
            with_counties=(watch_mode_key == "counties")
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"SPC watches unavailable: {exc}")

    county_geoms = {}
    if watch_mode_key == "counties":
        county_geoms = getattr(CensusCounties, "_fips_map", {}) or {}

    features = []
    included_items = []
    for watch in items or []:
        watch_type = str(watch.get("type") or watch.get("title") or "Watch")
        watch_type_lc = watch_type.lower()
        is_tor = "tornado" in watch_type_lc
        is_svr = "severe thunderstorm" in watch_type_lc
        if (is_tor and not include_tor) or (is_svr and not include_svr):
            continue
        included_items.append(watch)

        issue_iso = watch.get("issue_utc")
        expire_iso = watch.get("expire_utc")
        issue_iso = issue_iso.isoformat() if issue_iso else ""
        expire_iso = expire_iso.isoformat() if expire_iso else ""

        base_props = {
            "id": str(watch.get("id") or ""),
            "watch_number": str(watch.get("id") or ""),
            "event": watch_type,
            "headline": watch.get("label") or watch.get("title") or watch_type,
            "short_label": watch.get("short_label") or "",
            "description": watch.get("full_text") or "",
            "sent": issue_iso,
            "expires": expire_iso,
            "source_url": watch.get("detail_url") or "",
            "watch_type": watch_type,
            "watch_mode": watch_mode_key,
            "county_fips": watch.get("county_fips") or [],
            "probabilities": watch.get("probabilities") or {},
            "severity": "Severe",
        }

        if watch_mode_key == "counties":
            county_fips = watch.get("county_fips") or []
            county_count = 0
            for fips in county_fips:
                geom = county_geoms.get(fips)
                if geom is None:
                    continue
                geo = getattr(geom, "__geo_interface__", None)
                if not geo:
                    continue
                county_count += 1
                props = dict(base_props)
                props["county_fips_single"] = fips
                features.append(
                    {
                        "type": "Feature",
                        "id": f"spc-watch-{watch.get('id')}-county-{fips}",
                        "geometry": geo,
                        "properties": props,
                    }
                )

            if county_count == 0:
                polygon = watch.get("polygon") or []
                if len(polygon) >= 3:
                    features.append(
                        {
                            "type": "Feature",
                            "id": f"spc-watch-{watch.get('id')}",
                            "geometry": {"type": "Polygon", "coordinates": [polygon]},
                            "properties": base_props,
                        }
                    )
            continue

        polygon = watch.get("polygon") or []
        if len(polygon) < 3:
            continue
        features.append(
            {
                "type": "Feature",
                "id": f"spc-watch-{watch.get('id')}",
                "geometry": {"type": "Polygon", "coordinates": [polygon]},
                "properties": base_props,
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "count": len(features),
        "_source": source,
        "_updated": _latest_item_issue_iso(included_items),
        "product": "watches",
        "watch_mode": watch_mode_key,
    }
