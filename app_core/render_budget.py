"""Process-wide memory budget for heavyweight weather renders."""

from contextlib import contextmanager
import os
import threading
from typing import Iterator


def _configured_slots() -> int:
    try:
        return max(1, int(os.environ.get("WX_HEAVY_RENDER_SLOTS", "1")))
    except (TypeError, ValueError):
        return 1


_HEAVY_RENDER_SLOTS = threading.BoundedSemaphore(_configured_slots())


@contextmanager
def heavy_render_slot() -> Iterator[None]:
    """Serialize memory-heavy render families unless explicitly configured."""
    _HEAVY_RENDER_SLOTS.acquire()
    try:
        yield
    finally:
        _HEAVY_RENDER_SLOTS.release()
