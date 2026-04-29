"""
MRMS Product Configuration
Multi-Radar Multi-Sensor (MRMS) product definitions, colormaps, and metadata.

MRMS Data Source: s3://noaa-mrms-pds
Format: GRIB2
Update Frequency: Every 2 minutes
Resolution: ~1km

Product families with sub-product dropdowns are defined in MRMS_SUB_PRODUCTS.
The frontend uses that dict to build conditional sub-dropdowns.
The composed product key (e.g. "RotationTrack_LL_60min") maps into MRMS_PRODUCTS.
"""

import numpy as np
import matplotlib.colors as mcolors


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS for building product entries
# ═════════════════════════════════════════════════════════════════════════════


def _rotation_entry(level_label, level_tag, s3_infix, time_label, time_tag):
    """Build a Rotation Track product entry."""
    return {
        "full_name": f"Rotation Track – {level_label} {time_label}",
        "short_name": f"Rot {level_tag} {time_tag}",
        "s3_prefix": f"CONUS/{s3_infix}{time_tag}_00.50",
        "units": "0.001/s",
        "colormap": "rotation",
        "levels": np.arange(0, 11, 1),
        "description": f"Rotation Track {level_label} ({time_label})",
        "vmin": 0,
        "vmax": 10,
        "missing_value": 0,
        "no_coverage": 0,
    }


def _mesh_entry(time_label, time_tag, s3_name):
    """Build a MESH product entry."""
    return {
        "full_name": f"MESH – {time_label}",
        "short_name": f"MESH {time_tag}",
        "s3_prefix": f"CONUS/{s3_name}_00.50",
        "units": "mm",
        "colormap": "mesh",
        "levels": np.array([0, 1, 2, 4, 6, 8, 10, 15, 20, 30, 40, 50, 75, 100]),
        "description": f"Maximum Estimated Size of Hail ({time_label})",
        "vmin": 0,
        "vmax": 100,
        "missing_value": -1,
        "no_coverage": -3,
    }


_QPE_LEVELS = {
    "15M": (np.array([0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32]), 0, 40),
    "01H": (np.array([0.25, 0.5, 1, 2, 5, 10, 15, 25, 50, 75, 100, 150]), 0, 150),
    "03H": (np.array([1, 2, 5, 10, 15, 25, 50, 75, 100, 150, 200, 250]), 0, 250),
    "06H": (np.array([1, 5, 10, 15, 25, 50, 75, 100, 150, 200, 250, 300]), 0, 300),
    "12H": (np.array([2, 5, 10, 25, 50, 75, 100, 150, 200, 250, 300, 400]), 0, 400),
    "24H": (np.array([5, 10, 25, 50, 75, 100, 150, 200, 250, 300, 400, 500]), 0, 500),
    "48H": (np.array([10, 25, 50, 75, 100, 150, 200, 300, 400, 500, 600, 750]), 0, 750),
    "72H": (
        np.array([10, 25, 50, 100, 150, 200, 300, 400, 500, 750, 1000, 1250]),
        0,
        1250,
    ),
    "Since12Z": (np.array([0.25, 0.5, 1, 2, 5, 10, 25, 50, 75, 100, 150, 200]), 0, 200),
}


def _qpe_entry(source_label, source_tag, period_tag, s3_prefix):
    """Build a QPE product entry."""
    levels, vmin, vmax = _QPE_LEVELS.get(period_tag, _QPE_LEVELS["01H"])
    period_display = period_tag.replace("H", "-Hour").replace("M", "-Min")
    if period_tag == "Since12Z":
        period_display = "Since 12Z"
    return {
        "full_name": f"{period_display} QPE ({source_label})",
        "short_name": f"QPE {period_tag}",
        "s3_prefix": s3_prefix,
        "units": "mm",
        "colormap": "qpe",
        "levels": levels,
        "description": f"{source_label} precipitation accumulation {period_display}",
        "vmin": vmin,
        "vmax": vmax,
        "missing_value": -1,
        "no_coverage": -3,
    }


# ═════════════════════════════════════════════════════════════════════════════
# MRMS PRODUCT DEFINITIONS
# ═════════════════════════════════════════════════════════════════════════════

_ROT_TIMES = [
    ("30 min", "30min"),
    ("60 min", "60min"),
    ("2 hr", "120min"),
    ("4 hr", "240min"),
    ("6 hr", "360min"),
    ("24 hr", "1440min"),
]

