"""Scheduled-task entrypoint for Satellite v2 current-sector catalogs."""

import os
import sys

# Add project root to path for both module and direct execution
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from satellite_v2.worker import main, run_satellite_v2_worker

__all__ = ["main", "run_satellite_v2_worker"]


if __name__ == "__main__":
    main()
