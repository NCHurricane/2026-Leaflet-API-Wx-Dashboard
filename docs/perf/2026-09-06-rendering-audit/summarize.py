"""Summarize completed baseline samples without calling any renderer."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]


def main():
    groups = defaultdict(list)
    native_groups = defaultdict(list)
    hashes = defaultdict(set)
    for path in sorted(OUT.glob("baseline-*-*.json")):
        report = json.loads(path.read_text())
        for native in report["settings"].get("satellite_native_timings", []):
            native_groups[(report["case"], native["scenario"])].append(native)
        for row in report["rows"]:
            groups[(report["case"], row["state"])].append(row)
            image = row.get("png") or row["result"]
            hashes[report["case"]].add(image["rgba_sha256"])
    results = []
    for (case, state), rows in groups.items():
        walls = [r["wall_seconds"] for r in rows]
        row = {"case": case, "state": state, "samples": len(rows),
               "wall_median_seconds": median(walls), "wall_range_seconds": [min(walls), max(walls)],
               "cpu_median_seconds": median(r["cpu_seconds"] for r in rows),
               "rss_max_bytes": max(r["rss_peak_sampled"] for r in rows),
               "private_max_bytes": max(r["private_peak_sampled"] for r in rows),
               "peak_threads": max(s["threads"] for r in rows for s in r["samples"]),
               "minimum_host_available_bytes": min(s["host_available"] for r in rows for s in r["samples"])}
        if case.startswith("radar"):
            keys = ("read_ms", "field_ms", "plot_ms", "encode_ms", "webgl_artifact_ms", "png_size", "webgl_artifact_bytes")
            row["stage_medians"] = {k: median(r["result"][k] for r in rows)
                                    for k in keys if all(k in r["result"] for r in rows)}
        if case == "rtma-winds":
            row["stage_medians_seconds"] = {k: median(r["result"]["stages_seconds"][k] for r in rows)
                                            for k in rows[0]["result"]["stages_seconds"]}
        if (case, state) in native_groups:
            natives = native_groups[(case, state)]
            row["native_stage_medians_ms"] = {k: median(n.get(k, 0) for n in natives)
                                              for k in sorted(set().union(*(n.keys() for n in natives)))
                                              if "_ms" in k}
        results.append(row)
    batch = json.loads((OUT / "baseline-batch.json").read_text())
    scratch = ROOT / "cache/rendering-audit-20260906"
    result = {
        "timing_cells_exercised": len(hashes), "samples": sum(len(r) for r in groups.values()),
        "active_child_seconds_including_imports": batch["active_child_seconds"],
        "scratch_bytes_including_sources": sum(p.stat().st_size for p in scratch.rglob("*") if p.is_file()),
        "pixel_repeatability": {k: {"distinct_rgba_hashes": len(v), "sha256": sorted(v)} for k, v in hashes.items()},
        "summaries": results,
        "collector_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob("*.py")},
        "timing_note": "Outer wall includes resource sampler startup. Use native Satellite timing for sub-millisecond hit work; sampler overhead dominates its outer wall.",
    }
    assert all(len(v) == 1 for v in hashes.values()), "Investigate pixel drift before comparisons"
    assert all(row["samples"] == 3 for row in results)
    (OUT / "baseline-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
