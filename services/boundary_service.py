"""Boundary overlay GeoJSON builders and cache readers."""

from typing import Any, cast
import json
import os
import threading

from app_core.paths import CACHE_ROOT

_WORLD_BORDERS_CACHE_PATH = os.path.join(CACHE_ROOT, "overlays", "world_borders.geojson")
_WORLD_BORDERS_CACHE_VERSION = 3
_world_borders_lock = threading.Lock()
_world_borders_data: dict | None = None

_US_BOUNDARIES_CACHE_PATH = os.path.join(CACHE_ROOT, "overlays", "us_boundaries.geojson")
_US_BOUNDARIES_CACHE_VERSION = 3
_us_boundaries_lock = threading.Lock()
_us_boundaries_data: dict | None = None


def get_world_borders_geojson() -> dict:
    global _world_borders_data
    with _world_borders_lock:
        if _world_borders_data is not None:
            return _world_borders_data
        if os.path.exists(_WORLD_BORDERS_CACHE_PATH):
            try:
                with open(_WORLD_BORDERS_CACHE_PATH, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                props = data.get("properties") if isinstance(data, dict) else {}
                props = props if isinstance(props, dict) else {}
                if props.get("cache_version") == _WORLD_BORDERS_CACHE_VERSION:
                    _world_borders_data = data
                    return data
            except Exception:
                pass
        data = _build_world_borders_geojson()
        os.makedirs(os.path.dirname(_WORLD_BORDERS_CACHE_PATH), exist_ok=True)
        try:
            with open(_WORLD_BORDERS_CACHE_PATH, "w", encoding="utf-8") as fh:
                json.dump(data, fh, separators=(",", ":"))
        except Exception as exc:
            print(f"[world-borders] Cache write failed: {exc}")
        _world_borders_data = data
        return data


def get_us_boundaries_geojson() -> dict:
    global _us_boundaries_data
    with _us_boundaries_lock:
        if _us_boundaries_data is not None:
            return _us_boundaries_data
        if os.path.exists(_US_BOUNDARIES_CACHE_PATH):
            try:
                with open(_US_BOUNDARIES_CACHE_PATH, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                props = data.get("properties") if isinstance(data, dict) else {}
                props = props if isinstance(props, dict) else {}
                if props.get("cache_version") == _US_BOUNDARIES_CACHE_VERSION:
                    _us_boundaries_data = data
                    return data
            except Exception:
                pass
        data = _build_us_boundaries_geojson()
        os.makedirs(os.path.dirname(_US_BOUNDARIES_CACHE_PATH), exist_ok=True)
        try:
            with open(_US_BOUNDARIES_CACHE_PATH, "w", encoding="utf-8") as fh:
                json.dump(data, fh, separators=(",", ":"))
        except Exception as exc:
            print(f"[us-boundaries] Cache write failed: {exc}")
        _us_boundaries_data = data
        return data


def _iter_line_geometries(geom):
    if geom is None or geom.is_empty:
        return
    if geom.geom_type in {"LineString", "MultiLineString"}:
        yield geom
        return
    if geom.geom_type == "GeometryCollection":
        for part in cast(Any, geom).geoms:
            yield from _iter_line_geometries(part)


def _build_world_borders_geojson() -> dict:
    """Return coastlines and land-only country borders as GeoJSON."""
    import cartopy.io.shapereader as shpreader
    from shapely.geometry import mapping
    from shapely.ops import unary_union

    features = []

    try:
        land_shp = shpreader.natural_earth(
            resolution="10m", category="physical", name="land"
        )
        reader = shpreader.Reader(land_shp)
        for geom in reader.geometries():
            if geom is None or geom.is_empty:
                continue
            polys = cast(Any, geom).geoms if geom.geom_type == "MultiPolygon" else [geom]
            for poly in polys:
                poly_obj = cast(Any, poly)
                if not hasattr(poly_obj, "exterior"):
                    continue
                ext = list(poly_obj.exterior.coords)
                if len(ext) >= 2:
                    features.append(
                        {
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": ext},
                            "properties": {},
                        }
                    )
    except Exception as exc:
        print(f"[world-borders] Land/coastline load failed: {exc}")

    lake_geometry = None
    try:
        lakes_shp = shpreader.natural_earth(
            resolution="10m", category="physical", name="lakes"
        )
        lake_geoms = [
            geom
            for geom in shpreader.Reader(lakes_shp).geometries()
            if geom is not None and not geom.is_empty
        ]
        if lake_geoms:
            lake_geometry = unary_union(lake_geoms)
    except Exception as exc:
        print(f"[world-borders] Lake geometry load failed: {exc}")

    try:
        borders_shp = shpreader.natural_earth(
            resolution="10m", category="cultural", name="admin_0_boundary_lines_land"
        )
        reader = shpreader.Reader(borders_shp)
        for geom in reader.geometries():
            if geom is None or geom.is_empty:
                continue
            if lake_geometry is not None:
                geom = geom.difference(lake_geometry)
            for line_geom in _iter_line_geometries(geom):
                features.append(
                    {
                        "type": "Feature",
                        "geometry": mapping(line_geom),
                        "properties": {},
                    }
                )
    except Exception as exc:
        print(f"[world-borders] Border lines load failed: {exc}")

    return {
        "type": "FeatureCollection",
        "properties": {"cache_version": _WORLD_BORDERS_CACHE_VERSION},
        "features": features,
    }


def _build_us_boundaries_geojson() -> dict:
    """Return US state and county boundary GeoJSON."""
    import cartopy.io.shapereader as shpreader
    from shapely.geometry import mapping
    from shapely.ops import unary_union

    from lib.geo_utils import CensusCounties, load_state_geometries

    features = []
    lake_mask = None

    try:
        lakes_shp = shpreader.natural_earth(
            resolution="10m", category="physical", name="lakes"
        )
        lake_geoms = [
            geom
            for geom in shpreader.Reader(lakes_shp).geometries()
            if geom is not None and not geom.is_empty
        ]
        if lake_geoms:
            lake_geometry = unary_union(lake_geoms)
            lake_mask = lake_geometry.buffer(-0.02)
            if lake_mask.is_empty:
                lake_mask = lake_geometry
    except Exception as exc:
        print(f"[us-boundaries] Lake geometry load failed: {exc}")

    try:
        state_geoms = load_state_geometries() or {}
        for state_code, geom in state_geoms.items():
            if geom is None or getattr(geom, "is_empty", False):
                continue
            state_boundary = geom.boundary
            if lake_mask is not None:
                state_boundary = state_boundary.difference(lake_mask)
            for line_geom in _iter_line_geometries(state_boundary):
                features.append(
                    {
                        "type": "Feature",
                        "geometry": mapping(line_geom),
                        "properties": {"layer": "state", "state": state_code},
                    }
                )
    except Exception as exc:
        print(f"[us-boundaries] State geometry load failed: {exc}")

    try:
        CensusCounties.load()
        county_geoms = getattr(CensusCounties, "_fips_map", {}) or {}
        for fips, geom in county_geoms.items():
            if geom is None or getattr(geom, "is_empty", False):
                continue
            geo = getattr(geom, "__geo_interface__", None)
            if not geo:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": geo,
                    "properties": {"layer": "county", "fips": fips},
                }
            )
    except Exception as exc:
        print(f"[us-boundaries] County geometry load failed: {exc}")

    return {
        "type": "FeatureCollection",
        "properties": {"cache_version": _US_BOUNDARIES_CACHE_VERSION},
        "features": features,
    }
