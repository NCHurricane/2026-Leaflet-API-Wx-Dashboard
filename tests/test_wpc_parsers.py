from __future__ import annotations

import json
import zipfile

import pytest

from config.wpc_config import WPC_PRODUCTS
import workers.wpc_worker as wpc


def _polygon(west: float = -84.0, *, hole: bool = False) -> str:
    inner = ""
    if hole:
        inner = f"""
        <innerBoundaryIs><LinearRing><coordinates>
          {west + 0.5},34.5,0 {west + 1},34.5,0 {west + 1},35,0
          {west + 0.5},34.5,0
        </coordinates></LinearRing></innerBoundaryIs>
        """
    return f"""
    <Polygon>
      <outerBoundaryIs><LinearRing><coordinates>
        {west},34,0 {west + 2},34,0 {west + 2},36,0 {west},34,0
      </coordinates></LinearRing></outerBoundaryIs>
      {inner}
    </Polygon>
    """


def _kml(*body: str) -> str:
    return (
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        + "".join(body)
        + "</Document></kml>"
    )


def _placemark(
    name: str,
    *,
    style: str = "",
    geometry: str | None = None,
    description: str = "",
) -> str:
    style_xml = f"<styleUrl>#{style}</styleUrl>" if style else ""
    description_xml = (
        f"<description><![CDATA[{description}]]></description>"
        if description
        else ""
    )
    return (
        f"<Placemark><name>{name}</name>{style_xml}{description_xml}"
        f"{geometry if geometry is not None else _polygon()}</Placemark>"
    )


def test_ero_parser_maps_categories_sorts_risk_and_preserves_geometry():
    kml = _kml(
        _placemark("Slight (At Least 15%)", geometry=_polygon(-82)),
        _placemark("Marginal (At Least 5%)", geometry=_polygon(-86, hole=True)),
        _placemark("General Thunderstorms"),
        _placemark("High", geometry="<Point><coordinates>-80,35</coordinates></Point>"),
    )

    features = wpc._parse_ero_kml(kml)

    assert [feature["properties"]["category"] for feature in features] == [
        "MRGL",
        "SLGT",
    ]
    assert [feature["properties"]["rank"] for feature in features] == [1, 2]
    assert len(features[0]["geometry"]["coordinates"]) == 2
    assert features[0]["geometry"]["coordinates"][0][0] == [-86.0, 34.0]


def test_qpf_parser_decodes_kml_abgr_styles_and_sorts_thresholds():
    kml = _kml(
        """
        <Style id="half-inch"><PolyStyle><color>ff008b00</color></PolyStyle></Style>
        """,
        _placemark("QPF 1.00 inches", geometry=_polygon(-80)),
        _placemark(
            "QPF 0.50 inches",
            style="half-inch",
            geometry=_polygon(-84),
        ),
        _placemark("No numeric threshold", geometry=_polygon(-88)),
    )

    features = wpc._parse_qpf_kml(kml)

    assert [feature["properties"]["threshold"] for feature in features] == [
        0.5,
        1.0,
    ]
    assert features[0]["properties"]["color"] == "#008B00"
    assert features[1]["properties"]["color"] == "#888888"
    assert features[0]["properties"]["label"] == "≥ 0.5 in"


def test_winter_and_flood_outlook_parsers_keep_only_known_categories():
    winter_kml = _kml(
        """
        <Style id="poly_high"><PolyStyle><color>ff0000ff</color></PolyStyle></Style>
        """,
        _placemark("High probability", style="poly_high", geometry=_polygon(-80)),
        _placemark("Slight probability", style="poly_slight", geometry=_polygon(-84)),
        _placemark("Unknown probability", style="other", geometry=_polygon(-88)),
    )
    fop_kml = _kml(
        """
        <Style id="likely-style"><PolyStyle><color>ff00aaff</color></PolyStyle></Style>
        """,
        _placemark("LIKELY", style="likely-style", geometry=_polygon(-80)),
        _placemark("possible", geometry=_polygon(-84)),
        _placemark("UNKNOWN", geometry=_polygon(-88)),
    )

    winter = wpc._parse_winter_kml(winter_kml)
    flood = wpc._parse_fop_kml(fop_kml)

    assert [feature["properties"]["probability"] for feature in winter] == [
        10,
        70,
    ]
    assert winter[0]["properties"]["color"] == "#00C5F1"
    assert winter[1]["properties"]["color"] == "#FF0000"
    assert [feature["properties"]["category"] for feature in flood] == [
        "POSSIBLE",
        "LIKELY",
    ]
    assert flood[1]["properties"]["color"] == "#FFAA00"


def test_mpd_parser_normalizes_fields_category_and_month_boundary_times():
    description = """
    <table>
      <tr><td>MPDNumber</td><td>0042</td></tr>
      <tr><td>MPDType</td><td>Heavy rainfall, flash flooding likely</td></tr>
      <tr><td>IssueTime</td><td>Aug 31 2026 900 PM EDT</td></tr>
      <tr><td>ValidStart</td><td>312300</td></tr>
      <tr><td>ValidEndTi</td><td>010200</td></tr>
      <tr><td>WFO</td><td>RAH</td></tr>
      <tr><td>RFC</td><td>SERFC</td></tr>
      <tr><td>MPD</td><td>https://example.test/mpd42</td></tr>
      <tr><td>Area</td><td>12000</td></tr>
    </table>
    """
    kml = _kml(_placemark("MPD 42", description=description))

    features = wpc._parse_mpd_kml(kml, "0042")

    assert len(features) == 1
    props = features[0]["properties"]
    assert features[0]["id"] == "wpc-mpd-42"
    assert props["category"] == "LIKELY"
    assert props["mpd_number"] == 42
    assert props["valid_start"] == "2026-08-31T23:00:00+00:00"
    assert props["valid_end"] == "2026-09-01T02:00:00+00:00"
    assert props["wfo"] == "RAH"
    assert props["rfc"] == "SERFC"
    assert props["area_square_miles"] == "12000"


