"""
Shared geospatial utilities for the Weather Dashboard.

Centralises US state geometry loading, CONUS geometry building, country-level
geometry, and the Census county shapefile class so every module (surface,
satellite, radar, MRMS, alerts, lightning) shares a single cached copy instead
of maintaining independent duplicates.
"""

import os
import io
import zipfile
import warnings
import logging

import requests
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
_US_COUNTRY_GEOM_CACHE = None


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
    """Load and cache US state polygon geometries from Natural Earth.

    Returns:
        dict[str, shapely.geometry.base.BaseGeometry]:
            Mapping of two-letter postal codes (e.g. ``"NC"``) to Shapely
            polygon/multipolygon geometries.
    """
    global _STATE_GEOM_CACHE
    if _STATE_GEOM_CACHE is not None:
        return _STATE_GEOM_CACHE

    shpfile = shpreader.natural_earth(
        resolution="10m", category="cultural", name="admin_1_states_provinces"
    )
    reader = shpreader.Reader(shpfile)
    states = {}
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


def get_us_country_geometry():
    """Load and cache the USA country polygon from Natural Earth.

    Returns:
        shapely.geometry.base.BaseGeometry or None
    """
    global _US_COUNTRY_GEOM_CACHE
    if _US_COUNTRY_GEOM_CACHE is not None:
        return _US_COUNTRY_GEOM_CACHE

    shp_path = shpreader.natural_earth(
        resolution="10m", category="cultural", name="admin_0_countries"
    )
    reader = shpreader.Reader(shp_path)
    for rec in reader.records():
        if rec.attributes.get("NAME") == "United States of America":
            _US_COUNTRY_GEOM_CACHE = rec.geometry
            break

    return _US_COUNTRY_GEOM_CACHE


# ═════════════════════════════════════════════════════════════════════════════
# CENSUS COUNTIES SHAPEFILE
# ═════════════════════════════════════════════════════════════════════════════

# All modules share the project-root ``shapefiles/`` directory.
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
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
    _state_feature_map = {}
    _state_multi_feature_map = {}

    SHAPEFILE_URL = (
        "https://www2.census.gov/geo/tiger/GENZ2021/shp/cb_2021_us_county_5m.zip"
    )
    FILENAME = "cb_2021_us_county_5m"

    @classmethod
    def _state_county_shapefile_path(cls, state_abbr):
        state = str(state_abbr or "").strip().upper()
        if not state:
            return ""
        return os.path.join(
            _SHARED_SHAPEFILE_DIR,
            "counties",
            state,
            f"counties_{state}.shp",
        )

    @classmethod
    def _load_feature_from_shp(cls, shp_path):
        if not shp_path or not os.path.exists(shp_path):
            return None

        try:
            _configure_pyshp_logging()
            reader = shpreader.Reader(shp_path)
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore", message=".*Possible issue encountered.*"
                )
                warnings.filterwarnings(
                    "ignore", message=".*polygon interior holes.*"
                )
                geometries = list(reader.geometries())
            if not geometries:
                return None
            return ShapelyFeature(geometries, ccrs.PlateCarree())
        except Exception as exc:
            print(f"[WARN] Error loading county shapefile {shp_path}: {exc}")
            return None

    @classmethod
    def get_feature(cls):
        """Return a Cartopy ``ShapelyFeature`` of all counties."""
        cls.load()
        return cls._feature

    @classmethod
    def get_feature_for_state(cls, state_abbr):
        """Return county feature for a single state, with national fallback."""
        state = str(state_abbr or "").strip().upper()
        if not state:
            return cls.get_feature()

        cached = cls._state_feature_map.get(state)
        if cached is not None:
            return cached

        state_shp = cls._state_county_shapefile_path(state)
        feature = cls._load_feature_from_shp(state_shp)
        if feature is None:
            feature = cls.get_feature()

        cls._state_feature_map[state] = feature
        return feature

    @classmethod
    def get_feature_for_states(cls, state_abbr_list):
        """Return merged county feature for multiple states, with fallback."""
        if not state_abbr_list:
            return cls.get_feature()

        states = sorted(
            {
                str(state or "").strip().upper()
                for state in state_abbr_list
                if str(state or "").strip()
            }
        )
        if not states:
            return cls.get_feature()

        cache_key = tuple(states)
        cached = cls._state_multi_feature_map.get(cache_key)
        if cached is not None:
            return cached

        geoms = []
        for state in states:
            shp_path = cls._state_county_shapefile_path(state)
            if not shp_path or not os.path.exists(shp_path):
                continue
            try:
                reader = shpreader.Reader(shp_path)
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore", message=".*Possible issue encountered.*"
                    )
                    warnings.filterwarnings(
                        "ignore", message=".*polygon interior holes.*"
                    )
                    geoms.extend(list(reader.geometries()))
            except Exception as exc:
                print(
                    f"[WARN] Error reading state county shapefile {shp_path}: {exc}")

        if geoms:
            feature = ShapelyFeature(geoms, ccrs.PlateCarree())
        else:
            feature = cls.get_feature()

        cls._state_multi_feature_map[cache_key] = feature
        return feature

    @classmethod
    def load(cls):
        """Download (if needed) and load the county shapefile."""
        if cls._fips_map:
            return

        cache_dir = _SHARED_SHAPEFILE_DIR
        os.makedirs(cache_dir, exist_ok=True)

        shp_path = os.path.join(cache_dir, f"{cls.FILENAME}.shp")

        if not os.path.exists(shp_path):
            print("⬇️  Downloading High-Res Census Counties (5m)...")
            try:
                r = requests.get(cls.SHAPEFILE_URL)
                r.raise_for_status()
                with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                    z.extractall(cache_dir)
                print("Download complete.")
            except Exception as e:
                print(f"[WARN] Error downloading Census shapefile: {e}")
                return

        print("Loading Census Geometries...")
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
            print(f"Loaded {len(cls._fips_map)} counties.")
        except Exception as e:
            print(f"[WARN] Error loading Census shapefile: {e}")
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


