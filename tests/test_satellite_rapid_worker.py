from __future__ import annotations

from collections import Counter
from concurrent.futures import Future
from contextlib import contextmanager

from satellite_v2 import rapid_worker, tiler


class _RecordingPool:
    def __init__(self, max_workers=None):
        self.max_workers = max_workers
        self.tasks = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def submit(self, function, task):
        self.tasks.append((function, task))
        future = Future()
        future.set_result(
            {"rendered": 1, "skipped": 0, "errors": 0, "repaired": 0, "invalid": 0}
        )
        return future


def test_canvas_warm_uses_supplied_pool(tmp_path, monkeypatch):
    pool = _RecordingPool()
    monkeypatch.setattr(
        tiler,
        "planning_tile_coords",
        lambda _sector, zoom, **_kwargs: [(zoom, zoom)],
    )
    monkeypatch.setattr(
        tiler,
        "download_product_source_frames",
        lambda *_args: {"Channel13": tmp_path / "source.nc"},
    )

    stats = tiler.warm_frame_tiles_from_canvas(
        cache_root=tmp_path,
        sat_id="goes19",
        sector="MESO1",
        channel_key="Channel13",
        frame={"frame_key": "frame-a"},
        zooms=(7, 8),
        render_workers=2,
        pool=pool,
    )

    assert stats["rendered"] == 2
    assert [task[1]["z"] for task in pool.tasks] == [7, 8]


def test_canvas_warm_stops_scheduling_zooms_when_live_work_arrives(
    tmp_path, monkeypatch
):
    pool = _RecordingPool()
    ready = iter((True, True, False))
    monkeypatch.setattr(
        tiler,
        "planning_tile_coords",
        lambda _sector, zoom, **_kwargs: [(zoom, zoom)],
    )
    monkeypatch.setattr(
        tiler,
        "download_product_source_frames",
        lambda *_args: {"Channel13": tmp_path / "source.nc"},
    )

    stats = tiler.warm_frame_tiles_from_canvas(
        cache_root=tmp_path,
        sat_id="meteosat9",
        sector="FULLDISK",
        channel_key="Channel13",
        frame={"frame_key": "frame-a"},
        zooms=(4, 5, 6),
        render_workers=1,
        pool=pool,
        wait_until_ready=lambda: next(ready),
    )

    assert [task[1]["z"] for task in pool.tasks] == [4]
    assert stats["rendered"] == 1
    assert stats["cancelled"] == 1


def test_rapid_worker_reuses_one_pool_for_all_jobs(monkeypatch):
    pools = []
    seen_pools = []

    def make_pool(max_workers):
        pool = _RecordingPool(max_workers=max_workers)
        pools.append(pool)
        return pool

    @contextmanager
    def acquired_lock(_worker_name):
        yield True

    def fake_warm(*args):
        seen_pools.append(args[-2])
        return {"frames": 1, "rendered": 1, "skipped": 0, "errors": 0}

    monkeypatch.setattr(rapid_worker, "ProcessPoolExecutor", make_pool)
    monkeypatch.setattr(rapid_worker, "_worker_lock", acquired_lock)
    monkeypatch.setattr(rapid_worker, "_warm_one_job", fake_warm)
    monkeypatch.setattr(rapid_worker, "mark_run_complete", lambda _name: None)

    totals = rapid_worker.run_satellite_v2_rapid_worker(
        force=True,
        jobs=(("goes19", "MESO1"), ("goes19", "MESO2")),
        products=("Channel13",),
        frames=1,
        tile_workers=2,
        worker_name="test-rapid",
    )

    assert len(pools) == 1
    assert pools[0].max_workers == 2
    assert seen_pools == [pools[0], pools[0]]
    assert totals["jobs"] == 2


def test_single_worker_runs_without_process_pool(monkeypatch):
    @contextmanager
    def acquired_lock(_worker_name):
        yield True

    seen_pools = []
    monkeypatch.setattr(rapid_worker, "_worker_lock", acquired_lock)
    monkeypatch.setattr(
        rapid_worker,
        "ProcessPoolExecutor",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("single-worker accelerator should not spawn a process")
        ),
    )
    monkeypatch.setattr(
        rapid_worker,
        "_warm_one_job",
        lambda *args: seen_pools.append(args[-2])
        or {"frames": 1, "rendered": 1, "skipped": 0, "errors": 0},
    )
    monkeypatch.setattr(rapid_worker, "mark_run_complete", lambda _name: None)

    rapid_worker.run_satellite_v2_rapid_worker(
        force=True,
        jobs=(("meteosat11", "RSS"),),
        products=("Channel13",),
        frames=1,
        tile_workers=1,
        worker_name="test-rapid-single",
    )

    assert seen_pools == [None]


def test_warm_job_stops_before_next_frame_when_selection_changes(monkeypatch):
    frames = [{"frame_key": "older"}, {"frame_key": "newer"}]
    warmed = []
    active = iter((True, False))
    monkeypatch.setattr(
        rapid_worker, "build_catalog", lambda **_kwargs: {"frames": frames}
    )
    monkeypatch.setattr(
        rapid_worker,
        "warm_frame_tiles_from_canvas",
        lambda **kwargs: warmed.append(kwargs["frame"]["frame_key"])
        or {"rendered": 1, "skipped": 0, "errors": 0, "invalid": 0},
    )

    stats = rapid_worker._warm_one_job(
        "test-rapid",
        "meteosat11",
        "RSS",
        "Channel13",
        2,
        2,
        10,
        1,
        0,
        None,
        lambda: next(active),
    )

    assert warmed == ["newer"]
    assert stats["frames"] == 1


def test_noop_warm_job_skips_trailing_catalog_rebuild(monkeypatch):
    catalog_calls = []
    frame = {"frame_key": "frame-a"}

    def fake_catalog(**kwargs):
        catalog_calls.append(kwargs)
        return {"frames": [frame]}

    monkeypatch.setattr(rapid_worker, "build_catalog", fake_catalog)
    monkeypatch.setattr(
        rapid_worker,
        "warm_frame_tiles_from_canvas",
        lambda **_kwargs: {
            "rendered": 0,
            "skipped": 2,
            "errors": 0,
            "invalid": 0,
        },
    )

    stats = rapid_worker._warm_one_job(
        "test-rapid",
        "goes19",
        "MESO1",
        "Channel13",
        1,
        2,
        10,
        2,
        0,
        _RecordingPool(),
    )

    assert stats["rendered"] == 0
    assert len(catalog_calls) == 1


def test_changed_warm_job_refreshes_catalog(monkeypatch):
    calls = Counter()
    frame = {"frame_key": "frame-a"}

    def fake_catalog(**_kwargs):
        calls["catalog"] += 1
        return {"frames": [frame]}

    monkeypatch.setattr(rapid_worker, "build_catalog", fake_catalog)
    monkeypatch.setattr(
        rapid_worker,
        "warm_frame_tiles_from_canvas",
        lambda **_kwargs: {
            "rendered": 1,
            "skipped": 0,
            "errors": 0,
            "invalid": 0,
        },
    )

    rapid_worker._warm_one_job(
        "test-rapid",
        "goes19",
        "MESO1",
        "Channel13",
        1,
        2,
        10,
        2,
        0,
        _RecordingPool(),
    )

    assert calls["catalog"] == 2
