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


def test_archive_cache_rejects_non_object_json(tmp_path):
    cache_file = tmp_path / "archive.json"
    cache_file.write_text("[]", encoding="utf-8")

    assert archive_service._read_archive_cache(str(cache_file)) is None


@pytest.mark.parametrize(
    ("date_from", "date_to", "detail"),
    [
        ("", "2026-08-07T13:00:00Z", "date_from and date_to are required."),
        (
            "not-a-date",
            "2026-08-07T13:00:00Z",
            "Cannot parse date 'not-a-date'",
        ),
        (
            "2026-07-01T12:00:00Z",
            "2026-08-07T12:00:00Z",
            "Max alerts archive span is 30 days.",
        ),
    ],
)
def test_alerts_archive_validates_required_range_before_fetch(
    date_from,
    date_to,
    detail,
    monkeypatch,
):
    monkeypatch.setattr(
        archive_service,
        "_fetch_iem_alerts_range",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("invalid range reached provider")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        archive_service.get_archive_alerts(
            date_from=date_from,
            date_to=date_to,
        )

    assert exc_info.value.status_code == 400
    assert detail in exc_info.value.detail


def test_alerts_archive_builds_and_reuses_cached_feature_collection(
    tmp_path,
    monkeypatch,
):
    feature = {
        "type": "Feature",
        "geometry": None,
        "properties": {"event": "Fixture Warning"},
    }
    fetch_calls = []
    enrich_calls = []

    def fetch(dt_from, dt_to, state):
        fetch_calls.append((dt_from, dt_to, state))
        return [feature]

    monkeypatch.setattr(archive_service, "_ARCHIVE_JSON_DIR", str(tmp_path))
    monkeypatch.setattr(archive_service, "_fetch_iem_alerts_range", fetch)
    monkeypatch.setattr(
        archive_service,
        "enrich_alert_features_geometry",
        lambda features: enrich_calls.append(features),
    )

    first = archive_service.get_archive_alerts(
        date_from="2026-08-07T08:00:00-04:00",
        date_to="2026-08-07T09:00:00-04:00",
        state="nc",
    )
    second = archive_service.get_archive_alerts(
        date_from="2026-08-07T12:00:00Z",
        date_to="2026-08-07T13:00:00Z",
        state="NC",
    )

    assert first == second
    assert first == {
        "type": "FeatureCollection",
        "features": [feature],
        "count": 1,
        "date_from": "2026-08-07T12:00:00+00:00",
        "date_to": "2026-08-07T13:00:00+00:00",
        "_source": "iem_watchwarn",
    }
    assert len(fetch_calls) == 1
    assert fetch_calls[0][2] == "NC"
    assert enrich_calls == [[feature], [feature]]
    assert len(list(tmp_path.glob("alerts_*.json"))) == 1


def test_alerts_archive_provider_failure_is_not_empty_success(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(archive_service, "_ARCHIVE_JSON_DIR", str(tmp_path))
    monkeypatch.setattr(
        upstream_ledger.requests,
        "get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("provider offline")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        archive_service.get_archive_alerts(
            date_from="2026-08-07T12:00:00Z",
            date_to="2026-08-07T13:00:00Z",
        )

    assert exc_info.value.status_code == 502
    assert "provider offline" in exc_info.value.detail


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


@pytest.mark.parametrize(
    ("kwargs", "detail"),
    [
        (
            {
                "date_from": "2026-08-07T13:00:00Z",
                "date_to": "2026-08-07T12:00:00Z",
            },
            "date_to must be after date_from.",
        ),
        (
            {
                "date_from": "2026-07-30T12:00:00Z",
                "date_to": "2026-08-07T12:00:01Z",
            },
            "Archive range too large for surface.",
        ),
        (
            {
                "date_from": "2026-08-07T12:00:00Z",
                "date_to": "2026-08-07T12:15:00Z",
                "product": "not-a-product",
            },
            "Unknown product",
        ),
        (
            {
                "date_from": "2026-08-07T12:00:00Z",
                "date_to": "2026-08-07T12:15:00Z",
                "network": "AWOS",
            },
            "Only ASOS network is supported",
        ),
    ],
)
def test_surface_archive_validates_range_and_supported_contract(
    kwargs,
    detail,
    monkeypatch,
):
    monkeypatch.setattr(
        archive_service,
        "fetch_surface_archive_frames",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("invalid request reached provider")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        archive_service.get_archive_surface(**kwargs)

    assert exc_info.value.status_code == 400
    if isinstance(exc_info.value.detail, dict):
        assert detail in exc_info.value.detail["error"]
    else:
        assert detail in exc_info.value.detail


def test_surface_archive_builds_quarter_hour_frames_with_individual_fallback(
    tmp_path,
    monkeypatch,
):
    bulk_frame = _surface_archive_frame("awc", 70.0)
    fallback_calls = []
    bulk_calls = []

    def fetch_frames(region, frame_times, source):
        bulk_calls.append((region, frame_times, source))
        return [bulk_frame]

    def fetch_one(region, timestamp, source):
        fallback_calls.append((region, timestamp, source))
        return _surface_archive_frame("iem", 71.0)

    monkeypatch.setattr(archive_service, "_ARCHIVE_JSON_DIR", str(tmp_path))
    monkeypatch.setattr(
        archive_service,
        "fetch_surface_archive_frames",
        fetch_frames,
    )
    monkeypatch.setattr(
        archive_service,
        "fetch_surface_archive_at_time",
        fetch_one,
    )

    first = archive_service.get_archive_surface(
        region="NC",
        product="temperature",
        date_from="2026-08-07T12:00:00Z",
        date_to="2026-08-07T12:45:00Z",
        max_frames=3,
        source="auto",
    )
    second = archive_service.get_archive_surface(
        region="NC",
        product="temperature",
        date_from="2026-08-07T12:00:00Z",
        date_to="2026-08-07T12:45:00Z",
        max_frames=3,
        source="iem",
    )

    assert first == second
    assert first["frame_count"] == 3
    assert first["source"] == "mixed"
    assert [frame["timestamp"] for frame in first["frames"]] == [
        "2026-08-07T12:00:00+00:00",
        "2026-08-07T12:15:00+00:00",
        "2026-08-07T12:30:00+00:00",
    ]
    assert [frame["source"] for frame in first["frames"]] == [
        "awc",
        "iem",
        "iem",
    ]
    assert [frame["stations"][0]["value"] for frame in first["frames"]] == [
        70.0,
        71.0,
        71.0,
    ]
    assert len(bulk_calls) == 1
    assert bulk_calls[0][0] == "NC"
    assert bulk_calls[0][2] == "auto"
    assert len(fallback_calls) == 2
    assert len(list(tmp_path.glob("surface_*.json"))) == 1


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
