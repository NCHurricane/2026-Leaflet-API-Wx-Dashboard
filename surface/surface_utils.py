from config.geo_config import STATES_FULL, STATE_BOUNDS
from metpy.units import units
from metpy.calc import wind_components
from datetime import datetime, timezone, timedelta
from io import BytesIO, StringIO
from urllib.parse import urlencode
import os
import json
import gzip
import time
import re
from app_core.atomic_io import atomic_write_json
from app_core.upstream_ledger import requests
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

SURFACE_NETWORK_TYPES = ("ASOS", "COOP", "DCP", "RWIS")
_WORLD_STATION_NAME_CACHE = {}
_WORLD_STATION_NAME_CACHE_TS = 0.0
_STATION_METADATA_TTL_SECONDS = 24 * 3600
_WORLD_STATION_NAME_CACHE_TTL_SECONDS = _STATION_METADATA_TTL_SECONDS


def calc_wind_chill(temp_f, speed_kts):
    speed_mph = speed_kts * 1.15078
    wc = (
        35.74
        + (0.6215 * temp_f)
        - (35.75 * np.power(speed_mph, 0.16))
        + (0.4275 * temp_f * np.power(speed_mph, 0.16))
    )
    return wc


def calc_relative_humidity(t_f, td_f):
    t_c = (t_f - 32) * 5 / 9
    td_c = (td_f - 32) * 5 / 9
    es = 6.112 * np.exp((17.67 * t_c) / (t_c + 243.5))
    e = 6.112 * np.exp((17.67 * td_c) / (td_c + 243.5))
    rh = (e / es) * 100
    return np.clip(rh, 0, 100)


def calc_heat_index(t_f, rh):
    hi = 0.5 * (t_f + 61.0 + ((t_f - 68.0) * 1.2) + (rh * 0.094))
    if isinstance(hi, pd.Series):
        mask = hi > 80
        if mask.any():
            t = t_f[mask]
            r = rh[mask]
            hi_full = (
                -42.379
                + 2.04901523 * t
                + 10.14333127 * r
                - 0.22475541 * t * r
                - 0.00683783 * t * t
                - 0.05481717 * r * r
                + 0.00122874 * t * t * r
                + 0.00085282 * t * r * r
                - 0.00000199 * t * t * r * r
            )
            hi[mask] = hi_full
    return hi


# --- 3. DATA ACQUISITION & CACHING ---


def get_cache_path(state_code, reference_dt=None):
    base_path = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(base_path)

    if reference_dt is None:
        reference_dt = datetime.now(timezone.utc)
    if reference_dt.tzinfo is None:
        reference_dt = reference_dt.replace(tzinfo=timezone.utc)

    cache_dir = os.path.join(
        repo_root,
        "cache",
        "surface",
        "raw",
        state_code.upper(),
        reference_dt.strftime("%Y"),
        reference_dt.strftime("%m"),
        reference_dt.strftime("%d"),
    )
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir, os.path.join(cache_dir, "data.csv")


def is_cache_valid(file_path, minutes=30):
    if not os.path.exists(file_path):
        return False
    if (time.time() - os.path.getmtime(file_path)) < (minutes * 60):
        return True
    return False


def _get_station_names(network_id):
    return _get_station_names_for_day(
        network_id,
        int(time.time() // _STATION_METADATA_TTL_SECONDS),
    )


@lru_cache(maxsize=512)
def _get_station_names_for_day(network_id, _day_bucket):
    """
    Fetch station metadata from IEM to get station names.
    Returns a dict mapping station_id -> name.
    """
    try:
        url = f"https://mesonet.agron.iastate.edu/geojson/network/{network_id}.geojson"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        station_names = {}
        for feature in data.get("features", []):
            props = feature.get("properties") or {}
            sid = str(props.get("sid") or props.get("id") or "").strip()
            sname = str(props.get("sname") or props.get("name") or "").strip()
            if sid and sname:
                station_names[sid] = sname
        return station_names
    except Exception:
        return {}


_get_station_names.cache_clear = _get_station_names_for_day.cache_clear


def _fetch_single_network(state_code, network_type):
    """
    Fetch data from a single network for a state.
    Returns DataFrame with data from that network, tagged with network_type.
    network_type should be one of: ASOS, COOP, DCP, RWIS
    """
    try:
        network_id = f"{state_code.upper()}_{network_type}"
        api_url = f"https://mesonet.agron.iastate.edu/api/1/currents.json?network={network_id}"

        resp = requests.get(api_url, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", [])

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df["network"] = network_type  # Tag with network type
        names = _get_station_names(network_id)
        if names:
            station_ids = df.get("station", pd.Series("", index=df.index)).astype(str).str.strip()
            fetched_names = station_ids.map(names).fillna("")
            if "name" not in df.columns:
                df["name"] = fetched_names
            else:
                blank = df["name"].fillna("").astype(str).str.strip().eq("")
                df.loc[blank, "name"] = fetched_names[blank]
        return df
    except Exception:
        return pd.DataFrame()


def _fetch_all_networks_parallel(state_code):
    """
    Fetch current observations from all supported network types in parallel.
    Returns combined DataFrame with network field populated.
    """
    networks = list(SURFACE_NETWORK_TYPES)
    all_dfs = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_fetch_single_network, state_code, net): net
            for net in networks
        }
        for future in as_completed(futures):
            try:
                df = future.result()
                if not df.empty:
                    all_dfs.append(df)
            except Exception:
                pass

    if not all_dfs:
        return pd.DataFrame()

    return pd.concat(all_dfs, ignore_index=True)


