from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app_core.atomic_io import atomic_write_json
from app_core.refresh_coordinator import (
    RefreshCoordinator,
    RefreshPolicy,
    validate_single_process_configuration,
)


def _coordinator(**kwargs) -> RefreshCoordinator:
    coordinator = RefreshCoordinator(
        max_workers=kwargs.pop("max_workers", 2),
        max_queued=kwargs.pop("max_queued", 8),
        maintenance_interval_seconds=kwargs.pop(
            "maintenance_interval_seconds", 0.01
        ),
        random_uniform=lambda _start, _end: 0.0,
        **kwargs,
    )
    coordinator.register_policy(
        RefreshPolicy(
            provider="test",
            min_request_interval=0,
            max_concurrency=2,
            base_backoff_seconds=0.02,
            max_backoff_seconds=0.05,
        )
    )
    return coordinator


def test_ten_simultaneous_submissions_run_one_refresh():
    coordinator = _coordinator()
    started = threading.Event()
    release = threading.Event()
    calls = []

    def refresh():
        calls.append("run")
        started.set()
        assert release.wait(timeout=2)

    coordinator.start()
    try:
        with ThreadPoolExecutor(max_workers=10) as callers:
            results = list(
                callers.map(
                    lambda _index: coordinator.submit(
                        key=("test", "same-cold-key"),
                        provider="test",
                        function=refresh,
                    ),
                    range(10),
                )
            )
        assert started.wait(timeout=1)
        assert sum(result.accepted for result in results) == 1
        release.set()
        assert coordinator.wait_for_idle(timeout=2)
        assert calls == ["run"]
        assert coordinator.describe(("test", "same-cold-key"))["status"] == "succeeded"
    finally:
        release.set()
        coordinator.stop()


def test_failed_refresh_enters_backoff_before_retry():
    coordinator = _coordinator()
    calls = []

    def fail():
        calls.append("run")
        raise RuntimeError("signed URL must not reach state")

    coordinator.start()
    try:
        first = coordinator.submit(
            key=("test", "failure"),
            provider="test",
            function=fail,
        )
        assert first.accepted
        assert coordinator.wait_for_idle(timeout=1)
        state = coordinator.describe(("test", "failure"))
        assert state["status"] == "backoff"
        assert state["error_type"] == "RuntimeError"
        assert "signed" not in json.dumps(state)

        blocked = coordinator.submit(
            key=("test", "failure"),
            provider="test",
            function=fail,
        )
        assert not blocked.accepted
        assert blocked.status == "backoff"
        assert calls == ["run"]

        time.sleep(0.03)
        assert coordinator.describe(("test", "failure"))["status"] == "failed"
        retry = coordinator.submit(
            key=("test", "failure"),
            provider="test",
            function=lambda: calls.append("retry"),
        )
        assert retry.accepted
        assert coordinator.wait_for_idle(timeout=1)
        assert calls == ["run", "retry"]
    finally:
        coordinator.stop()


def test_bounded_queue_rejects_excess_distinct_work():
    coordinator = _coordinator(max_workers=1, max_queued=1)
    release = threading.Event()

    def wait():
        assert release.wait(timeout=2)

    coordinator.start()
    try:
        first = coordinator.submit(
            key=("test", "one"), provider="test", function=wait
        )
        second = coordinator.submit(
            key=("test", "two"), provider="test", function=lambda: None
        )
        third = coordinator.submit(
            key=("test", "three"), provider="test", function=lambda: None
        )
        assert first.accepted
        assert second.accepted
        assert not third.accepted
        assert third.status == "failed"
    finally:
        release.set()
        coordinator.stop()


def test_provider_policy_serializes_and_spaces_refresh_starts():
    coordinator = _coordinator()
    coordinator.register_policy(
        RefreshPolicy(
            provider="paced",
            min_request_interval=0.04,
            max_concurrency=1,
        )
    )
    starts = []
    coordinator.start()
    try:
        for key in ("one", "two"):
            result = coordinator.submit(
                key=("paced", key),
                provider="paced",
                function=lambda: starts.append(time.monotonic()),
            )
            assert result.accepted
        assert coordinator.wait_for_idle(timeout=1)
        assert len(starts) == 2
        assert starts[1] - starts[0] >= 0.035
    finally:
        coordinator.stop()


