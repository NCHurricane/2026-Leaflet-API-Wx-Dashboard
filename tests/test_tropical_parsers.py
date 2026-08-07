from __future__ import annotations

import zipfile

import pytest

import workers.tropical_archive_worker as archive_worker
import workers.tropical_worker as tropical_worker


def _polygon(west: float = -70.0) -> str:
    return f"""
    <Polygon><outerBoundaryIs><LinearRing><coordinates>
      {west},15,0 {west + 2},15,0 {west + 2},17,0 {west},15,0
    </coordinates></LinearRing></outerBoundaryIs></Polygon>
    """


def _kml(*body: str, name: str = "") -> str:
    name_xml = f"<name>{name}</name>" if name else ""
    return (
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        + name_xml
        + "".join(body)
        + "</Document></kml>"
    )


def _placemark(
    name: str = "",
    *,
    style: str = "",
    geometry: str | None = None,
    description: str = "",
    extended_data: dict[str, str] | None = None,
) -> str:
    style_xml = f"<styleUrl>#{style}</styleUrl>" if style else ""
    description_xml = (
        f"<description><![CDATA[{description}]]></description>"
        if description
        else ""
    )
    data_xml = ""
    if extended_data:
        data_xml = "<ExtendedData>" + "".join(
            f'<Data name="{key}"><value>{value}</value></Data>'
            for key, value in extended_data.items()
        ) + "</ExtendedData>"
    return (
        f"<Placemark><name>{name}</name>{style_xml}{description_xml}{data_xml}"
        f"{geometry if geometry is not None else _polygon()}</Placemark>"
    )


def test_tropical_rss_parser_normalizes_html_and_repairs_bare_ampersands():
    rss = """
    <rss><channel>
      <title>Atlantic & Caribbean</title>
      <description>National Hurricane Center</description>
      <link>https://example.test/feed</link>
      <pubDate>Fri, 07 Aug 2026 12:00:00 GMT</pubDate>
      <item>
        <title>Tropical Storm Alpha</title>
        <description><![CDATA[Alpha strengthens<br>Moving west & northwest]]></description>
        <pubDate>Fri, 07 Aug 2026 12:00:00 GMT</pubDate>
        <link>https://example.test/alpha</link>
        <guid>alpha-1</guid>
        <author>NHC</author>
      </item>
    </channel></rss>
    """

    payload = tropical_worker._parse_rss_feed(rss)

    assert payload["channel"]["title"] == "Atlantic & Caribbean"
    assert payload["channel"]["link"] == "https://example.test/feed"
    assert payload["items"] == [
        {
            "title": "Tropical Storm Alpha",
            "description": "Alpha strengthens\nMoving west & northwest",
            "description_html": "Alpha strengthens<br>Moving west &amp; northwest",
            "pubDate": "Fri, 07 Aug 2026 12:00:00 GMT",
            "link": "https://example.test/alpha",
            "guid": "alpha-1",
            "author": "NHC",
        }
    ]


def test_tropical_rss_parser_returns_explicit_error_for_unreadable_xml():
    payload = tropical_worker._parse_rss_feed("<rss><channel>")

    assert payload["channel"] == {}
    assert payload["items"] == []
    assert payload["error"]


def test_gtwo_parser_preserves_active_area_metadata_and_empty_state(tmp_path):
    active_kml = _kml(
        _placemark(
            style="2",
            geometry=_polygon(-65),
            extended_data={
                "Disturbance": "1",
                "Discussion": "1. Western Tropical Atlantic: Development possible.",
                "2day_percentage": "30%",
                "2day_category": "Low",
                "7day_percentage": "60%",
                "7day_category": "Medium",
            },
        ),
        _placemark(
            "Off-season label",
            geometry="<Point><coordinates>-60,20,0</coordinates></Point>",
        ),
        name="Issued 1200 UTC Fri Aug 7 2026",
    )
    empty_kml = _kml(
        "<description>Formation is not expected during the next 7 days.</description>",
        name="Issued 1200 UTC Fri Aug 7 2026",
    )
    kmz_path = tmp_path / "gtwo.kmz"
    with zipfile.ZipFile(kmz_path, "w") as archive:
        archive.writestr("outlook.kml", active_kml)

    active = tropical_worker._parse_gtwo_kmz(kmz_path)
    empty = tropical_worker._parse_gtwo_kml(empty_kml)

    assert active is not None
    assert active["issued"] == "Issued 1200 UTC Fri Aug 7 2026"
    assert len(active["geojson"]["features"]) == 1
    assert active["areas"] == [
        {
            "name": "Western Tropical Atlantic",
            "disturbance": "1",
            "category": "medium",
            "color": "#ff8c00",
            "twoDayPct": 30,
            "twoDayCategory": "Low",
            "sevenDayPct": 60,
            "sevenDayCategory": "Medium",
            "discussion": "1. Western Tropical Atlantic: Development possible.",
        }
    ]
    assert empty["notExpected"] is True
    assert empty["areas"] == []
    assert empty["geojson"]["features"] == []


