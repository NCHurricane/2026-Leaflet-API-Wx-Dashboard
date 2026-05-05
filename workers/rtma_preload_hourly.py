"""Manual RTMA preload wrapper for the hourly stream only.

This module is intentionally not wired into Windows Task Scheduler.
Run manually when a full hourly RTMA cache backfill is needed.
"""

from __future__ import annotations

import argparse

from config.rtma_config import RTMA_UI_PRODUCTS, RTMA_WORKER_REGIONS
from workers.rtma_preload import run_preload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manual RTMA preload for rtma_hourly only.",
    )
    parser.add_argument(
        "--region",
        choices=list(RTMA_WORKER_REGIONS),
        default=None,
        help="Limit backfill to one region (default: all RTMA regions).",
    )
    parser.add_argument(
        "--product",
        choices=list(RTMA_UI_PRODUCTS),
        default=None,
        help="Limit backfill to one product (default: all RTMA products).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-frame skip/ok messages.",
    )
    args = parser.parse_args()

    run_preload(
        regions=[args.region] if args.region else list(RTMA_WORKER_REGIONS),
        streams=["rtma_hourly"],
        products=[args.product] if args.product else list(RTMA_UI_PRODUCTS),
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
