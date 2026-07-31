from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path
import threading
import time
from unittest.mock import Mock

import requests
from starlette.responses import Response

from config.satellite_v2_config import SATELLITE_V2_RAPID_WORKER_ZOOMS
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
        "app_core.render_budget.heavy_render_slot",
        nullcontext,
    )

    result = service._run_selected_satellite_accelerator(
        "goes19", "MESO1", "Channel13", "rapid-tiles"
    )

    assert result == {"rendered": 1}
    assert calls[0] == "live-idle"
    assert calls[-1] == "accelerator"


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
    assert "hotFrameIndexes" not in animator
    assert "client_id" in (
        root / "frontend/pages/satellite/satellite-engine.js"
    ).read_text("utf-8")
    assert "satellite-page.js?v=20260731f" in page


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
            },
        ),
    )

    response = satellite_routes.get_satellite_v2_tile(
        z=7,
        x=1,
        y=2,
        sat_id="goes19",
        sector="CONUS",
        channel="Channel13",
        frame_key="frame-a",
    )

    assert isinstance(response, Response)
    assert response.body == content
