"""Configuration for the clean-sheet Satellite v2 tile workflow."""

from __future__ import annotations

import os
from dataclasses import dataclass

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

try:
    from config.satellite_colormaps import (
        CIRA_IR_CMAP,
        CIRA_IR_NORM,
        IR_TPC_CMAP,
        IR_TPC_NORM,
        SW_CMAP,
        SW_NORM,
        FIRE_DETECT_CMAP,
        FIRE_DETECT_NORM,
        RAMSDIS_WV_CMAP,
        RAMSDIS_WV_NORM,
    )
except ImportError:
    from .satellite_colormaps import (
        CIRA_IR_CMAP,
        CIRA_IR_NORM,
        IR_TPC_CMAP,
        IR_TPC_NORM,
        SW_CMAP,
        SW_NORM,
        FIRE_DETECT_CMAP,
        FIRE_DETECT_NORM,
        RAMSDIS_WV_CMAP,
        RAMSDIS_WV_NORM,
    )  # type: ignore

# GOES ABI channel configuration (consolidated from satellite_config.py)
ABI_CHANNELS = {
    "Channel01": {
        "name": "Blue Visible (0.47 µm)",
        "cmap": plt.cm.Greys_r,
        "norm": mcolors.Normalize(vmin=0, vmax=1.0),
    },
    "Channel02": {
        "name": "Red Visible (0.64 µm)",
        "cmap": plt.cm.Greys_r,
        "norm": mcolors.Normalize(vmin=0, vmax=1.0),
    },
    # GOES ABI L2 aerosol products. These are not imagery channels: ADP is a
    # categorical smoke/dust detection mask and AOD is a continuous optical
    # depth field. Their "source channel" is a pseudo token (ADP / AOD), so
    # they carry no ABI channel number.
    "AerosolDetection": {
        "name": "Smoke & Dust (ADP)",
        "req": ["ADP"],
        "cmap": None,
        "norm": None,
    },
    "AerosolOpticalDepth": {
        "name": "Aerosol Optical Depth (550 nm)",
        "req": ["AOD"],
        "cmap": plt.get_cmap("turbo"),
        "norm": mcolors.Normalize(vmin=0.0, vmax=1.0, clip=True),
    },
    # GOES ABI L2 Fire/Hot-Spot Characterization (FDC). Fire Radiative Power
    # is a sparse field — only actual fire pixels carry a value — so it renders
    # as hot points over a transparent background via the scalar colorizer.
    "FireRadiativePower": {
        "name": "Fire Radiative Power (MW)",
        "req": ["FRP"],
        "cmap": plt.get_cmap("YlOrRd"),
        "norm": mcolors.Normalize(vmin=0.0, vmax=150.0, clip=True),
    },
    "Channel03": {
        "name": "Veggie (Near-IR)",
        "cmap": plt.cm.Greys_r,
        "norm": mcolors.Normalize(vmin=0, vmax=1.0),
    },
    "Channel05": {
        "name": "Snow/Ice (1.6 µm)",
        "cmap": plt.cm.Greys_r,
        "norm": mcolors.Normalize(vmin=0, vmax=1.0),
    },
    "Channel06": {
        "name": "Cloud Particle Size (2.2 µm)",
        "cmap": plt.cm.Greys_r,
        "norm": mcolors.Normalize(vmin=0, vmax=1.0),
    },
    "Channel07": {
        "name": "Shortwave IR (MetPy ir_bd)",
        "cmap": SW_CMAP,
        "norm": SW_NORM,
    },
    "Channel07Fire": {
        "name": "Shortwave IR (Fire Detection)",
        "req": ["Channel07"],
        "cmap": FIRE_DETECT_CMAP,
        "norm": FIRE_DETECT_NORM,
    },
    "Channel08RAMSDIS": {
        "name": "Upper-Level WV (RAMSDIS)",
        "req": ["Channel08"],
        "cmap": RAMSDIS_WV_CMAP,
        "norm": RAMSDIS_WV_NORM,
    },
    "Channel09RAMSDIS": {
        "name": "Mid-Level WV (RAMSDIS)",
        "req": ["Channel09"],
        "cmap": RAMSDIS_WV_CMAP,
        "norm": RAMSDIS_WV_NORM,
    },
    "Channel13": {
        "name": "Clean IR (Enhanced)",
        "cmap": CIRA_IR_CMAP,
        "norm": CIRA_IR_NORM,
    },
    "Channel14": {
        "name": "Longwave IR (MetPy ir_tpc)",
        "cmap": IR_TPC_CMAP,
        "norm": IR_TPC_NORM,
    },
    "TrueColor": {
        "name": "Natural Color / True Color",
        "req": ["Channel01", "Channel02", "Channel03"],
    },
    "NaturalColor": {
        "name": "Natural Color",
        "req": ["Channel01", "Channel02", "Channel03"],
    },
    "GeoColor": {
        "name": "GEOColor (Day/Night Blend)",
        "req": ["Channel01", "Channel02", "Channel03", "Channel07", "Channel13"],
    },
    "GeoColorBlkMar": {
        "name": "GEOColor (Black Marble)",
        "req": ["Channel01", "Channel02", "Channel03", "Channel07", "Channel13"],
    },
    # ── goes2go RGB Recipes ──────────────────────────────────────────
    "FireTemperature": {
        "name": "Fire Temperature",
        "req": ["Channel05", "Channel06", "Channel07"],
    },
    "AirMass": {
        "name": "Air Mass",
        "req": ["Channel08", "Channel10", "Channel13"],
    },
    "DayCloudPhase": {
        "name": "Day Cloud Phase",
        "req": ["Channel02", "Channel05", "Channel13"],
    },
    "DayLandCloudFire": {
        "name": "Day Land Cloud Fire",
        "req": ["Channel02", "Channel03", "Channel06"],
    },
    "DaySnowFog": {
        "name": "Day Snow/Fog",
        "req": ["Channel03", "Channel05", "Channel07", "Channel13"],
    },
    "NighttimeMicrophysics": {
        "name": "Nighttime Microphysics",
        "req": ["Channel07", "Channel13", "Channel15"],
    },
    "Dust": {
        "name": "Dust",
        "req": ["Channel11", "Channel13", "Channel14", "Channel15"],
    },
    "Ash": {
        "name": "Ash",
        "req": ["Channel11", "Channel13", "Channel14", "Channel15"],
    },
    "SulfurDioxide": {
        "name": "Sulfur Dioxide",
        "req": ["Channel07", "Channel09", "Channel10", "Channel11", "Channel13"],
    },
    "RocketPlume": {
        "name": "Rocket Plume",
        "req": ["Channel02", "Channel05", "Channel06", "Channel07", "Channel08"],
    },
}

