from __future__ import annotations

from datetime import datetime, timedelta, timezone

from satellite_v2 import meteosat_prefetch_worker, meteosat_tile_worker
from satellite_v2.cache import tile_path
from satellite_v2.models import SourceFrame


def test_meteosat_disk_bounds_follow_each_platform_longitude():
    assert meteosat_tile_worker.meteosat_disk_bounds("meteosat12") == {
        "west": -81.0,
        "south": -80.0,
        "east": 81.0,
        "north": 80.0,
    }
    assert meteosat_tile_worker.meteosat_disk_bounds("meteosat9") == {
        "west": -35.5,
        "south": -80.0,
        "east": 126.5,
        "north": 80.0,
    }


def test_selected_meteosat_warmer_uses_newest_frames_product_and_reused_pool(
    monkeypatch,
):
    frames = [
        {"frame_key": "oldest"},
        {"frame_key": "middle"},
        {"frame_key": "newest"},
    ]
    catalog_calls = []
    warm_calls = []
    pool = object()

    def fake_catalog(**kwargs):
        catalog_calls.append(kwargs)
        return {"frames": frames}

    def fake_warm(**kwargs):
        warm_calls.append(kwargs)
        return {
            "rendered": 1,
            "skipped": 0,
            "errors": 0,
            "invalid": 0,
            "cancelled": 0,
        }

    monkeypatch.setattr(meteosat_tile_worker, "build_catalog", fake_catalog)
    monkeypatch.setattr(meteosat_tile_worker, "warm_frame_tiles_from_canvas", fake_warm)
    monkeypatch.setattr(meteosat_tile_worker, "_get_tile_pool", lambda: pool)

    result = meteosat_tile_worker.run_selected_meteosat_tile_warmer(
        sat_id="meteosat9",
        sector="FULLDISK",
        channel="Channel08RAMSDIS",
        should_continue=lambda: True,
        wait_until_ready=lambda: True,
    )

    assert [call["frame"]["frame_key"] for call in warm_calls] == [
        "newest",
        "middle",
    ]
    assert all(call["channel_key"] == "Channel08RAMSDIS" for call in warm_calls)
    assert all(call["zooms"] == tuple(range(1, 7)) for call in warm_calls)
    assert all(call["pool"] is pool for call in warm_calls)
    assert all(call["tile_bounds"]["east"] == 126.5 for call in warm_calls)
    assert result["frames"] == 2
    assert result["rendered"] == 2
    assert len(catalog_calls) == 2


def test_selected_meteosat_rss_warmer_uses_rss_tuned_tail_and_bounds(monkeypatch):
    frames = [{"frame_key": f"frame-{index}"} for index in range(6)]
    catalog_calls = []
    warm_calls = []
    pool = object()

    monkeypatch.setattr(
        meteosat_tile_worker,
        "build_catalog",
        lambda **kwargs: catalog_calls.append(kwargs) or {"frames": frames},
    )
    monkeypatch.setattr(
        meteosat_tile_worker,
        "warm_frame_tiles_from_canvas",
        lambda **kwargs: warm_calls.append(kwargs)
        or {
            "rendered": 1,
            "skipped": 0,
            "errors": 0,
            "invalid": 0,
            "cancelled": 0,
        },
    )
    monkeypatch.setattr(meteosat_tile_worker, "_get_tile_pool", lambda: pool)

    result = meteosat_tile_worker.run_selected_meteosat_tile_warmer(
        sat_id="meteosat11",
        sector="RSS",
        channel="Dust",
        should_continue=lambda: True,
        wait_until_ready=lambda: True,
    )

    assert [call["frame"]["frame_key"] for call in warm_calls] == [
        "frame-5",
        "frame-4",
        "frame-3",
        "frame-2",
    ]
    assert all(call["channel_key"] == "Dust" for call in warm_calls)
    assert all(call["zooms"] == (4, 5, 6, 7) for call in warm_calls)
    assert all(
        call["tile_bounds"]
        == {"west": -30.0, "south": 10.0, "east": 45.0, "north": 70.0}
        for call in warm_calls
    )
    assert result["frames"] == 4
    assert result["rendered"] == 4
    assert catalog_calls[0]["hours"] == 2
    assert len(catalog_calls) == 2