def _to_float_mi(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return np.nan

    # Common METAR visibility strings include suffixes like "+" (for 6+). Extract leading numeric portion.
    match = re.search(r"[-+]?\d*\.?\d+", text)
    if match:
        try:
            return float(match.group(0))
        except Exception:
            return np.nan
    return np.nan


def _get_world_station_name_map(force_refresh=False):
    """Return a daily station-id/name snapshot from Aviation Weather."""
    global _WORLD_STATION_NAME_CACHE, _WORLD_STATION_NAME_CACHE_TS

    now = time.time()
    if (
        not force_refresh
        and _WORLD_STATION_NAME_CACHE
        and (now - _WORLD_STATION_NAME_CACHE_TS) < _WORLD_STATION_NAME_CACHE_TTL_SECONDS
    ):
        return _WORLD_STATION_NAME_CACHE

    metadata_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "cache",
        "surface",
        "metadata",
        "aviationweather_station_names.json",
    )
    try:
        with open(metadata_path, "r", encoding="utf-8") as fh:
            disk_mapping = json.load(fh)
        disk_mtime = os.path.getmtime(metadata_path)
        if isinstance(disk_mapping, dict) and disk_mapping:
            _WORLD_STATION_NAME_CACHE = disk_mapping
            _WORLD_STATION_NAME_CACHE_TS = disk_mtime
            if not force_refresh and (now - disk_mtime) < _STATION_METADATA_TTL_SECONDS:
                return _WORLD_STATION_NAME_CACHE
    except (OSError, ValueError, TypeError):
        pass

    url = "https://aviationweather.gov/data/cache/stations.cache.json.gz"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        raw = gzip.decompress(resp.content).decode("utf-8", errors="replace")
        payload = json.loads(raw)
    except Exception as e:
        print(f"[WARN] WORLD station-name metadata fetch failed: {e}")
        return _WORLD_STATION_NAME_CACHE

    rows = payload if isinstance(
        payload, list) else payload.get("features", [])
    mapping = {}
    for row in rows:
        props = row.get("properties", {}) if isinstance(row, dict) else {}
        if not props and isinstance(row, dict):
            props = row
        if not isinstance(props, dict):
            continue

        site_name = str(props.get("site") or "").strip()
        if not site_name:
            continue

        for raw_id in (props.get("icaoId"), props.get("faaId"), props.get("wmoId")):
            sid = str(raw_id or "").strip().upper()
            if sid and sid not in mapping:
                mapping[sid] = site_name

    if mapping:
        _WORLD_STATION_NAME_CACHE = mapping
        _WORLD_STATION_NAME_CACHE_TS = now
        atomic_write_json(metadata_path, mapping)

    return _WORLD_STATION_NAME_CACHE


def _fetch_world_current_observations():
    """Fetch current global METAR observations from Aviation Weather cache feed."""
    url = "https://aviationweather.gov/data/cache/metars.cache.csv.gz"
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        df = pd.read_csv(BytesIO(response.content), compression="gzip")
    except Exception as e:
        print(f"[WARN] WORLD METAR fetch failed: {e}")
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    def _column_or_default(column_name: str, default: object = np.nan) -> pd.Series:
        if column_name in df.columns:
            return df[column_name]
        return pd.Series(default, index=df.index)

    station_ids = _column_or_default("station_id", "").astype(str).str.strip()
    station_name_map = _get_world_station_name_map()

    out = pd.DataFrame()
    out["station_id"] = station_ids
    out["name"] = station_ids.str.upper().map(
        station_name_map).fillna(station_ids)
    out["valid"] = _column_or_default("observation_time")
    out["latitude"] = pd.to_numeric(_column_or_default("latitude"), errors="coerce")
    out["longitude"] = pd.to_numeric(_column_or_default("longitude"), errors="coerce")

    temp_c = pd.to_numeric(_column_or_default("temp_c"), errors="coerce")
    dew_c = pd.to_numeric(_column_or_default("dewpoint_c"), errors="coerce")
    out["air_temperature"] = (temp_c * 9.0 / 5.0) + 32.0
    out["dew_point_temperature"] = (dew_c * 9.0 / 5.0) + 32.0

    out["wind_speed"] = pd.to_numeric(
        _column_or_default("wind_speed_kt"), errors="coerce"
    )
    out["wind_dir"] = pd.to_numeric(
        _column_or_default("wind_dir_degrees"), errors="coerce")
    out["wind_gust"] = pd.to_numeric(
        _column_or_default("wind_gust_kt"), errors="coerce"
    )
    out["altimeter"] = pd.to_numeric(
        _column_or_default("altim_in_hg"), errors="coerce"
    )
    out["mean_sea_level_pressure"] = pd.to_numeric(
        _column_or_default("sea_level_pressure_mb"), errors="coerce"
    )
    out["visibility"] = _column_or_default("visibility_statute_mi").apply(_to_float_mi)
    out["wxcodes"] = _column_or_default("wx_string")

    # Keep network taxonomy aligned with the existing frontend filters.
    out["network"] = "ASOS"

    # Filter out stations with placeholder/invalid coordinates
    # Aviation Weather uses -99.99, -99.99 for stations with unknown locations
    valid_coords = (
        (out["latitude"].notna()) & (out["longitude"].notna()) &
        (out["latitude"].abs() <= 90) & (out["longitude"].abs() <= 180) &
        (out["latitude"] != -99.99) & (out["longitude"] != -99.99)
    )
    out = out[valid_coords].copy()

    return out


