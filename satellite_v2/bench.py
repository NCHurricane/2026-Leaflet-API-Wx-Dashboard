"""Reproducible benchmark and golden-tile CLI for Satellite v2."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


_PACKAGE_NAMES = ("numpy", "rasterio", "netCDF4", "xarray", "Pillow", "pyproj")
_FULL_DISK_CENTERS = {
    "goes18": (-137.2, 0.0),
    "goes19": (-75.2, 0.0),
    "himawari9": (140.7, 0.0),
    "meteosat9": (45.5, 0.0),
    "meteosat11": (0.0, 0.0),
    "meteosat12": (0.0, 0.0),
}
_BASELINE_ROW_ORDER = {
    ("goes19", "CONUS", "Channel13", 7): 1,
    ("goes19", "CONUS", "GeoColor", 7): 2,
    ("goes19", "FULLDISK", "Channel13", 5): 3,
    ("goes19", "MESO1", "Channel02", 8): 4,
    ("himawari9", "FULLDISK", "Channel13", 5): 5,
    ("himawari9", "JAPAN", "Channel13", 8): 6,
    ("meteosat12", "FULLDISK", "Channel13", 5): 7,
    ("meteosat12", "FULLDISK", "NighttimeMicrophysics", 5): 8,
    ("meteosat9", "FULLDISK", "Channel13", 5): 9,
    ("meteosat11", "RSS", "Channel13", 6): 10,
}
_SCENARIO_ORDER = {"cold-parse": 0, "warm-parse": 1, "hit": 2}
# Tolerance-mode golden compare reports every differing pixel by default and
# only fails on the per-channel delta, so a resampling shift is measured rather
# than gated on how many pixels moved.
_GOLDEN_DEFAULT_DIFF_FRACTION = 1.0
_GOLDEN_MAX_CHANNEL_VALUE = 255


def _utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def _parse_tile_block(value: str) -> tuple[int, int]:
    parts = value.lower().split("x", 1)
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("tiles must use WIDTHxHEIGHT, for example 3x3")
    try:
        width, height = (int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("tile dimensions must be integers") from exc
    if width < 1 or height < 1 or width % 2 == 0 or height % 2 == 0:
        raise argparse.ArgumentTypeError("tile dimensions must be positive odd numbers")
    return width, height


def _tile_block_coords(z: int, center_x: int, center_y: int, block: tuple[int, int]) -> list[tuple[int, int]]:
    width, height = block
    max_index = (2 ** int(z)) - 1
    return [
        (x, y)
        for y in range(max(0, center_y - height // 2), min(max_index, center_y + height // 2) + 1)
        for x in range(max(0, center_x - width // 2), min(max_index, center_x + width // 2) + 1)
    ]


def _default_center(sat_id: str, sector: str) -> tuple[float, float]:
    sector_key = str(sector).upper()
    if sector_key == "FULLDISK":
        return _FULL_DISK_CENTERS.get(str(sat_id).lower(), (0.0, 0.0))
    if sector_key in {"JAPAN", "TARGET"}:
        return 135.0, 35.0
    if sector_key == "RSS":
        return 7.5, 40.0
    if sector_key in {"CONUS", "MESO1"}:
        return -95.0, 38.0
    if sector_key == "MESO2":
        return -85.0, 32.5
    from config.satellite_v2_config import SATELLITE_V2_SECTOR_BOUNDS

    bounds = SATELLITE_V2_SECTOR_BOUNDS.get(sector_key)
    if bounds:
        return (
            (float(bounds["west"]) + float(bounds["east"])) / 2.0,
            (float(bounds["south"]) + float(bounds["north"])) / 2.0,
        )
    return 0.0, 0.0


def _frame_tile_dir(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    product: str,
    frame_key: str,
) -> Path:
    from config.satellite_v2_config import satellite_v2_render_version_for_satellite
    from satellite_v2.cache import namespace_root
    from config.satellite_v2_config import normalize_channel, normalize_sat_id, normalize_sector

    sat_key = normalize_sat_id(sat_id)
    parent = (
        namespace_root(cache_root)
        / "tiles"
        / satellite_v2_render_version_for_satellite(sat_key)
        / sat_key
        / normalize_sector(sector)
        / normalize_channel(product)
    ).resolve()
    target = (parent / str(frame_key)).resolve()
    if target.parent != parent or target.name != str(frame_key) or target.name in {"", ".", ".."}:
        raise ValueError("Unsafe satellite benchmark frame key")
    return target


def _purge_target_frame(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    product: str,
    frame_key: str,
) -> None:
    target = _frame_tile_dir(cache_root, sat_id, sector, product, frame_key)
    if target.exists():
        shutil.rmtree(target)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * fraction)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _summary_markdown(run_id: str, records: list[dict[str, Any]], context: dict[str, Any]) -> str:
    metric_names = sorted(
        {
            key
            for record in records
            for key, value in record.items()
            if (key.endswith("_ms") or "_ms{" in key) and isinstance(value, (int, float))
        }
    )
    lines = [
        f"# Satellite v2 benchmark {run_id}",
        "",
        f"- Target: `{context['sat_id']}/{context['sector']}/{context['product']}`",
        f"- Frame: `{context['frame_key']}`",
        f"- Scenario: `{context['scenario']}`",
        f"- Zoom/tile: `z{context['z']}/{context['x']}/{context['y']}`",
        f"- Samples: {len(records)}",
        "",
        "| metric | p50 ms | p95 ms | samples |",
        "|---|---:|---:|---:|",
    ]
    for metric in metric_names:
        values = [float(record[metric]) for record in records if metric in record]
        lines.append(
            f"| `{metric}` | {_percentile(values, 0.50):.3f} | "
            f"{_percentile(values, 0.95):.3f} | {len(values)} |"
        )
    return "\n".join(lines) + "\n"


def _git_details(repo_root: Path) -> tuple[str, list[str]]:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.splitlines()
    return sha, dirty


def _environment_manifest(repo_root: Path, context: dict[str, Any]) -> dict[str, Any]:
    git_sha, dirty_files = _git_details(repo_root)
    packages = {}
    for name in _PACKAGE_NAMES:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    try:
        import rasterio
        packages["GDAL"] = rasterio.__gdal_version__
    except Exception:
        packages["GDAL"] = None
    try:
        import psutil
        ram_bytes = int(psutil.virtual_memory().total)
    except Exception:
        ram_bytes = None
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha,
        "dirty_files": dirty_files,
        "python": sys.version,
        "packages": packages,
        "cpu": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "ram_bytes": ram_bytes,
        "platform": platform.platform(),
        "wx_satellite_v2_env": {
            key: value for key, value in sorted(os.environ.items())
            if key.startswith("WX_SATELLITE_V2_")
        },
        "worker_state_note": context.get("worker_state_note")
        or "Not inspected automatically; record whether scheduled workers were paused.",
        "benchmark": context,
    }


def _update_baseline_index(output_dir: Path) -> None:
    manifests = []
    for path in sorted(output_dir.glob("*-manifest.json")):
        if path.name == "matrix-manifest.json":
            continue
        manifests.append(json.loads(path.read_text(encoding="utf-8")))
    if not manifests:
        return
    latest_manifest = manifests[-1]
    runs = [manifest["benchmark"] for manifest in manifests]
    runs.sort(
        key=lambda run: (
            _BASELINE_ROW_ORDER.get(
                (run["sat_id"], run["sector"], run["product"], int(run["z"])), 999
            ),
            _SCENARIO_ORDER.get(run["scenario"], 999),
            run["run_id"],
        )
    )
    pinned = {
        f"{run['sat_id']}/{run['sector']}/{run['product']}/z{run['z']}": run["frame_key"]
        for run in runs
    }
    matrix_manifest = dict(latest_manifest)
    matrix_manifest["benchmark_runs"] = runs
    matrix_manifest["pinned_frame_keys"] = pinned
    matrix_manifest.pop("benchmark", None)
    (output_dir / "matrix-manifest.json").write_text(
        json.dumps(matrix_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lines = [
        "# Satellite v2 baseline matrix",
        "",
        "| target | scenario | frame | samples | total p50 ms | total p95 ms |",
        "|---|---|---|---:|---:|---:|",
    ]
    for run in runs:
        records = _read_jsonl(output_dir / f"{run['run_id']}.jsonl")
        totals = [float(record["total_ms"]) for record in records if "total_ms" in record]
        target = f"{run['sat_id']}/{run['sector']}/{run['product']}/z{run['z']}"
        lines.append(
            f"| `{target}` | `{run['scenario']}` | `{run['frame_key']}` | {len(totals)} | "
            f"{_percentile(totals, 0.50):.3f} | {_percentile(totals, 0.95):.3f} |"
        )
    (output_dir / "baseline-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _tile_rgba(path: Path) -> Any:
    """Decode a tile PNG as signed RGBA so deltas cannot wrap around."""
    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA"), dtype=np.int16)


def _tile_delta(golden_tile: Path, current_tile: Path) -> dict[str, Any]:
    import numpy as np

    golden_pixels = _tile_rgba(golden_tile)
    current_pixels = _tile_rgba(current_tile)
    if golden_pixels.shape != current_pixels.shape:
        raise RuntimeError(
            f"Golden tile geometry changed: {golden_tile} is {golden_pixels.shape}, "
            f"rendered tile is {current_pixels.shape}"
        )
    delta = np.abs(current_pixels - golden_pixels)
    pixel_count = int(delta.shape[0] * delta.shape[1])
    differing = int(np.count_nonzero(delta.any(axis=-1)))
    return {
        "max_delta": int(delta.max()) if delta.size else 0,
        "mean_delta": round(float(delta.mean()), 4) if delta.size else 0.0,
        "differing_pixels": differing,
        "pixel_count": pixel_count,
        "diff_fraction": round(differing / pixel_count, 6) if pixel_count else 0.0,
    }


def _write_golden(
    mode: str,
    golden_dir: Path,
    cache_root: Path,
    context: dict[str, Any],
    coords: list[tuple[int, int]],
    *,
    tolerance: int | None = None,
    max_diff_fraction: float = _GOLDEN_DEFAULT_DIFF_FRACTION,
    version_override: str | None = None,
) -> list[dict[str, Any]]:
    """Capture or compare golden tiles.

    ``tolerance`` selects the comparison mode. ``None`` keeps the strict
    SHA-256 gate used by platforms whose pixels must not move; an integer
    switches to a per-channel absolute-delta gate for platforms where a
    resampling shift is expected and only its magnitude matters.

    ``version_override`` names the render version segment of the golden tree.
    Goldens are stored per render version, so a compare that spans a version
    bump has to be pointed back at the version they were captured under.
    """
    from config.satellite_v2_config import satellite_v2_render_version_for_satellite
    from satellite_v2.cache import tile_path

    version = version_override or satellite_v2_render_version_for_satellite(context["sat_id"])
    root = golden_dir / version / context["sat_id"] / context["sector"] / context["product"] / context["frame_key"]
    index_path = root / "sha256.json"
    current: dict[str, str] = {}
    rendered: dict[str, Path] = {}
    for x, y in coords:
        source = tile_path(
            cache_root, context["sat_id"], context["sector"], context["product"],
            context["frame_key"], context["z"], x, y,
        )
        if not source.exists():
            raise FileNotFoundError(f"Golden tile was not rendered: {source}")
        relative = f"{context['z']}/{x}/{y}.png"
        current[relative] = _sha256(source)
        rendered[relative] = source
        if mode == "capture":
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    if mode == "capture":
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return []
    expected = json.loads(index_path.read_text(encoding="utf-8"))
    missing = sorted(set(expected) - set(current))
    if tolerance is None:
        mismatches = [key for key, digest in current.items() if expected.get(key) != digest]
        if mismatches or missing:
            raise RuntimeError(f"Golden comparison failed: mismatched={mismatches}, missing={missing}")
        return []
    if missing:
        raise RuntimeError(f"Golden comparison failed: missing={missing}")
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for relative in sorted(current):
        golden_tile = root / relative
        if not golden_tile.exists():
            raise RuntimeError(
                f"Tolerance compare needs the captured tile image, which is absent: {golden_tile}"
            )
        row = {"tile": relative, "sha_equal": expected.get(relative) == current[relative]}
        row.update(_tile_delta(golden_tile, rendered[relative]))
        rows.append(row)
        if row["max_delta"] > tolerance or row["diff_fraction"] > max_diff_fraction:
            failures.append(
                f"{relative} (max_delta={row['max_delta']}, diff_fraction={row['diff_fraction']})"
            )
    if failures:
        raise RuntimeError(
            f"Golden tolerance comparison failed (tolerance={tolerance}, "
            f"max_diff_fraction={max_diff_fraction}): {failures}"
        )
    return rows


def _golden_report_markdown(run_id: str, context: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        f"# Golden tolerance compare {run_id}",
        "",
        f"- Target: `{context['sat_id']}/{context['sector']}/{context['product']}`",
        f"- Frame: `{context['frame_key']}`",
        "",
        "| tile | sha equal | max delta | mean delta | differing px | diff fraction |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['tile']}` | {'yes' if row['sha_equal'] else 'no'} | {row['max_delta']} | "
            f"{row['mean_delta']:.4f} | {row['differing_pixels']} | {row['diff_fraction']:.6f} |"
        )
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sat", default="goes19")
    parser.add_argument("--sector", default="CONUS")
    parser.add_argument("--product", default="GeoColor")
    parser.add_argument("--frame")
    parser.add_argument("--z", type=int, default=7)
    parser.add_argument("--tiles", type=_parse_tile_block, default=(3, 3))
    parser.add_argument("--center-lon", type=float)
    parser.add_argument("--center-lat", type=float)
    parser.add_argument("--scenario", choices=("cold-parse", "warm-parse", "hit"), required=True)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--golden", choices=("capture", "compare"))
    parser.add_argument("--golden-dir", type=Path)
    parser.add_argument(
        "--golden-tolerance",
        type=int,
        help=(
            "Compare golden tiles by max per-channel absolute delta instead of SHA-256. "
            "Omit to keep the strict byte-identical gate."
        ),
    )
    parser.add_argument(
        "--golden-version",
        help=(
            "Render version segment the golden tiles live under. Use it to compare "
            "against goldens captured before a render-version bump."
        ),
    )
    parser.add_argument(
        "--golden-max-diff-fraction",
        type=float,
        default=_GOLDEN_DEFAULT_DIFF_FRACTION,
        help="Fraction of differing pixels tolerated in --golden-tolerance mode.",
    )
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--worker-state-note")
    parser.add_argument("--respond-first", action="store_true")
    parser.add_argument("--settle-ms", type=int, default=0)
    parser.add_argument("--run-id", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--_child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_iteration", type=int, default=1, help=argparse.SUPPRESS)
    return parser


def _local_frame_payload(cache_root: Path, args: argparse.Namespace, frame_key: str) -> dict[str, Any] | None:
    from config.satellite_platforms import platform_descriptor
    from config.satellite_v2_config import source_channels_for_product
    from satellite_v2.cache import namespace_root

    sat_key = str(args.sat).lower()
    sector_key = str(args.sector).upper()
    instrument = str(platform_descriptor(sat_key).get("instrument") or "")
    source_root = namespace_root(cache_root) / "source" / sat_key / sector_key
    if instrument == "FCI":
        manifest = source_root / "FCI" / frame_key / "manifest.json"
        if manifest.exists():
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            return {"frame_key": frame_key, "source_key": payload.get("product_id", "")}
        return None
    if instrument == "SEVIRI":
        files = list((source_root / "SEVIRI" / frame_key).glob("*.nat"))
        if files:
            return {"frame_key": frame_key, "source_key": files[0].stem}
        return None
    if instrument == "ABI":
        source_keys = {}
        for channel in source_channels_for_product(args.product):
            files = list((source_root / channel / frame_key).glob("*.nc"))
            if not files:
                return None
            source_keys[channel] = files[0].name
        return {
            "frame_key": frame_key,
            "source_key": next(iter(source_keys.values())),
            "source_keys": source_keys,
        }
    return None


def _resolve_frame(cache_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    if args.frame:
        frame_key = str(args.frame)
        from satellite_v2.cache import catalog_path, read_json
        cached = read_json(catalog_path(cache_root, args.sat, args.sector, args.product))
        for frame in (cached or {}).get("frames") or []:
            if str(frame.get("frame_key") or "") == frame_key:
                return frame
        local = _local_frame_payload(cache_root, args, frame_key)
        if local is not None:
            return local
        from satellite_v2.providers import list_recent_frames
        for frame in list_recent_frames(args.sat, args.sector, args.product, hours=12, max_frames=360):
            if str(frame.frame_key) == frame_key:
                return frame.to_dict()
        raise RuntimeError(f"Frame {frame_key!r} is not cataloged and has no complete local source bundle")
    from satellite_v2.catalog import get_catalog
    payload = get_catalog(
        str(cache_root), args.sat, args.sector, args.product,
        hours=24, max_frames=100, refresh=False,
    )
    frames = list(payload.get("frames") or [])
    if not frames:
        raise RuntimeError("No cataloged frame is available for this benchmark target")
    return dict(frames[-1])


def _resolve_once(
    cache_root: Path,
    context: dict[str, Any],
    frame: dict[str, Any],
    purge: bool,
    *,
    respond_first: bool = False,
    settle_ms: int = 0,
) -> None:
    if purge:
        _purge_target_frame(
            cache_root, context["sat_id"], context["sector"], context["product"], context["frame_key"]
        )
    if respond_first:
        from satellite_v2.service import resolve_tile
        path, stats = resolve_tile(
            str(cache_root), context["sat_id"], context["sector"], context["product"],
            context["frame_key"], context["z"], context["x"], context["y"],
            allow_render=True, frame_override=frame,
        )
        if settle_ms > 0:
            from satellite_v2.cache import is_negative_tile_cached, tile_path
            width, height = (int(value) for value in context["tiles"].split("x", 1))
            coords = _tile_block_coords(
                context["z"], context["x"], context["y"], (width, height)
            )
            deadline = time.monotonic() + (settle_ms / 1000.0)
            while time.monotonic() < deadline:
                settled = True
                for tile_x, tile_y in coords:
                    candidate = tile_path(
                        cache_root, context["sat_id"], context["sector"],
                        context["product"], context["frame_key"], context["z"],
                        tile_x, tile_y,
                    )
                    if not candidate.exists() and not is_negative_tile_cached(candidate):
                        settled = False
                        break
                if settled:
                    break
                time.sleep(0.025)
    elif purge:
        from satellite_v2.tiler import render_frame_tile
        path, stats = render_frame_tile(
            str(cache_root), context["sat_id"], context["sector"], context["product"],
            frame, context["z"], context["x"], context["y"], overwrite=False,
        )
    else:
        from satellite_v2.service import resolve_tile
        try:
            path, stats = resolve_tile(
                str(cache_root), context["sat_id"], context["sector"], context["product"],
                context["frame_key"], context["z"], context["x"], context["y"], allow_render=True,
            )
        except ValueError:
            from satellite_v2.tiler import render_frame_tile
            path, stats = render_frame_tile(
                str(cache_root), context["sat_id"], context["sector"], context["product"],
                frame, context["z"], context["x"], context["y"], overwrite=False,
            )
    if not path.exists() or stats.get("cache_status") == "invalid":
        raise RuntimeError(f"Benchmark target did not render a valid tile: {stats}")


def _cold_child_command(args: argparse.Namespace, frame_key: str, run_id: str, iteration: int, cache_root: Path) -> list[str]:
    command = [
        sys.executable, "-m", "satellite_v2.bench",
        "--sat", args.sat, "--sector", args.sector, "--product", args.product,
        "--frame", frame_key, "--z", str(args.z), "--tiles", f"{args.tiles[0]}x{args.tiles[1]}",
        "--center-lon", str(args.center_lon), "--center-lat", str(args.center_lat),
        "--scenario", "cold-parse", "--repeat", "1", "--cache-root", str(cache_root),
        "--run-id", run_id, "--_child", "--_iteration", str(iteration),
    ]
    if args.respond_first:
        command.append("--respond-first")
    if args.settle_ms:
        command.extend(("--settle-ms", str(args.settle_ms)))
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.repeat < 1:
        raise SystemExit("--repeat must be at least 1")
    if args.settle_ms < 0:
        raise SystemExit("--settle-ms cannot be negative")
    if args.golden and args.golden_dir is None:
        raise SystemExit("--golden-dir is required with --golden")
    if args.golden == "compare" and args.scenario == "hit":
        raise SystemExit("--golden compare requires cold-parse or warm-parse so tiles are re-rendered")
    if args.golden_version and not args.golden:
        raise SystemExit("--golden-version only applies with --golden")
    if args.golden_tolerance is not None:
        if args.golden != "compare":
            raise SystemExit("--golden-tolerance only applies to --golden compare")
        if not 0 <= args.golden_tolerance <= _GOLDEN_MAX_CHANNEL_VALUE:
            raise SystemExit(f"--golden-tolerance must be between 0 and {_GOLDEN_MAX_CHANNEL_VALUE}")
    if not 0.0 <= args.golden_max_diff_fraction <= 1.0:
        raise SystemExit("--golden-max-diff-fraction must be between 0.0 and 1.0")

    run_id = args.run_id or _utc_run_id()
    os.environ["WX_SATELLITE_V2_BENCH"] = "1"
    os.environ["WX_SATELLITE_V2_BENCH_RUN_ID"] = run_id
    os.environ["WX_SATELLITE_V2_BENCH_SCENARIO"] = args.scenario
    from app_core.paths import BASE_PATH, CACHE_ROOT
    from config.satellite_v2_config import normalize_channel, normalize_sat_id, normalize_sector
    from satellite_v2.tiler import lon_lat_to_tile

    cache_root = (args.cache_root or Path(CACHE_ROOT)).resolve()
    sat_key = normalize_sat_id(args.sat)
    sector_key = normalize_sector(args.sector)
    product_key = normalize_channel(args.product)
    default_lon, default_lat = _default_center(sat_key, sector_key)
    args.center_lon = default_lon if args.center_lon is None else args.center_lon
    args.center_lat = default_lat if args.center_lat is None else args.center_lat
    frame = _resolve_frame(cache_root, args)
    frame_key = str(frame["frame_key"])
    center_x, center_y = lon_lat_to_tile(args.center_lon, args.center_lat, args.z)
    coords = _tile_block_coords(args.z, center_x, center_y, args.tiles)
    context = {
        "run_id": run_id, "sat_id": sat_key, "sector": sector_key,
        "product": product_key, "frame_key": frame_key, "z": args.z,
        "x": center_x, "y": center_y, "tiles": f"{args.tiles[0]}x{args.tiles[1]}",
        "scenario": args.scenario, "repeat": args.repeat,
        "respond_first": bool(args.respond_first), "settle_ms": int(args.settle_ms),
        "worker_state_note": args.worker_state_note or "",
    }
    print(f"Pinned frame_key: {frame_key}", flush=True)

    if args._child:
        os.environ["WX_SATELLITE_V2_BENCH_ITERATION"] = str(args._iteration)
        _resolve_once(
            cache_root, context, frame, purge=True,
            respond_first=args.respond_first, settle_ms=args.settle_ms,
        )
        return 0

    sink = cache_root / "satellite" / ".bench" / f"{run_id}.jsonl"
    if sink.exists():
        raise RuntimeError(f"Benchmark run id already exists: {run_id}")

    if args.scenario == "cold-parse":
        for iteration in range(1, args.repeat + 1):
            subprocess.run(
                _cold_child_command(args, frame_key, run_id, iteration, cache_root),
                cwd=BASE_PATH, check=True,
            )
    else:
        if args.scenario == "hit":
            _resolve_once(
                cache_root, context, frame, purge=False,
                respond_first=args.respond_first, settle_ms=args.settle_ms,
            )
            sink.unlink(missing_ok=True)
        elif args.scenario == "warm-parse":
            # Populate the in-process renderer/source caches before recording.
            # Each measured repeat still purges tiles, isolating warp/colorize/
            # encode without allowing the first cold parse to pollute p95.
            _resolve_once(
                cache_root, context, frame, purge=True,
                respond_first=args.respond_first, settle_ms=args.settle_ms,
            )
            sink.unlink(missing_ok=True)
        for iteration in range(1, args.repeat + 1):
            os.environ["WX_SATELLITE_V2_BENCH_ITERATION"] = str(iteration)
            _resolve_once(
                cache_root, context, frame, purge=args.scenario == "warm-parse",
                respond_first=args.respond_first, settle_ms=args.settle_ms,
            )

    golden_rows: list[dict[str, Any]] = []
    if args.golden:
        golden_rows = _write_golden(
            args.golden, args.golden_dir.resolve(), cache_root, context, coords,
            tolerance=args.golden_tolerance,
            max_diff_fraction=args.golden_max_diff_fraction,
            version_override=args.golden_version,
        )

    records = _read_jsonl(sink)
    output_dir = (args.output_dir or (Path(BASE_PATH) / "docs" / "perf" / f"{datetime.now().date().isoformat()}-baseline")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = _summary_markdown(run_id, records, context)
    (output_dir / f"{run_id}-summary.md").write_text(summary, encoding="utf-8")
    manifest = _environment_manifest(Path(BASE_PATH), context)
    (output_dir / f"{run_id}-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if sink.exists():
        shutil.copyfile(sink, output_dir / sink.name)
    _update_baseline_index(output_dir)
    if golden_rows:
        golden_report = _golden_report_markdown(run_id, context, golden_rows)
        (output_dir / f"{run_id}-golden.md").write_text(golden_report, encoding="utf-8")
        print(golden_report, end="")
    if args.summary:
        print(summary, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
