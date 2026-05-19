# Workflow Context

This file is a compact AI-oriented summary of the repository.

Total indexed files: 176

## Most Common Imports

- os (83)
- __future__ (77)
- time (71)
- datetime (70)
- argparse (62)
- json (59)
- numpy (57)
- workers._freshness (41)
- pathlib (40)
- matplotlib.pyplot (39)
- matplotlib (37)
- typing (34)
- matplotlib.colors (31)
- cartopy.crs (29)
- sys (27)
- config.satellite_v2_config (25)
- font_utils (25)
- re (25)
- cartopy.feature (24)
- config.geo_config (23)
- shutil (22)
- requests (21)
- math (21)
- urllib.parse (21)
- dateutil (20)

## Likely Important Files

### main.py
- Score: 356
- Imports: 66
- Functions: 135
- Classes: 0
- Key Functions:
  - _initialize_modules
    Calls: time, time, time, time, time, time, time, makedirs, makedirs, makedirs
  - _run_startup_sequence
    Calls: on_event, _initialize_modules
  - _stop_background_workers
    Calls: on_event, shutdown_live_tile_pool, stop_scheduler
  - _serve_page
    Calls: join, FileResponse, exists, HTTPException
  - parse_styles
    Calls: isinstance, items, float, loads, print, float, is_integer, int
  - _parse_and_validate_styles
    Calls: parse_styles, isinstance
  - _resolve_extent
    Calls: all
  - error_payload
  - infer_data_mode
    Calls: bool, bool, HTTPException, strip, strip, error_payload
  - parse_utc_datetime
    Calls: strip, replace, any, astimezone, HTTPException, HTTPException, replace, fromisoformat, error_payload, strptime
  - validate_archive_range
    Calls: float, timedelta, HTTPException, get, HTTPException, error_payload, error_payload
  - format_utc_for_legacy
    Calls: strftime, astimezone
  - success_payload
  - attach_mode_and_source
    Calls: isinstance, get, get
  - normalize_radar_site_id
    Calls: upper, get, strip, str

### listing_cache.py
- Score: 275
- Imports: 5
- Functions: 135
- Classes: 0
- Key Functions:
  - _initialize_modules
    Calls: time, time, time, time, time, time, time, makedirs, makedirs, makedirs
  - _run_startup_sequence
    Calls: on_event, _initialize_modules
  - _stop_background_workers
    Calls: on_event, shutdown_live_tile_pool, stop_scheduler
  - _serve_page
    Calls: join, FileResponse, exists, HTTPException
  - parse_styles
    Calls: isinstance, items, float, loads, print, float, is_integer, int
  - _parse_and_validate_styles
    Calls: parse_styles, isinstance
  - _resolve_extent
    Calls: all
  - error_payload
  - infer_data_mode
    Calls: bool, bool, HTTPException, strip, strip, error_payload
  - parse_utc_datetime
    Calls: strip, replace, any, astimezone, HTTPException, HTTPException, replace, fromisoformat, error_payload, strptime
  - validate_archive_range
    Calls: float, timedelta, HTTPException, get, HTTPException, error_payload, error_payload
  - format_utc_for_legacy
    Calls: strftime, astimezone
  - success_payload
  - attach_mode_and_source
    Calls: isinstance, get, get
  - normalize_radar_site_id
    Calls: upper, get, strip, str

### .kilo\worktrees\big-capri\listing_cache.py
- Score: 275
- Imports: 5
- Functions: 135
- Classes: 0
- Key Functions:
  - _initialize_modules
    Calls: time, time, time, time, time, time, time, makedirs, makedirs, makedirs
  - _run_startup_sequence
    Calls: on_event, _initialize_modules
  - _stop_background_workers
    Calls: on_event, shutdown_live_tile_pool, stop_scheduler
  - _serve_page
    Calls: join, FileResponse, exists, HTTPException
  - parse_styles
    Calls: isinstance, items, float, loads, print, float, is_integer, int
  - _parse_and_validate_styles
    Calls: parse_styles, isinstance
  - _resolve_extent
    Calls: all
  - error_payload
  - infer_data_mode
    Calls: bool, bool, HTTPException, strip, strip, error_payload
  - parse_utc_datetime
    Calls: strip, replace, any, astimezone, HTTPException, HTTPException, replace, fromisoformat, error_payload, strptime
  - validate_archive_range
    Calls: float, timedelta, HTTPException, get, HTTPException, error_payload, error_payload
  - format_utc_for_legacy
    Calls: strftime, astimezone
  - success_payload
  - attach_mode_and_source
    Calls: isinstance, get, get
  - normalize_radar_site_id
    Calls: upper, get, strip, str

