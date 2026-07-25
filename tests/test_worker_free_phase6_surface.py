from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import pytest

from app_core.refresh_coordinator import RefreshCoordinator, RefreshPolicy, Submission
from app_core.render_budget import surface_gradient_render_slot
import services.surface_service as surface_service
import workers.surface_worker as surface_worker


@pytest.fixture(autouse=True)
def _reset_surface_snapshots():
    surface_service._SURFACE_SNAPSHOTS.clear()
    yield
    surface_service._SURFACE_SNAPSHOTS.clear()


class _RecordingCoordinator:
    def __init__(self):
        self.calls = []

    def submit(self, **kwargs):
        self.calls.append(kwargs)
        return Submission(True, "queued")

    def record_presence(self, **_kwargs):
        return None


def _write_stale_gradient(tmp_path):
    gradient_dir = tmp_path / "surface" / "gradients" / "CONUS"
    gradient_dir.mkdir(parents=True)
    image_path = gradient_dir / "temperature.png"
    image_path.write_bytes(b"complete-gradient")
    meta_path = gradient_dir / "temperature.json"
    meta_path.write_text(
        json.dumps(
            {
                "region": "CONUS",
                "product": "temperature",
                "bounds": [-130.0, -60.0, 20.0, 55.0],
                "image_url": "/cache/surface/gradients/CONUS/temperature.png",
                "timestamp": "2026-07-23T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    stale_time = time.time() - surface_service._SURFACE_GRADIENT_TTL_SECONDS - 1
    os.utime(image_path, (stale_time, stale_time))
    os.utime(meta_path, (stale_time, stale_time))


def test_stale_gradient_is_served_while_observations_warm(tmp_path, monkeypatch):
    coordinator = _RecordingCoordinator()
    _write_stale_gradient(tmp_path)
    monkeypatch.setattr(surface_service, "CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(surface_service, "get_refresh_coordinator", lambda: coordinator)

    result = surface_service.get_surface_gradient("CONUS", "temperature")

    assert result["image_url"].endswith("/temperature.png")
    assert result["cache_state"] == "stale_refreshing"
    assert result["refresh_stage"] == "observations"
    assert coordinator.calls[0]["key"] == (
        "surface",
        "observations",
        "CONUS",
    )
    assert coordinator.calls[0]["provider"] == "aviationweather"


def test_ready_snapshot_submits_only_requested_gradient(tmp_path, monkeypatch):
    coordinator = _RecordingCoordinator()
    snapshot = object()
    monkeypatch.setattr(surface_service, "CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(surface_service, "get_refresh_coordinator", lambda: coordinator)
    monkeypatch.setattr(
        surface_service,
        "_render_surface_gradient",
        lambda dataframe, region, product: {
            "same_snapshot": dataframe is snapshot,
            "region": region,
            "product": product,
        },
    )
    surface_service._SURFACE_SNAPSHOTS["WORLD"] = (time.monotonic(), snapshot)

    result = surface_service.get_surface_gradient("WORLD", "dew_point")

    assert result["cache_state"] == "refreshing"
    assert result["refresh_stage"] == "gradient"
    call = coordinator.calls[0]
    assert call["key"] == ("surface", "gradient", "WORLD", "dew_point")
    assert call["provider"] == "surface-gradient"
    assert call["function"]() == {
        "same_snapshot": True,
        "region": "WORLD",
        "product": "dew_point",
    }


def test_surface_snapshot_is_shared_for_concurrent_products(monkeypatch):
    snapshot = object()
    calls = []

    def fetch(region):
        calls.append(region)
        time.sleep(0.02)
        return snapshot

    monkeypatch.setattr(surface_service.surface_utils, "fetch_metar_data", fetch)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda _index: surface_service._get_surface_observation_snapshot(
                    "CONUS"
                ),
                range(8),
            )
        )

    assert calls == ["CONUS"]
    assert all(result is snapshot for result in results)


def test_targeted_worker_renders_one_region_product(monkeypatch):
    calls = []
    monkeypatch.setattr(
        surface_worker,
        "_build_surface_gradients",
        lambda dataframe, selected_products, region, timestamp_iso: (
            calls.append(
                (dataframe, selected_products, region, timestamp_iso)
            )
            or {
                "visibility": {
                    "region": region,
                    "product": "visibility",
                }
            }
        ),
    )
    snapshot = object()

    result = surface_worker.render_surface_gradient(
        snapshot,
        region="CONUS",
        product="visibility",
        timestamp_iso="2026-07-23T12:00:00+00:00",
    )

    assert result["product"] == "visibility"
    assert calls == [
        (
            snapshot,
            {"visibility"},
            "CONUS",
            "2026-07-23T12:00:00+00:00",
        )
    ]


@pytest.mark.parametrize("region", ["CONUS", "WORLD"])
@pytest.mark.parametrize(
    "product",
    sorted(surface_worker._SURFACE_GRADIENT_PRODUCTS),
)
def test_isolated_gradient_product_region_paths(
    region,
    product,
    tmp_path,
    monkeypatch,
):
    point_count = 25
    longitudes = np.linspace(
        -125.0 if region == "CONUS" else -170.0,
        -65.0 if region == "CONUS" else 170.0,
        point_count,
    )
    latitudes = np.linspace(
        25.0 if region == "CONUS" else -60.0,
        50.0 if region == "CONUS" else 60.0,
        point_count,
    )
    snapshot = pd.DataFrame(
        {
            "longitude": longitudes,
            "latitude": latitudes,
            "air_temperature": np.linspace(20.0, 90.0, point_count),
            "feels_like": np.linspace(18.0, 95.0, point_count),
            "dew_point_temperature": np.linspace(10.0, 70.0, point_count),
            "relative_humidity": np.linspace(20.0, 95.0, point_count),
            "wind_speed": np.linspace(0.0, 50.0, point_count),
            "peak_wind": np.linspace(5.0, 65.0, point_count),
            "altimeter": np.linspace(29.5, 30.8, point_count),
            "mean_sea_level_pressure": np.linspace(
                990.0,
                1040.0,
                point_count,
            ),
            "visibility": np.linspace(0.5, 10.0, point_count),
        }
    )
    monkeypatch.setattr(surface_worker, "_CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(surface_worker, "_GRADIENT_WIDTH", 64)
    monkeypatch.setattr(surface_worker, "_GRADIENT_HEIGHT", 32)
    monkeypatch.setattr(surface_worker, "_GRADIENT_WIDTH_WORLD", 64)
    monkeypatch.setattr(surface_worker, "_GRADIENT_HEIGHT_WORLD", 32)
    monkeypatch.setattr(
        surface_worker,
        "_region_land_mask",
        lambda *_args, **_kwargs: None,
    )

    result = surface_worker.render_surface_gradient(
        snapshot,
        region=region,
        product=product,
        timestamp_iso="2026-07-23T12:00:00+00:00",
    )

    artifact_dir = tmp_path / "surface" / "gradients" / region
    assert result["region"] == region
    assert result["product"] == product
    assert (artifact_dir / f"{product}.png").is_file()
    assert (artifact_dir / f"{product}.json").is_file()
    assert sorted(path.stem for path in artifact_dir.glob("*.png")) == [product]


def test_surface_gradient_budget_serializes_renders():
    active = 0
    peak = 0
    lock = threading.Lock()
    first_entered = threading.Event()
    release = threading.Event()

    def render(index):
        nonlocal active, peak
        with surface_gradient_render_slot():
            with lock:
                active += 1
                peak = max(peak, active)
                if index == 0:
                    first_entered.set()
            if index == 0:
                assert release.wait(timeout=1)
            with lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(render, 0)
        assert first_entered.wait(timeout=1)
        second = executor.submit(render, 1)
        time.sleep(0.03)
        release.set()
        first.result(timeout=1)
        second.result(timeout=1)

    assert peak == 1


def test_direct_iem_fallback_uses_shared_provider_budget():
    coordinator = RefreshCoordinator()
    coordinator.register_policy(
        RefreshPolicy(provider="iem", min_request_interval=0, max_concurrency=1)
    )
    active = 0
    peak = 0
    lock = threading.Lock()
    first_entered = threading.Event()
    release = threading.Event()

    def request(index):
        nonlocal active, peak
        with coordinator.provider_budget("iem"):
            with lock:
                active += 1
                peak = max(peak, active)
                if index == 0:
                    first_entered.set()
            if index == 0:
                assert release.wait(timeout=1)
            with lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(request, 0)
        assert first_entered.wait(timeout=1)
        second = executor.submit(request, 1)
        time.sleep(0.03)
        release.set()
        first.result(timeout=1)
        second.result(timeout=1)

    assert peak == 1
