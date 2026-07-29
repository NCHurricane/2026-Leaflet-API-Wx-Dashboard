"""Versioned polar artifact for the optional paused-frame Radar WebGL pilot."""

from __future__ import annotations

import json
import os
import re
import struct
from pathlib import Path
from urllib.parse import quote

import numpy as np

MAGIC = b"RWPOLAR1"
PRODUCT = "L2_REF"
VALUE_OFFSET = -32.0
VALUE_SCALE = 0.5
MISSING_CODE = 255
PALETTE_BYTES = 256 * 4
_FRAME_RE = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}$")
_SITE_RE = re.compile(r"^[A-Z0-9]{4}$")


def feature_config() -> dict:
    from config.radar_config import (
        LIVE_RADAR_WEBGL_ACTIVATE_ZOOM,
        LIVE_RADAR_WEBGL_ANIMATION_ENABLED,
        LIVE_RADAR_WEBGL_ARTIFACT_VERSION,
        LIVE_RADAR_WEBGL_ENABLED,
        LIVE_RADAR_WEBGL_MAX_CONCURRENT_LOADS,
        LIVE_RADAR_WEBGL_MIN_FORWARD_TEXTURES,
        LIVE_RADAR_WEBGL_PREFETCH_ZOOM,
        LIVE_RADAR_WEBGL_RELEASE_GRACE_MS,
        LIVE_RADAR_WEBGL_TEXTURE_BUDGET,
    )

    return {
        "enabled": bool(LIVE_RADAR_WEBGL_ENABLED),
        "animation_enabled": bool(
            LIVE_RADAR_WEBGL_ENABLED and LIVE_RADAR_WEBGL_ANIMATION_ENABLED
        ),
        "product": PRODUCT,
        "artifact_version": int(LIVE_RADAR_WEBGL_ARTIFACT_VERSION),
        "prefetch_zoom": int(LIVE_RADAR_WEBGL_PREFETCH_ZOOM),
        "activate_zoom": int(LIVE_RADAR_WEBGL_ACTIVATE_ZOOM),
        "release_grace_ms": int(LIVE_RADAR_WEBGL_RELEASE_GRACE_MS),
        "texture_budget": int(LIVE_RADAR_WEBGL_TEXTURE_BUDGET),
        "min_forward_textures": int(LIVE_RADAR_WEBGL_MIN_FORWARD_TEXTURES),
        "max_concurrent_loads": int(LIVE_RADAR_WEBGL_MAX_CONCURRENT_LOADS),
    }


def _elevation_key(elevation: str | float | None) -> str:
    try:
        angle = float(elevation)
    except (TypeError, ValueError):
        angle = 0.5
    return f"{angle:.1f}".replace(".", "p")


def artifact_path(
    cache_root: str | Path,
    site: str,
    elevation: str | float | None,
    frame_key: str,
) -> Path:
    site_id = str(site or "").strip().upper()
    frame_id = str(frame_key or "").strip()
    if not _SITE_RE.fullmatch(site_id) or not _FRAME_RE.fullmatch(frame_id):
        raise ValueError("Invalid Radar WebGL artifact identity.")
    version = feature_config()["artifact_version"]
    return (
        Path(cache_root)
        / "radar"
        / "webgl"
        / f"v{version}"
        / site_id
        / _elevation_key(elevation)
        / f"{frame_id}.rwp"
    )


def artifact_url(
    site: str,
    elevation: str | float | None,
    frame_key: str,
) -> str:
    return (
        "/api/radar/live/webgl/"
        f"v{feature_config()['artifact_version']}/"
        f"{quote(PRODUCT)}/{quote(str(site).upper())}/"
        f"{quote(_elevation_key(elevation))}/{quote(str(frame_key))}"
    )


def artifact_metadata(
    cache_root: str | Path,
    site: str,
    product: str,
    elevation: str | float | None,
    frame_key: str,
) -> dict | None:
    config = feature_config()
    if not config["enabled"] or str(product).upper() != PRODUCT:
        return None
    try:
        path = artifact_path(cache_root, site, elevation, frame_key)
        size = path.stat().st_size
    except (OSError, ValueError):
        return None
    if size <= 0:
        return None
    return {
        "version": config["artifact_version"],
        "url": artifact_url(site, elevation, frame_key),
        "bytes": size,
    }


def resolve_artifact(
    cache_root: str | Path,
    version: str,
    product: str,
    site: str,
    elevation_key: str,
    frame_key: str,
) -> Path | None:
    config = feature_config()
    if (
        not config["enabled"]
        or str(version).lower() != f"v{config['artifact_version']}"
        or str(product).upper() != PRODUCT
    ):
        return None
    elevation = str(elevation_key or "").strip().lower().replace("p", ".")
    try:
        path = artifact_path(cache_root, site, elevation, frame_key)
    except ValueError:
        return None
    try:
        resolved = path.resolve(strict=True)
        root = (Path(cache_root) / "radar" / "webgl").resolve(strict=True)
    except OSError:
        return None
    if root not in resolved.parents or not resolved.is_file():
        return None
    return resolved