### satellite_v2\__init__.py
- Score: 192
- Imports: 0
- Functions: 96
- Classes: 0
- Key Functions:
  - _to_bool
    Calls: isinstance, lower, strip, str
  - _responsive_text_scale
    Calls: get, get_size_inches, max, max, max, _to_bool, float, float, min, get
  - _request_text
    Calls: range, RuntimeError, max, get, raise_for_status, RuntimeError
  - _request_json
    Calls: _request_text, loads
  - _cached_text
    Calls: _cached_text_custom
  - _cached_text_custom
    Calls: cached_call, _request_text
  - _cached_json
    Calls: _cached_json_custom
  - _cached_json_custom
    Calls: cached_call, _request_json
  - _clean_spc_text
    Calls: str, findall, sub, unescape, strip, join, sub, sub, sub, sub
  - _clean_spc_bulletin_text
    Calls: str, findall, sub, unescape, replace, join, strip, join, sub, sub
  - _format_hud_time
    Calls: strip, fromisoformat, astimezone, strftime, str, replace, strftime
  - _resolve_display_tz
    Calls: gettz, strip, gettz, str
  - _current_outlook_url
    Calls: lower, ValueError, strip
  - _spc_mapserver_layer_id
    Calls: lower, get, int, int, ValueError, strip, next, iter
  - _spc_mapserver_geojson_url
    Calls: _spc_mapserver_layer_id

### .kilo\worktrees\big-capri\satellite_v2\__init__.py
- Score: 192
- Imports: 0
- Functions: 96
- Classes: 0
- Key Functions:
  - _to_bool
    Calls: isinstance, lower, strip, str
  - _responsive_text_scale
    Calls: get, get_size_inches, max, max, max, _to_bool, float, float, min, get
  - _request_text
    Calls: range, RuntimeError, max, get, raise_for_status, RuntimeError
  - _request_json
    Calls: _request_text, loads
  - _cached_text
    Calls: _cached_text_custom
  - _cached_text_custom
    Calls: cached_call, _request_text
  - _cached_json
    Calls: _cached_json_custom
  - _cached_json_custom
    Calls: cached_call, _request_json
  - _clean_spc_text
    Calls: str, findall, sub, unescape, strip, join, sub, sub, sub, sub
  - _clean_spc_bulletin_text
    Calls: str, findall, sub, unescape, replace, join, strip, join, sub, sub
  - _format_hud_time
    Calls: strip, fromisoformat, astimezone, strftime, str, replace, strftime
  - _resolve_display_tz
    Calls: gettz, strip, gettz, str
  - _current_outlook_url
    Calls: lower, ValueError, strip
  - _spc_mapserver_layer_id
    Calls: lower, get, int, int, ValueError, strip, next, iter
  - _spc_mapserver_geojson_url
    Calls: _spc_mapserver_layer_id

### main_old.py
- Score: 163
- Imports: 67
- Functions: 38
- Classes: 0
- Key Functions:
  - _fahrenheit
  - _hectopascal
  - _mph
  - _miles
  - _inches
  - _format_legend_value
    Calls: is_integer, str, int, float
  - _format_display_value
    Calls: round, int, int, ceil, floor
  - _build_anchor_colormap
    Calls: float, float, max, from_list, float
  - _resolve_render_colormap
    Calls: get, _build_anchor_colormap
  - _build_legend_anchors
    Calls: get, get, float, _format_legend_value, float
  - get_product_config
    Calls: ValueError
  - _head_exists
    Calls: head
  - _looks_like_grib
    Calls: open, exists, getsize, read
  - _load_city_points
    Calls: open, load, append, float, float, get, get, isfinite, isfinite, get
  - _nearest_index_1d
    Calls: asarray, asarray, searchsorted, clip, astype, ValueError, zeros, abs, abs, astype

### .kilo\worktrees\big-capri\main.py
- Score: 162
- Imports: 66
- Functions: 38
- Classes: 0
- Key Functions:
  - _fahrenheit
  - _hectopascal
  - _mph
  - _miles
  - _inches
  - _format_legend_value
    Calls: is_integer, str, int, float
  - _format_display_value
    Calls: round, int, int, ceil, floor
  - _build_anchor_colormap
    Calls: float, float, max, from_list, float
  - _resolve_render_colormap
    Calls: get, _build_anchor_colormap
  - _build_legend_anchors
    Calls: get, get, float, _format_legend_value, float
  - get_product_config
    Calls: ValueError
  - _head_exists
    Calls: head
  - _looks_like_grib
    Calls: open, exists, getsize, read
  - _load_city_points
    Calls: open, load, append, float, float, get, get, isfinite, isfinite, get
  - _nearest_index_1d
    Calls: asarray, asarray, searchsorted, clip, astype, ValueError, zeros, abs, abs, astype