MRMS_PRODUCTS = {
    # ── Precipitation Rate/Type ─────────────────────────────────────────────
    "PrecipRate": {
        "full_name": "Precipitation Rate",
        "short_name": "PrecipRate",
        "s3_prefix": "CONUS/PrecipRate_00.00",
        "units": "mm/hr",
        "colormap": "precip_rate",
        "levels": np.array([0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64]),
        "description": "Radar Precipitation Rate",
        "vmin": 0,
        "vmax": 64,
        "missing_value": -1,
        "no_coverage": -3,
    },
    "PrecipFlag": {
        "full_name": "Surface Precipitation Type",
        "short_name": "PrecipFlag",
        "s3_prefix": "CONUS/PrecipFlag_00.00",
        "units": "flag",
        "colormap": "precip_type",
        "levels": [1, 3, 6, 7, 10, 91, 96],
        "description": "Surface Precipitation Type",
        "categorical": True,
        "missing_value": -1,
        "no_coverage": -3,
        "categories": {
            1: "Warm Rain",
            3: "Snow",
            6: "Convective",
            7: "Rain/Hail",
            10: "Cold Rain",
            91: "Trop Rain",
            96: "Trop Conv",
        },
    },
    # ── Rotation Tracks — Low Level (0-2 km AGL) ───────────────────────────
    **{
        f"RotationTrack_LL_{tag}": _rotation_entry(
            "Low Level", "LL", "RotationTrack", lbl, tag
        )
        for lbl, tag in _ROT_TIMES
    },
    # ── Rotation Tracks — Mid Level (3-6 km AGL) ───────────────────────────
    **{
        f"RotationTrack_ML_{tag}": _rotation_entry(
            "Mid Level", "ML", "RotationTrackML", lbl, tag
        )
        for lbl, tag in _ROT_TIMES
    },
    # ── MESH (Maximum Estimated Size of Hail) ──────────────────────────────
    "MESH_Instant": _mesh_entry("Instant", "Inst", "MESH"),
    "MESH_Max_30min": _mesh_entry("Max 30 min", "30m", "MESH_Max_30min"),
    "MESH_Max_60min": _mesh_entry("Max 60 min", "60m", "MESH_Max_60min"),
    "MESH_Max_120min": _mesh_entry("Max 2 hr", "2h", "MESH_Max_120min"),
    "MESH_Max_240min": _mesh_entry("Max 4 hr", "4h", "MESH_Max_240min"),
    "MESH_Max_360min": _mesh_entry("Max 6 hr", "6h", "MESH_Max_360min"),
    "MESH_Max_1440min": _mesh_entry("Max 24 hr", "24h", "MESH_Max_1440min"),
    # ── Azimuthal Shear ─────────────────────────────────────────────────────
    "AzShear_Low": {
        "full_name": "Azimuthal Shear – Low Level (0-2 km)",
        "short_name": "AzShear Low",
        "s3_prefix": "CONUS/MergedAzShear_0-2kmAGL_00.50",
        "units": "s⁻¹",
        "colormap": "azshear",
        "levels": np.array(
            [
                0.0,
                0.003,
                0.004,
                0.005,
                0.006,
                0.007,
                0.008,
                0.009,
                0.010,
                0.011,
                0.012,
                0.013,
                0.014,
                0.015,
                0.020,
            ]
        ),
        "description": "Azimuthal Shear 0-2 km AGL",
        "vmin": 0,
        "vmax": 0.02,
        "missing_value": 0,
        "no_coverage": 0,
    },
    "AzShear_Mid": {
        "full_name": "Azimuthal Shear – Mid Level (3-6 km)",
        "short_name": "AzShear Mid",
        "s3_prefix": "CONUS/MergedAzShear_3-6kmAGL_00.50",
        "units": "s⁻¹",
        "colormap": "azshear",
        "levels": np.array(
            [
                0.0,
                0.003,
                0.004,
                0.005,
                0.006,
                0.007,
                0.008,
                0.009,
                0.010,
                0.011,
                0.012,
                0.013,
                0.014,
                0.015,
                0.020,
            ]
        ),
        "description": "Azimuthal Shear 3-6 km AGL",
        "vmin": 0,
        "vmax": 0.02,
        "missing_value": 0,
        "no_coverage": 0,
    },
    # ── Hail Probability ────────────────────────────────────────────────────
    "SHI": {
        "full_name": "Severe Hail Index",
        "short_name": "SHI",
        "s3_prefix": "CONUS/SHI_00.50",
        "units": "Index",
        "colormap": "shi",
        "levels": np.array(
            [0, 5, 10, 20, 30, 40, 50, 60, 80, 100, 150, 250, 500, 1500]
        ),
        "description": "Severe Hail Index",
        "vmin": 0,
        "vmax": 1500,
        "missing_value": -1,
        "no_coverage": -3,
    },
    "POSH": {
        "full_name": "Probability of Severe Hail",
        "short_name": "POSH",
        "s3_prefix": "CONUS/POSH_00.50",
        "units": "%",
        "colormap": "probability",
        "levels": np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100]),
        "description": "Probability of Severe Hail",
        "vmin": 0,
        "vmax": 100,
        "missing_value": -1,
        "no_coverage": -3,
    },
    # ── Echo Top ────────────────────────────────────────────────────────────
    "EchoTop_18": {
        "full_name": "Echo Top – 18 dBZ",
        "short_name": "ET 18",
        "s3_prefix": "CONUS/EchoTop_18_00.50",
        "units": "km",
        "colormap": "echotop",
        "levels": np.arange(0, 21, 1),
        "description": "Echo Top Height at 18 dBZ threshold",
        "vmin": 0,
        "vmax": 20,
        "missing_value": -1,
        "no_coverage": -3,
    },
    "EchoTop_30": {
        "full_name": "Echo Top – 30 dBZ",
        "short_name": "ET 30",
        "s3_prefix": "CONUS/EchoTop_30_00.50",
        "units": "km",
        "colormap": "echotop",
        "levels": np.arange(0, 21, 1),
        "description": "Echo Top Height at 30 dBZ threshold",
        "vmin": 0,
        "vmax": 20,
        "missing_value": -1,
        "no_coverage": -3,
    },
    "EchoTop_50": {
        "full_name": "Echo Top – 50 dBZ",
        "short_name": "ET 50",
        "s3_prefix": "CONUS/EchoTop_50_00.50",
        "units": "km",
        "colormap": "echotop",
        "levels": np.arange(0, 21, 1),
        "description": "Echo Top Height at 50 dBZ threshold",
        "vmin": 0,
        "vmax": 20,
        "missing_value": -1,
        "no_coverage": -3,
    },
    "EchoTop_60": {
        "full_name": "Echo Top – 60 dBZ",
        "short_name": "ET 60",
        "s3_prefix": "CONUS/EchoTop_60_00.50",
        "units": "km",
        "colormap": "echotop",
        "levels": np.arange(0, 21, 1),
        "description": "Echo Top Height at 60 dBZ threshold",
        "vmin": 0,
        "vmax": 20,
        "missing_value": -1,
        "no_coverage": -3,
    },
    # ── VIL (Vertically Integrated Liquid) ──────────────────────────────────
    "VIL_Instant": {
        "full_name": "VIL – Instant",
        "short_name": "VIL",
        "s3_prefix": "CONUS/VIL_00.50",
        "units": "kg/m²",
        "colormap": "vil",
        "levels": np.array(
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 18, 25, 30, 40, 50, 60, 70]
        ),
        "description": "Vertically Integrated Liquid (instantaneous)",
        "vmin": 0,
        "vmax": 70,
        "missing_value": -1,
        "no_coverage": -3,
    },
    "VIL_Density": {
        "full_name": "VIL Density",
        "short_name": "VIL Den",
        "s3_prefix": "CONUS/VIL_Density_00.50",
        "units": "g/m³",
        "colormap": "vil",
        "levels": np.array([0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4]),
        "description": "VIL Density",
        "vmin": 0,
        "vmax": 4,
        "missing_value": -1,
        "no_coverage": -3,
    },
    "VIL_Max_120min": {
        "full_name": "VIL – Max 2 hr",
        "short_name": "VIL 2h",
        "s3_prefix": "CONUS/VIL_Max_120min_00.50",
        "units": "kg/m²",
        "colormap": "vil",
        "levels": np.array(
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 18, 25, 30, 40, 50, 60, 70]
        ),
        "description": "VIL Maximum Track (2 hour)",
        "vmin": 0,
        "vmax": 70,
        "missing_value": -1,
        "no_coverage": -3,
    },
    "VIL_Max_1440min": {
        "full_name": "VIL – Max 24 hr",
        "short_name": "VIL 24h",
        "s3_prefix": "CONUS/VIL_Max_1440min_00.50",
        "units": "kg/m²",
        "colormap": "vil",
        "levels": np.array(
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 18, 25, 30, 40, 50, 60, 70]
        ),
        "description": "VIL Maximum Track (24 hour)",
        "vmin": 0,
        "vmax": 70,
        "missing_value": -1,
        "no_coverage": -3,
    },
    # ── Reflectivity variants ───────────────────────────────────────────────
    "Refl_HSR": {
        "full_name": "Hybrid Scan Reflectivity",
        "short_name": "HSR",
        "s3_prefix": "CONUS/SeamlessHSR_00.00",
        "units": "dBZ",
        "colormap": "reflectivity",
        "levels": np.arange(5, 76, 5),
        "description": "Seamless Hybrid Scan Reflectivity with VPR correction",
        "vmin": 0,
        "vmax": 75,
        "missing_value": -99,
        "no_coverage": -999,
    },
    "Refl_BaseQC": {
        "full_name": "Base Reflectivity (QC)",
        "short_name": "BaseQC",
        "s3_prefix": "CONUS/MergedBaseReflectivityQC_00.50",
        "units": "dBZ",
        "colormap": "reflectivity",
        "levels": np.arange(5, 76, 5),
        "description": "Merged Base Reflectivity (Quality Controlled)",
        "vmin": 0,
        "vmax": 75,
        "missing_value": -99,
        "no_coverage": -999,
    },
    "Refl_CompLow": {
        "full_name": "Composite Reflectivity – Low",
        "short_name": "Comp Low",
        "s3_prefix": "CONUS/LayerCompositeReflectivity_Low_00.50",
        "units": "dBZ",
        "colormap": "reflectivity",
        "levels": np.arange(5, 76, 5),
        "description": "Layer Composite Reflectivity - Low Level",
        "vmin": 0,
        "vmax": 75,
        "missing_value": -99,
        "no_coverage": -999,
    },
    "Refl_CompHigh": {
        "full_name": "Composite Reflectivity – High",
        "short_name": "Comp High",
        "s3_prefix": "CONUS/LayerCompositeReflectivity_High_00.50",
        "units": "dBZ",
        "colormap": "reflectivity",
        "levels": np.arange(5, 76, 5),
        "description": "Layer Composite Reflectivity - High Level",
        "vmin": 0,
        "vmax": 75,
        "missing_value": -99,
        "no_coverage": -999,
    },
    "Refl_CompSuper": {
        "full_name": "Composite Reflectivity – Super",
        "short_name": "Comp Super",
        "s3_prefix": "CONUS/LayerCompositeReflectivity_Super_00.50",
        "units": "dBZ",
        "colormap": "reflectivity",
        "levels": np.arange(5, 76, 5),
        "description": "Layer Composite Reflectivity - Super (Full Column)",
        "vmin": 0,
        "vmax": 75,
        "missing_value": -99,
        "no_coverage": -999,
    },
    "Refl_BREF_1HR_MAX": {
        "full_name": "Base Reflectivity – 1 hr Max",
        "short_name": "BREF Max",
        "s3_prefix": "CONUS/BREF_1HR_MAX_00.50",
        "units": "dBZ",
        "colormap": "reflectivity",
        "levels": np.arange(5, 76, 5),
        "description": "Base Reflectivity 1-Hour Maximum",
        "vmin": 0,
        "vmax": 75,
        "missing_value": -99,
        "no_coverage": -999,
    },
    "Refl_CREF_1HR_MAX": {
        "full_name": "Composite Reflectivity – 1 hr Max",
        "short_name": "CREF Max",
        "s3_prefix": "CONUS/CREF_1HR_MAX_00.50",
        "units": "dBZ",
        "colormap": "reflectivity",
        "levels": np.arange(5, 76, 5),
        "description": "Composite Reflectivity 1-Hour Maximum",
        "vmin": 0,
        "vmax": 75,
        "missing_value": -99,
        "no_coverage": -999,
    },
    # ── QPE — MultiSensor Pass2 (2-hour latency, gauge corrected) ──────────
    **{
        f"QPE_MS2_{p}": _qpe_entry(
            "MultiSensor Pass2", "MS2", p, f"CONUS/MultiSensor_QPE_{p}_Pass2_00.00"
        )
        for p in ["01H", "03H", "06H", "12H", "24H", "48H", "72H"]
    },
    # ── QPE — MultiSensor Pass1 (1-hour latency, gauge corrected) ──────────
    **{
        f"QPE_MS1_{p}": _qpe_entry(
            "MultiSensor Pass1", "MS1", p, f"CONUS/MultiSensor_QPE_{p}_Pass1_00.00"
        )
        for p in ["01H", "03H", "06H", "12H", "24H", "48H", "72H"]
    },
    # ── QPE — Radar Only (no gauge correction, lowest latency) ─────────────
    **{
        f"QPE_RO_{p}": _qpe_entry(
            "RadarOnly", "RO", p, f"CONUS/RadarOnly_QPE_{p}_00.00"
        )
        for p in ["15M", "01H", "03H", "06H", "12H", "24H", "48H", "72H", "Since12Z"]
    },
    # ── Lightning Probability ───────────────────────────────────────────────
    "Lightning_30min": {
        "full_name": "Lightning Probability – Next 30 min",
        "short_name": "Ltg 30m",
        "s3_prefix": "CONUS/LightningProbabilityNext30minGrid_scale_1",
        "units": "%",
        "colormap": "probability",
        "levels": np.array([5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]),
        "description": "Probability of lightning in next 30 minutes",
        "vmin": 0,
        "vmax": 100,
        "missing_value": -1,
        "no_coverage": -3,
    },
    "Lightning_60min": {
        "full_name": "Lightning Probability – Next 60 min",
        "short_name": "Ltg 60m",
        "s3_prefix": "CONUS/LightningProbabilityNext60minGrid_scale_1",
        "units": "%",
        "colormap": "probability",
        "levels": np.array([5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]),
        "description": "Probability of lightning in next 60 minutes",
        "vmin": 0,
        "vmax": 100,
        "missing_value": -1,
        "no_coverage": -3,
    },
    # ── Model / Environment ─────────────────────────────────────────────────
    "Model_FreezingLevel": {
        "full_name": "Freezing Level Height",
        "short_name": "Frz Lvl",
        "s3_prefix": "CONUS/Model_0degC_Height_00.50",
        "units": "m",
        "colormap": "height",
        "levels": np.array([500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000]),
        "description": "Model 0°C Isotherm Height",
        "vmin": 0,
        "vmax": 5000,
        "missing_value": -1,
        "no_coverage": -3,
    },
    "Model_SurfaceTemp": {
        "full_name": "Surface Temperature",
        "short_name": "Sfc Temp",
        "s3_prefix": "CONUS/Model_SurfaceTemp_00.50",
        "units": "°C",
        "colormap": "temperature",
        "levels": np.arange(-30, 51, 5),
        "description": "Model Surface Temperature",
        "vmin": -30,
        "vmax": 50,
        "missing_value": -999,
        "no_coverage": -9999,
    },
    "Model_WetBulbTemp": {
        "full_name": "Wet Bulb Temperature",
        "short_name": "Wet Bulb",
        "s3_prefix": "CONUS/Model_WetBulbTemp_00.50",
        "units": "°C",
        "colormap": "temperature",
        "levels": np.arange(-30, 51, 5),
        "description": "Model Wet Bulb Temperature",
        "vmin": -30,
        "vmax": 50,
        "missing_value": -999,
        "no_coverage": -9999,
    },
    # ── Quality ─────────────────────────────────────────────────────────────
    "RadarQualityIndex": {
        "full_name": "Radar Quality Index",
        "short_name": "RQI",
        "s3_prefix": "CONUS/RadarQualityIndex_00.00",
        "units": "index",
        "colormap": "quality",
        "levels": np.arange(0, 1.1, 0.1),
        "description": "Radar Quality Index",
        "vmin": 0,
        "vmax": 1,
        "missing_value": -1,
        "no_coverage": -3,
    },
}

