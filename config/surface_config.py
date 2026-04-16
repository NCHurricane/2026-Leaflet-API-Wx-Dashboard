import numpy as np
from matplotlib.colors import LinearSegmentedColormap


TEMPERATURE_MIN_F = -60
TEMPERATURE_MAX_F = 130
TEMPERATURE_STEP_F = 2


TEMPERATURE_GRADIENT_ANCHORS = [
    (-60, "#00352C"),  # dark blue-green
    (-40, "#80b1b1"),  # light blue-green
    (-20, "#c4c4d4"),  # lavender
    (0, "#570057"),  # purple
    (2, "#ff69b4"),  # hot pink
    (10, "#c5939b"),  # pink
    (20, "#8db1bd"),  # light blue
    (32, "#0000ff"),  # blue
    (34, "#009400"),  # dark green
    (40, "#004600"),  # green
    (50, "#c4c403"),  # yellow
    (60, "#c78203"),  # orange
    (80, "#c20303"),  # red
    (100, "#bbbbbb"),  # white
    (130, "#000000"),  # black
]


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _interpolate_hex(start_hex, end_hex, fraction):
    start_rgb = _hex_to_rgb(start_hex)
    end_rgb = _hex_to_rgb(end_hex)
    out_rgb = tuple(
        int(round(start_rgb[i] + (end_rgb[i] - start_rgb[i]) * fraction))
        for i in range(3)
    )
    return _rgb_to_hex(out_rgb)


def build_temperature_gradient_levels_colors():
    """Build a 2°F-stepped palette from TEMPERATURE_MIN_F..TEMPERATURE_MAX_F."""
    temps = np.arange(TEMPERATURE_MIN_F, TEMPERATURE_MAX_F + 1, TEMPERATURE_STEP_F)
    colors = []

    for temp in temps:
        for idx in range(len(TEMPERATURE_GRADIENT_ANCHORS) - 1):
            t0, c0 = TEMPERATURE_GRADIENT_ANCHORS[idx]
            t1, c1 = TEMPERATURE_GRADIENT_ANCHORS[idx + 1]
            if t0 <= temp <= t1:
                if t1 == t0:
                    colors.append(c0)
                else:
                    frac = (temp - t0) / (t1 - t0)
                    colors.append(_interpolate_hex(c0, c1, frac))
                break
        else:
            if temp < TEMPERATURE_GRADIENT_ANCHORS[0][0]:
                colors.append(TEMPERATURE_GRADIENT_ANCHORS[0][1])
            else:
                colors.append(TEMPERATURE_GRADIENT_ANCHORS[-1][1])

    return temps, colors


def build_temperature_colormap(cmap_name="custom_temp"):
    levels, colors = build_temperature_gradient_levels_colors()
    cmap = LinearSegmentedColormap.from_list(
        cmap_name,
        list(zip(np.linspace(0, 1, len(colors)), colors)),
    )
    return cmap, levels


TEMPERATURE_COLORMAP, TEMPERATURE_LEVELS = build_temperature_colormap()

# Feels Like uses the same colorbar as Temperature.
FEELS_LIKE_COLORMAP = TEMPERATURE_COLORMAP
FEELS_LIKE_MIN_F = TEMPERATURE_MIN_F
FEELS_LIKE_MAX_F = TEMPERATURE_MAX_F