### satellite\satellite_tile_utils.py
- Score: 107
- Imports: 13
- Functions: 47
- Classes: 0
- Key Functions:
  - parse_goes_time_from_filename
    Calls: search, group, strptime, replace
  - _date_partition_dir
    Calls: join, replace, strftime, strftime, strftime, isinstance, isinstance, astimezone, now
  - get_cmi_var
    Calls: KeyError, list
  - _get_catalog_datasets_cached
    Calls: cached_call, TDSCatalog, sorted, keys
  - get_goes_data
    Calls: join, strip, replace, get, get, int, now, filter, lower, strftime
  - download_goes_data
    Calls: get_goes_data, sum, join, makedirs, items, items, print, join, makedirs, items
  - normalize_data
    Calls: clip, max, power
  - normalize
    Calls: clip
  - gamma_correction
    Calls: power
  - satpy_visible_reflectance
    Calls: normalize_data
  - _resample_to_match
    Calls: asarray, astype, _ndimage_zoom
  - _compute_downscale_factor
    Calls: min, max
  - _downscale_array
    Calls: astype, astype, _ndimage_zoom, _ndimage_zoom
  - build_true_color_rgb
    Calls: satpy_visible_reflectance, _compute_downscale_factor, _downscale_array, _resample_to_match, _resample_to_match, clip, dstack, _get_cmi_dataarray, array, type
  - build_geocolor_rgba
    Calls: build_true_color_rgb, _resample_to_match, normalize, normalize, zeros, normalize, range, clip, clip, zeros

### .kilo\worktrees\big-capri\satellite\satellite_tile_utils.py
- Score: 107
- Imports: 13
- Functions: 47
- Classes: 0
- Key Functions:
  - parse_goes_time_from_filename
    Calls: search, group, strptime, replace
  - _date_partition_dir
    Calls: join, replace, strftime, strftime, strftime, isinstance, isinstance, astimezone, now
  - get_cmi_var
    Calls: KeyError, list
  - _get_catalog_datasets_cached
    Calls: cached_call, TDSCatalog, sorted, keys
  - get_goes_data
    Calls: join, strip, replace, get, get, int, now, filter, lower, strftime
  - download_goes_data
    Calls: get_goes_data, sum, join, makedirs, items, items, print, join, makedirs, items
  - normalize_data
    Calls: clip, max, power
  - normalize
    Calls: clip
  - gamma_correction
    Calls: power
  - satpy_visible_reflectance
    Calls: normalize_data
  - _resample_to_match
    Calls: asarray, astype, _ndimage_zoom
  - _compute_downscale_factor
    Calls: min, max
  - _downscale_array
    Calls: astype, astype, _ndimage_zoom, _ndimage_zoom
  - build_true_color_rgb
    Calls: satpy_visible_reflectance, _compute_downscale_factor, _downscale_array, _resample_to_match, _resample_to_match, clip, dstack, _get_cmi_dataarray, array, type
  - build_geocolor_rgba
    Calls: build_true_color_rgb, _resample_to_match, normalize, normalize, zeros, normalize, range, clip, clip, zeros

### alerts\alerts_utils.py
- Score: 103
- Imports: 29
- Functions: 37
- Classes: 0
- Key Functions:
  - _overlays_root
    Calls: join
  - overlay_frame_dir
    Calls: join, _overlays_root, upper
  - overlay_meta_path
    Calls: join, overlay_frame_dir
  - overlay_image_path
    Calls: join, overlay_frame_dir
  - overlay_bounds_path
    Calls: join, overlay_frame_dir
  - overlay_index_path
    Calls: join, _overlays_root
  - frame_key_from_datetime
    Calls: astimezone, strftime
  - datetime_from_frame_key
    Calls: replace, strptime
  - _atomic_write_json
    Calls: makedirs, dirname, replace, open, dump, remove
  - build_overlay_meta
  - write_overlay_meta
    Calls: overlay_meta_path, _atomic_write_json
  - read_overlay_meta
    Calls: overlay_meta_path, open, load
  - read_overlay_index
    Calls: overlay_index_path, open, load
  - update_overlay_index
    Calls: overlay_index_path, makedirs, get, enumerate, _atomic_write_json, dirname, append, isoformat, open, load
  - read_latest_overlay_meta
    Calls: upper, read_overlay_index, join, isdir, read_overlay_meta, get, _overlays_root, max, get, iterdir

