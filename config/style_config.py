"""
Centralized style configuration for all weather dashboard workflows.

Each workflow has a FIXED_STYLE_CONFIG dict that defines the production
rendering defaults.  Values here are the single source of truth — utility
modules import the dict they need and merge any runtime overrides on top
via the corresponding resolve_*_style_config() helper.

Editing guide:
    • Adjust values in the dicts below to change the default look of any
      workflow's rendered output.
    • Keys use snake_case and match the names accepted by style_config
      query parameters on the API.
    • Do NOT add keys that are not consumed by the workflow's renderer.
"""

# ---------------------------------------------------------------------------
# Surface
# ---------------------------------------------------------------------------
SURFACE_FIXED_STYLE_CONFIG = {
    # Font (must also be defined in css/shared.css if changed)
    "font_family": "Montserrat",
    # Base map
    "land_color": "#5c5c5c",
    "ocean_color": "#152238",
    "coastline_width": 0.7,
    "coastline_color": "#303030",
    # Country borders
    "show_country": True,
    "country_border_width": 0.2,
    "country_border_color": "#000000",
    # State borders
    "show_states": True,
    "state_border_width": 0.5,
    "state_border_color": "#000000",
    # Counties
    "show_counties": False,
    "county_width": 0.5,
    "county_color": "#d3d3d3",
    # Highways
    "show_highways": False,
    "highway_color": "#888888",
    "highway_width": 0.8,
    "highway_opacity": 0.6,
    # Lakes
    "show_lakes": True,
    "lake_color": "#A0C8F0",
    "lake_outline_color": "#333333",
    "lake_outline_width": 0.5,
    # Rivers
    "show_rivers": False,
    "river_color": "#A0C8F0",
    "river_width": 0.5,
    # Cities
    "show_places": False,
    "cities_file": "us-cities.json",
    "city_density": 5,
    "city_text_size": 8,
    "city_text_color": "#d8e700",
    "city_text_bg_color": "#141414",
    "city_text_bg_alpha": 0.1,
    "city_collision_w": 0.05,
    "city_collision_h": 0.02,
    "city_font_weight": "black",
    "city_box_style": "round,pad=0.2",
    "city_halo_width": 1,
    "city_halo_color": "black",
    # Station/value dot rendering
    "dot_size": 30,
    "font_size": 14,
    "density_km": 35,
    "smooth_sigma": 5,
    # Selection border
    "sel_border_width": 0.5,
    "sel_border_color": "#d1d1d1",
    # Station Plot parameters
    "station_font_size": 8,
    "station_density_km": 30,
    "station_temp_color": "#D32F2F",
    "station_dewpoint_color": "#00796B",
    "station_mslp_color": "black",
    "station_visibility_color": "purple",
    "station_weather_color": "#1976D2",
    "station_wind_color": "#1976D2",
    "station_text_weight": "bold",
    "station_text_halo_width": 2,
    "station_text_halo_color": "white",
    "station_font_scale": 0.55,
    "station_spacing_factor": 1.2,
    "wind_barb_length": 5,
    # Wind arrows (Wind Speed parameter only)
    "wind_arrow_color": "black",
    "wind_arrow_scale": 25,
    "wind_arrow_width": 0.004,
    "wind_arrow_headwidth": 4,
    "wind_arrow_headlength": 5,
    "wind_arrow_offset": 0.01,
    # Scatter/value rendering
    "scatter_edge_color": "black",
    "scatter_edge_width": 0.5,
    "scatter_alpha": 0.8,
    "value_text_color": "white",
    "value_text_weight": "black",
    "value_text_halo_width": 2,
    "value_text_halo_color": "black",
    # Gradient/contour rendering
    "contour_fill_alpha": 0.55,
    "contour_label_size": 9,
    "contour_label_weight": "black",
    # Colorbar
    "cbar_size": 12,
    "cbar_title_size": 11,
    "cbar_left": 0.2,
    "cbar_bottom": 0.05,
    "cbar_width": 0.6,
    "cbar_height": 0.03,
    "cbar_tick_weight": "bold",
    # HUD
    "hud_left_size": 12,
    "hud_left_x": 0.03,
    "hud_left_y": 0.97,
    "hud_left_text_color": "#ffffff",
    "hud_left_bg_color": "#000000",
    "hud_left_edge_color": "#555555",
    "hud_left_alpha": 0.6,
    "hud_left_opacity": 0.6,
    "hud_right_size": 12,
    "hud_right_x": 0.97,
    "hud_right_y": 0.97,
    "hud_right_text_color": "#ffd700",
    "hud_right_bg_color": "#000000",
    "hud_right_edge_color": "#555555",
    "hud_right_alpha": 0.6,
    "hud_right_opacity": 0.6,
    "hud_box_style": "round,pad=0.5",
    "hud_line_spacing": 1.15,
    "hud_font_weight": "black",
    "hud_left_font_style": "italic",
    # Logo
    "logo_user_size": 0.08,
    "logo_user_x": 0.98,
    "logo_user_y": 0.01,
    # Figure layout margins (axes positioning fractions)
    "figure_left_margin": 0.02,
    "figure_right_margin": 0.02,
    "figure_top_margin": 0.02,
    "figure_bottom_margin_station": 0.20,
    "figure_bottom_margin_other": 0.12,
    "legend_pad": 0.02,
    # Map extent expansion
    "map_margin_top": 0,
    "map_margin_bottom": 0,
    "map_margin_left": 0,
    "map_margin_right": 0,
    # Z-orders
    "zorder_land": 0,
    "zorder_counties": 1,
    "zorder_water": 1,
    "zorder_gradient": 1,
    "zorder_contour_lines": 2,
    "zorder_highways": 2,
    "zorder_country_mask": 3,
    "zorder_borders": 4,
    "zorder_contour_labels": 10,
    "zorder_region_mask": 500,
    "zorder_state_border": 501,
    "zorder_cities": 502,
    "zorder_scatter": 505,
    "zorder_scatter_text": 510,
    "zorder_gradient_values": 1500,
    "zorder_hud": 2000,
    "zorder_logos": 2000,
}


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
ALERTS_FIXED_STYLE_CONFIG = {
    # Font (must also be defined in css/shared.css if changed)
    "font_family": "Montserrat",
    # Base map
    "land_color": "#5c5c5c",
    "ocean_color": "#152238",
    "coastline_width": 0.5,
    "coastline_color": "#303030",
    # Country borders
    "show_country": True,
    "country_width": 0.8,
    "country_color": "#000000",
    # State borders
    "show_states": False,
    "state_width": 0.5,
    "state_color": "#000000",
    # Counties
    "show_counties": False,
    "county_width": 0.2,
    "county_color": "#d3d3d3",
    # Highways
    "show_highways": False,
    "highway_color": "#888888",
    "highway_width": 0.8,
    "highway_opacity": 0.6,
    # Lakes
    "show_lakes": True,
    "lake_color": "#4774bd",
    "lake_outline_color": "#333333",
    "lake_outline_width": 0.5,
    # Rivers
    "show_rivers": False,
    "river_color": "#A0C8F0",
    "river_width": 0.5,
    # Cities
    "show_places": False,
    "cities_file": "us-cities.json",
    "city_density": 5,
    "city_text_size": 8,
    "city_text_color": "#d8e700",
    "city_text_bg_color": "#141414",
    "city_text_bg_alpha": 0.1,
    "city_collision_w": 0.05,
    "city_collision_h": 0.02,
    "city_font_weight": "black",
    "city_font_style": "italic",
    "city_box_style": "round,pad=0.2",
    "city_halo_width": 1.0,
    "city_halo_color": "black",
    "city_text_alpha": 0.95,
    # HUD
    "hud_left_size": 12,
    "hud_left_x": 0.03,
    "hud_left_y": 0.97,
    "hud_left_text_color": "#ffffff",
    "hud_left_bg_color": "#000000",
    "hud_left_edge_color": "#555555",
    "hud_left_alpha": 0.6,
    "hud_right_size": 12,
    "hud_right_x": 0.97,
    "hud_right_y": 0.97,
    "hud_right_text_color": "#ffd700",
    "hud_right_bg_color": "#000000",
    "hud_right_edge_color": "#555555",
    "hud_right_alpha": 0.6,
    "hud_left_box_style": "round,pad=0.5",
    "hud_right_box_style": "round,pad=0.4",
    "hud_line_spacing": 1.15,
    "hud_font_weight": "black",
    "hud_font_style": "italic",
    # Legend
    "legend_size": 13,
    "legend_cols": "auto",
    "legend_panel_height": 0.24,
    "legend_font_weight": "bold",
    "legend_title_color": "black",
    "legend_title_weight": "black",
    "legend_title_style": "italic",
    "legend_panel_bg_color": "white",
    "legend_panel_bg_alpha": 0.9,
    "legend_panel_edge_color": "none",
    "legend_rows_height_mult": 1.45,
    "legend_item_height_mult": 1.25,
    # No-alerts text
    "no_alerts_header_color": "#000000",
    "no_alerts_header_size_mult": 1.2,
    "no_alerts_text_color": "#ff0000",
    "no_alerts_text_size_mult": 1.25,
    # Projection
    "projection_mode": "auto",
    # Logo
    "logo_user_size": 0.08,
    "logo_user_x": 0.98,
    "logo_user_y": 0.01,
    # Selection border
    "sel_border_width": 1,
    "sel_border_color": "#d1d1d1",
    # Alert rendering
    "alert_line_width": 1.1,
    "alert_fill_alpha": 0.35,
    "alert_alpha": 0.35,
    "show_storm_alerts": True,
    "show_zone_alerts": True,
    # Figure layout margins
    "figure_bottom_margin": 0.18,
    "figure_top_margin": 0.02,
    "figure_left_margin": 0.02,
    "figure_right_margin": 0.02,
    # Z-orders
    "zorder_counties": 10,
    "zorder_region_mask": 20,
    "zorder_state_border": 21,
    "zorder_alerts": 30,
    "zorder_cities": 100,
    "zorder_logos": 150,
    "zorder_hud": 200,
    "zorder_legend": 1001,
}


