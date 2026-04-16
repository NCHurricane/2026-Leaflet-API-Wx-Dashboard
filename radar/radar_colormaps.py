"""
GRS-style radar color palettes for NEXRAD products.
Matches the color schemes from Gibson Ridge Software.
"""

import matplotlib.colors as mcolors


def _from_breakpoints(name, vmin, vmax, breaks, colors):
    """Build a segmented colormap from explicit value breakpoints."""
    if len(breaks) != len(colors):
        raise ValueError(f"{name}: breaks and colors must be same length")

    span = float(vmax - vmin)
    if span <= 0:
        raise ValueError(f"{name}: invalid range {vmin}..{vmax}")

    points = []
    for value, color in zip(breaks, colors):
        norm = (float(value) - float(vmin)) / span
        norm = min(max(norm, 0.0), 1.0)
        points.append((norm, tuple(channel / 255.0 for channel in color)))

    return mcolors.LinearSegmentedColormap.from_list(name, points, N=256)


def create_grs_cc_cmap():
    """
    Correlation Coefficient colormap (0.0-1.0).
    Used to identify precipitation vs non-precipitation targets.
    """
    breaks = [0.70, 0.75, 0.80, 0.85, 0.90, 0.93, 0.96, 0.98, 1.00]
    colors = [
        (40, 40, 120),
        (0, 110, 255),
        (0, 180, 255),
        (60, 220, 120),
        (220, 220, 0),
        (255, 160, 0),
        (220, 70, 0),
        (170, 0, 90),
        (255, 255, 255),
    ]
    return _from_breakpoints("ROC_CC", 0.70, 1.00, breaks, colors)


def create_grs_bv_cmap():
    """
    Base Velocity colormap (-160 to +160 knots).
    Zero velocity (0 kts) is white, positive (outbound) uses warm colors,
    negative (inbound) uses cool colors.
    """

    breaks = [-160, -120, -90, -60, -40, -25, -10, 0, 10, 25, 40, 60, 90, 120, 160]
    colors = [
        (80, 0, 130),
        (70, 20, 170),
        (45, 55, 185),
        (20, 95, 215),
        (25, 150, 235),
        (60, 200, 180),
        (120, 230, 150),
        (255, 255, 255),
        (255, 220, 150),
        (255, 180, 90),
        (255, 130, 60),
        (240, 80, 40),
        (210, 35, 35),
        (170, 20, 20),
        (120, 0, 0),
    ]
    return _from_breakpoints("ROC_BV", -160, 160, breaks, colors)


def create_grs_br_cmap():
    """
    Base Reflectivity colormap (-10 to +95 dBZ).
    Standard NEXRAD reflectivity color progression.
    """
    breaks = [
        -10,
        0,
        5,
        10,
        15,
        20,
        25,
        30,
        35,
        40,
        45,
        50,
        55,
        60,
        65,
        70,
        75,
        80,
        85,
        90,
        95,
    ]
    colors = [
        (70, 70, 70),
        (110, 110, 110),
        (145, 145, 145),
        (0, 236, 236),
        (1, 160, 246),
        (0, 0, 246),
        (0, 255, 0),
        (0, 200, 0),
        (0, 144, 0),
        (255, 255, 0),
        (231, 192, 0),
        (255, 144, 0),
        (255, 0, 0),
        (214, 0, 0),
        (192, 0, 0),
        (255, 0, 255),
        (153, 85, 201),
        (235, 235, 235),
        (195, 195, 195),
        (150, 150, 150),
        (255, 255, 255),
    ]
    return _from_breakpoints("ROC_BR", -10, 95, breaks, colors)


def create_grs_zdr_cmap():
    """
    Differential Reflectivity colormap (-2 to +8 dB).
    """
    breaks = [-2, -1, -0.5, 0, 0.5, 1, 2, 3, 4, 6, 8]
    colors = [
        (65, 0, 120),
        (85, 35, 165),
        (70, 95, 225),
        (30, 170, 255),
        (40, 210, 180),
        (60, 220, 95),
        (170, 220, 20),
        (255, 220, 0),
        (255, 160, 0),
        (235, 70, 0),
        (200, 0, 0),
    ]
    return _from_breakpoints("ROC_ZDR", -2, 8, breaks, colors)


def create_grs_vil_cmap():
    """
    Vertically Integrated Liquid colormap (0 to 80 kg m^-2).
    """
    breaks = [0, 5, 10, 20, 30, 40, 50, 60, 70, 80]
    colors = [
        (45, 45, 45),
        (0, 100, 225),
        (0, 170, 255),
        (0, 210, 145),
        (40, 210, 40),
        (200, 220, 20),
        (255, 185, 0),
        (255, 110, 0),
        (220, 0, 0),
        (255, 255, 255),
    ]
    return _from_breakpoints("ROC_VIL", 0, 80, breaks, colors)


