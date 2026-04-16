import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import os

try:
    from metpy.plots import ctables
except Exception:
    ctables = None


def _get_metpy_colormap(table_name, fallback_name):
    if ctables is not None:
        try:
            return ctables.registry.get_colortable(table_name)
        except Exception:
            pass
    return plt.get_cmap(fallback_name)


def _get_metpy_colormap_with_range(table_name, fallback_name, start_k, end_k):
    if ctables is not None:
        try:
            norm, cmap = ctables.registry.get_with_range(table_name, start_k, end_k)
            return cmap, norm
        except Exception:
            try:
                cmap = ctables.registry.get_colortable(table_name)
                return cmap, mcolors.Normalize(vmin=start_k, vmax=end_k)
            except Exception:
                pass

    cmap = plt.get_cmap(fallback_name)
    return cmap, mcolors.Normalize(vmin=start_k, vmax=end_k)


def _build_satpy_colorized_ir_clouds():
    """Approximate Satpy generic.yaml colorized_ir_clouds enhancement.

    Satpy uses a segmented enhancement for brightness temperature:
    - 193.15 K to 253.15 K: spectral
    - 253.15 K to 303.15 K: greys
    """
    vmin, vmid, vmax = 193.15, 253.15, 303.15
    steps = 256
    split = int(round((vmid - vmin) / (vmax - vmin) * (steps - 1)))
    split = max(2, min(steps - 2, split))

    spectral = plt.get_cmap("Spectral")(np.linspace(0, 1, split))
    greys = plt.get_cmap("Greys")(np.linspace(0, 1, steps - split))
    colors = np.vstack([spectral, greys])

    cmap = mcolors.ListedColormap(colors, name="satpy_colorized_ir_clouds")
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    return cmap, norm


def _load_awips_cmap(filename, subdir, name, vmin, vmax):
    """Load an AWIPS-format .cmap XML file and return (ListedColormap, Normalize).

    AWIPS .cmap files contain N RGBA colour entries in attribute-style XML
    (``<color a="..." b="..." g="..." r="..."/>``), ordered from warmest
    (index 0) to coldest (index N-1).  The array is reversed so that
    matplotlib's Normalize(vmin, vmax) maps low values → low indices (cold
    colours) and high values → high indices (warm colours/grays).

    Parameters
    ----------
    filename : str
        Name of the .cmap file (e.g. ``"IR_Color_Clouds_Summer.cmap"``).
    subdir : str
        Slash-separated path under ``config/cmaps/``
        (e.g. ``"GOES-R/IR"``).
    name : str
        Internal colourmap name for matplotlib.
    vmin, vmax : float
        Brightness-temperature (K) limits for the Normalize object.
    """
    import xml.etree.ElementTree as ET

    cmap_dir = os.path.join(os.path.dirname(__file__), "cmaps", *subdir.split("/"))
    cmap_path = os.path.join(cmap_dir, filename)

    tree = ET.parse(cmap_path)
    root = tree.getroot()

    colors = []
    for c in root.findall("color"):
        r = float(c.get("r", "0"))
        g = float(c.get("g", "0"))
        b = float(c.get("b", "0"))
        colors.append([r, g, b, 1.0])

    rgba = np.array(colors)
    rgba[:, 3] = 1.0  # ensure opaque

    # Reverse: AWIPS idx-0 = warmest; matplotlib convention = low-value first.
    rgba_rev = rgba[::-1]

    cmap = mcolors.ListedColormap(rgba_rev, name=name)
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    return cmap, norm


# MetPy-default thermal infrared presentation.
IR_CMAP, IR_NORM = _build_satpy_colorized_ir_clouds()

# ── AWIPS .cmap-based colormaps (Dan Lindsey / Chad Gravelle / CIRA) ──────

# CIRA Clean IR Summer — matches CIRA/RAMMB SLIDER (Dan Lindsey).
# 2048 entries, gray→cyan→blue→green→yellow.  160–330 K.
CIRA_IR_CMAP, CIRA_IR_NORM = _load_awips_cmap(
    "IR_Color_Clouds_Summer.cmap", "GOES-R/IR", "cira_clean_ir", 160.0, 330.0
)

# CIRA Clean IR Winter — same colour scheme tuned for cooler backgrounds.
# 2048 entries, 160–330 K.
CIRA_IR_WINTER_CMAP, CIRA_IR_WINTER_NORM = _load_awips_cmap(
    "IR_Color_Clouds_Winter.cmap", "GOES-R/IR", "cira_clean_ir_winter", 160.0, 330.0
)