# Custom Colormaps for MRMS Products


def _boundary_colormap(colors, boundaries, name, over_color=None):
    cmap = mcolors.ListedColormap(colors, name=name)
    cmap.set_bad("none")
    cmap.set_under("none")
    if over_color:
        cmap.set_over(over_color)
    norm = mcolors.BoundaryNorm(boundaries, cmap.N, clip=False)
    return cmap, norm, boundaries


def create_precip_rate_colormap():
    """NWS-style precipitation rate colormap."""
    colors = [
        "#00ECEC",  # Light blue
        "#01A0F6",  # Blue
        "#0000F6",  # Dark blue
        "#00FF00",  # Green
        "#00C800",  # Dark green
        "#009000",  # Darker green
        "#FFFF00",  # Yellow
        "#E7C000",  # Gold
        "#FF9000",  # Orange
        "#FF0000",  # Red
        "#D60000",  # Dark red
        "#C00000",  # Darker red
        "#FF00FF",  # Magenta
        "#9955C9",  # Purple
    ]
    n_bins = len(colors)
    cmap = mcolors.ListedColormap(colors, name="precip_rate", N=n_bins)
    cmap.set_bad("none")
    cmap.set_under("none")
    return cmap


def create_qpe_colormap():
    """NWS-style QPE accumulation colormap (similar to Stage IV)."""
    colors = [
        "#C7E9C7",  # Very light green
        "#A0D0A0",  # Light green
        "#70B870",  # Green
        "#50A050",  # Dark green
        "#FFFF80",  # Light yellow
        "#FFE000",  # Yellow
        "#FFA000",  # Orange
        "#FF6000",  # Dark orange
        "#FF0000",  # Red
        "#C00000",  # Dark red
        "#A00000",  # Darker red
        "#FF00FF",  # Magenta
        "#C000C0",  # Dark magenta
        "#8000FF",  # Purple
        "#6000C0",  # Dark purple
    ]
    cmap = mcolors.ListedColormap(colors, name="qpe")
    cmap.set_bad("none")
    cmap.set_under("none")
    return cmap


