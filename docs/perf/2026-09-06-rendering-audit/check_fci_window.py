"""Check the audit window prototype against pinned full-native output."""

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SCRATCH = ROOT / "cache/rendering-audit-20260906"
sys.path.insert(0, str(ROOT))

CASES = [
    ("interior", "Channel02", 8, 0, 5),
    ("equatorial-chunk-boundary", "Channel02", 8, 0, 0),
    ("east-limb", "Channel02", 8, 80, 0),
    ("visible-z4", "Channel02", 4, 18.22, 22.8),
    ("visible-z5", "Channel02", 5, 18.22, 22.8),
    ("visible-z6", "Channel02", 6, 18.22, 22.8),
    ("visible-z7", "Channel02", 7, 18.22, 22.8),
    ("ir-z5", "Channel13", 5, 0, 5),
    ("night-composite-z5", "NighttimeMicrophysics", 5, 0, 5),
    ("mixed-grid-diagnostic-z7", "DaySnowFog", 7, 0, 5),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--all-cases", action="store_true")
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--revision", choices=("v1", "v2"), default="v2")
    args = parser.parse_args()
    assert args.run_id.replace("-", "").isalnum()
    def audit(event, values):
        if event == "socket.connect":
            raise RuntimeError("No network in source-window audit")
    sys.addaudithook(audit)
    os.environ["MPLBACKEND"] = "Agg"
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    import numpy as np
    import psutil
    from PIL import Image
    from config.satellite_v2_config import source_channels_for_product
    from satellite_v2.renderer import SatelliteTileRenderer, _load_fci_source_rasters
    from satellite_v2.tiler import lon_lat_to_tile
    if args.revision == "v1":
        from fci_window_prototype_v1 import WindowLoader
        prototype_file = OUT / "fci_window_prototype_v1.py"
    else:
        from fci_window_prototype import WindowLoader
        prototype_file = OUT / "fci_window_prototype.py"

    work = SCRATCH / args.run_id
    assert not work.exists(), "Preserve earlier quality artifacts"
    work.mkdir()
    report = {"category": "prototype_quality_check_not_implementation_acceptance", "run_id": args.run_id,
              "revision": args.revision, "prototype_sha256": hashlib.sha256(prototype_file.read_bytes()).hexdigest(),
              "gate": {"max_rgb_delta": 1, "alpha_mismatch_pixels": 0}, "cases": []}
    report_path = OUT / (args.run_id + ".json")
    assert not report_path.exists()
    acquisition = json.loads((OUT / "meteosat-acquisition.json").read_text())
    paths = [ROOT / r["path"] for r in acquisition["transfers"] if r["path"].endswith(".nc")]
    selected = (CASES if args.all_cases else CASES[:3])[args.start_index:]
    assert selected
    done = threading.Event()
    started = time.monotonic()
    process = psutil.Process()
    peak_rss = 0

    def guard():
        nonlocal peak_rss
        while not done.wait(0.1):
            peak_rss = max(peak_rss, process.memory_info().rss)
            if peak_rss > 6 * 1024**3 or psutil.virtual_memory().available < 4 * 1024**3 or time.monotonic() - started > 600:
                print("Quality diagnostic resource/time guard reached", flush=True)
                os._exit(2)
    monitor = threading.Thread(target=guard, daemon=True)
    monitor.start()
    try:
        for name, product, z, lon, lat in selected:
            sources = source_channels_for_product(product)
            x, y = lon_lat_to_tile(lon, lat, z)
            target = (z, x - 1, y - 1, x + 1, y + 1)
            loader = WindowLoader(paths, sources)
            rasters, stats = loader.load(sources, *target)
            renderer = SatelliteTileRenderer(product, rasters, instrument="FCI")
            candidate = np.asarray(renderer.render_zoom_canvas(*target)).copy()
            candidate_path = work / (name + "-window.png")
            Image.fromarray(candidate).save(candidate_path)
            del renderer, rasters
            cache_stats = stats
            del loader
            gc.collect()
            existing = SCRATCH / "m12-detail-reference" / (name + "-native.png")
            if not existing.exists():
                existing = SCRATCH / "fci-window-quality-transitions-v1" / (name + "-reference.png")
            if existing.exists():
                with Image.open(existing) as image:
                    reference = np.asarray(image.convert("RGBA")).copy()
                reference_path = existing
            else:
                full = _load_fci_source_rasters(paths[0], sources, max_grid=11136)
                renderer = SatelliteTileRenderer(product, full, instrument="FCI")
                reference = np.asarray(renderer.render_zoom_canvas(*target)).copy()
                reference_path = work / (name + "-reference.png")
                Image.fromarray(reference).save(reference_path)
                del full, renderer
                gc.collect()
            opaque = (reference[:, :, 3] > 0) & (candidate[:, :, 3] > 0)
            delta = np.abs(reference[:, :, :3].astype(np.int16) - candidate[:, :, :3].astype(np.int16))
            max_rgb = int(delta[opaque].max()) if opaque.any() else 0
            alpha = int(np.count_nonzero(reference[:, :, 3] != candidate[:, :, 3]))
            row = {"case": name, "product": product, "target": target, "loader": cache_stats,
                   "max_rgb_delta": max_rgb, "alpha_mismatch_pixels": alpha,
                   "rgb_difference_mean": float(delta[opaque].mean()) if opaque.any() else 0,
                   "rgb_difference_gt_1_pixels": int(np.count_nonzero((delta.max(axis=2) > 1) & opaque)),
                   "pass": max_rgb <= 1 and alpha == 0,
                   "candidate_path": candidate_path.relative_to(ROOT).as_posix(),
                   "reference_path": reference_path.relative_to(ROOT).as_posix()}
            report["cases"].append(row)
            report_path.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(row), flush=True)
            if not row["pass"]:
                report["stopped_on_quality_difference"] = True
                break
    finally:
        done.set()
        monitor.join()
        report["peak_rss_sampled"] = peak_rss
        report["wall_seconds"] = time.monotonic() - started
        report["all_selected_cases_passed"] = len(report["cases"]) == len(selected) and all(r["pass"] for r in report["cases"])
        report_path.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
