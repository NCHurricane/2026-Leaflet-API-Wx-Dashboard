"""Final six allowed timing samples: integrated M12 visible and limb paths."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SCRATCH = ROOT / "cache/rendering-audit-20260906"
sys.path.insert(0, str(ROOT))


def child(args):
    def audit(event, values):
        if event == "socket.connect":
            raise RuntimeError("No network in integrated timing check")
    sys.addaudithook(audit)
    os.environ["MPLBACKEND"] = "Agg"
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from bench_fci_window import measure
    from satellite_v2.fci_windows import render_context
    from satellite_v2.renderer import SatelliteTileRenderer
    from satellite_v2.tiler import _publish_tile_image_to_target

    name = f"fci-integrated-{args.case}-{args.iteration}"
    work = SCRATCH / name
    assert not work.exists() and not (OUT / (name + ".json")).exists()
    work.mkdir()
    acquisition = json.loads((OUT / "meteosat-acquisition.json").read_text())
    primary = next(ROOT / row["path"] for row in acquisition["transfers"] if row["path"].endswith(".nc"))
    reference = json.loads((OUT / "fci-window-summary.json").read_text())["rgba_sha256_by_case"][args.case]
    target = (8, 127, 123, 129, 125) if args.case == "visible-z8" else (8, 183, 127, 185, 129)

    def operation():
        with render_context() as state:
            handle = SatelliteTileRenderer.from_sources("Channel02", {"Channel02": primary}, sat_id="meteosat12")
            canvas = handle.render_zoom_canvas(*target)
        digest = hashlib.sha256(canvas.tobytes()).hexdigest()
        statuses = []
        for row in range(3):
            for col in range(3):
                tile = canvas.crop((col*256, row*256, (col+1)*256, (row+1)*256))
                statuses.append(_publish_tile_image_to_target(tile, work / f"{col}-{row}.png", False))
                tile.close()
        canvas.close()
        assert digest == reference
        assert statuses == (["rendered"]*9 if args.case == "visible-z8" else ["rendered", "rendered", "invalid"]*3)
        return {"rgba_sha256": digest, "publication_statuses": statuses,
                "estimated_memory_bytes": state["estimated_memory_bytes"]}
    result = measure(operation)
    result.update(case=args.case, iteration=args.iteration, target=target)
    (OUT / (name + ".json")).write_text(json.dumps(result, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("visible-z8", "limb-z8"))
    parser.add_argument("--iteration", type=int)
    args = parser.parse_args()
    if args.case:
        child(args)
        return
    quality = json.loads((OUT / "fci-integration-quality-final.json").read_text())
    assert quality["all_checks_passed"]
    for name, digest in quality["runtime_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    report_path = OUT / "fci-integrated-pilot.json"
    assert not report_path.exists(), "Preserve completed six-sample check"
    report = {"category": "integrated_candidate_followup_against_prior_full_native_controls",
              "limits": {"samples": 6, "child_seconds": 120, "scratch_bytes": 10*1024**3, "new_downloads": 0},
              "combined_timed_samples_after_completion": 108, "runs": [], "comparisons": [],
              "runtime_sha256": quality["runtime_sha256"],
              "limitations": "Three fresh-process samples per case, local source and uncontrolled desktop/OS file cache. Prior full-native controls; no browser, OBS, history, low-memory-machine or p95 acceptance."}
    started = time.monotonic()
    controls = json.loads((OUT / "fci-window-summary.json").read_text())["groups"]
    for case in ("visible-z8", "limb-z8"):
        rows = []
        for iteration in range(1, 4):
            assert sum(path.stat().st_size for path in SCRATCH.rglob("*") if path.is_file()) < 10*1024**3
            remaining = 120 - (time.monotonic() - started)
            assert remaining > 0
            name = f"fci-integrated-{case}-{iteration}"
            command = [sys.executable, str(Path(__file__).resolve()), "--case", case, "--iteration", str(iteration)]
            began = time.monotonic()
            with (SCRATCH / (name + ".log")).open("x") as log:
                completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=remaining)
            row = {"case": case, "iteration": iteration, "child_seconds": time.monotonic() - began, "exit_code": completed.returncode}
            report["runs"].append(row)
            report_path.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(row), flush=True)
            assert completed.returncode == 0, "Stop and inspect; do not retry automatically"
            rows.append(json.loads((OUT / (name + ".json")).read_text()))
        control = next(row for row in controls if row["case"] == case and row["variant"] == "full" and row["state"] == "source_local_fresh_process")
        medians = {key: statistics.median(row[key] for row in rows) for key in ("wall_seconds", "cpu_seconds")}
        peaks = {key: max(row[key] for row in rows) for key in ("peak_rss_sampled", "peak_private_sampled")}
        comparison = {"case": case, "medians": medians, "maximum_sampled_bytes": peaks,
                      "wall_reduction_percent": 100*(1-medians["wall_seconds"]/control["wall_seconds"]["median"]),
                      "maximum_sampled_rss_reduction_percent": 100*(1-peaks["peak_rss_sampled"]/control["peak_rss_sampled"]["max"])}
        report["comparisons"].append(comparison)
        print(json.dumps(comparison), flush=True)
    report["all_six_completed"] = True
    report["wall_seconds"] = time.monotonic() - started
    report_path.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
