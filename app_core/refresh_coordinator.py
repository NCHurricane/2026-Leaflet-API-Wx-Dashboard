"""Bounded application-owned refresh coordination.

Phase 1 intentionally supports one application process. Persistent leases and
provider budgets are required before multi-process servers or legacy task
workers can safely share refresh ownership.
"""

from __future__ import annotations

import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

RefreshKey = tuple[str, ...]


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _utc_iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class RefreshPolicy:
    provider: str
    min_request_interval: float = 0.0
    max_concurrency: int = 1
    base_backoff_seconds: float = 2.0
    max_backoff_seconds: float = 300.0
    presence_required: bool = False
    stale_if_error: bool = True


@dataclass
class RefreshState:
    key: RefreshKey
    provider: str
    status: str
    queued_at: float
    started_at: float | None = None
    finished_at: float | None = None
    last_success_at: float | None = None
    source_timestamp: str | None = None
    retry_at: float | None = None
    failure_count: int = 0
    error_type: str | None = None
    lease_expires_at: float | None = None

    def as_dict(self, now: float | None = None) -> dict[str, Any]:
        current_time = time.time() if now is None else now
        retry_after = (
            max(0.0, self.retry_at - current_time) if self.retry_at else None
        )
        return {
            "key": list(self.key),
            "provider": self.provider,
            "status": self.status,
            "queued_at": _utc_iso(self.queued_at),
            "started_at": _utc_iso(self.started_at),
            "finished_at": _utc_iso(self.finished_at),
            "last_success_at": _utc_iso(self.last_success_at),
            "source_timestamp": self.source_timestamp,
            "retry_after_seconds": (
                round(retry_after, 3) if retry_after is not None else None
            ),
            "failure_count": self.failure_count,
            "error_type": self.error_type,
            "lease_expires_at": _utc_iso(self.lease_expires_at),
        }


@dataclass(frozen=True)
class Submission:
    accepted: bool
    status: str
    retry_after_seconds: float | None = None


@dataclass
class _PeriodicJob:
    key: RefreshKey
    provider: str
    interval_seconds: float
    next_run_at: float
    function: Callable[[], object]


@dataclass
class _PresenceJob:
    key: RefreshKey
    provider: str
    interval_seconds: float
    next_run_at: float
    function: Callable[[], object]


class _CoordinatorStopping(RuntimeError):
    pass


