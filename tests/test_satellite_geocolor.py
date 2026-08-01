import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from satellite_v2.composites import (
    _geocolor_display_tone,
    _geocolor_day_rgb,
    _rayleigh_correction_weight,
    _rayleigh_correct_reflectance,
    _satellite_local_vectors,
    _solar_day_weight,
    _solar_local_vectors,
    cira_visible_stretch,
)
from satellite_v2.renderer import _parse_observation_time


class GeoColorRecipeTests(unittest.TestCase):
    def test_cira_stretch_sets_documented_black_point(self):
        values = np.array([0.01, 0.0223, 0.10, 0.50, 1.60], dtype=np.float32)

        result = cira_visible_stretch(values)

        self.assertEqual(float(result[0]), 0.0)
        self.assertAlmostEqual(float(result[1]), 0.0, places=5)
        self.assertGreater(float(result[2]), 0.30)
        self.assertGreater(float(result[3]), 0.65)
        self.assertGreater(float(result[4]), 0.90)

    def test_display_tone_uses_full_luminance_range(self):
        rgb = np.array([[[0.0, 0.425, 0.85]]], dtype=np.float32)

        result = _geocolor_display_tone(rgb)

        np.testing.assert_allclose(
            result,
            np.array([[[0.0, 0.5, 1.0]]], dtype=np.float32),
            atol=1e-6,
        )

    def test_abi_display_tone_lifts_midtones_without_moving_endpoints(self):
        rgb = np.array([[[0.0, 0.425, 0.85]]], dtype=np.float32)

        result = _geocolor_display_tone(rgb, midtone_gamma=0.85)

        self.assertEqual(float(result[0, 0, 0]), 0.0)
        self.assertGreater(float(result[0, 0, 1]), 0.5)
        self.assertEqual(float(result[0, 0, 2]), 1.0)

    def test_geocolor_midtone_lift_is_abi_only(self):
        channels = {
            channel: np.full((1, 1), 0.20, dtype=np.float32)
            for channel in ("Channel01", "Channel02", "Channel03")
        }

        abi, _ = _geocolor_day_rgb(
            channels, None, None, None, None, None, "ABI"
        )
        non_abi, _ = _geocolor_day_rgb(
            channels, None, None, None, None, None, "AMI"
        )

        self.assertTrue(np.all(abi > non_abi))

    def test_day_weight_uses_solar_position_not_surface_brightness(self):
        lon = np.array([[-75.0]], dtype=np.float32)
        lat = np.array([[35.0]], dtype=np.float32)

        midday = _solar_day_weight(
            datetime(2026, 7, 16, 17, 0, tzinfo=timezone.utc), lon, lat
        )
        midnight = _solar_day_weight(
            datetime(2026, 7, 16, 5, 0, tzinfo=timezone.utc), lon, lat
        )

        self.assertEqual(float(midday[0, 0]), 1.0)
        self.assertEqual(float(midnight[0, 0]), 0.0)

    def test_rayleigh_correction_removes_more_blue_path_radiance(self):
        lon = np.array([[-75.0]], dtype=np.float32)
        lat = np.array([[35.0]], dtype=np.float32)
        when = datetime(2026, 7, 16, 17, 0, tzinfo=timezone.utc)
        solar = _solar_local_vectors(when, lon, lat)
        satellite = _satellite_local_vectors(lon, lat, -75.2, 35786.0)
        reflectance = np.array([[0.15]], dtype=np.float32)

        blue = _rayleigh_correct_reflectance(
            reflectance, "Channel01", solar, satellite
        )
        red = _rayleigh_correct_reflectance(
            reflectance, "Channel02", solar, satellite
        )
        near_ir = _rayleigh_correct_reflectance(
            reflectance, "Channel03", solar, satellite
        )

        self.assertLess(float(blue[0, 0]), float(red[0, 0]))
        self.assertLess(float(red[0, 0]), float(near_ir[0, 0]))

    def test_rayleigh_correction_tapers_through_low_sun_angles(self):
        solar_zenith = np.array([45.0, 60.0, 72.5, 85.0, 90.0])
        sun_up = np.cos(np.deg2rad(solar_zenith)).astype(np.float32)

        result = _rayleigh_correction_weight(sun_up)

        np.testing.assert_allclose(result[:2], np.ones(2), atol=1e-6)
        self.assertGreater(float(result[2]), 0.0)
        self.assertLess(float(result[2]), 1.0)
        np.testing.assert_allclose(result[3:], np.zeros(2), atol=1e-6)

    def test_goes_observation_time_prefers_dataset_metadata(self):
        dataset = xr.Dataset(
            attrs={"time_coverage_start": "2026-07-16T20:46:17.500Z"}
        )

        result = _parse_observation_time(dataset, Path("unused.nc"))

        self.assertEqual(
            result,
            datetime(2026, 7, 16, 20, 46, 17, 500000, tzinfo=timezone.utc),
        )

    def test_goes_observation_time_falls_back_to_filename(self):
        dataset = xr.Dataset()

        result = _parse_observation_time(
            dataset,
            Path("OR_ABI-L2-CMIPC-M6C01_G19_s20261972046175_e.nc"),
        )

        self.assertEqual(
            result,
            datetime(2026, 7, 16, 20, 46, 17, 500000, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
