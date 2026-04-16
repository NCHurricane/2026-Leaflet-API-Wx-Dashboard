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
