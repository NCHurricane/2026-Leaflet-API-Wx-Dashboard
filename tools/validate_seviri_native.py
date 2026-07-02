"""Standalone validation for the native SEVIRI .nat parser (no satpy).

Given a Meteosat-9 IODC Level 1.5 .nat file (or --download to fetch the
newest via the EUMETSAT provider), parses/calibrates one channel with
satellite_v2.seviri_nat, wraps it in the shared SourceRaster/GDAL-warp
renderer, and writes PNG proofs (ghosted basemap overlay for coastline
alignment) plus numeric sanity stats.

Usage:
  .venv\\Scripts\\python.exe tools\\validate_seviri_native.py --download --out DIR
  .venv\\Scripts\\python.exe tools\\validate_seviri_native.py --nat FILE --out DIR
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from config.satellite_v2_config import source_channels_for_product  # noqa: E402
from satellite_v2.renderer import SatelliteTileRenderer, SourceRaster  # noqa: E402
from satellite_v2.seviri_nat import load_seviri_raster  # noqa: E402
from validate_ahi_native import _tile_range, fetch_basemap  # noqa: E402


def _newest_nat(out_dir: Path) -> Path:
    from satellite_v2.provider_eumetsat import (
        download_product_source_frames,
        list_recent_frames,
    )

    frames = list_recent_frames("meteosat9", "FULLDISK", "Channel13", 2, 4)
    if not frames:
        raise RuntimeError("No recent Meteosat-9 IODC frames found.")
    frame = frames[-1]
    print(f"newest frame: {frame.frame_key} ({frame.source_key})")
    paths = download_product_source_frames(
        out_dir, "meteosat9", "FULLDISK", "Channel13", frame
    )
    return next(iter(paths.values()))


def _ghost_view(
    renderer: SatelliteTileRenderer,
    z: int,
    bounds: tuple[float, float, float, float],
    out_path: Path,
) -> None:
    west, south, east, north = bounds
    x_min, y_min, x_max, y_max = _tile_range(z, west, south, east, north)
    tiles = (x_max - x_min + 1) * (y_max - y_min + 1)
    print(f"  rendering z{z} x{x_min}-{x_max} y{y_min}-{y_max} ({tiles} tiles)")
    satellite = renderer.render_zoom_canvas(z, x_min, y_min, x_max, y_max)
    base = fetch_basemap(z, x_min, y_min, x_max, y_max)
    base.putalpha(115)
    satellite = satellite.convert("RGBA")
    satellite.alpha_composite(base)
    satellite.convert("RGB").save(out_path)
    print(f"  wrote {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nat", type=Path, help="Existing .nat file to parse")
    parser.add_argument(
        "--download", action="store_true", help="Fetch the newest IODC frame"
    )
    parser.add_argument(
        "--channel", default="Channel13", help="ABI-named product channel"
    )
    parser.add_argument("--out", type=Path, required=True, help="Working directory")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    if args.nat:
        nat_path = args.nat
    elif args.download:
        nat_path = _newest_nat(args.out)
    else:
        parser.error("Provide --nat FILE or --download.")

    print(f"parsing {nat_path.name} channel {args.channel} (native, no satpy)...")
    raster = load_seviri_raster(nat_path, args.channel)
    values = raster.values
    finite = np.isfinite(values)
    print(f"  grid: {values.shape[1]}x{values.shape[0]}")
    print(
        f"  values: min={np.nanmin(values):.2f} max={np.nanmax(values):.2f} "
        f"mean={np.nanmean(values):.2f} finite={finite.mean() * 100:.1f}%"
    )

    source_channel = source_channels_for_product(args.channel)[0]
    renderer = SatelliteTileRenderer(
        product_key=args.channel,
        source_rasters={
            source_channel: SourceRaster(
                cmi=values,
                src_transform=raster.src_transform,
                src_crs=raster.src_crs,
            )
        },
    )

    tag = f"seviri_{args.channel.lower()}_{nat_path.stem[-24:-3]}"
    # Native quicklook.
    quick = values[::4, ::4]
    if float(np.nanmax(quick)) > 5.0:  # brightness temperature
        norm = np.clip((310.0 - quick) / (310.0 - 180.0), 0.0, 1.0)
    else:
        norm = np.clip(quick, 0.0, 1.0)
    gray = np.where(np.isfinite(norm), norm * 255.0, 0.0).astype(np.uint8)
    Image.fromarray(gray, mode="L").save(args.out / f"{tag}_native.png")
    print(f"  wrote {args.out / f'{tag}_native.png'}")

    # Disk overview + India/Horn-of-Africa coastline checks from 45.5E.
    _ghost_view(renderer, 3, (-15.0, -62.0, 106.0, 62.0), args.out / f"{tag}_disk_z3.png")
    _ghost_view(renderer, 5, (42.0, 0.0, 80.0, 25.0), args.out / f"{tag}_india_z5.png")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
