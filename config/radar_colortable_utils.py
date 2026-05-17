"""
Parser and colormap builder for GRS-style .pal colortable files.

Produces:
  - matplotlib LinearSegmentedColormap for use in workers/radar_live_worker.py
  - legend JSON (list of {value, label, color} dicts) for the frontend legend endpoint

.pal format reference: https://github.com/swemmerson/colortables
"""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib.colors as mcolors

_COLORTABLE_DIR = Path(__file__).parent / "radar_colortables"

# Map product key → .pal filename (without the directory path)
_PAL_FILENAMES: dict[str, str] = {
    "BR": "RadarScope_BR.pal",
    "BV": "BV_grl3v2.pal",
}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _parse_pal(path: Path) -> dict:
    """Parse a .pal file into a structured dict.

    Returns:
        {
            "product": str,
            "units": str,          # "DBZ", "KTS", etc.
            "step": float | None,
            "scale": float,        # unit conversion factor (e.g. m/s → kts)
            "color_entries": [{"value": float, "c1": (R,G,B), "c2": (R,G,B)}, ...],
            "nd": (R,G,B) | None,  # no-data color
            "rf": (R,G,B) | None,  # range-folded color
        }
    """
    meta: dict = {
        "product": "",
        "units": "",
        "step": None,
        "scale": 1.0,
        "color_entries": [],
        "nd": None,
        "rf": None,
    }

    raw_lines: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        # Strip inline comments
        line = raw.split(";")[0].strip()
        if line:
            raw_lines.append(line)

    # Re-join lines that were soft-wrapped (continuation lines start with a
    # digit or sign and do NOT start with a keyword).
    _keywords = re.compile(
        r"^(color|nd|rf|product|units|step|scale):?\b", re.I)
    joined: list[str] = []
    for line in raw_lines:
        if joined and not _keywords.match(line):
            joined[-1] += " " + line
        else:
            joined.append(line)

    for line in joined:
        parts = line.split()
        if not parts:
            continue
        key = parts[0].rstrip(":").upper()
        rest = parts[1:]

        if key == "PRODUCT":
            meta["product"] = " ".join(rest)
        elif key == "UNITS":
            meta["units"] = " ".join(rest).upper().strip()
        elif key == "STEP" and rest:
            try:
                meta["step"] = float(rest[0])
            except ValueError:
                pass
        elif key == "SCALE" and rest:
            try:
                meta["scale"] = float(rest[0])
            except ValueError:
                pass
        elif key == "ND":
            nums = _extract_ints(rest, count=3)
            if nums:
                meta["nd"] = tuple(nums)
        elif key == "RF":
            nums = _extract_ints(rest, count=3)
            if nums:
                meta["rf"] = tuple(nums)
        elif key == "COLOR" and rest:
            entry = _parse_color_entry(rest)
            if entry is not None:
                meta["color_entries"].append(entry)

    # Sort ascending by value so colormap building is straightforward.
    meta["color_entries"].sort(key=lambda e: e["value"])
    return meta


def _extract_ints(tokens: list[str], count: int) -> list[int] | None:
    nums = []
    for t in tokens:
        try:
            nums.append(int(float(t)))
        except ValueError:
            pass
        if len(nums) == count:
            return nums
    return nums if len(nums) == count else None


def _parse_color_entry(rest: list[str]) -> dict | None:
    """Parse the value + 3 or 6 RGB integers from a Color: line."""
    nums: list[float] = []
    for t in rest:
        try:
            nums.append(float(t))
        except ValueError:
            pass
    if len(nums) < 4:
        return None
    value = nums[0]
    rgb_vals = [int(v) for v in nums[1:]]
    if len(rgb_vals) >= 6:
        c1 = (rgb_vals[0], rgb_vals[1], rgb_vals[2])
        c2 = (rgb_vals[3], rgb_vals[4], rgb_vals[5])
    else:
        c1 = (rgb_vals[0], rgb_vals[1], rgb_vals[2])
        c2 = c1
    return {"value": value, "c1": c1, "c2": c2}


# ---------------------------------------------------------------------------
# Colormap builder
# ---------------------------------------------------------------------------


