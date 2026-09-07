"""Small offline native-detail reference using the existing FCI renderer.

This changes the source cap only for reference construction, not runtime policy.
Six 3x3 canvases, one channel, one pinned frame, no benchmark repetitions.
"""

from __future__ import annotations

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
WORK = SCRATCH / "m12-detail-reference"
sys.path.insert(0, str(ROOT))


def main():
    def audit(event, args):
        if event == "socket.connect":
            raise RuntimeError("No network in native-detail reference")
    sys.addaudithook(audit)
    os.environ["MPLBACKEND"] = "Agg"
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    import numpy as np
    import psutil
    from PIL import Image
    from satellite_v2.renderer import SatelliteTileRenderer, _load_fci_source_rasters
    from satellite_v2.tiler import lon_lat_to_tile

    report_path = OUT / "m12-detail-reference.json"
    assert not report_path.exists() and not WORK.exists(), "Preserve completed reference"
    assert WORK.resolve().is_relative_to(SCRATCH.resolve())
    acquisition = json.loads((OUT / "meteosat-acquisition.json").read_text())
    inputs = [r for r in acquisition["transfers"] if r["path"].endswith(".nc")]
    assert len(inputs) == 40
    for record in inputs:
        with (ROOT / record["path"]).open("rb") as handle:
            assert hashlib.file_digest(handle, "sha256").hexdigest() == record["sha256"]
    assert psutil.virtual_memory().available > 8 * 1024**3
    WORK.mkdir(parents=True)
    started = time.monotonic()
    done = threading.Event()
    resources = []
    process = psutil.Process()

    def guard():
        while not done.wait(0.1):
            memory = process.memory_info()
            available = psutil.virtual_memory().available
            resources.append({"seconds": time.monotonic() - started, "rss": memory.rss,
                              "private": memory.private, "host_available": available})
            if memory.rss > 6 * 1024**3 or available < 4 * 1024**3 or time.monotonic() - started > 180:
                # Child owns only reference outputs. Stop instead of continuing a native call under pressure.
                print("Native-reference resource/time limit reached", flush=True)
                os._exit(2)
    monitor = threading.Thread(target=guard, daemon=True)
    monitor.start()
    cases = (("interior", 0, 5), ("equatorial-chunk-boundary", 0, 0), ("east-limb", 80, 0))
    results = {}
    try:
        for label, cap in (("current", 10848), ("native", 11136)):
            raster = _load_fci_source_rasters(ROOT / inputs[0]["path"], ("Channel02",), max_grid=cap)
            renderer = SatelliteTileRenderer("Channel02", raster, instrument="FCI")
            source = raster["Channel02"]
            variant = {"max_grid": cap, "shape": list(source.cmi.shape),
                       "retained_array_bytes": source.cmi.nbytes,
                       "source_transform": list(source.src_transform), "canvases": {}}
            for name, lon, lat in cases:
                x, y = lon_lat_to_tile(lon, lat, 8)
                image = renderer.render_zoom_canvas(8, x - 1, y - 1, x + 1, y + 1)
                path = WORK / f"{name}-{label}.png"
                image.save(path)
                variant["canvases"][name] = {"path": path.relative_to(ROOT).as_posix(),
                                             "z": 8, "x": x, "y": y,
                                             "rgba_sha256": hashlib.sha256(image.tobytes()).hexdigest()}
                if label == "current" and name == "interior":
                    crop = image.crop((256, 256, 512, 512))
                    expected = json.loads((OUT / "baseline-m12-visible-1.json").read_text())["rows"][0]["png"]["rgba_sha256"]
                    assert hashlib.sha256(crop.tobytes()).hexdigest() == expected, "Reference control differs from recorded baseline"
                image.close()
            results[label] = variant
            del renderer, source, raster
            gc.collect()
    finally:
        done.set()
        monitor.join()
    differences = {}
    for name, _, _ in cases:
        with Image.open(WORK / f"{name}-current.png") as image:
            current = np.asarray(image.convert("RGBA")).copy()
        with Image.open(WORK / f"{name}-native.png") as image:
            native = np.asarray(image.convert("RGBA")).copy()
        overlap = (current[:, :, 3] > 0) & (native[:, :, 3] > 0)
        delta = np.abs(current[:, :, :3].astype(np.int16) - native[:, :, :3].astype(np.int16))
        per_pixel = delta.max(axis=2)[overlap]
        differences[name] = {
            "mutually_opaque_pixels": int(overlap.sum()),
            "rgb_absolute_difference_mean": float(delta[overlap].mean()),
            "pixel_max_rgb_difference_p95": float(np.percentile(per_pixel, 95)),
            "pixel_max_rgb_difference_max": int(per_pixel.max()),
            "fraction_mutually_opaque_pixels_difference_gt_1": float((per_pixel > 1).mean()),
            "fraction_mutually_opaque_pixels_difference_gt_8": float((per_pixel > 8).mean()),
            "alpha_mismatch_pixels": int(np.count_nonzero(current[:, :, 3] != native[:, :, 3])),
        }
    report = {
        "category": "quality_reference_not_equal_quality_performance_comparison",
        "source_frame": next(f for f in acquisition["frames"] if f["sat"] == "meteosat12"),
        "baseline_control_center_hash_matches": True,
        "variants": results, "differences": differences,
        "resources": resources, "wall_seconds_after_source_hashing": time.monotonic() - started,
        "limits": {"seconds_after_hashing": 180, "rss_bytes": 6 * 1024**3,
                   "minimum_host_available_bytes": 4 * 1024**3, "canvases": 6},
        "limitations": ["Full-resolution reference shares the current calibration and warp; it is not an independent geolocation reference.",
                        "Pixel differences measure output impact, not a perceptual score or accepted tolerance.",
                        "Three scenes at z8 do not validate all products, zoom transitions, seasons, or limbs.",
                        "Reference array loading bypasses runtime admission; production cap and memory policy were not changed.",
                        "No browser, OBS, new download or architecture performance experiment."]}
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"differences": differences,
                      "wall_seconds_after_source_hashing": report["wall_seconds_after_source_hashing"]}, indent=2))


if __name__ == "__main__":
    main()
