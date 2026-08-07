from __future__ import annotations

import asyncio
from datetime import date, timedelta
import json

from fastapi import HTTPException
import pytest

import services.drought_service as drought_service


class _Response:
    status = 200

    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self._body


def test_drought_dates_are_fifteen_weekly_releases_newest_first(monkeypatch):
    latest = date(2026, 8, 4)
    monkeypatch.setattr(drought_service, "_latest_usdm_date", lambda: latest)

    payload = drought_service.get_drought_dates()

    expected = [
        (latest - timedelta(weeks=offset)).isoformat()
        for offset in range(15)
    ]
    assert payload == {"dates": expected, "latest": "2026-08-04"}
    assert all(date.fromisoformat(value).weekday() == 1 for value in expected)


def test_latest_drought_geojson_uses_release_date_and_caches_valid_payload(
    tmp_path,
    monkeypatch,
):
    raw = b'{"type":"FeatureCollection","features":[]}'
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return _Response(raw)

    monkeypatch.setattr(drought_service, "CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        drought_service,
        "_latest_usdm_date",
        lambda: date(2026, 8, 4),
    )
    monkeypatch.setattr(drought_service, "urlopen", fake_urlopen)

    first = asyncio.run(drought_service.get_drought_geojson("latest"))
    second = asyncio.run(drought_service.get_drought_geojson("2026-08-04"))

    assert first.body == raw
    assert second.body == raw
    assert first.media_type == "application/json"
    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.full_url.endswith("/usdm_20260804.json")
    assert request.get_header("User-agent") == "NCHurricane-Dashboard/1.0"
    assert timeout == 30
    assert (tmp_path / "drought" / "usdm_20260804.json").read_bytes() == raw


