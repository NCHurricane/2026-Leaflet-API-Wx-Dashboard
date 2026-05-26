"""Configuration for the clean-sheet Satellite v2 tile workflow."""

from __future__ import annotations

import os
from dataclasses import dataclass

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

try:
    from config.satellite_colormaps import (
        WV_UPPER_CMAP,
        WV_UPPER_NORM,
        WV_MID_CMAP,
        WV_MID_NORM,
        WV_LOW_CMAP,
        WV_LOW_NORM,
        WV2_UPPER_CMAP,
        WV2_UPPER_NORM,
        WV2_MID_CMAP,
        WV2_MID_NORM,
        WV2_LOW_CMAP,
        WV2_LOW_NORM,
        WV_TPC_CMAP,
        WV_TPC_NORM,
        IR_CMAP,
        IR_NORM,
        CIRA_IR_CMAP,
        CIRA_IR_NORM,
        IR_TPC_CMAP,
        IR_TPC_NORM,
        IR_TV1_CMAP,
        IR_TV1_NORM,
        IR_BD_CMAP,
        IR_BD_NORM,
        IR_RGBV_CMAP,
        IR_RGBV_NORM,
        IR_DRGB_CMAP,
        IR_DRGB_NORM,
        SW_CMAP,
        SW_NORM,
        SW_DRGB_CMAP,
        SW_DRGB_NORM,
        CIRA_IR_WINTER_CMAP,
        CIRA_IR_WINTER_NORM,
        FIRE_DETECT_CMAP,
        FIRE_DETECT_NORM,
        RAMSDIS_WV_CMAP,
        RAMSDIS_WV_NORM,
        FOGDIFF_BLUE_CMAP,
        FOGDIFF_BLUE_NORM,
    )
