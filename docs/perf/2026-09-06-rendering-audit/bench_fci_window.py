"""Paired full-native versus window prototype pilot; source quality held fixed."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SCRATCH = ROOT / "cache/rendering-audit-20260906"
sys.path.insert(0, str(ROOT))
CASES = {
    "visible-z8": ("Channel02", 8, 0, 5),
    "visible-z4": ("Channel02", 4, 18.22, 22.8),
    "night-z5": ("NighttimeMicrophysics", 5, 0, 5),
    "limb-z8": ("Channel02", 8, 80, 0),
}


def measure(operation):
    import psutil
    process = psutil.Process()
    ready, done = threading.Event(), threading.Event()
    samples = []
    def sampler():
        while True:
            memory = process.memory_info()
            samples.append({"rss": memory.rss, "private": memory.private,
                            "host_available": psutil.virtual_memory().available})
            ready.set()
            if memory.rss > 6 * 1024**3 or samples[-1]["host_available"] < 4 * 1024**3:
                print("Prototype pilot memory guard reached", flush=True)
                os._exit(2)
            if done.wait(0.02):
                return
    monitor = threading.Thread(target=sampler, daemon=True)
    monitor.start()
    ready.wait()
    io = process.io_counters()._asdict()
    started, cpu = time.perf_counter(), time.process_time()
    try:
        result = operation()
    finally:
        wall, cpu_used = time.perf_counter() - started, time.process_time() - cpu
        done.set()
        monitor.join()
    io_after = process.io_counters()._asdict()
    return {"wall_seconds": wall, "cpu_seconds": cpu_used,
            "peak_rss_sampled": max(s["rss"] for s in samples),
            "peak_private_sampled": max(s["private"] for s in samples),
            "rss_after": process.memory_info().rss,
            "io_delta": {k: io_after[k] - io[k] for k in io}, "samples": samples, "result": result}


def child(args):
    def audit(event, values):
        if event == "socket.connect":
            raise RuntimeError("Prototype benchmark has no network")
    sys.addaudithook(audit)
    os.environ["MPLBACKEND"] = "Agg"
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from config.satellite_v2_config import source_channels_for_product
    from satellite_v2.renderer import SatelliteTileRenderer, _load_fci_source_rasters
    from satellite_v2.tiler import lon_lat_to_tile, _publish_tile_image_to_target
    if args.variant == "window":
        from fci_window_prototype_v1 import WindowLoader
    else:
        from fci_window_prototype import WindowLoader

    run_id = f"fci-pilot-{args.case}-{args.variant}-{args.iteration}"
    work = SCRATCH / run_id
    assert not work.exists(), "Preserve existing pilot run"
    work.mkdir()
    acquisition = json.loads((OUT / "meteosat-acquisition.json").read_text())
    paths = [ROOT / r["path"] for r in acquisition["transfers"] if r["path"].endswith(".nc")]
    product, z, lon, lat = CASES[args.case]
    sources = source_channels_for_product(product)
    x, y = lon_lat_to_tile(lon, lat, z)
    target = (z, x - 1, y - 1, x + 1, y + 1)
    loader = rasters = None
    rows = []
    count = 4 if args.iteration == 1 and args.case in {"visible-z8", "night-z5"} else 1
    for sample in range(count):
        def operation():
            nonlocal loader, rasters
            stage = time.perf_counter()
            if args.variant.startswith("window"):
                if loader is None:
                    loader = WindowLoader(paths, sources)
                rasters, stats = loader.load(sources, *target)
            else:
                if rasters is None:
                    rasters = _load_fci_source_rasters(paths[0], sources, max_grid=11136)
                stats = {"retained_native_array_bytes": sum(r.cmi.nbytes for r in rasters.values())}
            loading_seconds = time.perf_counter() - stage
            renderer = SatelliteTileRenderer(product, rasters, instrument="FCI")
            stage = time.perf_counter()
            canvas = renderer.render_zoom_canvas(*target)
            rendering_seconds = time.perf_counter() - stage
            rgba_hash = hashlib.sha256(canvas.tobytes()).hexdigest()
            stage = time.perf_counter()
            statuses = []
            for row in range(3):
                for column in range(3):
                    tile = canvas.crop((column * 256, row * 256, (column + 1) * 256, (row + 1) * 256))
                    path = work / f"sample-{sample}/{column}-{row}.png"
                    statuses.append(_publish_tile_image_to_target(tile, path, False))
            publication_seconds = time.perf_counter() - stage
            canvas.close()
            return {"loading_seconds": loading_seconds, "rendering_seconds": rendering_seconds,
                    "publication_seconds": publication_seconds, "rgba_sha256": rgba_hash,
                    "publication_statuses": statuses, "loader": stats}
        measured = measure(operation)
        measured["state"] = "source_local_fresh_process" if sample == 0 else "decoded_native_sources_retained"
        rows.append(measured)
    report = {"case": args.case, "variant": args.variant, "iteration": args.iteration,
              "target": target, "product": product, "rows": rows,
              "scope": "full native source loading plus same 3x3 canvas and normal nine-tile publication",
              "limitations": ["Three repetitions are a pilot, not p95 or production acceptance.",
                              "20ms sampled memory can miss peaks; native library and process startup excluded from state wall time.",
                              "Warm tests only cover visible z8 and NighttimeMicrophysics z5; larger windows/fallbacks exceed the 64MiB prototype cache.",
                              "Cold means fresh process with local source, not cold OS file cache."]}
    (OUT / (run_id + ".json")).write_text(json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=tuple(CASES))
    parser.add_argument("--variant", choices=("full", "window", "window-v2"))
    parser.add_argument("--iteration", type=int)
    parser.add_argument("--followup-v2", action="store_true")
    args = parser.parse_args()
    if args.case:
        child(args)
        return
    for name in ("fci-window-quality-v1.json", "fci-window-quality-transitions-v1.json"):
        assert json.loads((OUT / name).read_text())["all_selected_cases_passed"]
    if args.followup_v2:
        assert json.loads((OUT / "fci-window-quality-v2.json").read_text())["all_selected_cases_passed"]
    record_path = OUT / ("fci-pilot-v2-batch.json" if args.followup_v2 else "fci-pilot-batch.json")
    assert not record_path.exists(), "Preserve prior benchmark records"
    started = time.monotonic()
    record = {"category": "targeted_prototype_revision_followup_using_prior_controls" if args.followup_v2 else "paired_equal_native_quality_prototype_pilot", "runs": [],
              "limits": {"child_seconds": 600, "new_source_downloads": 0, "samples": 18 if args.followup_v2 else 36,
                         "total_audit_scratch_bytes": 10 * 1024**3},
              "prototype_sha256": hashlib.sha256((OUT / "fci_window_prototype.py").read_bytes()).hexdigest()}
    for case in CASES:
        for iteration in range(1, 4):
            variants = ("window-v2",) if args.followup_v2 else (("full", "window") if iteration % 2 else ("window", "full"))
            for variant in variants:
                used = time.monotonic() - started
                assert used < 600
                assert sum(p.stat().st_size for p in SCRATCH.rglob("*") if p.is_file()) < 10 * 1024**3
                cmd = [sys.executable, str(Path(__file__).resolve()), "--case", case,
                       "--variant", variant, "--iteration", str(iteration)]
                began = time.monotonic()
                log_path = SCRATCH / f"fci-pilot-{case}-{variant}-{iteration}.log"
                with log_path.open("x") as log:
                    result = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=min(90, 600 - used))
                row = {"case": case, "variant": variant, "iteration": iteration,
                       "child_seconds": time.monotonic() - began, "exit_code": result.returncode, "command": cmd}
                record["runs"].append(row)
                record_path.write_text(json.dumps(record, indent=2) + "\n")
                print(json.dumps({k: row[k] for k in ("case", "variant", "iteration", "child_seconds", "exit_code")}), flush=True)
                if result.returncode:
                    raise SystemExit("Stop after first failed child; inspect before retrying.")
    record["wall_seconds"] = time.monotonic() - started
    record_path.write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
