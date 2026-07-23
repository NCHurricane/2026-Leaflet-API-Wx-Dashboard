"""Isolated cold-cache probes for the worker-free rendering Phase 0 ledger."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path


def _scratch_root(parent: Path, scenario: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f"{scenario}-", dir=parent))


def _surface_probe(args: argparse.Namespace) -> dict:
    from surface import surface_utils
    from workers import surface_worker

    scratch = _scratch_root(args.scratch_parent, f"surface-{args.region.lower()}")

    def _cache_path(state_code, reference_dt=None):
        target = scratch / "surface" / "raw" / str(state_code).upper()
        target.mkdir(parents=True, exist_ok=True)
        return str(target), str(target / "data.csv")

    surface_utils.get_cache_path = _cache_path
    surface_worker._CACHE_ROOT = str(scratch)
    frame = surface_utils.fetch_metar_data(args.region)
    if frame is None or frame.empty:
        raise RuntimeError(f"No Surface observations returned for {args.region}")
    surface_worker._build_surface_gradients(
        frame,
        selected_products={args.product},
        region=args.region,
    )
    output = Path(surface_worker._gradient_root(args.region)) / f"{args.product}.png"
    if not output.exists() or output.stat().st_size <= 0:
        raise RuntimeError(f"Surface gradient was not written: {output}")
    return {
        "scenario": f"surface-gradient-{args.region.lower()}",
        "scratch_root": str(scratch),
        "station_count": len(frame),
        "output_bytes": output.stat().st_size,
    }


def _radar_probe(args: argparse.Namespace) -> dict:
    from workers import radar_live_worker

    scratch = _scratch_root(args.scratch_parent, "radar-history")
    radar_live_worker._CACHE_ROOT = scratch
    radar_live_worker._RADAR_ROOT = scratch / "radar" / "live"
    radar_live_worker._TMP_RENDER_ROOT = scratch / "tmp" / "radar_live"
    radar_live_worker.mark_run_complete = lambda _name: None
    rendered = radar_live_worker.run_radar_live_site_product(
        site=args.site,
        product_key=args.product,
        force=True,
        latest_only=False,
        newest_first=True,
        max_render_frames=args.max_frames,
        lookback_hours=args.lookback_hours,
    )
    if rendered <= 0:
        raise RuntimeError("Radar history probe rendered no frames")
    pngs = list((scratch / "radar" / "live").rglob("*.png"))
    return {
        "scenario": "radar-history",
        "scratch_root": str(scratch),
        "site": args.site,
        "product": args.product,
        "rendered_frames": rendered,
        "output_frames": len(pngs),
        "output_bytes": sum(path.stat().st_size for path in pngs),
    }


def _satellite_probe(args: argparse.Namespace) -> dict:
    from satellite_v2.providers import list_recent_frames
    from satellite_v2.tiler import render_frame_tile

    scratch = _scratch_root(args.scratch_parent, args.scenario)
    frames = list_recent_frames(
        sat_id=args.sat,
        sector=args.sector,
        channel_key=args.product,
        hours=args.hours,
        max_frames=1,
    )
    if not frames:
        raise RuntimeError(f"No frame found for {args.sat}/{args.sector}")
    frame = frames[-1]
    output, stats = render_frame_tile(
        cache_root=scratch,
        sat_id=args.sat,
        sector=args.sector,
        channel_key=args.product,
        frame=frame.to_dict(),
        z=args.z,
        x=args.x,
        y=args.y,
        render_supertile=False,
    )
    if not output.exists() or output.stat().st_size <= 0:
        raise RuntimeError(f"Satellite tile was not written: {output}")
    return {
        "scenario": args.scenario,
        "scratch_root": str(scratch),
        "sat": args.sat,
        "sector": args.sector,
        "product": args.product,
        "frame_key": frame.frame_key,
        "output_bytes": output.stat().st_size,
        "cache_status": stats.get("cache_status"),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scratch-parent",
        type=Path,
        default=Path("cache/tmp/worker-free-phase0"),
    )
    subparsers = parser.add_subparsers(dest="probe", required=True)

    surface = subparsers.add_parser("surface")
    surface.add_argument("--region", choices=("WORLD", "CONUS"), required=True)
    surface.add_argument("--product", default="temperature")

    radar = subparsers.add_parser("radar")
    radar.add_argument("--site", default="KFCX")
    radar.add_argument("--product", default="L3_N0B")
    radar.add_argument("--lookback-hours", type=float, default=1.0)
    radar.add_argument("--max-frames", type=int, default=24)

    satellite = subparsers.add_parser("satellite")
    satellite.add_argument(
        "--scenario", choices=("goes-tile", "himawari-tile", "eumetsat-frame"), required=True
    )
    satellite.add_argument("--sat", required=True)
    satellite.add_argument("--sector", required=True)
    satellite.add_argument("--product", default="Channel13")
    satellite.add_argument("--hours", type=int, default=24)
    satellite.add_argument("--z", type=int, required=True)
    satellite.add_argument("--x", type=int, required=True)
    satellite.add_argument("--y", type=int, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.probe == "surface":
        result = _surface_probe(args)
    elif args.probe == "radar":
        result = _radar_probe(args)
    else:
        result = _satellite_probe(args)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