def test_tropical_kml_parsers_shape_surge_and_initial_wind_products(tmp_path):
    surge_kml = _kml(
        _placemark("Storm Surge Warning", geometry=_polygon(-82)),
        _placemark(
            "Boundary",
            geometry=(
                "<LineString><coordinates>-82,25,0 -80,26,0</coordinates>"
                "</LineString>"
            ),
        ),
    )
    peak_kml = _kml(
        _placemark(
            "Peak Surge Zone",
            geometry=_polygon(-82),
            description='{"peak_surge_range":"6-9 ft","color":"#ff0000"}',
        ),
        _placemark(
            "Cape Fear",
            geometry="<Point><coordinates>-77.9,33.8,0</coordinates></Point>",
            description="Cape Fear",
        ),
    )
    wind_kml = _kml(
        _placemark("64", geometry=_polygon(-75)),
        _placemark("34", geometry=_polygon(-78)),
        _placemark("100", geometry=_polygon(-81)),
    )
    wind_kmz = tmp_path / "initialradii.kmz"
    with zipfile.ZipFile(wind_kmz, "w") as archive:
        archive.writestr("wind.kml", wind_kml)

    surge = tropical_worker._parse_storm_surge_kml(surge_kml)
    peak = tropical_worker._parse_peak_surge_kml(peak_kml)
    wind = tropical_worker._parse_initial_wind_extent_kmz(wind_kmz)

    assert surge is not None
    assert len(surge["features"]) == 1
    assert surge["features"][0]["properties"]["name"] == "Storm Surge Warning"
    assert peak is not None
    assert [feature["properties"]["feature_type"] for feature in peak["features"]] == [
        "polygon",
        "breakpoint",
    ]
    assert peak["features"][0]["properties"]["peak_surge_range"] == "6-9 ft"
    assert peak["features"][0]["properties"]["color"] == "#ff0000"
    assert wind is not None
    assert [feature["properties"]["windField"] for feature in wind["features"]] == [
        "64",
        "34",
    ]


def test_tropical_kml_parsers_reject_unreadable_or_empty_products(tmp_path):
    bad_kmz = tmp_path / "bad.kmz"
    bad_kmz.write_bytes(b"not a zip")

    assert tropical_worker._parse_gtwo_kmz(bad_kmz) is None
    assert tropical_worker._parse_storm_surge_kml("<kml>") is None
    assert tropical_worker._parse_peak_surge_kml(_kml()) is None
    assert tropical_worker._parse_initial_wind_extent_kml(_kml()) is None


def test_tropical_advisory_parser_extracts_summary_and_signed_location():
    text = """
...ALPHA STRENGTHENS...
...HEAVY RAINFALL EXPECTED...

SUMMARY OF 1100 AM EDT INFORMATION
-----------------------------------------------
LOCATION...15.2N 60.4W ABOUT 200 MI EAST OF THE LEEWARD ISLANDS
MAXIMUM SUSTAINED WINDS...70 MPH...110 KM/H
PRESENT MOVEMENT...WEST-NORTHWEST OR 290 DEGREES AT 12 MPH...19 KM/H
MINIMUM CENTRAL PRESSURE...995 MB...29.39 INCHES

DISCUSSION AND OUTLOOK
Additional text.
"""

    advisory = tropical_worker._parse_advisory(text)

    assert advisory["location"] == {
        "lat": 15.2,
        "lon": -60.4,
        "latText": "15.2N",
        "lonText": "60.4W",
        "text": "ABOUT 200 MI EAST OF THE LEEWARD ISLANDS",
    }
    assert advisory["maxWindMph"] == 70
    assert advisory["maxWindKph"] == 110
    assert advisory["motion"] == {
        "text": "WEST-NORTHWEST OR 290 DEGREES",
        "mph": 12,
        "kph": 19,
    }
    assert advisory["pressureMb"] == 995
    assert advisory["headline"] == "ALPHA STRENGTHENS HEAVY RAINFALL EXPECTED"


def test_tropical_track_parser_supports_table_and_narrative_formats():
    table = """
INIT  07/1200Z 15.2N 60.4W 60 KT
12H   08/0000Z 15.8N 62.0W 65 KT
"""
    narrative = """
CENTER LOCATED NEAR 15.2N 60.4W AT 07/1200Z
MAX SUSTAINED WINDS 60 KT
FORECAST VALID 08/0000Z 15.8N 62.0W
MAX WINDS 65 KT
OUTLOOK VALID 09/0000Z 17.0N 65.0W
MAX WINDS 70 KT
"""

    assert tropical_worker._parse_track(table) == [
        {"hour": "INIT", "time": "07/1200Z", "lat": 15.2, "lon": -60.4, "windKt": 60},
        {"hour": "12H", "time": "08/0000Z", "lat": 15.8, "lon": -62.0, "windKt": 65},
    ]
    assert tropical_worker._parse_track(narrative) == [
        {"hour": "INIT", "time": "07/1200Z", "lat": 15.2, "lon": -60.4, "windKt": 60},
        {"hour": "FORECAST", "time": "08/0000Z", "lat": 15.8, "lon": -62.0, "windKt": 65},
        {"hour": "OUTLOOK", "time": "09/0000Z", "lat": 17.0, "lon": -65.0, "windKt": 70},
    ]


