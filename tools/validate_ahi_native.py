"""Standalone validation for the native AHI HSD parser (no satpy).

Downloads the most recent complete Himawari-9 FULLDISK timeslot for one band
from the public noaa-himawari9 bucket, parses/calibrates it with
satellite_v2.ahi_hsd, wraps the result in the existing GOES
SourceRaster/GDAL-warp renderer, and writes PNG proofs (composited over Carto
dark basemap tiles so coastline alignment is visually checkable) plus numeric
sanity stats.

Usage:
  .venv\\Scripts\\python.exe tools\\validate_ahi_native.py --band 13 --out DIR
"""

from __future__ import annotations

import argparse
import io
import math
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import numpy as np
from botocore import UNSIGNED
from botocore.config import Config
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from config.satellite_v2_config import source_channels_for_product  # noqa: E402
from satellite_v2.ahi_hsd import AhiRaster, load_ahi_raster  # noqa: E402
from satellite_v2.renderer import SatelliteTileRenderer, SourceRaster  # noqa: E402

BUCKET = "noaa-himawari9"
FULLDISK_SEGMENTS = 10
BASEMAP_URL = "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
TILE_SIZE = 256


def _s3_client():
    return boto3.client(
        "s3",
        config=Config(
            signature_version=UNSIGNED,
            connect_timeout=10,
            read_timeout=60,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def find_latest_slot(s3, band: int, max_back: int = 24) -> tuple[datetime, list[str]]:
    """Walk back through 10-minute FLDK timeslots until one has all segments."""
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    now -= timedelta(minutes=now.minute % 10)
    token = f"_B{band:02d}_FLDK"
    for step in range(1, max_back + 1):
        slot = now - timedelta(minutes=10 * step)
        prefix = f"AHI-L1b-FLDK/{slot:%Y/%m/%d/%H%M}/"
        keys: list[str] = []
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = str(obj.get("Key") or "")
                if token in key and key.endswith(".DAT.bz2"):
                    keys.append(key)
        if len(keys) >= FULLDISK_SEGMENTS:
            return slot, sorted(keys)
    raise RuntimeError(
        f"No complete B{band:02d} FLDK timeslot found in the last "
        f"{max_back * 10} minutes."
    )


def download_segments(s3, keys: list[str], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for key in keys:
        target = out_dir / key.rsplit("/", 1)[-1]
        if not target.exists() or target.stat().st_size <= 0:
            print(f"  downloading {key}")
            s3.download_file(BUCKET, key, str(target))
        paths.append(target)
    return paths


def _lon_to_tile_x(lon: float, z: int) -> float:
    return (lon + 180.0) / 360.0 * (2**z)


def _lat_to_tile_y(lat: float, z: int) -> float:
    rad = math.radians(lat)
    return (1.0 - math.asinh(math.tan(rad)) / math.pi) / 2.0 * (2**z)


def _tile_range(
    z: int, west: float, south: float, east: float, north: float
) -> tuple[int, int, int, int]:
    x_min = max(0, int(_lon_to_tile_x(west, z)))
    x_max = min(2**z - 1, int(_lon_to_tile_x(east, z)))
    y_min = max(0, int(_lat_to_tile_y(north, z)))
    y_max = min(2**z - 1, int(_lat_to_tile_y(south, z)))
    return x_min, y_min, x_max, y_max


def fetch_basemap(z: int, x_min: int, y_min: int, x_max: int, y_max: int) -> Image.Image:
    canvas = Image.new(
        "RGBA",
        ((x_max - x_min + 1) * TILE_SIZE, (y_max - y_min + 1) * TILE_SIZE),
        (24, 24, 32, 255),
    )
    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            url = BASEMAP_URL.format(z=z, x=x, y=y)
            request = urllib.request.Request(
                url, headers={"User-Agent": "nch-dashboard-ahi-validation"}
            )
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    tile = Image.open(io.BytesIO(response.read())).convert("RGBA")
                canvas.paste(tile, ((x - x_min) * TILE_SIZE, (y - y_min) * TILE_SIZE))
            except OSError as exc:
                print(f"  basemap tile {z}/{x}/{y} failed: {exc}")
    return canvas


def render_view(
    renderer: SatelliteTileRenderer,
    z: int,
    bounds: tuple[float, float, float, float],
    out_path: Path,
) -> None:
    west, south, east, north = bounds
    x_min, y_min, x_max, y_max = _tile_range(z, west, south, east, north)
    print(
        f"  rendering z{z} tiles x{x_min}-{x_max} y{y_min}-{y_max} "
        f"({(x_max - x_min + 1) * (y_max - y_min + 1)} tiles)"
    )
    satellite = renderer.render_zoom_canvas(z, x_min, y_min, x_max, y_max)
    base = fetch_basemap(z, x_min, y_min, x_max, y_max)
    base.alpha_composite(satellite)
    base.convert("RGB").save(out_path)
    print(f"  wrote {out_path}")


def native_quicklook(raster: AhiRaster, out_path: Path) -> None:
    values = raster.values[::5, ::5]
    if raster.header.band_number >= 7:
        # Invert brightness temperature so cold cloud tops render bright.
        norm = np.clip((310.0 - values) / (310.0 - 180.0), 0.0, 1.0)
    else:
        norm = np.clip(values, 0.0, 1.0)
    gray = np.where(np.isfinite(norm), norm * 255.0, 0.0).astype(np.uint8)
    Image.fromarray(gray, mode="L").save(out_path)
    print(f"  wrote {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band", type=int, default=13, help="AHI band number 1-16")
    parser.add_argument("--out", type=Path, required=True, help="Working directory")
    args = parser.parse_args()

    s3 = _s3_client()
    print(f"Locating latest complete B{args.band:02d} FLDK timeslot...")
    slot, keys = find_latest_slot(s3, args.band)
    print(f"  slot {slot:%Y-%m-%d %H:%M}Z with {len(keys)} segments")

    segment_dir = args.out / f"b{args.band:02d}_{slot:%Y%m%d%H%M}"
    paths = download_segments(s3, keys, segment_dir)

    print("Parsing + calibrating (native, no satpy)...")
    raster = load_ahi_raster(paths)
    header = raster.header
    finite = np.isfinite(raster.values)
    print(f"  observation_area={header.observation_area}")
    print(f"  band={header.band_number} cw={header.central_wavelength_um:.4f} um")
    print(
        f"  grid={raster.values.shape[1]}x{raster.values.shape[0]} "
        f"(stride {raster.stride} from {header.n_cols} cols)"
    )
    print(
        f"  sub_lon={header.sub_lon} CFAC={header.cfac} LFAC={header.lfac} "
        f"COFF={header.coff} LOFF={header.loff}"
    )
    print(
        f"  distance={header.distance_km} km req={header.earth_eq_radius_km} km "
        f"rpol={header.earth_polar_radius_km} km"
    )
    print(
        f"  values: min={np.nanmin(raster.values):.2f} "
        f"max={np.nanmax(raster.values):.2f} mean={np.nanmean(raster.values):.2f} "
        f"finite={finite.mean() * 100.0:.1f}%"
    )

    product_key = "Channel13" if header.band_number >= 7 else "Channel02"
    source_channel = source_channels_for_product(product_key)[0]
    renderer = SatelliteTileRenderer(
        product_key=product_key,
        source_rasters={
            source_channel: SourceRaster(
                cmi=raster.values,
                src_transform=raster.src_transform,
                src_crs=raster.src_crs,
            )
        },
    )

    tag = f"ahi_b{header.band_number:02d}_{slot:%Y%m%d%H%M}"
    print("Rendering proofs through the shared GDAL-warp path...")
    native_quicklook(raster, args.out / f"{tag}_native.png")
    render_view(renderer, 3, (45.0, -62.0, 179.9, 62.0), args.out / f"{tag}_disk_z3.png")
    render_view(renderer, 6, (128.0, 30.0, 148.0, 45.0), args.out / f"{tag}_japan_z6.png")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
