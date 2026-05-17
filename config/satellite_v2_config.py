"""Configuration for the clean-sheet Satellite v2 tile workflow."""

from __future__ import annotations

import os
from dataclasses import dataclass

from config.satellite_config import ABI_CHANNELS, RGB_COMPOSITE_KEYS


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
        "description": "Single-worker GOES-19 freshness profile (CONUS + FULLDISK only). MESO is handled by goes19-meso.",
        "products": SATELLITE_V2_WORKER_PRODUCTS,
        "satellites": ("goes19",),
        "sectors": ("CONUS", "FULLDISK"),
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
SATELLITE_V2_WORKER_PREWARM_FRAMES = 36
SATELLITE_V2_WORKER_CURRENT_DEEP_JOBS_PER_RUN = 8
SATELLITE_V2_WORKER_MESO_DEEP_JOBS_PER_RUN = 4
SATELLITE_V2_WORKER_FULLDISK_BASELINE_ZOOMS = (1, 2)
SATELLITE_V2_WORKER_CONUS_BASELINE_ZOOMS = (5, 6)
SATELLITE_V2_WORKER_MESO_BASELINE_ZOOMS = (7, 8)
SATELLITE_V2_WORKER_FULLDISK_PREWARM_ZOOMS = (1, 2, 3)
SATELLITE_V2_WORKER_CONUS_HIGH_RES_PREWARM_ZOOMS = (6, 7, 8)
SATELLITE_V2_WORKER_CONUS_STANDARD_PREWARM_ZOOMS = (5, 6)
SATELLITE_V2_WORKER_MESO_HIGH_RES_PREWARM_ZOOMS = (7, 8, 9)
SATELLITE_V2_WORKER_MESO_STANDARD_PREWARM_ZOOMS = (7, 8)


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
        if product_key in SATELLITE_V2_HIGH_RES_PRODUCTS:
            return SATELLITE_V2_WORKER_MESO_HIGH_RES_PREWARM_ZOOMS
        return SATELLITE_V2_WORKER_MESO_STANDARD_PREWARM_ZOOMS
    if product_key in SATELLITE_V2_HIGH_RES_PRODUCTS:
        return SATELLITE_V2_WORKER_CONUS_HIGH_RES_PREWARM_ZOOMS
    return SATELLITE_V2_WORKER_CONUS_STANDARD_PREWARM_ZOOMS


def max_native_zoom_for_product(sector: str, channel_key: str) -> int:
    return max(worker_zooms_for_product(sector, channel_key))


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