# ═════════════════════════════════════════════════════════════════════════════
# CENSUS STATES SHAPEFILE (dissolved outlines)
# ═════════════════════════════════════════════════════════════════════════════


class CensusStates:
    """Manages per-state dissolved outline shapefiles generated by
    ``tools/build_state_shapefiles.py``.

    Each file at ``shapefiles/states/{STATE}/state_{STATE}.shp`` contains a
    single polygon representing the outer boundary of that state (counties
    dissolved).  Use :meth:`get_feature` for a national all-states overlay and
    :meth:`get_feature_for_state` for a single-state outline.
    """

    _feature = None
    _state_feature_map = {}

    @classmethod
    def _state_outline_shapefile_path(cls, state_abbr):
        state = str(state_abbr or "").strip().upper()
        if not state:
            return ""
        return os.path.join(
            _SHARED_SHAPEFILE_DIR,
            "states",
            state,
            f"state_{state}.shp",
        )

    @classmethod
    def _load_feature_from_shp(cls, shp_path):
        if not shp_path or not os.path.exists(shp_path):
            return None
        try:
            _configure_pyshp_logging()
            reader = shpreader.Reader(shp_path)
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore", message=".*Possible issue encountered.*"
                )
                warnings.filterwarnings(
                    "ignore", message=".*polygon interior holes.*"
                )
                geometries = list(reader.geometries())
            if not geometries:
                return None
            return ShapelyFeature(geometries, ccrs.PlateCarree())
        except Exception as exc:
            print(
                f"[WARN] Error loading state outline shapefile {shp_path}: {exc}")
            return None

    @classmethod
    def get_feature(cls):
        """Return a Cartopy ``ShapelyFeature`` of all state outlines, or ``None``."""
        if cls._feature is not None:
            return cls._feature

        states_dir = os.path.join(_SHARED_SHAPEFILE_DIR, "states")
        if not os.path.isdir(states_dir):
            return None

        geoms = []
        for state_subdir in sorted(os.listdir(states_dir)):
            shp_path = os.path.join(
                states_dir, state_subdir, f"state_{state_subdir}.shp"
            )
            if not os.path.exists(shp_path):
                continue
            try:
                _configure_pyshp_logging()
                reader = shpreader.Reader(shp_path)
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore", message=".*Possible issue encountered.*"
                    )
                    warnings.filterwarnings(
                        "ignore", message=".*polygon interior holes.*"
                    )
                    geoms.extend(list(reader.geometries()))
            except Exception as exc:
                print(f"[WARN] Skipping state outline {state_subdir}: {exc}")

        if not geoms:
            return None

        cls._feature = ShapelyFeature(geoms, ccrs.PlateCarree())
        return cls._feature

    @classmethod
    def get_feature_for_state(cls, state_abbr):
        """Return a Cartopy ``ShapelyFeature`` for a single state outline, or ``None``."""
        state = str(state_abbr or "").strip().upper()
        if not state:
            return None

        cached = cls._state_feature_map.get(state)
        if cached is not None:
            return cached

        shp_path = cls._state_outline_shapefile_path(state)
        feature = cls._load_feature_from_shp(shp_path)
        if feature is not None:
            cls._state_feature_map[state] = feature
        return feature
