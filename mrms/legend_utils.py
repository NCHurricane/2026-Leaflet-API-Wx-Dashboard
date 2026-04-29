from __future__ import annotations

import math

import matplotlib.colors as mcolors
import numpy as np

from config.mrms_config import MRMS_COLORMAPS, MRMS_PRODUCTS


def _nws_hail_size_reference(size_in: float) -> str:
    size_in = float(size_in)
    if not np.isfinite(size_in) or size_in <= 0:
        return "Unknown"

    refs = [
        (0.25, "Pea"),
        (0.50, "Mothball/Peanut"),
        (0.75, "Penny"),
        (0.875, "Nickel"),
        (1.00, "Quarter"),
        (1.25, "Half Dollar"),
        (1.50, "Ping Pong Ball"),
        (1.75, "Golf Ball"),
        (2.00, "Hen Egg"),
        (2.50, "Tennis Ball"),
        (2.75, "Baseball"),
        (3.00, "Large Apple"),
        (4.00, "Softball"),
        (4.50, "Grapefruit"),
    ]

    if size_in > 4.5:
        return "Greater than Grapefruit"

    return min(refs, key=lambda item: abs(item[0] - size_in))[1]


def _rotation_intensity_label(value: float) -> str:
    if value >= 10:
        return "Extreme"
    if value >= 8:
        return "Very Strong"
    if value >= 6:
        return "Strong"
    if value >= 4:
        return "Moderate"
    if value >= 2:
        return "Weak"
    if value > 0:
        return "Minimal"
    return "None"


def _rotation_ticks(vmin: float, vmax: float) -> tuple[list[float], list[str]]:
    ticks = np.array([0, 2, 4, 6, 8, 10], dtype=float)
    mask = (ticks >= float(vmin)) & (ticks <= float(vmax))
    ticks = ticks[mask]
    labels_map = {
        0: "0 None",
        2: "2 Weak",
        4: "4 Mod",
        6: "6 Strong",
        8: "8 V.Strong",
        10: "10 Extreme",
    }
    return ticks.tolist(), [labels_map.get(int(t), f"{t:g}") for t in ticks]


def _display_unit(units: str) -> str:
    if units == "mm":
        return "in"
    if units == "mm/hr":
        return "in/hr"
    if units == "°C":
        return "°F"
    return units


def _convert_value(value: float, units: str) -> float:
    if units in {"mm", "mm/hr"}:
        return float(value) / 25.4
    if units == "°C":
        return _c_to_f(float(value))
    return float(value)


def _c_to_f(value_c: float) -> float:
    return (float(value_c) * 9.0 / 5.0) + 32.0


def _format_number(value: float) -> str:
    value = float(value)
    if not math.isfinite(value):
        return "--"
    abs_value = abs(value)
    if 0 < abs_value < 0.01:
        return f"{value:.3f}".rstrip("0").rstrip(".")
    if abs_value < 0.1:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    if abs_value >= 100:
        return f"{value:.0f}"
    if abs_value >= 10:
        return f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _color_hex(color) -> str:
    return mcolors.to_hex(color, keep_alpha=False)


def _resolve_cmap_and_norm(product_info: dict):
    cmap_key = product_info.get("colormap", "precip_rate")
    vmin = float(product_info.get("vmin", 0))
    vmax = float(product_info.get("vmax", 100))
    cmap_obj = MRMS_COLORMAPS.get(cmap_key)
    if isinstance(cmap_obj, tuple):
        cmap = cmap_obj[0]
        norm = (
            cmap_obj[1]
            if len(cmap_obj) > 1
            else mcolors.Normalize(vmin=vmin, vmax=vmax)
        )
    elif cmap_obj is not None:
        cmap = cmap_obj
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    else:
        cmap = mcolors.ListedColormap(["#808080"], name="fallback")
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    return cmap, norm


def get_mrms_valid_floor(product_info: dict) -> float:
    levels = np.asarray(product_info.get("levels", []), dtype=float)
    levels = levels[np.isfinite(levels)]
    if levels.size:
        return float(np.min(levels))
    return float(product_info.get("vmin", 0))


def mask_mrms_data(data, product_info: dict) -> np.ndarray:
    arr = np.asarray(data, dtype=float)
    invalid = ~np.isfinite(arr)
    missing_value = product_info.get("missing_value")
    no_coverage = product_info.get("no_coverage")
    if missing_value is not None:
        invalid |= arr == float(missing_value)
    if no_coverage is not None:
        invalid |= arr == float(no_coverage)
    invalid |= arr < get_mrms_valid_floor(product_info)
    return np.where(invalid, np.nan, arr)


def build_mrms_legend(product: str) -> dict:
    product_info = MRMS_PRODUCTS[product]
    cmap, norm = _resolve_cmap_and_norm(product_info)
    units = product_info.get("units", "")
    legend = {
        "kind": "categorical" if product_info.get("categorical") else "scale",
        "title": product_info.get("full_name", product),
        "display_units": _display_unit(units),
    }

    if product_info.get("categorical"):
        items = []
        categories = product_info.get("categories", {})
        columns = 3 if product == "PrecipFlag" else 2
        for raw_value in product_info.get("levels", []):
            color = _color_hex(cmap(norm(raw_value)))
            items.append(
                {
                    "value": int(raw_value),
                    "label": categories.get(int(raw_value), str(raw_value)),
                    "color": color,
                }
            )
        legend["items"] = items
        legend["columns"] = columns
        return legend

    ticks = []
    labels = None
    if product.startswith("RotationTrack"):
        ticks, labels = _rotation_ticks(
            float(product_info.get("vmin", 0)),
            float(product_info.get("vmax", 100)),
        )
    else:
        raw_levels = np.asarray(product_info.get("levels", []), dtype=float)
        raw_levels = raw_levels[np.isfinite(raw_levels)]
        ticks = raw_levels.tolist()

    scale = []
    for index, raw_value in enumerate(ticks):
        converted = _convert_value(raw_value, units)
        if labels:
            label = labels[index]
        elif product.startswith("AzShear"):
            label = f"{float(raw_value):.3f}"
        else:
            label = _format_number(converted)
        scale.append(
            {
                "raw_value": float(raw_value),
                "value": converted,
                "label": label,
                "color": _color_hex(cmap(norm(raw_value))),
            }
        )
    legend["scale"] = scale
    return legend


def build_mrms_overlay_meta(product: str, data) -> dict:
    product_info = MRMS_PRODUCTS[product]
    masked = mask_mrms_data(data, product_info)
    meta = {"legend": build_mrms_legend(product)}

    valid = masked[np.isfinite(masked)]
    if valid.size == 0:
        return meta

    if product.startswith("MESH"):
        max_mm = float(np.nanmax(valid))
        max_in = max_mm / 25.4
        hail_label = _nws_hail_size_reference(max_in)
        meta["legend"]["stat"] = {
            "label": "Largest Hail",
            "text": f"{_format_number(max_in)} in ({hail_label})",
            "raw_value": max_mm,
            "value": max_in,
        }
    elif product.startswith("RotationTrack"):
        max_intensity = float(np.nanmax(valid))
        units = product_info.get("units", "")
        meta["legend"]["stat"] = {
            "label": "Max Intensity",
            "text": f"{_format_number(max_intensity)} {units} ({_rotation_intensity_label(max_intensity)})".strip(),
            "raw_value": max_intensity,
            "value": max_intensity,
        }

    return meta
