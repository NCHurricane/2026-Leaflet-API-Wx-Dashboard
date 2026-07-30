"""GK2A AMI Level 1B NetCDF calibration and georeferencing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

import numpy as np
from rasterio.crs import CRS as RioCRS
from rasterio.transform import from_bounds as rio_from_bounds
import xarray as xr

from config.satellite_v2_config import ami_channel_for_source_channel


@dataclass(frozen=True)
class AmiRaster:
    values: np.ndarray
    src_transform: object
    src_crs: object
    observation_time: datetime
    satellite_longitude: float
    satellite_height_km: float
    channel_name: str


def _calibrate_brightness_temperature(
    dataset: xr.Dataset,
    counts: np.ndarray,
    valid: np.ndarray,
) -> np.ndarray:
    gain = float(dataset.attrs["DN_to_Radiance_Gain"])
    offset = float(dataset.attrs["DN_to_Radiance_Offset"])
    radiance = gain * counts.astype(np.float64) + offset
    radiance = np.where(valid & (radiance > 0.0), radiance, np.nan)

    wavelength_um = float(dataset.attrs["channel_center_wavelength"])
    wave_number = (10000.0 / wavelength_um) * 100.0
    light_speed = float(dataset.attrs["light_speed"])
    planck = float(dataset.attrs["Plank_constant_h"])
    boltzmann = float(dataset.attrs["Boltzmann_constant_k"])
    numerator = (2.0 * planck * light_speed * light_speed) * wave_number**3
    effective = ((planck * light_speed / boltzmann) * wave_number) / np.log(
        (numerator / (radiance * 1.0e-5)) + 1.0
    )
    c0 = float(dataset.attrs["Teff_to_Tbb_c0"])
    c1 = float(dataset.attrs["Teff_to_Tbb_c1"])
    c2 = float(dataset.attrs["Teff_to_Tbb_c2"])
    return np.asarray(c0 + c1 * effective + c2 * effective * effective, dtype=np.float32)


def load_ami_raster(dataset: xr.Dataset, source_channel: str) -> AmiRaster:
    expected_channel = ami_channel_for_source_channel(source_channel).upper()
    if str(dataset.attrs.get("instrument_name") or "").upper() != "AMI":
        raise ValueError("GK2A source is missing AMI instrument metadata.")
    if "image_pixel_values" not in dataset:
        raise ValueError("GK2A AMI source is missing image_pixel_values.")

    image = dataset["image_pixel_values"]
    channel_name = str(image.attrs.get("channel_name") or "").upper()
    if channel_name != expected_channel:
        raise ValueError(
            f"GK2A source channel is {channel_name or 'unknown'}, "
            f"expected {expected_channel}."
        )

    packed = np.asarray(image.values, dtype=np.uint16)
    valid_bits = int(image.attrs["number_of_valid_bits_per_pixel"])
    counts = packed & np.uint16((1 << valid_bits) - 1)
    valid = (packed & np.uint16(0xC000)) == 0
    values = _calibrate_brightness_temperature(dataset, counts, valid)

    rows, cols = values.shape
    equatorial_radius = float(dataset.attrs["earth_equatorial_radius"])
    polar_radius = float(dataset.attrs["earth_polar_radius"])
    perspective_height = (
        float(dataset.attrs["nominal_satellite_height"]) - equatorial_radius
    )
    longitude = math.degrees(float(dataset.attrs["sub_longitude"]))

    x_first = float(dataset.attrs["image_upperleft_x"]) * perspective_height
    x_last = float(dataset.attrs["image_lowerright_x"]) * perspective_height
    y_first = float(dataset.attrs["image_upperleft_y"]) * perspective_height
    y_last = float(dataset.attrs["image_lowerright_y"]) * perspective_height
    x_half = abs(x_last - x_first) / (2.0 * max(1, cols - 1))
    y_half = abs(y_first - y_last) / (2.0 * max(1, rows - 1))
    src_transform = rio_from_bounds(
        min(x_first, x_last) - x_half,
        min(y_first, y_last) - y_half,
        max(x_first, x_last) + x_half,
        max(y_first, y_last) + y_half,
        cols,
        rows,
    )
    src_crs = RioCRS.from_proj4(
        f"+proj=geos +h={perspective_height:.3f} +lon_0={longitude:.6f} "
        f"+sweep=y +a={equatorial_radius:.3f} +b={polar_radius:.3f} "
        "+units=m +no_defs"
    )

    timestamp = datetime.strptime(
        str(dataset.attrs["mission_reference_time"]), "%Y%m%d_%H%M%S"
    ).replace(tzinfo=timezone.utc)
    return AmiRaster(
        values=values,
        src_transform=src_transform,
        src_crs=src_crs,
        observation_time=timestamp,
        satellite_longitude=longitude,
        satellite_height_km=perspective_height / 1000.0,
        channel_name=channel_name,
    )
