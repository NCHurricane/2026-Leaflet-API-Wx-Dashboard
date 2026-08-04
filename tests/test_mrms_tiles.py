from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

import mrms.mrms_tiles as mrms_tiles
from mrms.mrms_tiles import (
    enrich_frame_with_tiles,
    filter_unpreparable_duplicate_frames,
    max_native_zoom_for_product,
    render_tile,
    tile_metadata,
    write_tile_source,
)
from mrms.legend_utils import colorize_masked_mrms_data
from services.mrms_service import _load_latest_source_timestamp
from workers.mrms_live_worker import _render_mrms_frame_to_overlay


FRAME_KEY = "2026_08_04_12_00_00"


def _web_mercator_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    count = 2**zoom
    x = int((lon + 180.0) / 360.0 * count)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * count)
    return x, y


def test_native_tile_source_and_png_tile_are_versioned_and_cached(tmp_path: Path):
    product = "Refl_BaseQC"
    lat = np.linspace(52.0, 21.0, 64)
    lon = np.linspace(-130.0, -60.0, 128)
    data = np.full((lat.size, lon.size), 30.0, dtype=np.float32)

    before = tile_metadata(product, FRAME_KEY, cache_root=str(tmp_path))
    assert before is not None
    assert before["version"] == "mrms-v1"
    assert before["min_zoom"] == 7
    assert before["max_native_zoom"] == 7
    assert before["ready"] is False

    source = Path(
        write_tile_source(
            data,
            lat,
            lon,
            product,
            FRAME_KEY,
            cache_root=str(tmp_path),
        )
    )
    assert source.is_file()
    assert tile_metadata(product, FRAME_KEY, cache_root=str(tmp_path))["ready"] is True

    x, y = _web_mercator_tile(-80.0, 35.0, 7)
    first = Path(
        render_tile(
            product,
            FRAME_KEY,
            7,
            x,
            y,
            cache_root=str(tmp_path),
        )
    )
    second = Path(
        render_tile(
            product,
            FRAME_KEY,
            7,
            x,
            y,
            cache_root=str(tmp_path),
        )
    )
    assert second == first
    with Image.open(first) as image:
        rgba = np.asarray(image.convert("RGBA"))
    assert rgba.shape == (256, 256, 4)
    assert np.max(rgba[:, :, 3]) == 255
    expected = colorize_masked_mrms_data(product, np.array([[30.0]]))[0, 0]
    assert np.array_equal(rgba[128, 128], expected)


def test_frame_enrichment_preserves_png_fallback_and_product_native_zoom(tmp_path: Path):
    frame = {
        "frame_key": FRAME_KEY,
        "image_url": "/cache/overlays/mrms/Refl_BaseQC/frame.png",
        "render": {"image_url": "/cache/overlays/mrms/Refl_BaseQC/frame.png"},
    }
    enriched = enrich_frame_with_tiles(
        frame,
        "Refl_BaseQC",
        cache_root=str(tmp_path),
    )

    assert enriched["image_url"] == frame["image_url"]
    assert enriched["render"]["image_url"] == frame["render"]["image_url"]
    assert enriched["tile"] == enriched["render"]["tile"]
    assert "{z}/{x}/{y}.png" in enriched["tile"]["url_template"]
    assert max_native_zoom_for_product("MESH_Instant") == 7
    assert max_native_zoom_for_product("RotationTrack_LL_30min") == 8
    assert max_native_zoom_for_product("AzShear_Low") == 8


def test_disabled_native_tiles_leave_png_metadata_unchanged(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mrms_tiles, "MRMS_TILES_ENABLED", False)
    frame = {"frame_key": FRAME_KEY, "image_url": "/existing.png"}

    assert tile_metadata("MESH_Instant", FRAME_KEY, cache_root=str(tmp_path)) is None
    assert enrich_frame_with_tiles(
        frame,
        "MESH_Instant",
        cache_root=str(tmp_path),
    ) == frame


def test_mtime_duplicate_is_hidden_when_a_source_backed_frame_is_nearby(
    tmp_path: Path,
):
    product_dir = tmp_path / "mrms" / "RotationTrack_LL_30min"
    product_dir.mkdir(parents=True)
    (product_dir / "2026-08-04_12-00-00.grib2.gz").write_bytes(b"grib")
    frames = [
        {"frame_key": "2026_08_04_11_00_00"},
        {"frame_key": "2026_08_04_12_00_00"},
        {"frame_key": "2026_08_04_12_00_30"},
    ]

    filtered = filter_unpreparable_duplicate_frames(
        frames,
        "RotationTrack_LL_30min",
        cache_root=str(tmp_path),
    )

    assert [frame["frame_key"] for frame in filtered] == [
        "2026_08_04_11_00_00",
        "2026_08_04_12_00_00",
    ]


def test_latest_source_state_supplies_canonical_timestamp(tmp_path: Path):
    product_dir = tmp_path / "mrms" / "RotationTrack_LL_30min"
    product_dir.mkdir(parents=True)
    (product_dir / "latest_source.json").write_text(
        '{"source_timestamp":"2026-08-04T21:12:00+00:00"}',
        encoding="utf-8",
    )

    assert _load_latest_source_timestamp(str(product_dir)) == (
        "2026-08-04T21:12:00+00:00"
    )


def test_history_render_builds_tile_source_during_existing_decode(
    monkeypatch,
    tmp_path: Path,
):
    render_calls = []
    monkeypatch.setattr(
        "workers.mrms_worker._render_mrms_png_standalone",
        lambda *args, **kwargs: render_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "workers.mrms_worker._write_mrms_overlay_cache",
        lambda *args, **kwargs: None,
    )

    rendered = _render_mrms_frame_to_overlay(
        str(tmp_path / "frame.grib2"),
        "RotationTrack_LL_30min",
        datetime(2026, 8, 4, 21, 12, tzinfo=timezone.utc),
        str(tmp_path),
    )

    assert rendered is True
    assert render_calls[0][1]["tile_frame_key"] == "2026_08_04_21_12_00"
