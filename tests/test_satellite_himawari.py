from __future__ import annotations

import bz2
import struct

import numpy as np
import pytest

from satellite_v2.ahi_hsd import load_ahi_raster
import satellite_v2.provider_himawari as provider_himawari


def _header_block(block_number: int, length: int) -> bytearray:
    block = bytearray(length)
    block[0] = block_number
    struct.pack_into("<H", block, 1, length)
    return block


def _ahi_segment_bytes(
    counts,
    *,
    band: int,
    segment_number: int = 1,
    total_segments: int = 1,
    first_line: int = 1,
) -> bytes:
    counts_array = np.asarray(counts, dtype="<u2")
    n_lines, n_cols = counts_array.shape

    block1 = _header_block(1, 80)
    block1[38:42] = b"FLDK"
    block2 = _header_block(2, 16)
    struct.pack_into("<HHH", block2, 3, 16, n_cols, n_lines)
    block2[9] = 0

    block3 = _header_block(3, 64)
    struct.pack_into("<d", block3, 3, 140.7)
    struct.pack_into("<II", block3, 11, 40_932_549, 40_932_549)
    struct.pack_into("<ff", block3, 19, (n_cols + 1) / 2, 2.5)
    struct.pack_into("<ddd", block3, 27, 42_164.0, 6_378.137, 6_356.7523)

    block5 = _header_block(5, 112)
    struct.pack_into("<H", block5, 3, band)
    struct.pack_into("<d", block5, 5, 0.64 if band <= 6 else 10.4)
    struct.pack_into("<HH", block5, 15, 65_535, 65_534)
    struct.pack_into("<dd", block5, 19, 0.01 if band <= 6 else 0.1, 0.0)
    if band <= 6:
        struct.pack_into("<d", block5, 35, 1.0)
    else:
        struct.pack_into("<ddd", block5, 35, 0.0, 1.0, 0.0)
        struct.pack_into(
            "<ddd",
            block5,
            83,
            299_792_458.0,
            6.626_070_15e-34,
            1.380_649e-23,
        )

    block7 = _header_block(7, 16)
    block7[3] = total_segments
    block7[4] = segment_number
    struct.pack_into("<H", block7, 5, first_line)

    blocks = [block1, block2, block3, block5, block7]
    total_header_length = sum(len(block) for block in blocks)
    struct.pack_into("<I", block1, 70, total_header_length)
    return b"".join(bytes(block) for block in blocks) + counts_array.tobytes()


def test_ahi_loader_decodes_and_stitches_visible_segments(tmp_path):
    northern = _ahi_segment_bytes(
        [[10, 20, 65_535, 40], [50, 60, 70, 80]],
        band=3,
        segment_number=1,
        total_segments=2,
        first_line=1,
    )
    southern = _ahi_segment_bytes(
        [[90, 100, 110, 120], [130, 140, 150, 160]],
        band=3,
        segment_number=2,
        total_segments=2,
        first_line=3,
    )
    north_path = tmp_path / "north.DAT.bz2"
    south_path = tmp_path / "south.DAT"
    north_path.write_bytes(bz2.compress(northern))
    south_path.write_bytes(southern)

    raster = load_ahi_raster([south_path, north_path], max_grid=4)

    assert raster.values.shape == (4, 4)
    assert raster.stride == 1
    assert raster.header.segment_number == 1
    assert raster.header.band_number == 3
    assert raster.values[0, 0] == pytest.approx(0.1)
    assert np.isnan(raster.values[0, 2])
    assert raster.values[-1, -1] == pytest.approx(1.6)
    assert raster.src_crs.to_dict()["lon_0"] == 140.7


def test_ahi_loader_calibrates_ir_counts_to_brightness_temperature(tmp_path):
    segment = _ahi_segment_bytes(
        [[80, 90, 100, 110], [120, 130, 65_534, 150]],
        band=13,
    )
    path = tmp_path / "ir.DAT"
    path.write_bytes(segment)

    raster = load_ahi_raster([path], max_grid=4)

    finite = raster.values[np.isfinite(raster.values)]
    assert finite.size == 7
    assert 250.0 < float(finite.min()) < float(finite.max()) < 350.0
    assert np.isnan(raster.values[1, 2])


def test_himawari_provider_lists_only_complete_full_disk_frames(monkeypatch):
    complete_prefix = "AHI-L1b-FLDK/2026/08/07/1200"
    keys = [
        (
            complete_prefix
            + "/HS_H09_20260807_1200_B03_FLDK_R20_S0102.DAT.bz2",
            100,
        ),
        (
            complete_prefix
            + "/HS_H09_20260807_1200_B03_FLDK_R20_S0202.DAT.bz2",
            200,
        ),
        (
            "AHI-L1b-FLDK/2026/08/07/1210/"
            "HS_H09_20260807_1210_B03_FLDK_R20_S0102.DAT.bz2",
            125,
        ),
    ]
    monkeypatch.setattr(
        provider_himawari,
        "_iter_hour_prefixes",
        lambda *_args, **_kwargs: ["fixture-prefix"],
    )
    monkeypatch.setattr(
        provider_himawari,
        "_list_prefix_objects",
        lambda *_args, **_kwargs: keys,
    )

    frames = provider_himawari.list_recent_frames(
        "himawari9",
        "FULLDISK",
        "Channel02",
        hours=1,
        max_frames=10,
    )

    assert [frame.frame_key for frame in frames] == ["20260807T120000Z"]
    assert frames[0].timestamp_utc == "2026-08-07T12:00:00Z"
    assert frames[0].file_size == 300
    assert frames[0].file_sizes == {"Channel02": 300}
    assert frames[0].source_key.endswith("_S0102.DAT.bz2")