def create_precip_type_colormap():
    """Precipitation type categorical colormap matching real MRMS PrecipFlag values.

    Official MRMS PrecipFlag values (from UserTable_MRMS_PrecipFlags):
        -3 = no coverage  (masked)
         0 = no precip     (masked)
         1 = Warm Rain  → light green
         3 = Snow                  → blue
         6 = Convective       → red
         7 = Rain/Hail         → magenta/pink
        10 = Cold Rain  → dark blue/cyan
        91 = Trop Rain   → yellow-orange
        96 = Trop Conv    → dark orange

    Uses BoundaryNorm so the colormap handles the non-contiguous integer values.
    """
    colors = [
        "#00C800",  # 1  = Warm Stratiform Rain (green)
        "#00BFFF",  # 3  = Snow (deep sky blue)
        "#FF0000",  # 6  = Convective Rain (red)
        "#FF69B4",  # 7  = Rain/Hail Mix (hot pink)
        "#0055FF",  # 10 = Cold Stratiform Rain (blue)
        "#FFB300",  # 91 = Tropical/Strat. Mix (amber)
        "#FF6600",  # 96 = Tropical/Conv. Mix (dark orange)
    ]
    cmap = mcolors.ListedColormap(colors, name="precip_type")
    # Boundaries placed between category values to bin each one correctly
    boundaries = [0.5, 2, 4.5, 6.5, 8.5, 50, 93.5, 100]
    norm = mcolors.BoundaryNorm(boundaries, cmap.N)
    cmap.set_bad("none")
    cmap.set_under("none")
    return cmap, norm, boundaries


