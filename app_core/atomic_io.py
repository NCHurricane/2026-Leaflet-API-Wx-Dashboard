"""Atomic filesystem publication helpers."""

from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


@contextmanager
def atomic_output_path(
    path: str | os.PathLike[str],
    *,
    suffix: str = ".tmp",
) -> Iterator[Path]:
    """Yield a job-owned sibling path and atomically publish it on success."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{os.getpid()}.{uuid.uuid4().hex}{suffix}"
    )
    try:
        yield temporary
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def atomic_write_text(
    path: str | os.PathLike[str],
    text: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """Publish text without exposing a partially written destination."""
    with atomic_output_path(path) as temporary:
        with temporary.open("w", encoding=encoding) as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())


def atomic_write_bytes(
    path: str | os.PathLike[str],
    payload: bytes,
) -> None:
    """Publish bytes without exposing a partially written destination."""
    with atomic_output_path(path) as temporary:
        with temporary.open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())


def atomic_write_json(
    path: str | os.PathLike[str],
    payload: Any,
    *,
    ensure_ascii: bool = True,
    separators: tuple[str, str] | None = None,
    default: Any = None,
) -> None:
    """Serialize and atomically publish a JSON document."""
    text = json.dumps(
        payload,
        ensure_ascii=ensure_ascii,
        separators=separators,
        default=default,
    )
    atomic_write_text(path, text)