def _build_colormap(
    parsed: dict,
    vmin: float,
    vmax: float,
    name: str,
) -> mcolors.LinearSegmentedColormap:
    """Build a matplotlib LinearSegmentedColormap from parsed .pal entries."""
    entries = parsed["color_entries"]
    if not entries:
        raise ValueError(f"No color entries found for colormap '{name}'")

    span = float(vmax - vmin)
    points: list[tuple[float, tuple]] = []

    for i, entry in enumerate(entries):
        v = float(entry["value"])
        norm_v = min(max((v - vmin) / span, 0.0), 1.0)
        c1 = tuple(ch / 255.0 for ch in entry["c1"])
        c2 = tuple(ch / 255.0 for ch in entry["c2"])

        # Avoid duplicate positions
        if not points or abs(norm_v - points[-1][0]) > 1e-6:
            points.append((norm_v, c1))

        # Two-color entries interpolate across the band
        if entry["c1"] != entry["c2"]:
            if i + 1 < len(entries):
                next_v = float(entries[i + 1]["value"])
                next_norm = min(max((next_v - vmin) / span, 0.0), 1.0)
                # Place c2 just before the next breakpoint
                insert_norm = norm_v + (next_norm - norm_v) * 0.85
                points.append((min(insert_norm, next_norm - 1e-5), c2))
            else:
                points.append((min(norm_v + 0.01, 1.0), c2))

    # Ensure the colormap spans [0, 1]
    if points[0][0] > 0.0:
        points.insert(0, (0.0, points[0][1]))
    if points[-1][0] < 1.0:
        points.append((1.0, points[-1][1]))

    return mcolors.LinearSegmentedColormap.from_list(name, points, N=512)


# ---------------------------------------------------------------------------
# Legend JSON builder
# ---------------------------------------------------------------------------


def _color_hex(rgba) -> str:
    r, g, b = int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255)
    return f"#{r:02x}{g:02x}{b:02x}"


def _build_legend(
    parsed: dict,
    cmap: mcolors.LinearSegmentedColormap,
    vmin: float,
    vmax: float,
    n_ticks: int = 11,
) -> list[dict]:
    """Return a list of {value, label, color} dicts for the frontend legend."""
    span = float(vmax - vmin)
    units = parsed.get("units", "")
    entries = []
    for i in range(n_ticks):
        v = vmin + (span * i / (n_ticks - 1))
        norm_v = i / (n_ticks - 1)
        color = _color_hex(cmap(norm_v))
        if units in ("DBZ",):
            label = f"{v:.0f}"
        elif units in ("KTS",):
            label = f"{v:.0f}"
        else:
            label = f"{v:.1f}"
        entries.append({"value": round(v, 2), "label": label, "color": color})
    return entries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Module-level cache: (pal_key, vmin, vmax) → result dict
_CACHE: dict[str, dict] = {}


def get_radar_colortable(
    pal_key: str,  # e.g. "BR" or "BV" — maps to samBR.pal / samVEL.pal
    vmin: float,
    vmax: float,
) -> dict:
    """Return (and cache) the full colortable result for a product.

    Returns:
        {
            "cmap": LinearSegmentedColormap,
            "vmin": float,
            "vmax": float,
            "units": str,
            "legend": [{"value", "label", "color"}, ...]
        }
    """
    cache_key = f"{pal_key}_{vmin}_{vmax}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    pal_filename = _PAL_FILENAMES.get(pal_key)
    if not pal_filename:
        raise FileNotFoundError(
            f"No .pal filename mapping for product key: {pal_key!r}"
        )
    pal_path = _COLORTABLE_DIR / pal_filename
    if not pal_path.exists():
        raise FileNotFoundError(f"Colortable not found: {pal_path}")

    parsed = _parse_pal(pal_path)
    cmap = _build_colormap(parsed, vmin, vmax, name=f"GRS_{pal_key}")
    cmap.set_bad((0, 0, 0, 0))
    cmap.set_under((0, 0, 0, 0))
    legend = _build_legend(parsed, cmap, vmin, vmax)

    result = {
        "cmap": cmap,
        "vmin": vmin,
        "vmax": vmax,
        "units": parsed.get("units", ""),
        "legend": legend,
    }
    _CACHE[cache_key] = result
    return result


def get_legend_json(pal_key: str, vmin: float, vmax: float) -> list[dict]:
    """Return just the JSON-serializable legend list (no cmap object)."""
    ct = get_radar_colortable(pal_key, vmin, vmax)
    return [
        {"value": e["value"], "label": e["label"], "color": e["color"]}
        for e in ct["legend"]
    ]
