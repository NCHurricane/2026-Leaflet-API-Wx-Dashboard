"""Versioned product-scoped polar artifacts for optional Radar WebGL layers."""

from __future__ import annotations

import json
import os
import re
import struct
from pathlib import Path
from urllib.parse import quote, urlencode

import numpy as np

MAGIC = b"RWPOLAR1"
PRODUCT = "L2_REF"
VALUE_OFFSET = -32.0
VALUE_SCALE = 0.5
MISSING_CODE = 255
SUPPORTED_PRODUCTS = frozenset({"L2_REF", "L2_VEL", "L2_SRV"})
VELOCITY_PRODUCTS = frozenset({"L2_VEL", "L2_SRV"})
U8_PALETTE_ENTRIES = 256
U16_PALETTE_ENTRIES = 512
U16_MISSING_CODE = 65535
_FRAME_RE = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}$")
_SITE_RE = re.compile(r"^[A-Z0-9]{4}$")
_VARIANT_RE = re.compile(r"^[a-z0-9_]{1,96}$")


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
        LIVE_RADAR_WEBGL_VELOCITY_ANIMATION_ENABLED,
        LIVE_RADAR_WEBGL_VELOCITY_ENABLED,
    )

    enabled = bool(LIVE_RADAR_WEBGL_ENABLED)
    velocity_enabled = bool(enabled and LIVE_RADAR_WEBGL_VELOCITY_ENABLED)
    products = [PRODUCT]
    if velocity_enabled:
        products.extend(sorted(VELOCITY_PRODUCTS))
    animation_products = []
    if enabled and LIVE_RADAR_WEBGL_ANIMATION_ENABLED:
        animation_products.append(PRODUCT)
    if velocity_enabled and LIVE_RADAR_WEBGL_VELOCITY_ANIMATION_ENABLED:
        animation_products.extend(sorted(VELOCITY_PRODUCTS))
    return {
        "enabled": enabled,
        "animation_enabled": bool(
            enabled and LIVE_RADAR_WEBGL_ANIMATION_ENABLED
        ),
        "product": PRODUCT,
        "products": products if enabled else [],
        "animation_products": animation_products,
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


def _product_key(product: str) -> str:
    product_id = str(product or "").strip().upper()
    if product_id not in SUPPORTED_PRODUCTS:
        raise ValueError("Unsupported Radar WebGL product.")
    return product_id


def _variant_key(product: str, variant: str | None = None) -> str:
    product_id = _product_key(product)
    if product_id != "L2_SRV":
        return "default"
    value = str(variant or "").strip().lower()
    if not value:
        from config.radar_config import LIVE_RADAR_PRODUCTS

        value = str(
            LIVE_RADAR_PRODUCTS["L2_SRV"].get("cache_variant") or "default"
        ).strip().lower()
    if not _VARIANT_RE.fullmatch(value):
        raise ValueError("Invalid Radar WebGL artifact variant.")
    return value


def _product_enabled(product: str) -> bool:
    try:
        product_id = _product_key(product)
    except ValueError:
        return False
    return product_id in feature_config()["products"]


def artifact_path(
    cache_root: str | Path,
    site: str,
    elevation: str | float | None,
    frame_key: str,
    product: str = PRODUCT,
    variant: str | None = None,
) -> Path:
    product_id = _product_key(product)
    variant_id = _variant_key(product_id, variant)
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
        / product_id
        / variant_id
        / site_id
        / _elevation_key(elevation)
        / f"{frame_id}.rwp"
    )


def artifact_url(
    site: str,
    elevation: str | float | None,
    frame_key: str,
    product: str = PRODUCT,
    variant: str | None = None,
) -> str:
    product_id = _product_key(product)
    variant_id = _variant_key(product_id, variant)
    url = (
        "/api/radar/live/webgl/"
        f"v{feature_config()['artifact_version']}/"
        f"{quote(product_id)}/{quote(str(site).upper())}/"
        f"{quote(_elevation_key(elevation))}/{quote(str(frame_key))}"
    )
    return f"{url}?{urlencode({'variant': variant_id})}"


