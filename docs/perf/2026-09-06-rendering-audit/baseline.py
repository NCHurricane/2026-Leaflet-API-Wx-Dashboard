"""Bounded offline calls to existing renderers with audit-only resource sampling."""

from __future__ import annotations

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
SAT_CASES = {
    "m12-ir": ("meteosat12", "FULLDISK", "Channel13", 5, 0, 5),
    "m12-visible": ("meteosat12", "FULLDISK", "Channel02", 8, 0, 5),
    "m12-composite": ("meteosat12", "FULLDISK", "NighttimeMicrophysics", 5, 0, 5),
    "m11-composite": ("meteosat11", "RSS", "NighttimeMicrophysics", 5, 7.5, 40),
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def png_contract(path):
    from PIL import Image
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
                "shape": list(rgba.size), "rgba_sha256": hashlib.sha256(rgba.tobytes()).hexdigest(),
                "alpha_extrema": list(rgba.getchannel("A").getextrema())}


def measure(label, operation):
    import psutil
    process = psutil.Process()
    done = threading.Event()
    samples = []
    started = time.perf_counter()
    cpu = time.process_time()
    io_before = process.io_counters()._asdict()

    def sample():
        while True:
            memory = process.memory_info()
            samples.append({"seconds": time.perf_counter() - started, "rss": memory.rss,
                            "private": getattr(memory, "private", None),
                            "threads": process.num_threads(),
                            "host_available": psutil.virtual_memory().available})
            if done.wait(0.05):
                break
    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        result = operation()
    finally:
        elapsed = time.perf_counter() - started
        cpu_seconds = time.process_time() - cpu
        done.set()
        sampler.join()
    io_after = process.io_counters()._asdict()
    return {"state": label, "wall_seconds": elapsed, "cpu_seconds": cpu_seconds,
            "rss_peak_sampled": max(s["rss"] for s in samples),
            "private_peak_sampled": max((s["private"] or 0) for s in samples),
            "rss_after": process.memory_info().rss,
            "io_delta": {k: io_after[k] - io_before[k] for k in io_before},
            "samples": samples, "result": result}


