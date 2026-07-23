"""Native MTG FCI Level 1c NetCDF chunk loader.

Initial support is scoped to Meteosat-12 Full Disk IR rendering. EUMETSAT FCI
frames arrive as multiple NetCDF body chunks; each chunk contains all channels
for one strip of the disk. This module stitches one requested channel into the
SourceRaster-compatible geostationary grid used by the shared tile renderer
(north-up rows via flip; columns are already west→east in the L1c layout).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import netCDF4
import numpy as np
from rasterio.crs import CRS as RioCRS
from rasterio.transform import from_bounds as rio_from_bounds

from config.satellite_v2_config import (
    SATELLITE_V2_FCI_MAX_GRID,
    fci_channel_for_source_channel,
)


@dataclass(frozen=True)
class FciRaster:
    values: np.ndarray
    src_transform: object
    src_crs: object
    channel_name: str


@dataclass
class _FciChannelState:
    channel_name: str
    strips: list[tuple[int, np.ndarray]] = field(default_factory=list)
    x_attrs: dict | None = None
    y_attrs: dict | None = None
    projection_attrs: dict | None = None
    full_cols: int = 0
    full_rows: int = 0
    stride: int = 1
    offset: int = 0
    out_cols: int = 0


def _normalize_fci_channel(channel: str) -> str:
    value = str(channel or "").strip().lower()
    if value in {
        "vis_04",
        "vis_05",
        "vis_06",
        "vis_08",
        "vis_09",
        "nir_13",
        "nir_16",
        "nir_22",
        "ir_38",
        "wv_63",
        "wv_73",
        "ir_87",
        "ir_97",
        "ir_105",
        "ir_123",
        "ir_133",
    }:
        return value
    return fci_channel_for_source_channel(channel)


def _as_float(value) -> float:
    array = np.asarray(value)
    return float(array.reshape(-1)[0])


def _scaled_axis(attrs: dict, count: int) -> np.ndarray:
    scale = float(attrs["scale_factor"])
    offset = float(attrs["add_offset"])
    packed = np.arange(1, count + 1, dtype=np.float64)
    return packed * scale + offset


def _calibrate_radiance(radiance: np.ndarray, measured, channel_name: str) -> np.ndarray:
    if channel_name.startswith(("ir_", "wv_")):
        c1 = _as_float(measured.variables["radiance_to_bt_conversion_constant_c1"][:])
        c2 = _as_float(measured.variables["radiance_to_bt_conversion_constant_c2"][:])
        coef_a = _as_float(
            measured.variables["radiance_to_bt_conversion_coefficient_a"][:]
        )
        coef_b = _as_float(
            measured.variables["radiance_to_bt_conversion_coefficient_b"][:]
        )
        wavenumber = _as_float(
            measured.variables["radiance_to_bt_conversion_coefficient_wavenumber"][:]
        )
        with np.errstate(divide="ignore", invalid="ignore"):
            effective_t = (c2 * wavenumber) / np.log(
                (c1 * wavenumber**3 / radiance) + 1.0
            )
            values = ((effective_t - coef_b) / coef_a).astype(np.float32)
        values[(radiance <= 0.0) | ~np.isfinite(values)] = np.nan
        return values

    solar = _as_float(measured.variables["channel_effective_solar_irradiance"][:])
    values = (np.pi * radiance / solar).astype(np.float32)
    values[(radiance <= 0.0) | ~np.isfinite(values)] = np.nan
    return values


def _chunk_paths(paths: Sequence[str | Path]) -> list[Path]:
    result = sorted(Path(path) for path in paths if "CHK-BODY" in Path(path).name)
    if not result:
        raise ValueError("No FCI CHK-BODY NetCDF chunks were provided.")
    return result

def load_fci_rasters(
    chunk_files: Sequence[str | Path],
    channels: Sequence[str],
    max_grid: int = SATELLITE_V2_FCI_MAX_GRID,
) -> dict[str, FciRaster]:
    """Load multiple FCI channels while opening each body chunk only once."""
    paths = _chunk_paths(chunk_files)
    requested = [str(channel) for channel in channels]
    if not requested:
        raise ValueError("No FCI channels were requested.")
    states = {
        channel: _FciChannelState(_normalize_fci_channel(channel))
        for channel in requested
    }

    for path in paths:
        with netCDF4.Dataset(path) as ds:
            data_group = ds.groups["data"]
            projection = data_group.variables["mtg_geos_projection"]
            projection_attrs = {
                name: getattr(projection, name) for name in projection.ncattrs()
            }
            for state in states.values():
                if state.channel_name not in data_group.groups:
                    raise ValueError(
                        f"FCI chunk is missing channel {state.channel_name}: {path}"
                    )
                measured = data_group.groups[state.channel_name].groups["measured"]
                start_row = int(np.asarray(measured.variables["start_position_row"][:]))
                end_row = int(np.asarray(measured.variables["end_position_row"][:]))
                start_col = int(np.asarray(measured.variables["start_position_column"][:]))
                end_col = int(np.asarray(measured.variables["end_position_column"][:]))
                if start_col != 1:
                    raise ValueError(f"FCI partial-width chunks are not supported: {path}")
                if state.full_cols == 0:
                    state.full_cols = end_col
                    state.stride = max(1, end_col // max(1, int(max_grid)))
                    state.offset = state.stride // 2
                    state.out_cols = len(range(state.offset, state.full_cols, state.stride))
                elif end_col != state.full_cols:
                    raise ValueError(
                        f"FCI chunk width mismatch ({end_col} vs {state.full_cols}): {path}"
                    )
                state.full_rows = max(state.full_rows, end_row)
                state.projection_attrs = projection_attrs
                if state.x_attrs is None:
                    x_var = measured.variables["x"]
                    y_var = measured.variables["y"]
                    state.x_attrs = {
                        name: getattr(x_var, name) for name in x_var.ncattrs()
                    }
                    state.y_attrs = {
                        name: getattr(y_var, name) for name in y_var.ncattrs()
                    }

                first_sampled = (start_row - 1) + (
                    (state.offset - (start_row - 1)) % state.stride
                )
                if first_sampled > end_row - 1:
                    continue
                radiance = np.ma.filled(
                    measured.variables["effective_radiance"][:], np.nan
                ).astype(np.float32)
                if state.stride > 1:
                    local_first = first_sampled - (start_row - 1)
                    radiance = radiance[
                        local_first::state.stride, state.offset::state.stride
                    ]
                calibrated = _calibrate_radiance(
                    radiance, measured, state.channel_name
                )
                expected_rows = (
                    (end_row - 1 - first_sampled) // state.stride + 1
                )
                if (
                    calibrated.shape[0] != expected_rows
                    or calibrated.shape[1] != state.out_cols
                ):
                    raise ValueError(
                        f"FCI chunk shape mismatch for rows {start_row}-{end_row}: "
                        f"{calibrated.shape}, expected ({expected_rows}, {state.out_cols})."
                    )
                state.strips.append(
                    ((first_sampled - state.offset) // state.stride, calibrated)
                )

    results: dict[str, FciRaster] = {}
    for channel, state in states.items():
        if (
            state.x_attrs is None
            or state.y_attrs is None
            or state.projection_attrs is None
        ):
            raise ValueError("FCI chunks did not expose projection metadata.")
        out_rows = len(range(state.offset, state.full_rows, state.stride))
        values_raw = np.full(
            (out_rows, state.out_cols), np.nan, dtype=np.float32
        )
        for out_row0, strip in state.strips:
            values_raw[out_row0 : out_row0 + strip.shape[0], :] = strip

        values = values_raw[::-1, :]
        projection_attrs = state.projection_attrs
        height = float(projection_attrs["perspective_point_height"])
        x_raw = _scaled_axis(state.x_attrs, state.full_cols)[state.offset::state.stride]
        y_raw = _scaled_axis(state.y_attrs, state.full_rows)[state.offset::state.stride]
        x_centers = -(x_raw * height)
        y_centers = y_raw[::-1] * height
        x_half = float(np.nanmedian(np.diff(x_centers))) / 2.0
        y_half = abs(float(np.nanmedian(np.diff(y_centers)))) / 2.0
        src_transform = rio_from_bounds(
            float(x_centers[0] - x_half),
            float(y_centers[-1] - y_half),
            float(x_centers[-1] + x_half),
            float(y_centers[0] + y_half),
            state.out_cols,
            out_rows,
        )
        proj4 = (
            f"+proj=geos +h={height:.3f} "
            f"+lon_0={float(projection_attrs['longitude_of_projection_origin'])} "
            f"+sweep={projection_attrs.get('sweep_angle_axis', 'y')} "
            f"+a={float(projection_attrs['semi_major_axis']):.3f} "
            f"+b={float(projection_attrs['semi_minor_axis']):.3f} +units=m +no_defs"
        )
        results[channel] = FciRaster(
            values=values,
            src_transform=src_transform,
            src_crs=RioCRS.from_proj4(proj4),
            channel_name=state.channel_name,
        )
    return results


def load_fci_raster(
    chunk_files: Sequence[str | Path],
    channel: str,
    max_grid: int = SATELLITE_V2_FCI_MAX_GRID,
) -> FciRaster:
    """Load one FCI channel through the shared batch implementation."""
    return load_fci_rasters(chunk_files, (channel,), max_grid=max_grid)[str(channel)]
