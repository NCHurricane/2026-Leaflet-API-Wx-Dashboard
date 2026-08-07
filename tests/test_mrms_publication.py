from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import threading

import app_core.overlay_cache as overlay_cache
import workers.mrms_live_worker as mrms_live_worker
import workers.mrms_worker as mrms_worker


FRAME_TIME = datetime(2026, 8, 7, 12, tzinfo=timezone.utc)


def _disable_processed_frame_dedup(monkeypatch):
    monkeypatch.setattr(
        overlay_cache,
        "flat_overlay_read_processed_keys",
        lambda *_args, **_kwargs: set(),
    )


def _write_render_artifacts(path: str, payload: bytes = b"png") -> None:
    Path(path).write_bytes(payload)
    Path(path.replace(".png", "_bounds.json")).write_text(
        "[-130,-60,21,52]",
        encoding="utf-8",
    )
    Path(path.replace(".png", "_meta.json")).write_text(
        "{}",
        encoding="utf-8",
    )


def test_mrms_live_render_uses_unique_paths_for_concurrent_same_frame(
    tmp_path,
    monkeypatch,
):
    _disable_processed_frame_dedup(monkeypatch)
    barrier = threading.Barrier(2)
    render_paths = []
    published_paths = []
    guard = threading.Lock()

    def render(_grib_path, _product, _extent, output_path, **_kwargs):
        with guard:
            render_paths.append(output_path)
        barrier.wait(timeout=2)
        _write_render_artifacts(output_path)

    monkeypatch.setattr(mrms_worker, "_render_mrms_png_standalone", render)
    monkeypatch.setattr(
        mrms_worker,
        "_write_mrms_overlay_cache",
        lambda _product, path, _file_dt, **_kwargs: published_paths.append(path),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                mrms_live_worker._render_mrms_frame_to_overlay,
                "fixture.grib2",
                "Refl_BaseQC",
                FRAME_TIME,
                str(tmp_path),
            )
            for _ in range(2)
        ]
        results = [future.result(timeout=3) for future in futures]

    assert results == [True, True]
    assert len(set(render_paths)) == 2
    assert sorted(published_paths) == sorted(render_paths)


def test_mrms_live_render_removes_png_and_sidecars_after_success(
    tmp_path,
    monkeypatch,
):
    _disable_processed_frame_dedup(monkeypatch)
    published = []
    monkeypatch.setattr(
        mrms_worker,
        "_render_mrms_png_standalone",
        lambda _grib, _product, _extent, path, **_kwargs: _write_render_artifacts(
            path
        ),
    )
    monkeypatch.setattr(
        mrms_worker,
        "_write_mrms_overlay_cache",
        lambda _product, path, _file_dt, **_kwargs: published.append(path),
    )

    rendered = mrms_live_worker._render_mrms_frame_to_overlay(
        "fixture.grib2",
        "Refl_BaseQC",
        FRAME_TIME,
        str(tmp_path),
    )

    assert rendered is True
    assert len(published) == 1
    assert list((tmp_path / "mrms" / "Refl_BaseQC").glob("temp_*")) == []


def test_mrms_live_render_removes_partial_artifacts_after_failure(
    tmp_path,
    monkeypatch,
):
    _disable_processed_frame_dedup(monkeypatch)

    def fail_render(_grib_path, _product, _extent, output_path, **_kwargs):
        _write_render_artifacts(output_path, b"partial")
        raise RuntimeError("render interrupted")

    monkeypatch.setattr(
        mrms_worker,
        "_render_mrms_png_standalone",
        fail_render,
    )

    rendered = mrms_live_worker._render_mrms_frame_to_overlay(
        "fixture.grib2",
        "Refl_BaseQC",
        FRAME_TIME,
        str(tmp_path),
    )

    assert rendered is False
    assert list((tmp_path / "mrms" / "Refl_BaseQC").glob("temp_*")) == []