def artifact_metadata(
    cache_root: str | Path,
    site: str,
    product: str,
    elevation: str | float | None,
    frame_key: str,
    variant: str | None = None,
) -> dict | None:
    config = feature_config()
    product_id = str(product or "").strip().upper()
    if not config["enabled"] or not _product_enabled(product_id):
        return None
    try:
        variant_id = _variant_key(product_id, variant)
        path = artifact_path(
            cache_root, site, elevation, frame_key, product_id, variant_id
        )
        size = path.stat().st_size
    except (OSError, ValueError):
        return None
    if size <= 0:
        return None
    return {
        "version": config["artifact_version"],
        "product": product_id,
        "variant": variant_id,
        "url": artifact_url(
            site, elevation, frame_key, product_id, variant_id
        ),
        "bytes": size,
    }


def resolve_artifact(
    cache_root: str | Path,
    version: str,
    product: str,
    site: str,
    elevation_key: str,
    frame_key: str,
    variant: str | None = None,
) -> Path | None:
    config = feature_config()
    product_id = str(product or "").strip().upper()
    if (
        not config["enabled"]
        or str(version).lower() != f"v{config['artifact_version']}"
        or not _product_enabled(product_id)
    ):
        return None
    elevation = str(elevation_key or "").strip().lower().replace("p", ".")
    try:
        path = artifact_path(
            cache_root,
            site,
            elevation,
            frame_key,
            product_id,
            _variant_key(product_id, variant),
        )
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


def _encoding(product: str, product_cfg: dict) -> dict:
    product_id = _product_key(product)
    if product_id == PRODUCT:
        return {
            "code_bytes": 1,
            "missing_code": MISSING_CODE,
            "palette_entries": U8_PALETTE_ENTRIES,
            "value_offset": VALUE_OFFSET,
            "value_scale": VALUE_SCALE,
        }
    vmin = float(product_cfg["vmin"])
    vmax = float(product_cfg["vmax"])
    return {
        "code_bytes": 2,
        "missing_code": U16_MISSING_CODE,
        "palette_entries": U16_PALETTE_ENTRIES,
        "value_offset": vmin,
        "value_scale": (vmax - vmin) / float(U16_MISSING_CODE - 1),
    }


