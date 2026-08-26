from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import struct
import threading
import time
import warnings

import netCDF4
import numpy as np
import pytest

from config.satellite_v2_config import (
    satellite_v2_render_version_for_satellite,
    source_channels_for_product,
)
import satellite_v2.fci_nc as fci_nc
from satellite_v2.fci_nc import load_fci_rasters
import satellite_v2.provider_eumetsat as provider_eumetsat
from satellite_v2.seviri_nat import (
    ARCHIVE_HEADER_BYTES,
    CHANNEL_INDEX,
    LINE_RECORD_BYTES,
    VISIR_LINE_BYTES,
    VISIR_LINE_DATA_OFFSET,
    VISIR_NUM_COLUMNS,
    VISIR_RECORD_BYTES,
    load_seviri_raster,
)


def _pack_10bit(counts: np.ndarray) -> bytes:
    values = np.asarray(counts, dtype=np.uint16)
    assert values.ndim == 1
    assert values.size % 4 == 0
    groups = values.reshape(-1, 4)
    packed = np.empty((groups.shape[0], 5), dtype=np.uint8)
    packed[:, 0] = groups[:, 0] >> 2
    packed[:, 1] = ((groups[:, 0] & 0x03) << 6) | (groups[:, 1] >> 4)
    packed[:, 2] = ((groups[:, 1] & 0x0F) << 4) | (groups[:, 2] >> 6)
    packed[:, 3] = ((groups[:, 2] & 0x3F) << 2) | (groups[:, 3] >> 8)
    packed[:, 4] = groups[:, 3] & 0xFF
    return packed.tobytes()


def _write_archive_ascii(payload: bytearray, offset: int, value: int) -> None:
    encoded = str(value).encode("ascii")
    payload[offset + 30 : offset + 30 + len(encoded)] = encoded


def _write_seviri_fixture(path) -> None:
    n_lines = 2
    payload = bytearray(ARCHIVE_HEADER_BYTES + n_lines * LINE_RECORD_BYTES)
    payload[:10] = b"FormatName"

    _write_archive_ascii(payload, 4474, 1855)
    _write_archive_ascii(payload, 4554, 1856)
    _write_archive_ascii(payload, 4634, 1)
    _write_archive_ascii(payload, 4714, VISIR_NUM_COLUMNS)
    _write_archive_ascii(payload, 4794, n_lines)
    _write_archive_ascii(payload, 4874, VISIR_NUM_COLUMNS)

    struct.pack_into(">H", payload, 5153, 322)
    struct.pack_into(">f", payload, 392046, 45.5)
    struct.pack_into(">f", payload, 392058, 3.0)
    struct.pack_into(">f", payload, 392062, 3.0)
    for index in range(12):
        slope = 0.01 if index == CHANNEL_INDEX["VIS006"] else 0.0
        if index == CHANNEL_INDEX["IR_108"]:
            slope = 0.1
        struct.pack_into(">d", payload, 392218 + index * 16, slope)
        struct.pack_into(">d", payload, 392218 + index * 16 + 8, 0.0)
    payload[413297] = 2
    struct.pack_into(">d", payload, 413298, 6378.137)
    struct.pack_into(">d", payload, 413306, 6356.7523)
    struct.pack_into(">d", payload, 413314, 6356.7523)

    visible = np.full((n_lines, VISIR_NUM_COLUMNS), 10, dtype=np.uint16)
    infrared = np.full((n_lines, VISIR_NUM_COLUMNS), 900, dtype=np.uint16)
    visible[0, 0] = 0
    visible[1, -1] = 20
    infrared[0, 0] = 0
    infrared[1, -1] = 1000

    for row in range(n_lines):
        line_offset = ARCHIVE_HEADER_BYTES + row * LINE_RECORD_BYTES
        for channel_name, counts in (
            ("VIS006", visible[row]),
            ("IR_108", infrared[row]),
        ):
            start = (
                line_offset
                + CHANNEL_INDEX[channel_name] * VISIR_RECORD_BYTES
                + VISIR_LINE_DATA_OFFSET
            )
            packed = _pack_10bit(counts)
            assert len(packed) == VISIR_LINE_BYTES
            payload[start : start + VISIR_LINE_BYTES] = packed

    path.write_bytes(payload)