### alerts\alerts_iem_utils.py
- Score: 92
- Imports: 18
- Functions: 37
- Classes: 0
- Key Functions:
  - _load_zone_disk_cache
    Calls: time, exists, open, load, items, print, print, get, get, shape
  - _save_zone_disk_cache
    Calls: makedirs, dirname, items, open, dump, print, mapping
  - _fetch_single_zone_geometry
    Calls: time, split, get, get, raise_for_status, get, shape, rstrip, json
  - _prefetch_zone_geometries
    Calls: time, set, list, min, time, print, _save_zone_disk_cache, len, ThreadPoolExecutor, list
  - _resolve_zone_geometry
    Calls: time, min, time, print, _save_zone_disk_cache, unary_union, get, len, ThreadPoolExecutor, map
  - resolve_alerts_legend_columns
    Calls: max, isinstance, max, min, min, lower, int, min, int, int
  - normalize_alerts_custom_extent
    Calls: max, max, min, max, min, float, cos, max, abs, float
  - get_ocean_geometry
    Calls: natural_earth, natural_earth, Reader, extend, Reader, extend, unary_union, print, geometries, geometries
  - get_cache_path
    Calls: dirname, join, makedirs, lower, abspath, upper, join, str
  - is_cache_valid
    Calls: getmtime, exists, time
  - fetch_active_alerts
    Calls: fetch_active_alerts_with_source
  - _coerce_utc_datetime
    Calls: isinstance, strip, endswith, astimezone, astimezone, isinstance, fromisoformat, replace, replace, strptime
  - _is_alert_active_for_time
    Calls: _coerce_utc_datetime, _coerce_utc_datetime, _coerce_utc_datetime, get, get
  - _alert_feature_fingerprint
    Calls: strip, strip, strip, strip, tuple, isinstance, get, isinstance, get, sorted
  - _supplement_state_intersecting_alerts
    Calls: upper, get, list, _prefetch_zone_geometries, box, get, raise_for_status, get, _alert_feature_fingerprint, strip

### .kilo\worktrees\big-capri\alerts\alerts_iem_utils.py
- Score: 92
- Imports: 18
- Functions: 37
- Classes: 0
- Key Functions:
  - _load_zone_disk_cache
    Calls: time, exists, open, load, items, print, print, get, get, shape
  - _save_zone_disk_cache
    Calls: makedirs, dirname, items, open, dump, print, mapping
  - _fetch_single_zone_geometry
    Calls: time, split, get, get, raise_for_status, get, shape, rstrip, json
  - _prefetch_zone_geometries
    Calls: time, set, list, min, time, print, _save_zone_disk_cache, len, ThreadPoolExecutor, list
  - _resolve_zone_geometry
    Calls: time, min, time, print, _save_zone_disk_cache, unary_union, get, len, ThreadPoolExecutor, map
  - resolve_alerts_legend_columns
    Calls: max, isinstance, max, min, min, lower, int, min, int, int
  - normalize_alerts_custom_extent
    Calls: max, max, min, max, min, float, cos, max, abs, float
  - get_ocean_geometry
    Calls: natural_earth, natural_earth, Reader, extend, Reader, extend, unary_union, print, geometries, geometries
  - get_cache_path
    Calls: dirname, join, makedirs, lower, abspath, upper, join, str
  - is_cache_valid
    Calls: getmtime, exists, time
  - fetch_active_alerts
    Calls: fetch_active_alerts_with_source
  - _coerce_utc_datetime
    Calls: isinstance, strip, endswith, astimezone, astimezone, isinstance, fromisoformat, replace, replace, strptime
  - _is_alert_active_for_time
    Calls: _coerce_utc_datetime, _coerce_utc_datetime, _coerce_utc_datetime, get, get
  - _alert_feature_fingerprint
    Calls: strip, strip, strip, strip, tuple, isinstance, get, isinstance, get, sorted
  - _supplement_state_intersecting_alerts
    Calls: upper, get, list, _prefetch_zone_geometries, box, get, raise_for_status, get, _alert_feature_fingerprint, strip

### mrms\__init__.py
- Score: 90
- Imports: 0
- Functions: 45
- Classes: 0
- Key Functions:
  - _suppress_geo_labels
    Calls: tick_params, list, match, list, list, list, set_visible, findobj, getattr, hasattr
  - _safe_color
    Calls: isinstance, strip, is_color_like, is_color_like
  - _city_outline_color
    Calls: _safe_color, to_rgb
  - _safe_radar_site_coords
    Calls: float, float, upper, isfinite, isfinite, abs, abs, str, float, float
  - _normalize_radar_site_coords
    Calls: _safe_radar_site_coords, getattr, isinstance, getattr, isinstance, get, get, array, array
  - _load_json_config
    Calls: _load_json_config_raw, dirname, abspath
  - _is_radar_alert_event_allowed
    Calls: strip, startswith, startswith, startswith, startswith, str
  - _radar_static_warning_legend_entries
    Calls: _safe_color, get
  - _materialize_feature_geometries
    Calls: tuple, geometries, tuple, append, append
  - _subset_geometries_by_extent
    Calls: zip, append
  - warm_radar_cartopy_cache
    Calls: perf_counter, _materialize_feature_geometries, _materialize_feature_geometries, _materialize_feature_geometries, _materialize_feature_geometries, print, next, iter, geometries, perf_counter
  - _find_gcp_l3_archive
    Calls: get, fromstring, findall, int, endswith, find, endswith, find, split
  - download_and_extract_l3_product
    Calls: makedirs, _find_gcp_l3_archive, join, makedirs, join, exists, sort, print, print, dirname
  - _extract_datetime_from_radar_filename
    Calls: basename, search, search, search, str, groups, groups, group, len, replace
  - _infer_partition_dt_from_key
    Calls: replace, search, _extract_datetime_from_radar_filename, isinstance, now, basename, str, datetime, replace, astimezone

