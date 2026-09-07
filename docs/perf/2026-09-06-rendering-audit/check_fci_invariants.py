"""Offline prototype cache and independent Earth-visibility diagnostics."""

import hashlib
import json
import os
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT))


def main():
    report_path = OUT / "fci-window-invariants.json"
    assert not report_path.exists(), "Preserve prior evidence"

    def audit(event, values):
        if event == "socket.connect":
            raise RuntimeError("No network in prototype invariant checks")

    sys.addaudithook(audit)
    os.environ["MPLBACKEND"] = "Agg"
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    import netCDF4
    import numpy as np
    from PIL import Image
    from fci_window_prototype import WindowLoader

    acquisition = json.loads((OUT / "meteosat-acquisition.json").read_text())
    paths = [ROOT / r["path"] for r in acquisition["transfers"] if r["path"].endswith(".nc")]
    report = {"category": "prototype_invariant_checks_not_browser_acceptance",
              "prototype_sha256": hashlib.sha256((OUT / "fci_window_prototype.py").read_bytes()).hexdigest()}
    loader = WindowLoader(paths, ("Channel02",), cache_bytes=2 * 1024**2)
    target = (8, 127, 123, 129, 125)
    first, first_stats = loader.load(("Channel02",), *target)
    digest = hashlib.sha256(first["Channel02"].cmi.tobytes()).hexdigest()
    warm, warm_stats = loader.load(("Channel02",), *target)
    assert warm["Channel02"] is first["Channel02"]
    assert warm_stats["channels"][0]["cache_hit"] and warm_stats["plan_cache_hit"]
    assert not first_stats["channels"][0]["cache_hit"]
    checks = []
    for offset in range(1, 10):
        shifted = (8, 127 + offset, 123, 129 + offset, 125)
        rasters, stats = loader.load(("Channel02",), *shifted)
        actual = sum(r.cmi.nbytes for r in loader.cache.values())
        assert actual == loader.cache_bytes <= loader.cache_limit
        assert len(loader.plans) <= 8
        checks.append({"offset": offset, "retained_array_bytes": actual,
                       "cache_entries": len(loader.cache), "plan_entries": len(loader.plans)})
        del rasters
    again, again_stats = loader.load(("Channel02",), *target)
    assert not again_stats["channels"][0]["cache_hit"]
    assert not again_stats["plan_cache_hit"]
    assert hashlib.sha256(again["Channel02"].cmi.tobytes()).hexdigest() == digest
    # Caller-held references remain valid after eviction and are intentionally
    # outside the retained-cache counter. Admission must account for both.
    assert hashlib.sha256(first["Channel02"].cmi.tobytes()).hexdigest() == digest
    report["eviction"] = {"pass": True, "cache_limit": loader.cache_limit,
                          "steps": checks, "reloaded_float32_source_sha256": digest,
                          "caller_reference_valid_after_eviction": True}
    aliases = WindowLoader(paths, ("Channel13", "Channel14"), cache_bytes=2 * 1024**2)
    rasters, stats = aliases.load(("Channel13", "Channel14"), *target)
    assert rasters["Channel13"] is rasters["Channel14"]
    assert len(stats["channels"]) == 1 and len(aliases.cache) == 1
    assert aliases.cache_bytes == rasters["Channel13"].cmi.nbytes
    report["physical_channel_alias"] = {"pass": True, "loader": stats}
    aliases.cache.clear()
    aliases.cache_bytes = 0
    aliases.cache_limit = 0
    _, stats = aliases.load(("Channel13", "Channel14"), *target)
    assert not aliases.cache and stats["cache_bytes"] == 0
    assert not stats["channels"][0]["cache_hit"]
    report["zero_cache_limit"] = {"pass": True}

    # Ellipsoid surface normal dotted with the surface-to-satellite vector:
    # positive means the surface is visible from the satellite. This uses
    # neither GDAL's geostationary warp nor the prototype's source window.
    with netCDF4.Dataset(paths[0]) as ds:
        projection = ds.groups["data"].variables["mtg_geos_projection"]
        attrs = {k: getattr(projection, k) for k in projection.ncattrs()}
    a, b = float(attrs["semi_major_axis"]), float(attrs["semi_minor_axis"])
    height = float(attrs["perspective_point_height"])
    lon0 = float(attrs["longitude_of_projection_origin"])
    pixels = np.arange(768) + 0.5
    lon = np.radians((183 + pixels / 256) / 2**8 * 360 - 180 - lon0)
    lat = np.arctan(np.sinh(np.pi * (1 - 2 * (127 + pixels / 256) / 2**8)))
    lon, lat = np.meshgrid(lon, lat)
    n = a / np.sqrt(1 - (1 - b**2 / a**2) * np.sin(lat)**2)
    visible = (a + height) * n * np.cos(lat) * np.cos(lon) / a**2 > 1
    masks = {}
    for variant in ("current", "native"):
        path = ROOT / f"cache/rendering-audit-20260906/m12-detail-reference/east-limb-{variant}.png"
        with Image.open(path) as image:
            opaque = np.asarray(image.convert("RGBA"))[:, :, 3] > 0
        masks[variant] = {"opaque_pixels": int(opaque.sum()),
                          "opaque_outside_geometric_earth": int((opaque & ~visible).sum()),
                          "visible_but_transparent_pixels": int((~opaque & visible).sum())}
        assert masks[variant]["opaque_outside_geometric_earth"] == 0
    report["limb_visibility"] = {"target": [8, 183, 127, 185, 129],
                                 "ellipsoid_metres": {"a": a, "b": b, "satellite_height": height, "lon0": lon0},
                                 "visible_pixel_centres": int(visible.sum()), "masks": masks,
                                 "formula": "N=a/sqrt(1-(1-b*b/(a*a))*sin(lat)^2); visible=(a+h)*N*cos(lat)*cos(lon-lon0)/(a*a)>1",
                                 "limitation": "Detects opacity outside the visible ellipsoid only; source validity inside the limb and geographic overlay alignment remain unverified."}
    report["all_checks_passed"] = True
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"all_checks_passed": True, "limb_visibility": report["limb_visibility"]}))


if __name__ == "__main__":
    main()