def test_hurdat2_parser_preserves_landfall_missing_values_and_basin(tmp_path):
    path = tmp_path / "hurdat2.txt"
    path.write_text(
        """AL012026, ALPHA, 3,
20260801, 0000, , TS, 15.0N, 45.0W, 40, 1005,
20260801, 0600, L, HU, 16.0N, 46.0W, 70, 980,
bad-date, 1200, , TS, 17.0N, 47.0W, -99, -999,
EP022026, BETA, 1,
20260901, 0000, , TD, 10.0N, 110.0W, -99, -999,
""",
        encoding="utf-8",
    )

    storms = list(archive_worker.parse_hurdat2(path))

    assert [storm["atcf_id"] for storm in storms] == ["AL012026", "EP022026"]
    assert storms[0]["basin"] == "AL"
    assert storms[0]["landfall"] is True
    assert len(storms[0]["rows"]) == 2
    assert storms[0]["rows"][0]["lat"] == 15.0
    assert storms[0]["rows"][0]["lon"] == -45.0
    assert storms[1]["rows"][0]["wind_kt"] is None
    assert storms[1]["rows"][0]["pres_mb"] is None


def test_hurdat2_parser_skips_bad_headers_and_contains_bad_row_values(tmp_path):
    path = tmp_path / "hurdat2-malformed.txt"
    path.write_text(
        """AL032026, GAMMA, not-a-count,
AL042026, DELTA, 1,
20261001, 0000, , TS, bad-lat, 45.0Q, bad-wind, bad-pressure,
""",
        encoding="utf-8",
    )

    storms = list(archive_worker.parse_hurdat2(path))

    assert len(storms) == 1
    assert storms[0]["atcf_id"] == "AL042026"
    assert storms[0]["rows"][0]["lat"] is None
    assert storms[0]["rows"][0]["lon"] is None
    assert storms[0]["rows"][0]["wind_kt"] is None
    assert storms[0]["rows"][0]["pres_mb"] is None


def _atcf_row(
    *,
    basin: str = "AL",
    number: str = "01",
    timestamp: str = "2026080712",
    technique: str = "BEST",
    lat: str = "152N",
    lon: str = "604W",
    wind: str = "60",
    pressure: str = "995",
    status: str = "TS",
    name: str = "ALPHA",
) -> str:
    cells = [""] * 28
    cells[0] = basin
    cells[1] = number
    cells[2] = timestamp
    cells[4] = technique
    cells[6] = lat
    cells[7] = lon
    cells[8] = wind
    cells[9] = pressure
    cells[10] = status
    cells[27] = name
    return ", ".join(cells)


def test_atcf_best_track_parser_deduplicates_times_and_normalizes_values():
    text = "\n".join(
        [
            _atcf_row(),
            _atcf_row(wind="50", pressure="999"),
            _atcf_row(
                timestamp="2026080718",
                lat="160N",
                lon="615W",
                wind="70",
                pressure="980",
                status="HU",
            ),
            _atcf_row(timestamp="bad", name="SHOULD_SKIP"),
            _atcf_row(timestamp="2026080800", technique="CARQ"),
        ]
    )

    storm = archive_worker.parse_atcf_btk(text)

    assert storm is not None
    assert storm["atcf_id"] == "AL012026"
    assert storm["name"] == "ALPHA"
    assert storm["basin"] == "AL"
    assert len(storm["rows"]) == 2
    assert storm["rows"][0]["lat"] == 15.2
    assert storm["rows"][0]["lon"] == -60.4
    assert storm["rows"][0]["wind_kt"] == 60
    assert storm["rows"][1]["status"] == "HU"


@pytest.mark.parametrize("wind,pressure", [("bad", "995"), ("60", "bad")])
def test_atcf_best_track_parser_contains_malformed_numeric_cells(wind, pressure):
    storm = archive_worker.parse_atcf_btk(
        _atcf_row(wind=wind, pressure=pressure)
    )

    assert storm is not None
    assert len(storm["rows"]) == 1
    assert storm["rows"][0]["wind_kt"] == (None if wind == "bad" else 60)
    assert storm["rows"][0]["pres_mb"] == (
        None if pressure == "bad" else 995
    )
