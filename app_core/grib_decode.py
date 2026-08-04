"""Process-wide serialization for the non-thread-enabled ecCodes runtime."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator


_ECCODES_DECODE_LOCK = threading.RLock()


@contextmanager
def serialized_grib_decode() -> Iterator[None]:
    """Guard cfgrib/ecCodes work that may touch native decoder state."""

    with _ECCODES_DECODE_LOCK:
        yield
