"""Scheduled-task entrypoint for the narrow Satellite v2 rapid-sector warmer."""

from __future__ import annotations

import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from satellite_v2.rapid_worker import main, run_satellite_v2_rapid_worker

__all__ = ["main", "run_satellite_v2_rapid_worker"]


if __name__ == "__main__":
    main()
