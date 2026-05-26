from collections import OrderedDict
from threading import Lock
import time
import os
import json


_CACHE = OrderedDict()
_LOCK = Lock()
_DEFAULT_MAX_ENTRIES = 2048


def _normalize_key(namespace, key):
    if isinstance(key, (list, tuple)):
        key_part = tuple(key)
    else:
        key_part = (key,)
    return (str(namespace),) + key_part


def _prune_expired(now_ts):
    expired_keys = [
        entry_key
        for entry_key, entry in _CACHE.items()
        if entry["expires_at"] <= now_ts
    ]
    for entry_key in expired_keys:
        _CACHE.pop(entry_key, None)


def _prune_size(max_entries):
    while len(_CACHE) > max_entries:
        _CACHE.popitem(last=False)


def cached_call(
    namespace,
    key,
    fetch_fn,
    ttl_seconds=30,
    max_entries=_DEFAULT_MAX_ENTRIES,
):
    now_ts = time.time()
    entry_key = _normalize_key(namespace, key)

    with _LOCK:
        _prune_expired(now_ts)
        entry = _CACHE.get(entry_key)
        if entry is not None:
            _CACHE.move_to_end(entry_key)
            value = entry["value"]
            return list(value) if isinstance(value, list) else value

    value = fetch_fn()

    with _LOCK:
        _CACHE[entry_key] = {
            "expires_at": now_ts + max(float(ttl_seconds), 1.0),
            "value": value,
        }
        _CACHE.move_to_end(entry_key)
        _prune_size(max_entries)

    return list(value) if isinstance(value, list) else value


def cache_stats():
    now_ts = time.time()
    with _LOCK:
        _prune_expired(now_ts)
        return {"entries": len(_CACHE)}


# ═════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS — formerly duplicated across radar, lightning, etc.
# ═════════════════════════════════════════════════════════════════════════════


def load_json_config(directory, filename, default=None):
    """Load a JSON configuration file from *directory*.

    Parameters
    ----------
    directory : str
        Folder containing the file (typically the calling module's dir).
    filename : str
        Name of the JSON file.
    default : any
        Value returned when the file cannot be loaded.

    Returns
    -------
    any
        Parsed JSON content, or *default* on failure.
    """
    path = os.path.join(directory, filename)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"WARNING: Could not load {filename}: {e}")
        return default


def check_dependencies(required):
    """Verify that all packages in *required* are importable.

    Parameters
    ----------
    required : dict[str, str]
        Mapping of ``{module_name: pip_package_name}``.

    Returns
    -------
    list[str]
        pip package names that could not be imported.
    """
    missing = []
    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    return missing