class RefreshCoordinator:
    """Coordinate deduplicated refresh work through a bounded executor."""

    def __init__(
        self,
        *,
        max_workers: int = 4,
        max_queued: int = 32,
        state_retention_seconds: float = 24 * 60 * 60,
        maintenance_interval_seconds: float = 1.0,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._max_workers = max(1, max_workers)
        self._max_queued = max(1, max_queued)
        self._state_retention_seconds = max(1.0, state_retention_seconds)
        self._maintenance_interval_seconds = max(
            0.01, maintenance_interval_seconds
        )
        self._random_uniform = random_uniform
        self._lock = threading.RLock()
        self._idle_condition = threading.Condition(self._lock)
        self._stop_event = threading.Event()
        self._executor: ThreadPoolExecutor | None = None
        self._capacity: threading.BoundedSemaphore | None = None
        self._maintenance_thread: threading.Thread | None = None
        self._running = False
        self._active_jobs = 0
        self._policies: dict[str, RefreshPolicy] = {}
        self._provider_semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._provider_last_started: dict[str, float] = {}
        self._states: dict[RefreshKey, RefreshState] = {}
        self._periodic_jobs: dict[RefreshKey, _PeriodicJob] = {}
        self._presence_jobs: dict[RefreshKey, _PresenceJob] = {}

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def register_policy(self, policy: RefreshPolicy) -> None:
        provider = policy.provider.strip().lower()
        if not provider:
            raise ValueError("Refresh policy provider is required")
        normalized = RefreshPolicy(
            provider=provider,
            min_request_interval=max(0.0, policy.min_request_interval),
            max_concurrency=max(1, policy.max_concurrency),
            base_backoff_seconds=max(0.0, policy.base_backoff_seconds),
            max_backoff_seconds=max(
                policy.base_backoff_seconds, policy.max_backoff_seconds
            ),
            presence_required=policy.presence_required,
            stale_if_error=policy.stale_if_error,
        )
        with self._lock:
            self._policies[provider] = normalized
            self._provider_semaphores[provider] = threading.BoundedSemaphore(
                normalized.max_concurrency
            )

    def register_periodic(
        self,
        *,
        key: RefreshKey,
        provider: str,
        interval_seconds: float,
        function: Callable[[], object],
        initial_delay_seconds: float = 0.0,
    ) -> None:
        normalized_key = self._normalize_key(key)
        if interval_seconds <= 0:
            raise ValueError("Periodic interval must be positive")
        with self._lock:
            self._periodic_jobs[normalized_key] = _PeriodicJob(
                key=normalized_key,
                provider=provider.strip().lower(),
                interval_seconds=interval_seconds,
                next_run_at=time.monotonic() + max(0.0, initial_delay_seconds),
                function=function,
            )

    def activate_presence_job(
        self,
        *,
        key: RefreshKey,
        provider: str,
        interval_seconds: float,
        function: Callable[[], object],
        lease_seconds: float = 90.0,
        min_success_interval_seconds: float = 0.0,
        run_immediately: bool = True,
        initial_delay_seconds: float = 0.0,
    ) -> Submission:
        """Renew a lease and run one deduplicated job per interval while active."""
        normalized_key = self._normalize_key(key)
        if interval_seconds <= 0:
            raise ValueError("Presence job interval must be positive")
        now = time.monotonic()
        with self._lock:
            current = self._presence_jobs.get(normalized_key)
            next_run_at = (
                current.next_run_at
                if current is not None
                else now + max(0.0, float(initial_delay_seconds))
            )
            self._presence_jobs[normalized_key] = _PresenceJob(
                key=normalized_key,
                provider=provider.strip().lower(),
                interval_seconds=float(interval_seconds),
                next_run_at=next_run_at,
                function=function,
            )
        if not run_immediately:
            self.record_presence(
                key=normalized_key,
                provider=provider,
                lease_seconds=lease_seconds,
            )
            return Submission(
                False,
                "scheduled",
                max(0.0, next_run_at - time.monotonic()),
            )
        return self.submit(
            key=normalized_key,
            provider=provider,
            function=function,
            lease_seconds=lease_seconds,
            min_success_interval_seconds=min_success_interval_seconds,
        )

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._stop_event.clear()
            self._capacity = threading.BoundedSemaphore(
                self._max_workers + self._max_queued
            )
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="refresh-coordinator",
            )
            self._running = True
            self._maintenance_thread = threading.Thread(
                target=self._maintenance_loop,
                name="refresh-coordinator-maintenance",
                daemon=False,
            )
            maintenance_thread = self._maintenance_thread
        maintenance_thread.start()

    def stop(self, *, wait: bool = True) -> None:
        with self._lock:
            if not self._running and self._executor is None:
                return
            self._running = False
            self._stop_event.set()
            maintenance_thread = self._maintenance_thread
            executor = self._executor
            self._maintenance_thread = None
            self._executor = None
        if maintenance_thread is not None:
            maintenance_thread.join(timeout=2.0)
        if executor is not None:
            executor.shutdown(wait=wait, cancel_futures=False)
        with self._idle_condition:
            for state in self._states.values():
                if state.status == "queued":
                    state.status = "failed"
                    state.finished_at = time.time()
                    state.error_type = "CoordinatorStopped"
            self._idle_condition.notify_all()

    def submit(
        self,
        *,
        key: RefreshKey,
        provider: str,
        function: Callable[[], object],
        lease_seconds: float = 90.0,
        min_success_interval_seconds: float = 0.0,
    ) -> Submission:
        normalized_key = self._normalize_key(key)
        provider_key = provider.strip().lower()
        now = time.time()
        with self._lock:
            current = self._states.get(normalized_key)
            if current is not None and lease_seconds > 0:
                current.lease_expires_at = now + lease_seconds
            if not self._running or self._executor is None or self._capacity is None:
                return Submission(False, "stopped")
            if current is not None and current.status in {"queued", "running"}:
                return Submission(False, current.status)
            if (
                current is not None
                and current.last_success_at is not None
                and min_success_interval_seconds > 0
            ):
                retry_after = (
                    current.last_success_at
                    + min_success_interval_seconds
                    - now
                )
                if retry_after > 0:
                    return Submission(False, "current", retry_after)
            if (
                current is not None
                and current.status == "backoff"
                and current.retry_at is not None
                and current.retry_at > now
            ):
                return Submission(
                    False,
                    "backoff",
                    max(0.0, current.retry_at - now),
                )
            if not self._capacity.acquire(blocking=False):
                self._states[normalized_key] = RefreshState(
                    key=normalized_key,
                    provider=provider_key,
                    status="failed",
                    queued_at=now,
                    finished_at=now,
                    error_type="CoordinatorQueueFull",
                    lease_expires_at=(
                        now + lease_seconds if lease_seconds > 0 else None
                    ),
                )
                return Submission(False, "failed")

            state = current or RefreshState(
                key=normalized_key,
                provider=provider_key,
                status="queued",
                queued_at=now,
            )
            state.provider = provider_key
            state.status = "queued"
            state.queued_at = now
            state.started_at = None
            state.finished_at = None
            state.retry_at = None
            state.error_type = None
            if lease_seconds > 0:
                state.lease_expires_at = now + lease_seconds
            self._states[normalized_key] = state
            self._active_jobs += 1
            executor = self._executor
            capacity = self._capacity
            try:
                executor.submit(
                    self._execute,
                    normalized_key,
                    provider_key,
                    function,
                    capacity,
                )
            except Exception:
                self._active_jobs -= 1
                capacity.release()
                state.status = "failed"
                state.finished_at = time.time()
                state.error_type = "ExecutorUnavailable"
                self._idle_condition.notify_all()
                return Submission(False, "failed")
        return Submission(True, "queued")

    def record_presence(
        self,
        *,
        key: RefreshKey,
        provider: str,
        lease_seconds: float = 90.0,
    ) -> None:
        """Create or renew an active request lease without enqueueing work."""
        normalized_key = self._normalize_key(key)
        now = time.time()
        with self._lock:
            state = self._states.get(normalized_key)
            if state is None:
                state = RefreshState(
                    key=normalized_key,
                    provider=provider.strip().lower(),
                    status="idle",
                    queued_at=now,
                    finished_at=now,
                )
                self._states[normalized_key] = state
            state.lease_expires_at = now + max(0.0, lease_seconds)

    def is_lease_active(self, key: RefreshKey) -> bool:
        normalized_key = self._normalize_key(key)
        with self._lock:
            state = self._states.get(normalized_key)
            return bool(
                state
                and state.lease_expires_at
                and state.lease_expires_at > time.time()
            )

    def describe(self, key: RefreshKey) -> dict[str, Any] | None:
        normalized_key = self._normalize_key(key)
        with self._lock:
            self._expire_backoff_locked(time.time())
            state = self._states.get(normalized_key)
            return state.as_dict() if state is not None else None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = time.time()
            self._expire_backoff_locked(now)
            states = [
                state.as_dict(now)
                for _, state in sorted(self._states.items(), key=lambda item: item[0])
            ]
            policies = {
                provider: {
                    "min_request_interval": policy.min_request_interval,
                    "max_concurrency": policy.max_concurrency,
                    "presence_required": policy.presence_required,
                    "stale_if_error": policy.stale_if_error,
                }
                for provider, policy in sorted(self._policies.items())
            }
            return {
                "mode": "single_process",
                "running": self._running,
                "max_workers": self._max_workers,
                "max_queued": self._max_queued,
                "active_jobs": self._active_jobs,
                "policies": policies,
                "periodic_jobs": [
                    list(key) for key in sorted(self._periodic_jobs)
                ],
                "presence_jobs": [
                    list(key) for key in sorted(self._presence_jobs)
                ],
                "states": states,
            }

    def wait_for_idle(self, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        with self._idle_condition:
            while self._active_jobs:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._idle_condition.wait(timeout=remaining)
            return True

    @contextmanager
    def provider_budget(self, provider: str) -> Iterator[None]:
        """Apply a registered provider's shared concurrency and pace budget."""
        provider_key = provider.strip().lower()
        if not provider_key:
            raise ValueError("Provider is required")
        provider_semaphore = self._provider_semaphore(provider_key)
        acquired = False
        try:
            while not acquired:
                if self._stop_event.is_set():
                    raise _CoordinatorStopping
                acquired = provider_semaphore.acquire(timeout=0.1)
            self._wait_for_provider_budget(provider_key)
            yield
        finally:
            if acquired:
                provider_semaphore.release()

    def _execute(
        self,
        key: RefreshKey,
        provider: str,
        function: Callable[[], object],
        capacity: threading.BoundedSemaphore,
    ) -> None:
        provider_semaphore = self._provider_semaphore(provider)
        acquired_provider = False
        try:
            while not acquired_provider:
                if self._stop_event.is_set():
                    raise _CoordinatorStopping
                acquired_provider = provider_semaphore.acquire(timeout=0.1)
            self._wait_for_provider_budget(provider)
            with self._lock:
                state = self._states[key]
                state.status = "running"
                state.started_at = time.time()
            result = function()
            finished_at = time.time()
            source_timestamp = self._source_timestamp(result)
            with self._lock:
                state = self._states[key]
                state.status = "succeeded"
                state.finished_at = finished_at
                state.last_success_at = finished_at
                state.source_timestamp = source_timestamp
                state.retry_at = None
                state.failure_count = 0
                state.error_type = None
        except _CoordinatorStopping:
            with self._lock:
                state = self._states[key]
                state.status = "failed"
                state.finished_at = time.time()
                state.error_type = "CoordinatorStopped"
        except Exception as exc:
            finished_at = time.time()
            with self._lock:
                state = self._states[key]
                state.failure_count += 1
                policy = self._policy(provider)
                base_delay = min(
                    policy.max_backoff_seconds,
                    policy.base_backoff_seconds
                    * (2 ** max(0, state.failure_count - 1)),
                )
                jitter = self._random_uniform(0.0, max(0.0, base_delay * 0.2))
                state.status = "backoff"
                state.finished_at = finished_at
                state.retry_at = finished_at + base_delay + jitter
                state.error_type = type(exc).__name__
        finally:
            if acquired_provider:
                provider_semaphore.release()
            capacity.release()
            with self._idle_condition:
                self._active_jobs = max(0, self._active_jobs - 1)
                self._idle_condition.notify_all()

    def _wait_for_provider_budget(self, provider: str) -> None:
        policy = self._policy(provider)
        while True:
            if self._stop_event.is_set():
                raise _CoordinatorStopping
            with self._lock:
                last_started = self._provider_last_started.get(provider)
                remaining = (
                    0.0
                    if last_started is None
                    else policy.min_request_interval
                    - (time.monotonic() - last_started)
                )
                if remaining <= 0:
                    self._provider_last_started[provider] = time.monotonic()
                    return
            if self._stop_event.wait(min(remaining, 0.1)):
                raise _CoordinatorStopping

    def _maintenance_loop(self) -> None:
        while not self._stop_event.wait(self._maintenance_interval_seconds):
            now_monotonic = time.monotonic()
            due: list[_PeriodicJob] = []
            presence_due: list[_PresenceJob] = []
            with self._lock:
                now = time.time()
                self._expire_backoff_locked(now)
                self._prune_states_locked(now)
                for periodic_job in self._periodic_jobs.values():
                    if periodic_job.next_run_at <= now_monotonic:
                        periodic_job.next_run_at = (
                            now_monotonic + periodic_job.interval_seconds
                        )
                        due.append(periodic_job)
                expired_presence_keys = []
                for key, presence_job in self._presence_jobs.items():
                    state = self._states.get(key)
                    if (
                        state is None
                        or state.lease_expires_at is None
                        or state.lease_expires_at <= now
                    ):
                        expired_presence_keys.append(key)
                        continue
                    if presence_job.next_run_at <= now_monotonic:
                        presence_job.next_run_at = (
                            now_monotonic + presence_job.interval_seconds
                        )
                        presence_due.append(presence_job)
                for key in expired_presence_keys:
                    self._presence_jobs.pop(key, None)
            for periodic_job in due:
                self.submit(
                    key=periodic_job.key,
                    provider=periodic_job.provider,
                    function=periodic_job.function,
                    lease_seconds=0,
                )
            for presence_job in presence_due:
                self.submit(
                    key=presence_job.key,
                    provider=presence_job.provider,
                    function=presence_job.function,
                    lease_seconds=0,
                    # The dynamic schedule already enforces the cadence. A
                    # second success gate here can skip a full interval when
                    # the prior job finished after its scheduled start.
                    min_success_interval_seconds=0,
                )

    def _expire_backoff_locked(self, now: float) -> None:
        for state in self._states.values():
            if (
                state.status == "backoff"
                and state.retry_at is not None
                and state.retry_at <= now
            ):
                state.status = "failed"

    def _prune_states_locked(self, now: float) -> None:
        removable = [
            key
            for key, state in self._states.items()
            if state.status not in {"queued", "running"}
            and state.finished_at is not None
            and now - state.finished_at > self._state_retention_seconds
        ]
        for key in removable:
            self._states.pop(key, None)

    def _policy(self, provider: str) -> RefreshPolicy:
        with self._lock:
            return self._policies.get(provider) or RefreshPolicy(provider=provider)

    def _provider_semaphore(
        self, provider: str
    ) -> threading.BoundedSemaphore:
        with self._lock:
            semaphore = self._provider_semaphores.get(provider)
            if semaphore is None:
                semaphore = threading.BoundedSemaphore(
                    self._policy(provider).max_concurrency
                )
                self._provider_semaphores[provider] = semaphore
            return semaphore

    @staticmethod
    def _normalize_key(key: RefreshKey) -> RefreshKey:
        normalized = tuple(str(part).strip() for part in key)
        if not normalized or any(not part for part in normalized):
            raise ValueError("Refresh key parts must be non-empty")
        return normalized

    @staticmethod
    def _source_timestamp(result: object) -> str | None:
        if not isinstance(result, dict):
            return None
        for field in ("source_timestamp", "timestamp", "_updated", "updated"):
            value = result.get(field)
            if value:
                return str(value)
        return None


def validate_single_process_configuration() -> None:
    """Reject common multi-worker environment settings until leases exist."""
    for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        try:
            configured_workers = int(raw)
        except ValueError:
            continue
        if configured_workers > 1:
            raise RuntimeError(
                "The refresh coordinator currently supports one application "
                f"process; {name}={configured_workers} requires persistent "
                "cross-process leases."
            )


_COORDINATOR = RefreshCoordinator(
    max_workers=_positive_int_env("WX_REFRESH_MAX_WORKERS", 4),
    max_queued=_positive_int_env("WX_REFRESH_MAX_QUEUED", 32),
)
for _policy_entry in (
    RefreshPolicy(
        provider="aviationweather",
        min_request_interval=60.0,
        max_concurrency=1,
        base_backoff_seconds=15.0,
        max_backoff_seconds=300.0,
        presence_required=True,
    ),
    RefreshPolicy(
        provider="iem",
        min_request_interval=60.0,
        max_concurrency=1,
        base_backoff_seconds=15.0,
        max_backoff_seconds=300.0,
        presence_required=True,
    ),
    RefreshPolicy(
        provider="nws-alerts",
        min_request_interval=35.0,
        max_concurrency=1,
        base_backoff_seconds=15.0,
        max_backoff_seconds=300.0,
        presence_required=True,
    ),
    RefreshPolicy(
        provider="wpc",
        min_request_interval=1.0,
        max_concurrency=1,
        base_backoff_seconds=15.0,
        max_backoff_seconds=300.0,
        presence_required=True,
    ),
    RefreshPolicy(
        provider="spc",
        min_request_interval=1.0,
        max_concurrency=2,
        base_backoff_seconds=15.0,
        max_backoff_seconds=300.0,
        presence_required=True,
    ),
    RefreshPolicy(
        provider="nhc",
        min_request_interval=1.0,
        max_concurrency=1,
        base_backoff_seconds=30.0,
        max_backoff_seconds=600.0,
        presence_required=True,
    ),
    RefreshPolicy(
        provider="usdm",
        min_request_interval=1.0,
        max_concurrency=1,
        base_backoff_seconds=30.0,
        max_backoff_seconds=600.0,
        presence_required=True,
    ),
    RefreshPolicy(
        provider="noaa-mrms",
        min_request_interval=0.0,
        max_concurrency=1,
        base_backoff_seconds=30.0,
        max_backoff_seconds=300.0,
        presence_required=True,
    ),
    RefreshPolicy(
        provider="noaa-rtma",
        min_request_interval=0.0,
        max_concurrency=1,
        base_backoff_seconds=30.0,
        max_backoff_seconds=600.0,
        presence_required=True,
    ),
    RefreshPolicy(
        provider="noaa-water",
        min_request_interval=1.0,
        max_concurrency=1,
        base_backoff_seconds=30.0,
        max_backoff_seconds=600.0,
        presence_required=True,
    ),
    RefreshPolicy(
        provider="surface-gradient",
        min_request_interval=0.0,
        max_concurrency=1,
        base_backoff_seconds=15.0,
        max_backoff_seconds=300.0,
        presence_required=True,
    ),
    RefreshPolicy(
        provider="nodd-radar",
        min_request_interval=0.0,
        max_concurrency=1,
        base_backoff_seconds=30.0,
        max_backoff_seconds=300.0,
        presence_required=True,
    ),
    RefreshPolicy(
        provider="satellite-aws",
        min_request_interval=0.0,
        max_concurrency=1,
        base_backoff_seconds=30.0,
        max_backoff_seconds=300.0,
        presence_required=True,
    ),
    RefreshPolicy(
        provider="eumetsat",
        min_request_interval=0.0,
        max_concurrency=1,
        base_backoff_seconds=60.0,
        max_backoff_seconds=600.0,
        presence_required=True,
    ),
    RefreshPolicy(
        provider="local",
        min_request_interval=0.0,
        max_concurrency=1,
        base_backoff_seconds=5.0,
        max_backoff_seconds=60.0,
    ),
):
    _COORDINATOR.register_policy(_policy_entry)


def get_refresh_coordinator() -> RefreshCoordinator:
    return _COORDINATOR
