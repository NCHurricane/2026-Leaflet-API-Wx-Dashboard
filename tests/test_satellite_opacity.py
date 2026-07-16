import unittest

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize

from satellite_v2.renderer import (
    _SATELLITE_FILLED_ALPHA,
    _SATELLITE_OVERLAY_ALPHA,
    _colorize_aod,
    _colorize_scalar,
    _rgb_to_image,
)


class SatelliteOpacityTests(unittest.TestCase):
    def test_rgb_tiles_are_opaque_inside_valid_coverage(self):
        rgb = np.ones((1, 2, 3), dtype=np.float32)
        valid = np.array([[True, False]])

        rgba = np.asarray(_rgb_to_image(rgb, valid))

        self.assertEqual(int(rgba[0, 0, 3]), _SATELLITE_FILLED_ALPHA)
        self.assertEqual(int(rgba[0, 1, 3]), 0)

    def test_filled_scalar_defaults_to_full_opacity(self):
        values = np.array([[0.0, 1.0]], dtype=np.float32)
        valid = np.array([[True, True]])

        rgba = np.asarray(
            _colorize_scalar(values, valid, plt.get_cmap("gray"), None)
        )

        np.testing.assert_array_equal(
            rgba[0, :, 3],
            np.array([_SATELLITE_FILLED_ALPHA] * 2, dtype=np.uint8),
        )

    def test_sparse_scalar_can_retain_overlay_opacity(self):
        values = np.array([[10.0]], dtype=np.float32)
        valid = np.array([[True]])

        rgba = np.asarray(
            _colorize_scalar(
                values,
                valid,
                plt.get_cmap("gray"),
                None,
                alpha=_SATELLITE_OVERLAY_ALPHA,
            )
        )

        self.assertEqual(int(rgba[0, 0, 3]), _SATELLITE_OVERLAY_ALPHA)

    def test_aod_keeps_its_transparency_ramp(self):
        values = np.array([[0.10, 0.40]], dtype=np.float32)
        valid = np.array([[True, True]])

        rgba = np.asarray(
            _colorize_aod(
                values,
                valid,
                plt.get_cmap("viridis"),
                Normalize(vmin=0.0, vmax=1.0),
            )
        )

        self.assertEqual(int(rgba[0, 0, 3]), 0)
        self.assertEqual(int(rgba[0, 1, 3]), _SATELLITE_OVERLAY_ALPHA)


if __name__ == "__main__":
    unittest.main()