# ---------------------------------------------------------------------------
# Radar
# ---------------------------------------------------------------------------
RADAR_FIXED_STYLE_CONFIG = {
    # Font — note: if changed, also define in CSS
    "font_family": "Montserrat",
    # Base map
    "land_color": "#5C5C5C",
    "ocean_color": "#152238",
    "map_bg_color": "#152238",
    # State borders
    "show_states": True,
    "state_color": "#ffffff",
    "state_width": 1.5,
    # Counties
    "show_counties": False,
    "county_width": 1.0,
    "county_color": "#000000",
    # Highways
    "show_highways": True,
    "highway_color": "#888888",
    "highway_width": 0.8,
    "highway_opacity": 0.6,
    # Lakes & Rivers
    "show_lakes": True,
    "lake_color": "#152238",
    "lake_outline_color": "#333333",
    "lake_outline_width": 0.5,
    "show_rivers": False,
    "river_color": "#152238",
    "river_width": 0.5,
    # Range rings
    "show_rings": True,
    "ring_color": "#ffffff",
    "ring_width": 1.0,
    "ring_alpha": 0.5,
    "ring_line_style": "--",
    # Alert overlays
    "show_alert_polygons": True,
    "radar_alert_width": 4.0,
    "radar_alert_alpha": 1.0,
    # Cities
    "cities_file": "us-cities.json",
    "city_density": 5,
    "city_text_size": 8,
    "city_text_color": "#ffffff",
    "city_text_bg_color": "#000000",
    "city_text_bg_alpha": 0.5,
    "city_collision_w": 0.05,
    "city_collision_h": 0.02,
    "city_font_weight": "black",
    "city_font_style": "italic",
    "city_box_style": "round,pad=0.2",
    "city_halo_width": 1.2,
    "city_halo_color": "black",
    "city_text_alpha": 0.95,
    # Footer / colorbar
    "footer_pixels": 120.0,
    "footer_bottom_pad_px": 22.0,
    "footer_bg_color": "#f2f2f2",
    "cbar_height_px": 28.0,
    "cbar_title_size": 11,
    "cbar_bg_color": "#f2f2f2",
    "cbar_outline_color": "#555555",
    "cbar_outline_width": 1.0,
    "cbar_tick_color": "#000000",
    "cbar_tick_labelsize": 10,
    "cbar_tick_pad": 3,
    "cbar_tick_width": 0.8,
    # HUD
    "hud_left_size": 10,
    "hud_left_x": 0.03,
    "hud_left_y": 0.97,
    "hud_left_text_color": "#ffffff",
    "hud_left_bg_color": "#000000",
    "hud_left_edge_color": "#555555",
    "hud_left_alpha": 0.7,
    "hud_right_size": 10,
    "hud_right_x": 0.97,
    "hud_right_y": 0.97,
    "hud_right_text_color": "#ffd700",
    "hud_right_bg_color": "#000000",
    "hud_right_edge_color": "#555555",
    "hud_right_alpha": 0.7,
    "hud_font_weight": "black",
    "hud_font_style": "italic",
    "hud_line_spacing": 1.15,
    "hud_left_box_style": "round,pad=0.5",
    "hud_right_box_style": "round,pad=0.4",
    # Legend panel (archive)
    "legend_panel_bg_color": "white",
    "legend_panel_edge_color": "none",
    "legend_panel_bg_alpha": 0.9,
    "cbar_bg_alpha": 0.9,
    "alert_legend_text_color": "#000000",
    "alert_legend_square_outline": "#333333",
    "alert_legend_font_weight": "bold",
    "alert_legend_font_style": "italic",
    # Logo
    "logo_user_size": 0.05,
    "logo_user_x": 0.98,
    "logo_user_y": 0.01,
    # Projection
    "radar_projection_mode": "local_aeqd",
    # Extent expansion (zero = no extra padding beyond range-ring coverage)
    "expand_top": 0.0,
    "expand_bottom": 0.0,
    "expand_left": 0.0,
    "expand_right": 0.0,
    # Figure margins (archive)
    "figure_bottom_margin": 0.10,
    "figure_top_margin": 0.0,
    "figure_left_margin": 0.0,
    "figure_right_margin": 0.0,
}


