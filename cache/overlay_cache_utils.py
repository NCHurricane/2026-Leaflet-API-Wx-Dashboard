"""Shared overlay cache schema helpers (flat overlays + live radar frames).

This module defines the on-disk layout used by the RTMA/MRMS overlay workers,
the live radar worker, and the /api/overlay/* and /api/radar/live/* endpoints.

Flat overlay cache (RTMA, MRMS):
    cache/overlays/{family}/{p0}/{p1}/{p2}/
        {frame_key}.png         rendered overlay frame
        index.json              {"frames": {frame_key: meta}, "updated": iso}
        processed_keys.json     source data keys already rendered (dedup)

Live radar cache:
    cache/radar/live/{SITE}/{LEVEL}/{PRODUCT}/
        same files as above

Frame keys are UTC timestamps formatted YYYY_MM_DD_HH_MM_SS, so lexical
ordering equals chronological ordering. Image URLs are served through the
/cache static mount in main.py.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

_FRAME_KEY_FORMAT = "%Y_%m_%d_%H_%M_%S"

# Single lock serializes all index/processed-key writes. The JSON files are
# small, and worker threads + API threads may touch the same product dir.
_write_lock = threading.Lock()


# ── Frame keys ────────────────────────────────────────────────────────────────


def frame_key_from_datetime(dt: datetime) -> str:
    """Format a datetime as a UTC frame key (YYYY_MM_DD_HH_MM_SS)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime(_FRAME_KEY_FORMAT)


def datetime_from_frame_key(frame_key: str) -> datetime:
    """Parse a frame key back into a tz-aware UTC datetime."""
    return datetime.strptime(str(frame_key).strip(), _FRAME_KEY_FORMAT).replace(
        tzinfo=timezone.utc
    )


# ── Path helpers ──────────────────────────────────────────────────────────────


def _flat_dir(cache_root, family, path_parts) -> str:
    return os.path.join(
        str(cache_root), "overlays", str(family), *[str(p) for p in path_parts]
    )


def _flat_url_dir(family, path_parts) -> str:
    return (
        "/cache/overlays/" + str(family) + "/" + "/".join(str(p) for p in path_parts)
    )


def _radar_dir(cache_root, site, level_code, product_key) -> str:
    return os.path.join(
        str(cache_root),
        "radar",
        "live",
        str(site).strip().upper(),
        str(level_code).strip().upper(),
        str(product_key).strip().upper(),
    )


def _radar_url_dir(site, level_code, product_key) -> str:
    return (
        "/cache/radar/live/"
        f"{str(site).strip().upper()}/"
        f"{str(level_code).strip().upper()}/"
        f"{str(product_key).strip().upper()}"
    )


# ── JSON I/O ──────────────────────────────────────────────────────────────────