# Fire Detection 3.9 µm — Chad Gravelle.
# 2048 entries, gray (cold) → yellow → orange → red (fires).  164–400 K.
FIRE_DETECT_CMAP, FIRE_DETECT_NORM = _load_awips_cmap(
    "fire_detection_3.9.cmap", "GOES-R/IR", "fire_detect_3.9", 164.0, 400.0
)

# RAMSDIS Water Vapor 12-bit — Dan Lindsey.
# 4096 entries, complex multi-colour WV enhancement.  163–330 K.
RAMSDIS_WV_CMAP, RAMSDIS_WV_NORM = _load_awips_cmap(
    "ramsdis_WV_12bit.cmap", "GOES-R/IR", "ramsdis_wv", 163.0, 330.0
)

# Fog Difference (10.3−3.9 µm) Blue — Dan Lindsey.
# 2048 entries, gray (non-fog) → shades of blue (liquid water clouds).
# Applied to Ch13−Ch07 brightness-temperature difference (K).
FOGDIFF_BLUE_CMAP, FOGDIFF_BLUE_NORM = _load_awips_cmap(
    "fogdiff_blue.cmap", "GOES-R/IR", "fogdiff_blue", -70.0, 30.0
)

IR_TPC_CMAP, IR_TPC_NORM = _get_metpy_colormap_with_range("ir_tpc", "turbo", 170, 330)

IR_TV1_CMAP, IR_TV1_NORM = _get_metpy_colormap_with_range("ir_tv1", "turbo", 170, 330)

IR_BD_CMAP, IR_BD_NORM = _get_metpy_colormap_with_range("ir_bd", "Greys_r", 170, 330)

IR_RGBV_CMAP, IR_RGBV_NORM = _get_metpy_colormap_with_range(
    "ir_rgbv", "turbo", 170, 330
)

IR_DRGB_CMAP, IR_DRGB_NORM = _get_metpy_colormap_with_range(
    "ir_drgb", "plasma", 170, 330
)


# MetPy-default water vapor presentation.
WV_CMAP, WV_NORM = _get_metpy_colormap_with_range("WVCIMSS", "viridis", 180, 280)

WV_TPC_CMAP, WV_TPC_NORM = _get_metpy_colormap_with_range("wv_tpc", "viridis", 180, 280)

# Satpy generic.yaml water_vapors1_default stretch bounds (per channel).
# min_stretch: [278.96, 242.67, 261.03]
# max_stretch: [202.29, 214.66, 245.12]
WV_UPPER_CMAP = _get_metpy_colormap("WVCIMSS", "viridis")
WV_UPPER_NORM = mcolors.Normalize(vmin=202.29, vmax=278.96, clip=True)

WV_MID_CMAP = _get_metpy_colormap("WVCIMSS", "viridis")
WV_MID_NORM = mcolors.Normalize(vmin=214.66, vmax=242.67, clip=True)

WV_LOW_CMAP = _get_metpy_colormap("WVCIMSS", "viridis")
WV_LOW_NORM = mcolors.Normalize(vmin=245.12, vmax=261.03, clip=True)

# Satpy generic.yaml water_vapors2_default stretch bounds (per channel).
# min_stretch: [30, 278.15, 243.9]
# max_stretch: [-3, 213.15, 208.5]
# First component appears in Celsius in Satpy config; converted here to Kelvin.
WV2_UPPER_CMAP = _get_metpy_colormap("WVCIMSS_r", "viridis_r")
WV2_UPPER_NORM = mcolors.Normalize(vmin=270.15, vmax=303.15, clip=True)

WV2_MID_CMAP = _get_metpy_colormap("WVCIMSS", "viridis")
WV2_MID_NORM = mcolors.Normalize(vmin=213.15, vmax=278.15, clip=True)

WV2_LOW_CMAP = _get_metpy_colormap("WVCIMSS", "viridis")
WV2_LOW_NORM = mcolors.Normalize(vmin=208.5, vmax=243.9, clip=True)


# MetPy-default shortwave IR presentation.
SW_CMAP, SW_NORM = _get_metpy_colormap_with_range("ir_bd", "plasma", 190, 340)

SW_DRGB_CMAP, SW_DRGB_NORM = _get_metpy_colormap_with_range(
    "ir_drgb", "plasma", 190, 340
)
