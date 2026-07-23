from services.wpc_service import _shape_collection
from workers.wpc_worker import _parse_sigwx_kml, _parse_sigwx_metadata


EMPTY_SIGWX_KML = """\
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Snippet>Issued 5:04 AM EDT Thu, Jul 23, 2026
      Valid for Thu, Jul 23, 2026</Snippet>
    <GroundOverlay>
      <name>No Areas of Significant Weather are Expected</name>
    </GroundOverlay>
  </Document>
</kml>
"""


ISSUED_SIGWX_KML = """\
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Snippet>Issued 9:00 AM EDT Thu, Jul 23, 2026
      Valid for Thu, Jul 23, 2026</Snippet>
    <Placemark>
      <styleUrl>#severe</styleUrl>
      <Polygon>
        <outerBoundaryIs><LinearRing><coordinates>
          -84,34,0 -82,34,0 -82,36,0 -84,34,0
        </coordinates></LinearRing></outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>
"""


def test_sigwx_empty_kml_preserves_authoritative_issue_state() -> None:
    assert _parse_sigwx_kml(EMPTY_SIGWX_KML) == []

    metadata = _parse_sigwx_metadata(EMPTY_SIGWX_KML)

    assert metadata == {
        "issued_text": "Issued 5:04 AM EDT Thu, Jul 23, 2026",
        "valid_text": "Valid for Thu, Jul 23, 2026",
        "no_significant_weather": True,
    }


def test_sigwx_issued_polygon_is_parsed_with_metadata() -> None:
    features = _parse_sigwx_kml(ISSUED_SIGWX_KML)

    assert len(features) == 1
    assert features[0]["geometry"]["type"] == "Polygon"
    assert features[0]["properties"]["category"] == "severe"
    assert features[0]["properties"]["label"] == "Severe Thunderstorms"
    assert _parse_sigwx_metadata(ISSUED_SIGWX_KML)["no_significant_weather"] is False


def test_wpc_service_exposes_sigwx_issuance_metadata() -> None:
    product = {"id": "sigwx_day1", "label": "Day 1 Significant Weather"}
    payload = {
        "updated": "2026-07-23T16:30:32+00:00",
        "source_url": "https://www.wpc.ncep.noaa.gov/example.kml",
        "geojson": {"type": "FeatureCollection", "features": []},
        "empty_message": "No areas of significant weather are expected.",
        **_parse_sigwx_metadata(EMPTY_SIGWX_KML),
    }

    result = _shape_collection(
        payload,
        group="sigwx",
        day=1,
        product=product,
        status={"available": True, "status": "ok"},
        cache_age_seconds=10.0,
        stale=False,
    )

    assert result["issued_text"] == "Issued 5:04 AM EDT Thu, Jul 23, 2026"
    assert result["valid_text"] == "Valid for Thu, Jul 23, 2026"
    assert result["no_significant_weather"] is True
