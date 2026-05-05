"""Rapid-update-only RTMA worker entry point.

Intended for schedulers that run a dedicated 15-minute rapid-update RTMA pass.
"""

from __future__ import annotations

import argparse

from workers.rtma_worker import run_rtma_rapid_worker


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the RTMA rapid-update worker once."
    )
    parser.add_argument("--force", action="store_true", help="Bypass freshness gate.")
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to logs/scheduled/rtma_rapid_update.log.",
    )
    args = parser.parse_args()

    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("rtma_rapid_update")

    run_rtma_rapid_worker(force=args.force)


if __name__ == "__main__":
    main()