### .kilo\worktrees\big-capri\mrms\__init__.py
- Score: 90
- Imports: 0
- Functions: 45
- Classes: 0
- Key Functions:
  - _suppress_geo_labels
    Calls: tick_params, list, match, list, list, list, set_visible, findobj, getattr, hasattr
  - _safe_color
    Calls: isinstance, strip, is_color_like, is_color_like
  - _city_outline_color
    Calls: _safe_color, to_rgb
  - _safe_radar_site_coords
    Calls: float, float, upper, isfinite, isfinite, abs, abs, str, float, float
  - _normalize_radar_site_coords
    Calls: _safe_radar_site_coords, getattr, isinstance, getattr, isinstance, get, get, array, array
  - _load_json_config
    Calls: _load_json_config_raw, dirname, abspath
  - _is_radar_alert_event_allowed
    Calls: strip, startswith, startswith, startswith, startswith, str
  - _radar_static_warning_legend_entries
    Calls: _safe_color, get
  - _materialize_feature_geometries
    Calls: tuple, geometries, tuple, append, append
  - _subset_geometries_by_extent
    Calls: zip, append
  - warm_radar_cartopy_cache
    Calls: perf_counter, _materialize_feature_geometries, _materialize_feature_geometries, _materialize_feature_geometries, _materialize_feature_geometries, print, next, iter, geometries, perf_counter
  - _find_gcp_l3_archive
    Calls: get, fromstring, findall, int, endswith, find, endswith, find, split
  - download_and_extract_l3_product
    Calls: makedirs, _find_gcp_l3_archive, join, makedirs, join, exists, sort, print, print, dirname
  - _extract_datetime_from_radar_filename
    Calls: basename, search, search, search, str, groups, groups, group, len, replace
  - _infer_partition_dt_from_key
    Calls: replace, search, _extract_datetime_from_radar_filename, isinstance, now, basename, str, datetime, replace, astimezone

### spc\__init__.py
- Score: 84
- Imports: 0
- Functions: 42
- Classes: 0
- Key Functions:
  - get_basemap_path
    Calls: join, upper
  - basemap_exists
    Calls: exists, get_basemap_path
  - _add_geometry_patch
    Calls: get, PathPatch, add_patch, PlateCarree, concatenate, concatenate, Path, list, hasattr, list
  - _perf_enabled
    Calls: get, isinstance, bool, lower
  - _perf_log
    Calls: print, time
  - _is_gradient_parameter
    Calls: startswith, startswith
  - _load_state_geometries
    Calls: _load_state_geometries_impl
  - _build_conus_geometry
    Calls: _build_conus_geometry_impl
  - _get_us_country_geometry
    Calls: _get_us_country_geometry_impl
  - calc_wind_chill
    Calls: power, power
  - calc_relative_humidity
    Calls: clip, exp, exp
  - calc_heat_index
    Calls: isinstance, any
  - get_cache_path
    Calls: dirname, join, makedirs, abspath, now, replace, upper, strftime, strftime, strftime
  - is_cache_valid
    Calls: exists, time, getmtime
  - _get_station_names
    Calls: get, raise_for_status, json, strip, strip, get, get

### .kilo\worktrees\big-capri\spc\__init__.py
- Score: 84
- Imports: 0
- Functions: 42
- Classes: 0
- Key Functions:
  - get_basemap_path
    Calls: join, upper
  - basemap_exists
    Calls: exists, get_basemap_path
  - _add_geometry_patch
    Calls: get, PathPatch, add_patch, PlateCarree, concatenate, concatenate, Path, list, hasattr, list
  - _perf_enabled
    Calls: get, isinstance, bool, lower
  - _perf_log
    Calls: print, time
  - _is_gradient_parameter
    Calls: startswith, startswith
  - _load_state_geometries
    Calls: _load_state_geometries_impl
  - _build_conus_geometry
    Calls: _build_conus_geometry_impl
  - _get_us_country_geometry
    Calls: _get_us_country_geometry_impl
  - calc_wind_chill
    Calls: power, power
  - calc_relative_humidity
    Calls: clip, exp, exp
  - calc_heat_index
    Calls: isinstance, any
  - get_cache_path
    Calls: dirname, join, makedirs, abspath, now, replace, upper, strftime, strftime, strftime
  - is_cache_valid
    Calls: exists, time, getmtime
  - _get_station_names
    Calls: get, raise_for_status, json, strip, strip, get, get

