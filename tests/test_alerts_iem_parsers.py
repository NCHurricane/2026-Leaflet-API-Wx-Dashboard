from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace

import cartopy.io.shapereader as shpreader
import pytest
from shapely.geometry import MultiPolygon, Polygon, shape

import alerts.alerts_iem_utils as iem
import alerts.alerts_utils as alerts_utils


def _zip_response() -> SimpleNamespace:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("alerts.shp", b"placeholder")

    return SimpleNamespace(
        content=payload.getvalue(),
        raise_for_status=lambda: None,
    )


class _Reader:
    def __init__(self, records) -> None:
        self._records = records

    def records(self):
        return iter(self._records)


def _record(geometry, **attrs):
    defaults = {
        "ISSUED": "200001010000",
        "EXPIRED": "209901010000",
        "PHENOM": "TO",
        "SIG": "W",
        "WFO": "RAH",
        "GTYPE": "P",
        "NWS_UGC": "NCZ001",
        "STATUS": "NEW",
    }
    defaults.update(attrs)
    return SimpleNamespace(attributes=defaults, geometry=geometry)


def test_iem_timestamp_parser_returns_utc_and_rejects_malformed_values():
    assert iem._iem_ts_to_dt("202608071245") == datetime(
        2026, 8, 7, 12, 45, tzinfo=timezone.utc
    )
    assert iem._iem_ts_to_dt("") is None
    assert iem._iem_ts_to_dt("20260807") is None
    assert iem._iem_ts_to_dt("202613071245") is None


def test_iem_event_mapping_prefers_nonblank_event_then_uses_codes():
    assert (
        iem._event_name_from_attrs(
            {"EVENT": "  Provider Event  ", "PHENOM": "TO", "SIG": "W"}
        )
        == "Provider Event"
    )
    assert (
        iem._event_name_from_attrs(
            {"EVENT": "   ", "PHENOM": "TO", "SIG": "W"}
        )
        == "Tornado Warning"
    )
    assert (
        iem._event_name_from_attrs({"PHENOM": "UP", "SIG": "W"})
        == "Heavy Freezing Spray Warning"
    )
    assert iem._event_name_from_attrs({"PHENOM": "??", "SIG": "W"}) is None


def test_iem_state_bbox_filter_keeps_intersections_and_rejects_outside():
    inside_nc = Polygon([(-80, 35), (-79, 35), (-79, 36), (-80, 35)])
    outside_nc = Polygon([(-110, 35), (-109, 35), (-109, 36), (-110, 35)])

    assert iem._state_bbox_filter(inside_nc, "nc") is True
    assert iem._state_bbox_filter(outside_nc, "NC") is False
    assert iem._state_bbox_filter(outside_nc, None) is True
    assert iem._state_bbox_filter(outside_nc, "XX") is True


def test_iem_antimeridian_split_shifts_eastern_parts_near_alaska():
    eastern = Polygon([(170, 55), (171, 55), (171, 56), (170, 55)])
    western = Polygon([(-179, 55), (-178, 55), (-178, 56), (-179, 55)])

    result = iem._split_antimeridian(MultiPolygon([eastern, western]))

    assert result is not None
    assert result.is_valid
    assert result.bounds[0] == -190
    assert result.bounds[2] == -178


def test_fetch_active_alerts_iem_normalizes_and_repairs_provider_record(
    monkeypatch,
):
    bowtie = Polygon(
        [(-81, 35), (-79, 37), (-81, 37), (-79, 35), (-81, 35)]
    )
    records = [_record(bowtie)]
    monkeypatch.setattr(iem.requests, "get", lambda *args, **kwargs: _zip_response())
    monkeypatch.setattr(shpreader, "Reader", lambda path: _Reader(records))

    features = iem.fetch_active_alerts_iem(state="NC")

    assert len(features) == 1
    feature = features[0]
    assert feature["type"] == "Feature"
    assert shape(feature["geometry"]).is_valid
    assert feature["properties"] == {
        "event": "Tornado Warning",
        "headline": "Tornado Warning",
        "phenomena": "TO",
        "significance": "W",
        "isMarine": False,
        "senderCode": "RAH",
        "gtype": "P",
        "nws_ugc": "NCZ001",
        "status": "NEW",
        "parameters": {
            "WFOidentifier": "RAH",
            "AWIPSidentifier": "RAH",
            "NWSidentifier": "RAH",
        },
    }


def test_fetch_active_alerts_iem_national_retry_preserves_state_filter(
    monkeypatch,
):
    inside_nc = Polygon([(-80, 35), (-79, 35), (-79, 36), (-80, 35)])
    outside_nc = Polygon([(-110, 35), (-109, 35), (-109, 36), (-110, 35)])
    records = [_record(inside_nc), _record(outside_nc, NWS_UGC="COZ001")]
    urls = []

    def get(url, **kwargs):
        urls.append(url)
        if len(urls) == 1:
            raise OSError("state-filtered request failed")
        return _zip_response()

    monkeypatch.setattr(iem.requests, "get", get)
    monkeypatch.setattr(shpreader, "Reader", lambda path: _Reader(records))

    features = iem.fetch_active_alerts_iem(state="NC")

    assert len(features) == 1
    assert "states=NC" in urls[0]
    assert "states=" not in urls[1]
    assert features[0]["properties"]["nws_ugc"] == "NCZ001"


def test_fetch_active_alerts_iem_filters_inactive_and_unusable_records(
    monkeypatch,
):
    inside_nc = Polygon([(-80, 35), (-79, 35), (-79, 36), (-80, 35)])
    records = [
        _record(inside_nc, EXPIRED="200101010000"),
        _record(inside_nc, ISSUED="bad"),
        _record(inside_nc, EVENT="", PHENOM="??"),
        _record(None),
    ]
    monkeypatch.setattr(iem.requests, "get", lambda *args, **kwargs: _zip_response())
    monkeypatch.setattr(shpreader, "Reader", lambda path: _Reader(records))

    assert iem.fetch_active_alerts_iem(state="NC") == []


def test_direct_iem_empty_result_is_valid_outside_strict_refresh(monkeypatch):
    monkeypatch.setattr(iem, "fetch_active_alerts_iem", lambda state: [])

    assert alerts_utils.fetch_active_alerts_with_source(source="iem") == (
        [],
        "IEM",
    )


def test_direct_iem_empty_result_retains_strict_failure_cause(monkeypatch):
    monkeypatch.setattr(iem, "fetch_active_alerts_iem", lambda state: [])

    with pytest.raises(RuntimeError, match="IEM alerts download failed") as exc_info:
        alerts_utils.fetch_active_alerts_with_source(source="iem", strict=True)

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert str(exc_info.value.__cause__) == "IEM alerts download returned no features"


def test_direct_iem_provider_failure_is_suppressed_for_ordinary_reads(
    monkeypatch,
):
    def fail(_state):
        raise OSError("provider unavailable")

    monkeypatch.setattr(iem, "fetch_active_alerts_iem", fail)

    assert alerts_utils.fetch_active_alerts_with_source(source="iem") == (
        [],
        "IEM",
    )
