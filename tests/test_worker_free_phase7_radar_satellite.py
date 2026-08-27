from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import inspect
from pathlib import Path
import threading
import time
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import requests
from starlette.responses import Response

from config.satellite_v2_config import (
    SATELLITE_V2_LIVE_TILE_RENDER_WORKERS,
    SATELLITE_V2_RAPID_WORKER_ZOOMS,
)
from radar import radar_chunks_utils
from satellite_v2 import providers, service
from satellite_v2.models import SourceFrame
from services import radar_service
from routes import satellite_v2 as satellite_routes


class _PrefixPaginator:
    def __init__(self):
        self.calls = 0

    def paginate(self, **_kwargs):
        self.calls += 1
        return [{"CommonPrefixes": [{"Prefix": "KMHX/10/"}, {"Prefix": "KMHX/11/"}]}]


class _S3:
    def __init__(self):
        self.paginator = _PrefixPaginator()

    def get_paginator(self, _name):
        return self.paginator


def test_radar_chunk_prefix_listing_is_cached(monkeypatch):
    s3 = _S3()
    radar_chunks_utils._PREFIX_CACHE.clear()
    monkeypatch.setattr(radar_chunks_utils._time, "monotonic", lambda: 100.0)

    assert radar_chunks_utils._list_site_prefixes(s3, "KMHX") == ["10", "11"]
    assert radar_chunks_utils._list_site_prefixes(s3, "KMHX") == ["10", "11"]
    assert s3.paginator.calls == 1


def test_incomplete_radar_history_bypasses_normal_refresh_cadence(monkeypatch):
    coordinator = Mock()
    coordinator.activate_presence_job.return_value = Mock(status="queued")
    monkeypatch.setattr(
        radar_service, "get_refresh_coordinator", lambda: coordinator
    )

    assert radar_service._radar_live_render_in_background(
        "KMHX",
        "L2_REF",
        "0.5",
        lookback_hours=6,
        urgent=True,
    )

    kwargs = coordinator.activate_presence_job.call_args.kwargs
    assert kwargs["min_success_interval_seconds"] == 0.0


def test_selected_radar_latest_refresh_is_bounded_and_latest_only(monkeypatch):
    coordinator = Mock()
    coordinator.activate_presence_job.return_value = Mock(status="queued")
    render = Mock(return_value=1)
    monkeypatch.setattr(
        radar_service, "get_refresh_coordinator", lambda: coordinator
    )
    monkeypatch.setattr(radar_service, "_radar_live_render_on_demand", render)

    assert radar_service._radar_live_refresh_latest_in_background(
        "KMHX",
        "L3_N0B",
        "auto",
        lookback_hours=1,
    )

    kwargs = coordinator.activate_presence_job.call_args.kwargs
    assert kwargs["key"][0] == "radar-live-latest"
    assert kwargs["interval_seconds"] == 60
    assert kwargs["lease_seconds"] == 180
    assert kwargs["min_success_interval_seconds"] == 60

    assert kwargs["function"]() == 1
    render.assert_called_once_with(
        "KMHX",
        "L3_N0B",
        latest_only=True,
        backfill_history=False,
        newest_first=True,
        max_render_frames=1,
        elevation="auto",
        motion=None,
        lookback_hours=1,
    )


def test_succeeded_radar_job_is_not_reported_as_still_filling(monkeypatch):
    coordinator = Mock()
    coordinator.describe.return_value = {"status": "succeeded"}
    coordinator.is_lease_active.return_value = True
    monkeypatch.setattr(
        radar_service, "get_refresh_coordinator", lambda: coordinator
    )

    assert not radar_service._radar_live_render_still_filling(
        "KMHX", "L2_REF", "0.5", None
    )


def test_satellite_source_download_is_deduplicated_per_frame(tmp_path, monkeypatch):
    active = 0
    maximum = 0
    guard = threading.Lock()

    class _Provider:
        @staticmethod
        def download_product_source_frames(**_kwargs):
            nonlocal active, maximum
            with guard:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.03)
            with guard:
                active -= 1
            return {"C13": tmp_path / "source.nc"}

    monkeypatch.setattr(providers, "_provider_module", lambda _sat_id: _Provider)
    frame = SourceFrame(
        frame_key="2026-07-24T12:00:00Z",
        timestamp_utc="2026-07-24T12:00:00Z",
        provider="test",
        source_key="source",
        source_url="https://example.invalid/source",
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                providers.download_product_source_frames,
                tmp_path,
                "goes19",
                "CONUS",
                "Channel13",
                frame,
            )
            for _ in range(2)
        ]
        [future.result() for future in futures]

    assert maximum == 1


