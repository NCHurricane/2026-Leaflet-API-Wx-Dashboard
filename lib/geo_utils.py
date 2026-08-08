"""
Shared geospatial utilities for the Weather Dashboard.

Centralises US state geometry loading, CONUS geometry building, country-level
geometry, and the Census county shapefile class so every module (surface,
satellite, radar, MRMS, and alerts) shares a single cached copy instead
of maintaining independent duplicates.
"""

import os
import io
import zipfile
import warnings
import logging

from app_core.upstream_ledger import requests
import cartopy.io.shapereader as shpreader
import cartopy.crs as ccrs
from cartopy.feature import ShapelyFeature
from shapely.ops import unary_union
import shapefile as pyshp

# ── Lazy import for STATES_FULL to avoid circular dependency ─────────────
from config.geo_config import STATES_FULL


# ═════════════════════════════════════════════════════════════════════════════
# STATE / CONUS / COUNTRY GEOMETRY CACHES
# ═════════════════════════════════════════════════════════════════════════════

_STATE_GEOM_CACHE = None
_CONUS_GEOM_CACHE = None
_WORLD_LAND_GEOM_CACHE = None


def _configure_pyshp_logging() -> None:
    """Silence known non-fatal pyshp GeoJSON conversion warnings."""
    try:
        pyshp.VERBOSE = False
    except Exception:
        pass
    try:
        pyshp.logger.setLevel(logging.ERROR)
    except Exception:
        pass


def load_state_geometries():
    """Load and cache US state polygon geometries from Census Cartographic Boundaries.

    Attempts Census Cartographic Boundaries (2025, 500k simplified) for clean map
    visualization, then falls back to TIGER/Line (full resolution), then Natural Earth.

    Returns:
        dict[str, shapely.geometry.base.BaseGeometry]:
            Mapping of two-letter postal codes (e.g. ``"NC"``) to Shapely
            polygon/multipolygon geometries.
    """
    global _STATE_GEOM_CACHE
    if _STATE_GEOM_CACHE is not None:
        return _STATE_GEOM_CACHE

    states = {}

    # Try Census Cartographic Boundaries 2025 (500k, simplified for maps)
    cb_path = os.path.join(_SHARED_SHAPEFILE_DIR, "cb_2025_us_state_500k.shp")
    if os.path.exists(cb_path):
        try:
            _configure_pyshp_logging()
            reader = shpreader.Reader(cb_path)
            for record in reader.records():
                stusps = record.attributes.get("STUSPS", "").upper()
                if stusps and len(stusps) == 2:
                    states[stusps] = record.geometry
            if states:
                logging.getLogger(__name__).info(f"Loaded {len(states)} states from Census Cartographic Boundaries 2025")
                _STATE_GEOM_CACHE = states
                return states
        except Exception as e:
            logging.getLogger(__name__).warning(f"[WARN] Error loading Cartographic Boundary state shapefile: {type(e).__name__}")

    # Fallback to TIGER/Line 2025 state boundaries (full resolution, Census Bureau)
    tiger_path = os.path.join(_SHARED_SHAPEFILE_DIR, "tl_2025_us_state.shp")
    if os.path.exists(tiger_path):
        try:
            _configure_pyshp_logging()
            reader = shpreader.Reader(tiger_path)
            for record in reader.records():
                stusps = record.attributes.get("STUSPS", "").upper()
                if stusps and len(stusps) == 2:
                    states[stusps] = record.geometry
            if states:
                logging.getLogger(__name__).info(f"Loaded {len(states)} states from TIGER/Line 2025")
                _STATE_GEOM_CACHE = states
                return states
        except Exception as e:
            logging.getLogger(__name__).warning(f"[WARN] Error loading TIGER state shapefile: {type(e).__name__}")

    # Fallback to Natural Earth 10m
    shpfile = shpreader.natural_earth(
        resolution="10m", category="cultural", name="admin_1_states_provinces"
    )
    reader = shpreader.Reader(shpfile)
    for record in reader.records():
        if record.attributes.get("admin") == "United States of America":
            postal = record.attributes.get("postal", "").upper()
            if postal:
                states[postal] = record.geometry
    if not states:
        # Fallback to 50m if 10m yielded nothing
        shpfile = shpreader.natural_earth(
            resolution="50m", category="cultural", name="admin_1_states_provinces"
        )
        reader = shpreader.Reader(shpfile)
        for record in reader.records():
            if record.attributes.get("admin") == "United States of America":
                postal = record.attributes.get("postal", "").upper()
                if postal:
                    states[postal] = record.geometry
    _STATE_GEOM_CACHE = states
    return states