def child(case, iteration):
    # Refuse accidental provider fallback. This process makes no child processes.
    def audit(event, args):
        if event == "socket.connect":
            raise RuntimeError("Network disabled for renderer baseline")
    sys.addaudithook(audit)
    os.environ["MPLBACKEND"] = "Agg"
    os.environ["WX_UPSTREAM_LEDGER"] = "0"
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    import psutil
    from config import satellite_v2_config as sc, radar_config as rc
    from radar.webgl_artifact import feature_config

    run_id = f"audit-{case}-{iteration}"
    work = SCRATCH / "baseline" / run_id
    work.mkdir(parents=True, exist_ok=False)
    settings = {name: getattr(sc, name) for name in dir(sc)
                if name.startswith("SATELLITE_V2_") and any(token in name for token in
                    ("MAX_GRID", "CACHE_MB", "CACHE_SIZE", "BUDGET", "WORKER", "CONCURRENCY"))
                and isinstance(getattr(sc, name), (int, float, str, bool))}
    settings["radar_webgl"] = feature_config()
    settings["radar_figure_size_inches"] = rc.LIVE_RADAR_FIGURE_SIZE_INCHES
    settings["radar_dpi"] = rc.LIVE_RADAR_RENDER_DPI
    rows = []
    if case.startswith("radar-"):
        from radar import bench
        local = json.loads((OUT / "validated-local.json").read_text())
        source = ROOT / local["radar"]["source"]["pinned_path"]
        product = "L2_REF" if case == "radar-ref" else "L2_RHO"
        context = bench._product_context("KRAX", product, "auto")
        rows.append(measure("source_local_fresh_process_no_artifact", lambda:
                            bench._render_one(context, source, work)))
    elif case == "rtma-winds":
        from rtma import rtma_utils as rtma
        from mrms import mrms_utils
        from config.geo_config import STATE_BOUNDS
        source = ROOT / json.loads((OUT / "validated-local.json").read_text())["rtma"]["source"]["pinned_path"]
        stages = {}
        def wrap(owner, name):
            original = getattr(owner, name)
            def timed(*args, **kwargs):
                started = time.perf_counter()
                try:
                    return original(*args, **kwargs)
                finally:
                    stages[name] = stages.get(name, 0.0) + time.perf_counter() - started
            setattr(owner, name, timed)
        for name in ("_extract_dataset", "_crop_grid", "_warp_to_latlon_grid"):
            wrap(rtma, name)
        wrap(mrms_utils, "warp_array_to_mercator")
        for index in range(4 if iteration == 1 else 1):
            stages.clear()
            target = work / f"winds-{index}.png"
            def render():
                _, bounds, meta = rtma._render_rtma_png_standalone(
                    str(source), "wind_speed", STATE_BOUNDS["CONUS"], str(target))
                return {"stages_seconds": dict(stages), "bounds": bounds, "metadata": meta}
            row = measure("source_local_fresh_process_no_artifact" if index == 0 else "parsed_dataset_cache_warm_no_artifact", render)
            row["png"] = png_contract(target)
            rows.append(row)
    else:
        os.environ["WX_SATELLITE_V2_BENCH"] = "1"
        os.environ["WX_SATELLITE_V2_BENCH_RUN_ID"] = run_id
        from satellite_v2 import bench
        from satellite_v2.tiler import lon_lat_to_tile
        from satellite_v2.cache import tile_path
        sat, sector, product, z, lon, lat = SAT_CASES[case]
        acquisition = json.loads((OUT / "meteosat-acquisition.json").read_text())
        frame_row = next(f for f in acquisition["frames"] if f["sat"] == sat)
        args = argparse.Namespace(sat=sat, sector=sector, product=product)
        frame = bench._local_frame_payload(SCRATCH, args, frame_row["frame_key"])
        assert frame is not None, "Pinned local frame missing; provider fallback prohibited"
        x, y = lon_lat_to_tile(lon, lat, z)
        context = {"sat_id": sat, "sector": sector, "product": product,
                   "frame_key": frame_row["frame_key"], "z": z, "x": x, "y": y, "tiles": "3x3"}
        purge_target = bench._frame_tile_dir(SCRATCH, sat, sector, product, context["frame_key"]).resolve()
        assert purge_target.is_relative_to((SCRATCH / "satellite/tiles").resolve())
        states = ["source_local_fresh_process_no_artifact"]
        if iteration == 1:
            states += ["decoded_source_warm_no_artifact"] * 3 + ["derived_artifact_hit"] * 3
        for index, state in enumerate(states):
            os.environ["WX_SATELLITE_V2_BENCH_SCENARIO"] = state
            os.environ["WX_SATELLITE_V2_BENCH_ITERATION"] = str(index + 1)
            row = measure(state, lambda: bench._resolve_once(SCRATCH, context, frame,
                          purge=state != "derived_artifact_hit"))
            row["png"] = png_contract(tile_path(SCRATCH, sat, sector, product, context["frame_key"], z, x, y))
            rows.append(row)
        sink = SCRATCH / "satellite/.bench" / f"{run_id}.jsonl"
        settings["satellite_context"] = context
        settings["satellite_native_timings"] = [json.loads(line) for line in sink.read_text().splitlines()]
    write_json(OUT / f"baseline-{case}-{iteration}.json", {
        "case": case, "iteration": iteration, "settings": settings, "rows": rows,
        "logical_cpus": psutil.cpu_count(), "host_memory_bytes": psutil.virtual_memory().total,
        "limitations": ["No browser/OBS or concurrent request test; ambient desktop load was not controlled.",
                        "50 ms process RSS/private sampling can miss transient peaks; no GPU residency or paging telemetry.",
                        "Process CPU includes sampler; startup/import time excluded from per-state measurements.",
                        "Fresh process does not mean cold operating-system file cache.",
                        "RTMA warm state retains parsed datasets; lazy field arrays can still decode on access."]})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("local", "meteosat"))
    parser.add_argument("--child")
    parser.add_argument("--iteration", type=int)
    args = parser.parse_args()
    if args.child:
        child(args.child, args.iteration)
        return
    assert args.phase
    ledger = OUT / "baseline-batch.json"
    batch = json.loads(ledger.read_text()) if ledger.exists() else {
        "active_child_seconds": 0, "runs": [], "limits": {"seconds": 2700, "scratch_bytes": 10 * 1024**3}}
    if any(r.get("exit_code") != 0 for r in batch["runs"]):
        raise RuntimeError("Prior failed run requires inspection before continuing")
    cases = list(SAT_CASES) if args.phase == "meteosat" else ["radar-ref", "radar-rho", "rtma-winds"]
    for case in cases:
        for iteration in range(1, 4):
            assert not (OUT / f"baseline-{case}-{iteration}.json").exists(), "Preserve completed run"
            scratch_bytes = sum(p.stat().st_size for p in SCRATCH.rglob("*") if p.is_file())
            assert scratch_bytes < batch["limits"]["scratch_bytes"]
            remaining = 2700 - batch["active_child_seconds"]
            assert remaining > 0
            command = [sys.executable, str(Path(__file__).resolve()), "--child", case, "--iteration", str(iteration)]
            started = time.perf_counter()
            log_path = SCRATCH / f"baseline-{case}-{iteration}.log"
            with log_path.open("w", encoding="utf-8") as log:
                try:
                    result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                            timeout=min(300, remaining))
                    exit_code = result.returncode
                except subprocess.TimeoutExpired:
                    exit_code = "timeout"
            elapsed = time.perf_counter() - started
            batch["active_child_seconds"] += elapsed
            batch["runs"].append({"case": case, "iteration": iteration, "command": command,
                                  "wall_seconds": elapsed, "exit_code": exit_code})
            write_json(ledger, batch)
            print(f"{case} repetition {iteration}: exit {exit_code}, {elapsed:.2f} seconds", flush=True)
            if exit_code != 0:
                raise SystemExit("Stopped at first failure; inspect the isolated log.")


if __name__ == "__main__":
    main()