@pytest.mark.parametrize(
    "raw",
    [
        b"not-json",
        b"[]",
        b'{"type":"Other","features":[]}',
        b'{"type":"FeatureCollection","features":{}}',
    ],
)
def test_drought_geojson_rejects_malformed_provider_payload(
    raw,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(drought_service, "CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        drought_service,
        "urlopen",
        lambda *_args, **_kwargs: _Response(raw),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(drought_service.get_drought_geojson("2026-08-04"))

    assert exc_info.value.status_code == 503
    assert "invalid" in str(exc_info.value.detail).lower()
    assert not (tmp_path / "drought" / "usdm_20260804.json").exists()


def test_drought_geojson_replaces_invalid_cached_payload(
    tmp_path,
    monkeypatch,
):
    cache_file = tmp_path / "drought" / "usdm_20260804.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text(
        '{"type":"FeatureCollection","features":{}}',
        encoding="utf-8",
    )
    valid = b'{"type":"FeatureCollection","features":[]}'
    calls = []

    def fake_urlopen(*_args, **_kwargs):
        calls.append(True)
        return _Response(valid)

    monkeypatch.setattr(drought_service, "CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(drought_service, "urlopen", fake_urlopen)

    response = asyncio.run(drought_service.get_drought_geojson("2026-08-04"))

    assert response.body == valid
    assert calls == [True]
    assert cache_file.read_bytes() == valid


def test_drought_state_stats_normalize_provider_rows_and_cache_result(
    tmp_path,
    monkeypatch,
):
    responses = iter(
        [
            _Response(
                json.dumps(
                    [
                        {
                            "d0": "30",
                            "d1": 20,
                            "d2": "10.5",
                            "d3": 5,
                            "d4": "1",
                        }
                    ]
                ).encode()
            ),
            _Response(b'[{"dsci":"125"}]'),
        ]
    )
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        return next(responses)

    monkeypatch.setattr(drought_service, "CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(drought_service, "urlopen", fake_urlopen)

    first = asyncio.run(
        drought_service.get_drought_state_stats("2026-08-04", " nc ")
    )
    second = asyncio.run(
        drought_service.get_drought_state_stats("2026-08-04", "NC")
    )

    assert first == second
    assert first == {
        "state": "NC",
        "date": "2026-08-04",
        "provider": "USDM/NDMC",
        "cumulative": {
            "D0-D4": 30.0,
            "D1-D4": 20.0,
            "D2-D4": 10.5,
            "D3-D4": 5.0,
            "D4": 1.0,
        },
        "individual": {
            "D0": 10.0,
            "D1": 9.5,
            "D2": 5.5,
            "D3": 4.0,
            "D4": 1.0,
        },
        "dsci": 125.0,
    }
    assert len(calls) == 2
    assert "aoi=37" in calls[0][0]
    assert "startdate=8%2F4%2F2026" in calls[0][0]
    assert calls[0][1] == 30
    cache_file = (
        tmp_path
        / "drought"
        / "stats"
        / "usdm_state_stats_NC_20260804.json"
    )
    assert json.loads(cache_file.read_text(encoding="utf-8")) == first


def test_drought_state_stats_accept_legitimate_empty_provider_rows(
    tmp_path,
    monkeypatch,
):
    responses = iter([_Response(b"[]"), _Response(b"[]")])
    monkeypatch.setattr(drought_service, "CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        drought_service,
        "urlopen",
        lambda *_args, **_kwargs: next(responses),
    )

    payload = asyncio.run(
        drought_service.get_drought_state_stats("2026-08-04", "NC")
    )

    assert payload["cumulative"] == {
        "D0-D4": 0.0,
        "D1-D4": 0.0,
        "D2-D4": 0.0,
        "D3-D4": 0.0,
        "D4": 0.0,
    }
    assert payload["individual"] == {
        "D0": 0.0,
        "D1": 0.0,
        "D2": 0.0,
        "D3": 0.0,
        "D4": 0.0,
    }
    assert payload["dsci"] == 0.0


@pytest.mark.parametrize(
    ("area_payload", "dsci_payload"),
    [
        ({}, [{"dsci": 1}]),
        ([[]], [{"dsci": 1}]),
        ([{"d0": "invalid"}], [{"dsci": 1}]),
        ([{"d0": 1}], {}),
        ([{"d0": 1}], [["invalid"]]),
        ([{"d0": 1}], [{"dsci": "NaN"}]),
    ],
)
def test_drought_state_stats_reject_malformed_provider_payloads(
    area_payload,
    dsci_payload,
    tmp_path,
    monkeypatch,
):
    responses = iter(
        [
            _Response(json.dumps(area_payload).encode()),
            _Response(json.dumps(dsci_payload).encode()),
        ]
    )
    monkeypatch.setattr(drought_service, "CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        drought_service,
        "urlopen",
        lambda *_args, **_kwargs: next(responses),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            drought_service.get_drought_state_stats("2026-08-04", "NC")
        )

    assert exc_info.value.status_code == 503
    assert "invalid" in str(exc_info.value.detail).lower()
    assert not (
        tmp_path
        / "drought"
        / "stats"
        / "usdm_state_stats_NC_20260804.json"
    ).exists()


def test_drought_state_stats_replaces_invalid_cached_payload(
    tmp_path,
    monkeypatch,
):
    cache_file = (
        tmp_path
        / "drought"
        / "stats"
        / "usdm_state_stats_NC_20260804.json"
    )
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text("[]", encoding="utf-8")
    responses = iter([_Response(b"[]"), _Response(b"[]")])
    calls = []

    def fake_urlopen(*_args, **_kwargs):
        calls.append(True)
        return next(responses)

    monkeypatch.setattr(drought_service, "CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(drought_service, "urlopen", fake_urlopen)

    payload = asyncio.run(
        drought_service.get_drought_state_stats("2026-08-04", "NC")
    )

    assert payload["state"] == "NC"
    assert calls == [True, True]
    assert isinstance(json.loads(cache_file.read_text(encoding="utf-8")), dict)


@pytest.mark.parametrize(
    ("date_value", "state", "status_code"),
    [
        ("20260804", "NC", 400),
        ("2026-08-04", "North Carolina", 400),
        ("2026-08-04", "ZZ", 404),
    ],
)
def test_drought_state_stats_validate_request_values(
    date_value,
    state,
    status_code,
):
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            drought_service.get_drought_state_stats(date_value, state)
        )

    assert exc_info.value.status_code == status_code
