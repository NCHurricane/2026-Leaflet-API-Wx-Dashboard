import unittest

from services.radar_storm_attributes_service import _build_cells, _radar_3letter


def _feature(nexrad, storm_id, **props):
    base = {
        "nexrad": nexrad,
        "storm_id": storm_id,
        "azimuth": 100,
        "range": 50,
        "tvs": "NONE",
        "meso": "NONE",
        "posh": 0,
        "poh": 0,
        "max_size": 0.0,
        "vil": 10,
        "max_dbz": 45,
        "top": 20.0,
        "drct": 270,
        "sknt": 25,
        "valid": "2026-06-27T02:00:00Z",
    }
    base.update(props)
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-77.0, 35.0]},
        "properties": base,
    }


class BuildCellsTest(unittest.TestCase):
    def _build(self, *features):
        return _build_cells({"type": "FeatureCollection", "features": list(features)}, "KMHX")

    def test_radar_3letter_strips_region_char(self):
        self.assertEqual(_radar_3letter("KMHX"), "MHX")
        self.assertEqual(_radar_3letter("PAHG"), "AHG")
        self.assertEqual(_radar_3letter("TJUA"), "JUA")

    def test_filters_to_requested_radar(self):
        built = self._build(_feature("MHX", "A1"), _feature("AMA", "Z9"))
        self.assertEqual(built["cell_count"], 1)
        self.assertEqual(built["cells"][0]["cell_id"], "A1")

    def test_attribute_and_motion_mapping(self):
        built = self._build(_feature("MHX", "A1", posh=40, poh=100, max_size=1.25, top=22.9))
        props = built["feature_collection"]["features"][0]["properties"]
        self.assertEqual(props["nhi"], {"posh": 40.0, "poh": 100.0, "max_hail_size_in": 1.25})
        self.assertEqual(props["nss"]["top_kft"], 22.9)
        # drct=270 is the FROM direction; stored heading is the opposite bearing.
        self.assertEqual(props["motion_to_degrees"], 90.0)
        self.assertEqual(props["speed_kt"], 25.0)

    def test_icon_priority_order(self):
        cases = [
            (dict(tvs="TVS", meso="MESO", posh=100, poh=100), "tvs"),
            (dict(meso=4, posh=100, poh=100), "meso"),
            (dict(posh=60), "pos_hail"),
            (dict(poh=70), "prob_hail"),
            (dict(), "cell"),
        ]
        for overrides, expected in cases:
            built = self._build(_feature("MHX", "A1", **overrides))
            self.assertEqual(
                built["feature_collection"]["features"][0]["properties"]["icon_priority"],
                expected,
                msg=f"{overrides} -> {expected}",
            )

    def test_forecast_track_emitted_with_motion(self):
        built = self._build(_feature("MHX", "A1", drct=270, sknt=25))
        kinds = [f["properties"]["kind"] for f in built["feature_collection"]["features"]]
        self.assertIn("nst_cell", kinds)
        self.assertIn("nst_forecast_track", kinds)

    def test_no_track_when_stationary(self):
        built = self._build(_feature("MHX", "A1", sknt=0))
        kinds = [f["properties"]["kind"] for f in built["feature_collection"]["features"]]
        self.assertNotIn("nst_forecast_track", kinds)


if __name__ == "__main__":
    unittest.main()