def test_seviri_loader_decodes_visible_and_ir_from_shared_native_bundle(tmp_path):
    source = tmp_path / "meteosat9_fixture.nat"
    _write_seviri_fixture(source)

    visible = load_seviri_raster(source, "Channel02")
    infrared = load_seviri_raster(source, "Channel13")

    assert visible.channel_name == "VIS006"
    assert infrared.channel_name == "IR_108"
    assert visible.values.shape == (2, VISIR_NUM_COLUMNS)
    assert visible.values[0, 0] == pytest.approx(np.pi * 0.2 / 65.2065)
    assert np.isnan(visible.values[-1, -1])
    assert 250.0 < float(infrared.values[0, 0]) < 350.0
    assert np.isnan(infrared.values[-1, -1])
    assert visible.src_crs.to_dict()["lon_0"] == 45.5
    assert visible.src_transform.a > 0.0
    assert visible.src_transform.e < 0.0


def _scalar_variable(group, name: str, value: float) -> None:
    variable = group.createVariable(name, "f8")
    variable.assignValue(value)


def _write_fci_chunk(path, start_row: int, ir: np.ndarray, visible: np.ndarray) -> None:
    rows, cols = ir.shape
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("scalar", 1)
        dataset.createDimension("rows", rows)
        dataset.createDimension("cols", cols)
        data_group = dataset.createGroup("data")
        projection = data_group.createVariable(
            "mtg_geos_projection", "i4", ("scalar",)
        )
        projection.perspective_point_height = 35_786_400.0
        projection.longitude_of_projection_origin = 0.0
        projection.sweep_angle_axis = "y"
        projection.semi_major_axis = 6_378_137.0
        projection.semi_minor_axis = 6_356_752.3

        for channel_name, radiance in (("ir_105", ir), ("vis_06", visible)):
            channel_group = data_group.createGroup(channel_name)
            measured = channel_group.createGroup("measured")
            for name, value in (
                ("start_position_row", start_row),
                ("end_position_row", start_row + rows - 1),
                ("start_position_column", 1),
                ("end_position_column", cols),
            ):
                _scalar_variable(measured, name, value)

            x_axis = measured.createVariable("x", "i4", ("cols",))
            x_axis.scale_factor = -0.01
            x_axis.add_offset = 0.025
            y_axis = measured.createVariable("y", "i4", ("rows",))
            y_axis.scale_factor = 0.01
            y_axis.add_offset = -0.025
            radiance_var = measured.createVariable(
                "effective_radiance", "f4", ("rows", "cols")
            )
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="Setting the shape on a NumPy array has been deprecated",
                    category=DeprecationWarning,
                )
                radiance_var[:] = radiance

            if channel_name == "ir_105":
                _scalar_variable(
                    measured, "radiance_to_bt_conversion_constant_c1", 1.19104273e-5
                )
                _scalar_variable(
                    measured, "radiance_to_bt_conversion_constant_c2", 1.43877523
                )
                _scalar_variable(
                    measured, "radiance_to_bt_conversion_coefficient_a", 1.0
                )
                _scalar_variable(
                    measured, "radiance_to_bt_conversion_coefficient_b", 0.0
                )
                _scalar_variable(
                    measured,
                    "radiance_to_bt_conversion_coefficient_wavenumber",
                    930.0,
                )
            else:
                _scalar_variable(
                    measured, "channel_effective_solar_irradiance", 100.0
                )


