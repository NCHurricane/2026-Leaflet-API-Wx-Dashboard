from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

import services.spc_service as spc_service
from spc import spc_utils


@pytest.fixture(autouse=True)
def _clear_spc_active_cache():
    spc_service._SPC_ACTIVE_CACHE.clear()
    yield
    spc_service._SPC_ACTIVE_CACHE.clear()


@pytest.fixture
def active_polygon():
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [-82.0, 34.0],
                [-78.0, 34.0],
                [-78.0, 37.0],
                [-82.0, 34.0],
            ]
        ],
    }


def test_outlook_and_fire_fetchers_preserve_geojson_and_product_urls(monkeypatch):
    payload = {"type": "FeatureCollection", "features": []}
    urls = []

    def fetch(url):
        urls.append(url)
        return payload

    monkeypatch.setattr(spc_utils, "_request_json", fetch)

    outlook, outlook_source = spc_utils.fetch_outlook_geojson(1, "torn")
    fire, fire_source = spc_utils.fetch_fire_wx_geojson(4, "drytprob")

    assert outlook is payload
    assert fire is payload
    assert outlook_source == "NWS SPC GeoJSON"
    assert fire_source == "SPC Fire Wx GeoJSON"
    assert urls == [
        "https://www.spc.noaa.gov/products/outlook/day1otlk_torn.lyr.geojson",
        "https://www.spc.noaa.gov/products/exper/fire_wx/day4fw_drytprob.lyr.geojson",
    ]


