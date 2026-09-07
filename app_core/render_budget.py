"""Process-wide memory budget for heavyweight weather renders."""

from collections import deque
from contextlib import contextmanager
import os
import threading
from typing import Callable, Iterator

import psutil


def _configured_slots(name: str, default: int = 1) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _configured_megabytes(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


class _ByteBudget:
    """Fair admission queue bounded by estimated in-flight bytes."""

    def __init__(self, capacity_bytes: int, capacity_provider=None):
        self.capacity_bytes = max(1, int(capacity_bytes))
        self._capacity_provider = capacity_provider
        self._condition = threading.Condition()
        self._in_flight_bytes = 0
        self._active = 0
        self._queue: deque[tuple[object, int]] = deque()

    def _can_admit(self, weight: int) -> bool:
        if self._capacity_provider is not None:
            self.capacity_bytes = max(1, int(self._capacity_provider()))
        if self._active == 0:
            # A render larger than the configured budget must still make
            # progress, but it owns the budget exclusively while it runs.
            return True
        return self._in_flight_bytes + weight <= self.capacity_bytes

    def acquire(
        self,
        estimated_bytes: int,
        should_continue: Callable[[], bool] | None = None,
    ) -> tuple[bool, int]:
        weight = max(1, int(estimated_bytes))
        token = object()
        with self._condition:
            self._queue.append((token, weight))
            try:
                while True:
                    if should_continue is not None and not should_continue():
                        self._queue = deque(
                            entry for entry in self._queue if entry[0] is not token
                        )
                        self._condition.notify_all()
                        return False, weight
                    if self._queue[0][0] is token and self._can_admit(weight):
                        self._queue.popleft()
                        self._in_flight_bytes += weight
                        self._active += 1
                        self._condition.notify_all()
                        return True, weight
                    self._condition.wait(timeout=0.05)
            except BaseException:
                self._queue = deque(
                    entry for entry in self._queue if entry[0] is not token
                )
                self._condition.notify_all()
                raise

    def release(self, weight: int) -> None:
        with self._condition:
            self._in_flight_bytes = max(0, self._in_flight_bytes - int(weight))
            self._active = max(0, self._active - 1)
            self._condition.notify_all()

    def snapshot(self) -> dict[str, int]:
        with self._condition:
            return {
                "capacity_bytes": self.capacity_bytes,
                "in_flight_bytes": self._in_flight_bytes,
                "active": self._active,
                "queued": len(self._queue),
            }


_HEAVY_RENDER_SLOTS = threading.BoundedSemaphore(
    _configured_slots("WX_HEAVY_RENDER_SLOTS")
)
_SURFACE_GRADIENT_SLOTS = threading.BoundedSemaphore(
    _configured_slots("WX_SURFACE_GRADIENT_SLOTS")
)
def _satellite_capacity_bytes() -> int:
    memory = psutil.virtual_memory()
    ceiling = _configured_megabytes("WX_SATELLITE_RENDER_BUDGET_MB", 16 * 1024) * 1024**2
    return max(1, min(ceiling, memory.total // 4, memory.available // 2))


_SATELLITE_RENDER_BUDGET = _ByteBudget(
    _satellite_capacity_bytes(), capacity_provider=_satellite_capacity_bytes
)


@contextmanager
def heavy_render_slot(
    should_continue: Callable[[], bool] | None = None,
) -> Iterator[bool]:
    """Serialize memory-heavy renders, with optional queued-work cancellation."""
    acquired = False
    if should_continue is None:
        _HEAVY_RENDER_SLOTS.acquire()
        acquired = True
    else:
        while should_continue():
            if _HEAVY_RENDER_SLOTS.acquire(timeout=0.05):
                acquired = True
                break
    try:
        yield acquired
    finally:
        if acquired:
            _HEAVY_RENDER_SLOTS.release()


@contextmanager
def satellite_render_slot(
    estimated_bytes: int,
    should_continue: Callable[[], bool] | None = None,
) -> Iterator[bool]:
    """Admit Satellite work while its estimated memory fits the byte budget."""
    acquired, weight = _SATELLITE_RENDER_BUDGET.acquire(
        estimated_bytes,
        should_continue=should_continue,
    )
    try:
        yield acquired
    finally:
        if acquired:
            _SATELLITE_RENDER_BUDGET.release(weight)


def satellite_render_budget_snapshot() -> dict[str, int]:
    """Return process-local Satellite admission state for diagnostics."""
    return _SATELLITE_RENDER_BUDGET.snapshot()


@contextmanager
def surface_gradient_render_slot() -> Iterator[None]:
    """Bound Surface gradients independently from Radar/Satellite renders."""
    _SURFACE_GRADIENT_SLOTS.acquire()
    try:
        yield
    finally:
        _SURFACE_GRADIENT_SLOTS.release()
