"""Manual RTMA preload wrapper for the rapid-update stream only.

This module is intentionally not wired into Windows Task Scheduler.
Run manually when a full rapid-update RTMA cache backfill is needed.

Usage:
  python -m workers.rtma_preload_rapid
  or directly:
  python workers/rtma_preload_rapid.py
"""

from __future__ import annotations

import argparse
import os
import sys

# Add project root to path for both module and direct execution
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config.rtma_config import RTMA_UI_PRODUCTS
from workers.rtma_preload import run_preload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manual RTMA preload for rtma_rapid_update only.",
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

    # Rapid update is CONUS-only by contract.
    run_preload(
        regions=["CONUS"],
        streams=["rtma_rapid_update"],
        products=[args.product] if args.product else list(RTMA_UI_PRODUCTS),
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
