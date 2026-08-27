from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from config.satellite_v2_config import (
    fci_supported_products,
    normalize_channel,
    seviri_supported_products,
)
from satellite_v2 import catalog


ROOT = Path(__file__).resolve().parents[1]


def test_wpc_raster_url_is_versioned_and_status_is_separate() -> None:
    engine = (ROOT / "frontend/pages/wpc/wpc-engine.js").read_text(encoding="utf-8")
    page = (ROOT / "frontend/pages/wpc/wpc.html").read_text(encoding="utf-8")

    assert "versionedImageUrl(geojson.image_url, geojson._updated)" in engine
    assert "status.setDataState('Fresh data', 'fresh')" in engine
    assert "Refreshing stale data…" in engine
    assert "wpc-page.js?v=20260826i" in page


def test_mrms_initial_load_and_live_append_hold_at_newest() -> None:
    page = (ROOT / "frontend/pages/mrms/mrms-page.js").read_text(encoding="utf-8")
    markup = (ROOT / "frontend/pages/mrms/mrms.html").read_text(encoding="utf-8")

    assert "scrubber.setFrames(frames, { index: frames.length - 1 })" in page
    assert "const wasAtNewest = currentIndex === frames.length - 1;" in page
    assert "Loading newest frame…" in page
    assert "mrms-page.js?v=20260826i" in markup


def test_satellite_requests_selected_newest_frame_before_neighbor_priming() -> None:
    page = (ROOT / "frontend/pages/satellite/satellite-page.js").read_text(
        encoding="utf-8"
    )

    assert "const nextIndex = frameIndexForReload(frames, preserveFrameKey);" in page
    assert "let displayed = await showFrame(nextIndex" in page
    assert "animator.primeLayers(nextIndex)" not in page
    assert "Newest frame requested first" in page
    assert "cached tiles); tiles fill as they render" not in page


def test_channel14_is_registered_for_the_platforms_that_offer_it() -> None:
    config = (ROOT / "config/satellite_v2_config.py").read_text(encoding="utf-8")

    assert '"Channel14",' in config.split("SATELLITE_V2_DASHBOARD_PRODUCTS", 1)[1]
    assert normalize_channel("Channel14") == "Channel14"
    assert "Channel14" in fci_supported_products()
    assert "Channel14" in seviri_supported_products()


def test_satellite_ready_requires_a_visible_tile_event() -> None:
    page = (ROOT / "frontend/pages/satellite/satellite-page.js").read_text(
        encoding="utf-8"
    )
    animator = (ROOT / "frontend/pages/satellite/satellite-anim.js").read_text(
        encoding="utf-8"
    )

    assert "updateState: false" in page
    assert "onFrameVisible(frameKey)" in page
    assert "layer.on('tileload', () => reportFrameVisible(layer, frameKey))" in animator
    assert "activeLayer !== layer" in animator
    assert "displayed ? 'Ready'" not in page


def test_satellite_zoom_keeps_integer_tiles_and_newest_frame_priority() -> None:
    page = (ROOT / "frontend/pages/satellite/satellite-page.js").read_text(
        encoding="utf-8"
    )
    animator = (ROOT / "frontend/pages/satellite/satellite-anim.js").read_text(
        encoding="utf-8"
    )

    assert "mapCore.map.options.zoomSnap = 1;" in page
    assert "mapCore.map.options.zoomDelta = 1;" in page
    assert "animator.prepareForZoom();" in page
    assert "Math.max(0, Math.round(configuredZoom))" in animator
    assert "function prepareForZoom()" in animator
    assert (
        "if (layer !== activeLayer && map.hasLayer(layer)) map.removeLayer(layer);"
        in animator
    )


def test_satellite_playback_retains_ready_layers_with_bounded_live_prefetch() -> None:
    page = (ROOT / "frontend/pages/satellite/satellite-page.js").read_text(
        encoding="utf-8"
    )
    animator = (ROOT / "frontend/pages/satellite/satellite-anim.js").read_text(
        encoding="utf-8"
    )
    assert "awaitFrameOnPlay: true" in page
    assert "waitForVisibleTile: scrubber.isPlaying()" in page
    assert "waitForLayerVisible" in animator
    assert "layer.on('tileload', onTileLoad);" in animator
    assert "waitForTiles: scrubber.isPlaying()" not in page
    assert "const PREFETCH_AHEAD_FRAMES = 2;" in animator
    assert "const PREFETCH_BEHIND_FRAMES = 1;" in animator
    assert "{ renderLive: true, renderNeighbors: false }" in animator
    assert "prefetchQueue = [];" in animator
    assert "const renderNeighbors = options?.renderNeighbors === true;" in animator
    assert "keepBuffer: 1" in animator
    assert "Current-frame delivery always wins" in animator
    assert "visibleFrameKey = String(frameKey || '')" in page
    assert "visibleFrameKey !== selectedFrameKey" in page
    assert "if (prevLayer)" in animator
    assert "ready = await waitForLayerReady(nextLayer" in animator
    assert "Keep the currently visible frame in place" in animator
    assert "if (shouldRetainLayers()" in animator
    assert "&& layerReadyForSwap(layer, map.getZoom()))" in animator
    assert "layer.setOpacity(0);" in animator
    assert "the established no-flash animation contract" in animator
    assert "if (map.hasLayer(layer)) map.removeLayer(layer);" in animator
    assert "hotFrameIndexes" not in animator