# Keys that produce direct RGB/RGBA arrays (no cmap/norm needed for display)
RGB_COMPOSITE_KEYS = {
    "TrueColor",
    "NaturalColor",
    "GeoColor",
    "GeoColorBlkMar",
    "FireTemperature",
    "AirMass",
    "DayCloudPhase",
    "DayLandCloudFire",
    "DaySnowFog",
    "NighttimeMicrophysics",
    "Dust",
    "Ash",
    "SulfurDioxide",
    "RocketPlume",
}


SATELLITE_V2_DASHBOARD_PRODUCTS = (
    "Channel01",
    "Channel02",
    "Channel03",
    "Channel05",
    "Channel06",
    "Channel07",
    "Channel07Fire",
    "Channel08RAMSDIS",
    "Channel09RAMSDIS",
    "Channel13",
    "Channel14",
    "AerosolDetection",
    "AerosolOpticalDepth",
    "FireRadiativePower",
    "FireTemperature",
    "AirMass",
    "GeoColor",
    "GeoColorBlkMar",
    "TrueColor",
    "NaturalColor",
    "DayCloudPhase",
    "DayLandCloudFire",
    "DaySnowFog",
    "NighttimeMicrophysics",
    "Dust",
    "Ash",
    "SulfurDioxide",
    "RocketPlume",
)