def test_success_interval_returns_current_without_requeueing():
    coordinator = _coordinator()
    calls = []
    coordinator.start()
    try:
        first = coordinator.submit(
            key=("paced", "selected-product"),
            provider="test",
            function=lambda: calls.append("run"),
            min_success_interval_seconds=60,
        )
        assert first.accepted
        assert coordinator.wait_for_idle(timeout=1)

        current = coordinator.submit(
            key=("paced", "selected-product"),
            provider="test",
            function=lambda: calls.append("duplicate"),
            min_success_interval_seconds=60,
        )

        assert not current.accepted
        assert current.status == "current"
        assert 0 < current.retry_after_seconds <= 60
        assert calls == ["run"]
    finally:
        coordinator.stop()


def test_periodic_job_runs_without_request_presence():
    coordinator = _coordinator(maintenance_interval_seconds=0.005)
    ran = threading.Event()
    coordinator.register_periodic(
        key=("maintenance", "test"),
        provider="test",
        interval_seconds=60,
        initial_delay_seconds=0,
        function=ran.set,
    )

    coordinator.start()
    try:
        assert ran.wait(timeout=1)
        assert coordinator.wait_for_idle(timeout=1)
        assert coordinator.describe(("maintenance", "test"))["status"] == "succeeded"
    finally:
        coordinator.stop()


def test_presence_lease_is_bounded():
    coordinator = _coordinator()
    coordinator.record_presence(
        key=("test", "active-page"),
        provider="test",
        lease_seconds=0.02,
    )

    state = coordinator.describe(("test", "active-page"))
    assert state["status"] == "idle"
    assert state["started_at"] is None
    assert state["last_success_at"] is None
    assert coordinator.is_lease_active(("test", "active-page"))
    time.sleep(0.03)
    assert not coordinator.is_lease_active(("test", "active-page"))


def test_presence_job_repeats_only_while_lease_is_active():
    coordinator = _coordinator(maintenance_interval_seconds=0.005)
    calls = []
    coordinator.start()
    try:
        submission = coordinator.activate_presence_job(
            key=("test", "active-product"),
            provider="test",
            interval_seconds=0.02,
            lease_seconds=0.07,
            function=lambda: calls.append(time.monotonic()),
        )
        assert submission.accepted
        deadline = time.monotonic() + 1
        while len(calls) < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert len(calls) >= 2

        time.sleep(0.09)
        calls_after_expiry = len(calls)
        time.sleep(0.05)
        assert len(calls) == calls_after_expiry
        assert ["test", "active-product"] not in coordinator.snapshot()["presence_jobs"]
    finally:
        coordinator.stop()


def test_atomic_publish_keeps_previous_file_during_graceful_shutdown(
    tmp_path, monkeypatch
):
    destination = tmp_path / "cache.json"
    atomic_write_json(destination, {"generation": "old"})
    replace_started = threading.Event()
    allow_replace = threading.Event()
    real_replace = os.replace

    def blocked_replace(source, target):
        replace_started.set()
        assert allow_replace.wait(timeout=2)
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", blocked_replace)
    coordinator = _coordinator(max_workers=1)
    coordinator.start()
    coordinator.submit(
        key=("test", "atomic"),
        provider="test",
        function=lambda: atomic_write_json(destination, {"generation": "new"}),
    )
    assert replace_started.wait(timeout=1)

    stopped = threading.Event()
    shutdown_thread = threading.Thread(
        target=lambda: (coordinator.stop(wait=True), stopped.set())
    )
    shutdown_thread.start()
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "generation": "old"
    }
    assert not stopped.wait(timeout=0.05)

    allow_replace.set()
    shutdown_thread.join(timeout=2)
    assert stopped.is_set()
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "generation": "new"
    }


def test_multi_process_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    with pytest.raises(RuntimeError, match="supports one application process"):
        validate_single_process_configuration()
