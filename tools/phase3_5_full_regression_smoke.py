#!/usr/bin/env python3
"""Run Phase 3/4/5 smoke scripts as one regression pass.

This wrapper expects the API server to already be running.

Usage:
  python tools/phase3_5_full_regression_smoke.py
  python tools/phase3_5_full_regression_smoke.py --base http://127.0.0.1:8016
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run_script(script_name: str, base: str) -> int:
    script_path = ROOT / script_name
    cmd = [sys.executable, str(script_path), "--base", base]
    print("\n" + "=" * 72)
    print(f"Running {script_name} against {base}")
    print("=" * 72)
    return subprocess.call(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 3/4/5 smoke suite")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    checks = [
        "phase3_smoke.py",
        "phase4_archive_smoke.py",
        "phase5_export_smoke.py",
    ]

    failures = []
    for script in checks:
        rc = run_script(script, args.base)
        if rc != 0:
            failures.append((script, rc))

    print("\n" + "#" * 72)
    if not failures:
        print("Full regression smoke PASS (Phase 3/4/5).")
        print("#" * 72)
        return 0

    print("Full regression smoke FAILED.")
    for script, rc in failures:
        print(f"  - {script}: exit code {rc}")
    print("#" * 72)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
