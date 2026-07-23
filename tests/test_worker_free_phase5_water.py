from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import threading
import time

import pytest

from app_core.refresh_coordinator import RefreshCoordinator, RefreshPolicy, Submission
from app_core.paths import BASE_DIR
import services.water_service as water_service
import workers.water_worker as water_worker


class _RecordingCoordinator:
    def __init__(self, submission: Submission | None = None):
        self.calls = []
        self.submission = submission or Submission(True, "queued")

    def submit(self, **kwargs):
        self.calls.append(kwargs)
        return self.submission


def _station(site_id: str, network: str, lon: float = -80.0) -> dict:
    return {
        "site_id": site_id,
        "name": site_id,
        "network": network,
        "lat": 35.0,
        "lon": lon,
    }


def _write_index(path, *, updated: datetime, stations: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "status": "success",
                "updated": updated.isoformat(),
                "source": "NOAA water gauges",
                "network_counts": {},
                "stations": stations,
            }
        ),
        encoding="utf-8",
    )


def test_missing_water_index_starts_exactly_one_shared_build(tmp_path, monkeypatch):
    coordinator = RefreshCoordinator(
        max_workers=2,
        max_queued=8,
        maintenance_interval_seconds=0.01,
    )
    coordinator.register_policy(
        RefreshPolicy(provider="noaa-water", max_concurrency=1)
    )
    started = threading.Event()
    release = threading.Event()
    refresh_calls = []
    index_file = tmp_path / "riv_gauges.json"

    def refresh():
        refresh_calls.append(True)
        started.set()
        assert release.wait(timeout=2)
        _write_index(
            index_file,
            updated=datetime.now(timezone.utc),
            stations=[
                _station("RIVER1", "river"),
                _station("COASTAL1", "coastal"),
                _station("NDBC_BUOY1", "buoy"),
            ],
        )
        return {"source_timestamp": "2026-07-23T12:00:00+00:00"}

    monkeypatch.setattr(
        water_service,
        "WATER_RIV_GAUGES_INDEX_FILE",
        index_file,
    )
    monkeypatch.setattr(water_service, "get_refresh_coordinator", lambda: coordinator)
    monkeypatch.setattr(water_service, "_water_index_refresh", refresh)
    water_service._WATER_CACHE.clear()
    coordinator.start()
    try:
        with ThreadPoolExecutor(max_workers=10) as callers:
            results = list(
                callers.map(
                    lambda _: water_service.get_water_stations_data(
                        bbox="-90,30,-70,40"
                    ),
                    range(10),
                )
            )
        assert started.wait(timeout=1)
        assert len(refresh_calls) == 1
        assert all(result["status"] == "warming" for result in results)
        assert all(result["refreshing"] for result in results)
        assert all(result["retry_after_seconds"] == 2.0 for result in results)
        release.set()
        assert coordinator.wait_for_idle(timeout=1)
        fresh = water_service.get_water_stations_data(
            bbox="-90,30,-70,40",
            networks="river",
        )
        assert fresh["status"] == "success"
        assert fresh["cache_state"] == "fresh"
        assert fresh["stations"] == [_station("RIVER1", "river")]
    finally:
        release.set()
        coordinator.stop()


def test_stale_water_index_is_served_while_refresh_runs(tmp_path, monkeypatch):
    index_file = tmp_path / "riv_gauges.json"
    _write_index(
        index_file,
        updated=datetime.now(timezone.utc) - timedelta(minutes=31),
        stations=[_station("RIVER1", "river")],
    )
    coordinator = _RecordingCoordinator()
    monkeypatch.setattr(water_service, "WATER_RIV_GAUGES_INDEX_FILE", index_file)
    monkeypatch.setattr(water_service, "get_refresh_coordinator", lambda: coordinator)
    water_service._WATER_CACHE.clear()

    result = water_service.get_water_stations_data(
        bbox="-90,30,-70,40",
        networks="river",
    )

    assert result["stations"] == [_station("RIVER1", "river")]
    assert result["stale"] is True
    assert result["cache_state"] == "stale_refreshing"
    assert result["refreshing"] is True
    assert result["retry_after_seconds"] == 2.0
    assert coordinator.calls[0]["key"] == ("water", "station-index")
    assert coordinator.calls[0]["provider"] == "noaa-water"


