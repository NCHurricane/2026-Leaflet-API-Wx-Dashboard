from routes.alerts import router as alerts_router
from routes.archive import router as archive_router
from routes.core import router as core_router
from routes.radar import router as radar_router
from routes.rtma import router as rtma_router
from routes.satellite_v2 import router as satellite_router
from routes.surface import router as surface_router
from routes.tropical import router as tropical_router


def _route_paths(router):
    return {route.path for route in router.routes}


def test_batch_b1_routes_are_not_registered():
    assert "/api/alerts/polygons" not in _route_paths(alerts_router)
    assert "/api/data/colormap" not in _route_paths(surface_router)
    assert "/api/data/rtma/grid" not in _route_paths(rtma_router)
    assert "/api/satellite-v2/status" not in _route_paths(satellite_router)
    assert "/api/tropical/summary" not in _route_paths(tropical_router)
    assert "/api/radar/sites" not in _route_paths(radar_router)
    assert "/api/radar/site-locations" not in _route_paths(radar_router)


def test_batch_b1_replacement_routes_remain_registered():
    assert "/api/data/alerts" in _route_paths(alerts_router)
    assert "/api/data/surface-gradient" in _route_paths(surface_router)
    assert "/api/data/rtma/points" in _route_paths(rtma_router)
    assert "/api/satellite-v2/catalog" in _route_paths(satellite_router)
    assert "/api/tropical/storms" in _route_paths(tropical_router)
    assert "/api/radar/live/sites" in _route_paths(radar_router)


def test_batch_b2_radar_debug_route_is_not_registered():
    assert "/api/radar/debug/meso-raw" not in _route_paths(radar_router)


def test_batch_c_disconnected_archive_routes_are_not_registered():
    assert "/api/archive/mrms" not in _route_paths(archive_router)
    assert "/api/archive/result" not in _route_paths(archive_router)
    assert "/api/archive/spc" not in _route_paths(archive_router)
    assert "/api/progress/{task_id}" not in _route_paths(core_router)


def test_batch_c_active_archive_and_core_routes_remain_registered():
    assert "/api/archive/alerts" in _route_paths(archive_router)
    assert "/api/archive/surface" in _route_paths(archive_router)
    assert "/api/status" in _route_paths(core_router)
    assert "/api/user-settings/defaults" in _route_paths(core_router)
