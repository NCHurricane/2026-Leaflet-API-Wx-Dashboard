"""Platform descriptors for all supported satellite instruments.

Phase 1: config + frontend abstraction only.
Phase 2 will add provider and renderer implementations per platform.
"""

from __future__ import annotations

# Provider type constants
PROVIDER_AWS_GOES = "aws_goes"
PROVIDER_AWS_GK2A = "aws_gk2a"
PROVIDER_AWS_GMGSI = "aws_gmgsi"
PROVIDER_AWS_HIMAWARI = "aws_himawari"
PROVIDER_EUMETSAT = "eumetsat"

# Platforms with a live data pipeline (Phase 2+)
GOES_PLATFORMS: frozenset[str] = frozenset({"goes18", "goes19"})

SATELLITE_PLATFORMS: dict[str, dict] = {
    "goes19": {
        "label": "GOES-19",
        "short_label": "G19",
        "instrument": "ABI",
        "provider": PROVIDER_AWS_GOES,
        "sectors": ["FULLDISK", "CONUS", "MESO1", "MESO2"],
        "default_sector": "CONUS",
        "lon_0": -75.0,
        "implemented": True,
    },
    "goes18": {
        "label": "GOES-18",
        "short_label": "G18",
        "instrument": "ABI",
        "provider": PROVIDER_AWS_GOES,
        "sectors": ["FULLDISK", "CONUS", "MESO1", "MESO2"],
        "default_sector": "CONUS",
        "lon_0": -137.0,
        "implemented": True,
    },
    "himawari9": {
        "label": "Himawari-9",
        "short_label": "H9",
        "instrument": "AHI",
        "provider": PROVIDER_AWS_HIMAWARI,
        "sectors": ["FULLDISK", "JAPAN", "TARGET"],
        "default_sector": "FULLDISK",
        "lon_0": 140.7,
        "implemented": True,
    },
    "gk2a": {
        "label": "GK2A",
        "short_label": "GK2A",
        "instrument": "AMI",
        "provider": PROVIDER_AWS_GK2A,
        "sectors": ["FULLDISK"],
        "default_sector": "FULLDISK",
        "lon_0": 128.2,
        "implemented": True,
    },
    "gmgsi": {
        "label": "GMGSI Global Mosaic",
        "short_label": "GMGSI",
        "instrument": "Multi-satellite mosaic",
        "provider": PROVIDER_AWS_GMGSI,
        "sectors": ["GLOBAL"],
        "default_sector": "GLOBAL",
        "lon_0": 0.0,
        "implemented": True,
    },
    "meteosat12": {
        "label": "Meteosat-12",
        "short_label": "M12",
        "instrument": "FCI",
        "provider": PROVIDER_EUMETSAT,
        "sectors": ["FULLDISK"],
        "default_sector": "FULLDISK",
        "lon_0": 0.0,
        "implemented": True,
    },
    "meteosat9": {
        "label": "Meteosat-9",
        "short_label": "M9",
        "instrument": "SEVIRI",
        "provider": PROVIDER_EUMETSAT,
        "sectors": ["FULLDISK"],
        "default_sector": "FULLDISK",
        "lon_0": 45.5,
        "implemented": True,
    },
    "meteosat11": {
        "label": "Meteosat-11",
        "short_label": "M11",
        "instrument": "SEVIRI",
        "provider": PROVIDER_EUMETSAT,
        "sectors": ["RSS"],
        "default_sector": "RSS",
        "lon_0": 9.5,
        "implemented": True,
    },
}

ALL_SATELLITE_IDS: frozenset[str] = frozenset(SATELLITE_PLATFORMS)


def platform_descriptor(sat_id: str) -> dict:
    desc = SATELLITE_PLATFORMS.get(str(sat_id or "").strip().lower())
    if desc is None:
        raise ValueError(f"Unknown satellite platform: '{sat_id}'")
    return desc