SATELLITE_V2_INTERPRETIVE_LEGENDS = {
    "FireTemperature": {
        "subtitle": "Renderer-matched RGB interpretation",
        "items": (
            {"color": "#ff3a1f", "label": "Active fire / hot spot"},
            {"color": "#a94f78", "label": "Warm land / desert background"},
            {"color": "#51345f", "label": "Cooler land or shadowed surface"},
            {"color": "#0f7eb3", "label": "Cold cloud tops"},
        ),
    },
    "AirMass": {
        "subtitle": "Renderer-matched RGB interpretation",
        "items": (
            {"color": "#c04c5c", "label": "Strong upper-level dry-air signal"},
            {"color": "#7d4ca8", "label": "Cold/dry upper-level air"},
            {"color": "#49a36b", "label": "Moist low/mid-level air mass"},
            {"color": "#d8e7f2", "label": "Cold high cloud tops"},
        ),
    },
    "DayCloudPhase": {
        "subtitle": "Renderer-matched daytime RGB interpretation",
        "items": (
            {"color": "#efe45a", "label": "Thick cold cloud tops"},
            {"color": "#df8a5a", "label": "High cloud edge / mixed phase"},
            {"color": "#4ad088", "label": "Low liquid cloud field"},
            {"color": "#6bb2d8", "label": "Ice/snow-band response"},
            {"color": "#061d38", "label": "Clear water or dark surface"},
        ),
    },
    "DayLandCloudFire": {
        "subtitle": "Renderer-matched daytime RGB interpretation",
        "items": (
            {"color": "#3d9c56", "label": "Vegetation-dominant surface"},
            {"color": "#b69476", "label": "Bare or dry ground"},
            {"color": "#ff3524", "label": "Strong 2.2 µm hot-spot signal"},
            {"color": "#1d3048", "label": "Water or very dark surface"},
            {"color": "#f5f5f5", "label": "Clouds"},
        ),
    },
    "DaySnowFog": {
        "subtitle": "Renderer-matched daytime RGB interpretation",
        "items": (
            {"color": "#d8c992", "label": "Snow / ice surface"},
            {"color": "#e8e5d8", "label": "Low cloud or fog"},
            {"color": "#b8c8ef", "label": "Cold cloud"},
            {"color": "#5a8b66", "label": "Vegetated land"},
            {"color": "#7b4e43", "label": "Bare or dry land"},
        ),
    },
    "NighttimeMicrophysics": {
        "subtitle": "Renderer-matched nighttime RGB interpretation",
        "items": (
            {"color": "#0717d6", "label": "Clear or warm low cloud"},
            {"color": "#b1009b", "label": "Higher cold cloud"},
            {"color": "#740010", "label": "Warm/thin cloud edge"},
            {"color": "#2a006f", "label": "Mixed cloud or transition zone"},
        ),
    },
    "Dust": {
        "subtitle": "Renderer-matched RGB interpretation",
        "items": (
            {"color": "#df65b0", "label": "Dust / split-window signal"},
            {"color": "#b8834a", "label": "Dry elevated dust or warm surface"},
            {"color": "#7a5fb0", "label": "Dust mixed with cloud"},
            {"color": "#5f90b5", "label": "Cloud or moist background"},
            {"color": "#2d3142", "label": "Clear or dark background"},
        ),
    },
    "Ash": {
        "subtitle": "Renderer-matched RGB interpretation",
        "items": (
            {"color": "#d75fb7", "label": "Split-window ash signal"},
            {"color": "#7857a4", "label": "Ash mixed with cold cloud"},
            {"color": "#d2935a", "label": "Dry slot / warmer split-window signal"},
            {"color": "#b8b8c5", "label": "Meteorological cloud"},
        ),
    },
    "SulfurDioxide": {
        "subtitle": "Renderer-matched RGB interpretation",
        "items": (
            {"color": "#dacb49", "label": "Stronger SO2-sensitive signal"},
            {"color": "#c05aa0", "label": "SO2 mixed with ash/cloud"},
            {"color": "#4aa4c7", "label": "Moist cloud or plume"},
            {"color": "#614682", "label": "Weak/mixed channel signal"},
            {"color": "#30384c", "label": "Background / clear air"},
        ),
    },
    "AerosolDetection": {
        "subtitle": "GOES ABI Aerosol Detection — opacity indicates confidence",
        "items": (
            {"color": "#39d0d8", "label": "Smoke detected"},
            {"color": "#e8a33d", "label": "Dust detected"},
            {"color": "#c44dff", "label": "Smoke + dust detected"},
        ),
    },
}

@dataclass(frozen=True)
class SatelliteV2Product:
    channel_key: str
    label: str
    kind: str
    units: str
    source_channels: tuple[str, ...]

    @property
    def channel_number(self) -> int:
        return channel_number_from_key(self.source_channels[0])


def channel_number_from_key(channel_key: str) -> int:
    digits = "".join(ch for ch in str(channel_key or "") if ch.isdigit())
    if not digits:
        raise ValueError(
            f"Could not determine ABI channel number from '{channel_key}'."
        )
    return int(digits)


