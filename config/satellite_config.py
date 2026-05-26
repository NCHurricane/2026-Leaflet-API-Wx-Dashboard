# GOES ABI channel configuration.

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

# Satellite products supported by the Leaflet tab migration (phase 1).
SATELLITE_LEAFLET_PHASE1_PRODUCTS = (
    "Channel01",
    "Channel02",
    "Channel08",
    "Channel13",
    "GeoColor",
    "TrueColor",
    "NaturalColor",
)

# Default live Satellite tab selection.
SATELLITE_LIVE_DEFAULTS = {
    "region": "CONUS",
    "sat_id": "goes19",
    "sector": "CONUS",
    "product": "Channel13",
    "lookback_hours": 1,
}

# User-editable lookback options for Satellite animate mode.
SATELLITE_ANIMATE_LOOKBACK_HOURS = (1, 3, 6, 12)

# NOTE: SATELLITE_PREWARM_* constants were removed along with the legacy
# satellite_worker / satellite_meso_worker. The satellite_v2 pipeline owns
# tile prewarming via its own profile system (see SATELLITE_V2_WORKER_PROFILES
# in config/satellite_v2_config.py).