def _filter_supported_network_rows(df):
    if df is None or df.empty or "network" not in df.columns:
        return df
    return df[df["network"].isin(SURFACE_NETWORK_TYPES)].copy()


def process_dataframe(df, state_code):
    rename_map = {
        "station": "station_id",
        "name": "name",
        "site_name": "name",
        "station_name": "name",
        "location": "name",
        "utc_valid": "valid",
        "lat": "latitude",
        "lon": "longitude",
        "tmpf": "air_temperature",
        "dwpf": "dew_point_temperature",
        "sknt": "wind_speed",
        "drct": "wind_dir",
        "relh": "relative_humidity",
        "alti": "altimeter",
        "vsby": "visibility",
        "gust": "wind_gust",
        "mslp": "mean_sea_level_pressure",
        "wxcodes": "wxcodes",
    }
    actual_rename = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=actual_rename)

    if "station_id" not in df.columns:
        df["station_id"] = ""
    df["station_id"] = df["station_id"].fillna("").astype(str)

    if "name" not in df.columns:
        df["name"] = df["station_id"]
    else:
        names = df["name"].fillna("").astype(str).str.strip()
        df["name"] = names.mask(names.eq(""), df["station_id"])

    if "valid" not in df.columns:
        df["valid"] = pd.NaT
    if "network" not in df.columns:
        df["network"] = "ASOS"
    else:
        networks = df["network"].fillna("").astype(str).str.strip()
        df["network"] = networks.mask(networks.eq(""), "ASOS")

    numeric_cols = [
        "air_temperature",
        "dew_point_temperature",
        "wind_speed",
        "wind_dir",
        "latitude",
        "longitude",
        "relative_humidity",
        "altimeter",
        "visibility",
        "wind_gust",
        "mean_sea_level_pressure",
    ]

    for c in numeric_cols:
        if c not in df.columns:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")

    if "wxcodes" not in df.columns:
        df["wxcodes"] = np.nan

    df = df.dropna(subset=["latitude", "longitude", "air_temperature"])
    if df.empty:
        return df

    wspd_safe = df["wind_speed"].fillna(0)
    wdir_safe = df["wind_dir"].fillna(0)
    u, v = wind_components(
        wspd_safe.values * units.knots, wdir_safe.values * units.degrees
    )
    df["u"] = u.m
    df["v"] = v.m

    df["peak_wind"] = df["wind_gust"].fillna(df["wind_speed"])
    df["wind_chill"] = calc_wind_chill(df["air_temperature"], wspd_safe)

    missing_rh = df["relative_humidity"].isna()
    if missing_rh.any():
        calculated_rh = calc_relative_humidity(
            df["air_temperature"],
            df["dew_point_temperature"].fillna(df["air_temperature"]),
        )
        df.loc[missing_rh, "relative_humidity"] = calculated_rh.loc[missing_rh]

    df["heat_index"] = calc_heat_index(
        df["air_temperature"], df["relative_humidity"])

    wspd_mph = wspd_safe * 1.15078
    cond_cold = (df["air_temperature"] <= 50) & (wspd_mph >= 3)
    cond_hot = df["air_temperature"] >= 80
    df["feels_like"] = df["air_temperature"].astype(float)
    df.loc[cond_cold, "feels_like"] = df.loc[cond_cold, "wind_chill"]
    df.loc[cond_hot, "feels_like"] = df.loc[cond_hot, "heat_index"]

    return df