def test_himawari_target_selection_uses_the_current_target_bounds() -> None:
    page = (ROOT / "frontend/pages/satellite/satellite-page.js").read_text(
        encoding="utf-8"
    )

    assert "'himawari9:Target': 'himawari-target-current'" in page
    assert "presetKey !== 'himawari-target-current'" in page
    assert "/api/satellite-v2/frame-bounds?" in page


def test_fresh_satellite_catalog_is_chronological_with_newest_last(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(catalog, "count_frame_tiles", lambda *_args: {})
    monkeypatch.setattr(catalog, "sample_frame_tiles", lambda *_args: [])
    monkeypatch.setattr(catalog, "atomic_write_json", lambda *_args: None)
    frames = [
        SimpleNamespace(
            frame_key="20260725T020000Z",
            timestamp_utc="2026-07-25T02:00:00Z",
            provider="test",
            source_key="newest",
            source_url="test://newest",
            source_keys={},
            source_urls={},
            file_sizes={},
        ),
        SimpleNamespace(
            frame_key="20260725T010000Z",
            timestamp_utc="2026-07-25T01:00:00Z",
            provider="test",
            source_key="oldest",
            source_url="test://oldest",
            source_keys={},
            source_urls={},
            file_sizes={},
        ),
    ]

    payload = catalog.build_catalog(
        str(tmp_path),
        "goes19",
        "CONUS",
        "Channel13",
        hours=2,
        max_frames=2,
        list_frames_fn=lambda **_kwargs: frames,
    )

    assert [frame["frame_key"] for frame in payload["frames"]] == [
        "20260725T010000Z",
        "20260725T020000Z",
    ]


def test_satellite_catalog_lookback_anchors_to_latest_delayed_frame(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(catalog, "count_frame_tiles", lambda *_args: {})
    monkeypatch.setattr(catalog, "sample_frame_tiles", lambda *_args: [])
    monkeypatch.setattr(catalog, "atomic_write_json", lambda *_args: None)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    frames = []
    for minutes_old in (115, 100, 85, 70, 55, 40):
        frame_time = now - timedelta(minutes=minutes_old)
        frame_key = frame_time.strftime("%Y%m%dT%H%M%SZ")
        frames.append(
            SimpleNamespace(
                frame_key=frame_key,
                timestamp_utc=frame_time.isoformat().replace("+00:00", "Z"),
                provider="test",
                source_key=frame_key,
                source_url=f"test://{frame_key}",
                source_keys={},
                source_urls={},
                file_sizes={},
            )
        )

    fresh = catalog.build_catalog(
        str(tmp_path),
        "meteosat12",
        "FullDisk",
        "NighttimeMicrophysics",
        hours=1,
        max_frames=6,
        list_frames_fn=lambda **_kwargs: frames,
    )
    cached = catalog._catalog_for_request(
        {
            **fresh,
            "frames": [
                {
                    "frame_key": frame.frame_key,
                    "timestamp_utc": frame.timestamp_utc,
                }
                for frame in frames
            ],
        },
        hours=1,
        max_frames=6,
    )

    expected_keys = [frame.frame_key for frame in frames[1:]]
    assert [frame["frame_key"] for frame in fresh["frames"]] == expected_keys
    assert [frame["frame_key"] for frame in cached["frames"]] == expected_keys


def test_global_timestamp_has_independent_data_state_line() -> None:
    script = (ROOT / "frontend/core/status.js").read_text(encoding="utf-8")
    styles = (ROOT / "frontend/core/core.css").read_text(encoding="utf-8")

    assert "setDataState(value, tone = '')" in script
    assert "core-global-timestamp-state" in script
    assert "info.updateState !== false" in script
    assert "Loading…" in script
    assert 'data-state-tone="loading"' in styles
    assert "core-status-pulse" in styles


def test_all_pages_receive_the_shared_timestamp_state_assets() -> None:
    status = (ROOT / "frontend/core/status.js").read_text(encoding="utf-8")
    assert "info.source" not in status
    assert "provider, source" not in status

    page_entries = {
        "alerts": "alerts-page.js",
        "drought": "drought-page.js",
        "mrms": "mrms-page.js",
        "radar": "radar-page.js",
        "rtma": "rtma-page.js",
        "satellite": "satellite-page.js",
        "spc": "spc-page.js",
        "surface": "surface-page.js",
        "tropical": "tropical-app.js",
        "water": "water-app.js",
        "workspace": "workspace-app.js",
        "wpc": "wpc-page.js",
    }
    for page_name, entry_name in page_entries.items():
        page_dir = ROOT / "frontend/pages" / page_name
        markup = (page_dir / f"{page_name}.html").read_text(encoding="utf-8")
        script = (page_dir / entry_name).read_text(encoding="utf-8")
        assert "core.css?v=20260826e" in markup
        assert f"/frontend/pages/{page_name}/{entry_name}?v=" in markup
        assert "status.js?v=20260808a" in script
        assert f"source: byId('{page_name}-source')" not in script