def test_mpd_parser_falls_back_from_malformed_number_and_time_fields():
    description = """
    <table>
      <tr><td>MPDNumber</td><td>not-a-number</td></tr>
      <tr><td>IssueTime</td><td>Aug 1 2026 900 PM EDT</td></tr>
      <tr><td>ValidStart</td><td>019999</td></tr>
    </table>
    """
    kml = _kml(_placemark("Malformed MPD", description=description))

    features = wpc._parse_mpd_kml(kml, "0043")

    assert features[0]["id"] == "wpc-mpd-43"
    assert features[0]["properties"]["mpd_number"] == 43
    assert features[0]["properties"]["valid_start"] is None


def test_mpd_index_and_discussion_parsers_handle_provider_html():
    index = """
    <a href="metwatch_mpd_multi.php?md=0042&amp;yr=2026">42</a>
    <a href="metwatch_mpd_multi.php?md=0043&yr=2026">43</a>
    <a href="metwatch_mpd_multi.php?md=0042&amp;yr=2026">duplicate</a>
    """
    page = "<html><pre>Line &amp; one<br>Line two</pre></html>"
    ero = """Header
Day 1
First discussion
Day 2
Second discussion
Day 3
Third discussion
Day 4 and Day 5
Extended discussion
"""

    assert wpc._active_mpd_ids(index) == ["0042", "0043"]
    assert wpc._discussion_text(page) == "Line & oneLine two"
    assert wpc._ero_discussion_for_day(ero, 1) == "Day 1\nFirst discussion"
    assert wpc._ero_discussion_for_day(ero, 4) == (
        "Day 4 and Day 5\nExtended discussion"
    )
    assert wpc._ero_discussion_for_day(ero, 5) == (
        "Day 4 and Day 5\nExtended discussion"
    )


def test_surface_geojson_parsers_normalize_valid_features_and_empty_inputs():
    single_product = {
        "id": "surface_qpf_d1",
        "label": "Rain — Day 1",
        "color": "#4169E1",
    }
    single = json.dumps(
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-84, 34], [-82, 34], [-82, 36], [-84, 34]]],
            },
            "properties": {
                "popupContent": "Rain area<br>Issued by WPC: Aug 7, 2026"
            },
        }
    )
    empty_single = json.dumps(
        {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[]]},
            "properties": {},
        }
    )
    collection_product = {
        "id": "surface_ero_d1",
        "label": "Excessive Rainfall — Day 1",
    }
    collection = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[-84, 34], [-82, 34], [-82, 36], [-84, 34]]
                        ],
                    },
                    "properties": {
                        "LABEL": "MRGL",
                        "LABEL2": "Marginal Risk",
                        "fill": "#00FF00",
                    },
                },
                {"type": "metadata"},
                None,
                42,
            ],
        }
    )

    parsed_single = wpc._parse_geojson_single(single, single_product)
    parsed_collection = wpc._parse_geojson_fc(collection, collection_product)

    assert parsed_single[0]["properties"]["label"] == "Rain area"
    assert parsed_single[0]["properties"]["color"] == "#4169E1"
    assert wpc._parse_geojson_single(empty_single, single_product) == []
    assert wpc._parse_geojson_single("[]", single_product) == []
    assert parsed_collection[0]["properties"]["label"] == "Marginal Risk"
    assert parsed_collection[0]["properties"]["category"] == "MRGL"
    assert parsed_collection[0]["properties"]["color"] == "#00FF00"


def test_ero_empty_provider_product_is_published_as_legitimate_empty(
    tmp_path,
    monkeypatch,
):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    product = WPC_PRODUCTS["ero"][0]
    with zipfile.ZipFile(raw_dir / "ero_day1.kmz", "w") as archive:
        archive.writestr("doc.kml", _kml())
    (raw_dir / "ero_discussion.html").write_text(
        "<pre>Day 1\nNo risk area.\nDay 2\nLater.</pre>",
        encoding="utf-8",
    )
    monkeypatch.setattr(wpc, "CACHE_DIR", tmp_path / "cache")

    count, error = wpc._process_layer(product, force=True, raw_dir=raw_dir)

    payload = json.loads(
        (tmp_path / "cache" / product["cache_path"]).read_text(encoding="utf-8")
    )
    assert (count, error) == (0, "")
    assert payload["geojson"] == {"type": "FeatureCollection", "features": []}
    assert payload["empty_message"] == product["empty_message"]


@pytest.mark.parametrize("raw", ["not json", "[]", "null", "42"])
def test_surface_feature_collection_parser_rejects_malformed_top_level(raw):
    product = {"id": "surface_ero_d1", "label": "ERO Day 1"}

    assert wpc._parse_geojson_fc(raw, product) == []
