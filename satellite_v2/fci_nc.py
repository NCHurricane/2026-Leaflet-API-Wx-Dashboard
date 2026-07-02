"""Native MTG FCI Level 1c NetCDF chunk loader.

Initial support is scoped to Meteosat-12 Full Disk IR rendering. EUMETSAT FCI
frames arrive as multiple NetCDF body chunks; each chunk contains all channels
for one strip of the disk. This module stitches one requested channel into the
SourceRaster-compatible geostationary grid used by the shared tile renderer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import netCDF4
import numpy as np
from rasterio.crs import CRS as RioCRS
from rasterio.transform import from_bounds as rio_from_bounds

from config.satellite_v2_config import fci_channel_for_source_channel


@dataclass(frozen=True)
class FciRaster:
    values: np.ndarray
    src_transform: object
    src_crs: object
    channel_name: str


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


def load_fci_raster(chunk_files: Sequence[str | Path], channel: str) -> FciRaster:
    """Load one FCI channel from a set of body chunk NetCDF files."""
    paths = _chunk_paths(chunk_files)
    channel_name = _normalize_fci_channel(channel)

    strips: list[tuple[int, int, np.ndarray]] = []
    x_attrs: dict | None = None
    y_attrs: dict | None = None
    projection_attrs: dict | None = None
    full_cols = 0
    full_rows = 0

    for path in paths:
        with netCDF4.Dataset(path) as ds:
            data_group = ds.groups["data"]
            if channel_name not in data_group.groups:
                raise ValueError(f"FCI chunk is missing channel {channel_name}: {path}")
            projection = data_group.variables["mtg_geos_projection"]
            projection_attrs = {name: getattr(projection, name) for name in projection.ncattrs()}
            measured = data_group.groups[channel_name].groups["measured"]
            start_row = int(np.asarray(measured.variables["start_position_row"][:]))
            end_row = int(np.asarray(measured.variables["end_position_row"][:]))
            start_col = int(np.asarray(measured.variables["start_position_column"][:]))
            end_col = int(np.asarray(measured.variables["end_position_column"][:]))
            if start_col != 1:
                raise ValueError(f"FCI partial-width chunks are not supported: {path}")
            radiance_var = measured.variables["effective_radiance"]
            radiance = np.ma.filled(radiance_var[:], np.nan).astype(np.float32)
            calibrated = _calibrate_radiance(radiance, measured, channel_name)
            strips.append((start_row, end_row, calibrated))
            full_rows = max(full_rows, end_row)
            full_cols = max(full_cols, end_col)
            if x_attrs is None:
                x_var = measured.variables["x"]
                y_var = measured.variables["y"]
                x_attrs = {name: getattr(x_var, name) for name in x_var.ncattrs()}
                y_attrs = {name: getattr(y_var, name) for name in y_var.ncattrs()}

    if x_attrs is None or y_attrs is None or projection_attrs is None:
        raise ValueError("FCI chunks did not expose projection metadata.")

    values_raw = np.full((full_rows, full_cols), np.nan, dtype=np.float32)
    for start_row, end_row, strip in strips:
        expected_rows = end_row - start_row + 1
        if strip.shape[0] != expected_rows or strip.shape[1] != full_cols:
            raise ValueError(
                f"FCI chunk shape mismatch for rows {start_row}-{end_row}: "
                f"{strip.shape}, expected ({expected_rows}, {full_cols})."
            )
        values_raw[start_row - 1 : end_row, :] = strip

    values = values_raw[::-1, ::-1]
    height = float(projection_attrs["perspective_point_height"])
    x_raw = _scaled_axis(x_attrs, full_cols)
    y_raw = _scaled_axis(y_attrs, full_rows)
    x_centers = x_raw[::-1] * height
    y_centers = y_raw[::-1] * height
    x_half = float(np.nanmedian(np.diff(x_centers))) / 2.0
    y_half = abs(float(np.nanmedian(np.diff(y_centers)))) / 2.0
    src_transform = rio_from_bounds(
        float(x_centers[0] - x_half),
        float(y_centers[-1] - y_half),
        float(x_centers[-1] + x_half),
        float(y_centers[0] + y_half),
        full_cols,
        full_rows,
    )
    proj4 = (
        f"+proj=geos +h={height:.3f} "
        f"+lon_0={float(projection_attrs['longitude_of_projection_origin'])} "
        f"+sweep={projection_attrs.get('sweep_angle_axis', 'y')} "
        f"+a={float(projection_attrs['semi_major_axis']):.3f} "
        f"+b={float(projection_attrs['semi_minor_axis']):.3f} +units=m +no_defs"
    )
    src_crs = RioCRS.from_proj4(proj4)
    return FciRaster(
        values=values,
        src_transform=src_transform,
        src_crs=src_crs,
        channel_name=channel_name,
    )
