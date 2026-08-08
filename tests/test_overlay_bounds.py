from __future__ import annotations

from datetime import datetime, timezone
import json

import numpy as np
import pytest

import app_core.overlay_cache as overlay_cache
import mrms.publication as mrms_publication
from mrms.mrms_utils import warp_array_to_mercator
from rtma.rtma_utils import _warp_to_latlon_grid


def test_mercator_warp_has_stable_bounds_and_orientation():
    latitude = np.array([35.0, 36.0, 37.0])
    longitude = np.array([280.0, 281.0, 282.0, 283.0])
    south_to_north = np.arange(12, dtype=np.float32).reshape(3, 4)

    ascending, ascending_bounds = warp_array_to_mercator(
        south_to_north,
        latitude,
        longitude,
    )
    descending, descending_bounds = warp_array_to_mercator(
        south_to_north[::-1],
        latitude[::-1],
        longitude,
    )

    assert ascending_bounds == pytest.approx(
        [-80.5, -76.1359843684, 34.8585954415, 37.5],
        abs=1.0e-8,
    )
    assert descending_bounds == pytest.approx(ascending_bounds, abs=1.0e-10)
    np.testing.assert_array_equal(ascending, descending)
    np.testing.assert_array_equal(
        ascending,
        np.array(
            [
                [8.0, 9.0, 10.0, 11.0],
                [4.0, 5.0, 6.0, 7.0],
                [0.0, 1.0, 2.0, 3.0],
            ],
            dtype=np.float32,
        ),
    )


def test_mercator_warp_dimension_cap_preserves_published_footprint():
    data = np.arange(12, dtype=np.float32).reshape(3, 4)
    latitude = np.array([35.0, 36.0, 37.0])
    longitude = np.array([280.0, 281.0, 282.0, 283.0])

    uncapped, uncapped_bounds = warp_array_to_mercator(data, latitude, longitude)
    capped, capped_bounds = warp_array_to_mercator(
        data,
        latitude,
        longitude,
        max_dim=3,
    )

    assert uncapped.shape == (3, 4)
    assert capped.shape == (2, 3)
    assert max(capped.shape) == 3
    assert capped_bounds == pytest.approx(uncapped_bounds, abs=1.0e-10)


def test_rtma_curvilinear_warp_has_stable_half_cell_bounds():
    latitude = np.array(
        [
            [35.0, 35.25, 35.5],
            [36.0, 36.25, 36.5],
            [37.0, 37.25, 37.5],
        ]
    )
    longitude = np.array(
        [
            [280.0, 281.0, 282.0],
            [280.1, 281.1, 282.1],
            [280.2, 281.2, 282.2],
        ]
    )
    data = np.arange(9, dtype=float).reshape(3, 3)

    warped, bounds = _warp_to_latlon_grid(data, latitude, longitude)

    assert bounds == pytest.approx([-80.55, -77.25, 34.375, 38.125])
    assert warped.shape == data.shape
    assert not np.ma.getmaskarray(warped).any()
    assert warped[0, 0] == pytest.approx(0.0)
    assert warped[-1, -1] == pytest.approx(8.0)


def test_mrms_overlay_cache_preserves_rendered_bounds(tmp_path, monkeypatch):
    rendered_bounds = [-102.125, -73.875, 24.25, 49.75]
    png_path = tmp_path / "render.png"
    png_path.write_bytes(b"png")
    png_path.with_name("render_bounds.json").write_text(
        json.dumps(rendered_bounds),
        encoding="utf-8",
    )
    png_path.with_name("render_meta.json").write_text(
        json.dumps({"legend": {"type": "continuous"}}),
        encoding="utf-8",
    )

    captured = []
    monkeypatch.setattr(mrms_publication, "CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setattr(
        overlay_cache,
        "flat_overlay_read_processed_keys",
        lambda *_args, **_kwargs: set(),
    )
    monkeypatch.setattr(
        overlay_cache,
        "flat_overlay_image_path",
        lambda *_args, **_kwargs: str(tmp_path / "cache" / "frame.png"),
    )
    monkeypatch.setattr(
        overlay_cache,
        "flat_overlay_update_index",
        lambda *_args, **kwargs: captured.append(kwargs),
    )
    monkeypatch.setattr(
        overlay_cache,
        "flat_overlay_write_processed_keys",
        lambda *_args, **_kwargs: None,
    )

    mrms_publication.write_mrms_overlay_cache(
        "Refl_BaseQC",
        str(png_path),
        datetime(2026, 8, 7, 12, tzinfo=timezone.utc),
        keep_n=None,
    )

    assert len(captured) == 1
    assert captured[0]["bounds"] == rendered_bounds