def build_conus_geometry():
    """Build and cache a lower-48 CONUS union geometry from state polygons.

    Returns:
        shapely.geometry.base.BaseGeometry or None
    """
    global _CONUS_GEOM_CACHE
    if _CONUS_GEOM_CACHE is not None:
        return _CONUS_GEOM_CACHE

    states = load_state_geometries()
    conus_codes = [
        code
        for code in STATES_FULL.keys()
        if code not in {"AK", "HI", "CONUS"} and code in states
    ]
    if not conus_codes:
        return None

    conus_geom = unary_union([states[code] for code in conus_codes]).buffer(0)
    _CONUS_GEOM_CACHE = conus_geom
    return _CONUS_GEOM_CACHE


def build_world_land_geometry():
    """Build and cache a global land polygon union from Natural Earth.

    Returns:
        shapely.geometry.base.BaseGeometry or None
    """
    global _WORLD_LAND_GEOM_CACHE
    if _WORLD_LAND_GEOM_CACHE is not None:
        return _WORLD_LAND_GEOM_CACHE

    # 10m provides maximum coastline detail for performance testing.
    shp_path = shpreader.natural_earth(
        resolution="10m", category="physical", name="land"
    )
    reader = shpreader.Reader(shp_path)
    geoms = [geom for geom in reader.geometries() if geom is not None]

    if not geoms:
        # Fallback to medium-resolution land polygons if needed.
        shp_path = shpreader.natural_earth(
            resolution="50m", category="physical", name="land"
        )
        reader = shpreader.Reader(shp_path)
        geoms = [geom for geom in reader.geometries() if geom is not None]

    if not geoms:
        return None

    _WORLD_LAND_GEOM_CACHE = unary_union(geoms).buffer(0)
    return _WORLD_LAND_GEOM_CACHE


# ═════════════════════════════════════════════════════════════════════════════
# CENSUS COUNTIES SHAPEFILE
# ═════════════════════════════════════════════════════════════════════════════

# All modules share the project-root ``shapefiles/`` directory.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SHARED_SHAPEFILE_DIR = os.path.join(_PROJECT_ROOT, "shapefiles")


class CensusCounties:
    """Manages the US Census county shapefile used across the dashboard.

    Downloads, caches, and provides access to county boundaries for overlaying
    on satellite, radar, MRMS, and alert maps.  Uses a single shared shapefile
    directory at the project root (``shapefiles/``).
    """

    _fips_map = {}
    _records_map = {}
    _feature = None

    SHAPEFILE_URL = (
        "https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_county_500k.zip"
    )
    FILENAME = "cb_2025_us_county_500k"

    @classmethod
    def get_feature(cls):
        """Return a Cartopy ``ShapelyFeature`` of all counties."""
        cls.load()
        return cls._feature

    @classmethod
    def load(cls):
        """Download (if needed) and load the county shapefile."""
        if cls._fips_map:
            return

        cache_dir = _SHARED_SHAPEFILE_DIR
        os.makedirs(cache_dir, exist_ok=True)

        shp_path = os.path.join(cache_dir, f"{cls.FILENAME}.shp")

        if not os.path.exists(shp_path):
            logging.getLogger(__name__).info("⬇️  Downloading High-Res Census Counties (500k)...")
            try:
                r = requests.get(cls.SHAPEFILE_URL)
                r.raise_for_status()
                with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                    z.extractall(cache_dir)
                logging.getLogger(__name__).info("Download complete.")
            except Exception as e:
                logging.getLogger(__name__).warning(f"[WARN] Error downloading Census shapefile: {type(e).__name__}")
                return

        logging.getLogger(__name__).info("Loading Census Geometries...")
        try:
            _configure_pyshp_logging()
            reader = shpreader.Reader(shp_path)

            # Suppress known non-fatal shapefile geometry warnings from upstream data.
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore", message=".*Possible issue encountered.*"
                )
                warnings.filterwarnings(
                    "ignore", message=".*polygon interior holes.*")
                geometries = list(reader.geometries())
                records = list(reader.records())

            cls._feature = ShapelyFeature(geometries, ccrs.PlateCarree())
            for record in records:
                fips = record.attributes.get("GEOID")
                if fips:
                    cls._fips_map[fips] = record.geometry
                    cls._records_map[fips] = record
            logging.getLogger(__name__).info(f"Loaded {len(cls._fips_map)} counties.")
        except Exception as e:
            logging.getLogger(__name__).warning(f"[WARN] Error loading Census shapefile: {type(e).__name__}")
            cls._feature = None

    @classmethod
    def get_geometry_for_fips(cls, fips_list):
        """Return the union geometry for a list of FIPS codes."""
        cls.load()
        geoms = []
        for fips in fips_list:
            if fips in cls._fips_map:
                geoms.append(cls._fips_map[fips])
        if not geoms:
            return None
        return unary_union(geoms)

    @classmethod
    def get_record_for_fips(cls, fips):
        """Return the full shapefile record for a single FIPS code."""
        cls.load()
        return cls._records_map.get(fips)