def test_request_text_honors_retry_after_before_retrying(monkeypatch):
    responses = iter(
        [
            SimpleNamespace(
                status_code=429,
                headers={"Retry-After": "2"},
                text="rate limited",
                raise_for_status=lambda: None,
            ),
            SimpleNamespace(
                status_code=200,
                headers={},
                text="ok",
                raise_for_status=lambda: None,
            ),
        ]
    )
    sleeps = []
    monkeypatch.setattr(spc_utils.requests, "get", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(spc_utils.time, "sleep", sleeps.append)

    assert spc_utils._request_text("https://example.test", retries=2) == "ok"
    assert sleeps == [2.0]


def test_request_text_uses_bounded_backoff_and_jitter(monkeypatch):
    response = SimpleNamespace(
        status_code=503,
        headers={},
        text="unavailable",
        raise_for_status=lambda: None,
    )
    sleeps = []
    monkeypatch.setattr(spc_utils.requests, "get", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(spc_utils.random, "uniform", lambda *_args: 0.125)
    monkeypatch.setattr(spc_utils.time, "sleep", sleeps.append)

    with pytest.raises(RuntimeError, match="HTTP 503"):
        spc_utils._request_text("https://example.test", retries=3)

    assert sleeps == [0.625, 1.125]


def test_request_json_uses_stdlib_json_decoder(monkeypatch):
    monkeypatch.setattr(spc_utils, "_request_text", lambda *_args, **_kwargs: '{"ok": true}')
    assert spc_utils._request_json("https://example.test") == {"ok": True}


def test_outlook_and_fire_bulletin_and_impacts_fixtures():
    outlook_html = """
        <html><pre>Day 1 Convective Outlook\nIssued 1200 UTC\n...SUMMARY...\nSevere storms.</pre></html>
    """
    impacts_html = """
        <table>
          <tr><td>Risk</td><td>Area</td><td>Population</td><td>Centers</td></tr>
          <tr><td>Enhanced</td><td>12,000</td><td>2,000,000</td><td>Charlotte...Raleigh</td></tr>
        </table>
    """
    fire_html = """
        <html><pre>Day 2 Fire Weather Outlook\nCritical fire weather is expected.</pre>
        <table>
          <tr><td>Risk</td><td>Area (Sq. Mi.)</td><td>Population</td><td>Population Centers</td></tr>
          <tr><td>Critical</td><td>5,000</td><td>100,000</td><td>Amarillo...Lubbock</td></tr>
        </table></html>
    """

    outlook = spc_utils._extract_outlook_bulletin(outlook_html, 1)
    impacts = spc_utils._parse_outlook_impacts_table(impacts_html)
    fire = spc_utils._extract_fire_outlook_bulletin(fire_html, 2)
    fire_impacts = spc_utils._extract_embedded_impacts_table(fire_html)

    assert "Day 1 Convective Outlook" in outlook
    assert "Severe storms." in outlook
    assert impacts == [
        {
            "risk": "Enhanced",
            "area_sq_mi": "12,000",
            "population": "2,000,000",
            "population_centers": ["Charlotte", "Raleigh"],
        }
    ]
    assert "Critical fire weather is expected." in fire
    assert fire_impacts[0]["risk"] == "Critical"
    assert fire_impacts[0]["population_centers"] == ["Amarillo", "Lubbock"]


def test_report_csv_fallback_filters_type_and_normalizes_coordinates(monkeypatch):
    report_csv = """Time,F_Scale,Location,County,State,Lat,Lon,Comments
1205,EF1,Asheville,Buncombe,NC,3544,8254,Tornado damage
Time,Speed,Location,County,State,Lat,Lon,Comments
1210,70,Charlotte,Mecklenburg,NC,3523,8084,Trees down
"""

    def fetch(url):
        if "_wind.csv" in url:
            raise RuntimeError("typed report unavailable")
        return report_csv

    monkeypatch.setattr(spc_utils, "_request_text", fetch)

    rows, source = spc_utils.fetch_reports_rows(
        datetime(2026, 8, 6, tzinfo=timezone.utc),
        report_mode="filtered",
        report_type="wind",
    )

    assert source == "SPC Storm Reports CSV"
    assert rows == [
        {
            "event": "Wind",
            "time": "1210",
            "magnitude": "70",
            "location": "Charlotte",
            "county": "Mecklenburg",
            "state": "NC",
            "remarks": "Trees down",
            "lat": 35.23,
            "lon": -80.84,
        }
    ]


def test_watch_wou_probability_and_public_text_parsers(monkeypatch):
    monkeypatch.setattr(spc_utils.CensusCounties, "load", lambda: None)
    monkeypatch.setattr(
        spc_utils.CensusCounties,
        "_records_map",
        {"37001": SimpleNamespace(attributes={"STUSPS": "NC", "STATEFP": "37"})},
    )
    wou = "NCC001-003-005-071200-\n.260807T1200Z-260807T1800Z/"
    probability_text = """
PROB OF 2 OR MORE TORNADOES : MODERATE (40%)
PROB OF 1 OR MORE WIND EVENTS >= 65 KNOTS : HIGH (70%)
"""
    probability_html = """
        <table><tr><td>Probability of 10 or more severe hail events</td>
        <td>Moderate (60%)</td></tr></table>
    """
    detail_html = """
        <pre>SEVERE THUNDERSTORM WATCH NUMBER 999\nWrong bulletin.</pre>
        <pre>TORNADO WATCH NUMBER 123\nPrimary watch narrative.</pre>
    """

    county_fips = spc_utils._parse_watch_county_fips_from_wou(wou)
    issue, expire = spc_utils._parse_watch_window_from_wou(wou)
    text_probs = spc_utils._parse_watch_probability_table(probability_text)
    html_probs = spc_utils._parse_watch_probability_page(probability_html)
    public_text = spc_utils._extract_watch_public_text(detail_html, "0123")

    assert county_fips == ["37001", "37003", "37005"]
    assert issue == datetime(2026, 8, 7, 12, tzinfo=timezone.utc)
    assert expire == datetime(2026, 8, 7, 18, tzinfo=timezone.utc)
    assert text_probs == {"tor2": "MODERATE (40%)", "wind65": "HIGH (70%)"}
    assert html_probs == {"hail10": "Moderate (60%)"}
    assert "TORNADO WATCH NUMBER 123" in public_text
    assert "Wrong bulletin" not in public_text


def test_active_watch_parser_skips_malformed_ids_and_enriches_valid_watch(
    monkeypatch, active_polygon
):
    features = [
        {"properties": {"num": "not-a-number"}, "geometry": active_polygon},
        {
            "properties": {
                "num": 123,
                "type": "TOR",
                "utc_issued": "2026-08-07T12:00:00Z",
                "utc_expired": "2099-08-07T18:00:00Z",
            },
            "geometry": active_polygon,
        },
    ]
    monkeypatch.setattr(
        spc_utils,
        "_cached_json",
        lambda *_args, **_kwargs: {
            "type": "FeatureCollection",
            "features": features,
        },
    )
    monkeypatch.setattr(
        spc_utils,
        "_fetch_watch_modal_details",
        lambda *_args, **_kwargs: (
            "Tornado watch narrative",
            {"tor2": "Moderate (40%)"},
        ),
    )
    monkeypatch.setattr(
        spc_utils,
        "_fetch_wou_county_fips",
        lambda *_args, **_kwargs: ["37001"],
    )

    items, source = spc_utils.fetch_active_watch_items(with_counties=True)

    assert source == "SPC Watches (IEM)"
    assert len(items) == 1
    assert items[0]["id"] == "0123"
    assert items[0]["type"] == "Tornado Watch"
    assert items[0]["issue_utc"] == datetime(2026, 8, 7, 12, tzinfo=timezone.utc)
    assert items[0]["county_fips"] == ["37001"]
    assert items[0]["probabilities"] == {"tor2": "Moderate (40%)"}
    assert items[0]["full_text"] == "Tornado watch narrative"


def test_md_rss_fixture_and_active_parser_skip_malformed_ids(
    monkeypatch, active_polygon
):
    rss = """<?xml version="1.0"?>
    <rss><channel><item>
      <title>Mesoscale Discussion 45</title>
      <link>https://www.spc.noaa.gov/products/md/md0045.html</link>
      <description><![CDATA[<pre>Mesoscale Discussion #45\nSevere storms are likely.</pre>]]></description>
    </item></channel></rss>"""
    monkeypatch.setattr(spc_utils, "_cached_text", lambda *_args, **_kwargs: rss)
    rss_map = spc_utils._build_spc_md_rss_text_map()

    features = [
        {"properties": {"num": "bad"}, "geometry": active_polygon},
        {
            "properties": {
                "num": 45,
                "issue": "2026-08-07T13:00:00Z",
                "expire": "2099-08-07T15:00:00Z",
                "concerning": "Severe thunderstorms",
            },
            "geometry": active_polygon,
        },
    ]
    monkeypatch.setattr(
        spc_utils,
        "_cached_json",
        lambda *_args, **_kwargs: {
            "type": "FeatureCollection",
            "features": features,
        },
    )
    monkeypatch.setattr(
        spc_utils,
        "_build_spc_md_rss_text_map",
        lambda **_kwargs: rss_map,
    )
    monkeypatch.setattr(
        spc_utils,
        "_fetch_spc_md_detail_text",
        lambda *_args, **_kwargs: pytest.fail("RSS text should avoid HTML fallback"),
    )

    items, source = spc_utils.fetch_active_md_items()

    assert source == "SPC Mesoscale Discussions (IEM + SPC RSS text)"
    assert len(items) == 1
    assert items[0]["id"] == "0045"
    assert items[0]["issue_utc"] == datetime(2026, 8, 7, 13, tzinfo=timezone.utc)
    assert "Severe storms are likely." in items[0]["full_text"]


def test_active_md_parser_uses_html_text_when_rss_is_empty(monkeypatch, active_polygon):
    monkeypatch.setattr(
        spc_utils,
        "_cached_json",
        lambda *_args, **_kwargs: {
            "features": [
                {
                    "properties": {
                        "num": 46,
                        "issue": "2026-08-07T14:00:00Z",
                        "expire": "2099-08-07T16:00:00Z",
                    },
                    "geometry": active_polygon,
                }
            ]
        },
    )
    monkeypatch.setattr(spc_utils, "_build_spc_md_rss_text_map", lambda **_kwargs: {})
    monkeypatch.setattr(
        spc_utils,
        "_fetch_spc_md_detail_text",
        lambda *_args, **_kwargs: "HTML fallback narrative",
    )

    items, source = spc_utils.fetch_active_md_items()

    assert source == "SPC Mesoscale Discussions (IEM + SPC HTML text fallback)"
    assert items[0]["full_text"] == "HTML fallback narrative"


def test_cached_empty_outlook_is_current_legitimate_empty(tmp_path, monkeypatch):
    spc_cache = tmp_path / "spc"
    spc_cache.mkdir()
    (spc_cache / "1_cat.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [],
                "_source": "NWS SPC GeoJSON",
                "_issued": "2026-08-07T12:00:00+00:00",
                "_updated": "2026-08-07T12:05:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(spc_service, "CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(spc_service, "SPC_OUTLOOK_SCHEDULES", {})
    monkeypatch.setattr(
        spc_utils,
        "fetch_outlook_modal_details",
        lambda *_args, **_kwargs: {"text": "", "impacts": [], "source_url": ""},
    )

    result = spc_service.get_spc_outlook(day=1, hazard="cat")

    assert result["features"] == []
    assert result["count"] == 0
    assert result["cache_state"] == "current"
    assert result["retry_after_seconds"] is None


@pytest.mark.parametrize(
    ("product", "expected_product"),
    [("watches", "watches"), ("mds", "mds")],
)
def test_active_products_preserve_product_specific_empty_success(
    product, expected_product, monkeypatch
):
    monkeypatch.setattr(
        spc_utils,
        "fetch_active_watch_items",
        lambda **_kwargs: ([], "SPC Watches (IEM)"),
    )
    monkeypatch.setattr(
        spc_utils,
        "fetch_active_md_items",
        lambda: ([], "SPC Mesoscale Discussions (IEM)"),
    )

    result = spc_service._get_spc_active_uncached(product=product)

    assert result["type"] == "FeatureCollection"
    assert result["features"] == []
    assert result["count"] == 0
    assert result["product"] == expected_product
    assert result["_updated"] is None


def test_active_cache_canonicalizes_watch_types_and_evicts_lru(monkeypatch):
    calls = []

    def load(**kwargs):
        calls.append(kwargs)
        return {"selection": kwargs["watch_types"]}

    monkeypatch.setattr(spc_service, "_get_spc_active_uncached", load)
    monkeypatch.setattr(spc_service, "_SPC_ACTIVE_CACHE_MAX_ENTRIES", 2)

    first = spc_service.get_spc_active(watch_types="SVR,TOR")
    equivalent = spc_service.get_spc_active(watch_types="tornado,severe")
    spc_service.get_spc_active(watch_types="TOR")
    spc_service.get_spc_active(watch_types="SVR")

    assert first is equivalent
    assert calls[0]["watch_types"] == "tor,svr"
    assert len(calls) == 3
    assert len(spc_service._SPC_ACTIVE_CACHE) == 2
    assert {key[2] for key in spc_service._SPC_ACTIVE_CACHE} == {"tor", "svr"}


def test_reports_preserve_legitimate_empty_success(monkeypatch):
    monkeypatch.setattr(
        spc_utils,
        "fetch_reports_rows",
        lambda **_kwargs: ([], "SPC Storm Reports CSV"),
    )

    result = spc_service.get_spc_reports(day="today")

    assert result["type"] == "FeatureCollection"
    assert result["features"] == []
    assert result["count"] == 0
    assert result["_source"] == "SPC Storm Reports CSV"
    assert result["report_day"] == "today"
