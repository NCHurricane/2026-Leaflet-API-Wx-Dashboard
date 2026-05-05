"""Hourly-only RTMA worker entry point.

Intended for schedulers that run a dedicated hourly RTMA pass.
"""

from __future__ import annotations

import argparse

from workers.rtma_worker import run_rtma_hourly_worker


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RTMA hourly worker once.")
    parser.add_argument("--force", action="store_true", help="Bypass freshness gate.")
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to logs/scheduled/rtma_hourly.log.",
    )
    args = parser.parse_args()

    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("rtma_hourly")

    run_rtma_hourly_worker(force=args.force)


if __name__ == "__main__":
    main()
