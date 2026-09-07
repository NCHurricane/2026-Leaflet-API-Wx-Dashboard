"""Offline real-source acceptance checks for the integrated native M12 path."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="fci-integration-quality")
    args = parser.parse_args()
    assert args.run_id.replace("-", "").isalnum()
    def audit(event, values):
        if event == "socket.connect":
            raise RuntimeError("No network during M12 integration verification")
    sys.addaudithook(audit)
    os.environ["MPLBACKEND"] = "Agg"
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    import numpy as np
    import psutil
    from PIL import Image
    from config.satellite_v2_config import source_channels_for_product
    from satellite_v2 import fci_windows, service, tiler
    from satellite_v2.renderer import SatelliteTileRenderer

    work = ROOT / "cache/rendering-audit-20260906" / args.run_id
    report_path = OUT / (args.run_id + ".json")
    assert not work.exists() and not report_path.exists(), "Preserve prior integration evidence"
    work.mkdir()
    acquisition = json.loads((OUT / "meteosat-acquisition.json").read_text())
    sources = [r for r in acquisition["transfers"] if r["path"].endswith(".nc")]
    assert len(sources) == 40
    for source in sources:
        with (ROOT / source["path"]).open("rb") as handle:
            assert hashlib.file_digest(handle, "sha256").hexdigest() == source["sha256"]
    primary = ROOT / sources[0]["path"]
    original = json.loads((OUT / "fci-window-quality-v2.json").read_text())
    report = {"category": "integrated_backend_quality_and_publication_checks_not_browser_acceptance", "cases": [], "service": [],
              "runtime_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                                 ("satellite_v2/fci_windows.py", "satellite_v2/fci_nc.py", "satellite_v2/renderer.py",
                                  "satellite_v2/tiler.py", "satellite_v2/service.py", "app_core/render_budget.py",
                                  "config/satellite_v2_config.py", "satellite_v2/meteosat_tile_worker.py")}}
    done = threading.Event()
    process = psutil.Process()
    started = time.monotonic()
    peaks = {"rss": 0, "private": 0}

    def guard():
        while not done.wait(0.05):
            memory = process.memory_info()
            for key in peaks:
                peaks[key] = max(peaks[key], getattr(memory, key))
            if peaks["rss"] > 6*1024**3 or psutil.virtual_memory().available < 4*1024**3 or time.monotonic() - started > 180:
                os._exit(2)
    monitor = threading.Thread(target=guard, daemon=True)
    monitor.start()
    try:
        for case in original["cases"]:
            channels = source_channels_for_product(case["product"])
            handle = SatelliteTileRenderer.from_sources(case["product"], dict.fromkeys(channels, primary), sat_id="meteosat12")
            assert not handle.source_rasters
            with fci_windows.render_context() as state:
                candidate = handle.render_zoom_canvas(*case["target"])
            with Image.open(ROOT / case["reference_path"]) as reference:
                a = np.asarray(candidate.convert("RGBA"))
                b = np.asarray(reference.convert("RGBA"))
                exact = np.array_equal(a, b)
            candidate_path = work / (case["case"] + ".png")
            candidate.save(candidate_path)
            candidate.close()
            row = {"case": case["case"], "whole_rgba_exact": bool(exact),
                   "rgba_sha256": hashlib.sha256(a.tobytes()).hexdigest(),
                   "estimated_memory_bytes": state["estimated_memory_bytes"],
                   "retained_cache_bytes": fci_windows._ARRAY_BYTES,
                   "candidate_path": candidate_path.relative_to(ROOT).as_posix()}
            report["cases"].append(row)
            report_path.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(row), flush=True)
            assert exact, case["case"]
        for name in ("interior", "east-limb"):
            case = next(row for row in original["cases"] if row["case"] == name)
            z, x0, y0, _, _ = case["target"]
            kwargs = dict(cache_root=work, sat_id="meteosat12", sector="FULLDISK", channel_key=case["product"],
                          frame={"frame_key": "20260906T120000Z"}, z=z, x=x0+1, y=y0+1)
            with patch.object(tiler, "download_product_source_frames", return_value={"Channel02": primary}) as download:
                path, stats = service._render_tile_with_budget(**kwargs)
                assert download.call_count == 1
                hit_path, hit_stats = service._render_tile_with_budget(**kwargs)
                assert download.call_count == 1 and hit_path == path and hit_stats["cache_status"] == "hit"
            with Image.open(path) as tile, Image.open(ROOT / case["reference_path"]) as reference:
                assert np.array_equal(np.asarray(tile), np.asarray(reference.crop((256, 256, 512, 512))))
            assert "products-fci6" in path.parts
            if name == "east-limb":
                assert stats["supertile_invalid"] == 3
            report["service"].append({"case": name, "native_centre_exact": True, "cache_hit_without_download": True,
                                      "path": path.relative_to(ROOT).as_posix(), "stats": stats})
        report["all_checks_passed"] = True
    finally:
        done.set()
        monitor.join()
        report["diagnostic_peak_sampled_bytes"] = peaks
        report["diagnostic_wall_seconds_not_benchmark"] = time.monotonic() - started
        report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"all_checks_passed": True, "cases": len(report["cases"]), "service_cases": len(report["service"])}))


if __name__ == "__main__":
    main()