def test_rss_source_prefetch_does_not_walk_back_beyond_the_latest_tail(monkeypatch):
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    frames = [
        SourceFrame(
            frame_key=(now - timedelta(minutes=minutes_old)).strftime(
                "%Y%m%dT%H%M%SZ"
            ),
            timestamp_utc=(now - timedelta(minutes=minutes_old))
            .isoformat()
            .replace("+00:00", "Z"),
            provider="test",
            source_key=f"source-{minutes_old}",
            source_url=f"test://{minutes_old}",
        )
        for minutes_old in (25, 20, 15, 10, 5, 0)
    ]
    newest_keys = {frame.frame_key for frame in frames[-2:]}
    downloads = []
    monkeypatch.setattr(
        meteosat_prefetch_worker, "list_recent_frames", lambda **_kwargs: frames
    )
    monkeypatch.setattr(
        meteosat_prefetch_worker,
        "_frame_sources_cached",
        lambda _sat, _sector, frame: frame.frame_key in newest_keys,
    )
    monkeypatch.setattr(
        meteosat_prefetch_worker,
        "download_product_source_frames",
        lambda **kwargs: downloads.append(kwargs["frame"].frame_key),
    )
    monkeypatch.setattr(meteosat_prefetch_worker, "_prune_stale_sources", lambda *_args: 0)
    monkeypatch.setattr(meteosat_prefetch_worker, "_prune_stale_tiles", lambda *_args: 0)

    stats = meteosat_prefetch_worker._prefetch_one_job(
        "test-rss",
        "meteosat11",
        "RSS",
        "Channel13",
        newest_count=2,
        backfill_count=0,
        hours=2,
        max_frames=48,
        keep_hours=3,
        newest_only=True,
    )

    assert downloads == []
    assert stats["cached"] == 2


def test_meteosat_tile_pool_is_reused_and_shutdown(monkeypatch):
    pools = []

    class FakePool:
        def __init__(self, max_workers):
            self.max_workers = max_workers
            self.shutdown_calls = []
            pools.append(self)

        def shutdown(self, **kwargs):
            self.shutdown_calls.append(kwargs)

    monkeypatch.setattr(meteosat_tile_worker, "ProcessPoolExecutor", FakePool)
    monkeypatch.setattr(meteosat_tile_worker, "_TILE_POOL", None)

    first = meteosat_tile_worker._get_tile_pool()
    second = meteosat_tile_worker._get_tile_pool()
    meteosat_tile_worker.shutdown_meteosat_tile_pool()

    assert first is second
    assert len(pools) == 1
    assert pools[0].max_workers == 2
    assert pools[0].shutdown_calls == [{"wait": False, "cancel_futures": True}]


def test_meteosat_prune_removes_only_stale_current_version_tile_frames(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(meteosat_prefetch_worker, "_CACHE_ROOT", str(tmp_path))
    now = datetime.now(timezone.utc)
    old_frame = (now - timedelta(hours=8)).strftime("%Y%m%dT%H%M%SZ")
    current_frame = (now - timedelta(hours=1)).strftime("%Y%m%dT%H%M%SZ")
    old_tile = tile_path(
        tmp_path, "meteosat12", "FULLDISK", "Channel13", old_frame, 4, 1, 1
    )
    current_tile = tile_path(
        tmp_path, "meteosat12", "FULLDISK", "Channel13", current_frame, 4, 1, 1
    )
    old_tile.parent.mkdir(parents=True)
    current_tile.parent.mkdir(parents=True)
    old_tile.write_bytes(b"old")
    current_tile.write_bytes(b"current")

    pruned = meteosat_prefetch_worker._prune_stale_tiles(
        "meteosat12", "FULLDISK", 7
    )

    assert pruned == 1
    assert not old_tile.parents[2].exists()
    assert current_tile.exists()