### tools\satellite_v2_smoke.py
- Score: 79
- Imports: 7
- Functions: 36
- Classes: 0
- Key Functions:
  - _parse_datetime
    Calls: replace, astimezone, replace, strip, strptime, fromisoformat, now
  - validate_product_group
    Calls: lower, lower, lower
  - compute_lambert_params
    Calls: LambertConformal, PlateCarree, transform_points, max, max, get, max, min, array, array
  - _basemap_cache_key
    Calls: lower, lower, append, append, join, upper, upper, append, hexdigest, get
  - generate_basemap
    Calls: _basemap_cache_key, join, compute_lambert_params, get, get, figure, set_facecolor, add_axes, set_extent, set_facecolor
  - _session_dir
    Calls: join
  - _manifest_path
    Calls: join, _session_dir
  - create_session
    Calls: _session_dir, isoformat, isoformat, makedirs, upper, open, dump, strftime, join, now
  - touch_session
    Calls: _manifest_path, exists, isoformat, isoformat, open, load, open, dump, now, now
  - cleanup_sessions
    Calls: listdir, now, isdir, join, join, get, append, len, sort, isdir
  - validate_layers_path
    Calls: isabs, normpath, join, realpath, realpath, split, isdir, startswith
  - _create_transparent_axes
    Calls: figure, add_axes, set_extent, set_facecolor, set_alpha, set_frame_on, hasattr, set_visible, PlateCarree
  - _save_transparent
    Calls: savefig, close
  - _format_weather_region_label
    Calls: upper, get, strip, str
  - get_weather_group_label
    Calls: lower, get, strip, strip, str, str

### .kilo\worktrees\big-capri\tools\satellite_v2_smoke.py
- Score: 79
- Imports: 7
- Functions: 36
- Classes: 0
- Key Functions:
  - _parse_datetime
    Calls: replace, astimezone, replace, strip, strptime, fromisoformat, now
  - validate_product_group
    Calls: lower, lower, lower
  - compute_lambert_params
    Calls: LambertConformal, PlateCarree, transform_points, max, max, get, max, min, array, array
  - _basemap_cache_key
    Calls: lower, lower, append, append, join, upper, upper, append, hexdigest, get
  - generate_basemap
    Calls: _basemap_cache_key, join, compute_lambert_params, get, get, figure, set_facecolor, add_axes, set_extent, set_facecolor
  - _session_dir
    Calls: join
  - _manifest_path
    Calls: join, _session_dir
  - create_session
    Calls: _session_dir, isoformat, isoformat, makedirs, upper, open, dump, strftime, join, now
  - touch_session
    Calls: _manifest_path, exists, isoformat, isoformat, open, load, open, dump, now, now
  - cleanup_sessions
    Calls: listdir, now, isdir, join, join, get, append, len, sort, isdir
  - validate_layers_path
    Calls: isabs, normpath, join, realpath, realpath, split, isdir, startswith
  - _create_transparent_axes
    Calls: figure, add_axes, set_extent, set_facecolor, set_alpha, set_frame_on, hasattr, set_visible, PlateCarree
  - _save_transparent
    Calls: savefig, close
  - _format_weather_region_label
    Calls: upper, get, strip, str
  - get_weather_group_label
    Calls: lower, get, strip, strip, str, str

### satellite_v2\worker.py
- Score: 71
- Imports: 13
- Functions: 29
- Classes: 0
- Key Functions:
  - _resolve_cache_root
    Calls: resolve, get, get, expanduser, Path
  - _ordered_unique
    Calls: set, tuple, str, add, append
  - _profile_config
    Calls: lower, join, ValueError, sorted, strip, str
  - _profile_key
    Calls: lower, strip, str
  - _ordered_products
    Calls: tuple, tuple, _ordered_unique, normalize_channel, str, get, normalize_channel, _profile_config
  - _ordered_satellites
    Calls: tuple, _ordered_unique, str, get, _profile_config
  - _ordered_sectors
    Calls: tuple, _ordered_unique, _ordered_unique, _ordered_unique, str, get, _profile_config
  - _worker_jobs
    Calls: _profile_config, normalize_sat_id, normalize_channel, _ordered_satellites, _ordered_sectors, _ordered_products, get, normalize_sat_id, normalize_channel
  - _deep_state_path
  - _load_deep_index
    Calls: _deep_state_path, loads, read_text, max, int, get
  - _save_deep_index
    Calls: mkdir, _deep_state_path, with_suffix, write_text, replace, max, int, dumps
  - _resume_state_path
  - _lock_path
  - _now_utc
    Calls: now
  - _job_key
    Calls: normalize_sat_id, normalize_channel