def test_fci_loader_stitches_body_chunks_and_calibrates_shared_channels(tmp_path):
    first = tmp_path / "FCI-1C-RRAD-FDHSI-CHK-BODY-0001.nc"
    second = tmp_path / "FCI-1C-RRAD-FDHSI-CHK-BODY-0002.nc"
    _write_fci_chunk(
        first,
        1,
        np.array([[80.0, 90.0, 100.0, 110.0], [90.0, 100.0, 110.0, 120.0]]),
        np.full((2, 4), 1.0),
    )
    _write_fci_chunk(
        second,
        3,
        np.array(
            [[100.0, 110.0, 120.0, 130.0], [110.0, 120.0, 130.0, 140.0]]
        ),
        np.full((2, 4), 2.0),
    )

    rasters = load_fci_rasters(
        [second, first],
        ["Channel13", "Channel02"],
        max_grid=4,
    )

    infrared = rasters["Channel13"]
    visible = rasters["Channel02"]
    assert infrared.channel_name == "ir_105"
    assert visible.channel_name == "vis_06"
    assert infrared.values.shape == (4, 4)
    assert np.isfinite(infrared.values).all()
    assert 250.0 < float(infrared.values.min()) < 350.0
    assert visible.values[0, 0] == pytest.approx(np.pi * 2.0 / 100.0)
    assert visible.values[-1, 0] == pytest.approx(np.pi * 1.0 / 100.0)
    assert infrared.src_transform.a > 0.0
    assert infrared.src_transform.e < 0.0
    assert infrared.src_crs.to_dict()["lon_0"] == 0

    decimated = load_fci_rasters(
        [second, first],
        ["Channel13"],
        max_grid=2,
    )["Channel13"]
    assert decimated.values.shape == (2, 2)
    assert np.isfinite(decimated.values).all()
    assert decimated.src_transform.a > infrared.src_transform.a
    assert satellite_v2_render_version_for_satellite("meteosat12") == "products-fci5"


def test_fci_loader_serializes_native_netcdf_access_across_zoom_keys(monkeypatch):
    active = 0
    peak = 0
    guard = threading.Lock()

    def fake_load(paths, requested, max_grid):
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with guard:
            active -= 1
        return {channel: max_grid for channel in requested}

    monkeypatch.setattr(fci_nc, "_load_fci_rasters_serialized", fake_load)
    body_chunk = "FCI-1C-RRAD-FDHSI-CHK-BODY-0001.nc"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda max_grid: load_fci_rasters(
                    [body_chunk], ["Channel13"], max_grid=max_grid
                ),
                (2048, 4096),
            )
        )

    assert results == [{"Channel13": 2048}, {"Channel13": 4096}]
    assert peak == 1


def test_eumetsat_seviri_catalog_uses_shared_bundle_for_composite(monkeypatch):
    monkeypatch.setattr(
        provider_eumetsat,
        "_search_products",
        lambda *_args, **_kwargs: [
            {
                "id": "MSG-SEVIRI-FIXTURE",
                "properties": {
                    "date": "2026-08-07T12:07:43Z/2026-08-07T12:12:43Z",
                    "productInformation": {"size": 123_456},
                },
            }
        ],
    )

    frames = provider_eumetsat.list_recent_frames(
        "meteosat9",
        "FULLDISK",
        "NighttimeMicrophysics",
        hours=1,
        max_frames=5,
    )

    channels = source_channels_for_product("NighttimeMicrophysics")
    assert [frame.frame_key for frame in frames] == ["20260807T120000Z"]
    assert frames[0].timestamp_utc == "2026-08-07T12:00:00Z"
    assert frames[0].source_keys == {
        channel: "MSG-SEVIRI-FIXTURE" for channel in channels
    }
    assert frames[0].file_sizes == {channel: 123_456 for channel in channels}


def test_eumetsat_fci_catalog_skips_products_without_body_chunks(monkeypatch):
    monkeypatch.setattr(
        provider_eumetsat,
        "_search_products",
        lambda *_args, **_kwargs: [
            {
                "id": "FCI-COMPLETE",
                "properties": {
                    "date": "2026-08-07T12:22:00Z/2026-08-07T12:32:00Z",
                    "productInformation": {"size": 987_654},
                    "links": {
                        "sip-entries": [
                            {
                                "title": "FCI-1C-RRAD-FDHSI-CHK-BODY-0001.nc",
                                "href": "https://example.invalid/body-1.nc",
                            }
                        ]
                    },
                },
            },
            {
                "id": "FCI-INCOMPLETE",
                "properties": {
                    "date": "2026-08-07T12:37:00Z/2026-08-07T12:47:00Z",
                    "productInformation": {"size": 100},
                    "links": {"sip-entries": []},
                },
            },
        ],
    )

    frames = provider_eumetsat.list_recent_frames(
        "meteosat12",
        "FULLDISK",
        "Channel13",
        hours=1,
        max_frames=5,
    )

    assert [frame.frame_key for frame in frames] == ["20260807T121500Z"]
    assert frames[0].source_key == "FCI-COMPLETE"
    assert frames[0].source_keys == {"Channel13": "FCI-COMPLETE"}
