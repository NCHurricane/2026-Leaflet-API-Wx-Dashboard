import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import os

try:
    from metpy.plots import ctables
except Exception:
    ctables = None


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


def _load_awips_cmap(filename, name, vmin, vmax):
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
    name : str
        Internal colourmap name for matplotlib.
    vmin, vmax : float
        Brightness-temperature (K) limits for the Normalize object.
    """
    import xml.etree.ElementTree as ET

    cmap_dir = os.path.join(os.path.dirname(__file__), "sat_cmaps")
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


# ── AWIPS .cmap-based colormaps (Dan Lindsey / Chad Gravelle / CIRA) ──────

# CIRA Clean IR Summer — matches CIRA/RAMMB SLIDER (Dan Lindsey).
# 2048 entries, gray→cyan→blue→green→yellow.  160–330 K.
CIRA_IR_CMAP, CIRA_IR_NORM = _load_awips_cmap(
    "IR_Color_Clouds_Summer.cmap", "cira_clean_ir", 160.0, 330.0
)

# Fire Detection 3.9 µm — Chad Gravelle.
# 2048 entries, gray (cold) → yellow → orange → red (fires).  164–400 K.
FIRE_DETECT_CMAP, FIRE_DETECT_NORM = _load_awips_cmap(
    "fire_detection_3.9.cmap", "fire_detect_3.9", 164.0, 400.0
)

# RAMSDIS Water Vapor 12-bit — Dan Lindsey.
# 4096 entries, complex multi-colour WV enhancement.  163–330 K.
RAMSDIS_WV_CMAP, RAMSDIS_WV_NORM = _load_awips_cmap(
    "ramsdis_WV_12bit.cmap", "ramsdis_wv", 163.0, 330.0
)

IR_TPC_CMAP, IR_TPC_NORM = _get_metpy_colormap_with_range("ir_tpc", "turbo", 170, 330)

# MetPy-default shortwave IR presentation.
SW_CMAP, SW_NORM = _get_metpy_colormap_with_range("ir_bd", "plasma", 190, 340)
