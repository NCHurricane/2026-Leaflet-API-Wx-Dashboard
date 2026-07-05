"""Deduped background render thread helpers."""

import threading
from collections.abc import Callable

_LIVE_RENDER_BG_LOCK = threading.Lock()
_LIVE_RENDER_BG_INFLIGHT: set[tuple] = set()


def is_live_render_inflight(key: tuple) -> bool:
    """Check whether a background render for key is currently running.

    Read-only counterpart to spawn_live_render_thread -- lets a caller report
    accurate "still filling" status on requests that didn't themselves trigger
    the render (e.g. a poll that landed while an earlier request's background
    fill is still in progress).
    """
    with _LIVE_RENDER_BG_LOCK:
        return key in _LIVE_RENDER_BG_INFLIGHT


def spawn_live_render_thread(key: tuple, label: str, render_fn: Callable[[], object]) -> bool:
    """Run a live render in a daemon thread, deduped by key.

    Returns True when a refresh is running for the key, whether newly started or
    already in flight, so callers can tag responses as refreshing.
    """
    with _LIVE_RENDER_BG_LOCK:
        if key in _LIVE_RENDER_BG_INFLIGHT:
            return True
        _LIVE_RENDER_BG_INFLIGHT.add(key)

    def _run():
        try:
            render_fn()
        except Exception as exc:
            print(f"[live_render_bg] {label} failed: {type(exc).__name__}: {exc}")
        finally:
            with _LIVE_RENDER_BG_LOCK:
                _LIVE_RENDER_BG_INFLIGHT.discard(key)

    threading.Thread(target=_run, name=f"live-render-bg-{label}", daemon=True).start()
    return True