def fetch_nws_current_observations(state_code):
    """
    Fetch current surface observations from NWS API (api.weather.gov).
    Returns DataFrame in the same format as IEM METAR data for compatibility.
    Falls back gracefully if NWS is unavailable or sparse.
    """
    if state_code.upper() not in STATES_FULL:
        return pd.DataFrame()

    state_bounds = STATE_BOUNDS.get(state_code.upper())
    if not state_bounds:
        return pd.DataFrame()

    # STATE_BOUNDS format: [west, east, south, north]
    west, east, south, north = state_bounds
    center_lat = (north + south) / 2.0
    center_lon = (east + west) / 2.0

    try:
        # NWS gridpoint endpoint
        gridpoint_url = (
            f"https://api.weather.gov/points/{center_lat:.2f},{center_lon:.2f}"
        )
        resp = requests.get(gridpoint_url, timeout=10)
        resp.raise_for_status()
        gridpoint_data = resp.json()

        # Extract grid point ID for observations
        if "properties" not in gridpoint_data:
            return pd.DataFrame()

        grid_id = gridpoint_data["properties"].get("gridId")
        grid_x = gridpoint_data["properties"].get("gridX")
        grid_y = gridpoint_data["properties"].get("gridY")

        if not (grid_id and grid_x is not None and grid_y is not None):
            return pd.DataFrame()

        # Fetch observations from that grid point
        obs_url = f"https://api.weather.gov/gridpoints/{grid_id}/{grid_x},{grid_y}/observations/latest"
        obs_resp = requests.get(obs_url, timeout=10)
        obs_resp.raise_for_status()
        obs_data = obs_resp.json()

        if "features" not in obs_data or not obs_data["features"]:
            return pd.DataFrame()

        # Convert NWS format to METAR-like format for compatibility
        records = []
        for feature in obs_data["features"]:
            props = feature.get("properties", {})
            if not props:
                continue

            # Extract key fields and standardize names
            record = {
                "station": props.get("station", "").split("/")[-1],
                "name": props.get("name", ""),  # NWS may include station name
                "tmpf": props.get("temperature"),
                "dwpf": props.get("dewpoint"),
                "relh": props.get("relativeHumidity"),
                "drct": props.get("windDirection"),
                "sknt": props.get("windSpeed"),
                "vsby": props.get("visibility"),
                "alti": props.get("seaLevelPressure"),
                "mslp": props.get("seaLevelPressure"),
                "gust": props.get("windGust"),
                "valid": props.get("timestamp"),
            }
            if pd.notna(record["tmpf"]) and pd.notna(record["dwpf"]):
                record["feelsx"] = record["tmpf"]
            records.append(record)

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        return process_dataframe(df, state_code)

    except Exception as e:
        print(f"[WARN] NWS current fetch failed for {state_code.upper()}: {e}")
        return pd.DataFrame()


