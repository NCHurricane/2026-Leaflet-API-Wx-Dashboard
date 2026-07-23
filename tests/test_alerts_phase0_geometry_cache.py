from __future__ import annotations

from shapely.geometry import Polygon

import alerts.alerts_utils as alerts_utils
import services.alerts_service as alerts_service


def _feature(zone: str) -> dict:
    return {
        "type": "Feature",
        "properties": {"affectedZones": [zone], "geocode": {"SAME": []}},
        "geometry": None,
    }


def test_enriched_geometry_reuses_process_local_cache(monkeypatch):
    calls = []
    polygon = Polygon([(-80, 35), (-79, 35), (-79, 36), (-80, 35)])

    monkeypatch.setattr(alerts_utils, "_prefetch_zone_geometries", lambda features: None)

    def resolve(zones):
        calls.append(tuple(zones))
        return polygon

    monkeypatch.setattr(alerts_utils, "_resolve_zone_geometry", resolve)
    with alerts_service._ENRICHED_GEOMETRY_CACHE_LOCK:
        alerts_service._ENRICHED_GEOMETRY_CACHE.clear()

    first = [_feature("https://api.weather.gov/zones/forecast/NCZ001")]
    second = [_feature("https://api.weather.gov/zones/forecast/NCZ001")]
    alerts_service.enrich_alert_features_geometry(first)
    alerts_service.enrich_alert_features_geometry(second)

    assert first[0]["geometry"] == second[0]["geometry"]
    assert calls == [("https://api.weather.gov/zones/forecast/NCZ001",)]


def test_enriched_geometry_cache_is_bounded(monkeypatch):
    polygon = Polygon([(-80, 35), (-79, 35), (-79, 36), (-80, 35)])
    monkeypatch.setattr(alerts_utils, "_prefetch_zone_geometries", lambda features: None)
    monkeypatch.setattr(alerts_utils, "_resolve_zone_geometry", lambda zones: polygon)
    monkeypatch.setattr(alerts_service, "_ENRICHED_GEOMETRY_CACHE_MAX_ENTRIES", 2)
    with alerts_service._ENRICHED_GEOMETRY_CACHE_LOCK:
        alerts_service._ENRICHED_GEOMETRY_CACHE.clear()

    for index in range(3):
        alerts_service.enrich_alert_features_geometry(
            [_feature(f"https://api.weather.gov/zones/forecast/NCZ00{index}")]
        )

    assert len(alerts_service._ENRICHED_GEOMETRY_CACHE) == 2