def create_reflectivity_colormap():
    """Standard radar reflectivity colormap."""
    colors = [
        "#00ECEC",  # 5-9 dBZ (light blue)
        "#01A0F6",  # 10-14 (blue)
        "#0000F6",  # 15-19 (dark blue)
        "#00FF00",  # 20-24 (green)
        "#00C800",  # 25-29 (dark green)
        "#009000",  # 30-34 (darker green)
        "#FFFF00",  # 35-39 (yellow)
        "#E7C000",  # 40-44 (gold)
        "#FF9000",  # 45-49 (orange)
        "#FF0000",  # 50-54 (red)
        "#D60000",  # 55-59 (dark red)
        "#C00000",  # 60-64 (darker red)
        "#FF00FF",  # 65-69 (magenta)
        "#9955C9",  # 70-74 (purple)
        "#FFFFFF",  # 75+ (white)
    ]
    return mcolors.ListedColormap(colors, name="reflectivity")


def create_quality_colormap():
    """Quality index colormap (low=red, high=green)."""
    colors = [
        "#8B0000",  # 0.0-0.1 (dark red - very poor)
        "#FF0000",  # 0.1-0.2 (red - poor)
        "#FF4500",  # 0.2-0.3 (orange-red)
        "#FF8C00",  # 0.3-0.4 (dark orange)
        "#FFA500",  # 0.4-0.5 (orange)
        "#FFD700",  # 0.5-0.6 (gold)
        "#FFFF00",  # 0.6-0.7 (yellow)
        "#9ACD32",  # 0.7-0.8 (yellow-green)
        "#32CD32",  # 0.8-0.9 (lime green)
        "#228B22",  # 0.9-1.0 (forest green - excellent)
    ]
    return mcolors.ListedColormap(colors, name="quality")


