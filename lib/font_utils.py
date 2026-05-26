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


def resolve_logo_path(style_config, base_dir, default_logo):
    """Resolve logo file path from style_config, with fallback to *default_logo*.

    The dashboard repeats this pattern in every endpoint.  This function
    centralises the logic:

    1. Check ``style_config["logo_path"]``.
    2. If relative, join with *base_dir*.
    3. If the resolved path doesn't exist on disk, fall back to *default_logo*.

    Parameters
    ----------
    style_config : dict or None
        Parsed user style overrides.
    base_dir : str
        Project root directory for relative path resolution.
    default_logo : str
        Absolute path to the default logo image.

    Returns
    -------
    str
        Absolute path to the logo file to use.
    """
    logo_path_from_style = style_config.get("logo_path") if style_config else None
    if logo_path_from_style:
        if not os.path.isabs(logo_path_from_style):
            logo_path_to_use = os.path.join(base_dir, logo_path_from_style)
        else:
            logo_path_to_use = logo_path_from_style
        if os.path.exists(logo_path_to_use):
            return logo_path_to_use
    return default_logo
