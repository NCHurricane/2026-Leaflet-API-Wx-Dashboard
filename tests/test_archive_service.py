import io
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace

import cartopy.io.shapereader as shpreader
from fastapi import HTTPException
import pandas as pd
import pytest
from shapely.geometry import Polygon

import app_core.upstream_ledger as upstream_ledger
import services.archive_service as archive_service
from services.archive_service import _parse_archive_dt


def test_archive_datetime_accepts_browser_iso_timestamp():
    assert _parse_archive_dt("2026-08-05T20:00:00.000Z") == datetime(
        2026, 8, 5, 20, tzinfo=timezone.utc
    )


def test_archive_datetime_normalizes_offsets_to_utc():
    assert _parse_archive_dt("2026-08-05T16:00:00-04:00") == datetime(
        2026, 8, 5, 20, tzinfo=timezone.utc
    )


def _surface_archive_frame(source: str, temperature: float) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "station_id": ["KAVL"],
            "name": ["Asheville Regional Airport"],
            "network": ["ASOS"],
            "latitude": [35.44],
            "longitude": [-82.54],
            "air_temperature": [temperature],
        }
    )
    frame.attrs["surface_source"] = source
    return frame


def test_surface_archive_reports_per_frame_and_mixed_actual_provenance(
    tmp_path, monkeypatch
):
    frames = [
        _surface_archive_frame("awc", 70.0),
        _surface_archive_frame("iem", 71.0),
    ]
    monkeypatch.setattr(archive_service, "_ARCHIVE_JSON_DIR", str(tmp_path))
    monkeypatch.setattr(
        archive_service,
        "fetch_surface_archive_frames",
        lambda *_args, **_kwargs: frames,
    )

    result = archive_service.get_archive_surface(
        region="NC",
        product="temperature",
        date_from="2026-08-07T12:00:00Z",
        date_to="2026-08-07T12:15:00Z",
        max_frames=2,
        source="iem",
    )

    assert result["source"] == "mixed"
    assert [frame["source"] for frame in result["frames"]] == ["awc", "iem"]
    assert [frame["stations"][0]["value"] for frame in result["frames"]] == [
        70.0,
        71.0,
    ]


def test_surface_archive_rejects_unsupported_source():
    with pytest.raises(HTTPException) as exc_info:
        archive_service.get_archive_surface(
            date_from="2026-08-07T12:00:00Z",
            date_to="2026-08-07T12:15:00Z",
            source="nws",
        )

    assert exc_info.value.status_code == 400
    assert "source must be 'auto' or 'iem'" in exc_info.value.detail


def test_surface_archive_rejects_unsupported_historical_world():
    with pytest.raises(HTTPException) as exc_info:
        archive_service.get_archive_surface(
            region="WORLD",
            date_from="2026-08-07T12:00:00Z",
            date_to="2026-08-07T12:15:00Z",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Historical WORLD surface archive is not supported."


def _iem_zip_response() -> SimpleNamespace:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("alerts.shp", b"placeholder")
    return SimpleNamespace(
        content=payload.getvalue(),
        raise_for_status=lambda: None,
    )


class _IemReader:
    def __init__(self, records) -> None:
        self._records = records

    def records(self):
        return iter(self._records)


def _iem_record(event: str, issued: str, expired: str, geometry):
    return SimpleNamespace(
        attributes={
            "EVENT": event,
            "ISSUED": issued,
            "EXPIRED": expired,
            "AREA_DESC": "fixture area",
        },
        geometry=geometry,
    )


def test_alerts_archive_rejects_reversed_range_before_fetch(monkeypatch):
    def unexpected_fetch(*_args, **_kwargs):
        raise AssertionError("reversed range reached IEM")

    monkeypatch.setattr(
        archive_service,
        "_fetch_iem_alerts_range",
        unexpected_fetch,
    )

    with pytest.raises(HTTPException) as exc_info:
        archive_service.get_archive_alerts(
            date_from="2026-08-07T13:00:00Z",
            date_to="2026-08-07T12:00:00Z",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "date_to must be after date_from."


def test_iem_alert_archive_keeps_spanning_alerts_and_filters_to_interval(
    monkeypatch,
):
    nc_geometry = Polygon(
        [(-80, 35), (-79, 35), (-79, 36), (-80, 35)]
    )
    records = [
        _iem_record(
            "Spanning Warning",
            "202608060900",
            "202608071230",
            nc_geometry,
        ),
        _iem_record(
            "Within Warning",
            "202608071205",
            "202608071245",
            nc_geometry,
        ),
        _iem_record(
            "Expired Warning",
            "202608070800",
            "202608071159",
            nc_geometry,
        ),
        _iem_record(
            "Future Warning",
            "202608071301",
            "202608071400",
            nc_geometry,
        ),
        _iem_record("Malformed Warning", "bad", "also-bad", nc_geometry),
    ]
    urls = []

    def get(url, **_kwargs):
        urls.append(url)
        return _iem_zip_response()

    monkeypatch.setattr(upstream_ledger.requests, "get", get)
    monkeypatch.setattr(shpreader, "Reader", lambda path: _IemReader(records))

    features = archive_service._fetch_iem_alerts_range(
        datetime(2026, 8, 7, 12, tzinfo=timezone.utc),
        datetime(2026, 8, 7, 13, tzinfo=timezone.utc),
        None,
    )

    assert [feature["properties"]["event"] for feature in features] == [
        "Spanning Warning",
        "Within Warning",
    ]
    assert "year1=2026&month1=8&day1=4&hour1=12" in urls[0]
    assert "year2=2026&month2=8&day2=7&hour2=13" in urls[0]


def test_iem_alert_archive_national_retry_preserves_requested_state(
    monkeypatch,
):
    nc_geometry = Polygon(
        [(-80, 35), (-79, 35), (-79, 36), (-80, 35)]
    )
    colorado_geometry = Polygon(
        [(-105, 39), (-104, 39), (-104, 40), (-105, 39)]
    )
    records = [
        _iem_record(
            "North Carolina Warning",
            "202608071205",
            "202608071245",
            nc_geometry,
        ),
        _iem_record(
            "Colorado Warning",
            "202608071205",
            "202608071245",
            colorado_geometry,
        ),
    ]
    urls = []

    def get(url, **_kwargs):
        urls.append(url)
        if len(urls) == 1:
            raise OSError("state-filtered request failed")
        return _iem_zip_response()

    monkeypatch.setattr(upstream_ledger.requests, "get", get)
    monkeypatch.setattr(shpreader, "Reader", lambda path: _IemReader(records))

    features = archive_service._fetch_iem_alerts_range(
        datetime(2026, 8, 7, 12, tzinfo=timezone.utc),
        datetime(2026, 8, 7, 13, tzinfo=timezone.utc),
        "NC",
    )

    assert "states=NC" in urls[0]
    assert "states=" not in urls[1]
    assert [feature["properties"]["event"] for feature in features] == [
        "North Carolina Warning"
    ]