def _read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _write_json_atomic(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    os.replace(tmp, path)


# ── Shared index operations ───────────────────────────────────────────────────


def _index_path(dir_path: str) -> str:
    return os.path.join(dir_path, "index.json")


def _keys_path(dir_path: str) -> str:
    return os.path.join(dir_path, "processed_keys.json")


def _load_index_frames(dir_path: str) -> dict:
    index = _read_json(_index_path(dir_path), {})
    frames = index.get("frames") if isinstance(index, dict) else None
    return frames if isinstance(frames, dict) else {}


def _update_index(dir_path: str, frame_key: str, meta: dict) -> None:
    with _write_lock:
        index = _read_json(_index_path(dir_path), {})
        if not isinstance(index, dict):
            index = {}
        frames = index.get("frames")
        if not isinstance(frames, dict):
            frames = {}
        frames[str(frame_key)] = meta
        index["frames"] = frames
        index["updated"] = datetime.now(timezone.utc).isoformat()
        _write_json_atomic(_index_path(dir_path), index)


def _frame_response(dir_path: str, url_dir: str, frame_key: str, entry: dict):
    """Build the API frame dict for one cached frame, or None if PNG missing."""
    png_path = os.path.join(dir_path, f"{frame_key}.png")
    try:
        if not os.path.exists(png_path) or os.path.getsize(png_path) == 0:
            return None
    except OSError:
        return None

    # Renderers write {frame_key}_meta.json / {frame_key}_bounds.json sidecars
    # next to the PNG; use them to fill anything missing from the index entry
    # (e.g. frames produced by the on-demand render path).
    if entry.get("bounds") is None or not entry.get("full_name"):
        sidecar = _read_json(os.path.join(dir_path, f"{frame_key}_meta.json"), {})
        if isinstance(sidecar, dict) and sidecar:
            merged = dict(sidecar)
            merged.update({k: v for k, v in entry.items() if v not in (None, "")})
            entry = merged
        if entry.get("bounds") is None:
            bounds = _read_json(
                os.path.join(dir_path, f"{frame_key}_bounds.json"), None
            )
            if isinstance(bounds, list) and len(bounds) == 4:
                entry = dict(entry)
                entry["bounds"] = bounds

    timestamp = entry.get("timestamp")
    if not timestamp:
        try:
            timestamp = datetime_from_frame_key(frame_key).isoformat()
        except ValueError:
            timestamp = None

    image_url = f"{url_dir}/{frame_key}.png"
    return {
        "frame_key": frame_key,
        "timestamp": timestamp,
        "source_data_key": entry.get("data_key") or frame_key,
        "image_url": image_url,
        "bounds": entry.get("bounds"),
        "full_name": entry.get("full_name", ""),
        "units": entry.get("units", ""),
        "legend": entry.get("legend"),
        "vmin": entry.get("vmin"),
        "vmax": entry.get("vmax"),
        "available_elevations": entry.get("available_elevations") or [],
        "selected_elevation": entry.get("selected_elevation"),
        "render": {"type": "image", "image_url": image_url},
    }


def _list_frames(dir_path: str, url_dir: str) -> list[dict]:
    """List cached frames oldest-first, including PNGs missing from the index."""
    frames_meta = _load_index_frames(dir_path)

    all_keys = set(frames_meta.keys())
    try:
        for name in os.listdir(dir_path):
            if name.endswith(".png"):
                stem = name[:-4]
                try:
                    datetime_from_frame_key(stem)
                except ValueError:
                    continue
                all_keys.add(stem)
    except OSError:
        pass

    out = []
    for frame_key in sorted(all_keys):
        entry = frames_meta.get(frame_key) or {}
        frame = _frame_response(dir_path, url_dir, frame_key, entry)
        if frame is not None:
            out.append(frame)
    return out


def _read_latest(dir_path: str, url_dir: str):
    frames = _list_frames(dir_path, url_dir)
    return frames[-1] if frames else None


def _prune_frames(dir_path: str, keep_n) -> None:
    """Delete frames beyond the newest keep_n (PNG + index entry)."""
    if keep_n is None:
        return
    keep_n = max(1, int(keep_n))

    with _write_lock:
        index = _read_json(_index_path(dir_path), {})
        if not isinstance(index, dict):
            index = {}
        frames = index.get("frames")
        if not isinstance(frames, dict):
            frames = {}

        all_keys = set(frames.keys())
        try:
            for name in os.listdir(dir_path):
                if name.endswith(".png"):
                    stem = name[:-4]
                    try:
                        datetime_from_frame_key(stem)
                    except ValueError:
                        continue
                    all_keys.add(stem)
        except OSError:
            pass

        ordered = sorted(all_keys)
        stale = ordered[:-keep_n] if len(ordered) > keep_n else []
        if not stale:
            return

        for frame_key in stale:
            frames.pop(frame_key, None)
            for suffix in (".png", "_meta.json", "_bounds.json"):
                try:
                    os.remove(os.path.join(dir_path, f"{frame_key}{suffix}"))
                except OSError:
                    pass

        index["frames"] = frames
        index["updated"] = datetime.now(timezone.utc).isoformat()
        _write_json_atomic(_index_path(dir_path), index)


def _read_processed_keys(dir_path: str) -> set:
    data = _read_json(_keys_path(dir_path), [])
    if isinstance(data, dict):
        data = data.get("keys") or []
    return {str(k) for k in data} if isinstance(data, list) else set()


def _write_processed_keys(dir_path: str, keys, keep_n) -> None:
    ordered = sorted(str(k) for k in keys)
    if keep_n is not None and len(ordered) > int(keep_n):
        ordered = ordered[-int(keep_n):]
    with _write_lock:
        _write_json_atomic(_keys_path(dir_path), ordered)


# ── Flat overlay cache (RTMA, MRMS) ───────────────────────────────────────────


def flat_overlay_image_path(cache_root, family, path_parts, frame_key) -> str:
    """Disk path for one overlay frame PNG."""
    return os.path.join(_flat_dir(cache_root, family, path_parts), f"{frame_key}.png")


def flat_overlay_update_index(
    cache_root,
    family,
    path_parts,
    frame_key,
    *,
    bounds=None,
    full_name="",
    units="",
    legend=None,
    vmin=None,
    vmax=None,
    timestamp=None,
    data_key=None,
) -> None:
    """Record (or refresh) one frame's metadata in the product index."""
    _update_index(
        _flat_dir(cache_root, family, path_parts),
        frame_key,
        {
            "bounds": bounds,
            "full_name": full_name,
            "units": units,
            "legend": legend,
            "vmin": vmin,
            "vmax": vmax,
            "timestamp": timestamp,
            "data_key": data_key,
        },
    )


def flat_overlay_read_latest(cache_root, family, path_parts):
    """Return the newest cached frame meta (with render.image_url), or None."""
    return _read_latest(
        _flat_dir(cache_root, family, path_parts), _flat_url_dir(family, path_parts)
    )


def flat_overlay_list_frames(cache_root, family, path_parts) -> list[dict]:
    """Return cached frames oldest-first; only frames whose PNG exists."""
    return _list_frames(
        _flat_dir(cache_root, family, path_parts), _flat_url_dir(family, path_parts)
    )


def flat_overlay_prune_frames(cache_root, family, path_parts, keep_n) -> None:
    """Retain only the newest keep_n frames for a product."""
    _prune_frames(_flat_dir(cache_root, family, path_parts), keep_n)


def flat_overlay_read_processed_keys(cache_root, family, path_parts) -> set:
    """Return the set of source data keys already rendered (dedup gate)."""
    return _read_processed_keys(_flat_dir(cache_root, family, path_parts))


def flat_overlay_write_processed_keys(
    cache_root, family, path_parts, processed_keys, keep_n=30
) -> None:
    """Persist the dedup key set, trimmed to the newest keep_n entries."""
    _write_processed_keys(
        _flat_dir(cache_root, family, path_parts), processed_keys, keep_n
    )


def flat_overlay_batch_update_index_and_keys(
    cache_root, family, overlay_metadata, keep_n=30
) -> None:
    """Apply many frame-metadata updates grouped per product directory.

    Each item in overlay_metadata is a dict with: path_parts, frame_key,
    data_key, bounds, full_name, units, legend, vmin, vmax, timestamp
    (as produced by workers/rtma_worker.py).
    """
    grouped: dict[tuple, list[dict]] = {}
    for item in overlay_metadata or []:
        parts = tuple(str(p) for p in (item.get("path_parts") or ()))
        if not parts or not item.get("frame_key"):
            continue
        grouped.setdefault(parts, []).append(item)

    for parts, items in grouped.items():
        for item in items:
            flat_overlay_update_index(
                cache_root,
                family,
                parts,
                str(item["frame_key"]),
                bounds=item.get("bounds"),
                full_name=item.get("full_name", ""),
                units=item.get("units", ""),
                legend=item.get("legend"),
                vmin=item.get("vmin"),
                vmax=item.get("vmax"),
                timestamp=item.get("timestamp"),
                data_key=item.get("data_key"),
            )
        new_keys = {str(i["data_key"]) for i in items if i.get("data_key")}
        if new_keys:
            existing = flat_overlay_read_processed_keys(cache_root, family, parts)
            flat_overlay_write_processed_keys(
                cache_root, family, parts, existing | new_keys, keep_n
            )


# ── Live radar cache ──────────────────────────────────────────────────────────


def radar_overlay_image_path(
    cache_root, site, level_code, product_key, frame_key
) -> str:
    """Disk path for one live radar frame PNG."""
    return os.path.join(
        _radar_dir(cache_root, site, level_code, product_key), f"{frame_key}.png"
    )


def radar_update_index(
    cache_root,
    site,
    level_code,
    product_key,
    frame_key,
    *,
    bounds=None,
    full_name="",
    units="",
    legend=None,
    vmin=None,
    vmax=None,
    timestamp=None,
    data_key=None,
    available_elevations=None,
    selected_elevation=None,
) -> None:
    """Record (or refresh) one radar frame's metadata in the site/product index."""
    _update_index(
        _radar_dir(cache_root, site, level_code, product_key),
        frame_key,
        {
            "bounds": bounds,
            "full_name": full_name,
            "units": units,
            "legend": legend,
            "vmin": vmin,
            "vmax": vmax,
            "timestamp": timestamp,
            "data_key": data_key,
            "available_elevations": available_elevations,
            "selected_elevation": selected_elevation,
        },
    )


def radar_read_latest_frame(cache_root, site, level_code, product_key):
    """Return the newest cached radar frame meta, or None."""
    return _read_latest(
        _radar_dir(cache_root, site, level_code, product_key),
        _radar_url_dir(site, level_code, product_key),
    )


def radar_list_frames(cache_root, site, level_code, product_key) -> list[dict]:
    """Return cached radar frames oldest-first; only frames whose PNG exists."""
    return _list_frames(
        _radar_dir(cache_root, site, level_code, product_key),
        _radar_url_dir(site, level_code, product_key),
    )


def radar_prune_frames(cache_root, site, level_code, product_key, keep_n=12) -> None:
    """Retain only the newest keep_n radar frames for a site/product."""
    _prune_frames(_radar_dir(cache_root, site, level_code, product_key), keep_n)


def radar_read_processed_keys(cache_root, site, level_code, product_key) -> set:
    """Return source file names already rendered for a site/product."""
    return _read_processed_keys(_radar_dir(cache_root, site, level_code, product_key))


def radar_write_processed_keys(
    cache_root, site, level_code, product_key, processed_keys, keep_n=30
) -> None:
    """Persist the radar dedup key set, trimmed to the newest keep_n entries."""
    _write_processed_keys(
        _radar_dir(cache_root, site, level_code, product_key), processed_keys, keep_n
    )
