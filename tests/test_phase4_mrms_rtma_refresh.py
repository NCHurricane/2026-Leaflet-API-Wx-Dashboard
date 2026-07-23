from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from app_core.refresh_coordinator import Submission
from app_core.render_budget import heavy_render_slot
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
        "cache.overlay_cache_utils.flat_overlay_list_frames",
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
        "cache.overlay_cache_utils.flat_overlay_read_processed_keys",
        lambda *args: {"cached-source"},
    )
    image = tmp_path / "cached.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(
        "cache.overlay_cache_utils.flat_overlay_image_path",
        lambda *args: str(image),
    )

    assert rtma_live_worker._render_rtma_frame_to_overlay(
        str(tmp_path),
        source,
        "CONUS",
        "rtma_hourly",
        "temperature",
    )


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
