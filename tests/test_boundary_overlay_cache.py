import json

import pytest
from fastapi import HTTPException

import routes.overlays as overlays


def _endpoint(path):
    router = overlays.create_overlays_router()
    return next(route.endpoint for route in router.routes if route.path == path)


def test_us_boundary_route_filters_layers_and_sets_long_lived_cache(monkeypatch):
    monkeypatch.setattr(
        overlays,
        "get_us_boundaries_geojson",
        lambda: {
            "type": "FeatureCollection",
            "properties": {"cache_version": 3},
            "features": [
                {"type": "Feature", "properties": {"layer": "state"}, "geometry": None},
                {"type": "Feature", "properties": {"layer": "county"}, "geometry": None},
            ],
        },
    )

    response = _endpoint("/api/overlay/us-boundaries")(layer="state")
    payload = json.loads(response.body)

    assert [feature["properties"]["layer"] for feature in payload["features"]] == ["state"]
    assert response.headers["cache-control"] == "public, max-age=604800, immutable"


def test_us_boundary_route_rejects_unknown_layer(monkeypatch):
    monkeypatch.setattr(overlays, "get_us_boundaries_geojson", lambda: {"features": []})

    with pytest.raises(HTTPException) as error:
        _endpoint("/api/overlay/us-boundaries")(layer="city")

    assert error.value.status_code == 400


def test_world_boundary_route_sets_long_lived_cache(monkeypatch):
    monkeypatch.setattr(
        overlays,
        "get_world_borders_geojson",
        lambda: {"type": "FeatureCollection", "features": []},
    )

    response = _endpoint("/api/overlay/world-borders")()

    assert response.headers["cache-control"] == "public, max-age=604800, immutable"
