"""Scheduled-task entrypoint for Satellite v2 light composite catalogs."""

from __future__ import annotations

import argparse

from config.satellite_v2_config import SATELLITE_V2_WORKER_PROFILES
from satellite_v2.worker import run_satellite_v2_worker
from workers._freshness import redirect_stdio_to_log

_WORKER_NAME = "satellite_v2_light_composites"
_DEFAULT_PROFILE = "goes19-light-composites"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh Satellite v2 light composite catalogs"
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--log-to-file", action="store_true")
    parser.add_argument(
        "--tile-workers",
        type=int,
        default=2,
        help="Override Satellite v2 tile render worker process count.",
    )
    parser.add_argument(
        "--profile",
        default=_DEFAULT_PROFILE,
        choices=sorted(SATELLITE_V2_WORKER_PROFILES),
        help="Satellite v2 worker ownership profile.",
    )
    parser.add_argument(
        "--all-frames",
        action="store_true",
        help="Warm every cataloged frame for selected jobs instead of baseline/deep rotation.",
    )
    args = parser.parse_args()
    if args.log_to_file:
        redirect_stdio_to_log(_WORKER_NAME)
    run_satellite_v2_worker(
        force=args.force,
        tile_workers=args.tile_workers,
        profile=args.profile,
        all_frames=args.all_frames,
        worker_name_override=_WORKER_NAME,
    )


if __name__ == "__main__":
    main()