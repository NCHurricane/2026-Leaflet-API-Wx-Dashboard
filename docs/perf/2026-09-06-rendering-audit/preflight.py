"""Read local audit inputs without importing renderers, decoding, or downloading."""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
CACHE = ROOT / "cache"


def file_record(path: Path) -> dict:
    stat = path.stat()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def data_files(directory: Path, suffixes: set[str]) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
        and path.stat().st_size > 0
    )


def summarize(files: list[Path]) -> dict:
    return {
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "sample": [file_record(path) for path in files[-3:]],
    }


def literal_dict_keys(relative_path: str, name: str) -> list[str]:
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ) and isinstance(node.value, ast.Dict):
            return [key.value for key in node.value.keys if isinstance(key, ast.Constant)]
    raise ValueError(f"No literal dict keys found for {relative_path}:{name}")


def main() -> None:
    satellite_groups = defaultdict(list)
    sat_root = CACHE / "satellite" / "source"
    for path in data_files(sat_root, {".nc", ".nat", ".dat", ".bz2"}):
        parts = path.relative_to(sat_root).parts
        satellite_groups["/".join(parts[:3])].append(path)

    radar_root = CACHE / "radar" / "live" / "radar_level2_downloads" / "_VOLUME"
    radar_groups = {}
    for directory in sorted(radar_root.iterdir()) if radar_root.is_dir() else []:
        if directory.is_dir():
            files = sorted(
                path for path in directory.iterdir()
                if path.is_file() and re.fullmatch(r"[A-Z0-9]{4}\d{8}_\d{6}_V\d{2}", path.name)
                and path.stat().st_size > 0
            )
            if files:
                radar_groups[directory.name] = files

    mrms_groups = {}
    mrms_root = CACHE / "mrms"
    for directory in sorted(mrms_root.iterdir()) if mrms_root.is_dir() else []:
        if directory.is_dir() and directory.name != "tiles":
            files = data_files(directory, {".gz", ".grib2"})
            if files:
                mrms_groups[directory.name] = files

    rtma_files = data_files(CACHE / "rtma" / "grib", {".grb2", ".grib2"})
    rtma_rapid = [path for path in rtma_files if "_ru." in path.name]
    rtma_hourly = [path for path in rtma_files if "_ru." not in path.name]

    preferred_site = next((site for site in ("KGSP", "KMHX", "KRAX") if site in radar_groups), None)
    if preferred_site is None:
        preferred_site = next(iter(radar_groups), None)

    rows = []
    for case, group in (
        ("M12 Channel13 z5", "meteosat12/FULLDISK/FCI"),
        ("M12 Channel02 z8", "meteosat12/FULLDISK/FCI"),
        ("M12 NighttimeMicrophysics z5", "meteosat12/FULLDISK/FCI"),
        ("M11 RSS non-rapid composite z5", "meteosat11/RSS/SEVIRI"),
        ("GOES Full Disk Channel02 z8", "goes19/FULLDISK/Channel02"),
        ("GMGSI Channel13 z3", "gmgsi/GLOBAL/Channel13"),
    ):
        rows.append({"case": case, "candidate_files": len(satellite_groups.get(group, []))})
    for product in ("L2_REF", "L2_RHO"):
        rows.append({"case": f"Radar {product} z11", "candidate_files": len(radar_groups.get(preferred_site, [])), "site": preferred_site})
    mesh = [path for name, files in mrms_groups.items() if name.startswith("MESH") for path in files]
    rotation = [path for name, files in mrms_groups.items() if name.startswith("RotationTrack_") for path in files]
    rows.extend([
        {"case": "MRMS MESH z7", "candidate_files": len(mesh)},
        {"case": "MRMS RotationTrack z8", "candidate_files": len(rotation)},
        {"case": "RTMA CONUS hourly temperature", "candidate_files": len(rtma_hourly)},
        {"case": "RTMA rapid-update Winds", "candidate_files": len(rtma_rapid)},
    ])
    for row in rows:
        row["status"] = "candidate_needs_content_validation" if row["candidate_files"] else "missing_local_source"

    historical = ROOT / "docs/perf/2026-07-26-radar-phase5/matrix-manifest.json"
    old_sources = sorted({source for run in json.loads(historical.read_text(encoding="utf-8"))["benchmark_runs"] for source in run.get("sources", [])})
    versions = {}
    for name in ("numpy", "rasterio", "netCDF4", "xarray", "Pillow", "pyproj", "arm_pyart", "psutil"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None

    # Hash only the three candidate inputs, not the entire retained cache.
    selected = []
    for files in (radar_groups.get(preferred_site, []), rtma_rapid, rtma_hourly):
        if files:
            path = files[-1]
            with path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            selected.append({**file_record(path), "sha256": digest})

    manifest = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_category": "read_only_file_inventory_and_dependency_metadata",
        "command": ".venv/Scripts/python.exe docs/perf/2026-09-06-rendering-audit/preflight.py",
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_status": subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True).splitlines(),
        "radar_configured_products": literal_dict_keys("config/radar_config.py", "LIVE_RADAR_PRODUCTS"),
        "satellite_sources": {key: summarize(files) for key, files in sorted(satellite_groups.items())},
        "radar_level2_sources": {key: summarize(files) for key, files in sorted(radar_groups.items())},
        "mrms_sources": {key: summarize(files) for key, files in sorted(mrms_groups.items())},
        "rtma_sources": {"rapid_by_filename": summarize(rtma_rapid), "hourly_candidates_by_filename": summarize(rtma_hourly)},
        "planned_timing_cells": rows,
        "historical_radar_inputs": [{"path": source, "exists": Path(source).is_file()} for source in old_sources],
        "selected_input_candidates": selected,
        "package_versions": versions,
        "limitations": [
            "Filenames, existence and byte sizes do not validate complete source contents or weather variables.",
            "No renderer imported; no native data decode, provider request, benchmark, or browser execution.",
            "RTMA hourly versus rapid grouping is filename-based; grid, time and variables still need header checks.",
            "Source caches were only read; no application/cache settings changed.",
        ],
    }
    (OUT / "preflight.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"planned_cells": len(rows), "with_candidates": sum(row["candidate_files"] > 0 for row in rows), "missing": [row["case"] for row in rows if not row["candidate_files"]], "selected_inputs": selected}, indent=2))


if __name__ == "__main__":
    main()