def _product_kind(product_key: str, source_channels: tuple[str, ...]) -> str:
    if product_key in RGB_COMPOSITE_KEYS:
        return "composite"
    source = source_channels[0]
    if source == "ADP":
        return "categorical"
    if source == "AOD":
        return "aod"
    if source == "FRP":
        return "frp"
    channel_number = channel_number_from_key(source_channels[0])
    if channel_number <= 6:
        return "reflectance"
    return "brightness_temperature"


def _product_units(kind: str) -> str:
    if kind == "composite":
        return "RGB"
    if kind == "reflectance":
        return "1"
    if kind == "categorical":
        return "flag"
    if kind == "aod":
        return "1"
    if kind == "frp":
        return "MW"
    return "K"


def _build_product_registry() -> dict[str, SatelliteV2Product]:
    products: dict[str, SatelliteV2Product] = {}
    for product_key in SATELLITE_V2_DASHBOARD_PRODUCTS:
        metadata = ABI_CHANNELS[product_key]
        raw_sources = metadata.get("req", [product_key])
        source_channels = tuple(str(channel) for channel in raw_sources)
        kind = _product_kind(product_key, source_channels)
        products[product_key] = SatelliteV2Product(
            channel_key=product_key,
            label=str(metadata.get("name") or product_key),
            kind=kind,
            units=_product_units(kind),
            source_channels=source_channels,
        )
    return products


SATELLITE_V2_PRODUCTS: dict[str, SatelliteV2Product] = _build_product_registry()

SATELLITE_V2_SUPPORTED_SATELLITES = {
    "gk2a",
    "gmgsi",
    "goes18",
    "goes19",
    "himawari9",
    "meteosat9",
    "meteosat11",
    "meteosat12",
}

# AHI band equivalent for each ABI source channel (Himawari-9). Product keys
# stay ABI-named everywhere; the mapping applies only when a provider builds
# AHI filenames. AHI B03 (0.64 µm, 0.5 km) is the red-visible analog of ABI
# Channel02; AHI B04 (0.86 µm) matches ABI Channel03 (veggie).
AHI_BAND_FOR_ABI_CHANNEL = {
    "Channel01": 1,
    "Channel02": 3,
    "Channel03": 4,
    "Channel05": 5,
    "Channel06": 6,
    "Channel07": 7,
    "Channel08": 8,
    "Channel09": 9,
    "Channel10": 10,
    "Channel11": 11,
    "Channel13": 13,
    "Channel14": 14,
    "Channel15": 15,
}


def ahi_band_for_source_channel(source_channel: str) -> int:
    channel = normalize_source_channel(source_channel)
    band = AHI_BAND_FOR_ABI_CHANNEL.get(channel)
    if band is None:
        raise ValueError(f"No Himawari AHI band mapping for '{source_channel}'.")
    return band


# AMI channel names for the proven GK2A direct products. Product keys remain
# ABI-named so the existing renderer, legend, and cache contracts stay stable.
AMI_CHANNEL_FOR_ABI_CHANNEL = {
    "Channel01": "vi004",
    "Channel02": "vi006",
    "Channel03": "vi008",
    "Channel05": "nr016",
    "Channel07": "sw038",
    "Channel08": "wv063",
    "Channel09": "wv069",
    "Channel13": "ir105",
    "Channel14": "ir112",
}


def ami_channel_for_source_channel(source_channel: str) -> str:
    channel = normalize_source_channel(source_channel)
    ami_name = AMI_CHANNEL_FOR_ABI_CHANNEL.get(channel)
    if ami_name is None:
        raise ValueError(f"No GK2A AMI channel mapping for '{source_channel}'.")
    return ami_name


def ami_supported_products() -> tuple[str, ...]:
    supported = []
    for product_key in SATELLITE_V2_DASHBOARD_PRODUCTS:
        sources = SATELLITE_V2_PRODUCTS[product_key].source_channels
        if all(ch in AMI_CHANNEL_FOR_ABI_CHANNEL for ch in sources):
            supported.append(product_key)
    return tuple(supported)


# SEVIRI channel name for each ABI source channel (Meteosat SEVIRI).
# SEVIRI has no blue (C01) or 2.2 µm (C06) band, so products requiring them
# are unavailable on Meteosat platforms. C09/C10 both map to WV_073 and
# C13/C14 both map to IR_108 — with those, the goes2go Dust/Ash recipes
# reduce exactly to the canonical EUMETSAT split-window RGBs.
SEVIRI_CHANNEL_FOR_ABI_CHANNEL = {
    "Channel02": "VIS006",
    "Channel03": "VIS008",
    "Channel05": "IR_016",
    "Channel07": "IR_039",
    "Channel08": "WV_062",
    "Channel09": "WV_073",
    "Channel10": "WV_073",
    "Channel11": "IR_087",
    "Channel13": "IR_108",
    "Channel14": "IR_108",
    "Channel15": "IR_120",
}


