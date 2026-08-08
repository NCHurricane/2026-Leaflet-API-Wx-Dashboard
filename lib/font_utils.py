import os
import matplotlib
from matplotlib import font_manager as fm

_REGISTERED = False


def register_montserrat_fonts(fonts_dir=None):
    """Register local Montserrat .ttf files so all weights are available."""
    global _REGISTERED
    if _REGISTERED:
        return

    if fonts_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        fonts_dir = os.path.join(base_dir, "fonts")

    if not os.path.isdir(fonts_dir):
        return

    for name in os.listdir(fonts_dir):
        if name.lower().endswith(".ttf"):
            fm.fontManager.addfont(os.path.join(fonts_dir, name))

    matplotlib.rcParams["font.family"] = "Montserrat"
    matplotlib.rcParams["font.sans-serif"] = ["Montserrat", "DejaVu Sans"]
    _REGISTERED = True
