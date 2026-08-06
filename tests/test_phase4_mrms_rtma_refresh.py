from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from pathlib import Path

from app_core.refresh_coordinator import Submission
from app_core.grib_decode import serialized_grib_decode
from app_core.render_budget import heavy_render_slot
import mrms.mrms_utils as mrms_utils
import rtma.rtma_utils as rtma_utils
import services.mrms_service as mrms_service
import services.overlay_service as overlay_service
import services.rtma_service as rtma_service
import workers.mrms_live_worker as mrms_live_worker
import workers.mrms_worker as mrms_worker
import workers.rtma_live_worker as rtma_live_worker


class _RecordingCoordinator:
    def __init__(self):
        self.calls = []
        self.presence = []

    def record_presence(self, **kwargs):
        self.presence.append(kwargs)

    def submit(self, **kwargs):
        self.calls.append(kwargs)
        return Submission(True, "queued")


def test_mrms_refresh_is_keyed_to_selected_product(monkeypatch):
    coordinator = _RecordingCoordinator()
    monkeypatch.setattr(
        mrms_service,
        "get_refresh_coordinator",
        lambda: coordinator,
    )
    worker_calls = []
    monkeypatch.setattr(
        mrms_service,
        "_refresh_mrms_product",
        lambda product: worker_calls.append(product) or {"product": product},
    )

    result = mrms_service.set_mrms_product("PrecipRate")

    assert result["refresh_status"] == "queued"
    call = coordinator.calls[0]
    assert call["key"] == ("mrms", "latest", "PrecipRate")
    assert call["provider"] == "noaa-mrms"
    assert call["min_success_interval_seconds"] == 120
    call["function"]()
    assert worker_calls == ["PrecipRate"]


def test_rtma_refresh_is_hourly_and_latest_only(monkeypatch):
    coordinator = _RecordingCoordinator()
    monkeypatch.setattr(
        rtma_service,
        "get_refresh_coordinator",
        lambda: coordinator,
    )
    worker_calls = []
    monkeypatch.setattr(
        "workers.rtma_live_worker.run_rtma_live_product",
        lambda *args, **kwargs: worker_calls.append((args, kwargs)) or 1,
    )

    rtma_service.start_rtma_product_refresh(
        "CONUS",
        "rtma_hourly",
        "temperature",
    )

    call = coordinator.calls[0]
    assert call["key"] == (
        "rtma",
        "latest",
        "CONUS",
        "rtma_hourly",
        "temperature",
    )
    assert call["provider"] == "noaa-rtma"
    assert call["min_success_interval_seconds"] == 3600
    call["function"]()
    assert worker_calls == [
        (
            ("CONUS", "rtma_hourly", "temperature"),
            {"force": True, "latest_only": True, "max_hours": 2},
        )
    ]


def test_main_quiets_pyart_before_route_imports():
    main_source = Path("main.py").read_text(encoding="utf-8")

    quiet_index = main_source.index('_os.environ.setdefault("PYART_QUIET", "1")')
    route_index = main_source.index("from routes.radar import router as radar_router")
    assert quiet_index < route_index


def test_rtma_rapid_refresh_uses_fifteen_minute_cadence(monkeypatch):
    coordinator = _RecordingCoordinator()
    monkeypatch.setattr(rtma_service, "get_refresh_coordinator", lambda: coordinator)

    rtma_service.start_rtma_product_refresh(
        "CONUS",
        "rtma_rapid_update",
        "temperature",
    )

    assert coordinator.calls[0]["min_success_interval_seconds"] == 15 * 60


def test_partial_overlay_cache_still_schedules_horizon_fill(monkeypatch):
    coordinator = _RecordingCoordinator()
    monkeypatch.setattr(
        overlay_service,
        "_start_selected_refresh",
        lambda *args: Submission(False, "current"),
    )
    monkeypatch.setattr(
        overlay_service,
        "get_refresh_coordinator",
        lambda: coordinator,
    )
    monkeypatch.setattr(
        "app_core.overlay_cache.flat_overlay_list_frames",
        lambda *args: [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "frame_key": "current",
            }
        ],
    )

    result = overlay_service.get_overlay_frames(
        family="mrms",
        product="Refl_HSR",
        hours=3,
    )

    assert result["frame_count"] == 1
    assert result["refreshing"] is True
    call = coordinator.calls[0]
    assert call["key"] == (
        "overlay-history",
        "mrms",
        "CONUS",
        "rtma_hourly",
        "Refl_HSR",
        "3",
    )
    assert call["provider"] == "noaa-mrms"
    assert call["min_success_interval_seconds"] == 120


