import unittest

from services.radar_nst_service import (
    _attach_geojson,
    parse_nst_storm_tracks,
)


NST_SAMPLE = b"""
P                            STORM POSITION/FORECAST
P     RADAR ID 338  DATE/TIME 06:21:26/22:02:43   NUMBER OF STORM CELLS   1
P
P                   AVG SPEED 39 KTS    AVG DIRECTION 272 DEG
P
P STORM    CURRENT POSITION              FORECAST POSITIONS               ERROR
P  ID     AZRAN     MOVEMENT    15 MIN    30 MIN    45 MIN    60 MIN    FCST/MEAN
P        (DEG/NM)  (DEG/KTS)   (DEG/NM)  (DEG/NM)  (DEG/NM)  (DEG/NM)     (NM)
P
P  B0     261/195   272/ 39     260/185   260/176   NO DATA   NO DATA    1.2/ 1.2
"""


class RadarNstServiceTests(unittest.TestCase):
    def test_parse_nst_storm_tracks_extracts_motion(self):
        parsed = parse_nst_storm_tracks(NST_SAMPLE, "sample")

        self.assertEqual(parsed["timestamp"], "2026-06-21T22:02:43+00:00")
        self.assertEqual(parsed["cell_count"], 1)
        self.assertEqual(parsed["average_motion"]["speed_kt"], 39)
        self.assertEqual(parsed["average_motion"]["motion_to_degrees"], 272)
        self.assertEqual(len(parsed["cells"]), 1)
        cell = parsed["cells"][0]
        self.assertEqual(cell["id"], "B0")
        self.assertEqual(cell["current_azimuth_deg"], 261)
        self.assertEqual(cell["current_range_nm"], 195)
        self.assertEqual(cell["motion_to_degrees"], 272)
        self.assertEqual(cell["speed_kt"], 39)
        self.assertEqual(cell["forecast_raw"][45], "NO DATA")

    def test_attach_geojson_emits_clickable_cell_and_track(self):
        parsed = parse_nst_storm_tracks(NST_SAMPLE, "sample")
        enriched = _attach_geojson(parsed, 39.42, -83.822, "KILN")

        self.assertEqual(enriched["site"], "KILN")
        self.assertEqual(len(enriched["cells"]), 1)
        self.assertAlmostEqual(enriched["cells"][0]["lat"], 38.80, delta=0.2)
        self.assertAlmostEqual(enriched["cells"][0]["lon"], -87.95, delta=0.3)

        features = enriched["feature_collection"]["features"]
        self.assertEqual(features[0]["geometry"]["type"], "Point")
        self.assertEqual(features[0]["properties"]["cell_id"], "B0")
        self.assertEqual(features[0]["properties"]["speed_kt"], 39)
        self.assertEqual(features[1]["geometry"]["type"], "LineString")
        self.assertEqual(features[1]["properties"]["kind"], "nst_forecast_track")


if __name__ == "__main__":
    unittest.main()
