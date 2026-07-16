# NEXRAD Level II and Level III product definitions.

import math

L2_PRODUCTS = {
    "REF": "Reflectivity",
    "VEL": "Velocity",
    "SRV": "Storm-Relative Velocity",
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
    "N0S": "Storm-Relative Velocity",
    "N0X": "Differential Reflectivity",
    "N0C": "Correlation Coefficient",
    "N0K": "Specific Differential Phase",
    "DVL": "Vertically Integrated Liquid",
    "NET": "Echo Tops",
    "DHR": "1-Hour Precipitation",
    "N1P": "1-Hour Precipitation (Legacy Alias)",
    "DPR": "1-Hour Precipitation",
    "DPA": "Digital Precipitation Array",
    "DAA": "One-Hour Accumulation",
    "NTP": "Storm Total Precipitation (Legacy Alias)",
    "NRR": "Storm Total Precipitation",
    "DTA": "Storm Total Accumulation",
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

# Elevation the scheduled worker renders L2 products at. Must match the UI's
# default request so worker output and on-demand renders share one cache key
# (no more parallel ELEV_AUTO / ELEV_0P5 directories rendered twice).
LIVE_RADAR_L2_DEFAULT_ELEVATION = "0.5"

# Authoritative live-radar product catalog. These entries drive the API, UI,
# worker field selection/rendering, legends, units, and cache product keys.
LIVE_RADAR_PRODUCTS = {
    "L2_REF": {
        "level": "Level 2",
        "product": "REF",
        "label": "L2 Reflectivity",
        "field_names": ["reflectivity"],
        "palette": "BR",
        "units": "dBZ",
        "vmin": -30.0,
        "vmax": 90.0,
        "mask": "reflectivity",
        # Hide the lightest returns (below the first opaque color in BR.pal).
        "min_value": 5.0,
        "value_scale": 1.0,
        "cache_variant": "br_min5dbz_v4",
        "figure_size_inches": 22,
        "capabilities": {"elevation_selection": True},
    },
    "L2_VEL": {
        "level": "Level 2",
        "product": "VEL",
        "label": "L2 Velocity",
        "field_names": ["velocity"],
        "palette": "BV",
        "units": "mph",
        # BV.pal is in mph: -64..+64 gradient with a green inbound floor to -150.
        "vmin": -150.0,
        "vmax": 64.0,
        "mask": "velocity",
        "value_scale": 2.2369363,
        "figure_size_inches": 22,
        "capabilities": {"elevation_selection": True},
    },
    "L2_SRV": {
        "level": "Level 2",
        "product": "SRV",
        "source_product": "VEL",
        "label": "L2 Storm-Relative Velocity",
        "field_names": ["velocity"],
        "derived_field": "storm_relative_velocity",
        "palette": "SRV",
        "units": "kt",
        "vmin": -100.0,
        "vmax": 160.0,
        "mask": "velocity",
        "value_scale": 1.94384449,
        # Test default: storm motion vector, explicitly defined as direction
        # the storm is moving toward. Adjust after visual comparison.
        "storm_motion_speed_kt": 25.0,
        "storm_motion_to_degrees": 45.0,
        "cache_variant": "motion_25kt_to045_v1",
        "figure_size_inches": 22,
        "capabilities": {"elevation_selection": True},
    },
    "L2_SW": {
        "level": "Level 2",
        "product": "SW",
        "label": "L2 Spectrum Width",
        "field_names": ["spectrum_width"],
        "palette": "SW",
        "units": "kt",
        "vmin": 0.0,
        "vmax": 35.0,
        "mask": "nonnegative",
        "value_scale": 1.94384449,
        "figure_size_inches": 22,
        "capabilities": {"elevation_selection": True},
    },
    "L2_ZDR": {
        "level": "Level 2",
        "product": "ZDR",
        "label": "L2 Differential Reflectivity",
        "field_names": [
            "differential_reflectivity",
            "corrected_differential_reflectivity",
        ],
        "palette": "ZDR",
        "units": "dB",
        "vmin": -8.0,
        "vmax": 8.0,
        "mask": "finite",
        "value_scale": 1.0,
        "figure_size_inches": 22,
        "capabilities": {"elevation_selection": True},
    },
    "L2_RHO": {
        "level": "Level 2",
        "product": "RHO",
        "label": "L2 Correlation Coefficient",
        "field_names": ["cross_correlation_ratio"],
        "palette": "CC",
        "units": "ratio",
        "vmin": 0.0,
        "vmax": 1.05,
        "mask": "finite",
        "value_scale": 1.0,
        "figure_size_inches": 22,
        "capabilities": {"elevation_selection": True},
    },
    # L2_KDP removed: NEXRAD Level 2 contains differential_phase (PHIDP) but not
    # specific_differential_phase (KDP). KDP must be derived from PHIDP (~8s per
    # volume via Py-ART), which is too costly for the live worker. Use L3_N0K
    # (NWS-computed KDP) instead.
    "L2_PHI": {
        "level": "Level 2",
        "product": "PHI",
        "label": "L2 Differential Phase",
        "field_names": [
            "differential_phase",
            "corrected_differential_phase",
            "unfolded_differential_phase",
        ],
        "palette": "PHI",
        "units": "deg",
        "vmin": 0.0,
        "vmax": 360.0,
        "mask": "finite",
        "value_scale": 1.0,
        "figure_size_inches": 22,
        "capabilities": {"elevation_selection": True},
    },
    "L3_N0B": {
        "level": "Level 3",
        "product": "N0B",
        "label": "L3 Reflectivity",
        "field_names": ["reflectivity"],
        "palette": "BR",
        "units": "dBZ",
        "vmin": -30.0,
        "vmax": 90.0,
        "mask": "reflectivity",
        # Hide the lightest returns (below the first opaque color in BR.pal).
        "min_value": 5.0,
        "value_scale": 1.0,
        "cache_variant": "br_min5dbz_v4",
        "figure_size_inches": 22,
        "capabilities": {"elevation_selection": False},
    },
    "L3_N0G": {
        "level": "Level 3",
        "product": "N0G",
        "label": "L3 Velocity",
        "field_names": ["velocity"],
        "palette": "BV",
        "units": "mph",
        # BV.pal is in mph: -64..+64 gradient with a green inbound floor to -150.
        "vmin": -150.0,
        "vmax": 64.0,
        "mask": "velocity",
        "value_scale": 2.2369363,
        "figure_size_inches": 22,
        "capabilities": {"elevation_selection": False},
    },
    "L3_N0S": {
        "level": "Level 3",
        "product": "N0S",
        "label": "L3 Storm-Relative Velocity",
        "field_names": ["velocity"],
        "palette": "SRV",
        "units": "kt",
        "vmin": -100.0,
        "vmax": 160.0,
        "mask": "velocity",
        # Legacy Level III product 56 thresholds are already decoded in knots,
        # despite Py-ART exposing the generic velocity metadata as m/s.
        "value_scale": 1.0,
        "cache_variant": "srv_knots_v2",
        "capabilities": {"elevation_selection": False},
    },
    "L3_N0X": {
        "level": "Level 3",
        "product": "N0X",
        "label": "L3 Differential Reflectivity",
        "field_names": ["differential_reflectivity"],
        "palette": "ZDR",
        "units": "dB",
        "vmin": -8.0,
        "vmax": 8.0,
        "mask": "finite",
        "value_scale": 1.0,
        "capabilities": {"elevation_selection": False},
    },
    "L3_N0C": {
        "level": "Level 3",
        "product": "N0C",
        "label": "L3 Correlation Coefficient",
        "field_names": ["cross_correlation_ratio"],
        "palette": "CC",
        "units": "ratio",
        "vmin": 0.0,
        "vmax": 1.05,
        "mask": "finite",
        "value_scale": 1.0,
        "capabilities": {"elevation_selection": False},
    },
    "L3_N0K": {
        "level": "Level 3",
        "product": "N0K",
        "label": "L3 Specific Differential Phase",
        "field_names": ["specific_differential_phase"],
        "palette": "KDP",
        "units": "deg/km",
        "vmin": -2.0,
        "vmax": 10.0,
        "mask": "finite",
        "value_scale": 1.0,
        "capabilities": {"elevation_selection": False},
    },
    "L3_N0H": {
        "level": "Level 3",
        "product": "N0H",
        "label": "L3 Hydrometeor Classification",
        "field_names": ["radar_echo_classification"],
        "palette": "HCA",
        "units": "category",
        "vmin": 0.0,
        "vmax": 150.0,
        "mask": "nonnegative",
        "value_scale": 1.0,
        "capabilities": {"elevation_selection": False},
    },
    "L3_DPR": {
        "level": "Level 3",
        "product": "DPR",
        "label": "L3 Digital Precipitation Rate",
        "field_names": ["radar_estimated_rain_rate"],
        "palette": "DPA",
        "units": "in/hr",
        "vmin": 0.0,
        "vmax": 8.0,
        "mask": "nonnegative",
        "value_scale": 1.0,
        "capabilities": {"elevation_selection": False},
    },
    "L3_DAA": {
        "level": "Level 3",
        "product": "DAA",
        "label": "L3 One-Hour Accumulation",
        "field_names": ["radar_estimated_rain_rate"],
        "palette": "DAA",
        "units": "in",
        "vmin": 0.0,
        "vmax": 4.0,
        "mask": "nonnegative",
        "value_scale": 1.0,
        "capabilities": {"elevation_selection": False},
    },
    "L3_DTA": {
        "level": "Level 3",
        "product": "DTA",
        "label": "L3 Storm Total Accumulation",
        "field_names": ["radar_estimated_rain_rate"],
        "palette": "STP",
        "units": "in",
        "vmin": 0.0,
        "vmax": 18.0,
        "mask": "nonnegative",
        "value_scale": 1.0,
        "capabilities": {"elevation_selection": False},
    },
    "L3_EET": {
        "level": "Level 3",
        "product": "EET",
        "label": "L3 Echo Tops",
        "field_names": ["reflectivity"],
        "palette": "ET",
        "units": "kft",
        "vmin": 0.0,
        "vmax": 70.0,
        "mask": "nonnegative",
        "value_scale": 1.0,
        "capabilities": {"elevation_selection": False},
    },
    "L3_DVL": {
        "level": "Level 3",
        "product": "DVL",
        "label": "L3 Vertically Integrated Liquid",
        "field_names": ["reflectivity"],
        "palette": "VIL",
        "units": "kg/m²",
        "vmin": 0.0,
        "vmax": 80.0,
        "mask": "nonnegative",
        "value_scale": 1.0,
        "capabilities": {"elevation_selection": False},
    },
}

# Worker cadence and retention.
LIVE_RADAR_LOOKBACK_HOURS = 1
LIVE_RADAR_WORKER_INTERVAL_MIN = 5
# Use the unidata-nexrad-level2-chunks S3 bucket for L2 products.
# Enables sub-minute latency by assembling scans incrementally as chunks arrive,
# but the flat unidata-nexrad-level2 bucket posts a completed scan at the exact
# same instant the chunk stream for it finishes -- so the only real benefit is
# up to one volume-interval (~5-6 min) of early visibility into the *current*
# in-progress scan. Not worth the added discovery/latency complexity for now.
LIVE_RADAR_L2_USE_CHUNKS = False
LIVE_RADAR_TILE_WORKER_INTERVAL_MIN = 5
LIVE_RADAR_KEEP_FRAMES = 45
LIVE_RADAR_MIN_LOOKBACK_HOURS = 0.5
LIVE_RADAR_MAX_LOOKBACK_HOURS = 12.0
# Allow for the fastest common NEXRAD volume cadence plus a small boundary
# buffer when translating a requested wall-clock window into a file count.
LIVE_RADAR_SCANS_PER_HOUR = 15
LIVE_RADAR_LOOKBACK_FRAME_BUFFER = 3
LIVE_RADAR_BACKFILL_BATCH_FRAMES = 12


def normalize_live_radar_lookback_hours(value, default=LIVE_RADAR_LOOKBACK_HOURS) -> float:
    """Clamp live-radar lookback requests to the supported slider range."""
    try:
        hours = float(value)
    except (TypeError, ValueError):
        hours = float(default)
    return max(
        LIVE_RADAR_MIN_LOOKBACK_HOURS,
        min(hours, LIVE_RADAR_MAX_LOOKBACK_HOURS),
    )


def live_radar_target_frames(lookback_hours) -> int:
    """Return a bounded scan-count target for one requested lookback window."""
    hours = normalize_live_radar_lookback_hours(lookback_hours)
    target = math.ceil(hours * LIVE_RADAR_SCANS_PER_HOUR)
    target += LIVE_RADAR_LOOKBACK_FRAME_BUFFER
    maximum = math.ceil(
        LIVE_RADAR_MAX_LOOKBACK_HOURS * LIVE_RADAR_SCANS_PER_HOUR
    ) + LIVE_RADAR_LOOKBACK_FRAME_BUFFER
    return max(1, min(target, maximum))


LIVE_RADAR_MAX_KEEP_FRAMES = max(
    LIVE_RADAR_KEEP_FRAMES,
    live_radar_target_frames(LIVE_RADAR_MAX_LOOKBACK_HOURS),
)

# Rendering performance settings (easily tunable without code changes)
# Figure size in inches. At DPI=200: 12 → 2400×2400px (native L3 Super-Res 0.25km grid)
# 12 inches matches the data's native resolution at 250nm (460km) coverage; larger
# values only oversample the source grid and slow rendering ~quadratically.
LIVE_RADAR_FIGURE_SIZE_INCHES = 12
# DPI for rendering. 200 DPI achieves native 0.25km grid resolution for Level 3 Super-Res.
LIVE_RADAR_RENDER_DPI = 200
# Number of parallel worker processes for rendering frames. 0=auto (CPU count), 1=sequential
LIVE_RADAR_PARALLEL_WORKERS = 0