# ---------------------------------------------------------------------------
# MRMS
# ---------------------------------------------------------------------------
MRMS_FIXED_STYLE_CONFIG = {
    # Base map
    "land_color": "#5c5c5c",
    "ocean_color": "#152238",
    "coastline_width": 0.8,
    "coastline_color": "#000000",
    # Country borders
    "show_country": True,
    "country_width": 1.0,
    "country_color": "#ffffff",
    # State borders
    "show_states": True,
    "state_width": 0.5,
    "state_color": "#ffffff",
    # Counties
    "show_counties": False,
    "county_width": 0.3,
    "county_color": "#ffffff",
    # Selection border
    "sel_border_width": 0.5,
    "sel_border_color": "#d1d1d1",
    # Hydro and roads
    "show_highways": False,
    "show_lakes": True,
    "show_rivers": False,
    # Cities
    "cities_file": "us-cities.json",
    "city_density": 5,
    "city_text_size": 8,
    "city_text_color": "#d8e700",
    "city_text_bg_color": "#141414",
    "city_text_bg_alpha": 0.1,
    "city_collision_w": 0.05,
    "city_collision_h": 0.02,
    # HUD
    "hud_left_size": 12,
    "hud_left_x": 0.03,
    "hud_left_y": 0.97,
    "hud_left_text_color": "#ffffff",
    "hud_left_bg_color": "#000000",
    "hud_left_edge_color": "#555555",
    "hud_left_alpha": 0.6,
    "hud_right_size": 12,
    "hud_right_x": 0.97,
    "hud_right_y": 0.97,
    "hud_right_text_color": "#ffd700",
    "hud_right_bg_color": "#000000",
    "hud_right_edge_color": "#555555",
    "hud_right_alpha": 0.6,
    # Colorbar and logo
    "cbar_size": 12,
    "cbar_title_size": 11,
    "logo_user_size": 0.08,
    "logo_user_x": 0.98,
    "logo_user_y": 0.01,
    # Extent margins
    "map_margin_top": 0,
    "map_margin_bottom": 0,
    "map_margin_left": 0,
    "map_margin_right": 0,
}


