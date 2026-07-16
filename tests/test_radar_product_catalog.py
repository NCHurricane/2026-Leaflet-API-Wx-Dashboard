import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from cache.overlay_cache_utils import radar_list_frames, radar_update_index
from config.radar_config import (
    LIVE_RADAR_MAX_KEEP_FRAMES,
    LIVE_RADAR_PRODUCTS,
    live_radar_target_frames,
    normalize_live_radar_lookback_hours,
)
from services.radar_service import (
    _radar_live_catalog,
    _radar_live_product_metadata,
    _radar_live_render_on_demand,
    get_radar_live_frames_data,
    get_radar_colortable_data,
    normalize_radar_srv_motion,
    normalize_radar_elevation,
    radar_cache_product_key,
)
from radar import radar_nodd_utils
from workers.radar_live_worker import (
    _ensure_derived_field,
    _field_for_product,
    _prepare_field_data,
    _select_sweep,
    _source_product_code,
    _product_cfg_with_storm_motion,
)


class RadarProductCatalogTests(unittest.TestCase):
    @patch("radar.radar_nodd_utils._enforce_cache_size")
    @patch("radar.radar_nodd_utils.list_nexrad_files")
    @patch("radar.radar_nodd_utils.get_s3_client")
    def test_nodd_backfill_downloads_newest_missing_batch_only(
        self, get_s3_client, list_files, _enforce_cache_size
    ):
        keys = [
            "2026/07/16/KMHX/KMHX-old",
            "2026/07/16/KMHX/KMHX-middle",
            "2026/07/16/KMHX/KMHX-new",
        ]
        list_files.return_value = keys

        class FakeS3:
            downloaded_keys = []

            def download_file(self, _bucket, key, local_path):
                self.downloaded_keys.append(key)
                Path(local_path).write_bytes(b"radar")

        fake_s3 = FakeS3()
        get_s3_client.return_value = fake_s3

        with TemporaryDirectory() as temp_dir:
            existing = (
                Path(temp_dir)
                / "radar_level2_downloads"
                / "REF"
                / "KMHX"
                / "KMHX-new"
            )
            existing.parent.mkdir(parents=True)
            existing.write_bytes(b"cached")
            _save_dir, total, downloaded = radar_nodd_utils.download_radar_data(
                "Level 2",
                "KMHX",
                "REF",
                6,
                temp_dir,
                newest_first=True,
                max_new_files=1,
            )

        self.assertEqual(total, 3)
        self.assertEqual(downloaded, 1)
        self.assertEqual(fake_s3.downloaded_keys, [keys[-2]])

    def test_live_radar_lookback_supports_thirty_minutes_and_is_bounded(self):
        self.assertEqual(normalize_live_radar_lookback_hours(0.25), 0.5)
        self.assertEqual(normalize_live_radar_lookback_hours(0.5), 0.5)
        self.assertEqual(normalize_live_radar_lookback_hours(1.5), 1.5)
        self.assertEqual(normalize_live_radar_lookback_hours(99), 12.0)
        self.assertLess(
            live_radar_target_frames(0.5),
            live_radar_target_frames(1),
        )
        self.assertEqual(
            live_radar_target_frames(12),
            LIVE_RADAR_MAX_KEEP_FRAMES,
        )

    @patch("workers.radar_live_worker.run_radar_live_site_product", return_value=4)
    def test_on_demand_render_passes_requested_lookback_to_worker(self, run_worker):
        cached = _radar_live_render_on_demand(
            "KMHX",
            "L2_REF",
            latest_only=False,
            backfill_history=False,
            elevation="0.5",
            lookback_hours=6,
        )
        self.assertEqual(cached, 4)
        self.assertEqual(run_worker.call_args.kwargs["lookback_hours"], 6.0)

    @patch("services.radar_service._radar_live_render_in_background", return_value=True)
    @patch("cache.overlay_cache_utils.radar_list_frames")
    def test_frames_endpoint_backfills_when_cache_does_not_cover_request(
        self, list_frames, render_background
    ):
        now = datetime.now(timezone.utc)
        list_frames.return_value = [
            {"timestamp": (now - timedelta(minutes=45)).isoformat()},
            {"timestamp": (now - timedelta(minutes=5)).isoformat()},
        ]

        data = get_radar_live_frames_data(
            site="KMHX",
            product="L2_REF",
            elevation="0.5",
            hours=6,
        )

        self.assertFalse(data["coverage_complete"])
        self.assertTrue(data["refreshing"])
        self.assertEqual(data["lookback_hours"], 6.0)
        render_background.assert_called_once_with(
            "KMHX", "L2_REF", "0.5", None, 6.0
        )

    def test_supported_live_products_have_required_metadata(self):
        self.assertEqual(
            list(LIVE_RADAR_PRODUCTS),
            [
                "L2_REF",
                "L2_VEL",
                "L2_SRV",
                "L2_SW",
                "L2_ZDR",
                "L2_RHO",
                "L2_KDP",
                "L2_PHI",
                "L3_N0B",
                "L3_N0G",
                "L3_N0S",
                "L3_N0X",
                "L3_N0C",
                "L3_N0K",
            ],
        )
        self.assertNotIn("L3_DTA", LIVE_RADAR_PRODUCTS)

        required = {
            "level",
            "product",
            "label",
            "field_names",
            "palette",
            "units",
            "vmin",
            "vmax",
            "mask",
            "value_scale",
            "capabilities",
        }
        for product_id, metadata in LIVE_RADAR_PRODUCTS.items():
            with self.subTest(product_id=product_id):
                self.assertTrue(required.issubset(metadata))
                self.assertLess(metadata["vmin"], metadata["vmax"])
                expected_elevation = product_id.startswith("L2_")
                self.assertEqual(
                    metadata["capabilities"]["elevation_selection"],
                    expected_elevation,
                )

    def test_service_catalog_uses_config_catalog(self):
        self.assertEqual(_radar_live_catalog(), LIVE_RADAR_PRODUCTS)
        self.assertEqual(
            _radar_live_product_metadata("l3_n0g")["palette"],
            "BV",
        )

    def test_colortable_accepts_catalog_product_id(self):
        data = get_radar_colortable_data("L3_N0G")
        self.assertEqual(data["product"], "L3_N0G")
        self.assertEqual(data["palette"], "BV")
        self.assertEqual(data["vmin"], -120.0)
        self.assertEqual(data["vmax"], 120.0)
        self.assertTrue(data["entries"])

    def test_all_catalog_palettes_generate_legends(self):
        for product_id, metadata in LIVE_RADAR_PRODUCTS.items():
            with self.subTest(product_id=product_id):
                data = get_radar_colortable_data(product_id)
                self.assertEqual(data["palette"], metadata["palette"])
                self.assertEqual(data["vmin"], metadata["vmin"])
                self.assertEqual(data["vmax"], metadata["vmax"])
                self.assertTrue(data["entries"])

    def test_level_two_field_selection_uses_catalog(self):
        metadata = LIVE_RADAR_PRODUCTS["L2_ZDR"]
        selected = _field_for_product(
            metadata["level"],
            metadata["product"],
            ["reflectivity", "corrected_differential_reflectivity"],
            metadata,
        )
        self.assertEqual(selected, "corrected_differential_reflectivity")

    def test_level_two_storm_relative_velocity_uses_velocity_source(self):
        metadata = LIVE_RADAR_PRODUCTS["L2_SRV"]
        self.assertEqual(_source_product_code(metadata["product"], metadata), "VEL")
        self.assertEqual(metadata["palette"], "SRV")
        self.assertEqual(metadata["units"], "kt")
        self.assertEqual(metadata["derived_field"], "storm_relative_velocity")
        self.assertEqual(
            radar_cache_product_key("L2_SRV", "0.5"),
            "L2_SRV__MOTION_25KT_TO045_V1__ELEV_0P5",
        )
        selected = _field_for_product(
            metadata["level"],
            metadata["product"],
            ["reflectivity", "velocity"],
            metadata,
        )
        self.assertEqual(selected, "velocity")

    def test_level_two_storm_relative_velocity_selected_cell_cache_key(self):
        motion = normalize_radar_srv_motion(
            "L2_SRV",
            storm_motion_speed_kt="39.2",
            storm_motion_to_degrees="272.4",
            storm_motion_source="NST",
            storm_cell_id="B0",
        )
        self.assertEqual(motion["speed_kt"], 39.0)
        self.assertEqual(motion["motion_to_degrees"], 272.0)
        self.assertEqual(motion["source"], "NST")
        self.assertEqual(motion["cell_id"], "B0")
        self.assertEqual(
            radar_cache_product_key("L2_SRV", "0.5", motion),
            "L2_SRV__NST_CELL_B0_039KT_TO272_V1__ELEV_0P5",
        )
        cfg = _product_cfg_with_storm_motion(
            "L2_SRV", LIVE_RADAR_PRODUCTS["L2_SRV"], motion
        )
        self.assertEqual(cfg["storm_motion_speed_kt"], 39.0)
        self.assertEqual(cfg["storm_motion_to_degrees"], 272.0)
        self.assertEqual(cfg["cache_variant"], "nst_cell_b0_039kt_to272_v1")

    def test_level_two_storm_relative_velocity_derives_field(self):
        class FakeRadar:
            azimuth = {"data": np.array([45.0, 225.0])}
            fields = {
                "velocity": {
                    "data": np.ma.array([[10.0, -999.0], [10.0, 10.0]]),
                    "units": "meters_per_second",
                }
            }

        metadata = {
            **LIVE_RADAR_PRODUCTS["L2_SRV"],
            "storm_motion_speed_kt": 1.94384449,
            "storm_motion_to_degrees": 45.0,
        }
        field_name = _ensure_derived_field(FakeRadar, "velocity", metadata)
        self.assertEqual(field_name, "storm_relative_velocity")
        derived = FakeRadar.fields[field_name]["data"]
        self.assertAlmostEqual(float(derived[0, 0]), 9.0)
        self.assertTrue(bool(derived.mask[0, 1]))
        self.assertAlmostEqual(float(derived[1, 0]), 11.0)

    def test_level_three_dual_pol_field_selection_uses_catalog(self):
        expected = {
            "L3_N0S": "velocity",
            "L3_N0X": "differential_reflectivity",
            "L3_N0C": "cross_correlation_ratio",
            "L3_N0K": "specific_differential_phase",
        }
        for product_id, field_name in expected.items():
            metadata = LIVE_RADAR_PRODUCTS[product_id]
            with self.subTest(product_id=product_id):
                selected = _field_for_product(
                    metadata["level"],
                    metadata["product"],
                    ["reflectivity", field_name],
                    metadata,
                )
                self.assertEqual(selected, field_name)

    def test_storm_relative_velocity_uses_custom_palette(self):
        metadata = LIVE_RADAR_PRODUCTS["L3_N0S"]
        self.assertEqual(metadata["palette"], "SRV")
        self.assertEqual(metadata["units"], "kt")
        self.assertEqual(metadata["value_scale"], 1.0)
        self.assertEqual(
            radar_cache_product_key("L3_N0S", "auto"),
            "L3_N0S__SRV_KNOTS_V2",
        )
        data = get_radar_colortable_data("L3_N0S")
        self.assertEqual(data["palette"], "SRV")
        self.assertEqual(data["vmin"], -100.0)
        self.assertEqual(data["vmax"], 160.0)
        self.assertTrue(data["entries"])

    def test_velocity_and_spectrum_width_convert_to_knots(self):
        velocity = _prepare_field_data(
            np.ma.array([-10.0, 0.0, 10.0]),
            "VEL",
            LIVE_RADAR_PRODUCTS["L2_VEL"],
        )
        self.assertAlmostEqual(float(velocity[2]), 19.4384449)

        spectrum_width = _prepare_field_data(
            np.ma.array([-1.0, 5.0, np.nan]),
            "SW",
            LIVE_RADAR_PRODUCTS["L2_SW"],
        )
        self.assertTrue(bool(spectrum_width.mask[0]))
        self.assertAlmostEqual(float(spectrum_width[1]), 9.71922245)
        self.assertTrue(bool(spectrum_width.mask[2]))

    def test_elevation_normalization_and_cache_keys(self):
        self.assertEqual(normalize_radar_elevation("L2_REF", None), "auto")
        self.assertEqual(normalize_radar_elevation("L2_REF", "0.54"), "0.5")
        self.assertEqual(normalize_radar_elevation("L3_N0B", "1.5"), "auto")
        self.assertEqual(
            radar_cache_product_key("L2_REF", "auto"),
            "L2_REF__ELEV_AUTO",
        )
        self.assertEqual(
            radar_cache_product_key("L2_REF", "1.5"),
            "L2_REF__ELEV_1P5",
        )
        self.assertEqual(radar_cache_product_key("L3_N0B", "auto"), "L3_N0B")

    def test_nearest_elevation_sweep_selection(self):
        class FakeRadar:
            fixed_angle = {"data": np.array([0.5, 1.5, 2.4])}
            nsweeps = 3
            fields = {"reflectivity": {"data": np.ma.ones(6)}}

            @staticmethod
            def get_slice(index):
                return slice(index * 2, index * 2 + 2)

        sweep, available, selected = _select_sweep(
            FakeRadar(), "reflectivity", "1.8"
        )
        self.assertEqual(sweep, 1)
        self.assertEqual(available, [0.5, 1.5, 2.4])
        self.assertEqual(selected, 1.5)

    def test_radar_cache_preserves_elevation_metadata(self):
        with TemporaryDirectory() as temp_dir:
            frame_key = "20260621_120000"
            product_key = "L2_REF__ELEV_1P5"
            image_path = (
                Path(temp_dir)
                / "radar"
                / "live"
                / "KMHX"
                / "L2"
                / product_key
                / f"{frame_key}.png"
            )
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"png")
            radar_update_index(
                temp_dir,
                "KMHX",
                "L2",
                product_key,
                frame_key,
                available_elevations=[0.5, 1.5, 2.4],
                selected_elevation=1.5,
            )
            frames = radar_list_frames(temp_dir, "KMHX", "L2", product_key)
            self.assertEqual(frames[0]["available_elevations"], [0.5, 1.5, 2.4])
            self.assertEqual(frames[0]["selected_elevation"], 1.5)


if __name__ == "__main__":
    unittest.main()
