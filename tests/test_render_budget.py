from concurrent.futures import ThreadPoolExecutor
import threading
import time

from app_core import render_budget


def _run_slot(weight, entered, release, results):
    with render_budget.satellite_render_slot(weight) as acquired:
        results.append(acquired)
        if acquired:
            entered.set()
            assert release.wait(timeout=2)


def test_satellite_budget_admits_work_that_fits_concurrently(monkeypatch):
    monkeypatch.setattr(
        render_budget, "_SATELLITE_RENDER_BUDGET", render_budget._ByteBudget(100)
    )
    release = threading.Event()
    entered_a = threading.Event()
    entered_b = threading.Event()
    results = []

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_run_slot, 40, entered_a, release, results)
        second = pool.submit(_run_slot, 40, entered_b, release, results)
        assert entered_a.wait(timeout=1)
        assert entered_b.wait(timeout=1)
        snapshot = render_budget.satellite_render_budget_snapshot()
        assert snapshot["active"] == 2
        assert snapshot["in_flight_bytes"] == 80
        release.set()
        first.result(timeout=2)
        second.result(timeout=2)

    assert results == [True, True]


def test_satellite_budget_queues_work_that_would_exceed_capacity(monkeypatch):
    monkeypatch.setattr(
        render_budget, "_SATELLITE_RENDER_BUDGET", render_budget._ByteBudget(100)
    )
    release_first = threading.Event()
    release_second = threading.Event()
    first_entered = threading.Event()
    second_entered = threading.Event()
    results = []

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            _run_slot, 70, first_entered, release_first, results
        )
        assert first_entered.wait(timeout=1)
        second = pool.submit(
            _run_slot, 40, second_entered, release_second, results
        )
        time.sleep(0.05)
        assert not second_entered.is_set()
        assert render_budget.satellite_render_budget_snapshot()["queued"] == 1
        release_first.set()
        assert second_entered.wait(timeout=1)
        release_second.set()
        first.result(timeout=2)
        second.result(timeout=2)

    assert results == [True, True]


def test_oversized_satellite_render_runs_alone(monkeypatch):
    monkeypatch.setattr(
        render_budget, "_SATELLITE_RENDER_BUDGET", render_budget._ByteBudget(100)
    )
    release_oversized = threading.Event()
    release_small = threading.Event()
    oversized_entered = threading.Event()
    small_entered = threading.Event()
    results = []

    with ThreadPoolExecutor(max_workers=2) as pool:
        oversized = pool.submit(
            _run_slot, 150, oversized_entered, release_oversized, results
        )
        assert oversized_entered.wait(timeout=1)
        assert render_budget.satellite_render_budget_snapshot()["in_flight_bytes"] == 150
        small = pool.submit(
            _run_slot, 1, small_entered, release_small, results
        )
        time.sleep(0.05)
        assert not small_entered.is_set()
        release_oversized.set()
        assert small_entered.wait(timeout=1)
        release_small.set()
        oversized.result(timeout=2)
        small.result(timeout=2)

    assert results == [True, True]


def test_cancelled_satellite_waiter_releases_its_queue_position(monkeypatch):
    monkeypatch.setattr(
        render_budget, "_SATELLITE_RENDER_BUDGET", render_budget._ByteBudget(100)
    )
    acquired, weight = render_budget._SATELLITE_RENDER_BUDGET.acquire(100)
    assert acquired
    keep_waiting = threading.Event()
    keep_waiting.set()

    def wait_then_cancel():
        with render_budget.satellite_render_slot(
            10, should_continue=keep_waiting.is_set
        ) as slot_acquired:
            return slot_acquired

    with ThreadPoolExecutor(max_workers=1) as pool:
        waiting = pool.submit(wait_then_cancel)
        deadline = time.monotonic() + 1
        while (
            render_budget.satellite_render_budget_snapshot()["queued"] != 1
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        keep_waiting.clear()
        assert waiting.result(timeout=1) is False

    assert render_budget.satellite_render_budget_snapshot()["queued"] == 0
    render_budget._SATELLITE_RENDER_BUDGET.release(weight)


def test_satellite_admission_is_independent_from_radar_heavy_slot(monkeypatch):
    monkeypatch.setattr(
        render_budget, "_SATELLITE_RENDER_BUDGET", render_budget._ByteBudget(100)
    )
    entered = threading.Event()
    release = threading.Event()
    results = []

    with render_budget.heavy_render_slot():
        with ThreadPoolExecutor(max_workers=1) as pool:
            satellite = pool.submit(_run_slot, 50, entered, release, results)
            assert entered.wait(timeout=1)
            release.set()
            satellite.result(timeout=2)

    assert results == [True]
