"""Offline owner-viewport quality checks and one bounded before/after pair."""

import argparse
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from unittest.mock import patch

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
WORK = ROOT / "cache/rendering-audit-20260906/fci-limb-correction"
sys.path.insert(0, str(ROOT))


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(mode):
    quality_mode = mode.startswith("quality")
    def audit(event, values):
        if event == "socket.connect":
            raise RuntimeError("No network in the first-frame correction check")
    sys.addaudithook(audit)
    os.environ["MPLBACKEND"] = "Agg"
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from PIL import Image
    from bench_fci_window import measure
    from satellite_v2 import fci_windows, renderer, service, tiler

    # Independent wall guard includes fixture/reference preparation as well.
    deadline = threading.Timer(180 if quality_mode else 120, lambda: os._exit(2))
    deadline.daemon = True
    deadline.start()
    report_path = OUT / f"fci-limb-viewport-{mode}.json"
    assert not report_path.exists(), "Do not replace earlier evidence"
    write(report_path, {"mode": mode, "status": "started"})
    smoke = json.loads((OUT / "owner-smoke-first-frame-2330.json").read_text())
    fixture_path = OUT / "fci-limb-correction-fixture.json"
    if quality_mode and not fixture_path.exists():
        assert not WORK.exists() and not fixture_path.exists()
        source_dir = WORK / "source"
        source_dir.mkdir(parents=True)
        live = ROOT / "cache/satellite/source/meteosat12/FULLDISK/FCI/20260906T233000Z"
        paths = sorted(live.glob("*.nc"))
        assert len(paths) == 40 and sum(path.stat().st_size for path in paths) == smoke["source_files_snapshot"]["total_bytes"]
        files = []
        for source in paths:
            before = (source.stat().st_size, source.stat().st_mtime_ns)
            target = source_dir / source.name
            expected = digest(source)
            shutil.copy2(source, target)
            assert digest(target) == expected and before == (source.stat().st_size, source.stat().st_mtime_ns)
            files.append({"path": target.relative_to(ROOT).as_posix(), "sha256": expected, "bytes": before[0]})
        write(fixture_path, {"frame": smoke["selection"]["frame_key"], "files": files, "new_downloads": 0})
    fixture = json.loads(fixture_path.read_text())
    for row in fixture["files"]:
        assert digest(ROOT / row["path"]) == row["sha256"]
    primary = ROOT / fixture["files"][0]["path"]
    references = WORK / "references"
    references_manifest = OUT / "fci-limb-viewport-references.json"

    def make_references():
        references.mkdir()
        rasters = renderer._load_fci_source_rasters(primary, ("Channel02",), max_grid=11136)
        assert rasters["Channel02"].cmi.shape == (11136, 11136)
        full = renderer.SatelliteTileRenderer("Channel02", rasters, {"Channel02": primary}, "FCI")
        rows = []
        for tile in smoke["files"]:
            z, x, y = tile["xyz"]
            image = full.render_tile(z, x, y)
            path = references / f"{z}-{x}-{y}.png"
            image.save(path)
            rows.append({"xyz": tile["xyz"], "rgba_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                         "empty": image.getbbox() is None, "path": path.relative_to(ROOT).as_posix()})
            image.close()
        write(references_manifest, {"category": "independent_full_native_references", "cases": rows})
        return {"references": len(rows)}

    reference_diagnostics = None
    if quality_mode and not references_manifest.exists():
        reference_diagnostics = measure(make_references)
        gc.collect()
    expected = json.loads(references_manifest.read_text())["cases"]
    assert len(expected) == 40
    output = WORK / mode
    output.mkdir()
    rows = []
    current = {}
    original_plan = fci_windows.Frame.plan
    if mode == "control":
        name = "fci_windows_before_limb_fix"
        spec = importlib.util.spec_from_file_location(name, OUT / (name + ".py"))
        before = importlib.util.module_from_spec(spec)
        sys.modules[name] = before
        spec.loader.exec_module(before)
        original_plan = before.Frame.plan

    def plan(*args):
        result = original_plan(*args)
        _, windows, full = result
        current.update(windows=windows, full_native_fallback=full)
        return result

    publish = tiler._publish_zoom_canvas_tiles

    def checked_publish(canvas, **kwargs):
        actual = hashlib.sha256(canvas.tobytes()).hexdigest()
        assert actual == expected[len(rows)]["rgba_sha256"], expected[len(rows)]["xyz"]
        current["whole_rgba_exact"] = True
        return publish(canvas, **kwargs)

    def viewport():
        with patch.object(fci_windows.Frame, "plan", plan), \
                patch.object(tiler, "download_product_source_frames", return_value={"Channel02": primary}), \
                patch.object(tiler, "_publish_zoom_canvas_tiles", checked_publish), \
                patch.object(fci_windows, "_load", wraps=fci_windows._load) as reads, \
                patch.object(renderer, "_load_fci_source_rasters", wraps=renderer._load_fci_source_rasters) as full_reads:
            for case in expected:
                current.clear()
                z, x, y = case["xyz"]
                prior_reads, prior_full = reads.call_count, full_reads.call_count
                started = time.perf_counter()
                path, stats = service._render_tile_with_budget(
                    cache_root=output, sat_id="meteosat12", sector="FULLDISK", channel_key="Channel02",
                    frame={"frame_key": fixture["frame"]}, z=z, x=x, y=y, render_supertile=False, record_timing=False)
                if case["empty"]:
                    assert not path.exists() and tiler.is_negative_tile_cached(path)
                else:
                    with Image.open(path) as image:
                        assert hashlib.sha256(image.tobytes()).hexdigest() == case["rgba_sha256"]
                row = {"xyz": case["xyz"], **current, "load_calls": reads.call_count - prior_reads,
                       "full_load_calls": full_reads.call_count - prior_full, "stats": stats,
                       "retained_cache_bytes": fci_windows._ARRAY_BYTES}
                if not quality_mode:
                    row["elapsed_seconds"] = time.perf_counter() - started
                if mode != "control":
                    assert not row["full_native_fallback"] and row["full_load_calls"] == 0
                    assert row["load_calls"] == (0 if case["empty"] else 1)
                rows.append(row)
        return {"tiles": rows, "all_40_exact": True}

    try:
        result = measure(viewport)
    except Exception as exc:
        write(report_path, {"mode": mode, "status": "failed", "error": str(exc), "completed_tiles": rows})
        raise
    result.update(mode=mode, category="quality_and_publication_not_timing_sample" if quality_mode else "single_local_source_viewport_timing",
                  reference_diagnostics=reference_diagnostics,
                  runtime_sha256={path: digest(ROOT / path) for path in
                                  json.loads((OUT / "fci-integration-validation.json").read_text())["runtime_sha256"]},
                  control_module_sha256=digest(OUT / "fci_windows_before_limb_fix.py"),
                  limitations="Sequential service calls in observed completion order; one process, local pinned frame, uncontrolled OS cache/desktop. No HTTP/browser/OBS, acquisition or cross-machine timing.")
    write(report_path, result)
    deadline.cancel()
    print(json.dumps({"mode": mode, "all_40_exact": True, "wall_seconds": result["wall_seconds"],
                      "peak_rss": result["peak_rss_sampled"]}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("quality", "quality-final", "timings", "control", "candidate"))
    args = parser.parse_args()
    if args.mode != "timings":
        run(args.mode)
        return
    quality = json.loads((OUT / "fci-limb-viewport-quality-final.json").read_text())
    assert quality["result"]["all_40_exact"]
    for path, expected in quality["runtime_sha256"].items():
        assert digest(ROOT / path) == expected
    path = OUT / "fci-limb-viewport-pair.json"
    assert not path.exists()
    report = {"limits": {"samples": 2, "child_seconds": 240, "new_downloads": 0}, "runs": [],
              "previous_allocation_used": "108/108", "total_samples_after_success": 110}
    write(path, report)
    start = time.monotonic()
    for mode in ("control", "candidate"):
        assert sum(p.stat().st_size for p in WORK.rglob("*") if p.is_file()) < 2*1024**3
        began = time.monotonic()
        with (WORK / (mode + ".log")).open("x") as log:
            child = subprocess.run([sys.executable, str(Path(__file__).resolve()), mode], cwd=ROOT,
                                   stdout=log, stderr=subprocess.STDOUT, timeout=min(120, 240 - (began - start)))
        report["runs"].append({"mode": mode, "exit_code": child.returncode, "child_seconds": time.monotonic() - began})
        write(path, report)
        print(json.dumps(report["runs"][-1]), flush=True)
        assert child.returncode == 0, "Stop on failure; do not automatically repeat"
    report["both_passed"] = True
    write(path, report)


if __name__ == "__main__":
    main()