def create_mesh_colormap():
    """MESH legend/colors from SVG reference (MESHMAX)."""
    boundaries = [0, 1, 2, 4, 6, 8, 10, 15, 20, 30, 40, 50, 75, 100]
    colors = [
        "#00ECEC",
        "#01A0F6",
        "#0000F6",
        "#00FF00",
        "#00C800",
        "#009000",
        "#FFFF00",
        "#E7C000",
        "#FF9000",
        "#FF0000",
        "#C00000",
        "#FF00FF",
        "#BE55DC",
    ]
    return _boundary_colormap(colors, boundaries, "mesh", over_color="#7E32A7")


def create_rotation_colormap():
    """Rotation track strength colormap."""
    colors = [
        "#FFFFFF",  # 0 (white - no rotation)
        "#87CEEB",  # 1 (sky blue - very weak)
        "#00BFFF",  # 2 (deep sky blue)
        "#00FF00",  # 3 (green - weak)
        "#ADFF2F",  # 4 (green-yellow)
        "#FFFF00",  # 5 (yellow - moderate)
        "#FFA500",  # 6 (orange)
        "#FF4500",  # 7 (orange-red - strong)
        "#FF0000",  # 8 (red)
        "#C00000",  # 9 (dark red - very strong)
        "#8B008B",  # 10 (dark magenta - extreme)
    ]
    return mcolors.ListedColormap(colors, name="rotation")


def create_azshear_colormap():
    """Azimuthal shear legend/colors from SVG reference (AZ_SHEAR)."""
    boundaries = [
        0.000,
        0.003,
        0.004,
        0.005,
        0.006,
        0.007,
        0.008,
        0.009,
        0.010,
        0.011,
        0.012,
        0.013,
        0.014,
        0.015,
        0.020,
    ]
    colors = [
        "#A0A0A0",
        "#787878",
        "#505050",
        "#777700",
        "#999900",
        "#BBBB00",
        "#DDDD00",
        "#FFFF00",
        "#770000",
        "#990000",
        "#BB0000",
        "#DD0000",
        "#FF0000",
        "#FFFFFF",
    ]
    return _boundary_colormap(colors, boundaries, "azshear", over_color="#00FFFF")


def create_echotop_colormap():
    """Echo top colormap from SVG reference (ETP18 [ECHO TOPS])."""
    boundaries = list(range(0, 21))
    colors = [
        "#00ECEC",
        "#00C8F0",
        "#00A0FF",
        "#003CFF",
        "#00FF00",
        "#00DC00",
        "#00BE00",
        "#008D00",
        "#FFFF00",
        "#F0D200",
        "#E7B400",
        "#C87800",
        "#FFA0A0",
        "#FF3C3C",
        "#E60000",
        "#B40000",
        "#FF00FF",
        "#D900D9",
        "#A400A4",
        "#780078",
    ]
    return _boundary_colormap(colors, boundaries, "echotop")


