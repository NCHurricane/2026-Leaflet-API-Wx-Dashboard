"""Process-wide memory budget for heavyweight weather renders."""

from contextlib import contextmanager
import os
import threading
from typing import Iterator


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
def heavy_render_slot() -> Iterator[None]:
    """Serialize memory-heavy render families unless explicitly configured."""
    _HEAVY_RENDER_SLOTS.acquire()
    try:
        yield
    finally:
        _HEAVY_RENDER_SLOTS.release()


@contextmanager
def surface_gradient_render_slot() -> Iterator[None]:
    """Bound Surface gradients independently from Radar/Satellite renders."""
    _SURFACE_GRADIENT_SLOTS.acquire()
    try:
        yield
    finally:
        _SURFACE_GRADIENT_SLOTS.release()
