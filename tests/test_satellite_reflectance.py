import unittest

import numpy as np

from satellite_v2.composites import scalar_reflectance
from satellite_v2.renderer import SatelliteTileRenderer


class ScalarReflectanceTests(unittest.TestCase):
    def test_legacy_reflective_channel_uses_existing_fixed_window(self):
        values = np.array([0.0, 0.02, 0.24, 0.90, 1.0], dtype=np.float32)

        result = scalar_reflectance(values, source_channel="Channel03")

        np.testing.assert_allclose(
            result,
            np.array([0.0, 0.0, 0.5, 1.0, 1.0], dtype=np.float32),
            atol=1e-6,
        )

    def test_legacy_percent_reflectance_uses_the_same_display_stretch(self):
        fractions = np.array([2.0, 24.0, 90.0], dtype=np.float32)

        result = scalar_reflectance(fractions, source_channel="Channel03")

        np.testing.assert_allclose(
            result,
            np.array([0.0, 0.5, 1.0], dtype=np.float32),
            atol=1e-6,
        )

    def test_channel02_preserves_highlight_detail_through_120_percent(self):
        values = np.array(
            [0.0, 0.30, 0.70, 0.90, 1.0, 1.20, 1.30],
            dtype=np.float32,
        )

        result = scalar_reflectance(values, source_channel="Channel02")

        np.testing.assert_allclose(
            result,
            np.sqrt(
                np.array(
                    [0.0, 0.25, 0.70 / 1.20, 0.75, 1.0 / 1.20, 1.0, 1.0],
                    dtype=np.float32,
                )
            ),
            atol=1e-6,
        )
        self.assertLess(result[3], result[4])
        self.assertLess(result[4], result[5])

    def test_channel02_percent_reflectance_uses_expanded_window(self):
        values = np.array([0.0, 30.0, 90.0, 120.0], dtype=np.float32)

        result = scalar_reflectance(values, source_channel="Channel02")

        np.testing.assert_allclose(
            result,
            np.sqrt(np.array([0.0, 0.25, 0.75, 1.0], dtype=np.float32)),
            atol=1e-6,
        )

    def test_channel02_renderer_keeps_bright_reflectance_levels_distinct(self):
        renderer = SatelliteTileRenderer(
            product_key="Channel02",
            source_rasters={},
        )
        values = np.array([[0.90, 1.00, 1.20]], dtype=np.float32)

        rgba = np.asarray(
            renderer._composite_image(
                {"Channel02": values},
                z=0,
                x_min=0,
                y_min=0,
                canvas_w=3,
                canvas_h=1,
                tile_size=1,
            )
        )

        brightness = rgba[0, :, 0]
        self.assertLess(int(brightness[0]), int(brightness[1]))
        self.assertLess(int(brightness[1]), int(brightness[2]))
        np.testing.assert_array_equal(
            rgba[0, :, 3],
            np.array([255, 255, 255], dtype=np.uint8),
        )

    def test_nan_remains_nan(self):
        result = scalar_reflectance(
            np.array([np.nan], dtype=np.float32),
            source_channel="Channel02",
        )

        self.assertTrue(np.isnan(result[0]))


if __name__ == "__main__":
    unittest.main()
