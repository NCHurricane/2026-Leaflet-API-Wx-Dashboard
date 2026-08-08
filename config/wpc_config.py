"""WPC product registry and color tables for the /wpc page."""

from __future__ import annotations

WPC_BASE_URL = "https://www.wpc.ncep.noaa.gov"

# ERO categorical risk -> fill color. Values match the colors embedded in the
# WPC ERO KMZ PolyStyle blocks (decoded from KML ABGR), verified 2026-06-18
# against Day_1_Excessive_Rainfall_Outlook.kmz.
ERO_COLORS: dict[str, str] = {
    "MRGL": "#00FF00",  # Marginal  (>= 5%)
    "SLGT": "#FFFF00",  # Slight    (>= 15%)
    "MDT": "#EE2C2C",   # Moderate  (>= 40%)
    "HIGH": "#FF00FF",  # High      (>= 70%)
}

DEFAULT_ERO_COLOR = "#C0C0C0"

# Leading word of a Placemark <name> -> canonical category code.
ERO_NAME_CATEGORY: dict[str, str] = {
    "marginal": "MRGL",
    "slight": "SLGT",
    "moderate": "MDT",
    "high": "HIGH",
}

ERO_CATEGORY_LABEL: dict[str, str] = {
    "MRGL": "Marginal",
    "SLGT": "Slight",
    "MDT": "Moderate",
    "HIGH": "High",
}

# Render/draw order (low -> high so the High risk paints on top).
ERO_CATEGORY_RANK: dict[str, int] = {
    "MRGL": 1,
    "SLGT": 2,
    "MDT": 3,
    "HIGH": 4,
}

ERO_DAYS = (1, 2, 3, 4, 5)
ERO_DISCUSSION_URL = (
    f"{WPC_BASE_URL}/discussions/hpcdiscussions.php?disc=qpferd"
)
WINTER_DISCUSSION_URL = (
    f"{WPC_BASE_URL}/discussions/hpcdiscussions.php?disc=qpfhsd"
)


def _ero_product(day: int) -> dict:
    return {
        "id": f"ero_day{day}",
        "group": "ero",
        "day": day,
        "label": f"Excessive Rainfall Outlook — Day {day}",
        "url": f"{WPC_BASE_URL}/kml/ero/Day_{day}_Excessive_Rainfall_Outlook.kmz",
        "format": "kmz",
        "cache_path": f"ero/day{day}.geojson",
        "seasonal": False,
        "empty_message": (
            f"WPC Day {day} Excessive Rainfall Outlook: "
            "The probability of rainfall exceeding flash flood guidance is less than 5%."
        ),
    }


QPF_DAYS = tuple(range(1, 8))


def _qpf_product(
    product_id: str,
    label: str,
    filename: str,
    days: tuple[int, ...],
) -> dict:
    return {
        "id": product_id,
        "group": "qpf",
        "days": days,
        "label": label,
        "url": f"{WPC_BASE_URL}/kml/qpf/{filename}",
        "format": "kmz",
        "cache_path": f"qpf/{product_id}.geojson",
        "seasonal": False,
    }


