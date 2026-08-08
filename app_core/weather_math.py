"""Product-neutral meteorological calculation helpers."""

import numpy as np


def calc_relative_humidity(temperature_f, dew_point_f):
    """Calculate relative humidity from Fahrenheit temperature and dew point."""
    temperature_c = (temperature_f - 32) * 5 / 9
    dew_point_c = (dew_point_f - 32) * 5 / 9
    saturation_vapor_pressure = 6.112 * np.exp(
        (17.67 * temperature_c) / (temperature_c + 243.5)
    )
    vapor_pressure = 6.112 * np.exp(
        (17.67 * dew_point_c) / (dew_point_c + 243.5)
    )
    return np.clip((vapor_pressure / saturation_vapor_pressure) * 100, 0, 100)
