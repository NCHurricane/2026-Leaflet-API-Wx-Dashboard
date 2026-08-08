"""Authoritative Surface color palettes shared by services and workers."""

TEMPERATURE_MIN_F = -60
TEMPERATURE_MAX_F = 130


TEMPERATURE_GRADIENT_ANCHORS = (
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
)

RELATIVE_HUMIDITY_GRADIENT_ANCHORS = (
    (0, "#c8a000"),
    (20, "#f5dd72"),
    (40, "#69bb6d"),
    (60, "#0099cc"),
    (80, "#0055aa"),
    (100, "#003377"),
)

WIND_GRADIENT_ANCHORS = (
    (0, "#b0d4f0"),
    (10, "#70b0e0"),
    (20, "#3090d0"),
    (30, "#f5dd72"),
    (45, "#ff9d2e"),
    (60, "#ff4f4f"),
)

ALTIMETER_GRADIENT_ANCHORS = (
    (29.5, "#5b1a8f"),
    (30.0, "#2a6db3"),
    (30.2, "#2ca58d"),
    (30.4, "#f5dd72"),
    (30.6, "#ff9d2e"),
    (30.8, "#bf2c2c"),
)

MSLP_GRADIENT_ANCHORS = (
    (990, "#5b1a8f"),
    (1000, "#2a6db3"),
    (1010, "#2ca58d"),
    (1020, "#f5dd72"),
    (1030, "#ff9d2e"),
    (1040, "#bf2c2c"),
)

VISIBILITY_GRADIENT_ANCHORS = (
    (0, "#7f1d1d"),
    (1, "#b45309"),
    (3, "#d97706"),
    (5, "#65a30d"),
    (7, "#16a34a"),
    (10, "#0ea5e9"),
)

SURFACE_COLOR_ANCHORS = {
    "station_plot": TEMPERATURE_GRADIENT_ANCHORS,
    "temperature": TEMPERATURE_GRADIENT_ANCHORS,
    "feels_like": TEMPERATURE_GRADIENT_ANCHORS,
    "dew_point": TEMPERATURE_GRADIENT_ANCHORS,
    "relative_humidity": RELATIVE_HUMIDITY_GRADIENT_ANCHORS,
    "wind_speed": WIND_GRADIENT_ANCHORS,
    "wind_gust": WIND_GRADIENT_ANCHORS,
    "altimeter": ALTIMETER_GRADIENT_ANCHORS,
    "mslp": MSLP_GRADIENT_ANCHORS,
    "visibility": VISIBILITY_GRADIENT_ANCHORS,
}