except ImportError:
    from .satellite_colormaps import (
        WV_UPPER_CMAP,
        WV_UPPER_NORM,
        WV_MID_CMAP,
        WV_MID_NORM,
        WV_LOW_CMAP,
        WV_LOW_NORM,
        WV2_UPPER_CMAP,
        WV2_UPPER_NORM,
        WV2_MID_CMAP,
        WV2_MID_NORM,
        WV2_LOW_CMAP,
        WV2_LOW_NORM,
        WV_TPC_CMAP,
        WV_TPC_NORM,
        IR_CMAP,
        IR_NORM,
        CIRA_IR_CMAP,
        CIRA_IR_NORM,
        IR_TPC_CMAP,
        IR_TPC_NORM,
        IR_TV1_CMAP,
        IR_TV1_NORM,
        IR_BD_CMAP,
        IR_BD_NORM,
        IR_RGBV_CMAP,
        IR_RGBV_NORM,
        IR_DRGB_CMAP,
        IR_DRGB_NORM,
        SW_CMAP,
        SW_NORM,
        SW_DRGB_CMAP,
        SW_DRGB_NORM,
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
    "Channel07MetPyDRGB": {
        "name": "Shortwave IR (MetPy ir_drgb)",
        "req": ["Channel07"],
        "cmap": SW_DRGB_CMAP,
        "norm": SW_DRGB_NORM,
    },
    "Channel07Fire": {
        "name": "Shortwave IR (Fire Detection)",
        "req": ["Channel07"],
        "cmap": FIRE_DETECT_CMAP,
        "norm": FIRE_DETECT_NORM,
    },
    "Channel08": {
        "name": "Upper-Level WV (Satpy water_vapors1)",
        "cmap": WV_UPPER_CMAP,
        "norm": WV_UPPER_NORM,
    },
    "Channel08MetPyTPC": {
        "name": "Upper-Level WV (MetPy wv_tpc)",
        "req": ["Channel08"],
        "cmap": WV_TPC_CMAP,
        "norm": WV_TPC_NORM,
    },
    "Channel08SatpyWV2": {
        "name": "Upper-Level WV (Satpy water_vapors2)",
        "req": ["Channel08"],
        "cmap": WV2_UPPER_CMAP,
        "norm": WV2_UPPER_NORM,
    },
    "Channel08RAMSDIS": {
        "name": "Upper-Level WV (RAMSDIS)",
        "req": ["Channel08"],
        "cmap": RAMSDIS_WV_CMAP,
        "norm": RAMSDIS_WV_NORM,
    },
    "Channel09": {
        "name": "Mid-Level WV (Satpy water_vapors1)",
        "cmap": WV_MID_CMAP,
        "norm": WV_MID_NORM,
    },
    "Channel09MetPyTPC": {
        "name": "Mid-Level WV (MetPy wv_tpc)",
        "req": ["Channel09"],
        "cmap": WV_TPC_CMAP,
        "norm": WV_TPC_NORM,
    },
    "Channel09SatpyWV2": {
        "name": "Mid-Level WV (Satpy water_vapors2)",
        "req": ["Channel09"],
        "cmap": WV2_MID_CMAP,
        "norm": WV2_MID_NORM,
    },
    "Channel09RAMSDIS": {
        "name": "Mid-Level WV (RAMSDIS)",
        "req": ["Channel09"],
        "cmap": RAMSDIS_WV_CMAP,
        "norm": RAMSDIS_WV_NORM,
    },
    "Channel10": {
        "name": "Low-Level WV (Satpy water_vapors1)",
        "cmap": WV_LOW_CMAP,
        "norm": WV_LOW_NORM,
    },
    "Channel10MetPyTPC": {
        "name": "Low-Level WV (MetPy wv_tpc)",
        "req": ["Channel10"],
        "cmap": WV_TPC_CMAP,
        "norm": WV_TPC_NORM,
    },
    "Channel10SatpyWV2": {
        "name": "Low-Level WV (Satpy water_vapors2)",
        "req": ["Channel10"],
        "cmap": WV2_LOW_CMAP,
        "norm": WV2_LOW_NORM,
    },
    "Channel10RAMSDIS": {
        "name": "Low-Level WV (RAMSDIS)",
        "req": ["Channel10"],
        "cmap": RAMSDIS_WV_CMAP,
        "norm": RAMSDIS_WV_NORM,
    },
    "Channel11": {
        "name": "Cloud-Top Phase (8.4 µm)",
        "cmap": IR_TPC_CMAP,
        "norm": IR_TPC_NORM,
    },
    "Channel15": {
        "name": "Dirty Longwave (12.3 µm)",
        "cmap": IR_TPC_CMAP,
        "norm": IR_TPC_NORM,
    },
    "Channel13": {
        "name": "Clean IR (Enhanced)",
        "cmap": CIRA_IR_CMAP,
        "norm": CIRA_IR_NORM,
    },
    "Channel13Satpy": {
        "name": "Clean IR (Satpy colorized_ir_clouds)",
        "req": ["Channel13"],
        "cmap": IR_CMAP,
        "norm": IR_NORM,
    },
    "Channel13MetPyTPC": {
        "name": "Clean IR (MetPy ir_tpc)",
        "req": ["Channel13"],
        "cmap": IR_TPC_CMAP,
        "norm": IR_TPC_NORM,
    },
    "Channel13MetPyTV1": {
        "name": "Clean IR (MetPy ir_tv1)",
        "req": ["Channel13"],
        "cmap": IR_TV1_CMAP,
        "norm": IR_TV1_NORM,
    },
    "Channel13MetPyBD": {
        "name": "Clean IR (MetPy ir_bd)",
        "req": ["Channel13"],
        "cmap": IR_BD_CMAP,
        "norm": IR_BD_NORM,
    },
    "Channel13MetPyRGBV": {
        "name": "Clean IR (MetPy ir_rgbv)",
        "req": ["Channel13"],
        "cmap": IR_RGBV_CMAP,
        "norm": IR_RGBV_NORM,
    },
    "Channel13MetPyDRGB": {
        "name": "Clean IR (MetPy ir_drgb)",
        "req": ["Channel13"],
        "cmap": IR_DRGB_CMAP,
        "norm": IR_DRGB_NORM,
    },
    "Channel13CIRAWinter": {
        "name": "Clean IR (Winter)",
        "req": ["Channel13"],
        "cmap": CIRA_IR_WINTER_CMAP,
        "norm": CIRA_IR_WINTER_NORM,
    },
    "Channel14": {
        "name": "Longwave IR (MetPy ir_tpc)",
        "cmap": IR_TPC_CMAP,
        "norm": IR_TPC_NORM,
    },
    "Channel14MetPyTV1": {
        "name": "Longwave IR (MetPy ir_tv1)",
        "req": ["Channel14"],
        "cmap": IR_TV1_CMAP,
        "norm": IR_TV1_NORM,
    },
    "Channel14MetPyBD": {
        "name": "Longwave IR (MetPy ir_bd)",
        "req": ["Channel14"],
        "cmap": IR_BD_CMAP,
        "norm": IR_BD_NORM,
    },
    "Channel14CIRA": {
        "name": "Longwave IR (Enhanced)",
        "req": ["Channel14"],
        "cmap": CIRA_IR_CMAP,
        "norm": CIRA_IR_NORM,
    },
    "Channel14CIRAWinter": {
        "name": "Longwave IR (Winter)",
        "req": ["Channel14"],
        "cmap": CIRA_IR_WINTER_CMAP,
        "norm": CIRA_IR_WINTER_NORM,
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
    "DayNightHybrid": {
        "name": "Day/Night Hybrid (Legacy Alias)",
        "req": ["Channel01", "Channel02", "Channel03", "Channel13"],
    },
    "Sandwich": {
        "name": "VIS/IR Sandwich",
        "req": ["Channel02", "Channel13"],
        "cmap": IR_CMAP,
        "norm": IR_NORM,
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
    "WaterVapor": {
        "name": "Simple Water Vapor",
        "req": ["Channel08", "Channel10", "Channel13"],
    },
    "DifferentialWaterVapor": {
        "name": "Differential Water Vapor",
        "req": ["Channel08", "Channel10"],
    },
    "DayConvection": {
        "name": "Day Convection",
        "req": [
            "Channel02",
            "Channel05",
            "Channel07",
            "Channel08",
            "Channel10",
            "Channel13",
        ],
    },
    "DayCloudConvection": {
        "name": "Day Cloud Convection",
        "req": ["Channel02", "Channel13"],
    },
    "DayCloudPhase": {
        "name": "Day Cloud Phase",
        "req": ["Channel02", "Channel05", "Channel13"],
    },
    "DayCloudPhaseEUMETSAT": {
        "name": "Day Cloud Phase (EUMETSAT)",
        "req": ["Channel02", "Channel05", "Channel06"],
    },
    "DayLandCloud": {
        "name": "Day Land Cloud",
        "req": ["Channel02", "Channel03", "Channel05"],
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
    "SplitWindowDifference": {
        "name": "Split Window Difference",
        "req": ["Channel13", "Channel15"],
    },
    "NightFogDifference": {
        "name": "Night Fog Difference",
        "req": ["Channel07", "Channel13"],
    },
    "BlowingSnow": {
        "name": "Blowing Snow",
        "req": ["Channel02", "Channel05", "Channel07", "Channel13"],
    },
    "SeaSpray": {
        "name": "Sea Spray",
        "req": ["Channel02", "Channel03", "Channel07", "Channel13"],
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
    "DayNightHybrid",
    "FireTemperature",
    "AirMass",
    "WaterVapor",
    "DifferentialWaterVapor",
    "DayConvection",
    "DayCloudConvection",
    "DayCloudPhase",
    "DayCloudPhaseEUMETSAT",
    "DayLandCloud",
    "DayLandCloudFire",
    "DaySnowFog",
    "NighttimeMicrophysics",
    "Dust",
    "Ash",
    "SulfurDioxide",
    "SplitWindowDifference",
    "NightFogDifference",
    "BlowingSnow",
    "SeaSpray",
    "RocketPlume",
}


SATELLITE_V2_DASHBOARD_PRODUCTS = (
    "Channel01",
    "Channel02",
    "Channel03",
    "Channel07",
    "Channel07Fire",
    "Channel08RAMSDIS",
    "Channel09RAMSDIS",
    "Channel13",
    "GeoColor",
    "GeoColorBlkMar",
    "TrueColor",
    "NaturalColor",
    "Dust",
    "RocketPlume",
)

SATELLITE_V2_HIGH_RES_PRODUCTS = {
    "Channel01",
    "Channel02",
    "Channel03",
    "Channel13",
    "GeoColor",
    "GeoColorBlkMar",
    "TrueColor",
    "NaturalColor",
    "Dust",
    "RocketPlume",
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
    channel_number = channel_number_from_key(source_channels[0])
    if channel_number <= 6:
        return "reflectance"
    return "brightness_temperature"


def _product_units(kind: str) -> str:
    if kind == "composite":
        return "RGB"
    if kind == "reflectance":
        return "1"
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

SATELLITE_V2_SUPPORTED_SATELLITES = {"goes18", "goes19"}
SATELLITE_V2_SUPPORTED_SECTORS = {"CONUS", "FULLDISK", "MESO1", "MESO2"}

SATELLITE_V2_DEFAULT_SAT_ID = "goes19"
SATELLITE_V2_DEFAULT_SECTOR = "CONUS"
SATELLITE_V2_DEFAULT_CHANNEL = "Channel13"
SATELLITE_V2_DEFAULT_HOURS = 1
SATELLITE_V2_DEFAULT_MAX_FRAMES = 360

SATELLITE_V2_PROVIDER = "aws"
SATELLITE_V2_CACHE_NAMESPACE = "satellite"
SATELLITE_V2_RENDER_VERSION = "products"
SATELLITE_V2_TILE_SIZE = 256
SATELLITE_V2_CATALOG_MAX_AGE_SECONDS = 20 * 60

SATELLITE_V2_CONUS_ZOOMS = tuple(range(2, 9))
SATELLITE_V2_FULLDISK_ZOOMS = tuple(range(1, 7))
SATELLITE_V2_MESO_ZOOMS = tuple(range(4, 9))

SATELLITE_V2_WORKER_SATELLITES = ("goes19", "goes18")
SATELLITE_V2_WORKER_PRODUCTS = ("Channel13", "Channel02", "Channel08RAMSDIS")
SATELLITE_V2_WORKER_LIGHT_COMPOSITE_PRODUCTS = (
    "TrueColor",
    "NaturalColor",
    "Dust",
    "RocketPlume",
)
SATELLITE_V2_WORKER_GEOCOLOR_PRODUCTS = ("GeoColor", "GeoColorBlkMar")
SATELLITE_V2_WORKER_CURRENT_SECTORS = ("CONUS",)
SATELLITE_V2_WORKER_MESO_SECTORS = ("MESO1", "MESO2")
SATELLITE_V2_WORKER_PRIORITY_PRODUCTS = (
    "Channel13",
    "GeoColor",
    "GeoColorBlkMar",
    "TrueColor",
    "NaturalColor",
    "Dust",
    "RocketPlume",
    "Channel02",
    "Channel01",
    "Channel07",
    "Channel07Fire",
    "Channel08RAMSDIS",
    "Channel09RAMSDIS",
)
SATELLITE_V2_PRIMARY_PRODUCTS = (
    "Channel02",
    "Channel09RAMSDIS",
    "Channel13",
    "GeoColor",
    "GeoColorBlkMar",
)
SATELLITE_V2_WORKER_PROFILES = {
    "full": {
        "description": "All configured Satellite v2 worker jobs.",
        "products": SATELLITE_V2_WORKER_PRODUCTS,
        "satellites": SATELLITE_V2_WORKER_SATELLITES,
    },
    "local-primary": {
        "description": "High-use GOES-19/18 CONUS products for local/main PC warming. Full Disk rendered live.",
        "products": ("Channel13", "Channel02", "Channel08RAMSDIS"),
        "satellites": ("goes19", "goes18"),
        "sectors": ("CONUS",),
    },
    "remote-backfill": {
        "description": "Lower-priority products and GOES-18 jobs for helper-machine backfill (disabled when using local-primary only scope).",
        "products": SATELLITE_V2_WORKER_PRODUCTS,
        "satellites": SATELLITE_V2_WORKER_SATELLITES,
        "exclude_jobs": tuple(
            ("goes19", product_key) for product_key in SATELLITE_V2_WORKER_PRODUCTS
        ),
    },
    "goes19-freshness": {
        "description": "Single-worker GOES-19 freshness profile (CONUS only). FULLDISK is on-demand; MESO is handled by goes19-meso.",
        "products": SATELLITE_V2_WORKER_PRODUCTS,
        "satellites": ("goes19",),
        "sectors": ("CONUS",),
        "mode": "rolling-lookback",
        "recency_hours": 1,
        "deadline_minutes": 115,
        "deadline_buffer_seconds": 180,
        "latest_frames_per_job": 1,
        "overlap_lock": True,
    },
    "goes19-meso": {
        "description": "Dedicated GOES-19 MESO1/MESO2 rolling-warm profile. Run as a separate scheduled task.",
        "products": SATELLITE_V2_WORKER_PRODUCTS,
        "satellites": ("goes19",),
        "sectors": ("MESO1", "MESO2"),
        "mode": "rolling-lookback",
        "recency_hours": 1,
        "deadline_minutes": 25,
        "deadline_buffer_seconds": 60,
        "latest_frames_per_job": 1,
        "overlap_lock": True,
    },
    "goes19-light-composites": {
        "description": "Dedicated GOES-19 CONUS light-composite rolling-warm profile.",
        "products": SATELLITE_V2_WORKER_LIGHT_COMPOSITE_PRODUCTS,
        "satellites": ("goes19",),
        "sectors": ("CONUS",),
        "mode": "rolling-lookback",
        "recency_hours": 1,
        "deadline_minutes": 60,
        "deadline_buffer_seconds": 60,
        "latest_frames_per_job": 1,
        "overlap_lock": True,
    },
    "goes19-geocolor": {
        "description": "Dedicated GOES-19 CONUS GEOColor rolling-warm profile.",
        "products": SATELLITE_V2_WORKER_GEOCOLOR_PRODUCTS,
        "satellites": ("goes19",),
        "sectors": ("CONUS",),
        "mode": "rolling-lookback",
        "recency_hours": 1,
        "deadline_minutes": 60,
        "deadline_buffer_seconds": 60,
        "latest_frames_per_job": 1,
        "overlap_lock": True,
    },
}
SATELLITE_V2_WORKER_BASELINE_FRAMES = 2
SATELLITE_V2_WORKER_PREWARM_FRAMES = 18         # CONUS/FULLDISK (~1.5hr at 5-min intervals)
SATELLITE_V2_WORKER_MESO_PREWARM_FRAMES = 72    # MESO (~1.2hr at 1-min intervals)
SATELLITE_V2_WORKER_CURRENT_DEEP_JOBS_PER_RUN = 8
SATELLITE_V2_WORKER_MESO_DEEP_JOBS_PER_RUN = 4
SATELLITE_V2_WORKER_FULLDISK_BASELINE_ZOOMS = (1, 2)
SATELLITE_V2_WORKER_CONUS_BASELINE_ZOOMS = (5, 6)
SATELLITE_V2_WORKER_MESO_BASELINE_ZOOMS = (7, 8)
SATELLITE_V2_WORKER_FULLDISK_PREWARM_ZOOMS = (1, 2, 3)
SATELLITE_V2_WORKER_CONUS_HIGH_RES_PREWARM_ZOOMS = (5, 6)
SATELLITE_V2_WORKER_CONUS_CHANNEL2_PREWARM_ZOOMS = (5, 6)
SATELLITE_V2_WORKER_CONUS_STANDARD_PREWARM_ZOOMS = (5, 6)
SATELLITE_V2_WORKER_MESO_HIGH_RES_PREWARM_ZOOMS = (7, 8)
SATELLITE_V2_WORKER_MESO_CHANNEL2_PREWARM_ZOOMS = (7, 8)
SATELLITE_V2_WORKER_MESO_STANDARD_PREWARM_ZOOMS = (7, 8)

# Max zoom levels the frontend is allowed to request.
# Prewarm covers default + 1 zoom-in; deeper zooms render on-demand.
SATELLITE_V2_MAX_NATIVE_ZOOM_CONUS = 8
SATELLITE_V2_MAX_NATIVE_ZOOM_FULLDISK = 5
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


SATELLITE_V2_WORKER_TILE_RENDER_WORKERS = _env_int(
    "WX_SATELLITE_V2_TILE_WORKERS", 4, 1, 16
)
SATELLITE_V2_WORKER_MESO_TILE_RENDER_WORKERS = _env_int(
    "WX_SATELLITE_V2_MESO_TILE_WORKERS", 4, 1, 16
)

SATELLITE_V2_SECTOR_BOUNDS = {
    "CONUS": {"west": -140.0, "south": 20.0, "east": -55.0, "north": 55.0},
    "FULLDISK": {"west": -180.0, "south": -80.0, "east": 20.0, "north": 80.0},
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
    if value.lower().startswith("channel"):
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            return f"Channel{int(digits):02d}"
    raise ValueError(f"Unsupported satellite source channel '{channel_key}'.")


def worker_zooms_for_product(sector: str, channel_key: str) -> tuple[int, ...]:
    sector_key = normalize_sector(sector)
    product_key = normalize_channel(channel_key)
    if sector_key == "FULLDISK":
        return SATELLITE_V2_WORKER_FULLDISK_PREWARM_ZOOMS
    if sector_key in {"MESO1", "MESO2"}:
        if product_key == "Channel02":
            return SATELLITE_V2_WORKER_MESO_CHANNEL2_PREWARM_ZOOMS
        if product_key in SATELLITE_V2_HIGH_RES_PRODUCTS:
            return SATELLITE_V2_WORKER_MESO_HIGH_RES_PREWARM_ZOOMS
        return SATELLITE_V2_WORKER_MESO_STANDARD_PREWARM_ZOOMS
    if product_key == "Channel02":
        return SATELLITE_V2_WORKER_CONUS_CHANNEL2_PREWARM_ZOOMS
    if product_key in SATELLITE_V2_HIGH_RES_PRODUCTS:
        return SATELLITE_V2_WORKER_CONUS_HIGH_RES_PREWARM_ZOOMS
    return SATELLITE_V2_WORKER_CONUS_STANDARD_PREWARM_ZOOMS


def max_native_zoom_for_product(sector: str, channel_key: str) -> int:
    # Max zoom is decoupled from prewarm — worker pre-renders shallow zooms,
    # on-demand renderer fills deeper zoom requests up to these limits.
    sector_key = normalize_sector(sector)
    if sector_key == "FULLDISK":
        return SATELLITE_V2_MAX_NATIVE_ZOOM_FULLDISK
    if sector_key in {"MESO1", "MESO2"}:
        return SATELLITE_V2_MAX_NATIVE_ZOOM_MESO
    return SATELLITE_V2_MAX_NATIVE_ZOOM_CONUS


def worker_baseline_zooms_for_sector(sector: str) -> tuple[int, ...]:
    sector_key = normalize_sector(sector)
    if sector_key == "FULLDISK":
        return SATELLITE_V2_WORKER_FULLDISK_BASELINE_ZOOMS
    if sector_key in {"MESO1", "MESO2"}:
        return SATELLITE_V2_WORKER_MESO_BASELINE_ZOOMS
    return SATELLITE_V2_WORKER_CONUS_BASELINE_ZOOMS


def satellite_v2_worker_tile_workers(meso: bool, override: int | None = None) -> int:
    if override is not None:
        return max(1, min(16, int(override)))
    return (
        SATELLITE_V2_WORKER_MESO_TILE_RENDER_WORKERS
        if meso
        else SATELLITE_V2_WORKER_TILE_RENDER_WORKERS
    )


def zooms_for_sector(sector: str) -> tuple[int, ...]:
    sector_key = normalize_sector(sector)
    if sector_key == "FULLDISK":
        return SATELLITE_V2_FULLDISK_ZOOMS
    if sector_key in {"MESO1", "MESO2"}:
        return SATELLITE_V2_MESO_ZOOMS
    return SATELLITE_V2_CONUS_ZOOMS


def aws_product_prefix_for_sector(sector: str) -> str:
    sector_key = normalize_sector(sector)
    if sector_key == "FULLDISK":
        return "ABI-L2-CMIPF"
    if sector_key in {"MESO1", "MESO2"}:
        return "ABI-L2-CMIPM"
    return "ABI-L2-CMIPC"


def channel_token(channel_key: str) -> str:
    product = SATELLITE_V2_PRODUCTS[normalize_channel(channel_key)]
    return f"C{product.channel_number:02d}"


def source_channels_for_product(channel_key: str) -> tuple[str, ...]:
    return SATELLITE_V2_PRODUCTS[normalize_channel(channel_key)].source_channels


def source_channel_token(source_channel: str) -> str:
    return f"C{channel_number_from_key(source_channel):02d}"