def create_vil_colormap():
    """VIL colormap from SVG reference (VIL)."""
    boundaries = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 18, 25, 30, 40, 50, 60, 70]
    colors = [
        "#00ECEC",
        "#00A0F6",
        "#0000F6",
        "#00FF00",
        "#00C800",
        "#009000",
        "#FFFF00",
        "#E7C000",
        "#FF9000",
        "#FF0000",
        "#C00000",
        "#FF00FF",
        "#BE55DC",
        "#7E32A7",
        "#FFFFFF",
        "#C8C8C8",
        "#A0A0A0",
        "#808080",
    ]
    return _boundary_colormap(colors, boundaries, "vil", over_color="#404040")


def create_probability_colormap():
    """Probability colormap (0-100%) — shared by POSH and Lightning."""
    colors = [
        "#E0E0E0",  # 0-10% (light gray)
        "#A0D0FF",  # 10-20 (light blue)
        "#60B0FF",  # 20-30 (blue)
        "#00CC00",  # 30-40 (green)
        "#80E000",  # 40-50 (yellow-green)
        "#FFFF00",  # 50-60 (yellow)
        "#FFA500",  # 60-70 (orange)
        "#FF4500",  # 70-80 (orange-red)
        "#FF0000",  # 80-90 (red)
        "#C00000",  # 90-100 (dark red)
    ]
    return mcolors.ListedColormap(colors, name="probability")


def create_shi_colormap():
    """SHI colormap from SVG reference (SHI)."""
    boundaries = [0, 5, 10, 20, 30, 40, 50, 60, 80, 100, 150, 250, 500, 1500]
    colors = [
        "#00ECEC",
        "#01A0F6",
        "#0000F6",
        "#00FF00",
        "#00C800",
        "#009000",
        "#FFFF00",
        "#E7C000",
        "#FF9000",
        "#FF0000",
        "#C00000",
        "#FF00FF",
        "#BE55DC",
    ]
    return _boundary_colormap(colors, boundaries, "shi", over_color="#7E32A7")


def create_temperature_colormap():
    """Temperature colormap (°C) — purple through red."""
    colors = [
        "#9955C9",  # -30 to -20 (purple)
        "#6060FF",  # -20 to -10 (blue)
        "#00BFFF",  # -10 to 0 (sky blue)
        "#00E0A0",  # 0 to 5 (teal)
        "#00CC00",  # 5 to 10 (green)
        "#80E000",  # 10 to 15 (yellow-green)
        "#CCCC00",  # 15 to 20 (dark yellow)
        "#FFD700",  # 20 to 25 (gold)
        "#FFA500",  # 25 to 30 (orange)
        "#FF4500",  # 30 to 35 (orange-red)
        "#FF0000",  # 35 to 40 (red)
        "#C00000",  # 40 to 45 (dark red)
        "#8B008B",  # 45 to 50 (dark magenta)
    ]
    return mcolors.ListedColormap(colors, name="temperature")


def create_height_colormap():
    """Height/altitude colormap (m) — blue through red-brown."""
    colors = [
        "#00BFFF",  # 0-500 m (sky blue)
        "#0080FF",  # 500-1000 (blue)
        "#00CC00",  # 1000-1500 (green)
        "#80E000",  # 1500-2000 (yellow-green)
        "#FFFF00",  # 2000-2500 (yellow)
        "#FFD700",  # 2500-3000 (gold)
        "#FFA500",  # 3000-3500 (orange)
        "#FF4500",  # 3500-4000 (orange-red)
        "#FF0000",  # 4000-4500 (red)
        "#8B4513",  # 4500-5000 (saddle brown)
    ]
    return mcolors.ListedColormap(colors, name="height")


# Colormap registry
MRMS_COLORMAPS = {
    "precip_rate": create_precip_rate_colormap(),
    "qpe": create_qpe_colormap(),
    "precip_type": create_precip_type_colormap(),  # returns (cmap, norm, boundaries)
    "reflectivity": create_reflectivity_colormap(),
    "quality": create_quality_colormap(),
    "mesh": create_mesh_colormap(),
    "rotation": create_rotation_colormap(),
    "azshear": create_azshear_colormap(),
    "echotop": create_echotop_colormap(),
    "vil": create_vil_colormap(),
    "probability": create_probability_colormap(),
    "shi": create_shi_colormap(),
    "temperature": create_temperature_colormap(),
    "height": create_height_colormap(),
}

# MRMS S3 Bucket
MRMS_BUCKET = "noaa-mrms-pds"

# Archive depth (MRMS data available from ~2015+ depending on product)
MRMS_ARCHIVE_START = "2015-01-01"

# ═════════════════════════════════════════════════════════════════════════════
# SUB-PRODUCT DROPDOWN DEFINITIONS (consumed by frontend)
# ═════════════════════════════════════════════════════════════════════════════
# Each family with sub-products defines:
#   selectors: ordered list of sub-dropdown configs
#     - id:      HTML element id suffix
#     - label:   <label> text
#     - options: [(value, display_text), ...]
#     - default: default option value
#   compose:  a Python-format template for building the product key from
#             the family key + selector values.
#
# The frontend reads this to build the UI; compose() is for documentation/
# reference (the JS equivalent is composeMrmsProductKey()).

