"""Scheduled-task entrypoint for Satellite v2 current-sector catalogs."""

from satellite_v2.worker import main, run_satellite_v2_worker

__all__ = ["main", "run_satellite_v2_worker"]


if __name__ == "__main__":
    main()
