import json
from pathlib import Path

import pytest

from app_core.atomic_io import atomic_output_path, atomic_write_json


def test_atomic_output_paths_are_job_owned_siblings(tmp_path: Path) -> None:
    destination = tmp_path / "artifact.bin"

    with atomic_output_path(destination, suffix=".part") as first:
        with atomic_output_path(destination, suffix=".part") as second:
            assert first != second
            assert first.parent == destination.parent
            assert second.parent == destination.parent
            assert first.name.startswith(f".{destination.name}.")
            first.write_bytes(b"first")
            second.write_bytes(b"second")
        assert destination.read_bytes() == b"second"

    assert destination.read_bytes() == b"first"
    assert not list(tmp_path.glob(".*.part"))


def test_atomic_output_failure_preserves_publication(tmp_path: Path) -> None:
    destination = tmp_path / "artifact.txt"
    destination.write_text("retained", encoding="utf-8")

    with pytest.raises(RuntimeError, match="injected"):
        with atomic_output_path(destination) as temporary:
            temporary.write_text("partial", encoding="utf-8")
            raise RuntimeError("injected")

    assert destination.read_text(encoding="utf-8") == "retained"
    assert not list(tmp_path.glob(".*.tmp"))


def test_atomic_json_supports_worker_specific_serializers(tmp_path: Path) -> None:
    destination = tmp_path / "payload.json"

    atomic_write_json(destination, {"path": Path("cache/frame")}, default=str)

    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "path": str(Path("cache/frame"))
    }
