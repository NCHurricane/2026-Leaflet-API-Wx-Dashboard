from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

import services.water_service as water_service
import workers.water_worker as water_worker


def test_water_timestamp_helpers_accept_provider_formats_and_reject_bad_values():
    observed = datetime(2026, 8, 7, 12, 30, tzinfo=timezone.utc)

    assert water_worker._arcgis_time(observed.timestamp()) == observed.isoformat()
    assert water_worker._arcgis_time(observed.timestamp() * 1000) == observed.isoformat()
    assert water_worker._arcgis_time("not-a-time") == "not-a-time"
    assert water_worker._arcgis_time(None) == ""
    assert water_worker._ndbc_time(["2026", "08", "07", "12", "30"]) == observed.isoformat()
    assert water_worker._ndbc_time(["2026", "13", "07", "12", "30"]) == ""


def test_normalize_nwps_map_feature_handles_thresholds_and_missing_values():
    observed = datetime(2026, 8, 7, 12, 30, tzinfo=timezone.utc)
    station = water_worker._normalize_feature(
        {
            "attributes": {
                "gaugelid": " abcn7 ",
                "location": "Example River",
                "observed": "7.25",
                "units": "ft",
                "obstime": observed.timestamp() * 1000,
                "status": " Minor Flooding ",
                "action": "6.0",
                "flood": "7.0",
                "moderate": -999,
                "major": "10.0",
                "state": "NC",
                "wfo": "RAH",
                "waterbody": "Example Creek",
            },
            "geometry": {"x": -78.5, "y": 35.75},
        }
    )

    assert station is not None
    assert station["site_id"] == "ABCN7"
    assert station["lat"] == 35.75
    assert station["lon"] == -78.5
    assert station["readings"]["stage"] == {
        "value": 7.25,
        "timestamp": observed.isoformat(),
        "qualifiers": "",
        "label": "Stage",
        "units": "ft",
    }
    assert station["observed_category"] == "minor flooding"
    assert station["flood"]["categories"] == {
        "action": {"stage": 6.0, "flow": None},
        "minor": {"stage": 7.0, "flow": None},
        "major": {"stage": 10.0, "flow": None},
    }

    missing = water_worker._normalize_feature(
        {
            "properties": {
                "gaugelid": "MISS1",
                "latitude": 35,
                "longitude": -79,
                "observed": -9999,
                "status": "No Flooding",
            }
        }
    )
    assert missing is not None
    assert missing["readings"] == {}
    assert missing["status"] == "missing"
    assert missing["observed_category"] == ""


@pytest.mark.parametrize(
    "feature",
    [
        None,
        {},
        {"attributes": {"gaugelid": ""}},
        {"attributes": {"gaugelid": "NOCOORD"}},
    ],
)
def test_normalize_nwps_map_feature_skips_malformed_rows(feature):
    assert water_worker._normalize_feature(feature) is None


def test_normalize_coops_feature_preserves_station_metadata():
    updated = datetime(2026, 8, 7, 12, tzinfo=timezone.utc)
    station = water_worker._normalize_coops_feature(
        {
            "attributes": {
                "id": "8651370",
                "name": "Duck, NC",
                "state": "NC",
                "affil": "NOS",
                "cg_filedate": updated.timestamp() * 1000,
                "data": "data-url",
                "dataapi": "data-api-url",
                "metaapi": "meta-api-url",
            },
            "geometry": {"x": -75.746, "y": 36.183},
        },
        "water_level",
        "Water Level",
    )

    assert station is not None
    assert station["site_id"] == "COOPS_8651370"
    assert station["network"] == "coastal"
    assert station["capabilities"] == ["Water Level"]
    assert station["lat"] == 36.183
    assert station["lon"] == -75.746
    assert station["updated"] == updated.isoformat()
    assert station["dataapi_url"] == "data-api-url"


@pytest.mark.parametrize("feature", [None, {}, {"attributes": {"id": "123"}}])
def test_normalize_coops_feature_skips_malformed_rows(feature):
    assert water_worker._normalize_coops_feature(feature, "current", "Currents") is None


def test_normalize_ndbc_row_parses_readings_and_missing_markers():
    station = water_worker._normalize_ndbc_row(
        [
            "41025",
            "35.010",
            "-75.454",
            "2026",
            "08",
            "07",
            "12",
            "30",
            "180",
            "5.5",
            "7.0",
            "1.2",
            "8",
            "MM",
            "175",
            "1015.2",
            "-0.8",
            "24.1",
            "25.2",
            "MM",
            "9.0",
            "1.1",
        ]
    )

    assert station is not None
    assert station["site_id"] == "NDBC_41025"
    assert station["updated"] == "2026-08-07T12:30:00+00:00"
    assert station["readings"]["wind_speed"]["value"] == 5.5
    assert station["readings"]["tide"]["value"] == 1.1
    assert "average_wave_period" not in station["readings"]
    assert "dewpoint" not in station["readings"]
    assert station["status"] == "normal"

    missing = water_worker._normalize_ndbc_row(
        ["MISS", "35", "-75", "bad", "time", "parts", "x", "y"]
        + ["MM"] * 14
    )
    assert missing is not None
    assert missing["updated"] == ""
    assert missing["readings"] == {}
    assert missing["status"] == "missing"


@pytest.mark.parametrize(
    "parts",
    [
        [],
        ["SHORT"] * 20,
        [""] + ["0"] * 21,
        ["BADLAT", "not-a-lat", "-75"] + ["0"] * 19,
    ],
)
def test_normalize_ndbc_row_skips_malformed_rows(parts):
    assert water_worker._normalize_ndbc_row(parts) is None