# ---------------------------------------------------------------------------
# Satellite
# ---------------------------------------------------------------------------
SATELLITE_FIXED_STYLE_CONFIG = {
    # Font
    "font_family": "Montserrat",
    # Base map / canvas
    "land_color": "#5c5c5c",
    "ocean_color": "#152238",
    "map_bg_color": "#000000",
    "coastline_width": 0.8,
    "coastline_color": "#000000",
    # Country borders
    "show_country": True,
    "country_width": 0.5,
    "country_color": "#ffffff",
    # State borders
    "show_states": True,
    "state_width": 0.5,
    "state_color": "#ffffff",
    # Counties
    "show_counties": False,
    "county_width": 0.3,
    "county_linewidth": 0.3,
    "county_color": "#ffffff",
    # Highways
    "show_highways": False,
    "highway_color": "#888888",
    "highway_width": 0.8,
    "highway_opacity": 0.6,
    # Lakes & rivers
    "show_lakes": False,
    "lake_color": "#000000",
    "lake_outline_color": "#333333",
    "lake_outline_width": 0.5,
    "show_rivers": False,
    "river_color": "#000000",
    "river_width": 0.5,
    # Cities
    "show_places": False,
    "cities_file": "us-cities.json",
    "city_density": 5,
    "city_text_size": 8,
    "city_text_color": "#d8e700",
    "city_text_bg_color": "#141414",
    "city_text_bg_alpha": 0.1,
    "city_collision_w": 0.05,
    "city_collision_h": 0.02,
    "city_font_weight": "black",
    "city_font_style": "italic",
    "city_box_style": "round,pad=0.2",
    "city_halo_width": 1.2,
    "city_halo_color": "black",
    "city_text_alpha": 0.95,
    # Colorbar / legend
    "cbar_size": 0.75,
    "cbar_size_horizontal": 0.35,
    "cbar_fraction_horizontal": 0.045,
    "cbar_title_size": 14,
    "cbar_tick_labelsize": 10,
    "cbar_tick_color": "black",
    "cbar_tick_weight": "bold",
    "cbar_outline_color": "#555555",
    # HUD
    "hud_left_size": 10,
    "hud_left_x": 0.03,
    "hud_left_y": 0.97,
    "hud_left_text_color": "#ffffff",
    "hud_left_bg_color": "#000000",
    "hud_left_edge_color": "#555555",
    "hud_left_alpha": 0.7,
    "hud_right_size": 10,
    "hud_right_x": 0.97,
    "hud_right_y": 0.97,
    "hud_right_text_color": "#ffd700",
    "hud_right_bg_color": "#000000",
    "hud_right_edge_color": "#555555",
    "hud_right_alpha": 0.7,
    "hud_font_weight": "black",
    "hud_font_style": "italic",
    "hud_line_spacing": 1.15,
    "hud_left_box_style": "round,pad=0.5",
    "hud_right_box_style": "round,pad=0.4",
    # Logo
    "logo_path": "img/nchurricane_logo.png",
    "logo_user_size": 0.08,
    "logo_user_x": 0.98,
    "logo_user_y": 0.01,
    # Figure / extent layout
    "figure_left_margin": 0.0,
    "figure_right_margin": 0.0,
    "figure_top_margin": 0.0,
    "figure_bottom_margin": 0.0,
    "map_margin_top": 0,
    "map_margin_bottom": 0,
    "map_margin_left": 0,
    "map_margin_right": 0,
    # Night background
    "night_bg_source_pref": "auto",
    "night_bg_lon_offset": 0,
    "night_bg_lat_offset": 0,
    "night_bg_zoom": 1,
    # Z-orders
    "zorder_land": 0,
    "zorder_water": 0,
    "zorder_sat_image": 1,
    "zorder_counties": 14,
    "zorder_borders": 15,
    "zorder_cities": 30,
    "zorder_hud": 100,
    "zorder_logos": 100,
}