def seviri_channel_for_source_channel(source_channel: str) -> str:
    channel = normalize_source_channel(source_channel)
    seviri_name = SEVIRI_CHANNEL_FOR_ABI_CHANNEL.get(channel)
    if seviri_name is None:
        raise ValueError(f"No SEVIRI channel mapping for '{source_channel}'.")
    return seviri_name


def seviri_supported_products() -> tuple[str, ...]:
    """Dashboard products whose source channels all exist on SEVIRI."""
    supported = []
    for product_key in SATELLITE_V2_DASHBOARD_PRODUCTS:
        sources = SATELLITE_V2_PRODUCTS[product_key].source_channels
        if all(ch in SEVIRI_CHANNEL_FOR_ABI_CHANNEL for ch in sources):
            supported.append(product_key)
    return tuple(supported)


# FCI source-channel mapping for direct IR/WV/VIS products. Composite UI exposure
# stays separate until each recipe has a proof render against live MTG chunks.
# C13/C14 both map to ir_105 and C15 maps to ir_123 (FCI has no 11.2 µm band)
# so the goes2go split-window recipes (Night Microphysics, Dust, Ash) reduce
# exactly to the canonical EUMETSAT MTG RGBs — the same aliasing SEVIRI uses.
FCI_CHANNEL_FOR_ABI_CHANNEL = {
    "Channel01": "vis_04",
    "Channel02": "vis_06",
    "Channel03": "vis_08",
    "Channel05": "nir_16",
    "Channel06": "nir_22",
    "Channel07": "ir_38",
    "Channel08": "wv_63",
    "Channel09": "wv_73",
    "Channel10": "ir_97",
    "Channel11": "ir_87",
    "Channel13": "ir_105",
    "Channel14": "ir_105",
    "Channel15": "ir_123",
}


def fci_channel_for_source_channel(source_channel: str) -> str:
    channel = normalize_source_channel(source_channel)
    fci_name = FCI_CHANNEL_FOR_ABI_CHANNEL.get(channel)
    if fci_name is None:
        raise ValueError(f"No FCI channel mapping for '{source_channel}'.")
    return fci_name


def fci_supported_products() -> tuple[str, ...]:
    supported = []
    for product_key in SATELLITE_V2_DASHBOARD_PRODUCTS:
        sources = SATELLITE_V2_PRODUCTS[product_key].source_channels
        if all(ch in FCI_CHANNEL_FOR_ABI_CHANNEL for ch in sources):
            supported.append(product_key)
    return tuple(supported)

SATELLITE_V2_SUPPORTED_SECTORS = {
    "CONUS", "FULLDISK", "GLOBAL", "MESO1", "MESO2", "RSS", "JAPAN", "TARGET",
}

SATELLITE_V2_DEFAULT_SAT_ID = "goes19"
SATELLITE_V2_DEFAULT_SECTOR = "CONUS"
SATELLITE_V2_DEFAULT_CHANNEL = "Channel13"
SATELLITE_V2_DEFAULT_HOURS = 1
SATELLITE_V2_DEFAULT_MAX_FRAMES = 360

SATELLITE_V2_PROVIDER = "aws"
SATELLITE_V2_CACHE_NAMESPACE = "satellite"
# These versions retain the filled-image opacity and white-point invalidations;
# the GOES/default namespace also includes the low-sun Rayleigh taper and ABI
# daytime midtone lift.
SATELLITE_V2_RENDER_VERSION = "products-v8"
SATELLITE_V2_RENDER_VERSION_GK2A = "products-ami2"
SATELLITE_V2_RENDER_VERSION_GMGSI = "products-gmgsi1"
SATELLITE_V2_RENDER_VERSION_HIMAWARI = "products-ahi4"
# fci4 also retains the Meteosat-12 east-west mirror invalidation from fci1.
SATELLITE_V2_RENDER_VERSION_METEOSAT12 = "products-fci4"
SATELLITE_V2_TILE_SIZE = 256
SATELLITE_V2_CATALOG_MAX_AGE_SECONDS = 20 * 60

