import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_core.overlay_cache import (
    radar_list_frames,
    radar_overlay_image_path,
    radar_prune_frames,
    radar_update_index,
)
from workers import radar_live_worker as worker


def _source_file(directory: Path, name: str, payload: bytes = b"radar") -> Path:
    path = directory / name
    path.write_bytes(payload)
    return path


def test_discovery_reuses_persisted_filenames_while_directory_is_unchanged(
    tmp_path, monkeypatch
):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    expected = [
        _source_file(source_dir, "KGSP_20260726_120000"),
        _source_file(source_dir, "KGSP_20260726_120500"),
    ]
    monkeypatch.setattr(worker, "_CACHE_ROOT", tmp_path / "cache")

    first, first_reused = worker._discover_radar_files_cached(
        source_dir, "KGSP", "L3", "L3_N0B"
    )
    assert first == expected
    assert first_reused is False

    def fail_scan(_data_path):
        raise AssertionError("unchanged discovery should not rescan the directory")

    monkeypatch.setattr(worker, "_discover_radar_files", fail_scan)
    second, second_reused = worker._discover_radar_files_cached(
        source_dir, "KGSP", "L3", "L3_N0B"
    )

    assert second == expected
    assert second_reused is True


def test_discovery_rescans_when_directory_mtime_changes(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    first = _source_file(source_dir, "KGSP_20260726_120000")
    monkeypatch.setattr(worker, "_CACHE_ROOT", tmp_path / "cache")

    worker._discover_radar_files_cached(source_dir, "KGSP", "L3", "L3_N0B")
    second = _source_file(source_dir, "KGSP_20260726_120500")
    stat = source_dir.stat()
    os.utime(source_dir, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    discovered, reused = worker._discover_radar_files_cached(
        source_dir, "KGSP", "L3", "L3_N0B"
    )

    assert discovered == [first, second]
    assert reused is False


def test_discovery_recovers_from_missing_cached_file(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    kept = _source_file(source_dir, "KGSP_20260726_120000")
    removed = _source_file(source_dir, "KGSP_20260726_120500")
    monkeypatch.setattr(worker, "_CACHE_ROOT", tmp_path / "cache")

    worker._discover_radar_files_cached(source_dir, "KGSP", "L3", "L3_N0B")
    removed.unlink()
    # Simulate an interrupted external cleanup that restored the old directory
    # timestamp; validating cached entries must still force safe rediscovery.
    index_path = worker._discovery_index_path("KGSP", "L3", "L3_N0B")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    os.utime(
        source_dir,
        ns=(source_dir.stat().st_atime_ns, int(index["dir_mtime_ns"])),
    )

    discovered, reused = worker._discover_radar_files_cached(
        source_dir, "KGSP", "L3", "L3_N0B"
    )

    assert discovered == [kept]
    assert reused is False


def test_atomic_finalize_replaces_destination_and_has_no_orphan(tmp_path):
    destination = tmp_path / "public" / "frame.png"
    destination.parent.mkdir()
    destination.write_bytes(b"old")
    temporary = tmp_path / "render.tmp"
    temporary.write_bytes(b"new")

    result = worker._finalize_rendered_png(temporary, destination)

    assert result == destination
    assert destination.read_bytes() == b"new"
    assert not temporary.exists()


def test_atomic_finalize_failure_preserves_public_frame(tmp_path, monkeypatch):
    destination = tmp_path / "public" / "frame.png"
    destination.parent.mkdir()
    destination.write_bytes(b"old")
    temporary = tmp_path / "render.tmp"
    temporary.write_bytes(b"new")

    def fail_replace(_source, _destination):
        raise OSError("simulated interruption")

    monkeypatch.setattr(worker.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated interruption"):
        worker._finalize_rendered_png(temporary, destination)

    assert destination.read_bytes() == b"old"
    assert temporary.read_bytes() == b"new"


def test_worker_cleans_temporary_render_when_atomic_finalize_fails(
    tmp_path, monkeypatch
):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    _source_file(source_dir, "KGSP_20260726_120000")
    cache_root = tmp_path / "cache"
    render_root = cache_root / "radar" / ".render_tmp"
    written_processed_keys = []

    provider = SimpleNamespace(
        __name__="tests.pinned_radar_provider",
        download_radar_data=lambda *_args, **_kwargs: (str(source_dir), 1, 0),
    )
    radar = SimpleNamespace(fields={"reflectivity": {}})

    monkeypatch.setattr(worker, "_CACHE_ROOT", cache_root)
    monkeypatch.setattr(worker, "_TMP_RENDER_ROOT", render_root)
    monkeypatch.setattr(worker, "_site_bounds", lambda _site: [-84, -81, 33, 36])
    monkeypatch.setattr(worker, "radar_list_frames", lambda *_args: [])
    monkeypatch.setattr(worker, "radar_read_processed_keys", lambda *_args: set())
    monkeypatch.setattr(
        worker,
        "radar_write_processed_keys",
        lambda *_args: written_processed_keys.append(set(_args[4])),
    )
    monkeypatch.setattr(worker, "radar_prune_frames", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(worker, "_read_radar", lambda *_args: radar)
    monkeypatch.setattr(
        worker, "_field_for_product", lambda *_args, **_kwargs: "reflectivity"
    )
    monkeypatch.setattr(
        worker, "_ensure_derived_field", lambda *_args, **_kwargs: "reflectivity"
    )
    monkeypatch.setattr(
        worker,
        "_frame_dt_from_radar",
        lambda *_args: datetime(2026, 7, 26, 12, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(worker, "_select_sweep", lambda *_args: (0, [0.5], 0.5))

    def render_overlay(**kwargs):
        Path(kwargs["out_path"]).write_bytes(b"complete-render")
        return True

    def fail_finalize(*_args):
        raise OSError("simulated interruption")

    monkeypatch.setattr(worker, "_render_overlay_png", render_overlay)
    monkeypatch.setattr(worker, "_finalize_rendered_png", fail_finalize)
    monkeypatch.setattr(
        worker,
        "radar_update_index",
        lambda *_args, **_kwargs: pytest.fail("failed publication reached index write"),
    )

    cached = worker._render_site_product(
        provider,
        "Pinned-Disk",
        "KGSP",
        "L3_N0B",
        {"level": "Level 3", "product": "N0B", "label": "Reflectivity"},
        latest_only=True,
        newest_first=True,
        max_render_frames=1,
        elevation="auto",
        lookback_hours=12,
    )

    assert cached == 0
    assert written_processed_keys == [set()]
    assert not list(render_root.glob("*.png"))


def test_atomic_publication_is_immediately_visible_and_pruning_keeps_newest(
    tmp_path,
):
    site, level, product = "KGSP", "L3", "L3_N0B"
    frame_keys = [
        "2026_07_26_12_00_00",
        "2026_07_26_12_05_00",
        "2026_07_26_12_10_00",
    ]

    for index, frame_key in enumerate(frame_keys):
        temporary = tmp_path / f"{frame_key}.tmp"
        temporary.write_bytes(f"png-{index}".encode())
        destination = Path(
            radar_overlay_image_path(tmp_path, site, level, product, frame_key)
        )
        worker._finalize_rendered_png(temporary, destination)

        # A crash before index persistence still leaves the complete PNG visible.
        assert [frame["frame_key"] for frame in radar_list_frames(
            tmp_path, site, level, product
        )][-1] == frame_key
        radar_update_index(
            tmp_path,
            site,
            level,
            product,
            frame_key,
            data_key=f"source-{index}",
        )

    radar_prune_frames(tmp_path, site, level, product, keep_n=2)

    frames = radar_list_frames(tmp_path, site, level, product)
    assert [frame["frame_key"] for frame in frames] == frame_keys[-2:]
    assert not Path(
        radar_overlay_image_path(tmp_path, site, level, product, frame_keys[0])
    ).exists()
    assert not list(tmp_path.rglob("*.tmp"))
