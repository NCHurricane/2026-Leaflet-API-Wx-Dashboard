"""Meso-only Satellite prewarm worker entry point."""

from __future__ import annotations

import argparse

from workers.satellite_worker import run_satellite_meso_worker


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Satellite mesoscale prewarm worker once."
    )
    parser.add_argument("--force", action="store_true", help="Bypass freshness gate.")
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to logs/scheduled/satellite_meso.log.",
    )
    args = parser.parse_args()

    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("satellite_meso")

    run_satellite_meso_worker(force=args.force)


if __name__ == "__main__":
    main()
