import os
import json
import cartopy.crs as ccrs
import matplotlib.patheffects as PathEffects

# ── Module-level constants ───────────────────────────────────────────────────

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")

# In-process cache so the same file is only read once.
_CITIES_CACHE = {}


# ═════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═════════════════════════════════════════════════════════════════════════════


def load_cities(filename="us-cities.json"):
    """Load and normalise city data from a JSON file in ``data/``.

    Supports two formats:

    * **dict** — ``{"CityName": [lat, lon]}`` or ``{"CityName": [lat, lon, align]}
    * **list** — ``[{"city": "Name", "latitude": ..., "longitude": ..., "rank": ...}, ...]``

    Returns:
        list[dict]: Normalised list sorted by *rank* (ascending).
    """
    cities_path = os.path.join(_DATA_DIR, filename)

    # Fallback to us-cities.json if the requested file doesn't exist
    if not os.path.exists(cities_path) and filename != "us-cities.json":
        print(f"[WARN] {filename} not found, falling back to us-cities.json")
        cities_path = os.path.join(_DATA_DIR, "us-cities.json")

    cached = _CITIES_CACHE.get(cities_path)
    if cached is not None:
        return cached

    try:
        with open(cities_path, "r") as f:
            raw_data = json.load(f)
    except Exception as e:
        print(f"[WARN] Could not load city data from {filename}: {e}")
        return []

    cities = []
    if isinstance(raw_data, dict):
        for name, props in raw_data.items():
            if isinstance(props, (list, tuple)) and len(props) >= 2:
                cities.append(
                    {
                        "city": name,
                        "latitude": float(props[0]),
                        "longitude": float(props[1]),
                        "align": props[2] if len(props) > 2 else "left",
                        "rank": 1,
                    }
                )
    elif isinstance(raw_data, list):
        cities = raw_data
    else:
        print(f"[WARN] Unknown city data format in {filename}")
        return []

    def _city_priority(city):
        try:
            rank_val = float(city.get("rank"))
        except (TypeError, ValueError):
            rank_val = 9999.0
        return rank_val

    cities.sort(key=_city_priority)
    _CITIES_CACHE[cities_path] = cities
    return cities


def filter_cities_by_density(cities, density=5):
    """Return a subset of *cities* based on a 1–10 density scale.

    Higher density → more cities shown.  Cities are selected by rank so the
    most important ones always appear first.
    """
    if not cities or density < 1:
        return cities
    if density >= 10:
        return cities

    ratio = density / 10.0
    num_to_show = max(1, int(len(cities) * ratio))

    def _city_priority(x):
        try:
            return float(x.get("rank"))
        except (ValueError, TypeError):
            return 9999

    sorted_cities = sorted(cities, key=_city_priority)
    return sorted_cities[:num_to_show]


# ═════════════════════════════════════════════════════════════════════════════
# PLOTTING
# ═════════════════════════════════════════════════════════════════════════════


def plot_cities(
    ax,
    extent_bounds,
    *,
    filename="us-cities.json",
    density_scale=1.0,
    collision_w_factor=0.05,
    collision_h_factor=0.02,
    font_size=12,
    z_cities=30,
    text_color="#ffffff",
    text_bg_color="#000000",
    text_bg_alpha=0.3,
    italic=True,
    stroke_width=2,
    collision_detect=True,
    style_config=None,
):
    """Plot city labels on a Cartopy axes.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        A ``GeoAxes`` with a Cartopy projection.
    extent_bounds : tuple
        ``(min_lon, max_lon, min_lat, max_lat)`` of the current viewport.
    filename : str
        JSON file in ``data/`` to load cities from.
    density_scale : float
        Multiplier on collision bounding-box size.  Larger → fewer labels.
    font_size : int
        Text size in points.
    z_cities : int
        Base zorder for labels.
    text_color, text_bg_color, text_bg_alpha :
        Visual styling for labels.
    italic : bool
        Whether to render city names in italic.
    stroke_width : float
        Width of the black stroke outline around label text.
    collision_detect : bool
        When *True*, skip labels that overlap previously-drawn ones.
    style_config : dict or None
        If provided, styling keys in the dict override the explicit kwargs
        above.  Recognised keys: ``cities_file``, ``city_density``,
        ``city_text_size``, ``city_collision_w``, ``city_collision_h``,
        ``city_text_color``, ``city_text_bg_color``, ``city_text_bg_alpha``.
    """
    # Allow style_config to override individual parameters
    if style_config:
        filename = style_config.get("cities_file", filename)
        city_density = int(style_config.get("city_density", 5))
        density_scale = city_density / 5.0
        collision_w_factor = float(
            style_config.get("city_collision_w", collision_w_factor)
        )
        collision_h_factor = float(
            style_config.get("city_collision_h", collision_h_factor)
        )
        font_size = int(style_config.get("city_text_size", font_size))
        text_color = style_config.get("city_text_color", text_color)
        text_bg_color = style_config.get("city_text_bg_color", text_bg_color)
        text_bg_alpha = float(style_config.get("city_text_bg_alpha", text_bg_alpha))

    cities = load_cities(filename)
    if not cities:
        return

    try:
        min_lon, max_lon, min_lat, max_lat = extent_bounds
    except (ValueError, TypeError):
        return

    map_width = max_lon - min_lon
    map_height = max_lat - min_lat
    text_w = map_width * collision_w_factor * density_scale
    text_h = map_height * collision_h_factor * density_scale

    drawn_bboxes = []

    for city_data in cities:
        city_name = city_data.get("city", city_data.get("name", ""))
        try:
            lat = float(city_data.get("latitude", city_data.get("lat")))
            lon = float(city_data.get("longitude", city_data.get("lon")))
        except (ValueError, TypeError):
            continue

        # Skip cities outside the visible extent (with a small buffer)
        if not (
            (min_lat - 0.1) <= lat <= (max_lat + 0.1)
            and (min_lon - 0.1) <= lon <= (max_lon + 0.1)
        ):
            continue

        if collision_detect:
            cand_x_min = lon - (text_w / 2.0)
            cand_x_max = lon + (text_w / 2.0)
            cand_y_min = lat - (text_h / 2.0)
            cand_y_max = lat + (text_h / 2.0)

            collision = False
            for bx_min, bx_max, by_min, by_max in drawn_bboxes:
                if (
                    cand_x_min < bx_max
                    and cand_x_max > bx_min
                    and cand_y_min < by_max
                    and cand_y_max > by_min
                ):
                    collision = True
                    break
            if collision:
                continue

        # Label text
        txt = ax.text(
            lon,
            lat,
            city_name.upper(),
            transform=ccrs.PlateCarree(),
            fontsize=font_size,
            color=text_color,
            fontname="Montserrat",
            fontweight="black",
            fontstyle="italic" if italic else "normal",
            ha="center",
            va="center",
            zorder=z_cities,
            alpha=0.95,
            bbox=dict(
                facecolor=text_bg_color,
                alpha=text_bg_alpha,
                edgecolor="none",
                boxstyle="round,pad=0.2",
            ),
            clip_on=True,
        )
        if stroke_width > 0:
            txt.set_path_effects(
                [PathEffects.withStroke(linewidth=stroke_width, foreground="black")]
            )

        if collision_detect:
            drawn_bboxes.append((cand_x_min, cand_x_max, cand_y_min, cand_y_max))
