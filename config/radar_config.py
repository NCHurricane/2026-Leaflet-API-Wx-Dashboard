# NEXRAD Level II and Level III product definitions.

L2_PRODUCTS = {
    "REF": "Reflectivity",
    "VEL": "Velocity",
    "SW": "Spectrum Width",
    "ZDR": "Differential Reflectivity",
    "RHO": "Correlation Coefficient",
    "KDP": "Specific Differential Phase",
    "PHI": "Differential Phase",
}

L3_PRODUCTS = {
    "N0B": "Super-Res Base Reflectivity",
    "N0G": "Super-Res Base Velocity",
    "NVW": "Super-Res Base Velocity (Legacy Alias)",
    "N0S": "Storm-Relative Velocity (Legacy Formatting)",
    "N0C": "Reflectivity (Recombined Legacy)",
    "N0M": "Correlation Coefficient",
    "N0X": "Hybrid Reflectivity Variant",
    "NBU": "Differential Reflectivity (ZDR)",
    "DVL": "Vertically Integrated Liquid",
    "NET": "Echo Tops",
    "DHR": "1-Hour Precipitation",
    "N1P": "1-Hour Precipitation (Legacy Alias)",
    "DPR": "1-Hour Precipitation",
    "DPA": "Digital Precipitation Array",
    "DAA": "Digital Precipitation Array",
    "NTP": "Storm Total Precipitation (Legacy Alias)",
    "NRR": "Storm Total Precipitation",
    "DTA": "Storm Total Precipitation",
    "N0H": "Hydrometeor Classification",
    "HHC": "Hybrid Hydrometeor Classification",
    # Pre-Build 19 legacy codes (for archive data before ~2020)
    "N0Q": "Base Reflectivity",
    "N1Q": "Base Reflectivity (1.5°)",
    "N2Q": "Base Reflectivity (2.4°)",
    "N3Q": "Base Reflectivity (3.1°)",
    "N0U": "Base Velocity",
    "N1U": "Base Velocity (1.5°)",
}


# Live radar tab cache config (weather.html inline tab)
LIVE_RADAR_SITES = [
    "KMHX",
    "KLTX",
    "KAKQ",
    "KRAX",
    "KFCX",
    "KMRX",
    "KGSP",
]

# Keys are UI/backend-facing product IDs for the weather.html Radar tab.
LIVE_RADAR_PRODUCTS = {
    "L2_REF": {
        "level": "Level 2",
        "product": "REF",
        "label": "L2 Reflectivity",
    },
    "L2_VEL": {
        "level": "Level 2",
        "product": "VEL",
        "label": "L2 Velocity",
    },
    "L3_N0B": {
        "level": "Level 3",
        "product": "N0B",
        "label": "L3 Reflectivity",
    },
    "L3_N0G": {
        "level": "Level 3",
        "product": "N0G",
        "label": "L3 Velocity",
    },
}

# Worker cadence and retention.
LIVE_RADAR_LOOKBACK_HOURS = 3
LIVE_RADAR_WORKER_INTERVAL_MIN = 5
LIVE_RADAR_TILE_WORKER_INTERVAL_MIN = 5
LIVE_RADAR_KEEP_FRAMES = 45
