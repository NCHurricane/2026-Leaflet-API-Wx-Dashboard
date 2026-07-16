"""Satellite v2 product rendering recipes.

The formulas mirror the v1 product registry while operating directly on tile-sized
sample arrays from the v2 Web Mercator renderer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from config.satellite_colormaps import IR_CMAP, IR_NORM

Image.MAX_IMAGE_PIXELS = None

_SCALAR_REFLECTANCE_BLACK_POINT = 0.02
_SCALAR_REFLECTANCE_WHITE_POINT = 0.90
_CIRA_VISIBLE_BLACK_POINT = 0.0223
_CIRA_VISIBLE_LOG_ROOT = np.log10(_CIRA_VISIBLE_BLACK_POINT)
_CIRA_VISIBLE_DENOMINATOR = (1.0 - _CIRA_VISIBLE_LOG_ROOT) * 0.75

# ABI molecular optical depths used by the corrected-reflectance (CREFL)
# algorithm for its 0.47, 0.64, and 0.86 micron bands.  The compact
# single-scattering correction below removes the dominant blue atmospheric
# path radiance without adding a large runtime dependency or external LUT.
_ABI_RAYLEIGH_OPTICAL_DEPTH = {
    "Channel01": 0.184720,
    "Channel02": 0.052349,
    "Channel03": 0.015845,
}
_ABI_RAYLEIGH_CORRECTION_STRENGTH = 0.55
_EARTH_EQUATORIAL_RADIUS_KM = 6378.137

# EUMETSAT publishes its own stretch windows for SEVIRI/FCI RGB recipes
# ("Compilation of RGB Recipes") that differ from the NOAA/CIRA windows used
# for GOES ABI/Himawari AHI. Apply the EUMETSAT windows only for those two
# instruments; ABI/AHI (and unspecified/legacy callers) keep the CIRA windows.
_EUMETSAT_RECIPE_INSTRUMENTS = frozenset({"SEVIRI", "FCI"})


def normalize(value: np.ndarray, lower_limit: float, upper_limit: float, clip: bool = True) -> np.ndarray:
    result = (value - lower_limit) / (upper_limit - lower_limit)
    if clip:
        result = np.clip(result, 0.0, 1.0)
    return result.astype(np.float32)


def gamma_correction(value: np.ndarray, gamma: float) -> np.ndarray:
    if gamma == 1:
        return value.astype(np.float32)
    return np.power(value, 1.0 / gamma).astype(np.float32)


def reflectance(values: np.ndarray, gamma: float | None = None) -> np.ndarray:
    data = np.asarray(values, dtype=np.float32)
    finite = np.isfinite(data)
    if finite.any() and float(np.nanmax(data[finite])) > 1.5:
        data = data / 100.0
    data = np.clip(data, 0.0, 1.0)
    if gamma is not None:
        data = np.power(data, gamma)
    return data.astype(np.float32)


def visible_reflectance(values: np.ndarray) -> np.ndarray:
    return reflectance(values, gamma=0.45)


def _geocolor_reflectance(values: np.ndarray) -> np.ndarray:
    """Normalize reflectance while retaining bright-cloud values above one."""
    data = np.asarray(values, dtype=np.float32)
    finite = np.isfinite(data)
    if finite.any() and float(np.nanmax(data[finite])) > 2.0:
        data = data / 100.0
    return np.clip(data, 0.0, 1.6).astype(np.float32)


def cira_visible_stretch(values: np.ndarray) -> np.ndarray:
    """Apply CIRA's logarithmic visible-channel display stretch."""
    data = _geocolor_reflectance(values)
    with np.errstate(divide="ignore", invalid="ignore"):
        data = (np.log10(np.clip(data, np.finfo(np.float32).eps, 1.6))
                - _CIRA_VISIBLE_LOG_ROOT) / _CIRA_VISIBLE_DENOMINATOR
    return np.clip(data, 0.0, 1.0).astype(np.float32)