def _palette_row(product_cfg: dict, encoding: dict) -> np.ndarray:
    from config.radar_colortable_utils import get_radar_colortable
    from matplotlib.colors import Normalize

    vmin = float(product_cfg.get("vmin", -30.0))
    vmax = float(product_cfg.get("vmax", 90.0))
    palette = str(product_cfg.get("palette") or "BR")
    cmap = get_radar_colortable(palette, vmin, vmax)["cmap"]
    entries = int(encoding["palette_entries"])
    if int(encoding["code_bytes"]) == 1:
        values = (
            float(encoding["value_offset"])
            + np.arange(entries, dtype=np.float32) * float(encoding["value_scale"])
        )
        normalized = Normalize(vmin=vmin, vmax=vmax)(values)
    else:
        normalized = (np.arange(entries, dtype=np.float32) + 0.5) / entries
    rgba = cmap(normalized, bytes=True)
    rgba = np.asarray(rgba, dtype=np.uint8)
    if int(encoding["code_bytes"]) == 1:
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
    product: str = PRODUCT,
) -> tuple[dict, bytes]:
    product_id = _product_key(product)
    encoding = _encoding(product_id, product_cfg)
    sweep_slice = radar.get_slice(int(sweep))
    field = np.ma.array(radar.fields[field_name]["data"])[sweep_slice]
    azimuth = np.asarray(radar.azimuth["data"][sweep_slice], dtype=np.float64)
    if field.ndim != 2 or field.shape[0] != azimuth.size:
        raise ValueError("Radar sweep geometry does not match its field values.")

    order = np.argsort(np.mod(azimuth, 360.0), kind="stable")
    field = field[order]
    azimuth = np.mod(azimuth[order], 360.0)
    ray_count, gate_count = field.shape
    code_bytes = int(encoding["code_bytes"])
    palette_bytes = int(encoding["palette_entries"]) * 4
    texture_width = max(gate_count * code_bytes + 2, palette_bytes)
    texture_height = ray_count + 1
    texture = np.zeros((texture_height, texture_width), dtype=np.uint8)

    azimuth_code = np.rint(azimuth * 100.0).astype(np.uint16)
    texture[:ray_count, 0] = azimuth_code & 0xFF
    texture[:ray_count, 1] = azimuth_code >> 8

    valid = ~np.ma.getmaskarray(field)
    values = np.asarray(np.ma.filled(field, np.nan), dtype=np.float32)
    valid &= np.isfinite(values)
    value_offset = float(encoding["value_offset"])
    value_scale = float(encoding["value_scale"])
    missing_code = int(encoding["missing_code"])
    if code_bytes == 2:
        valid &= values >= float(product_cfg["vmin"])
    code_dtype = np.uint8 if code_bytes == 1 else np.uint16
    codes = np.full(values.shape, missing_code, dtype=code_dtype)
    encoded = np.rint((values[valid] - value_offset) / value_scale)
    codes[valid] = np.clip(encoded, 0, missing_code - 1).astype(code_dtype)
    if code_bytes == 1:
        texture[:ray_count, 2 : gate_count + 2] = codes
    else:
        texture[:ray_count, 2 : 2 + gate_count * 2 : 2] = codes & 0xFF
        texture[:ray_count, 3 : 2 + gate_count * 2 : 2] = codes >> 8
    texture[ray_count, :palette_bytes] = _palette_row(product_cfg, encoding)

    ranges = np.asarray(radar.range["data"], dtype=np.float64)
    if ranges.size < gate_count:
        raise ValueError("Radar range geometry is shorter than its field values.")
    range_step = float(np.median(np.diff(ranges[:gate_count]))) if gate_count > 1 else 1.0
    valid_values = values[valid]
    clipped_values = np.minimum(valid_values, float(product_cfg["vmax"]))
    decoded = value_offset + codes[valid].astype(np.float64) * value_scale
    quantization_error = (
        float(np.max(np.abs(clipped_values - decoded)))
        if valid_values.size
        else 0.0
    )
    header = {
        "version": feature_config()["artifact_version"],
        "product": product_id,
        "variant": _variant_key(
            product_id, str(product_cfg.get("cache_variant") or "") or None
        ),
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
        "code_bytes": code_bytes,
        "palette_entries": int(encoding["palette_entries"]),
        "value_offset": value_offset,
        "value_scale": value_scale,
        "missing_code": missing_code,
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
    product: str = PRODUCT,
) -> Path | None:
    product_id = _product_key(product)
    if not _product_enabled(product_id):
        return None
    header, texture = build_artifact(
        radar,
        field_name,
        sweep,
        site,
        frame_key,
        selected_elevation,
        product_cfg,
        product_id,
    )
    header_bytes = json.dumps(
        header, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    payload = MAGIC + struct.pack("<I", len(header_bytes)) + header_bytes + texture
    variant = str(product_cfg.get("cache_variant") or "") or None
    path = artifact_path(
        cache_root,
        site,
        selected_elevation,
        frame_key,
        product_id,
        variant,
    )
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
    product: str = PRODUCT,
    variant: str | None = None,
) -> None:
    directory = artifact_path(
        cache_root,
        site,
        elevation,
        "2000_01_01_00_00_00",
        product,
        variant,
    ).parent
    if not directory.exists():
        return
    files = sorted(directory.glob("*.rwp"), key=lambda path: path.name)
    for path in files[: max(0, len(files) - max(1, int(keep_n)))]:
        path.unlink(missing_ok=True)