def test_dedupe_stations_merges_coops_capabilities_and_sorts_by_name():
    water_level = {
        "site_id": "COOPS_1",
        "name": "Zulu",
        "network": "coastal",
        "station_type": "water_level",
        "capabilities": ["Water Level"],
    }
    currents = {
        "site_id": "COOPS_1",
        "name": "Zulu",
        "network": "coastal",
        "station_type": "current",
        "capabilities": ["Currents"],
    }
    river = {
        "site_id": "RIVER1",
        "name": "Alpha",
        "network": "river",
        "capabilities": ["River Gauge"],
    }

    stations = water_worker._dedupe_stations([water_level, river, currents, {}])

    assert [station["site_id"] for station in stations] == ["RIVER1", "COOPS_1"]
    assert stations[1]["capabilities"] == ["Water Level", "Currents"]
    assert stations[1]["station_type"] == "multi"


def test_parse_nwps_gauge_normalizes_detail_payload_and_missing_sentinels():
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    station = water_service._parse_nwps_gauge(
        {
            "lid": " abcn7 ",
            "usgsId": "02000000",
            "name": "Example River",
            "latitude": 35.75,
            "longitude": -78.5,
            "county": "Wake",
            "state": {"abbreviation": "NC"},
            "wfo": {"abbreviation": "RAH"},
            "rfc": {"abbreviation": "SERFC"},
            "timeZone": "EST5EDT",
            "pedts": {"observed": "HGIRG"},
            "status": {
                "observed": {
                    "primary": "7.25",
                    "primaryUnit": "ft",
                    "validTime": observed_at,
                    "floodCategory": "minor",
                },
                "forecast": {
                    "primary": "8.5",
                    "primaryUnit": "ft",
                    "validTime": "2026-08-08T00:00:00+00:00",
                    "floodCategory": "moderate",
                },
            },
            "flood": {
                "stageUnits": "ft",
                "flowUnits": "kcfs",
                "categories": {
                    "action": {"stage": "6", "flow": -9999},
                    "minor": {"stage": "7", "flow": "2.5"},
                    "moderate": {"stage": -999, "flow": -9999},
                },
            },
            "images": {
                "hydrograph": {
                    "default": "https://example.test/hydrograph.png",
                    "floodcat": "https://example.test/floodcat.png",
                }
            },
        }
    )

    assert station["site_id"] == "ABCN7"
    assert station["readings"]["stage"]["label"] == "Stage"
    assert station["readings"]["stage"]["value"] == 7.25
    assert station["status"] == "normal"
    assert station["forecast"]["value"] == 8.5
    assert station["flood"]["categories"] == {
        "action": {"stage": 6.0, "flow": None},
        "minor": {"stage": 7.0, "flow": 2.5},
    }
    assert station["hydrograph_url"] == "https://example.test/hydrograph.png"
    assert station["state"] == "NC"

    tide = water_service._parse_nwps_gauge(
        {
            "lid": "TIDE1",
            "pedts": {"observed": "HMIFZ"},
            "status": {
                "observed": {
                    "primary": "1.2",
                    "primaryUnit": "ft",
                    "validTime": observed_at,
                },
                "forecast": {"primary": -9999},
            },
        }
    )
    assert tide["readings"]["stage"]["label"] == "Tide Height"
    assert tide["forecast"] is None


@pytest.mark.parametrize("payload", [{}, [], None])
def test_parse_nwps_gauge_rejects_missing_or_malformed_payload(payload):
    with pytest.raises(HTTPException) as exc_info:
        water_service._parse_nwps_gauge(payload)

    assert exc_info.value.status_code == 404


def test_fetch_coops_live_readings_uses_latest_water_level_row(monkeypatch):
    captured = {}

    def fake_fetch(url, params, timeout):
        captured.update({"url": url, "params": params, "timeout": timeout})
        return {
            "data": [
                {"t": "2026-08-07 11:00", "v": "1.0", "q": "v"},
                {"t": "2026-08-07 12:00", "v": "1.25", "q": "p"},
            ]
        }

    monkeypatch.setattr(water_service, "_fetch_json", fake_fetch)

    readings = water_service._fetch_coops_live_readings("8651370", "water_level")

    assert captured["params"]["product"] == "water_level"
    assert "bin" not in captured["params"]
    assert readings == {
        "water_level": {
            "value": 1.25,
            "timestamp": "2026-08-07T12:00:00+00:00",
            "qualifiers": "p",
            "label": "Water Level",
            "units": "ft",
        }
    }


def test_fetch_coops_live_readings_parses_currents_and_legitimate_empty(monkeypatch):
    responses = iter(
        [
            {"data": [{"t": "bad-time", "s": "2.5", "d": "145"}]},
            {"data": []},
            {"data": ["malformed-row"]},
            [],
        ]
    )
    calls = []

    def fake_fetch(url, params, timeout):
        calls.append(params.copy())
        return next(responses)

    monkeypatch.setattr(water_service, "_fetch_json", fake_fetch)

    readings = water_service._fetch_coops_live_readings("cb0102", "current")
    empty = water_service._fetch_coops_live_readings("cb0102", "current")
    malformed = water_service._fetch_coops_live_readings("cb0102", "current")
    malformed_payload = water_service._fetch_coops_live_readings("cb0102", "current")

    assert calls[0]["product"] == "currents"
    assert calls[0]["bin"] == "1"
    assert readings["current_speed"]["value"] == 2.5
    assert readings["current_speed"]["timestamp"] == "bad-time"
    assert readings["current_direction"]["value"] == 145.0
    assert empty == {}
    assert malformed == {}
    assert malformed_payload == {}