def _palette_row(product_cfg: dict) -> np.ndarray:
    from config.radar_colortable_utils import get_radar_colortable
    from matplotlib.colors import Normalize

    vmin = float(product_cfg.get("vmin", -30.0))
    vmax = float(product_cfg.get("vmax", 90.0))
    palette = str(product_cfg.get("palette") or "BR")
    cmap = get_radar_colortable(palette, vmin, vmax)["cmap"]
    values = VALUE_OFFSET + np.arange(256, dtype=np.float32) * VALUE_SCALE
    rgba = cmap(Normalize(vmin=vmin, vmax=vmax)(values), bytes=True)
    rgba = np.asarray(rgba, dtype=np.uint8)
    rgba[MISSING_CODE] = (0, 0, 0, 0)
    return rgba.reshape(-1)


def build_artifact(
    radar,
    field_name: str,
    sweep: int,
    site: str,
    frame_key: str,
    selected_elevation: str | float | None,
    product_cfg: dict,
) -> tuple[dict, bytes]:
    sweep_slice = radar.get_slice(int(sweep))
    field = np.ma.array(radar.fields[field_name]["data"])[sweep_slice]
    azimuth = np.asarray(radar.azimuth["data"][sweep_slice], dtype=np.float64)
    if field.ndim != 2 or field.shape[0] != azimuth.size:
        raise ValueError("Radar sweep geometry does not match its field values.")

    order = np.argsort(np.mod(azimuth, 360.0), kind="stable")
    field = field[order]
    azimuth = np.mod(azimuth[order], 360.0)
    ray_count, gate_count = field.shape
    texture_width = max(gate_count + 2, PALETTE_BYTES)
    texture_height = ray_count + 1
    texture = np.zeros((texture_height, texture_width), dtype=np.uint8)

    azimuth_code = np.rint(azimuth * 100.0).astype(np.uint16)
    texture[:ray_count, 0] = azimuth_code & 0xFF
    texture[:ray_count, 1] = azimuth_code >> 8

    valid = ~np.ma.getmaskarray(field)
    values = np.asarray(np.ma.filled(field, np.nan), dtype=np.float32)
    valid &= np.isfinite(values)
    codes = np.full(values.shape, MISSING_CODE, dtype=np.uint8)
    encoded = np.rint((values[valid] - VALUE_OFFSET) / VALUE_SCALE)
    codes[valid] = np.clip(encoded, 0, MISSING_CODE - 1).astype(np.uint8)
    texture[:ray_count, 2 : gate_count + 2] = codes
    texture[ray_count, :PALETTE_BYTES] = _palette_row(product_cfg)

    ranges = np.asarray(radar.range["data"], dtype=np.float64)
    if ranges.size < gate_count:
        raise ValueError("Radar range geometry is shorter than its field values.")
    range_step = float(np.median(np.diff(ranges[:gate_count]))) if gate_count > 1 else 1.0
    valid_values = values[valid]
    decoded = VALUE_OFFSET + codes[valid].astype(np.float32) * VALUE_SCALE
    quantization_error = (
        float(np.max(np.abs(valid_values - decoded))) if valid_values.size else 0.0
    )
    header = {
        "version": feature_config()["artifact_version"],
        "product": PRODUCT,
        "site": str(site).upper(),
        "frame_key": str(frame_key),
        "selected_elevation": float(selected_elevation or 0.5),
        "radar_lat": float(np.asarray(radar.latitude["data"]).flat[0]),
        "radar_lon": float(np.asarray(radar.longitude["data"]).flat[0]),
        "ray_count": int(ray_count),
        "gate_count": int(gate_count),
        "texture_width": int(texture_width),
        "texture_height": int(texture_height),
        "range_start_m": float(ranges[0]),
        "range_step_m": range_step,
        "value_offset": VALUE_OFFSET,
        "value_scale": VALUE_SCALE,
        "missing_code": MISSING_CODE,
        "max_quantization_error": quantization_error,
    }
    return header, texture.tobytes(order="C")


def write_artifact(
    cache_root: str | Path,
    site: str,
    frame_key: str,
    selected_elevation: str | float | None,
    radar,
    field_name: str,
    sweep: int,
    product_cfg: dict,
) -> Path | None:
    if not feature_config()["enabled"]:
        return None
    header, texture = build_artifact(
        radar,
        field_name,
        sweep,
        site,
        frame_key,
        selected_elevation,
        product_cfg,
    )
    header_bytes = json.dumps(
        header, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    payload = MAGIC + struct.pack("<I", len(header_bytes)) + header_bytes + texture
    path = artifact_path(cache_root, site, selected_elevation, frame_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def read_artifact(path: str | Path) -> tuple[dict, bytes]:
    payload = Path(path).read_bytes()
    if payload[: len(MAGIC)] != MAGIC:
        raise ValueError("Unsupported Radar WebGL artifact.")
    offset = len(MAGIC)
    header_size = struct.unpack_from("<I", payload, offset)[0]
    offset += 4
    header = json.loads(payload[offset : offset + header_size].decode("utf-8"))
    texture = payload[offset + header_size :]
    expected = int(header["texture_width"]) * int(header["texture_height"])
    if len(texture) != expected:
        raise ValueError("Radar WebGL artifact payload is incomplete.")
    return header, texture


def prune_artifacts(
    cache_root: str | Path,
    site: str,
    elevation: str | float | None,
    keep_n: int,
) -> None:
    directory = artifact_path(
        cache_root, site, elevation, "2000_01_01_00_00_00"
    ).parent
    if not directory.exists():
        return
    files = sorted(directory.glob("*.rwp"), key=lambda path: path.name)
    for path in files[: max(0, len(files) - max(1, int(keep_n)))]:
        path.unlink(missing_ok=True)
