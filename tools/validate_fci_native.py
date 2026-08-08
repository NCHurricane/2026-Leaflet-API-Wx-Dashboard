r"""Validate native Meteosat-12 FCI chunks through the shared tile renderer.

Supply an existing completed ``manifest.json`` or use ``--download`` with
configured EUMETSAT credentials. The tool parses one ABI-named channel,
reports numeric sanity data, and writes native and coastline-alignment PNGs.

Usage:
  .venv\Scripts\python.exe tools\validate_fci_native.py --manifest FILE --out DIR
  .venv\Scripts\python.exe tools\validate_fci_native.py --download --out DIR
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from config.satellite_v2_config import source_channels_for_product  # noqa: E402
from satellite_v2.fci_nc import load_fci_raster  # noqa: E402
from satellite_v2.renderer import SatelliteTileRenderer, SourceRaster  # noqa: E402
from validate_ahi_native import fetch_basemap, tile_range  # noqa: E402


def chunk_paths_from_manifest(manifest_path: Path) -> list[Path]:
    """Return all completed FCI body chunks named by a provider manifest."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [manifest_path.parent / str(name) for name in payload.get("chunks", [])]
    if not paths:
        raise ValueError(f"FCI manifest contains no chunks: {manifest_path}")
    missing = [path.name for path in paths if not path.is_file() or path.stat().st_size <= 0]
    if missing:
        raise FileNotFoundError(f"FCI manifest has missing/empty chunks: {', '.join(missing)}")
    return paths


def newest_manifest(out_dir: Path, channel: str) -> tuple[Path, str]:
    from satellite_v2.provider_eumetsat import (
        download_product_source_frames,
        list_recent_frames,
    )

    frames = list_recent_frames("meteosat12", "FULLDISK", channel, 2, 4)
    if not frames:
        raise RuntimeError("No recent Meteosat-12 FCI frames found.")
    frame = frames[-1]
    paths = download_product_source_frames(
        out_dir, "meteosat12", "FULLDISK", channel, frame
    )
    primary = next(iter(paths.values()))
    return primary.parent / "manifest.json", frame.frame_key


def render_ghost_view(
    renderer: SatelliteTileRenderer,
    zoom: int,
    bounds: tuple[float, float, float, float],
    out_path: Path,
) -> None:
    west, south, east, north = bounds
    x_min, y_min, x_max, y_max = tile_range(zoom, west, south, east, north)
    satellite = renderer.render_zoom_canvas(zoom, x_min, y_min, x_max, y_max)
    base = fetch_basemap(zoom, x_min, y_min, x_max, y_max)
    base.putalpha(115)
    satellite = satellite.convert("RGBA")
    satellite.alpha_composite(base)
    satellite.convert("RGB").save(out_path)
    print(f"  wrote {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="Completed FCI manifest.json")
    parser.add_argument("--download", action="store_true", help="Fetch newest frame")
    parser.add_argument("--channel", default="Channel13", help="ABI-named channel")
    parser.add_argument("--out", type=Path, required=True, help="Working directory")
    args = parser.parse_args()
    if bool(args.manifest) == bool(args.download):
        parser.error("Provide exactly one of --manifest FILE or --download.")

    args.out.mkdir(parents=True, exist_ok=True)
    if args.download:
        manifest_path, frame_key = newest_manifest(args.out, args.channel)
    else:
        manifest_path, frame_key = args.manifest, args.manifest.parent.name
    chunks = chunk_paths_from_manifest(manifest_path)

    print(f"parsing {len(chunks)} FCI chunks for {args.channel}...")
    source_channel = source_channels_for_product(args.channel)[0]
    raster = load_fci_raster(chunks, source_channel)
    values = raster.values
    finite = np.isfinite(values)
    print(
        f"  grid={values.shape[1]}x{values.shape[0]} min={np.nanmin(values):.2f} "
        f"max={np.nanmax(values):.2f} mean={np.nanmean(values):.2f} "
        f"finite={finite.mean() * 100:.1f}%"
    )

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
    tag = f"fci_{args.channel.lower()}_{frame_key}"
    quick = values[::4, ::4]
    norm = np.clip((310.0 - quick) / 130.0, 0.0, 1.0)
    gray = np.where(np.isfinite(norm), norm * 255.0, 0.0).astype(np.uint8)
    native_path = args.out / f"{tag}_native.png"
    Image.fromarray(gray, mode="L").save(native_path)
    print(f"  wrote {native_path}")
    render_ghost_view(
        renderer, 3, (-70.0, -62.0, 70.0, 62.0), args.out / f"{tag}_disk_z3.png"
    )
    render_ghost_view(
        renderer, 5, (-15.0, 25.0, 35.0, 60.0), args.out / f"{tag}_europe_z5.png"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