def test_mrms_history_lists_and_renders_upstream_window(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    upstream = [
        ("older.grib2.gz", now - timedelta(minutes=10)),
        ("newer.grib2.gz", now - timedelta(minutes=5)),
    ]
    monkeypatch.setattr(mrms_live_worker, "_CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(mrms_live_worker, "_MRMS_CACHE", str(tmp_path / "mrms"))
    monkeypatch.setattr(
        "mrms.mrms_nodd_utils.list_mrms_files",
        lambda *args: upstream,
    )
    downloads = []

    def download(source_key, target_dir):
        downloads.append((source_key, target_dir))
        return str(tmp_path / source_key)

    monkeypatch.setattr("mrms.mrms_nodd_utils.download_mrms_file", download)
    rendered = []
    monkeypatch.setattr(
        mrms_live_worker,
        "_render_mrms_frame_to_overlay",
        lambda path, product, file_dt, cache_root: rendered.append(
            (path, product, file_dt, cache_root)
        )
        or True,
    )
    monkeypatch.setattr(mrms_live_worker, "mark_run_complete", lambda *_args: None)

    count = mrms_live_worker.run_mrms_live_product(
        "Refl_HSR",
        max_hours=3,
    )

    assert count == 2
    assert [item[0] for item in downloads] == [
        "newer.grib2.gz",
        "older.grib2.gz",
    ]
    assert [item[2] for item in rendered] == [
        now - timedelta(minutes=5),
        now - timedelta(minutes=10),
    ]


def test_rtma_latest_only_uses_newest_source(monkeypatch):
    now = datetime.now(timezone.utc)
    newest = SimpleNamespace(valid_time=now, data_key="newest")
    oldest = SimpleNamespace(
        valid_time=now - timedelta(hours=1),
        data_key="oldest",
    )
    monkeypatch.setattr(
        "rtma.rtma_utils.iter_rtma_sources_within_hours",
        lambda *args, **kwargs: iter((newest, oldest)),
    )
    rendered = []
    monkeypatch.setattr(
        rtma_live_worker,
        "_render_rtma_frame_to_overlay",
        lambda cache_root, source, *args: rendered.append(source.data_key) or True,
    )
    monkeypatch.setattr(rtma_live_worker, "mark_run_complete", lambda *_args: None)

    count = rtma_live_worker.run_rtma_live_product(
        "CONUS",
        "rtma_hourly",
        "temperature",
        latest_only=True,
    )

    assert count == 1
    assert rendered == ["newest"]


def test_rtma_cached_frame_is_a_successful_noop(monkeypatch, tmp_path):
    source = SimpleNamespace(
        valid_time=datetime.now(timezone.utc),
        data_key="cached-source",
    )
    monkeypatch.setattr(
        "app_core.overlay_cache.flat_overlay_read_processed_keys",
        lambda *args: {"cached-source"},
    )
    image = tmp_path / "cached.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(
        "app_core.overlay_cache.flat_overlay_image_path",
        lambda *args: str(image),
    )

    assert rtma_live_worker._render_rtma_frame_to_overlay(
        str(tmp_path),
        source,
        "CONUS",
        "rtma_hourly",
        "temperature",
    )


def test_rtma_grib_download_is_deduplicated_per_source(monkeypatch, tmp_path):
    source = SimpleNamespace(url="https://example.invalid/rtma.grb2")
    entered = threading.Event()
    release = threading.Event()
    request_count = 0
    active = 0
    maximum = 0
    guard = threading.Lock()

    class _Response:
        def __enter__(self):
            nonlocal request_count, active, maximum
            with guard:
                request_count += 1
                active += 1
                maximum = max(maximum, active)
            return self

        def __exit__(self, *_args):
            nonlocal active
            with guard:
                active -= 1

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def iter_content(chunk_size):
            assert chunk_size == 1024 * 1024
            entered.set()
            assert release.wait(timeout=1)
            yield b"GRIB test payload"

    monkeypatch.setattr(
        rtma_utils.requests,
        "get",
        lambda *_args, **_kwargs: _Response(),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(rtma_utils.ensure_rtma_grib, str(tmp_path), source)
        assert entered.wait(timeout=1)
        second = executor.submit(rtma_utils.ensure_rtma_grib, str(tmp_path), source)
        time.sleep(0.03)
        release.set()
        paths = [first.result(timeout=1), second.result(timeout=1)]

    assert paths[0] == paths[1]
    assert request_count == 1
    assert maximum == 1
    assert open(paths[0], "rb").read() == b"GRIB test payload"
    assert not os.path.exists(f"{paths[0]}.part")


def test_rtma_cfgrib_decode_is_serialized(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    active = 0
    maximum = 0
    guard = threading.Lock()

    class _Value:
        def __init__(self, values):
            self.values = values

        def squeeze(self, drop=True):
            assert drop is True
            return self

    class _Dataset:
        data_vars = {"t2m": _Value([[1.0, 2.0], [3.0, 4.0]])}
        coords = {}

        def __getitem__(self, key):
            if key == "latitude":
                return _Value([35.0, 36.0])
            if key == "longitude":
                return _Value([-79.0, -78.0])
            return self.data_vars[key]

    def fake_open(path, **_kwargs):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        if path == "first.grb2":
            entered.set()
            assert release.wait(timeout=1)
        with guard:
            active -= 1
        return [_Dataset()]

    rtma_utils._get_grib_datasets_cached.cache_clear()
    monkeypatch.setattr(rtma_utils.cfgrib, "open_datasets", fake_open)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(rtma_utils._extract_dataset, "first.grb2", "t2m")
        assert entered.wait(timeout=1)
        second = executor.submit(rtma_utils._extract_dataset, "second.grb2", "t2m")
        time.sleep(0.03)
        release.set()
        first.result(timeout=1)
        second.result(timeout=1)
    rtma_utils._get_grib_datasets_cached.cache_clear()

    assert maximum == 1


def test_mrms_decode_uses_shared_eccodes_gate(monkeypatch):
    entered = threading.Event()
    monkeypatch.setattr(mrms_utils, "CFGRIB_AVAILABLE", True)
    monkeypatch.setattr(
        mrms_utils,
        "_read_mrms_grib2_unlocked",
        lambda *_args, **_kwargs: entered.set() or ([], {}),
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        with serialized_grib_decode():
            future = executor.submit(
                mrms_utils.read_mrms_grib2,
                "test.grib2",
                "PrecipRate",
            )
            time.sleep(0.03)
            assert not entered.is_set()
        future.result(timeout=1)

    assert entered.is_set()


def test_rtma_city_cache_generation_is_deduplicated(monkeypatch, tmp_path):
    source = SimpleNamespace(
        url="https://example.invalid/current.grb2",
        data_key="current",
        valid_time=datetime.now(timezone.utc),
    )
    cities_path = tmp_path / "cities.json"
    cities_path.write_text("[]", encoding="utf-8")
    entered = threading.Event()
    release = threading.Event()
    load_count = 0

    def fake_load(*_args, **_kwargs):
        nonlocal load_count
        load_count += 1
        entered.set()
        assert release.wait(timeout=1)
        return (
            [[1.0, 2.0], [3.0, 4.0]],
            [35.0, 36.0],
            [-79.0, -78.0],
            source.valid_time.isoformat(),
        )

    monkeypatch.setattr(rtma_utils, "_load_rtma_product_grid", fake_load)
    with ThreadPoolExecutor(max_workers=2) as executor:
        args = (
            str(tmp_path), source, "CONUS", "rtma_rapid_update",
            "temperature", str(cities_path),
        )
        first = executor.submit(rtma_utils.ensure_rtma_city_geojson, *args)
        assert entered.wait(timeout=1)
        second = executor.submit(rtma_utils.ensure_rtma_city_geojson, *args)
        time.sleep(0.03)
        release.set()
        first_result = first.result(timeout=1)
        second_result = second.result(timeout=1)

    assert first_result == second_result
    assert load_count == 1


def test_unchanged_mrms_source_skips_conversion(monkeypatch, tmp_path):
    source_time = time.time()
    source_dt = datetime.fromtimestamp(
        source_time,
        tz=timezone.utc,
    )
    latest = tmp_path / "conus.grib2.gz"
    latest.write_bytes(b"cached")
    monkeypatch.setattr(mrms_worker, "_MRMS_CACHE", str(tmp_path))
    monkeypatch.setattr(
        mrms_worker,
        "_fetch_latest_product_grib",
        lambda product, fetch: (
            str(latest),
            source_dt,
            30,
            False,
            "CONUS/PrecipRate/cached.grib2.gz",
        ),
    )
    monkeypatch.setattr(
        "mrms.mrms_nodd_utils.get_latest_mrms_file",
        lambda *args, **kwargs: None,
    )
    render_calls = []
    monkeypatch.setattr(
        mrms_worker,
        "_prewarm_conus_png",
        lambda *args, **kwargs: render_calls.append(args),
    )
    monkeypatch.setattr(mrms_worker, "mark_run_complete", lambda *_args: None)

    result = mrms_worker.run_mrms_worker(
        force=True,
        product="PrecipRate",
    )

    assert result["status"] == "current"
    assert result["product"] == "PrecipRate"
    assert render_calls == []


def test_unchanged_mrms_source_skips_object_download(monkeypatch, tmp_path):
    product = "PrecipRate"
    source_key = "CONUS/PrecipRate/20260723/current.grib2.gz"
    source_dt = datetime(2026, 7, 23, 12, tzinfo=timezone.utc)
    product_dir = tmp_path / product
    product_dir.mkdir()
    (product_dir / "conus.grib2.gz").write_bytes(b"cached")
    (product_dir / "latest_source.json").write_text(
        json.dumps(
            {
                "product": product,
                "source_key": source_key,
                "source_timestamp": source_dt.isoformat(),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mrms_worker, "_MRMS_CACHE", str(tmp_path))
    downloads = []
    monkeypatch.setattr(
        "mrms.mrms_nodd_utils.download_mrms_file",
        lambda *args, **kwargs: downloads.append((args, kwargs)),
    )

    result = mrms_worker._fetch_latest_product_grib(
        product,
        lambda *args, **kwargs: (source_key, source_dt),
    )

    assert result == (
        str(product_dir / "conus.grib2.gz"),
        source_dt,
        30,
        False,
        source_key,
    )
    assert downloads == []


def test_heavy_render_budget_serializes_families():
    active = 0
    peak = 0
    lock = threading.Lock()
    release = threading.Event()
    first_entered = threading.Event()

    def render(index):
        nonlocal active, peak
        with heavy_render_slot():
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
