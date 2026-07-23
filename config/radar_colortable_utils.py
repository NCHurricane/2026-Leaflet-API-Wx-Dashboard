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
    "BV": "BV.pal",
    "SRV": "SRV.pal",
    "CC": "CC.pal",
    "ZDR": "ZDR.pal",
    "KDP": "KDP.pal",
    "SW": "SW.pal",
    "PHI": "PHI.pal",
    "HCA": "HC.pal",
    "ET": "EET.pal",
    "VIL": "DVL.pal",
    "DPA": "DPR.pal",
    "DAA": "DAA.pal",          # L3_DAA One-Hour Accumulation (indexed levels)
    "STP": "STP.pal",          # L3_DTA Storm Total Accumulation (physical inches)
}

# Palettes whose .pal entry values do not share the product's config value
# scale -- either array indices (DPR/DAA) or a different-but-linear unit (SW is
# in m/s while the data is scaled to knots). Their colormaps are normalized
# across the palette's own min/max so the color sequence spans the full data
# range set by the product's config vmin/vmax.
_PAL_INDEXED: set[str] = {"DPA", "DAA", "SW"}

_GENERATED_UNITS: dict[str, str] = {
    "CC": "RATIO",
    "ZDR": "DB",
    "SW": "KTS",
    "KDP": "DEG/KM",
    "PHI": "DEG",
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
        r"^(color\d*|solidcolor\d*|nd|rf|product|units|step|scale):?\b", re.I)
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
        elif (key.startswith("COLOR") or key.startswith("SOLIDCOLOR")) and rest:
            # Color/SolidColor (RGB) and Color4/SolidColor4 (RGBA) all supported;
            # the trailing "4" signals a 4-channel format whose alpha is skipped.
            channels = 4 if key.endswith("4") else 3
            entry = _parse_color_entry(rest, channels)
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


def _parse_color_entry(rest: list[str], channels: int = 3) -> dict | None:
    """Parse a Color/SolidColor line into value + one or two RGB colors.

    ``channels`` is 3 for RGB or 4 for RGBA (Color4/SolidColor4); for RGBA the
    alpha component is skipped so only RGB is kept. Each color occupies
    ``channels`` components, so a two-color band has ``2 * channels`` of them.
    """
    nums: list[float] = []
    for t in rest:
        try:
            nums.append(float(t))
        except ValueError:
            pass
    if len(nums) < 1 + channels:
        return None
    value = nums[0]
    comps = [int(v) for v in nums[1:]]
    c1 = (comps[0], comps[1], comps[2])
    if len(comps) >= 2 * channels:
        c2 = (comps[channels], comps[channels + 1], comps[channels + 2])
    else:
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
    own_range: bool = False,
) -> mcolors.LinearSegmentedColormap:
    """Build a matplotlib LinearSegmentedColormap from parsed .pal entries.

    When ``own_range`` is True the colormap is normalized across the palette's
    own min/max value instead of (vmin, vmax). Use this for indexed palettes
    whose entry values are array indices, not physical units, so the color
    sequence spans the full data range at render time.
    """
    entries = parsed["color_entries"]
    if not entries:
        raise ValueError(f"No color entries found for colormap '{name}'")

    if own_range:
        entry_vals = [float(e["value"]) for e in entries]
        vmin = min(entry_vals)
        vmax = max(entry_vals)

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

    # matplotlib requires strictly increasing positions. Densely packed
    # two-color bands can collide at a position (e.g. a two-color top entry that
    # maps to 1.0 emits both colors there); keep the later color at a shared
    # position so the gradient stays monotonic.
    cleaned: list[tuple[float, tuple]] = []
    for pos, color in points:
        if cleaned and pos <= cleaned[-1][0]:
            cleaned[-1] = (cleaned[-1][0], color)
        else:
            cleaned.append((pos, color))

    return mcolors.LinearSegmentedColormap.from_list(name, cleaned, N=512)


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
    legend_vmin: float | None = None,
) -> list[dict]:
    """Return a list of {value, label, color} dicts for the frontend legend.

    ``legend_vmin`` clips the left edge of the legend (e.g. a dBZ floor) while
    the colormap normalization still uses the original ``vmin`` so colors are
    correct for their physical values.
    """
    eff_vmin = float(legend_vmin) if legend_vmin is not None else float(vmin)
    full_span = float(vmax - vmin)
    legend_span = float(vmax - eff_vmin)
    units = parsed.get("units", "")
    entries = []
    for i in range(n_ticks):
        v = eff_vmin + (legend_span * i / (n_ticks - 1))
        norm_v = (v - vmin) / full_span if full_span else 0.0
        norm_v = min(max(norm_v, 0.0), 1.0)
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
    pal_key: str,  # palette key (e.g. "BR", "BV") -> .pal file via _PAL_FILENAMES
    vmin: float,
    vmax: float,
    legend_vmin: float | None = None,
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
    cache_key = f"{pal_key}_{vmin}_{vmax}_{legend_vmin}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    pal_filename = _PAL_FILENAMES.get(pal_key)
    if pal_filename:
        pal_path = _COLORTABLE_DIR / pal_filename
        if not pal_path.exists():
            raise FileNotFoundError(f"Colortable not found: {pal_path}")
        parsed = _parse_pal(pal_path)
        cmap = _build_colormap(
            parsed,
            vmin,
            vmax,
            name=f"GRS_{pal_key}",
            own_range=pal_key in _PAL_INDEXED,
        )
    else:
        from radar.radar_colormaps import GRS_COLORMAPS

        factory = GRS_COLORMAPS.get(pal_key)
        if not factory:
            raise FileNotFoundError(
                f"No colortable mapping for product key: {pal_key!r}"
            )
        cmap = factory()
        parsed = {"units": _GENERATED_UNITS.get(pal_key, "")}
    cmap.set_bad((0, 0, 0, 0))
    cmap.set_under((0, 0, 0, 0))
    legend = _build_legend(parsed, cmap, vmin, vmax, legend_vmin=legend_vmin)

    result = {
        "cmap": cmap,
        "vmin": vmin,
        "vmax": vmax,
        "legend_vmin": legend_vmin,
        "units": parsed.get("units", ""),
        "legend": legend,
    }
    _CACHE[cache_key] = result
    return result


def get_legend_json(
    pal_key: str,
    vmin: float,
    vmax: float,
    legend_vmin: float | None = None,
) -> list[dict]:
    """Return just the JSON-serializable legend list (no cmap object)."""
    ct = get_radar_colortable(pal_key, vmin, vmax, legend_vmin=legend_vmin)
    return [
        {"value": e["value"], "label": e["label"], "color": e["color"]}
        for e in ct["legend"]
    ]