def fetch_metar_data(state_code, use_nws_first=False):
    """
    Fetch current METAR observations for a state.
    Uses IEM by default. When use_nws_first=True, tries NWS first for
    current-mode flows, then falls back to IEM.
    """
    state_upper = str(state_code or "").upper().strip() or "NC"

    # WORLD current-mode: use global METAR cache feed.
    if state_upper == "WORLD":
        cache_dir, cache_file = get_cache_path(state_upper)
        if is_cache_valid(cache_file, minutes=30):
            try:
                df_cached = pd.read_csv(cache_file)
                if not df_cached.empty:
                    return process_dataframe(df_cached, state_upper)
            except Exception:
                pass

        try:
            df_world_raw = _fetch_world_current_observations()
            if df_world_raw.empty:
                return pd.DataFrame()
            df_world = process_dataframe(df_world_raw, state_upper)
            if not df_world.empty:
                df_world.to_csv(cache_file, index=False)
            return df_world
        except Exception as e:
            print(f"API Error WORLD: {e}")
            return pd.DataFrame()

    # Try NWS first for current data
    if use_nws_first:
        try:
            df_nws = fetch_nws_current_observations(state_upper)
            if not df_nws.empty and len(df_nws) > 5:
                return df_nws
        except Exception:
            pass

    # Fall back to IEM
    cache_dir, cache_file = get_cache_path(state_upper)
    base_path = os.path.dirname(os.path.abspath(__file__))
    legacy_cache_file = os.path.join(
        base_path, "surface_data", state_upper, "data.csv"
    )

    for candidate in (cache_file, legacy_cache_file):
        if is_cache_valid(candidate, minutes=30):
            try:
                df = pd.read_csv(candidate)
                if not df.empty:
                    df = _filter_supported_network_rows(df)
                    if candidate != cache_file:
                        try:
                            df.to_csv(cache_file, index=False)
                        except Exception:
                            pass
                    return process_dataframe(df, state_upper)
                else:
                    os.remove(candidate)
            except Exception:
                pass

    if state_upper == "CONUS":
        # Use AWC bulk METAR API — avoids IEM rate limiting (192 requests → ~80 batched)
        try:
            df_awc = _fetch_awc_current_conus()
            if df_awc is not None and not df_awc.empty:
                df_awc.to_csv(cache_file, index=False)
                return df_awc
        except Exception as e:
            print(
                f"[surface] AWC CONUS fetch failed, falling back to IEM: {e}")

        # Fallback: per-state IEM (may be rate-limited)
        from app_core.refresh_coordinator import get_refresh_coordinator

        with get_refresh_coordinator().provider_budget("iem"):
            all_dfs = []
            states = [
                state
                for state in STATES_FULL.keys()
                if state not in ["AK", "HI", "CONUS"]
            ]

            max_workers = min(12, max(4, len(states)))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_state = {
                    executor.submit(fetch_metar_data, state): state
                    for state in states
                }
                for future in as_completed(future_to_state):
                    state = future_to_state[future]
                    try:
                        df_state = future.result()
                        if not df_state.empty:
                            all_dfs.append(df_state)
                    except Exception as e:
                        print(f"API Error {state}: {e}")

        if not all_dfs:
            return pd.DataFrame()
        combined_df = pd.concat(all_dfs, ignore_index=True)
        combined_df.to_csv(cache_file, index=False)
        return combined_df

    # Fetch from all supported network types in parallel
    try:
        df_raw = _fetch_all_networks_parallel(state_upper)
        if df_raw.empty:
            return pd.DataFrame()

        df_processed = process_dataframe(df_raw, state_upper)

        # Enrich station names for each network
        if not df_processed.empty and "network" in df_processed.columns:
            for network_type in SURFACE_NETWORK_TYPES:
                network_id = f"{state_upper}_{network_type}"
                station_names = _get_station_names(network_id)
                if station_names:
                    # Fill missing names for this network
                    mask = (df_processed["network"] == network_type) & (
                        (df_processed["name"].isna()) | (
                            df_processed["name"] == "")
                    )
                    df_processed.loc[mask, "name"] = df_processed.loc[
                        mask, "station_id"
                    ].map(
                        lambda x: station_names.get(
                            x.strip() if isinstance(x, str) else x, ""
                        )
                    )

        if not df_processed.empty:
            df_processed.to_csv(cache_file, index=False)
        return df_processed
    except Exception as e:
        print(f"API Error {state_upper}: {e}")
        return pd.DataFrame()


def _normalize_utc(dt_val):
    dt_out = dt_val or datetime.now(timezone.utc)
    if dt_out.tzinfo is None:
        return dt_out.replace(tzinfo=timezone.utc)
    return dt_out.astimezone(timezone.utc)


_SURFACE_SOURCE_ATTR = "surface_source"


def _with_surface_source(df, source):
    if df is not None and source:
        df.attrs[_SURFACE_SOURCE_ATTR] = source
    return df


def _select_nearest_station_rows(df, target_dt, max_delta_seconds=75 * 60):
    source = getattr(df, "attrs", {}).get(_SURFACE_SOURCE_ATTR)
    if (
        df is None
        or df.empty
        or "valid" not in df.columns
        or "station_id" not in df.columns
    ):
        return _with_surface_source(pd.DataFrame(), source)

    target_ts = pd.Timestamp(_normalize_utc(target_dt))
    if "_valid_ts" in df.columns:
        df_work = df.copy()
    else:
        ts = pd.to_datetime(df["valid"], utc=True, errors="coerce")
        df_work = df.assign(_valid_ts=ts)

    df_work = df_work.dropna(subset=["_valid_ts", "station_id"])
    if df_work.empty:
        return _with_surface_source(pd.DataFrame(), source)

    df_work["_delta_seconds"] = (
        (df_work["_valid_ts"] - target_ts).abs().dt.total_seconds()
    )
    df_work = (
        df_work.sort_values(["station_id", "_delta_seconds"])
        .groupby("station_id", as_index=False)
        .first()
    )
    df_work = df_work[df_work["_delta_seconds"] <= max_delta_seconds]
    if df_work.empty:
        return _with_surface_source(pd.DataFrame(), source)

    out = df_work.drop(
        columns=["_valid_ts", "_delta_seconds"], errors="ignore")
    if "network" not in out.columns:
        out["network"] = "ASOS"
    return _with_surface_source(out, source)


