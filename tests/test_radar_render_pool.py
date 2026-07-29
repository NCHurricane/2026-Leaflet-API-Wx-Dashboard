from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from workers import radar_live_worker as worker


def test_pool_owner_is_lazy_and_reuses_one_pool():
    pool = MagicMock()
    pool.starmap.side_effect = [["first"], ["second"]]

    with patch.object(worker.multiprocessing, "Pool", return_value=pool) as create:
        with worker._radar_render_pool_owner(processes=3) as owner:
            create.assert_not_called()
            assert owner.starmap(str, [(1,)]) == ["first"]
            assert owner.starmap(str, [(2,)]) == ["second"]
            assert owner.creation_count == 1
            assert owner.render_batches == 2

    create.assert_called_once_with(processes=3)
    pool.close.assert_called_once_with()
    pool.join.assert_called_once_with()
    pool.terminate.assert_not_called()


def test_pool_owner_terminates_workers_after_failure():
    pool = MagicMock()

    with patch.object(worker.multiprocessing, "Pool", return_value=pool):
        with pytest.raises(RuntimeError, match="failed batch"):
            with worker._radar_render_pool_owner(processes=2) as owner:
                owner.start()
                raise RuntimeError("failed batch")

    pool.terminate.assert_called_once_with()
    pool.join.assert_called_once_with()
    pool.close.assert_not_called()


def test_scheduled_run_passes_one_external_pool_to_every_batch():
    render_pool = object()
    radar_utils = SimpleNamespace(__name__="radar.radar_nodd_utils")
    products = {
        "L3_N0B": {"level": "Level 3"},
        "L3_N0G": {"level": "Level 3"},
    }

    with (
        patch.object(worker, "LIVE_RADAR_SITES", ("KGSP",)),
        patch.object(worker, "LIVE_RADAR_PRODUCTS", products),
        patch.object(worker, "is_cache_fresh", return_value=False),
        patch.object(worker, "_resolve_radar_data_utils", return_value=radar_utils),
        patch.object(worker, "_render_site_product", return_value=0) as render,
        patch.object(worker, "mark_run_complete"),
    ):
        worker._run_radar_live_worker_unbounded(
            force=True,
            render_pool=render_pool,
        )

    assert render.call_count == 2
    assert all(
        call.kwargs["render_pool"] is render_pool for call in render.call_args_list
    )


def test_site_product_run_passes_external_pool_to_render_batch():
    render_pool = object()
    radar_utils = SimpleNamespace(__name__="radar.radar_nodd_utils")

    with (
        patch.object(worker, "_resolve_radar_data_utils", return_value=radar_utils),
        patch.object(worker, "_render_site_product", return_value=4) as render,
        patch.object(worker, "mark_run_complete"),
    ):
        cached = worker._run_radar_live_site_product_unbounded(
            "KGSP",
            "L3_N0B",
            render_pool=render_pool,
        )

    assert cached == 4
    assert render.call_args.kwargs["render_pool"] is render_pool


def test_response_critical_single_frame_does_not_start_pool():
    with (
        patch(
            "app_core.render_budget.heavy_render_slot",
            return_value=nullcontext(),
        ),
        patch.object(
            worker,
            "_run_radar_live_site_product_unbounded",
            return_value=1,
        ) as run,
        patch.object(worker.multiprocessing, "Pool") as create,
    ):
        cached = worker.run_radar_live_site_product(
            "KGSP",
            "L3_N0B",
            latest_only=True,
            max_render_frames=1,
        )

    assert cached == 1
    create.assert_not_called()
    assert isinstance(
        run.call_args.kwargs["render_pool"],
        worker._RadarRenderPoolOwner,
    )