### .kilo\worktrees\big-capri\satellite_v2\worker.py
- Score: 71
- Imports: 13
- Functions: 29
- Classes: 0
- Key Functions:
  - _resolve_cache_root
    Calls: resolve, get, get, expanduser, Path
  - _ordered_unique
    Calls: set, tuple, str, add, append
  - _profile_config
    Calls: lower, join, ValueError, sorted, strip, str
  - _profile_key
    Calls: lower, strip, str
  - _ordered_products
    Calls: tuple, tuple, _ordered_unique, normalize_channel, str, get, normalize_channel, _profile_config
  - _ordered_satellites
    Calls: tuple, _ordered_unique, str, get, _profile_config
  - _ordered_sectors
    Calls: tuple, _ordered_unique, _ordered_unique, _ordered_unique, str, get, _profile_config
  - _worker_jobs
    Calls: _profile_config, normalize_sat_id, normalize_channel, _ordered_satellites, _ordered_sectors, _ordered_products, get, normalize_sat_id, normalize_channel
  - _deep_state_path
  - _load_deep_index
    Calls: _deep_state_path, loads, read_text, max, int, get
  - _save_deep_index
    Calls: mkdir, _deep_state_path, with_suffix, write_text, replace, max, int, dumps
  - _resume_state_path
  - _lock_path
  - _now_utc
    Calls: now
  - _job_key
    Calls: normalize_sat_id, normalize_channel

### satellite_v2\tiler.py
- Score: 70
- Imports: 12
- Functions: 29
- Classes: 0
- Key Functions:
  - _resolve_cache_root
    Calls: resolve, get, get, expanduser, Path
  - _ordered_unique
    Calls: set, tuple, str, add, append
  - _profile_config
    Calls: lower, join, ValueError, sorted, strip, str
  - _profile_key
    Calls: lower, strip, str
  - _ordered_products
    Calls: tuple, tuple, _ordered_unique, normalize_channel, str, get, normalize_channel, _profile_config
  - _ordered_satellites
    Calls: tuple, _ordered_unique, str, get, _profile_config
  - _ordered_sectors
    Calls: tuple, _ordered_unique, _ordered_unique, _ordered_unique, str, get, _profile_config
  - _worker_jobs
    Calls: _profile_config, normalize_sat_id, normalize_channel, _ordered_satellites, _ordered_sectors, _ordered_products, get, normalize_sat_id, normalize_channel
  - _deep_state_path
  - _load_deep_index
    Calls: _deep_state_path, loads, read_text, max, int, get
  - _save_deep_index
    Calls: mkdir, _deep_state_path, with_suffix, write_text, replace, max, int, dumps
  - _resume_state_path
  - _lock_path
  - _now_utc
    Calls: now
  - _job_key
    Calls: normalize_sat_id, normalize_channel

### .kilo\worktrees\big-capri\satellite_v2\tiler.py
- Score: 70
- Imports: 12
- Functions: 29
- Classes: 0
- Key Functions:
  - _resolve_cache_root
    Calls: resolve, get, get, expanduser, Path
  - _ordered_unique
    Calls: set, tuple, str, add, append
  - _profile_config
    Calls: lower, join, ValueError, sorted, strip, str
  - _profile_key
    Calls: lower, strip, str
  - _ordered_products
    Calls: tuple, tuple, _ordered_unique, normalize_channel, str, get, normalize_channel, _profile_config
  - _ordered_satellites
    Calls: tuple, _ordered_unique, str, get, _profile_config
  - _ordered_sectors
    Calls: tuple, _ordered_unique, _ordered_unique, _ordered_unique, str, get, _profile_config
  - _worker_jobs
    Calls: _profile_config, normalize_sat_id, normalize_channel, _ordered_satellites, _ordered_sectors, _ordered_products, get, normalize_sat_id, normalize_channel
  - _deep_state_path
  - _load_deep_index
    Calls: _deep_state_path, loads, read_text, max, int, get
  - _save_deep_index
    Calls: mkdir, _deep_state_path, with_suffix, write_text, replace, max, int, dumps
  - _resume_state_path
  - _lock_path
  - _now_utc
    Calls: now
  - _job_key
    Calls: normalize_sat_id, normalize_channel