# ---------------------------------------------------------------------------
# Resolver helpers — merge runtime overrides on top of the fixed defaults.
# Each workflow's *_utils.py imports only the resolver it needs.
# ---------------------------------------------------------------------------

def resolve_surface_style_config(style_config=None):
    resolved = dict(SURFACE_FIXED_STYLE_CONFIG)
    if style_config:
        resolved.update(style_config)
    return resolved


def resolve_alerts_style_config(style_config=None):
    resolved = dict(ALERTS_FIXED_STYLE_CONFIG)
    if style_config:
        resolved.update(style_config)
    return resolved


def resolve_radar_style_config(style_config=None):
    resolved = dict(RADAR_FIXED_STYLE_CONFIG)
    if style_config:
        resolved.update(style_config)
    return resolved


def resolve_mrms_style_config(style_config=None):
    resolved = dict(MRMS_FIXED_STYLE_CONFIG)
    if style_config:
        resolved.update(style_config)
    return resolved


def resolve_satellite_style_config(style_config=None):
    resolved = dict(SATELLITE_FIXED_STYLE_CONFIG)
    if style_config:
        resolved.update(style_config)
    if "county_width" in resolved and "county_linewidth" not in resolved:
        resolved["county_linewidth"] = resolved["county_width"]
    elif "county_linewidth" in resolved and "county_width" not in resolved:
        resolved["county_width"] = resolved["county_linewidth"]
    return resolved