def test_missing_eumetsat_credentials_return_capability_response(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("EUMETSAT_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("WX_EUMETSAT_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("EUMETSAT_CONSUMER_SECRET", raising=False)
    monkeypatch.delenv("WX_EUMETSAT_CONSUMER_SECRET", raising=False)
    get_catalog = Mock()
    monkeypatch.setattr(service.catalog, "get_catalog", get_catalog)

    payload = service.get_catalog_payload(
        str(tmp_path), "meteosat12", "FULLDISK", "Channel13", 1, 12, False
    )

    assert payload["status"] == "credentials_required"
    assert payload["frames"] == []
    get_catalog.assert_not_called()


def test_selected_rapid_product_activates_lease_job(monkeypatch):
    coordinator = Mock()
    coordinator.activate_presence_job.return_value = Mock(
        status="scheduled", retry_after_seconds=5.0
    )
    monkeypatch.setattr(
        "app_core.refresh_coordinator.get_refresh_coordinator", lambda: coordinator
    )

    payload = service._activate_satellite_accelerator(
        "goes19", "MESO1", "Channel13"
    )

    assert payload["accelerator"] == "rapid-tiles"
    assert payload["accelerator_status"] == "scheduled"
    kwargs = coordinator.activate_presence_job.call_args.kwargs
    assert kwargs["key"] == (
        "satellite",
        "rapid-tiles",
        "goes19",
        "MESO1",
        "Channel13",
    )
    assert kwargs["provider"] == "satellite-aws"
    assert kwargs["run_immediately"] is False


def test_selected_meteosat_product_activates_channel_specific_tile_job(monkeypatch):
    coordinator = Mock()
    coordinator.activate_presence_job.return_value = Mock(
        status="scheduled", retry_after_seconds=5.0
    )
    monkeypatch.setattr(
        "app_core.refresh_coordinator.get_refresh_coordinator", lambda: coordinator
    )

    payload = service._activate_satellite_accelerator(
        "meteosat12", "FULLDISK", "NighttimeMicrophysics"
    )

    assert payload["accelerator"] == "meteosat-tiles"
    kwargs = coordinator.activate_presence_job.call_args.kwargs
    assert kwargs["key"] == (
        "satellite",
        "meteosat-tiles",
        "meteosat12",
        "FULLDISK",
        "NighttimeMicrophysics",
    )
    assert kwargs["run_immediately"] is False


def test_selected_meteosat_rss_composite_activates_rss_tuned_tile_job(monkeypatch):
    coordinator = Mock()
    coordinator.activate_presence_job.return_value = Mock(
        status="scheduled", retry_after_seconds=5.0
    )
    monkeypatch.setattr(
        "app_core.refresh_coordinator.get_refresh_coordinator", lambda: coordinator
    )

    payload = service._activate_satellite_accelerator(
        "meteosat11", "RSS", "Dust"
    )

    assert payload["accelerator"] == "meteosat-rss-tiles"
    kwargs = coordinator.activate_presence_job.call_args.kwargs
    assert kwargs["key"] == (
        "satellite",
        "meteosat-rss-tiles",
        "meteosat11",
        "RSS",
        "Dust",
    )
    assert kwargs["run_immediately"] is False


def test_meteosat_rss_channels_keep_the_existing_deep_rapid_tail(monkeypatch):
    coordinator = Mock()
    coordinator.activate_presence_job.return_value = Mock(
        status="scheduled", retry_after_seconds=5.0
    )
    monkeypatch.setattr(
        "app_core.refresh_coordinator.get_refresh_coordinator", lambda: coordinator
    )

    payload = service._activate_satellite_accelerator(
        "meteosat11", "RSS", "Channel13"
    )

    assert payload["accelerator"] == "rapid-tiles"
    assert coordinator.activate_presence_job.call_args.kwargs["key"][1] == "rapid-tiles"


def test_selected_meteosat_accelerator_chains_source_and_memory_guarded_tiles(
    monkeypatch,
):
    calls = []
    slot = Mock(side_effect=lambda *_args, **_kwargs: nullcontext(True))
    wait_kwargs = []

    def fake_wait(**kwargs):
        calls.append("live-idle")
        wait_kwargs.append(kwargs)
        return True

    monkeypatch.setattr(service, "_wait_for_live_tile_idle", fake_wait)
    monkeypatch.setattr(
        "satellite_v2.meteosat_prefetch_worker.run_satellite_v2_meteosat_prefetch_worker",
        lambda **_kwargs: calls.append("source") or {"downloaded": 1},
    )

    def fake_tiles(**kwargs):
        calls.append("tiles")
        assert kwargs["wait_until_ready"]()
        return {"frames": 1, "rendered": 4, "cancelled": 0}

    monkeypatch.setattr(
        "satellite_v2.meteosat_tile_worker.run_selected_meteosat_tile_warmer",
        fake_tiles,
    )
    monkeypatch.setattr(
        "app_core.render_budget.satellite_render_slot",
        slot,
    )
    monkeypatch.setattr(service, "estimate_source_grid_bytes", lambda *_args, **_kwargs: 100)

    result = service._run_selected_satellite_accelerator(
        "meteosat12", "FULLDISK", "Channel13", "meteosat-tiles"
    )

    assert calls == ["live-idle", "source", "live-idle", "tiles", "live-idle"]
    assert result["source_downloaded"] == 1
    assert result["tile_rendered"] == 4
    assert result["estimated_memory_bytes"] == 200
    assert slot.call_args.args == (200,)
    assert wait_kwargs[-1]["timeout_seconds"] == 0.0


def test_selected_meteosat_rss_accelerator_uses_bounded_source_and_tile_tail(
    monkeypatch,
):
    source_calls = []
    tile_calls = []
    slot = Mock(side_effect=lambda *_args, **_kwargs: nullcontext(True))
    monkeypatch.setattr(service, "_wait_for_live_tile_idle", lambda **_kwargs: True)
    monkeypatch.setattr(
        "satellite_v2.meteosat_prefetch_worker.run_satellite_v2_meteosat_prefetch_worker",
        lambda **kwargs: source_calls.append(kwargs) or {"downloaded": 2},
    )
    monkeypatch.setattr(
        "satellite_v2.meteosat_tile_worker.run_selected_meteosat_tile_warmer",
        lambda **kwargs: tile_calls.append(kwargs)
        or {"frames": 4, "rendered": 8, "cancelled": 0},
    )
    monkeypatch.setattr("app_core.render_budget.satellite_render_slot", slot)
    monkeypatch.setattr(service, "estimate_source_grid_bytes", lambda *_args, **_kwargs: 100)

    result = service._run_selected_satellite_accelerator(
        "meteosat11", "RSS", "Dust", "meteosat-rss-tiles"
    )

    assert source_calls[0]["jobs"] == (("meteosat11", "RSS"),)
    assert source_calls[0]["frames"] == 2
    assert source_calls[0]["backfill"] == 0
    assert source_calls[0]["newest_only"] is True
    assert source_calls[0]["hours"] == 2
    assert source_calls[0]["keep_hours"] == 3
    assert tile_calls[0]["channel"] == "Dust"
    assert result["source_downloaded"] == 2
    assert result["tile_frames"] == 4
    assert result["tile_rendered"] == 8
    assert result["estimated_memory_bytes"] == 200


def test_meso_accelerator_uses_initial_view_zooms():
    assert SATELLITE_V2_RAPID_WORKER_ZOOMS["MESO1"] == (5, 6)
    assert SATELLITE_V2_RAPID_WORKER_ZOOMS["MESO2"] == (5, 6)


def test_selected_accelerator_waits_for_live_tiles(monkeypatch):
    calls = []
    monkeypatch.setattr(
        service,
        "_wait_for_live_tile_idle",
        lambda **_kwargs: calls.append("live-idle") or True,
    )
    monkeypatch.setattr(
        "satellite_v2.rapid_worker.run_satellite_v2_rapid_worker",
        lambda **_kwargs: calls.append("accelerator") or {"rendered": 1},
    )
    monkeypatch.setattr(
        "app_core.render_budget.satellite_render_slot",
        lambda *_args, **_kwargs: nullcontext(True),
    )

    result = service._run_selected_satellite_accelerator(
        "goes19", "MESO1", "Channel13", "rapid-tiles"
    )

    assert result == {"rendered": 1}
    assert calls[0] == "live-idle"
    assert calls[-1] == "accelerator"


def test_live_tile_uses_estimated_satellite_memory_budget(tmp_path, monkeypatch):
    tile = tmp_path / "tile.png"
    slot = Mock(side_effect=lambda *_args, **_kwargs: nullcontext(True))
    monkeypatch.setattr(
        "app_core.render_budget.satellite_render_slot",
        slot,
    )
    monkeypatch.setattr(service, "estimate_source_grid_bytes", lambda *_args, **_kwargs: 123)
    monkeypatch.setattr(
        service,
        "render_frame_tile",
        lambda **_kwargs: (tile, {"cache_status": "miss"}),
    )

    path, stats = service._render_tile_with_budget(
        sat_id="meteosat12",
        channel_key="Channel13",
        z=5,
    )

    assert path == tile
    assert stats["estimated_memory_bytes"] == 123
    assert slot.call_args.args == (123,)


def test_selected_accelerator_stops_after_client_changes_selection(monkeypatch):
    coordinator = Mock()
    continued = []
    coordinator.activate_presence_job.return_value = Mock(
        status="scheduled", retry_after_seconds=5.0
    )
    monkeypatch.setattr(
        "app_core.refresh_coordinator.get_refresh_coordinator", lambda: coordinator
    )
    monkeypatch.setattr(
        service,
        "_run_selected_satellite_accelerator",
        lambda *args: continued.append(args[-1]()) or {"cancelled": 1},
    )
    service._SATELLITE_SELECTIONS.clear()
    service._record_satellite_selection(
        "page-a", ("meteosat11", "RSS", "Channel13")
    )

    service._activate_satellite_accelerator(
        "meteosat11", "RSS", "Channel13", client_id="page-a"
    )
    function = coordinator.activate_presence_job.call_args.kwargs["function"]
    service._record_satellite_selection(
        "page-a", ("meteosat9", "FULLDISK", "Channel13")
    )
    function()

    assert continued == [False]


def test_stale_catalog_completion_does_not_reclaim_client_selection(monkeypatch):
    coordinator = Mock()
    continued = []
    coordinator.activate_presence_job.return_value = Mock(
        status="scheduled", retry_after_seconds=5.0
    )
    monkeypatch.setattr(
        "app_core.refresh_coordinator.get_refresh_coordinator", lambda: coordinator
    )
    monkeypatch.setattr(
        service,
        "_run_selected_satellite_accelerator",
        lambda *args: continued.append(args[-1]()) or {"cancelled": 1},
    )
    service._SATELLITE_SELECTIONS.clear()
    service._record_satellite_selection(
        "page-a", ("meteosat9", "FULLDISK", "Channel13")
    )

    service._activate_satellite_accelerator(
        "meteosat11", "RSS", "Channel13", client_id="page-a"
    )
    coordinator.activate_presence_job.call_args.kwargs["function"]()

    assert continued == [False]


def test_releasing_one_page_preserves_another_pages_matching_selection():
    selection = ("meteosat12", "FULLDISK", "Channel13")
    service._SATELLITE_SELECTIONS.clear()
    service._record_satellite_selection("page-a", selection)
    service._record_satellite_selection("page-b", selection)

    service.release_satellite_selection("page-a")
    assert service._satellite_selection_is_active(selection)

    service.release_satellite_selection("page-b")
    assert not service._satellite_selection_is_active(selection)


def test_new_foreground_frame_cancels_queued_work_for_superseded_frame(
    tmp_path, monkeypatch
):
    selection = ("goes19", "MESO2", "Channel13")
    client_id = "page-a"
    render_future = service.Future()
    render_pool = Mock()
    render_pool.submit.return_value = render_future
    monkeypatch.setattr(service, "_ON_DEMAND_TILE_RENDER_POOL", render_pool)
    service._IN_FLIGHT_TILE_RENDERS.clear()
    service._SATELLITE_SELECTIONS.clear()
    service._SATELLITE_FRAME_REQUESTS.clear()
    service._record_satellite_selection(client_id, selection)
    service._record_satellite_frame_request(client_id, selection, "frame-a", 1)

    _, submitted = service._submit_tile_render(
        tmp_path / "frame-a.png",
        client_id=client_id,
        selection=selection,
        tile_frame_key="frame-a",
        foreground_frame_key="frame-a",
        frame_generation=1,
    )
    should_continue = render_pool.submit.call_args.kwargs["render_should_continue"]

    assert submitted
    assert should_continue()
    service._record_satellite_frame_request(client_id, selection, "frame-b", 2)
    assert not should_continue()
    assert service._satellite_client_owns_frame_request(
        client_id, selection, "frame-b", "frame-b", 2
    )
    render_future.cancel()


def test_eumetsat_download_concurrency_is_bounded():
    from satellite_v2 import provider_eumetsat

    assert 1 <= provider_eumetsat._FCI_DOWNLOAD_WORKERS <= 2


def test_eumetsat_forbidden_error_maps_to_license_required(monkeypatch):
    monkeypatch.setenv("EUMETSAT_CONSUMER_KEY", "configured")
    monkeypatch.setenv("EUMETSAT_CONSUMER_SECRET", "configured")
    response = Mock(status_code=403)
    error = requests.HTTPError("403 forbidden", response=response)

    capability = providers.classify_provider_error("meteosat12", error)

    assert capability["status"] == "license_required"


def test_satellite_page_surfaces_cached_provider_capability_state():
    root = Path(__file__).resolve().parents[1]
    page = (root / "frontend/pages/satellite/satellite.html").read_text("utf-8")
    script = (root / "frontend/pages/satellite/satellite-page.js").read_text("utf-8")
    animator = (root / "frontend/pages/satellite/satellite-anim.js").read_text(
        "utf-8"
    )

    assert "catalog.capability_status !== 'available'" in script
    assert "catalog?.capability_message" in script
    assert "'goes19:Meso1': 'goes-meso-current'" in script
    assert "const visibleLayers = new Set([currentLayer, previousLayer]" in animator
    assert "if (shouldRetainLayers()" in animator
    assert "&& layerReadyForSwap(layer, map.getZoom()))" in animator
    assert "layer.setOpacity(0);" in animator
    assert "if (map.hasLayer(layer)) map.removeLayer(layer);" in animator
    assert "if (prevLayer)" in animator
    assert "ready = await waitForLayerReady(nextLayer" in animator
    assert "hotFrameIndexes" not in animator
    assert "client_id" in (
        root / "frontend/pages/satellite/satellite-engine.js"
    ).read_text("utf-8")
    assert "selection/release" in (
        root / "frontend/pages/satellite/satellite-engine.js"
    ).read_text("utf-8")
    assert "satellite-page.js?v=20260826i" in page


def test_satellite_png_response_does_not_require_deferred_file_thread(
    tmp_path, monkeypatch
):
    tile = tmp_path / "tile.png"
    content = service._PNG_SIGNATURE + b"finished-tile"
    tile.write_bytes(content)
    monkeypatch.setattr(
        satellite_routes.satellite_v2_service,
        "resolve_tile",
        lambda **_kwargs: (
            tile,
            {
                "cache_status": "hit",
                "sat_id": "goes19",
                "sector": "CONUS",
                "channel": "Channel13",
                "download_elapsed_ms": 120,
                "decode_elapsed_ms": 45,
                "render_elapsed_ms": 8,
                "estimated_memory_bytes": 128 * 1024 * 1024,
            },
        ),
    )

    response = asyncio.run(
        satellite_routes.get_satellite_v2_tile(
            z=7,
            x=1,
            y=2,
            sat_id="goes19",
            sector="CONUS",
            channel="Channel13",
            frame_key="frame-a",
        )
    )

    assert isinstance(response, Response)
    assert response.body == content
    assert response.headers["X-Satellite-V2-Download-Ms"] == "120"
    assert response.headers["X-Satellite-V2-Decode-Ms"] == "45"
    assert response.headers["X-Satellite-V2-Render-Ms"] == "8"
    assert response.headers["X-Satellite-V2-Estimated-Memory-MB"] == "128"


@pytest.mark.parametrize(
    ("miss_reason", "expected_cache_control"),
    [
        # A negative marker is permanent for this frame, so the placeholder is
        # as immutable as a rendered tile and must survive a pan.
        ("negative-cache", "public, max-age=86400, immutable"),
        # Not-yet-rendered and cancelled tiles are transient and must not stick.
        ("missing", "no-store, max-age=0"),
    ],
)
def test_off_disk_tile_is_cacheable_only_when_permanently_empty(
    tmp_path, monkeypatch, miss_reason, expected_cache_control
):
    monkeypatch.setattr(
        satellite_routes.satellite_v2_service,
        "resolve_tile",
        lambda **_kwargs: (
            tmp_path / "absent.png",
            {
                "cache_status": "invalid" if miss_reason == "negative-cache" else "empty",
                "miss_reason": miss_reason,
                "sat_id": "meteosat11",
                "sector": "RSS",
                "channel": "Channel13",
            },
        ),
    )

    response = asyncio.run(
        satellite_routes.get_satellite_v2_tile(
            z=6,
            x=32,
            y=23,
            sat_id="meteosat11",
            sector="RSS",
            channel="Channel13",
            frame_key="frame-a",
        )
    )

    assert response.headers["Cache-Control"] == expected_cache_control


def test_satellite_tile_route_waits_outside_shared_request_threads(
    tmp_path, monkeypatch
):
    assert inspect.iscoroutinefunction(satellite_routes.get_satellite_v2_tile)
    tile = tmp_path / "tile.png"
    tile.write_bytes(service._PNG_SIGNATURE + b"concurrency-test")
    release = threading.Event()
    entered_lock = threading.Lock()
    entered = 0

    def slow_resolve(**_kwargs):
        nonlocal entered
        with entered_lock:
            entered += 1
        assert release.wait(timeout=5)
        return tile, {"cache_status": "hit"}

    monkeypatch.setattr(service, "resolve_tile", slow_resolve)

    app = FastAPI()
    app.include_router(satellite_routes.router)

    @app.get("/unrelated")
    def unrelated():
        return Response(content=b"ok")

    url = (
        "/api/satellite-v2/tile/5/1/1?"
        "sat_id=goes19&sector=CONUS&channel=Channel13&frame_key=frame-a"
    )
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=49) as callers:
        tile_requests = [callers.submit(client.get, url) for _ in range(48)]
        try:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with entered_lock:
                    if entered >= SATELLITE_V2_LIVE_TILE_RENDER_WORKERS:
                        break
                time.sleep(0.01)
            with entered_lock:
                assert entered >= SATELLITE_V2_LIVE_TILE_RENDER_WORKERS
            time.sleep(0.1)
            response = callers.submit(client.get, "/unrelated").result(timeout=1)
            assert response.status_code == 200
            assert response.content == b"ok"
        finally:
            release.set()
            [request.result(timeout=5) for request in tile_requests]


def test_released_satellite_selection_stops_waiting_but_keeps_started_artifact(
    tmp_path, monkeypatch
):
    render_future = service.Future()
    submitted = threading.Event()

    def fake_submit(*_args, **_kwargs):
        submitted.set()
        return render_future, True

    monkeypatch.setattr(service, "_submit_tile_render", fake_submit)
    service._SATELLITE_SELECTIONS.clear()
    service._record_satellite_selection(
        "page-a", ("goes19", "CONUS", "Channel13")
    )

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            service.resolve_tile,
            str(tmp_path),
            "goes19",
            "CONUS",
            "Channel13",
            "frame-a",
            5,
            1,
            1,
            frame_override={"frame_key": "frame-a"},
            client_id="page-a",
        )
        assert submitted.wait(timeout=1)
        service.release_satellite_selection("page-a")
        path, stats = pending.result(timeout=1)

    assert stats["cache_status"] == "cancelled"
    assert stats["miss_reason"] == "selection-released"
    assert not render_future.cancelled()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(service._PNG_SIGNATURE + b"completed-after-release")
    render_future.set_result((path, {"cache_status": "miss"}))
    assert path.read_bytes().endswith(b"completed-after-release")
