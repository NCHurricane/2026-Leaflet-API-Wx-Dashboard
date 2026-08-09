"""Process-wide memory budget for heavyweight weather renders."""

from contextlib import contextmanager
import os
import threading
from typing import Callable, Iterator


def _configured_slots(name: str, default: int = 1) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


_HEAVY_RENDER_SLOTS = threading.BoundedSemaphore(
    _configured_slots("WX_HEAVY_RENDER_SLOTS")
)
_SURFACE_GRADIENT_SLOTS = threading.BoundedSemaphore(
    _configured_slots("WX_SURFACE_GRADIENT_SLOTS")
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
def surface_gradient_render_slot() -> Iterator[None]:
    """Bound Surface gradients independently from Radar/Satellite renders."""
    _SURFACE_GRADIENT_SLOTS.acquire()
    try:
        yield
    finally:
        _SURFACE_GRADIENT_SLOTS.release()
