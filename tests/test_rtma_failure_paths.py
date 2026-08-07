from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

import rtma.rtma_utils as rtma_utils


def test_rtma_crop_grid_handles_descending_1d_coordinates_and_360_longitudes():
    data = np.arange(16).reshape(4, 4)
    latitude = np.array([40.0, 39.0, 38.0, 37.0])
    longitude = np.array([280.0, 281.0, 282.0, 283.0])

    cropped, lat_crop, lon_crop = rtma_utils._crop_grid(
        data,
        latitude,
        longitude,
        [-79.5, -77.5, 37.5, 39.5],
    )

    assert cropped.tolist() == [[5, 6], [9, 10]]
    assert lat_crop.tolist() == [39.0, 38.0]
    assert lon_crop.tolist() == [-79.0, -78.0]


def test_rtma_crop_grid_masks_projected_cells_outside_geographic_extent():
    data = np.arange(9, dtype=float).reshape(3, 3)
    latitude = np.array(
        [
            [34.0, 35.0, 34.0],
            [35.0, 35.0, 35.0],
            [34.0, 35.0, 34.0],
        ]
    )
    longitude = np.array(
        [
            [-80.0, -79.0, -80.0],
            [-79.0, -79.0, -79.0],
            [-80.0, -79.0, -80.0],
        ]
    )

    cropped, lat_crop, lon_crop = rtma_utils._crop_grid(
        data,
        latitude,
        longitude,
        [-79.5, -78.5, 34.5, 35.5],
    )

    assert np.ma.isMaskedArray(cropped)
    assert cropped.shape == (3, 3)
    assert np.ma.getmaskarray(cropped).tolist() == [
        [True, False, True],
        [False, False, False],
        [True, False, True],
    ]
    assert cropped[1, 1] == 4.0
    assert lat_crop.tolist() == latitude.tolist()
    assert lon_crop.tolist() == longitude.tolist()


def test_rtma_crop_grid_preserves_existing_mask_for_projected_coordinates():
    data = np.ma.array(
        np.arange(4, dtype=float).reshape(2, 2),
        mask=[[False, True], [False, False]],
    )
    latitude = np.array([[35.0, 35.0], [36.0, 36.0]])
    longitude = np.array([[-79.0, -78.0], [-79.0, -78.0]])

    cropped, _lat_crop, _lon_crop = rtma_utils._crop_grid(
        data,
        latitude,
        longitude,
        [-79.5, -77.5, 34.5, 36.5],
    )

    assert np.ma.isMaskedArray(cropped)
    assert np.ma.getmaskarray(cropped).tolist() == [
        [False, True],
        [False, False],
    ]


def test_rtma_failed_download_removes_partial_file(tmp_path, monkeypatch):
    source = rtma_utils.RtmaSource(
        url="https://example.invalid/rtma.grb2",
        data_key="fixture",
        valid_time=datetime(2026, 8, 7, 12, tzinfo=timezone.utc),
    )

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def iter_content(chunk_size):
            assert chunk_size == 1024 * 1024
            yield b"GRIB partial payload"
            raise OSError("connection interrupted")

    monkeypatch.setattr(
        rtma_utils.requests,
        "get",
        lambda *_args, **_kwargs: _Response(),
    )

    with pytest.raises(OSError, match="connection interrupted"):
        rtma_utils.ensure_rtma_grib(str(tmp_path), source)

    cache_dir = tmp_path / "rtma" / "grib"
    assert list(cache_dir.glob("*.part")) == []
    assert list(cache_dir.glob("*.grb2")) == []