def _fetch_iem_state_archive_window(state, start_dt, end_dt):
    state_upper = str(state or "").upper().strip()
    if not state_upper or state_upper in {"CONUS", "WORLD", "AK", "HI"}:
        return _with_surface_source(pd.DataFrame(), "iem")

    start = _normalize_utc(start_dt)
    end = _normalize_utc(end_dt)
    network_id = f"{state_upper}_ASOS"
    fields = [
        "station",
        "valid",
        "lon",
        "lat",
        "tmpf",
        "dwpf",
        "sknt",
        "drct",
        "relh",
        "alti",
        "vsby",
        "gust",
        "mslp",
        "wxcodes",
    ]
    params = [
        ("network", network_id),
        ("tz", "Etc/UTC"),
        ("format", "onlycomma"),
        ("latlon", "yes"),
        ("direct", "no"),
        ("report_type", "1"),
        ("report_type", "2"),
        ("year1", str(start.year)),
        ("month1", str(start.month)),
        ("day1", str(start.day)),
        ("hour1", str(start.hour)),
        ("minute1", str(start.minute)),
        ("year2", str(end.year)),
        ("month2", str(end.month)),
        ("day2", str(end.day)),
        ("hour2", str(end.hour)),
        ("minute2", str(end.minute)),
    ]
    params.extend(("data", field) for field in fields)

    url = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
    query = f"{url}?{urlencode(params, doseq=True)}"
    headers = {"User-Agent": "2026-dashboard-surface-archive/1.0"}

    for attempt in range(4):
        try:
            resp = requests.get(query, timeout=45, headers=headers)
            resp.raise_for_status()
            if not (resp.text or "").strip():
                raise ValueError("Empty response body")

            df_raw = pd.read_csv(StringIO(resp.text))
            if (
                df_raw is None
                or df_raw.empty
                or "station" not in df_raw.columns
                or "valid" not in df_raw.columns
            ):
                raise ValueError("Unexpected IEM response schema")

            df = process_dataframe(df_raw, state_upper)
            if df is None or df.empty:
                raise ValueError("No processed rows")

            ts = pd.to_datetime(df["valid"], utc=True, errors="coerce")
            out = df.assign(_valid_ts=ts).dropna(
                subset=["_valid_ts", "station_id"])
            if out.empty:
                raise ValueError("No timestamped rows")

            if "network" not in out.columns:
                out["network"] = "ASOS"
            return _with_surface_source(out, "iem")
        except Exception:
            if attempt < 3:
                time.sleep(0.6 * (attempt + 1))

    return _with_surface_source(pd.DataFrame(), "iem")


# ---------------------------------------------------------------------------
# AWC (AviationWeather.gov) bulk METAR — replaces rate-limited IEM endpoints
# for both current and archive surface data.
# ---------------------------------------------------------------------------
_AWC_METAR_URL = "https://aviationweather.gov/api/data/metar"
_AWC_BATCH_SIZE = 30  # stay under 400-record limit per request
_AWC_MAX_WORKERS = 6
_AWC_STATION_CACHE: set[str] = set()
_AWC_STATION_CACHE_TS: float = 0.0
_AWC_STATION_CACHE_TTL: float = _STATION_METADATA_TTL_SECONDS


def _get_conus_icao_ids() -> set[str]:
    """Return US ASOS ICAO IDs from daily AWC metadata, with a budgeted IEM fallback."""
    global _AWC_STATION_CACHE, _AWC_STATION_CACHE_TS

    now = time.time()
    if _AWC_STATION_CACHE and (now - _AWC_STATION_CACHE_TS) < _AWC_STATION_CACHE_TTL:
        return _AWC_STATION_CACHE

    station_names = _get_world_station_name_map()
    awc_ids = {
        station_id
        for station_id in station_names
        if len(station_id) == 4 and station_id.startswith("K")
    }
    if len(awc_ids) >= 100:
        _AWC_STATION_CACHE = awc_ids
        _AWC_STATION_CACHE_TS = now
        return awc_ids

    all_ids: set[str] = set()
    states = [s for s in STATES_FULL.keys() if s not in ("AK", "HI", "CONUS")]
    hdrs = {"User-Agent": "2026-dashboard-surface-archive/1.0"}

    def _ids_for_state(st: str) -> set[str]:
        try:
            r = requests.get(
                f"https://mesonet.agron.iastate.edu/api/1/currents.json?network={st}_ASOS",
                timeout=10,
                headers=hdrs,
            )
            if r.status_code != 200:
                return set()
            ids: set[str] = set()
            for d in r.json().get("data", []):
                sid = d.get("station", "")
                if len(sid) == 3 and sid.isalnum():
                    ids.add("K" + sid)
                elif len(sid) == 4 and sid[0] == "K":
                    ids.add(sid)
            return ids
        except Exception:
            return set()

    from app_core.refresh_coordinator import get_refresh_coordinator

    with get_refresh_coordinator().provider_budget("iem"):
        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = {pool.submit(_ids_for_state, st): st for st in states}
            for f in as_completed(futs):
                all_ids.update(f.result())

    if all_ids:
        _AWC_STATION_CACHE = all_ids
        _AWC_STATION_CACHE_TS = now
    return all_ids


