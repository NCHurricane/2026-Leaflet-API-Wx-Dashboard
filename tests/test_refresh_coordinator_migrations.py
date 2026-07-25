from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app_core.refresh_coordinator import (
    RefreshCoordinator,
    RefreshPolicy,
    Submission,
)
import services.surface_service as surface_service
import services.wpc_service as wpc_service


class _RecordingCoordinator:
    def __init__(self):
        self.calls = []

    def submit(self, **kwargs):
        self.calls.append(kwargs)
        return Submission(True, "queued")

    def record_presence(self, **kwargs):
        return None


def test_stale_surface_refresh_uses_shared_coordinator(tmp_path, monkeypatch):
    coordinator = _RecordingCoordinator()
    monkeypatch.setattr(
        surface_service,
        "get_refresh_coordinator",
        lambda: coordinator,
    )
    monkeypatch.setattr(surface_service, "CACHE_ROOT", str(tmp_path))
    cache_dir = tmp_path / "surface"
    cache_dir.mkdir()
    cache_file = cache_dir / "NC_temperature.json"
    cache_file.write_text(
        json.dumps(
            {
                "stations": [],
                "product": "temperature",
                "unit": "°F",
                "region": "NC",
                "count": 0,
                "timestamp": "2026-07-23T00:00:00+00:00",
                "timestamp_source": "station_valid",
            }
        ),
        encoding="utf-8",
    )
    stale_time = time.time() - surface_service._SURFACE_CACHE_TTL_SECONDS - 1
    os.utime(cache_file, (stale_time, stale_time))

    result = surface_service.get_surface_data(region="NC", product="temperature")

    assert result["cache_state"] == "stale_refreshing"
    assert result["refreshing"] is True
    assert coordinator.calls[0]["key"] == (
        "surface",
        "observations",
        "NC",
    )
    assert coordinator.calls[0]["provider"] == "iem"


def test_mixed_cold_surface_requests_start_one_region_refresh(tmp_path, monkeypatch):
    coordinator = RefreshCoordinator(
        max_workers=2,
        max_queued=8,
        maintenance_interval_seconds=0.01,
    )
    coordinator.register_policy(
        RefreshPolicy(provider="iem", min_request_interval=0, max_concurrency=1)
    )
    started = threading.Event()
    release = threading.Event()
    calls = []

    def refresh(region, cache_dir):
        calls.append((region, cache_dir))
        started.set()
        assert release.wait(timeout=2)

    monkeypatch.setattr(surface_service, "CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(surface_service, "get_refresh_coordinator", lambda: coordinator)
    monkeypatch.setattr(surface_service, "_refresh_surface_region", refresh)
    coordinator.start()
    try:
        products = [
            "temperature",
            "dew_point",
            "wind_speed",
            "visibility",
            "altimeter",
        ]
        with ThreadPoolExecutor(max_workers=10) as callers:
            results = list(
                callers.map(
                    lambda index: surface_service.get_surface_data(
                        region="NC",
                        product=products[index % len(products)],
                    ),
                    range(10),
                )
            )
        assert started.wait(timeout=1)
        assert len(calls) == 1
        assert all(result["refreshing"] for result in results)
        assert all(result["cache_state"] == "refreshing" for result in results)
    finally:
        release.set()
        coordinator.stop()


def test_surface_region_refresh_fetches_once_and_publishes_all_products(
    tmp_path, monkeypatch
):
    cache_dir = tmp_path / "surface"
    cache_dir.mkdir()
    observations = object()
    fetch_calls = []

    def fetch(region):
        fetch_calls.append(region)
        return observations

    monkeypatch.setattr(surface_service.surface_utils, "fetch_metar_data", fetch)
    monkeypatch.setattr(
        surface_service,
        "_surface_source_timestamp_iso",
        lambda dataframe: "2026-07-23T12:00:00+00:00",
    )
    monkeypatch.setattr(
        surface_service,
        "build_surface_stations",
        lambda dataframe, product: [{"product": product}],
    )

    result = surface_service._refresh_surface_region("CONUS", str(cache_dir))

    assert fetch_calls == ["CONUS"]
    assert result["published_products"] == list(surface_service.SURFACE_PRODUCTS)
    for product, config in surface_service.SURFACE_PRODUCTS.items():
        payload = json.loads(
            (cache_dir / f"CONUS_{product}.json").read_text(encoding="utf-8")
        )
        assert payload["stations"] == [{"product": product}]
        assert payload["unit"] == config["unit"]
        assert payload["timestamp_source"] == "station_valid"


def test_stale_wpc_refresh_uses_shared_coordinator(tmp_path, monkeypatch):
    coordinator = _RecordingCoordinator()
    monkeypatch.setattr(wpc_service, "get_refresh_coordinator", lambda: coordinator)
    monkeypatch.setattr(wpc_service, "_WPC_CACHE", str(tmp_path))
    monkeypatch.setattr(wpc_service, "_WPC_STATUS", str(tmp_path / ".status"))
    product = {
        "id": "ero_day1",
        "label": "Day 1",
        "cache_path": "ero/day1.json",
        "day": 1,
    }
    monkeypatch.setattr(wpc_service, "get_product", lambda *args: product)
    monkeypatch.setattr(
        wpc_service,
        "wpc_schedule_for",
        lambda _product: type(
            "_DueSchedule",
            (),
            {"refresh_due": lambda self, **_kwargs: True},
        )(),
    )
    cache_file = tmp_path / "ero" / "day1.json"
    cache_file.parent.mkdir()
    cache_file.write_text(
        json.dumps(
            {
                "updated": "2026-07-23T00:00:00+00:00",
                "geojson": {"type": "FeatureCollection", "features": []},
            }
        ),
        encoding="utf-8",
    )
    result = wpc_service.get_wpc_layer(group="ero", day=1)

    assert result["cache_state"] == "stale_refreshing"
    assert result["refreshing"] is True
    assert coordinator.calls[0]["key"] == ("wpc", "product", "ero_day1")
    assert coordinator.calls[0]["provider"] == "wpc"


def test_failed_wpc_check_does_not_close_missed_boundary(tmp_path, monkeypatch):
    cache_file = tmp_path / "ero.json"
    cache_file.write_text(
        json.dumps({"updated": "2026-07-23T00:00:00+00:00"}),
        encoding="utf-8",
    )
    seen = {}

    class _Schedule:
        def refresh_due(self, **kwargs):
            seen.update(kwargs)
            return True

    monkeypatch.setattr(wpc_service, "wpc_schedule_for", lambda _product: _Schedule())

    _, stale = wpc_service._cache_state(
        str(cache_file),
        {"id": "ero_day1", "group": "ero"},
        {
            "status": "error",
            "checked_at": "2026-07-24T20:00:00+00:00",
        },
    )

    assert stale is True
    assert seen["last_checked_at"] is None