# ---------------------------------------------------------------------------
# SPC
# ---------------------------------------------------------------------------
SPC_FIXED_STYLE_CONFIG = {
    # Base map
    "land_color": "#5c5c5c",
    "ocean_color": "#152238",
    # Watches
    "watch_tornado_color": "#FFFF00",
    "watch_severe_color": "#FFA500",
    "watch_fill_alpha": 0.25,
    "watch_line_width": 1.5,
    # Mesoscale Discussions
    "md_edge_color": "#66CCFF",
    "md_fill_color_r": 0.4,
    "md_fill_color_g": 0.8,
    "md_fill_color_b": 1.0,
    "md_fill_alpha": 0.2,
    "md_line_width": 1.5,
    # Storm Reports
    "report_tornado_color": "#FF0000",
    "report_hail_color": "#00FF00",
    "report_wind_color": "#0088FF",
    "report_default_color": "#FFFFFF",
    "report_marker_size": 4,
    "report_alpha": 0.8,
    # Outlook polygons
    "outlook_fill_alpha": 0.45,
    "outlook_line_width": 1.0,
    # No-items text
    "no_items_font_size": 16,
    "no_items_color": "white",
    "no_items_bg_alpha": 0.6,
    # HUD
    "hud_right_size": 12,
    "hud_right_x": 0.97,
    "hud_right_y": 0.97,
    "hud_right_text_color": "#ffd700",
    "hud_right_bg_color": "#000000",
    "hud_right_edge_color": "#555555",
    "hud_right_alpha": 0.6,
}


def resolve_spc_style_config(style_config=None):
    resolved = dict(SPC_FIXED_STYLE_CONFIG)
    if style_config:
        resolved.update(style_config)
    return resolved


# ---------------------------------------------------------------------------
# Unified Weather — shared base + per-group merge
# ---------------------------------------------------------------------------
WEATHER_FIXED_STYLE_CONFIG = {
    "font_family": "Montserrat",
    "land_color": "#5c5c5c",
    "ocean_color": "#152238",
    "hud_right_size": 12,
    "hud_right_x": 0.97,
    "hud_right_y": 0.97,
    "hud_right_text_color": "#ffd700",
    "hud_right_bg_color": "#000000",
    "hud_right_edge_color": "#555555",
    "hud_right_alpha": 0.6,
}

_WEATHER_GROUP_CONFIGS = {
    "surface": SURFACE_FIXED_STYLE_CONFIG,
    "alerts": ALERTS_FIXED_STYLE_CONFIG,
    "mrms": MRMS_FIXED_STYLE_CONFIG,
    "spc": SPC_FIXED_STYLE_CONFIG,
}


def resolve_weather_style_config(style_config=None):
    resolved = dict(WEATHER_FIXED_STYLE_CONFIG)
    if style_config:
        resolved.update(style_config)
    return resolved


def resolve_weather_group_style_config(product_group, style_config=None):
    """Merge WEATHER base -> per-group defaults -> user overrides."""
    resolved = dict(WEATHER_FIXED_STYLE_CONFIG)
    group_cfg = _WEATHER_GROUP_CONFIGS.get((product_group or "").lower())
    if group_cfg:
        resolved.update(group_cfg)
    if style_config:
        resolved.update(style_config)
    return resolved