def scalar_reflectance(values: np.ndarray) -> np.ndarray:
    """Apply a stable contrast stretch for scalar VIS/NIR display products."""
    data = reflectance(values)
    data = normalize(
        data,
        _SCALAR_REFLECTANCE_BLACK_POINT,
        _SCALAR_REFLECTANCE_WHITE_POINT,
    )
    return np.sqrt(data).astype(np.float32)


def _rgb(red: np.ndarray, green: np.ndarray, blue: np.ndarray) -> np.ndarray:
    return np.clip(np.dstack([red, green, blue]), 0.0, 1.0).astype(np.float32)


def _boost_saturation(rgb: np.ndarray, amount: float = 1.1) -> np.ndarray:
    luma = (0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2])
    return np.clip(luma[:, :, np.newaxis] + amount * (rgb - luma[:, :, np.newaxis]), 0.0, 1.0).astype(np.float32)


def _as_utc(observation_time: datetime) -> datetime:
    if observation_time.tzinfo is None:
        return observation_time.replace(tzinfo=timezone.utc)
    return observation_time.astimezone(timezone.utc)


def _solar_local_vectors(
    observation_time: datetime,
    lon_grid: np.ndarray,
    lat_grid: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return local east/north/up unit-vector components toward the sun."""
    when = _as_utc(observation_time)
    longitude_values = np.asarray(lon_grid, dtype=np.float32)
    latitude_values = np.asarray(lat_grid, dtype=np.float32)
    fractional_hour = (
        when.hour + when.minute / 60.0 + when.second / 3600.0
        + when.microsecond / 3_600_000_000.0
    )
    year_days = 366.0 if (
        when.year % 4 == 0 and (when.year % 100 != 0 or when.year % 400 == 0)
    ) else 365.0
    fractional_year = (
        2.0 * np.pi / year_days
        * (when.timetuple().tm_yday - 1.0 + (fractional_hour - 12.0) / 24.0)
    )
    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * np.cos(fractional_year)
        - 0.032077 * np.sin(fractional_year)
        - 0.014615 * np.cos(2.0 * fractional_year)
        - 0.040849 * np.sin(2.0 * fractional_year)
    )
    declination = (
        0.006918
        - 0.399912 * np.cos(fractional_year)
        + 0.070257 * np.sin(fractional_year)
        - 0.006758 * np.cos(2.0 * fractional_year)
        + 0.000907 * np.sin(2.0 * fractional_year)
        - 0.002697 * np.cos(3.0 * fractional_year)
        + 0.001480 * np.sin(3.0 * fractional_year)
    )
    solar_minutes = (
        fractional_hour * 60.0 + equation_of_time + 4.0 * longitude_values
    ) % 1440.0
    hour_angle = np.deg2rad(solar_minutes / 4.0 - 180.0)
    latitude = np.deg2rad(latitude_values)
    cos_declination = np.cos(declination)
    sun_east = -cos_declination * np.sin(hour_angle)
    sun_north = (
        np.cos(latitude) * np.sin(declination)
        - np.sin(latitude) * cos_declination * np.cos(hour_angle)
    )
    sun_up = (
        np.sin(latitude) * np.sin(declination)
        + np.cos(latitude) * cos_declination * np.cos(hour_angle)
    )
    return (
        sun_east.astype(np.float32),
        sun_north.astype(np.float32),
        sun_up.astype(np.float32),
    )


def _satellite_local_vectors(
    lon_grid: np.ndarray,
    lat_grid: np.ndarray,
    satellite_longitude: float,
    satellite_height_km: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return local east/north/up unit-vector components toward a GEO satellite."""
    longitude = np.deg2rad(np.asarray(lon_grid, dtype=np.float32))
    latitude = np.deg2rad(np.asarray(lat_grid, dtype=np.float32))
    satellite_lon = np.deg2rad(float(satellite_longitude))
    satellite_radius = _EARTH_EQUATORIAL_RADIUS_KM + float(satellite_height_km)

    observer_x = _EARTH_EQUATORIAL_RADIUS_KM * np.cos(latitude) * np.cos(longitude)
    observer_y = _EARTH_EQUATORIAL_RADIUS_KM * np.cos(latitude) * np.sin(longitude)
    observer_z = _EARTH_EQUATORIAL_RADIUS_KM * np.sin(latitude)
    delta_x = satellite_radius * np.cos(satellite_lon) - observer_x
    delta_y = satellite_radius * np.sin(satellite_lon) - observer_y
    delta_z = -observer_z

    east = -np.sin(longitude) * delta_x + np.cos(longitude) * delta_y
    north = (
        -np.sin(latitude) * np.cos(longitude) * delta_x
        - np.sin(latitude) * np.sin(longitude) * delta_y
        + np.cos(latitude) * delta_z
    )
    up = (
        np.cos(latitude) * np.cos(longitude) * delta_x
        + np.cos(latitude) * np.sin(longitude) * delta_y
        + np.sin(latitude) * delta_z
    )
    magnitude = np.sqrt(east * east + north * north + up * up)
    magnitude = np.where(magnitude > 0.0, magnitude, 1.0)
    return (
        (east / magnitude).astype(np.float32),
        (north / magnitude).astype(np.float32),
        (up / magnitude).astype(np.float32),
    )


def _rayleigh_correct_reflectance(
    values: np.ndarray,
    channel: str,
    solar_vectors: tuple[np.ndarray, np.ndarray, np.ndarray],
    satellite_vectors: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> np.ndarray:
    """Remove a bounded single-scattering Rayleigh path-reflectance estimate."""
    data = _geocolor_reflectance(values)
    optical_depth = _ABI_RAYLEIGH_OPTICAL_DEPTH[channel]
    sun_east, sun_north, sun_up = solar_vectors
    sat_east, sat_north, sat_up = satellite_vectors

    mu_sun = np.clip(sun_up, 0.05, 1.0)
    mu_view = np.clip(sat_up, 0.05, 1.0)
    scattering_cosine = np.clip(
        sun_east * sat_east + sun_north * sat_north + sun_up * sat_up,
        -1.0,
        1.0,
    )
    phase = 0.75 * (1.0 + scattering_cosine * scattering_cosine)
    air_mass = 1.0 / mu_sun + 1.0 / mu_view
    path_reflectance = (
        0.25
        * phase
        * (1.0 - np.exp(-optical_depth * air_mass))
        / (mu_sun + mu_view)
    )

    # Fade the correction from full strength at 70 degrees solar zenith to
    # zero at the terminator, where the single-scattering approximation is
    # least stable and the product is transitioning into the night recipe.
    correction_weight = np.clip(sun_up / np.cos(np.deg2rad(70.0)), 0.0, 1.0)
    correction_weight = correction_weight * correction_weight * (
        3.0 - 2.0 * correction_weight
    )
    corrected = (
        data
        - _ABI_RAYLEIGH_CORRECTION_STRENGTH
        * path_reflectance
        * correction_weight
    )
    return np.clip(corrected, 0.0, 1.6).astype(np.float32)


def _solar_day_weight(
    observation_time: datetime,
    lon_grid: np.ndarray,
    lat_grid: np.ndarray,
) -> np.ndarray:
    """Blend smoothly from the daytime recipe at 80° SZA to night at 95°."""
    sun_up = _solar_local_vectors(observation_time, lon_grid, lat_grid)[2]
    return _solar_day_weight_from_up(sun_up)


def _solar_day_weight_from_up(sun_up: np.ndarray) -> np.ndarray:
    night_edge = np.cos(np.deg2rad(95.0))
    day_edge = np.cos(np.deg2rad(80.0))
    weight = np.clip((sun_up - night_edge) / (day_edge - night_edge), 0.0, 1.0)
    return (weight * weight * (3.0 - 2.0 * weight)).astype(np.float32)


def _true_color(channels: dict[str, np.ndarray]) -> np.ndarray:
    red = visible_reflectance(channels["Channel02"])
    blue = visible_reflectance(channels["Channel01"])
    veggie = visible_reflectance(channels["Channel03"])
    green = np.clip(0.45 * red + 0.1 * veggie + 0.45 * blue, 0.0, 1.0)
    return _rgb(red, green, blue)


def _geocolor_day_rgb(
    channels: dict[str, np.ndarray],
    lon_grid: np.ndarray | None,
    lat_grid: np.ndarray | None,
    observation_time: datetime | None,
    satellite_longitude: float | None,
    satellite_height_km: float | None,
    instrument: str | None,
) -> tuple[np.ndarray, np.ndarray | None]:
    reflectances = {
        channel: _geocolor_reflectance(channels[channel])
        for channel in ("Channel01", "Channel02", "Channel03")
    }
    has_geometry = (
        str(instrument or "").upper() == "ABI"
        and lon_grid is not None
        and lat_grid is not None
        and observation_time is not None
        and satellite_longitude is not None
        and satellite_height_km is not None
    )
    solar_up = None
    if has_geometry:
        solar_vectors = _solar_local_vectors(
            observation_time, lon_grid, lat_grid
        )
        solar_up = solar_vectors[2]
        satellite_vectors = _satellite_local_vectors(
            lon_grid,
            lat_grid,
            satellite_longitude,
            satellite_height_km,
        )
        reflectances = {
            channel: _rayleigh_correct_reflectance(
                values, channel, solar_vectors, satellite_vectors
            )
            for channel, values in reflectances.items()
        }
        del solar_vectors, satellite_vectors

    red = reflectances["Channel02"]
    blue = reflectances["Channel01"]
    veggie = reflectances["Channel03"]
    # This is the established CIMSS/Kaba simulated-green approximation.  The
    # atmospheric correction is applied before the channels are combined.
    green = np.clip(0.45 * blue + 0.45 * red + 0.10 * veggie, 0.0, 1.0)
    stretched = _rgb(
        cira_visible_stretch(red),
        cira_visible_stretch(green),
        cira_visible_stretch(blue),
    )
    return _boost_saturation(stretched, amount=1.08), solar_up


def _geocolor_day_weight(
    day_rgb: np.ndarray,
    observation_time: datetime | None,
    lon_grid: np.ndarray | None,
    lat_grid: np.ndarray | None,
    solar_up: np.ndarray | None = None,
) -> np.ndarray:
    if solar_up is not None:
        return _solar_day_weight_from_up(solar_up)
    if observation_time is not None and lon_grid is not None and lat_grid is not None:
        return _solar_day_weight(observation_time, lon_grid, lat_grid)
    # Preserve legacy behavior for non-GOES sources that do not yet expose
    # frame-time metadata. GOES rendering always uses the solar geometry path.
    return np.clip((day_rgb[:, :, 0] - 0.06) / 0.16, 0.0, 1.0).astype(np.float32)


def _geocolor(
    channels: dict[str, np.ndarray],
    lon_grid: np.ndarray | None = None,
    lat_grid: np.ndarray | None = None,
    observation_time: datetime | None = None,
    satellite_longitude: float | None = None,
    satellite_height_km: float | None = None,
    instrument: str | None = None,
) -> np.ndarray:
    day_rgb, solar_up = _geocolor_day_rgb(
        channels,
        lon_grid,
        lat_grid,
        observation_time,
        satellite_longitude,
        satellite_height_km,
        instrument,
    )
    bt13 = channels["Channel13"]
    bt07 = channels.get("Channel07", bt13)

    high_cloud = normalize(bt13, 273.15, 193.15)
    low_cloud = normalize(bt13 - bt07, 1.0, 8.0)

    night_rgb = np.zeros((*bt13.shape, 3), dtype=np.float32)
    night_rgb[:, :, 0] = 0.03
    night_rgb[:, :, 1] = 0.06
    night_rgb[:, :, 2] = 0.16
    night_rgb *= 0.6

    cold_boost = normalize(bt13, 260.0, 200.0)
    night_rgb[:, :, 2] += 0.14 * cold_boost
    night_rgb[:, :, 0] += 0.28 * low_cloud
    night_rgb[:, :, 1] += 0.42 * low_cloud
    night_rgb[:, :, 2] += 0.60 * low_cloud
    for channel_index in range(3):
        night_rgb[:, :, channel_index] += 1.4 * high_cloud
    night_rgb = np.clip(night_rgb, 0.0, 1.0)

    day_weight = _geocolor_day_weight(
        day_rgb, observation_time, lon_grid, lat_grid, solar_up
    )
    blended = day_rgb * day_weight[:, :, np.newaxis] + \
        night_rgb * (1.0 - day_weight[:, :, np.newaxis])
    return np.clip(blended, 0.0, 1.0).astype(np.float32)


@lru_cache(maxsize=1)
def _load_black_marble_image() -> np.ndarray:
    path = Path(__file__).resolve().parent.parent / \
        "img" / "BlackMarble_2016_3km_geo.tif"
    if not path.exists():
        raise FileNotFoundError(f"Black Marble background not found: {path}")
    with Image.open(path) as image:
        rgb_image = image.convert("RGB")
        data = np.asarray(rgb_image, dtype=np.float32)
    if data.max() > 1.5:
        data = data / 255.0
    return np.clip(data, 0.0, 1.0).astype(np.float32)


def _sample_black_marble(lon_grid: np.ndarray, lat_grid: np.ndarray) -> np.ndarray:
    image = _load_black_marble_image()
    height, width = image.shape[:2]
    valid = np.isfinite(lon_grid) & np.isfinite(lat_grid)
    lon = ((lon_grid + 180.0) % 360.0) - 180.0
    lat = np.clip(lat_grid, -90.0, 90.0)

    col_f = ((lon + 180.0) / 360.0) * (width - 1)
    row_f = ((90.0 - lat) / 180.0) * (height - 1)
    col_f = np.where(valid, np.clip(col_f, 0.0, width - 1.0), 0.0)
    row_f = np.where(valid, np.clip(row_f, 0.0, height - 1.0), 0.0)

    row0 = np.floor(row_f).astype(np.int32)
    col0 = np.floor(col_f).astype(np.int32)
    row1 = np.clip(row0 + 1, 0, height - 1)
    col1 = np.clip(col0 + 1, 0, width - 1)
    dr = (row_f - row0).astype(np.float32)
    dc = (col_f - col0).astype(np.float32)

    sampled = np.empty((*lon_grid.shape, 3), dtype=np.float32)
    for channel_index in range(3):
        v00 = image[row0, col0, channel_index]
        v01 = image[row0, col1, channel_index]
        v10 = image[row1, col0, channel_index]
        v11 = image[row1, col1, channel_index]
        sampled[:, :, channel_index] = (
            (1.0 - dr) * (1.0 - dc) * v00
            + (1.0 - dr) * dc * v01
            + dr * (1.0 - dc) * v10
            + dr * dc * v11
        )
    sampled[~valid] = 0.0
    return sampled


def _geocolor_black_marble(
    channels: dict[str, np.ndarray],
    lon_grid: np.ndarray | None,
    lat_grid: np.ndarray | None,
    observation_time: datetime | None = None,
    satellite_longitude: float | None = None,
    satellite_height_km: float | None = None,
    instrument: str | None = None,
) -> np.ndarray:
    if lon_grid is None or lat_grid is None:
        return _geocolor(
            channels,
            observation_time=observation_time,
            satellite_longitude=satellite_longitude,
            satellite_height_km=satellite_height_km,
            instrument=instrument,
        )

    day_rgb, solar_up = _geocolor_day_rgb(
        channels,
        lon_grid,
        lat_grid,
        observation_time,
        satellite_longitude,
        satellite_height_km,
        instrument,
    )
    bt13 = channels["Channel13"]
    bt07 = channels.get("Channel07", bt13)

    high_cloud = normalize(bt13, 310.0, 190.0)
    low_cloud = normalize(bt13 - bt07, 0.5, 8.0)

    night_rgb = _sample_black_marble(lon_grid, lat_grid) * 0.5
    night_rgb[:, :, 0] += 0.30 * low_cloud + 1.0 * high_cloud
    night_rgb[:, :, 1] += 0.40 * low_cloud + 1.0 * high_cloud
    night_rgb[:, :, 2] += 0.50 * low_cloud + 1.1 * high_cloud
    night_rgb = gamma_correction(np.clip(night_rgb * 1.1, 0.0, 1.0), 0.8)

    day_weight = _geocolor_day_weight(
        day_rgb, observation_time, lon_grid, lat_grid, solar_up
    )
    blended = day_rgb * day_weight[:, :, np.newaxis] + \
        night_rgb * (1.0 - day_weight[:, :, np.newaxis])
    return np.clip(blended, 0.0, 1.0).astype(np.float32)


def _day_night_hybrid(channels: dict[str, np.ndarray]) -> np.ndarray:
    day_rgb = _true_color(channels)
    bt13 = channels["Channel13"]
    ir_rgba = IR_CMAP(IR_NORM(bt13)).astype(np.float32)
    result = np.array(day_rgb, copy=True)
    night_mask = day_rgb[:, :, 0] < 0.05
    result[night_mask] = ir_rgba[:, :, :3][night_mask]
    return np.clip(result, 0.0, 1.0).astype(np.float32)


def _sandwich(channels: dict[str, np.ndarray]) -> np.ndarray:
    visible = visible_reflectance(channels["Channel02"])
    base_rgb = _rgb(visible, visible, visible)
    bt13 = channels["Channel13"]
    ir_rgba = IR_CMAP(IR_NORM(bt13)).astype(np.float32)
    alpha = np.clip((273.0 - bt13) / 50.0, 0.0, 0.85).astype(np.float32)
    return np.clip(ir_rgba[:, :, :3] * alpha[:, :, np.newaxis] + base_rgb * (1.0 - alpha[:, :, np.newaxis]), 0.0, 1.0).astype(np.float32)


def render_composite_rgb(
    product_key: str,
    channels: dict[str, np.ndarray],
    lon_grid: np.ndarray | None = None,
    lat_grid: np.ndarray | None = None,
    instrument: str | None = None,
    observation_time: datetime | None = None,
    satellite_longitude: float | None = None,
    satellite_height_km: float | None = None,
) -> np.ndarray:
    use_eumetsat_recipe = instrument in _EUMETSAT_RECIPE_INSTRUMENTS
    if product_key in {"TrueColor", "NaturalColor"}:
        return _true_color(channels)
    if product_key == "GeoColor":
        return _geocolor(
            channels,
            lon_grid,
            lat_grid,
            observation_time,
            satellite_longitude,
            satellite_height_km,
            instrument,
        )
    if product_key == "GeoColorBlkMar":
        return _geocolor_black_marble(
            channels,
            lon_grid,
            lat_grid,
            observation_time,
            satellite_longitude,
            satellite_height_km,
            instrument,
        )
    if product_key == "DayNightHybrid":
        return _day_night_hybrid(channels)
    if product_key == "Sandwich":
        return _sandwich(channels)
    if product_key == "FireTemperature":
        red = gamma_correction(
            normalize(channels["Channel07"] - 273.15, 0.0, 60.0), 0.4)
        return _rgb(red, reflectance(channels["Channel06"]), normalize(reflectance(channels["Channel05"]), 0.0, 0.75))
    if product_key == "AirMass":
        red = normalize(channels["Channel08"] -
                        channels["Channel10"], -26.2, 0.6)
        green = normalize(channels["Channel10"] -
                          channels["Channel13"], -42.2, 6.7)
        blue = 1.0 - normalize(channels["Channel08"] - 273.15, -64.65, -29.25)
        return _rgb(red, green, blue)
    if product_key == "WaterVapor":
        red = 1.0 - normalize(channels["Channel13"] - 273.15, -70.86, 5.81)
        green = 1.0 - normalize(channels["Channel08"] - 273.15, -58.49, -30.48)
        blue = 1.0 - normalize(channels["Channel10"] - 273.15, -28.03, -12.12)
        return _rgb(red, green, blue)
    if product_key == "DifferentialWaterVapor":
        red = 1.0 - \
            gamma_correction(
                normalize(channels["Channel10"] - channels["Channel08"], -3.0, 30.0), 0.2587)
        green = 1.0 - \
            gamma_correction(
                normalize(channels["Channel10"] - 273.15, -60.0, 5.0), 0.4)
        blue = 1.0 - \
            gamma_correction(
                normalize(channels["Channel08"] - 273.15, -64.65, -29.25), 0.4)
        return _rgb(red, green, blue)
    if product_key == "DayConvection":
        red = normalize(channels["Channel08"] -
                        channels["Channel10"], -35.0, 5.0)
        green = normalize(channels["Channel07"] -
                          channels["Channel13"], -5.0, 60.0)
        blue = normalize(reflectance(
            channels["Channel05"]) - reflectance(channels["Channel02"]), -0.75, 0.25)
        return _rgb(red, green, blue)
    if product_key == "DayCloudConvection":
        red = gamma_correction(
            normalize(reflectance(channels["Channel02"]), 0.0, 1.0), 1.7)
        green = gamma_correction(
            normalize(reflectance(channels["Channel02"]), 0.0, 1.0), 1.7)
        blue = 1.0 - normalize(channels["Channel13"] - 273.15, -70.15, 49.85)
        return _rgb(red, green, blue)
    if product_key == "DayCloudPhase":
        red = 1.0 - normalize(channels["Channel13"] - 273.15, -53.5, 7.5)
        green = normalize(reflectance(channels["Channel02"]), 0.0, 0.78)
        blue = normalize(reflectance(channels["Channel05"]), 0.01, 0.59)
        return _rgb(red, green, blue)
    if product_key == "DayCloudPhaseEUMETSAT":
        return _rgb(
            normalize(reflectance(channels["Channel05"]), 0.0, 0.5),
            normalize(reflectance(channels["Channel06"]), 0.0, 0.5),
            normalize(reflectance(channels["Channel02"]), 0.0, 1.0),
        )
    if product_key == "DayLandCloud":
        return _rgb(
            normalize(reflectance(channels["Channel05"]), 0.0, 0.975),
            normalize(reflectance(channels["Channel03"]), 0.0, 1.086),
            normalize(reflectance(channels["Channel02"]), 0.0, 1.0),
        )
    if product_key == "DayLandCloudFire":
        return _rgb(reflectance(channels["Channel06"]), reflectance(channels["Channel03"]), reflectance(channels["Channel02"]))
    if product_key == "DaySnowFog":
        red = gamma_correction(
            normalize(reflectance(channels["Channel03"]), 0.0, 1.0), 1.7)
        green = gamma_correction(
            normalize(reflectance(channels["Channel05"]), 0.0, 0.7), 1.7)
        blue = gamma_correction(
            normalize(channels["Channel07"] - channels["Channel13"], 0.0, 30.0), 1.7)
        return _rgb(red, green, blue)
    if product_key == "NighttimeMicrophysics":
        if use_eumetsat_recipe:
            return _rgb(
                normalize(channels["Channel15"] -
                          channels["Channel13"], -4.0, 2.0),
                normalize(channels["Channel13"] -
                          channels["Channel07"], 0.0, 10.0),
                normalize(channels["Channel13"] - 273.15, -30.15, 19.85),
            )
        return _rgb(
            normalize(channels["Channel15"] -
                      channels["Channel13"], -6.7, 2.6),
            normalize(channels["Channel13"] -
                      channels["Channel07"], -3.1, 5.2),
            normalize(channels["Channel13"] - 273.15, -29.6, 19.5),
        )
    if product_key == "Dust":
        if use_eumetsat_recipe:
            return _rgb(
                normalize(channels["Channel15"] -
                          channels["Channel13"], -4.0, 2.0),
                gamma_correction(
                    normalize(channels["Channel14"] - channels["Channel11"], 0.0, 15.0), 2.5),
                normalize(channels["Channel13"] - 273.15, -12.15, 15.85),
            )
        return _rgb(
            normalize(channels["Channel15"] -
                      channels["Channel13"], -6.7, 2.6),
            gamma_correction(
                normalize(channels["Channel14"] - channels["Channel11"], -0.5, 20.0), 2.5),
            normalize(channels["Channel13"] - 273.15, -11.95, 15.55),
        )
    if product_key == "Ash":
        if use_eumetsat_recipe:
            return _rgb(
                normalize(channels["Channel15"] -
                          channels["Channel13"], -4.0, 2.0),
                normalize(channels["Channel14"] -
                          channels["Channel11"], -4.0, 5.0),
                normalize(channels["Channel13"] - 273.15, -30.15, 29.85),
            )
        return _rgb(
            normalize(channels["Channel15"] -
                      channels["Channel13"], -6.7, 2.6),
            normalize(channels["Channel14"] -
                      channels["Channel11"], -6.0, 6.3),
            normalize(channels["Channel13"] - 273.15, -29.55, 29.25),
        )
    if product_key == "SulfurDioxide":
        return _rgb(
            normalize(channels["Channel09"] -
                      channels["Channel10"], -4.0, 2.0),
            normalize(channels["Channel13"] -
                      channels["Channel11"], -4.0, 5.0),
            normalize(channels["Channel07"] - 273.15, -30.1, 29.8),
        )
    if product_key == "SplitWindowDifference":
        data = normalize(channels["Channel15"] -
                         channels["Channel13"], -10.0, 10.0)
        return _rgb(data, data, data)
    if product_key == "NightFogDifference":
        data = 1.0 - \
            normalize(channels["Channel13"] -
                      channels["Channel07"], -90.0, 15.0)
        return _rgb(data, data, data)
    if product_key == "BlowingSnow":
        gamma = 1.0 / 0.7
        return _rgb(
            gamma_correction(normalize(reflectance(
                channels["Channel02"]), 0.0, 0.5), gamma),
            normalize(reflectance(channels["Channel05"]), 0.0, 0.2),
            gamma_correction(
                normalize(channels["Channel07"] - channels["Channel13"], 0.0, 30.0), gamma),
        )
    if product_key == "SeaSpray":
        gamma = 1.0 / 0.6
        return _rgb(
            normalize(channels["Channel07"] - channels["Channel13"], 0.0, 5.0),
            gamma_correction(normalize(reflectance(
                channels["Channel03"]), 0.01, 0.09), gamma),
            gamma_correction(normalize(reflectance(
                channels["Channel02"]), 0.02, 0.12), gamma),
        )
    if product_key == "RocketPlume":
        return _rgb(
            normalize(channels["Channel07"] - 273.15, 0.0, 65.0),
            normalize(channels["Channel08"] - 273.15, -40.0, -20.0),
            normalize(reflectance(channels["Channel02"]), 0.0, 0.8),
        )
    raise ValueError(
        f"Unsupported Satellite v2 composite product: {product_key}")
