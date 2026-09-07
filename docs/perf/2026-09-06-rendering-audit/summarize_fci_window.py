"""Recalculate pilot summaries without running renderers or refreshing evidence."""

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]


def main():
    groups = defaultdict(list)
    hashes = defaultdict(set)
    sample_count = 0
    for path in sorted(OUT.glob("fci-pilot-*.json")):
        data = json.loads(path.read_text())
        if "rows" not in data:
            continue
        for row in data["rows"]:
            expected = (["rendered", "rendered", "invalid"] * 3
                        if data["case"] == "limb-z8" else ["rendered"] * 9)
            assert row["result"]["publication_statuses"] == expected
            groups[(data["case"], data["variant"], row["state"])].append(row)
            hashes[data["case"]].add(row["result"]["rgba_sha256"])
            sample_count += 1
    assert sample_count == 54 and len(groups) == 18
    assert all(len(values) == 1 for values in hashes.values())
    summary = []
    for (case, variant, state), rows in sorted(groups.items()):
        assert len(rows) == 3
        row = {"case": case, "variant": variant, "state": state, "n": len(rows)}
        for key in ("wall_seconds", "cpu_seconds", "peak_rss_sampled", "peak_private_sampled"):
            values = [r[key] for r in rows]
            row[key] = {"median": statistics.median(values), "min": min(values), "max": max(values)}
        row["stage_median_seconds"] = {key: statistics.median(r["result"][key] for r in rows)
                                       for key in ("loading_seconds", "rendering_seconds", "publication_seconds")}
        row["median_process_io_delta"] = {key: statistics.median(r["io_delta"][key] for r in rows)
                                          for key in rows[0]["io_delta"]}
        summary.append(row)
    comparisons = []
    by_key = {(r["case"], r["variant"], r["state"]): r for r in summary}
    for candidate in summary:
        if candidate["variant"] != "window-v2":
            continue
        control = by_key[(candidate["case"], "full", candidate["state"])]
        comparisons.append({"case": candidate["case"], "state": candidate["state"],
                            "median_wall_reduction_percent": 100 * (1 - candidate["wall_seconds"]["median"] / control["wall_seconds"]["median"]),
                            "median_cpu_reduction_percent": 100 * (1 - candidate["cpu_seconds"]["median"] / control["cpu_seconds"]["median"]),
                            "maximum_sampled_rss_reduction_percent": 100 * (1 - candidate["peak_rss_sampled"]["max"] / control["peak_rss_sampled"]["max"])})
    revisions = {}
    active_child_seconds = 0
    for revision, source, batch in (("v1", "fci_window_prototype_v1.py", "fci-pilot-batch.json"),
                                    ("v2", "fci_window_prototype.py", "fci-pilot-v2-batch.json")):
        digest = hashlib.sha256((OUT / source).read_bytes()).hexdigest()
        ledger = json.loads((OUT / batch).read_text())
        assert digest == ledger["prototype_sha256"]
        assert all(r["exit_code"] == 0 for r in ledger["runs"])
        active_child_seconds += sum(r["child_seconds"] for r in ledger["runs"])
        revisions[revision] = {"file": source, "sha256": digest, "batch": batch}
    quality = json.loads((OUT / "fci-window-quality-v2.json").read_text())
    assert quality["all_selected_cases_passed"] and len(quality["cases"]) == 10
    output_hashes = []
    for case in quality["cases"]:
        assert case["max_rgb_delta"] == 0 and case["alpha_mismatch_pixels"] == 0
        output_hashes.append({"case": case["case"], **{key + "_sha256": hashlib.sha256((ROOT / case[key]).read_bytes()).hexdigest()
                                                       for key in ("candidate_path", "reference_path")}})
    acquisition = json.loads((OUT / "meteosat-acquisition.json").read_text())
    inputs = [r for r in acquisition["transfers"] if r["path"].endswith(".nc")]
    assert len(inputs) == 40
    for source in inputs:
        with (ROOT / source["path"]).open("rb") as handle:
            assert hashlib.file_digest(handle, "sha256").hexdigest() == source["sha256"]
    invariants = json.loads((OUT / "fci-window-invariants.json").read_text())
    assert invariants["all_checks_passed"]
    assert invariants["prototype_sha256"] == revisions["v2"]["sha256"]
    scratch_bytes = sum(p.stat().st_size for p in (ROOT / "cache/rendering-audit-20260906").rglob("*") if p.is_file())
    report = {"category": "equal_native_quality_backend_prototype_pilot",
              "comparison_limit": "V1 was paired with fresh controls; V2 is a targeted later follow-up against those same controls. Three samples per cell are not p95 or cross-machine acceptance.",
              "timed_samples": sample_count, "baseline_plus_prototype_timed_samples": 48 + sample_count,
              "prototype_active_child_seconds": active_child_seconds, "current_total_audit_scratch_bytes": scratch_bytes,
              "revisions": revisions, "all_40_source_hashes_revalidated": True,
              "all_four_benchmark_cases_exact_rgba": True, "rgba_sha256_by_case": {key: next(iter(value)) for key, value in hashes.items()},
              "publication_parity": "All variants publish nine tiles for interior cases; limb publishes six PNGs and returns invalid/negative markers for the same three fully transparent eastern tiles.",
              "quality_output_file_hashes": output_hashes, "groups": summary, "v2_comparisons_to_prior_controls": comparisons}
    (OUT / "fci-window-summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"samples": sample_count, "scratch_bytes": scratch_bytes,
                      "active_child_seconds": active_child_seconds, "comparisons": comparisons}, indent=2))


if __name__ == "__main__":
    main()