def test_fresh_but_incomplete_water_index_automatically_rebuilds(
    tmp_path,
    monkeypatch,
):
    index_file = tmp_path / "riv_gauges.json"
    _write_index(
        index_file,
        updated=datetime.now(timezone.utc),
        stations=[
            _station("COASTAL1", "coastal"),
            _station("NDBC_BUOY1", "buoy"),
        ],
    )
    coordinator = _RecordingCoordinator()
    monkeypatch.setattr(water_service, "WATER_RIV_GAUGES_INDEX_FILE", index_file)
    monkeypatch.setattr(water_service, "get_refresh_coordinator", lambda: coordinator)
    water_service._WATER_CACHE.clear()

    result = water_service.get_water_stations_data(bbox="-90,20,-70,40")

    assert result["cache_state"] == "stale_refreshing"
    assert result["refreshing"] is True
    assert result["missing_networks"] == ["river"]
    assert result["retry_after_seconds"] == 2.0
    assert "missing river stations" in result["message"]
    assert coordinator.calls[0]["key"] == ("water", "station-index")


def test_fresh_water_index_balances_networks_and_fills_limit(tmp_path, monkeypatch):
    index_file = tmp_path / "riv_gauges.json"
    stations = (
        [_station("COASTAL1", "coastal")]
        + [_station(f"BUOY{i}", "buoy", -80.0 + i / 100) for i in range(8)]
        + [_station("RIVER1", "river")]
    )
    _write_index(
        index_file,
        updated=datetime.now(timezone.utc),
        stations=stations,
    )
    coordinator = _RecordingCoordinator()
    monkeypatch.setattr(water_service, "WATER_RIV_GAUGES_INDEX_FILE", index_file)
    monkeypatch.setattr(water_service, "get_refresh_coordinator", lambda: coordinator)
    water_service._WATER_CACHE.clear()

    result = water_service.get_water_stations_data(
        bbox="-90,30,-70,40",
        max_sites=6,
    )

    networks = [station["network"] for station in result["stations"]]
    assert len(result["stations"]) == 6
    assert {"river", "coastal", "buoy"} <= set(networks)
    assert result["cache_state"] == "fresh"
    assert result["refreshing"] is False
    assert coordinator.calls == []
    one_result = water_service.get_water_stations_data(
        bbox="-90,30,-70,40",
        max_sites=1,
    )
    assert len(one_result["stations"]) == 1


def test_station_detail_cache_deduplicates_and_is_bounded(monkeypatch):
    water_service._WATER_DETAIL_CACHE.clear()
    water_service._DETAIL_PROVIDER_BACKOFF.clear()
    monkeypatch.setattr(water_service, "WATER_DETAIL_CACHE_MAX_ENTRIES", 2)
    calls = []

    def fetch():
        calls.append(True)
        time.sleep(0.03)
        return {"value": 1}

    with ThreadPoolExecutor(max_workers=8) as callers:
        results = list(
            callers.map(
                lambda _: water_service._fetch_station_detail(
                    "nwps",
                    "nwps-station:TEST",
                    fetch,
                ),
                range(8),
            )
        )

    assert calls == [True]
    assert results == [{"value": 1}] * 8
    water_service._detail_cache_set("detail:2", {"value": 2})
    water_service._detail_cache_set("detail:3", {"value": 3})
    assert list(water_service._WATER_DETAIL_CACHE) == ["detail:2", "detail:3"]


def test_station_detail_failure_enters_provider_backoff():
    water_service._WATER_DETAIL_CACHE.clear()
    water_service._DETAIL_PROVIDER_BACKOFF.clear()
    calls = []

    def fail():
        calls.append(True)
        raise OSError("provider unavailable")

    with pytest.raises(OSError, match="provider unavailable"):
        water_service._fetch_station_detail("coops", "coops-live:FAIL", fail)
    with pytest.raises(RuntimeError, match="backed off"):
        water_service._fetch_station_detail("coops", "coops-live:OTHER", fail)

    failures, retry_at = water_service._DETAIL_PROVIDER_BACKOFF["coops"]
    assert calls == [True]
    assert failures == 1
    assert time.monotonic() < retry_at <= time.monotonic() + 5.1