MRMS_SUB_PRODUCTS = {
    "RotationTrack": {
        "selectors": [
            {
                "id": "mrms-rotation-level",
                "label": "Altitude Level",
                "options": [("LL", "Low Level (0-2 km)"), ("ML", "Mid Level (3-6 km)")],
                "default": "LL",
            },
            {
                "id": "mrms-rotation-time",
                "label": "Time Window",
                "options": [
                    ("30min", "30 min"),
                    ("60min", "60 min"),
                    ("120min", "2 hr"),
                    ("240min", "4 hr"),
                    ("360min", "6 hr"),
                    ("1440min", "24 hr"),
                ],
                "default": "60min",
            },
        ],
    },
    "MESH": {
        "selectors": [
            {
                "id": "mrms-mesh-time",
                "label": "Time Window",
                "options": [
                    ("Instant", "Instant"),
                    ("Max_30min", "Max 30 min"),
                    ("Max_60min", "Max 60 min"),
                    ("Max_120min", "Max 2 hr"),
                    ("Max_240min", "Max 4 hr"),
                    ("Max_360min", "Max 6 hr"),
                    ("Max_1440min", "Max 24 hr"),
                ],
                "default": "Instant",
            },
        ],
    },
    "AzShear": {
        "selectors": [
            {
                "id": "mrms-azshear-level",
                "label": "Altitude Level",
                "options": [
                    ("Low", "Low Level (0-2 km)"),
                    ("Mid", "Mid Level (3-6 km)"),
                ],
                "default": "Low",
            },
        ],
    },
    "EchoTop": {
        "selectors": [
            {
                "id": "mrms-echotop-threshold",
                "label": "dBZ Threshold",
                "options": [
                    ("18", "18 dBZ"),
                    ("30", "30 dBZ"),
                    ("50", "50 dBZ"),
                    ("60", "60 dBZ"),
                ],
                "default": "18",
            },
        ],
    },
    "VIL": {
        "selectors": [
            {
                "id": "mrms-vil-type",
                "label": "Type",
                "options": [
                    ("Instant", "Instant"),
                    ("Density", "Density"),
                    ("Max_120min", "Max 2 hr"),
                    ("Max_1440min", "Max 24 hr"),
                ],
                "default": "Instant",
            },
        ],
    },
    "QPE": {
        "selectors": [
            {
                "id": "mrms-qpe-source",
                "label": "Source",
                "options": [
                    ("MS2", "MultiSensor Pass2"),
                    ("MS1", "MultiSensor Pass1"),
                    ("RO", "Radar Only"),
                ],
                "default": "MS2",
            },
            {
                "id": "mrms-qpe-period",
                "label": "Accumulation Period",
                "options": [
                    ("01H", "1 Hour"),
                    ("03H", "3 Hour"),
                    ("06H", "6 Hour"),
                    ("12H", "12 Hour"),
                    ("24H", "24 Hour"),
                    ("48H", "48 Hour"),
                    ("72H", "72 Hour"),
                ],
                "default": "01H",
            },
        ],
    },
    "Reflectivity": {
        "selectors": [
            {
                "id": "mrms-refl-variant",
                "label": "Variant",
                "options": [
                    ("HSR", "Hybrid Scan (HSR)"),
                    ("BaseQC", "Base Reflectivity (QC)"),
                    ("CompLow", "Composite – Low"),
                    ("CompHigh", "Composite – High"),
                    ("CompSuper", "Composite – Super"),
                    ("BREF_1HR_MAX", "Base Refl 1hr Max"),
                    ("CREF_1HR_MAX", "Comp Refl 1hr Max"),
                ],
                "default": "HSR",
            },
        ],
    },
    "Lightning": {
        "selectors": [
            {
                "id": "mrms-lightning-window",
                "label": "Forecast Window",
                "options": [("30min", "Next 30 min"), ("60min", "Next 60 min")],
                "default": "30min",
            },
        ],
    },
    "Model": {
        "selectors": [
            {
                "id": "mrms-model-field",
                "label": "Field",
                "options": [
                    ("FreezingLevel", "Freezing Level Height"),
                    ("SurfaceTemp", "Surface Temperature"),
                    ("WetBulbTemp", "Wet Bulb Temperature"),
                ],
                "default": "FreezingLevel",
            },
        ],
    },
}

# Families with no sub-products are standalone entries:
# PrecipRate, PrecipFlag, SHI, POSH, RadarQualityIndex

# Product groupings for UI (family-level for the primary dropdown)
PRODUCT_GROUPS = {
    "Precipitation": ["PrecipRate", "PrecipFlag"],
    "Rotation Tracks": ["RotationTrack"],
    "MESH / Hail": ["MESH", "SHI", "POSH"],
    "Azimuthal Shear": ["AzShear"],
    "Echo Top": ["EchoTop"],
    "VIL": ["VIL"],
    "QPE Accumulation": ["QPE"],
    "Reflectivity": ["Reflectivity"],
    "Lightning Probability": ["Lightning"],
    "Model / Environment": ["Model"],
    "Quality": ["RadarQualityIndex"],
}
