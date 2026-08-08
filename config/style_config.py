"""Retained style defaults for the Radar and MRMS render contracts."""

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
