import unittest

import numpy as np

from satellite_v2.composites import scalar_reflectance


class ScalarReflectanceTests(unittest.TestCase):
    def test_fixed_contrast_window_and_square_root_stretch(self):
        values = np.array([0.0, 0.02, 0.24, 0.90, 1.0], dtype=np.float32)

        result = scalar_reflectance(values)

        np.testing.assert_allclose(
            result,
            np.array([0.0, 0.0, 0.5, 1.0, 1.0], dtype=np.float32),
            atol=1e-6,
        )

    def test_percent_reflectance_uses_the_same_display_stretch(self):
        fractions = np.array([2.0, 24.0, 90.0], dtype=np.float32)

        result = scalar_reflectance(fractions)

        np.testing.assert_allclose(
            result,
            np.array([0.0, 0.5, 1.0], dtype=np.float32),
            atol=1e-6,
        )

    def test_nan_remains_nan(self):
        result = scalar_reflectance(np.array([np.nan], dtype=np.float32))

        self.assertTrue(np.isnan(result[0]))


if __name__ == "__main__":
    unittest.main()