SATELLITE_V2_CONUS_ZOOMS = tuple(range(2, 9))
SATELLITE_V2_FULLDISK_ZOOMS = tuple(range(1, 7))
SATELLITE_V2_MESO_ZOOMS = tuple(range(4, 9))


def satellite_v2_render_version_for_satellite(sat_id: str | None) -> str:
    sat_key = str(sat_id or "").strip().lower()
    if sat_key == "gk2a":
        return SATELLITE_V2_RENDER_VERSION_GK2A
    if sat_key == "gmgsi":
        return SATELLITE_V2_RENDER_VERSION_GMGSI
    if sat_key == "himawari9":
        return SATELLITE_V2_RENDER_VERSION_HIMAWARI
    if sat_key == "meteosat12":
        return SATELLITE_V2_RENDER_VERSION_METEOSAT12
    return SATELLITE_V2_RENDER_VERSION

# Max zoom levels the frontend is allowed to request.
# These are request ceilings. Live rendering, supertiles, and any narrow
# rapid-sector warming decide what is actually generated ahead of time.
SATELLITE_V2_MAX_NATIVE_ZOOM_CONUS = 10
SATELLITE_V2_MAX_NATIVE_ZOOM_FULLDISK = 10
SATELLITE_V2_MAX_NATIVE_ZOOM_MESO = 10


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


SATELLITE_V2_ON_DEMAND_CATALOG_HOURS = 12
SATELLITE_V2_ON_DEMAND_CATALOG_MAX_FRAMES = 360
SATELLITE_V2_LEGEND_ANCHOR_COUNT = 65
SATELLITE_V2_LEGEND_TICK_COUNT = 7

# Narrow rapid-scan warmer policy.  This is intentionally separate from the
# legacy broad prewarm worker settings above: Full Disk and CONUS remain live
# rendered/cache-assisted by default, while high-cadence sectors get a small
# cache-first animation tail.
SATELLITE_V2_RAPID_WORKER_PRODUCTS = ("Channel02", "Channel13")
SATELLITE_V2_RAPID_WORKER_JOBS = (
    ("goes19", "MESO1"),
    ("goes19", "MESO2"),
    ("goes18", "MESO1"),
    ("goes18", "MESO2"),
    ("himawari9", "JAPAN"),
    ("meteosat11", "RSS"),
)
SATELLITE_V2_RAPID_WORKER_FRAMES = _env_int(
    "WX_SATELLITE_V2_RAPID_WORKER_FRAMES", 12, 1, 120
)
SATELLITE_V2_RAPID_WORKER_HOURS = _env_int(
    "WX_SATELLITE_V2_RAPID_WORKER_HOURS", 2, 1, 6
)
SATELLITE_V2_RAPID_WORKER_MAX_FRAMES = _env_int(
    "WX_SATELLITE_V2_RAPID_WORKER_MAX_FRAMES", 120, 1, 360
)
SATELLITE_V2_RAPID_WORKER_TILE_WORKERS = _env_int(
    "WX_SATELLITE_V2_RAPID_TILE_WORKERS", 2, 1, 8
)
SATELLITE_V2_RAPID_WORKER_TILE_BUFFER = _env_int(
    "WX_SATELLITE_V2_RAPID_TILE_BUFFER", 1, 0, 3
)
SATELLITE_V2_RAPID_WORKER_FRESH_WINDOW_SECONDS = _env_int(
    "WX_SATELLITE_V2_RAPID_FRESH_WINDOW_SECONDS", 225, 0, 3600
)
SATELLITE_V2_RAPID_WORKER_ZOOMS = {
    "MESO1": (5, 6),
    "MESO2": (5, 6),
    "JAPAN": (6, 7),
    "RSS": (6, 7),
}
SATELLITE_V2_RAPID_WORKER_BOUNDS = {
    "JAPAN": {"west": 115.0, "south": 20.0, "east": 155.0, "north": 50.0},
    "RSS": {"west": -30.0, "south": 10.0, "east": 45.0, "north": 70.0},
}

