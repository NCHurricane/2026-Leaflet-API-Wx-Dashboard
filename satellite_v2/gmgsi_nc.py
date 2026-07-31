"""NOAA GMGSI global-mosaic NetCDF calibration and georeferencing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from pyproj import Transformer
from rasterio.crs import CRS as RioCRS
from rasterio.transform import from_bounds as rio_from_bounds
import xarray as xr


_TITLE_FOR_SOURCE_CHANNEL = {
    "Channel02": "GLOBCOMPVIS",
    "Channel07": "GLOBCOMPSIR",
    "Channel09": "GLOBCOMPWV",
    "Channel13": "GLOBCOMPLIR",
}


@dataclass(frozen=True)
class GmgsiRaster:
    values: np.ndarray
    src_transform: object
    src_crs: object
    observation_time: datetime


def _observation_time(dataset: xr.Dataset) -> datetime:
    if "time" in dataset and dataset["time"].size:
        stamp = np.datetime_as_string(dataset["time"].values.reshape(-1)[0], unit="s")
        return datetime.fromisoformat(f"{stamp}+00:00").astimezone(timezone.utc)
    text = str(dataset.attrs.get("time_coverage_start") or "").strip()
    if not text:
        raise ValueError("GMGSI source is missing its observation time.")
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def _brightness_count_to_kelvin(counts: np.ndarray) -> np.ndarray:
    """Decode the operational 8-bit McIDAS/GINI brightness-temperature scale."""
    return np.where(counts <= 176.0, 330.0 - counts / 2.0, 418.0 - counts)


def load_gmgsi_raster(dataset: xr.Dataset, source_channel: str) -> GmgsiRaster:
    expected_title = _TITLE_FOR_SOURCE_CHANNEL.get(str(source_channel or ""))
    if expected_title is None:
        raise ValueError(f"No GMGSI product mapping for '{source_channel}'.")
    title = str(dataset.attrs.get("title") or "").strip().upper()
    if title != expected_title:
        raise ValueError(
            f"GMGSI source product is {title or 'unknown'}, expected {expected_title}."
        )
    if "data" not in dataset or "dqf" not in dataset:
        raise ValueError("GMGSI source is missing data/dqf variables.")
    if "lon" not in dataset or "lat" not in dataset:
        raise ValueError("GMGSI source is missing lon/lat coordinates.")

    image = dataset["data"]
    quality = dataset["dqf"]
    if "time" in image.dims:
        image = image.isel(time=0)
    if "time" in quality.dims:
        quality = quality.isel(time=0)
    if image.ndim != 2 or quality.shape != image.shape:
        raise ValueError("GMGSI data/dqf arrays must be matching 2D grids.")

    y_dim, x_dim = image.dims
    lon_var = dataset["lon"]
    lat_var = dataset["lat"]
    lon = np.asarray(
        lon_var.isel({y_dim: 0}).values if lon_var.ndim == 2 else lon_var.values,
        dtype=np.float64,
    )
    lat = np.asarray(
        lat_var.isel({x_dim: 0}).values if lat_var.ndim == 2 else lat_var.values,
        dtype=np.float64,
    )
    if lon.size != image.shape[1] or lat.size != image.shape[0]:
        raise ValueError("GMGSI coordinate dimensions do not match the image grid.")

    x_order = np.argsort(lon)
    y_order = np.argsort(lat)[::-1]
    counts = np.asarray(image.values, dtype=np.float32)[np.ix_(y_order, x_order)]
    dqf = np.asarray(quality.values, dtype=np.float32)[np.ix_(y_order, x_order)]
    valid = np.isfinite(counts) & np.isfinite(dqf) & (dqf == 0.0)

    if source_channel == "Channel02":
        values = counts / np.float32(255.0)
    else:
        values = _brightness_count_to_kelvin(counts)
    values = np.where(valid, values, np.nan).astype(np.float32)

    # GMGSI publishes lon/lat coordinate arrays, but the latitude spacing is
    # regular in Web Mercator. Deriving the y bounds from those coordinates
    # preserves the native 8 km grid and avoids a curvilinear resample.
    to_mercator = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    _, y_m = to_mercator.transform(np.zeros_like(lat), lat)
    y_sorted = np.asarray(y_m, dtype=np.float64)[y_order]
    y_step = float(np.median(np.abs(np.diff(y_sorted))))
    world_half = 20037508.342789244
    src_transform = rio_from_bounds(
        -world_half,
        float(y_sorted[-1]) - y_step / 2.0,
        world_half,
        float(y_sorted[0]) + y_step / 2.0,
        values.shape[1],
        values.shape[0],
    )
    return GmgsiRaster(
        values=values,
        src_transform=src_transform,
        src_crs=RioCRS.from_epsg(3857),
        observation_time=_observation_time(dataset),
    )
