from routes.radar import router


def test_legacy_iem_tile_routes_are_not_registered():
    methods_by_path = {
        route.path: route.methods
        for route in router.routes
    }

    assert "/api/radar/tiles/{z}/{x}/{y}" not in methods_by_path
    assert "/api/radar/tiles/freshness" not in methods_by_path


def test_cache_first_live_routes_remain_registered():
    route_paths = {route.path for route in router.routes}

    assert "/api/radar/live/sites" in route_paths
    assert "/api/radar/live/latest" in route_paths
    assert "/api/radar/live/frames" in route_paths
    assert "/api/radar/live/value" in route_paths
    assert "/api/radar/live/storm-tracks" in route_paths