### radar\radar_archive_utils.py
- Score: 66
- Imports: 42
- Functions: 12
- Classes: 0
- Key Functions:
  - _from_breakpoints
    Calls: float, zip, from_list, len, len, ValueError, ValueError, min, append, max
  - create_grs_cc_cmap
    Calls: _from_breakpoints
  - create_grs_bv_cmap
    Calls: _from_breakpoints
  - create_grs_br_cmap
    Calls: _from_breakpoints
  - create_grs_zdr_cmap
    Calls: _from_breakpoints
  - create_grs_vil_cmap
    Calls: _from_breakpoints
  - create_grs_et_cmap
    Calls: _from_breakpoints
  - create_grs_sw_cmap
    Calls: _from_breakpoints
  - create_grs_precip_cmap
    Calls: _from_breakpoints
  - create_grs_dpa_cmap
    Calls: _from_breakpoints
  - create_grs_precip_total_cmap
    Calls: _from_breakpoints
  - create_grs_hca_style
    Calls: ListedColormap, list, BoundaryNorm, range, range

### .kilo\worktrees\big-capri\radar\radar_archive_utils.py
- Score: 66
- Imports: 42
- Functions: 12
- Classes: 0
- Key Functions:
  - _from_breakpoints
    Calls: float, zip, from_list, len, len, ValueError, ValueError, min, append, max
  - create_grs_cc_cmap
    Calls: _from_breakpoints
  - create_grs_bv_cmap
    Calls: _from_breakpoints
  - create_grs_br_cmap
    Calls: _from_breakpoints
  - create_grs_zdr_cmap
    Calls: _from_breakpoints
  - create_grs_vil_cmap
    Calls: _from_breakpoints
  - create_grs_et_cmap
    Calls: _from_breakpoints
  - create_grs_sw_cmap
    Calls: _from_breakpoints
  - create_grs_precip_cmap
    Calls: _from_breakpoints
  - create_grs_dpa_cmap
    Calls: _from_breakpoints
  - create_grs_precip_total_cmap
    Calls: _from_breakpoints
  - create_grs_hca_style
    Calls: ListedColormap, list, BoundaryNorm, range, range

### satellite\satellite_utils.py
- Score: 58
- Imports: 28
- Functions: 15
- Classes: 0
- Key Functions:
  - namespace_root
    Calls: Path
  - catalog_path
    Calls: normalize_sector, normalize_sat_id, normalize_channel, namespace_root
  - tile_path
    Calls: str, str, int, int, str, int, normalize_channel, normalize_sector, normalize_sat_id, namespace_root
  - negative_tile_marker_path
    Calls: Path, str
  - is_negative_tile_cached
    Calls: exists, negative_tile_marker_path
  - write_negative_tile_marker
    Calls: negative_tile_marker_path, mkdir, mkstemp, int, replace, time, str, fdopen, dump, write
  - clear_negative_tile_marker
    Calls: unlink, negative_tile_marker_path
  - source_path
    Calls: str, normalize_source_channel, normalize_sector, normalize_sat_id, namespace_root
  - read_json
    Calls: exists, open, load, isinstance
  - atomic_write_json
    Calls: mkdir, Path, range, mkstemp, str, open, close, replace, unlink, str
  - file_age_seconds
    Calls: max, exists, time, stat
  - tile_image_has_content
    Calls: asarray, convert, float, float, count_nonzero, int, float, max, std
  - is_valid_tile_file
    Calls: exists, open, tile_image_has_content, stat
  - count_frame_tiles
    Calls: sum, exists, str, tile_path, str, glob, is_file, is_valid_tile_file
  - sample_frame_tiles
    Calls: next, exists, tile_path, str, int, int, int, glob, is_file, is_valid_tile_file

## Potential Entry Points

- main.py
- main_old.py
- .kilo\worktrees\big-capri\main.py

## Largest Files

- main_old.py (7299 LOC)
- .kilo\worktrees\big-capri\main.py (7298 LOC)
- main.py (7297 LOC)
- spc\spc_utils.py (3694 LOC)
- .kilo\worktrees\big-capri\spc\spc_utils.py (3694 LOC)
- .kilo\worktrees\big-capri\config\cmaps\metpy.ctables.py (3472 LOC)
- config\cmaps\metpy.ctables.py (3472 LOC)
- radar\radar_archive_utils.py (2953 LOC)
- .kilo\worktrees\big-capri\radar\radar_archive_utils.py (2953 LOC)
- weather\weather_utils.py (2745 LOC)
- .kilo\worktrees\big-capri\weather\weather_utils.py (2745 LOC)
- surface\surface_utils.py (2641 LOC)
- .kilo\worktrees\big-capri\surface\surface_utils.py (2641 LOC)
- alerts\alerts_utils.py (2396 LOC)
- .kilo\worktrees\big-capri\alerts\alerts_utils.py (2396 LOC)
- satellite\satellite_utils.py (2315 LOC)
- .kilo\worktrees\big-capri\satellite\satellite_utils.py (2315 LOC)
- mrms\mrms_utils.py (1950 LOC)
- .kilo\worktrees\big-capri\mrms\mrms_utils.py (1950 LOC)
- satellite\satellite_archive_utils.py (1756 LOC)