# Meteosat source-prefetch worker (download-only, no tile rendering).
# EUMETSAT frames are all-channel bundles (one SEVIRI .nat / one FCI chunk set
# per frame), so prefetching any product key warms every channel. Each run
# downloads the newest FRAMES missing frames plus up to BACKFILL of the oldest
# missing frames inside HOURS, so animation depth fills in across runs.
SATELLITE_V2_METEOSAT_PREFETCH_JOBS = (
    ("meteosat12", "FULLDISK"),
    ("meteosat9", "FULLDISK"),
)
SATELLITE_V2_METEOSAT_PREFETCH_CHANNEL = "Channel13"
SATELLITE_V2_METEOSAT_PREFETCH_FRAMES = _env_int(
    "WX_SATELLITE_V2_METEOSAT_PREFETCH_FRAMES", 2, 1, 12
)
SATELLITE_V2_METEOSAT_PREFETCH_BACKFILL = _env_int(
    "WX_SATELLITE_V2_METEOSAT_PREFETCH_BACKFILL", 1, 0, 6
)
SATELLITE_V2_METEOSAT_PREFETCH_HOURS = _env_int(
    "WX_SATELLITE_V2_METEOSAT_PREFETCH_HOURS", 6, 1, 24
)
SATELLITE_V2_METEOSAT_PREFETCH_MAX_FRAMES = _env_int(
    "WX_SATELLITE_V2_METEOSAT_PREFETCH_MAX_FRAMES", 48, 1, 200
)
# Source frames older than this are pruned from the source cache. Slightly
# larger than HOURS so a frame is never pruned while still inside the window.
SATELLITE_V2_METEOSAT_PREFETCH_KEEP_HOURS = _env_int(
    "WX_SATELLITE_V2_METEOSAT_PREFETCH_KEEP_HOURS", 7, 1, 48
)
SATELLITE_V2_METEOSAT_PREFETCH_FRESH_WINDOW_SECONDS = _env_int(
    "WX_SATELLITE_V2_METEOSAT_PREFETCH_FRESH_WINDOW_SECONDS", 450, 0, 3600
)

SATELLITE_V2_LIVE_TILE_RENDER_WORKERS = _env_int(
    "WX_SATELLITE_V2_LIVE_TILE_WORKERS", 10, 1, 32
)
SATELLITE_V2_LIVE_SUPERTILE_RADIUS = _env_int(
    "WX_SATELLITE_V2_LIVE_SUPERTILE_RADIUS", 1, 0, 3
)
SATELLITE_V2_NETCDF_CACHE_SIZE = _env_int(
    "WX_SATELLITE_V2_NETCDF_CACHE_SIZE", 16, 1, 64
)
SATELLITE_V2_RENDERER_CACHE_SIZE = _env_int(
    "WX_SATELLITE_V2_RENDERER_CACHE_SIZE", 8, 0, 64
)
SATELLITE_V2_SOURCE_RASTER_CACHE_MB = _env_int(
    "WX_SATELLITE_V2_SOURCE_RASTER_CACHE_MB", 4096, 0, 131072
)

# Full-disk source grids are capped before reprojection to keep high-resolution
# channels usable on live tile requests. Raise provider caps independently.
SATELLITE_V2_GOES_FULLDISK_MAX_GRID = _env_int(
    "WX_SATELLITE_V2_GOES_FULLDISK_MAX_GRID", 10848, 1024, 21696
)
SATELLITE_V2_AHI_MAX_GRID = _env_int(
    "WX_SATELLITE_V2_AHI_MAX_GRID", 10848, 1024, 21696
)
SATELLITE_V2_AMI_MAX_GRID = _env_int(
    "WX_SATELLITE_V2_AMI_MAX_GRID", 10848, 1024, 22000
)
SATELLITE_V2_FCI_MAX_GRID = _env_int(
    "WX_SATELLITE_V2_FCI_MAX_GRID", 10848, 1024, 22272
)

SATELLITE_V2_SECTOR_BOUNDS = {
    "CONUS": {"west": -140.0, "south": 20.0, "east": -55.0, "north": 55.0},
    "FULLDISK": {"west": -180.0, "south": -80.0, "east": 20.0, "north": 80.0},
    "GLOBAL": {"west": -180.0, "south": -72.75, "east": 180.0, "north": 72.75},
    "MESO1": {"west": -115.0, "south": 25.0, "east": -75.0, "north": 50.0},
    "MESO2": {"west": -105.0, "south": 20.0, "east": -65.0, "north": 45.0},
}


def normalize_sat_id(sat_id: str | None) -> str:
    value = str(sat_id or SATELLITE_V2_DEFAULT_SAT_ID).strip().lower()
    if value not in SATELLITE_V2_SUPPORTED_SATELLITES:
        raise ValueError(
            f"Unsupported satellite '{sat_id}'. Use one of: "
            f"{', '.join(sorted(SATELLITE_V2_SUPPORTED_SATELLITES))}."
        )
    return value