def _get_state_icao_ids(state_code: str) -> set[str]:
    """Return ASOS ICAO IDs for a single state via IEM currents.json."""
    hdrs = {"User-Agent": "2026-dashboard-surface-archive/1.0"}
    try:
        r = requests.get(
            f"https://mesonet.agron.iastate.edu/api/1/currents.json?network={state_code}_ASOS",
            timeout=10,
            headers=hdrs,
        )
        if r.status_code != 200:
            return set()
        ids: set[str] = set()
        for d in r.json().get("data", []):
            sid = d.get("station", "")
            if len(sid) == 3 and sid.isalnum():
                ids.add("K" + sid)
            elif len(sid) == 4 and sid[0] == "K":
                ids.add(sid)
        return ids
    except Exception:
        return set()


def _fetch_awc_metar_bulk(icao_ids: set[str], hours: int) -> list[dict]:
    """Fetch historical METAR observations from AWC in batches of 30 stations."""
    station_list = sorted(icao_ids)
    batches = [
        station_list[i: i + _AWC_BATCH_SIZE]
        for i in range(0, len(station_list), _AWC_BATCH_SIZE)
    ]
    all_records: list[dict] = []
    hdrs = {"User-Agent": "2026-dashboard-surface-archive/1.0"}

    def _fetch_batch(batch_ids: list[str]) -> list[dict]:
        id_str = ",".join(batch_ids)
        url = f"{_AWC_METAR_URL}?ids={id_str}&format=json&hours={hours}"
        try:
            resp = requests.get(url, timeout=30, headers=hdrs)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    with ThreadPoolExecutor(max_workers=_AWC_MAX_WORKERS) as pool:
        futs = [pool.submit(_fetch_batch, b) for b in batches]
        for f in as_completed(futs):
            all_records.extend(f.result())

    return all_records