def test_water_worker_fetches_each_shared_source_once_and_publishes_atomically(
    tmp_path,
    monkeypatch,
):
    index_file = tmp_path / "riv_gauges.json"
    river_calls = []
    coops_calls = []
    ndbc_calls = []

    monkeypatch.setattr(water_worker, "INDEX_FILE", index_file)
    monkeypatch.setattr(
        water_worker,
        "_fetch_feature_page",
        lambda offset: river_calls.append(offset)
        or [
            {
                "attributes": {
                    "gaugelid": "RIVER1",
                    "location": "River One",
                    "latitude": 35,
                    "longitude": -80,
                }
            }
        ],
    )

    def fetch_coops(layer, offset):
        coops_calls.append((layer, offset))
        return [
            {
                "attributes": {
                    "id": "COAST1",
                    "name": "Coastal One",
                    "latitude": 34,
                    "longitude": -78,
                }
            }
        ]

    monkeypatch.setattr(water_worker, "_fetch_coops_feature_page", fetch_coops)
    monkeypatch.setattr(
        water_worker,
        "_fetch_ndbc_latest_stations",
        lambda: ndbc_calls.append(True)
        or [_station("NDBC_BUOY1", "buoy", -75.0)],
    )

    result = water_worker.refresh_riv_gauges_cache()

    assert river_calls == [0]
    assert coops_calls == [(0, 0), (2, 0)]
    assert ndbc_calls == [True]
    assert result["network_counts"] == {"buoy": 1, "coastal": 1, "river": 1}
    assert json.loads(index_file.read_text(encoding="utf-8")) == result
    assert not index_file.with_suffix(".json.tmp").exists()


def test_water_worker_rejects_partial_network_before_replacing_index(
    tmp_path,
    monkeypatch,
):
    index_file = tmp_path / "riv_gauges.json"
    original = {
        "status": "success",
        "updated": "2026-07-23T16:00:00+00:00",
        "count": 3,
        "network_counts": {"river": 1, "coastal": 1, "buoy": 1},
        "stations": [
            _station("RIVER1", "river"),
            _station("COAST1", "coastal"),
            _station("NDBC_BUOY1", "buoy"),
        ],
    }
    index_file.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(water_worker, "INDEX_FILE", index_file)
    monkeypatch.setattr(water_worker, "_fetch_feature_page", lambda _offset: [])
    monkeypatch.setattr(
        water_worker,
        "_fetch_coops_feature_page",
        lambda layer, _offset: [
            {
                "attributes": {
                    "id": f"COAST{layer}",
                    "name": "Coastal",
                    "latitude": 34,
                    "longitude": -78,
                }
            }
        ],
    )
    monkeypatch.setattr(
        water_worker,
        "_fetch_ndbc_latest_stations",
        lambda: [_station("NDBC_BUOY1", "buoy")],
    )

    with pytest.raises(RuntimeError, match="without river stations"):
        water_worker.refresh_riv_gauges_cache()

    assert json.loads(index_file.read_text(encoding="utf-8")) == original


def test_only_optional_coops_current_layer_may_skip_source_error(monkeypatch):
    monkeypatch.setattr(
        water_worker,
        "_fetch_json",
        lambda *_args, **_kwargs: {
            "error": {
                "code": 400,
                "message": "Failed to execute query.",
                "details": [],
            }
        },
    )

    assert water_worker._fetch_coops_feature_page(2, 0) == []
    with pytest.raises(RuntimeError, match="CO-OPS source error"):
        water_worker._fetch_coops_feature_page(0, 0)


def test_water_client_retries_from_response_hint():
    app = (
        Path(BASE_DIR)
        / "frontend"
        / "pages"
        / "water"
        / "water-app.js"
    ).read_text(encoding="utf-8")

    assert "Number(data?.retry_after_seconds)" in app
    assert "data?.cache_state !== 'fresh'" in app
    assert "_scheduleWaterReload(Math.max(500, retryAfterSeconds * 1000))" in app
