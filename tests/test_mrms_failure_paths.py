from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path

import pytest

import app_core.overlay_cache as overlay_cache
import mrms.mrms_nodd_utils as mrms_nodd_utils
import mrms.mrms_utils as mrms_utils
import workers.mrms_live_worker as mrms_live_worker


class _DownloadingS3Client:
    def __init__(self, download):
        self._download = download

    @staticmethod
    def head_object(**_kwargs):
        return {"ContentLength": 128}

    def download_file(self, _bucket, _key, target, **_kwargs):
        self._download(Path(target))


def test_mrms_download_rejects_corrupt_gzip_and_removes_partial(
    tmp_path,
    monkeypatch,
):
    client = _DownloadingS3Client(
        lambda target: target.write_bytes(b"not a gzip stream")
    )
    monkeypatch.setattr(mrms_nodd_utils, "get_s3_client", lambda: client)

    with pytest.raises(ValueError, match="failed integrity validation"):
        mrms_nodd_utils.download_mrms_file(
            "CONUS/Refl_BaseQC/corrupt.grib2.gz",
            str(tmp_path),
        )

    assert list(tmp_path.iterdir()) == []


def test_mrms_interrupted_download_removes_partial(tmp_path, monkeypatch):
    def interrupt(target: Path):
        target.write_bytes(b"partial gzip payload")
        raise OSError("connection interrupted")

    client = _DownloadingS3Client(interrupt)
    monkeypatch.setattr(mrms_nodd_utils, "get_s3_client", lambda: client)

    with pytest.raises(OSError, match="connection interrupted"):
        mrms_nodd_utils.download_mrms_file(
            "CONUS/Refl_BaseQC/interrupted.grib2.gz",
            str(tmp_path),
        )

    assert list(tmp_path.iterdir()) == []


def test_mrms_corrupt_gzip_preserves_prior_decode_and_removes_partial(tmp_path):
    gzip_path = tmp_path / "frame.grib2.gz"
    grib_path = tmp_path / "frame.grib2"
    grib_path.write_bytes(b"previous valid decoded frame")
    gzip_path.write_bytes(b"not a gzip stream")
    os.utime(grib_path, (1, 1))
    os.utime(gzip_path, (2, 2))

    with pytest.raises(OSError):
        mrms_utils.decompress_grib2_gz(str(gzip_path))

    assert grib_path.read_bytes() == b"previous valid decoded frame"
    assert not (tmp_path / "frame.grib2.part").exists()


def test_mrms_history_uses_local_fallback_when_upstream_discovery_fails(
    tmp_path,
    monkeypatch,
):
    frame_time = datetime(2026, 8, 7, 12, tzinfo=timezone.utc)
    local_grib = tmp_path / "local.grib2.gz"
    local_grib.write_bytes(b"fixture")

    monkeypatch.setattr(mrms_live_worker, "_CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(mrms_live_worker, "_MRMS_CACHE", str(tmp_path / "mrms"))
    monkeypatch.setattr(
        mrms_live_worker,
        "_discover_upstream_gribs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("upstream unavailable")
        ),
    )
    monkeypatch.setattr(
        mrms_live_worker,
        "_discover_timestamped_gribs",
        lambda *_args, **_kwargs: [(str(local_grib), frame_time)],
    )
    monkeypatch.setattr(
        overlay_cache,
        "flat_overlay_read_processed_keys",
        lambda *_args, **_kwargs: set(),
    )
    monkeypatch.setattr(
        overlay_cache,
        "flat_overlay_image_path",
        lambda *_args, **_kwargs: str(tmp_path / "missing.png"),
    )
    rendered = []
    monkeypatch.setattr(
        mrms_live_worker,
        "_render_mrms_frame_to_overlay",
        lambda path, product, file_dt, cache_root: rendered.append(
            (path, product, file_dt, cache_root)
        )
        or True,
    )
    monkeypatch.setattr(mrms_live_worker, "mark_run_complete", lambda *_args: None)

    count = mrms_live_worker.run_mrms_live_product(
        "Refl_BaseQC",
        max_hours=1,
    )

    assert count == 1
    assert rendered == [
        (str(local_grib), "Refl_BaseQC", frame_time, str(tmp_path))
    ]
