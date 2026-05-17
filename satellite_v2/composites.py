"""Satellite v2 product rendering recipes.

The formulas mirror the v1 product registry while operating directly on tile-sized
sample arrays from the v2 Web Mercator renderer.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from config.satellite_colormaps import IR_CMAP, IR_NORM

Image.MAX_IMAGE_PIXELS = None


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
    return reflectance(values, gamma=0.5)


def _rgb(red: np.ndarray, green: np.ndarray, blue: np.ndarray) -> np.ndarray:
    return np.clip(np.dstack([red, green, blue]), 0.0, 1.0).astype(np.float32)


def _true_color(channels: dict[str, np.ndarray]) -> np.ndarray:
    red = visible_reflectance(channels["Channel02"])
    blue = visible_reflectance(channels["Channel01"])
    veggie = visible_reflectance(channels["Channel03"])
    green = np.clip(0.45 * red + 0.1 * veggie + 0.45 * blue, 0.0, 1.0)
    return _rgb(red, green, blue)


def _geocolor(channels: dict[str, np.ndarray]) -> np.ndarray:
    day_rgb = _true_color(channels)
    red_ref = day_rgb[:, :, 0]
    bt13 = channels["Channel13"]
    bt07 = channels.get("Channel07", bt13)

    high_cloud = normalize(bt13, 273.15, 193.15)
    low_cloud = normalize(bt13 - bt07, 1.0, 8.0)

    night_rgb = np.zeros((*bt13.shape, 3), dtype=np.float32)
    night_rgb[:, :, 0] = 0.03
    night_rgb[:, :, 1] = 0.05
    night_rgb[:, :, 2] = 0.10
    night_rgb *= 0.5

    cold_boost = normalize(bt13, 260.0, 200.0)
    night_rgb[:, :, 2] += 0.12 * cold_boost
    night_rgb[:, :, 0] += 0.30 * low_cloud
    night_rgb[:, :, 1] += 0.45 * low_cloud
    night_rgb[:, :, 2] += 0.55 * low_cloud
    for channel_index in range(3):
        night_rgb[:, :, channel_index] += 1.3 * high_cloud
    night_rgb = np.clip(night_rgb, 0.0, 1.0)

    day_weight = np.clip((red_ref - 0.05) / 0.15, 0.0, 1.0)
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
) -> np.ndarray:
    if lon_grid is None or lat_grid is None:
        return _geocolor(channels)

    day_rgb = _true_color(channels)
    red_ref = day_rgb[:, :, 0]
    bt13 = channels["Channel13"]
    bt07 = channels.get("Channel07", bt13)

    high_cloud = normalize(bt13, 310.0, 190.0)
    low_cloud = normalize(bt13 - bt07, 0.5, 8.0)

    night_rgb = _sample_black_marble(lon_grid, lat_grid) * 0.5
    night_rgb[:, :, 0] += 0.30 * low_cloud + 1.0 * high_cloud
    night_rgb[:, :, 1] += 0.40 * low_cloud + 1.0 * high_cloud
    night_rgb[:, :, 2] += 0.50 * low_cloud + 1.1 * high_cloud
    night_rgb = gamma_correction(np.clip(night_rgb * 1.1, 0.0, 1.0), 0.8)

    day_signal_pct = red_ref * 100.0
    day_weight = np.clip((day_signal_pct - 7.8) / (8.8 - 7.8), 0.0, 1.0)
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
) -> np.ndarray:
    if product_key in {"TrueColor", "NaturalColor"}:
        return _true_color(channels)
    if product_key == "GeoColor":
        return _geocolor(channels)
    if product_key == "GeoColorBlkMar":
        return _geocolor_black_marble(channels, lon_grid, lat_grid)
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
        return _rgb(
            normalize(channels["Channel15"] -
                      channels["Channel13"], -6.7, 2.6),
            normalize(channels["Channel13"] -
                      channels["Channel07"], -3.1, 5.2),
            normalize(channels["Channel13"] - 273.15, -29.6, 19.5),
        )
    if product_key == "Dust":
        return _rgb(
            normalize(channels["Channel15"] -
                      channels["Channel13"], -6.7, 2.6),
            gamma_correction(
                normalize(channels["Channel14"] - channels["Channel11"], -0.5, 20.0), 2.5),
            normalize(channels["Channel13"] - 273.15, -11.95, 15.55),
        )
    if product_key == "Ash":
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