def _awc_records_to_iem_df(records: list[dict]) -> pd.DataFrame:
    """Convert AWC METAR JSON records into an IEM-compatible raw DataFrame.

    The returned DataFrame has the same column names as the IEM CSV download
    so it can be passed directly into ``process_dataframe()``.
    """
    if not records:
        return pd.DataFrame()

    rows: list[dict] = []
    station_names = _get_world_station_name_map()
    for r in records:
        obs_time = r.get("obsTime")
        if obs_time is None:
            continue

        # Celsius → Fahrenheit
        temp_c = r.get("temp")
        dewp_c = r.get("dewp")
        tmpf = (temp_c * 9.0 / 5.0 + 32.0) if temp_c is not None else None
        dwpf = (dewp_c * 9.0 / 5.0 + 32.0) if dewp_c is not None else None

        # Visibility: AWC returns string like "10+", "6", etc.
        vsby_raw = r.get("visib")
        vsby = None
        if vsby_raw is not None:
            vsby_str = str(vsby_raw).replace("+", "")
            match = re.search(r"[\d.]+", vsby_str)
            if match:
                try:
                    vsby = float(match.group(0))
                except (ValueError, TypeError):
                    pass

        # Convert ICAO → FAA LID (strip K-prefix for US 4-char IDs)
        icao = r.get("icaoId", "")
        station = icao[1:] if len(icao) == 4 and icao.startswith("K") else icao

        valid_dt = datetime.fromtimestamp(obs_time, tz=timezone.utc)
        valid_str = valid_dt.strftime("%Y-%m-%d %H:%M+00:00")

        rows.append(
            {
                "station": station,
                "name": (
                    station_names.get(str(icao).upper())
                    or station_names.get(str(station).upper())
                    or station
                ),
                "valid": valid_str,
                "lat": r.get("lat"),
                "lon": r.get("lon"),
                "tmpf": tmpf,
                "dwpf": dwpf,
                "sknt": r.get("wspd"),
                "drct": r.get("wdir"),
                "relh": None,
                "alti": r.get("altim"),
                "vsby": vsby,
                "gust": r.get("wgst"),
                "mslp": r.get("slp"),
                "wxcodes": None,
            }
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _fetch_awc_archive_window(icao_ids: set[str], start_dt, end_dt):
    """Fetch AWC bulk data for a set of station IDs covering a time window.

    Returns a processed DataFrame with ``_valid_ts`` column ready for
    ``_select_nearest_station_rows()``.
    """
    start = _normalize_utc(start_dt)
    end = _normalize_utc(end_dt)
    span_hours = max(1, int((end - start).total_seconds() / 3600) + 2)
    # AWC 'hours' param looks back from now, so we must ensure it covers the window
    age_hours = (
        max(0, int((datetime.now(timezone.utc) - start).total_seconds() / 3600)) + 1
    )
    hours = max(span_hours, age_hours)
    hours = min(hours, 24)  # AWC practical limit

    records = _fetch_awc_metar_bulk(icao_ids, hours)
    if not records:
        return _with_surface_source(pd.DataFrame(), "awc")

    raw_df = _awc_records_to_iem_df(records)
    if raw_df.empty:
        return _with_surface_source(pd.DataFrame(), "awc")

    df = process_dataframe(raw_df, "CONUS")
    if df is None or df.empty:
        return _with_surface_source(pd.DataFrame(), "awc")

    ts = pd.to_datetime(df["valid"], utc=True, errors="coerce")
    out = df.assign(_valid_ts=ts).dropna(subset=["_valid_ts", "station_id"])
    if "network" not in out.columns:
        out["network"] = "ASOS"
    return _with_surface_source(out, "awc")


def _fetch_awc_current_conus() -> pd.DataFrame:
    """Fetch current CONUS ASOS observations from AWC in a single bulk call.

    Returns a fully processed DataFrame compatible with ``fetch_metar_data``
    output — ready for caching and the ``/api/data/surface`` endpoint.
    Uses ``hours=2`` so every station that reported in the last 2 hours is
    included, then deduplicates to the latest observation per station.
    """
    icao_ids = _get_conus_icao_ids()
    if not icao_ids:
        return pd.DataFrame()

    records = _fetch_awc_metar_bulk(icao_ids, hours=2)
    if not records:
        return pd.DataFrame()

    # Deduplicate to latest observation per station
    latest: dict[str, dict] = {}
    for r in records:
        sid = r.get("icaoId", "")
        if not sid:
            continue
        if sid not in latest or r.get("obsTime", 0) > latest[sid].get("obsTime", 0):
            latest[sid] = r

    raw_df = _awc_records_to_iem_df(list(latest.values()))
    if raw_df.empty:
        return pd.DataFrame()

    df = process_dataframe(raw_df, "CONUS")
    if df is None or df.empty:
        return pd.DataFrame()

    if "network" not in df.columns:
        df["network"] = "ASOS"
    return df


def fetch_metar_data_archive_frames(state_code, frame_times_utc, source="iem"):
    """Fetch archive frames with AWC first and an IEM state fallback."""
    frame_times = [
        _normalize_utc(ts) for ts in (frame_times_utc or []) if ts is not None
    ]
    if not frame_times:
        return []

    source_key = str(source or "iem").strip().lower()
    if source_key not in {"iem", "auto"}:
        return [
            fetch_metar_data_at_time(state_code, ts, source=source_key)
            for ts in frame_times
        ]

    state = str(state_code or "").upper().strip() or "NC"
    window_start = min(frame_times) - timedelta(minutes=40)
    window_end = max(frame_times) + timedelta(minutes=20)

    if state == "WORLD":
        return [
            fetch_metar_data_at_time("WORLD", ts, source="iem") for ts in frame_times
        ]

    if state == "CONUS":
        icao_ids = _get_conus_icao_ids()
        if not icao_ids:
            return [pd.DataFrame() for _ in frame_times]

        df_all = _fetch_awc_archive_window(icao_ids, window_start, window_end)
        if df_all is None or df_all.empty:
            return [pd.DataFrame() for _ in frame_times]

        return [_select_nearest_station_rows(df_all, ts) for ts in frame_times]

    # Single state — use AWC with state-specific station IDs
    icao_ids = _get_state_icao_ids(state)
    if icao_ids:
        df_window = _fetch_awc_archive_window(
            icao_ids, window_start, window_end)
        if df_window is not None and not df_window.empty:
            return [_select_nearest_station_rows(df_window, ts) for ts in frame_times]

    # Fallback to IEM if AWC returned nothing for this state
    df_window = _fetch_iem_state_archive_window(
        state, window_start, window_end)
    return [_select_nearest_station_rows(df_window, ts) for ts in frame_times]


def fetch_metar_data_at_time(state_code, valid_time_utc, source="iem"):
    """Fetch station observations nearest a target UTC time."""
    source_key = str(source or "iem").strip().lower()
    target_dt = _normalize_utc(valid_time_utc)

    # NWS and aviationweather are near-real-time sources; use NWS opportunistically
    # for recent targets, then fall back to IEM.
    if source_key in {"nws", "aviationweather", "auto"}:
        age_seconds = abs(
            (datetime.now(timezone.utc) - target_dt).total_seconds())
        if age_seconds <= 2 * 3600:
            try:
                df_nws = fetch_nws_current_observations(state_code)
                if df_nws is not None and not df_nws.empty and len(df_nws) > 5:
                    return df_nws
            except Exception:
                pass

    state = str(state_code or "").upper().strip() or "NC"

    if state == "WORLD":
        try:
            df_world_raw = _fetch_world_current_observations()
            if df_world_raw.empty:
                return pd.DataFrame()
            df = process_dataframe(df_world_raw, state)
        except Exception:
            return pd.DataFrame()
        return _select_nearest_station_rows(df, target_dt)

    if state == "CONUS":
        frames = fetch_metar_data_archive_frames(
            "CONUS", [target_dt], source="iem")
        if frames:
            return frames[0]
        return pd.DataFrame()

    start = target_dt - timedelta(minutes=40)
    end = target_dt + timedelta(minutes=20)
    df_window = _fetch_iem_state_archive_window(state, start, end)
    return _select_nearest_station_rows(df_window, target_dt)
