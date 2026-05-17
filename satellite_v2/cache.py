"""Disk cache helpers for Satellite v2."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError

from config.satellite_v2_config import (
    SATELLITE_V2_CACHE_NAMESPACE,
    SATELLITE_V2_RENDER_VERSION,
    normalize_channel,
    normalize_sat_id,
    normalize_sector,
    normalize_source_channel,
)


def namespace_root(cache_root: str | Path) -> Path:
    return Path(cache_root) / SATELLITE_V2_CACHE_NAMESPACE


def catalog_path(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    channel_key: str,
) -> Path:
    return (
        namespace_root(cache_root)
        / "catalog"
        / normalize_sat_id(sat_id)
        / normalize_sector(sector)
        / f"{normalize_channel(channel_key)}.json"
    )


def tile_path(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    channel_key: str,
    frame_key: str,
    z: int,
    x: int,
    y: int,
) -> Path:
    return (
        namespace_root(cache_root)
        / "tiles"
        / SATELLITE_V2_RENDER_VERSION
        / normalize_sat_id(sat_id)
        / normalize_sector(sector)
        / normalize_channel(channel_key)
        / str(frame_key)
        / str(int(z))
        / str(int(x))
        / f"{int(y)}.png"
    )


def negative_tile_marker_path(tile_file: Path) -> Path:
    return Path(str(tile_file) + ".empty.json")


def is_negative_tile_cached(tile_file: Path) -> bool:
    return negative_tile_marker_path(tile_file).exists()


def write_negative_tile_marker(tile_file: Path) -> None:
    marker = negative_tile_marker_path(tile_file)
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {"status": "empty", "created_at": int(time.time())}
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{marker.name}.", suffix=".tmp", dir=str(marker.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, marker)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def clear_negative_tile_marker(tile_file: Path) -> None:
    try:
        negative_tile_marker_path(tile_file).unlink()
    except FileNotFoundError:
        pass


def source_path(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    channel_key: str,
    frame_key: str,
    filename: str,
) -> Path:
    return (
        namespace_root(cache_root)
        / "source"
        / normalize_sat_id(sat_id)
        / normalize_sector(sector)
        / normalize_source_channel(channel_key)
        / str(frame_key)
        / filename
    )


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = Path(str(path) + ".lock")
    # Acquire lock with retry (up to 30 seconds).
    for attempt in range(60):
        try:
            lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(lock_fd)
            break
        except FileExistsError:
            if attempt == 59:
                raise TimeoutError(f"Could not acquire lock on {path} after 30 seconds")
            time.sleep(0.5)

    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    finally:
        # Release lock.
        try:
            lock_path.unlink()
        except OSError:
            pass


def file_age_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    return max(0.0, time.time() - path.stat().st_mtime)


def tile_image_has_content(image: Image.Image) -> bool:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[..., 3]
    visible = alpha > 8
    visible_fraction = float(np.count_nonzero(visible)) / float(visible.size or 1)
    if visible_fraction < 0.01:
        return False

    rgb = rgba[..., :3][visible]
    if rgb.size and int(rgb.max()) <= 2 and float(rgb.std()) < 0.5:
        return False
    return True


def is_valid_tile_file(path: Path) -> bool:
    if not path.exists() or path.stat().st_size <= 0:
        return False
    try:
        with Image.open(path) as image:
            return tile_image_has_content(image)
    except (OSError, UnidentifiedImageError, ValueError):
        return False


def count_frame_tiles(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    channel_key: str,
    frame_key: str,
    zooms: tuple[int, ...],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for zoom in zooms:
        zoom_dir = tile_path(
            cache_root, sat_id, sector, channel_key, frame_key, zoom, 0, 0
        ).parent.parent
        if not zoom_dir.exists():
            counts[str(zoom)] = 0
            continue
        counts[str(zoom)] = sum(
            1
            for item in zoom_dir.glob("*/*.png")
            if item.is_file() and is_valid_tile_file(item)
        )
    return counts


def sample_frame_tiles(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    channel_key: str,
    frame_key: str,
    zooms: tuple[int, ...],
) -> dict[str, dict[str, int]]:
    samples: dict[str, dict[str, int]] = {}
    for zoom in zooms:
        zoom_dir = tile_path(
            cache_root, sat_id, sector, channel_key, frame_key, zoom, 0, 0
        ).parent.parent
        if not zoom_dir.exists():
            continue
        first = next(
            (
                item
                for item in zoom_dir.glob("*/*.png")
                if item.is_file() and is_valid_tile_file(item)
            ),
            None,
        )
        if first is None:
            continue
        try:
            samples[str(zoom)] = {
                "z": int(zoom),
                "x": int(first.parent.name),
                "y": int(first.stem),
            }
        except ValueError:
            continue
    return samples