def normalize_sector(sector: str | None) -> str:
    value = str(sector or SATELLITE_V2_DEFAULT_SECTOR).strip().upper()
    if value in {"FD", "FULL_DISK", "FULL-DISK"}:
        value = "FULLDISK"
    if value not in SATELLITE_V2_SUPPORTED_SECTORS:
        raise ValueError(
            f"Unsupported sector '{sector}'. Use one of: "
            f"{', '.join(sorted(SATELLITE_V2_SUPPORTED_SECTORS))}."
        )
    return value


def normalize_channel(channel_key: str | None) -> str:
    value = str(channel_key or SATELLITE_V2_DEFAULT_CHANNEL).strip()
    if value in SATELLITE_V2_PRODUCTS:
        return value
    if value.lower().startswith("channel") and value[7:].isdigit():
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            value = f"Channel{int(digits):02d}"
    if value not in SATELLITE_V2_PRODUCTS:
        raise ValueError(
            f"Unsupported satellite channel '{channel_key}'. Use one of: "
            f"{', '.join(sorted(SATELLITE_V2_PRODUCTS))}."
        )
    return value


def normalize_source_channel(channel_key: str | None) -> str:
    value = str(channel_key or "").strip()
    if value.upper() == "SEVIRI":
        # Shared pseudo-channel: one SEVIRI .nat bundles all channels, so
        # the source cache stores it once under this directory.
        return "SEVIRI"
    if value.upper() == "FCI":
        # Shared pseudo-channel: one FCI frame is a set of NetCDF body chunks
        # containing all channels.
        return "FCI"
    if value.upper() == "ADP":
        # Pseudo-channel: one ABI-L2-ADP file holds all detection flags
        # (Smoke, Dust, ...). Stored once under this source directory.
        return "ADP"
    if value.upper() == "AOD":
        # Pseudo-channel: one ABI-L2-AOD file holds the optical-depth field.
        return "AOD"
    if value.upper() == "FRP":
        # Pseudo-channel: one ABI-L2-FDC file holds the fire characterization
        # variables; FRP extracts the Fire Radiative Power field.
        return "FRP"
    if value.lower().startswith("channel"):
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            return f"Channel{int(digits):02d}"
    raise ValueError(f"Unsupported satellite source channel '{channel_key}'.")


def max_native_zoom_for_product(sector: str, channel_key: str) -> int:
    # Frontend/request ceiling; live rendering and narrow rapid warming decide
    # what is generated ahead of time.
    sector_key = normalize_sector(sector)
    if sector_key in {"FULLDISK", "GLOBAL"}:
        return SATELLITE_V2_MAX_NATIVE_ZOOM_FULLDISK
    if sector_key in {"MESO1", "MESO2"}:
        return SATELLITE_V2_MAX_NATIVE_ZOOM_MESO
    return SATELLITE_V2_MAX_NATIVE_ZOOM_CONUS


def zooms_for_sector(sector: str) -> tuple[int, ...]:
    sector_key = normalize_sector(sector)
    if sector_key in {"FULLDISK", "GLOBAL"}:
        return tuple(
            range(
                min(SATELLITE_V2_FULLDISK_ZOOMS),
                SATELLITE_V2_MAX_NATIVE_ZOOM_FULLDISK + 1,
            )
        )
    if sector_key in {"MESO1", "MESO2"}:
        return tuple(
            range(
                min(SATELLITE_V2_MESO_ZOOMS),
                SATELLITE_V2_MAX_NATIVE_ZOOM_MESO + 1,
            )
        )
    return tuple(
        range(
            min(SATELLITE_V2_CONUS_ZOOMS),
            SATELLITE_V2_MAX_NATIVE_ZOOM_CONUS + 1,
        )
    )


def aws_product_prefix_for_sector(sector: str) -> str:
    sector_key = normalize_sector(sector)
    if sector_key == "FULLDISK":
        return "ABI-L2-CMIPF"
    if sector_key in {"MESO1", "MESO2"}:
        return "ABI-L2-CMIPM"
    return "ABI-L2-CMIPC"


def source_channels_for_product(channel_key: str) -> tuple[str, ...]:
    return SATELLITE_V2_PRODUCTS[normalize_channel(channel_key)].source_channels


def source_channel_token(source_channel: str) -> str:
    return f"C{channel_number_from_key(source_channel):02d}"