QPF_PRODUCTS = (
    *(
        _qpf_product(
            f"qpf24_day{day}",
            f"24-hour QPF — Day {day}",
            f"QPF24hr_Day{day}_latest.kmz",
            (day,),
        )
        for day in ERO_DAYS
    ),
    *(
        _qpf_product(
            f"qpf6_f{start:02d}_f{start + 6:02d}",
            f"6-hour QPF — F{start:02d}–F{start + 6:02d}",
            f"QPF6hr_f{start:02d}-f{start + 6:02d}_latest.kmz",
            (((start - 6) // 24) + 1,),
        )
        for start in range(6, 78, 6)
    ),
    _qpf_product(
        "qpf48_day1_2",
        "48-hour QPF — Days 1–2",
        "QPF48hr_Day1-2_latest.kmz",
        (1, 2),
    ),
    _qpf_product(
        "qpf72_day1_3",
        "72-hour QPF — Days 1–3",
        "QPF72hr_Day1-3_latest.kmz",
        (1, 2, 3),
    ),
    _qpf_product(
        "qpf48_day4_5",
        "48-hour QPF — Days 4–5",
        "QPF48hr_Day4-5_latest.kmz",
        (4, 5),
    ),
    _qpf_product(
        "qpf48_day6_7",
        "48-hour QPF — Days 6–7",
        "QPF48hr_Day6-7_latest.kmz",
        (6, 7),
    ),
    _qpf_product(
        "qpf120_day1_5",
        "120-hour QPF — Days 1–5",
        "QPF120hr_Day1-5_latest.kmz",
        (1, 2, 3, 4, 5),
    ),
    _qpf_product(
        "qpf168_day1_7",
        "168-hour QPF — Days 1–7",
        "QPF168hr_Day1-7_latest.kmz",
        QPF_DAYS,
    ),
)

WINTER_DAYS = (1, 2, 3)
WINTER_PROBABILITY_COLORS: dict[int, str] = {
    10: "#00C5F1",
    40: "#008A00",
    70: "#FF0000",
}


def _winter_product(
    day: int,
    product_key: str,
    label: str,
    filename: str,
    empty_message: str,
) -> dict:
    product_id = f"winter_{product_key}_day{day}"
    return {
        "id": product_id,
        "group": "winter",
        "days": (day,),
        "label": f"{label} — Day {day}",
        "url": f"{WPC_BASE_URL}/kml/winwx/{filename}",
        "format": "kml",
        "cache_path": f"winter/{product_id}.geojson",
        "seasonal": False,
        "empty_message": empty_message,
    }


WINTER_PRODUCTS = tuple(
    product
    for day in WINTER_DAYS
    for product in (
        _winter_product(
            day,
            "snow4",
            'Probability of Snow > 4"',
            f"Day{day}_psnow_gt_04inches_latest.kml",
            (
                f"The probability of receiving at least 4 inches of snow on Day {day} "
                "over the Continental U.S. is less than 10%."
            ),
        ),
        _winter_product(
            day,
            "snow8",
            'Probability of Snow > 8"',
            f"Day{day}_psnow_gt_08inches_latest.kml",
            (
                f"The probability of receiving at least 8 inches of snow on Day {day} "
                "over the Continental U.S. is less than 10%."
            ),
        ),
        _winter_product(
            day,
            "snow12",
            'Probability of Snow > 12"',
            f"Day{day}_psnow_gt_12inches_latest.kml",
            (
                f"The probability of receiving at least 12 inches of snow on Day {day} "
                "over the Continental U.S. is less than 10%."
            ),
        ),
        _winter_product(
            day,
            "ice025",
            'Probability of Ice > 0.25"',
            f"Day{day}_picez_gt_.25inch_latest.kml",
            (
                "The probability of receiving at least 0.25 inch of freezing rain "
                f"on Day {day} over the Continental U.S. is less than 10%."
            ),
        ),
    )
)

FOP_COLORS: dict[str, str] = {
    "POSSIBLE": "#FFFF00",
    "LIKELY": "#FFAA00",
    "OCCURRING": "#E60000",
}

FOP_PRODUCT = {
    "id": "fop_5day",
    "group": "fop",
    "days": (1,),
    "label": "5-Day River Flood Outlook",
    "url": f"{WPC_BASE_URL}/kml/fop/fop_v2.kmz",
    "format": "kmz",
    "cache_path": "fop/fop_5day.geojson",
    "seasonal": False,
    "empty_message": "No river flooding is forecast during the next five days.",
}

MPD_COLORS: dict[str, str] = {
    "LIKELY": "#E60000",
    "POSSIBLE": "#F59E0B",
    "UNLIKELY": "#64748B",
}

MPD_PRODUCT = {
    "id": "mpd_active",
    "group": "mpd",
    "days": (1,),
    "label": "Active Mesoscale Precipitation Discussions",
    "url": f"{WPC_BASE_URL}/metwatch/metwatch_mpd.php",
    "kml_base_url": f"{WPC_BASE_URL}/kml/mpd",
    "format": "mpd_index",
    "cache_path": "mpd/active.geojson",
    "seasonal": False,
    "empty_message": "There are no active WPC Mesoscale Precipitation Discussions.",
}

SURFACE_BOUNDS = {
    "north": 58.79,
    "south": 14.88,
    "east": -64.06,
    "west": -130.08,
}


def _surface_png_product(
    product_id: str,
    label: str,
    filename: str,
    forecast_hour: int | None,
) -> dict:
    return {
        "id": product_id,
        "group": "surface",
        "days": (1,),
        "label": label,
        "url": f"{WPC_BASE_URL}/kml/conus_png/{filename}",
        "format": "png",
        "cache_path": f"surface/{product_id}.json",
        "bounds": SURFACE_BOUNDS,
        "forecast_hour": forecast_hour,
        "seasonal": False,
    }


SURFACE_ANALYSIS_PRODUCTS = (
    _surface_png_product(
        "surface_analysis_latest",
        "Latest Surface Analysis",
        "conussfc_trans_latest.png",
        None,
    ),
)

SURFACE_FORECAST_PRODUCTS = (
    *(
        _surface_png_product(
            f"surface_forecast_f{hour:02d}",
            f"Surface Front Forecast — F{hour:02d}",
            f"{code}f_trans_CED.png",
            hour,
        )
        for hour, code in (
            (6, 91),
            (12, 92),
            (18, 93),
            (24, 94),
            (30, 95),
            (36, 96),
            (48, 98),
            (60, 99),
        )
    ),
)

SURFACE_PRODUCTS = SURFACE_ANALYSIS_PRODUCTS

SIGWX_COLORS: dict[str, str] = {
    "flooding": "#FF0000",
    "severe": "#FFFF00",
    "zr": "#FF00FF",
    "snow": "#FFFFFF",
}

SIGWX_CATEGORY_LABEL: dict[str, str] = {
    "flooding": "Flash Flooding",
    "severe": "Severe Thunderstorms",
    "zr": "Freezing Rain",
    "snow": "Heavy Snowfall",
}

SIGWX_CATEGORY_RANK: dict[str, int] = {
    "snow": 1,
    "zr": 2,
    "severe": 3,
    "flooding": 4,
}

SIGWX_EMPTY_MESSAGE = "No areas of significant weather are expected."


def _sigwx_product(product_id: str, label: str, filename: str, days: tuple[int, ...]) -> dict:
    return {
        "id": product_id,
        "group": "sigwx",
        "days": days,
        "label": label,
        "url": f"{WPC_BASE_URL}/kml/noaa_chart/{filename}",
        "format": "kml",
        "cache_path": f"sigwx/{product_id}.geojson",
        "seasonal": False,
        "empty_message": SIGWX_EMPTY_MESSAGE,
    }


SIGWX_PRODUCTS = (
    _sigwx_product("sigwx_day1", "Day 1 Significant Weather", "WPC_Day1_SigWx_latest.kml", (1,)),
    _sigwx_product("sigwx_day2", "Day 2 Significant Weather", "WPC_Day2_SigWx_latest.kml", (2,)),
    _sigwx_product("sigwx_day3", "Day 3 Significant Weather", "WPC_Day3_SigWx_latest.kml", (3,)),
    _sigwx_product("sigwx_day1_3", "Days 1–3 Significant Weather", "WPC_Day1-3_SigWx_latest.kml", (1, 2, 3)),
)

WPC_PRODUCTS: dict[str, tuple[dict, ...]] = {
    "ero": tuple(_ero_product(day) for day in ERO_DAYS),
    "qpf": QPF_PRODUCTS,
    "winter": WINTER_PRODUCTS,
    "fop": (FOP_PRODUCT,),
    "mpd": (MPD_PRODUCT,),
    "sigwx": SIGWX_PRODUCTS,
    "surface": SURFACE_PRODUCTS,
    "forecast": SURFACE_FORECAST_PRODUCTS,
}


def qpf_threshold_from_name(name: str) -> float | None:
    """Parse the accumulation bin from a QPF Placemark <name> ('QPF 0.50 inches')."""
    import re

    match = re.search(r"(\d+(?:\.\d+)?)", name or "")
    return float(match.group(1)) if match else None


def get_product(group: str, day: int, product_id: str | None = None) -> dict | None:
    """Return the selected product, with a group-appropriate default."""
    group_key = (group or "").strip().lower()
    entries = WPC_PRODUCTS.get(group_key, ())
    requested_id = (product_id or "").strip().lower()
    if requested_id:
        return next(
            (entry for entry in entries if entry["id"] == requested_id),
            None,
        )
    default_ids = {
        "ero": f"ero_day{day}",
        "qpf": f"qpf24_day{day}",
        "winter": f"winter_snow4_day{day}",
        "fop": "fop_5day",
        "mpd": "mpd_active",
        "sigwx": "sigwx_day1",
        "surface": "surface_analysis_latest",
        "forecast": "surface_forecast_f06",
    }
    default_id = default_ids.get(group_key, "")
    return next((entry for entry in entries if entry["id"] == default_id), None)


def ero_category_from_name(name: str) -> str:
    """Map a Placemark <name> ('Marginal (At Least 5%)') to a category code.

    Returns the canonical code (MRGL/SLGT/MDT/HIGH) or '' when unrecognized.
    """
    tokens = (name or "").strip().split()
    if not tokens:
        return ""
    return ERO_NAME_CATEGORY.get(tokens[0].lower(), "")