def create_grs_et_cmap():
    """
    Echo Tops colormap (0 to 70 kft).
    """
    breaks = [0, 10, 20, 30, 40, 50, 60, 70]
    colors = [
        (35, 35, 35),
        (0, 120, 255),
        (0, 210, 220),
        (30, 210, 90),
        (220, 220, 0),
        (255, 145, 0),
        (220, 20, 20),
        (255, 0, 255),
    ]
    return _from_breakpoints("ROC_ET", 0, 70, breaks, colors)


def create_grs_sw_cmap():
    """
    Spectrum Width colormap (0 to 30 kt).
    """
    breaks = [0, 2, 4, 6, 8, 10, 14, 18, 22, 26, 30]
    colors = [
        (20, 20, 20),
        (70, 70, 120),
        (50, 100, 200),
        (35, 155, 230),
        (20, 200, 190),
        (40, 210, 90),
        (170, 220, 30),
        (255, 220, 0),
        (255, 155, 0),
        (235, 70, 0),
        (200, 0, 0),
    ]
    return _from_breakpoints("ROC_SW", 0, 30, breaks, colors)


def create_grs_precip_cmap():
    """
    One-hour precipitation colormap (0 to 4 in/hr equivalent scale).
    """
    breaks = [0.0, 0.05, 0.10, 0.25, 0.50, 1.0, 1.5, 2.0, 3.0, 4.0]
    colors = [
        (40, 40, 40),
        (120, 120, 120),
        (120, 200, 255),
        (50, 155, 255),
        (20, 190, 120),
        (170, 220, 30),
        (255, 210, 0),
        (255, 145, 0),
        (235, 70, 0),
        (200, 0, 0),
    ]
    return _from_breakpoints("ROC_PRECIP", 0.0, 4.0, breaks, colors)


def create_grs_dpa_cmap():
    """
    Digital Precipitation Array colormap (0 to 8 in equivalent scale).
    """
    breaks = [0.0, 0.05, 0.10, 0.25, 0.50, 1.0, 2.0, 3.0, 5.0, 8.0]
    colors = [
        (45, 45, 45),
        (110, 110, 110),
        (130, 205, 255),
        (55, 160, 255),
        (20, 190, 120),
        (170, 220, 30),
        (255, 210, 0),
        (255, 145, 0),
        (235, 70, 0),
        (200, 0, 0),
    ]
    return _from_breakpoints("ROC_DPA", 0.0, 8.0, breaks, colors)


def create_grs_precip_total_cmap():
    """
    Storm-total precipitation colormap (0 to 20 in equivalent scale).
    """
    breaks = [0.0, 0.10, 0.25, 0.50, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 16.0, 20.0]
    colors = [
        (45, 45, 45),
        (95, 95, 95),
        (120, 200, 255),
        (45, 150, 255),
        (20, 190, 120),
        (170, 220, 30),
        (255, 210, 0),
        (255, 145, 0),
        (235, 70, 0),
        (210, 35, 35),
        (175, 0, 90),
        (255, 255, 255),
    ]
    return _from_breakpoints("ROC_PRECIP_TOTAL", 0.0, 20.0, breaks, colors)


def create_grs_hca_style():
    """
    Hydrometeor Classification style (categorical classes).
    Returns cmap, norm, ticks, labels.
    """
    labels = [
        "Biological",
        "AP/Clutter",
        "Ice Crystals",
        "Dry Snow",
        "Wet Snow",
        "Light Rain",
        "Heavy Rain",
        "Big Drops",
        "Graupel",
        "Hail",
    ]

    colors = [
        (170 / 255, 0 / 255, 170 / 255),
        (130 / 255, 130 / 255, 130 / 255),
        (110 / 255, 180 / 255, 255 / 255),
        (40 / 255, 120 / 255, 255 / 255),
        (80 / 255, 210 / 255, 255 / 255),
        (70 / 255, 210 / 255, 90 / 255),
        (255 / 255, 220 / 255, 0 / 255),
        (255 / 255, 150 / 255, 0 / 255),
        (235 / 255, 70 / 255, 0 / 255),
        (215 / 255, 0 / 255, 0 / 255),
    ]

    cmap = mcolors.ListedColormap(colors, name="ROC_HCA")
    ticks = list(range(1, 11))
    bounds = [x - 0.5 for x in range(1, 12)]
    norm = mcolors.BoundaryNorm(bounds, cmap.N)
    return cmap, norm, ticks, labels


# Convenience dictionary for easy lookup
GRS_COLORMAPS = {
    "CC": create_grs_cc_cmap,
    "BV": create_grs_bv_cmap,
    "BR": create_grs_br_cmap,
    "ZDR": create_grs_zdr_cmap,
    "VIL": create_grs_vil_cmap,
    "ET": create_grs_et_cmap,
    "SW": create_grs_sw_cmap,
    "PRECIP": create_grs_precip_cmap,
    "DPA": create_grs_dpa_cmap,
    "PRECIP_TOTAL": create_grs_precip_total_cmap,
    "HCA": create_grs_hca_style,
}
