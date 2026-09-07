"""Bounded offline contract/quality experiment. No application implementation.

Run once with a unique --run-id. A parent watchdog meters both child phases;
failures and consumed execution time remain in the immutable run ledger.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
GIB = 1024**3


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def isolate(work):
    sys.dont_write_bytecode = True
    os.environ["MPLBACKEND"] = "Agg"
    os.environ["MPLCONFIGDIR"] = str(work / "matplotlib")

    def within(path):
        if isinstance(path, (str, bytes, os.PathLike)):
            if os.path.normcase(os.fsdecode(path)) == os.path.normcase(os.devnull):
                return  # Windows platform discovery redirects only to its null device.
            path = Path(os.fsdecode(path)).resolve()
            if not path.is_relative_to(work):
                raise RuntimeError(f"Offline experiment write outside its scratch: {path}")

    def audit(event, args):
        if event in {"socket.connect", "socket.getaddrinfo"}:
            raise RuntimeError("No network in first-use contract verification")
        if event == "open":
            path, mode, flags = args
            if (mode and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                within(path)
        elif event in {"os.mkdir", "os.remove", "os.rmdir"}:
            within(args[0])
        elif event in {"os.rename", "os.link", "os.symlink"}:
            within(args[0])
            within(args[1])
    sys.addaudithook(audit)


def contracts(work):
    import unittest
    import test_fci_first_use_contract

    suite = unittest.defaultTestLoader.loadTestsFromModule(test_fci_first_use_contract)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    write(work / "contracts.json", {"tests": result.testsRun, "passed": result.wasSuccessful(),
                                    "failures": len(result.failures), "errors": len(result.errors)})
    if not result.wasSuccessful():
        raise RuntimeError("Contract tests failed; quality phase not started")


def quality(work):
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    import numpy as np
    import psutil
    from PIL import Image
    from config.satellite_v2_config import fci_channel_for_source_channel, source_channels_for_product
    from app_core.render_budget import satellite_render_slot
    from satellite_v2 import fci_windows as native
    from satellite_v2.renderer import SatelliteTileRenderer, SourceRaster
    from fci_first_use_contract import Bundle, Demand, File, Index, Owner, Pending, Scheduler, Strip

    report = {"category": "offline_contract_and_exact_quality_not_timing_or_live_ingestion",
              "cases": [], "sources": [], "simulation": [], "network_requests": 0,
              "cold_geometry": "unsupported_until_all_expected_headers_arrive",
              "trusted_index_mode": "all_header_oracle_only_not_current_product_discovery"}
    correction = json.loads((OUT / "fci-limb-correction-fixture.json").read_text())
    acquisition = json.loads((OUT / "meteosat-acquisition.json").read_text())
    viewport = json.loads((OUT / "fci-limb-viewport-references.json").read_text())["cases"]
    original = json.loads((OUT / "fci-window-quality-v2.json").read_text())["cases"]
    groups = [
        ("20260906T233000Z", correction["files"],
         [{"case": "viewport-" + "-".join(map(str, c["xyz"])), "product": "Channel02",
           "target": [*c["xyz"], *c["xyz"][1:]], "reference_path": c["path"],
           "reference_rgba_sha256": c["rgba_sha256"]} for c in viewport]),
        ("20260906T120000Z", [f for f in acquisition["transfers"] if f["path"].endswith(".nc")], original),
    ]
    # Preflight every source/reference before expensive native operations.
    for _, sources, cases in groups:
        for row in sources:
            path = ROOT / row["path"]
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != row["sha256"]:
                    raise ValueError(f"Pinned source hash mismatch: {path.name}")
        for case in cases:
            if not (ROOT / case["reference_path"]).is_file():
                raise FileNotFoundError(case["reference_path"])

    for frame_key, sources, cases in groups:
        paths = tuple(sorted(ROOT / row["path"] for row in sources))
        source_rows = {Path(row["path"]).name: row for row in sources}
        channels = tuple(dict.fromkeys(ch for c in cases for ch in source_channels_for_product(c["product"])))
        natives = tuple(dict.fromkeys(fci_channel_for_source_channel(ch) for ch in channels))
        # Complete reference metadata is deliberately labeled as an oracle.
        metadata = {p.name: native._metadata(p, natives) for p in paths}
        files = {}
        for path in paths:
            spans = []
            for ch, (start, end, cols, attrs, axes, _) in metadata[path.name].items():
                geometry = hashlib.sha256(json.dumps([attrs, axes], sort_keys=True, default=str).encode()).hexdigest()
                spans.append(Strip(ch, start, end, cols, geometry))
            files[path.name] = File(path.name, source_rows[path.name]["sha256"], path.stat().st_size, tuple(spans))
        names = tuple(files)
        index = Index(tuple((name, f.strips) for name, f in files.items()))
        reference_frame = native.Frame(paths, native._signature(paths))
        reference_frame.grids_for(natives, complete=True)
        cold = Bundle(frame_key, names)
        for name in (names[0], names[-1]):
            cold.arrive(files[name], revision=frame_key)
        assert cold.index is None  # Endpoint dimensions alone do not grant readiness.
        report["sources"].append({"frame": frame_key, "count": len(paths),
                                  "bytes": sum(f.size for f in files.values()), "sha256_verified": True,
                                  "cold_after_endpoints": "pending", "native_channels": natives})
        planned = []
        for case in cases:
            channels = source_channels_for_product(case["product"])
            natives_case = tuple(dict.fromkeys(fci_channel_for_source_channel(ch) for ch in channels))
            target = tuple(case["target"])
            grids, windows, full = reference_frame.plan(natives_case, target, 256)
            deps = frozenset(names) if full else index.dependencies(windows, offdisk=not windows)
            planned.append((case, target, channels, natives_case, grids, windows, full, deps))

        if frame_key == "20260906T233000Z":
            for mode in ("whole-bundle", "tile-prioritized-six", "viewport-prioritized", "cold-no-index"):
                bundle = Bundle(frame_key, names, index if mode != "cold-no-index" else None)
                schedule = Scheduler({"frame": bundle}, workers=4)
                owner = Owner("fixture", "M12/Channel02", 1, 1)
                schedule.register(Demand(owner, "frame", "discovery", frozenset((names[0], names[-1])), 0))
                schedule.register(Demand(owner, "frame", "complete", frozenset(names), 4))
                announced = 0

                def announce(stop):
                    nonlocal announced
                    for n in range(announced, stop):
                        schedule.register(Demand(owner, "frame", str(n), planned[n][-1], 1 if n == 0 else 2))
                    announced = stop

                if mode in {"whole-bundle", "cold-no-index"}:
                    announced = len(planned)
                else:
                    announce(6 if mode == "tile-prioritized-six" else len(planned))
                first = complete_view = first_reference = None
                completion_order = []
                while not bundle.complete:
                    jobs = schedule.dispatch(available=32 * GIB, headroom=4 * GIB)
                    assert jobs, "Scheduler made no progress"
                    # Virtual, reverse completion of each batch; no clock-based latency.
                    for job in reversed(jobs):
                        schedule.finish(job, files[job[1]])
                        completion_order.append(job[1])
                        ready = {n for n, p in enumerate(planned[:announced]) if p[-1] <= bundle.files.keys()}
                        if bundle.index is None or (mode == "whole-bundle" and not bundle.complete):
                            ready.clear()
                        useful = {n for n in ready if planned[n][-1]}
                        counts = {"completed_files": len(bundle.files), "completed_body_bytes": sum(f.size for f in bundle.files.values())}
                        if useful and first is None:
                            first = counts
                        if 0 in ready and first_reference is None:
                            first_reference = counts
                        if mode == "tile-prioritized-six" and ready:
                            # Optimistic slot-release model: announce one next tile per ready request.
                            announce(min(len(planned), 6 + len(ready)))
                        if len(ready) == len(planned) and complete_view is None:
                            complete_view = counts
                report["simulation"].append({"mode": mode, "first_useful_tile": first,
                                              "first_reference_tile": first_reference, "complete_viewport": complete_view,
                                              "body_completion_order": completion_order,
                                              "no_latency_prediction": True})

        # Exactly one native candidate render per retained quality case.
        for case, target, channels, natives_case, grids, windows, full, deps in planned:
            bundle = Bundle(frame_key, names, index)
            for name in sorted(deps, reverse=True):
                if len(bundle.files) < len(deps):
                    try:
                        bundle.snapshot(windows, offdisk=not windows, full=full)
                    except Pending:
                        pass
                    else:
                        raise AssertionError("Premature native-window readiness")
                bundle.arrive(files[name], revision=frame_key)
            snapshot = bundle.snapshot(windows, offdisk=not windows, full=full)
            selected_paths = tuple(p for p in paths if p.name in deps)
            if selected_paths:
                subset_frame = native.Frame(selected_paths, native._signature(selected_paths))
            width, height = (target[3] - target[1] + 1) * 256, (target[4] - target[2] + 1) * 256
            estimate = native.estimate_working_bytes(grids, windows, width * height, len(channels))
            native._trim(native.cache_limit_bytes())
            memory = psutil.virtual_memory()
            if memory.available < estimate + max(4 * GIB, memory.total // 8):
                raise Pending("Prototype native admission lacks reviewed headroom")
            acquired, weight = native._OWNER.acquire(1)
            assert acquired
            try:
                with bundle.pin(snapshot), satellite_render_slot(estimate + native._ARRAY_BYTES) as admitted:
                    assert admitted
                    if windows:
                        rasters = native._load(subset_frame, natives_case, grids, windows, full, native.cache_limit_bytes())
                        concrete = SatelliteTileRenderer(case["product"],
                                                         {ch: rasters[fci_channel_for_source_channel(ch)] for ch in channels},
                                                         dict.fromkeys(channels, paths[0]), "FCI")
                        candidate = concrete.render_zoom_canvas(*target)
                    else:
                        rasters = {ch: SourceRaster(np.empty((0, 0), dtype=np.float32),
                                                   grids[fci_channel_for_source_channel(ch)].transform,
                                                   grids[fci_channel_for_source_channel(ch)].crs) for ch in channels}
                        concrete = SatelliteTileRenderer(case["product"], rasters, dict.fromkeys(channels, paths[0]), "FCI")
                        samples = {ch: np.full((height, width), np.nan, dtype=np.float32) for ch in channels}
                        candidate = concrete._composite_image(samples, *target[:3], width, height, 256)
                    if selected_paths and native._signature(selected_paths) != subset_frame.signature:
                        raise ValueError("Source file changed during native reading")
                    # A newly completed unrelated body must not cancel this output.
                    unrelated = next((name for name in names if name not in deps), None)
                    if unrelated:
                        bundle.arrive(files[unrelated], revision=frame_key)
                    with Image.open(ROOT / case["reference_path"]) as reference:
                        actual, expected = np.asarray(candidate.convert("RGBA")), np.asarray(reference.convert("RGBA"))
                        exact = np.array_equal(actual, expected)
                        digest = hashlib.sha256(actual.tobytes()).hexdigest()
                        assert exact, case["case"]
                        if "reference_rgba_sha256" in case:
                            assert digest == case["reference_rgba_sha256"]
                    output = work / (case["case"] + ".png")
                    tmp = output.with_suffix(".tmp")

                    def publish():
                        candidate.save(tmp, format="PNG")
                        if selected_paths and native._signature(selected_paths) != subset_frame.signature:
                            raise ValueError("Dependency changed before publication")
                        os.replace(tmp, output)

                    bundle.publish(snapshot, lambda: True, publish)
                    candidate.close()
            finally:
                native._OWNER.release(weight)
            report["cases"].append({"case": case["case"], "frame": frame_key, "whole_rgba_exact": bool(exact),
                                    "rgba_sha256": digest, "required_files": len(deps), "full_native_fallback": full,
                                    "unrelated_arrival_preserved_snapshot": unrelated is not None,
                                    "native_window_admission_bytes": estimate,
                                    "retained_array_bytes": native._ARRAY_BYTES})
            write(work / "quality.json", report)
            print(f"Exact native RGBA: {case['case']} ({len(deps)}/{len(names)} dependencies)", flush=True)
        native._trim(0)
        assert native._signature(paths) == reference_frame.signature
    report["all_checks_passed"] = True
    report["cold_live_activation_recommended"] = False
    write(work / "quality.json", report)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--phase", choices=("contracts", "quality"))
    parser.add_argument("--previous-run")
    args = parser.parse_args()
    if not args.run_id.replace("-", "").isalnum():
        raise ValueError("Unsafe run id")
    work = (ROOT / "cache/rendering-audit-20260906" / args.run_id).resolve()
    if args.phase:
        isolate(work)
        return (contracts if args.phase == "contracts" else quality)(work)

    import psutil
    ledger_path = OUT / (args.run_id + ".json")
    if work.exists() or ledger_path.exists():
        raise RuntimeError("Preserve prior run evidence; no implicit restart of allocation")
    work.mkdir(parents=True)
    ledger = {"category": "bounded_offline_contract_execution_not_benchmark", "phases": [],
              "approved_limits": {"combined_child_seconds": 900, "scratch_bytes": 2 * GIB,
                                  "child_rss_bytes": 6 * GIB, "minimum_host_available": "max(4 GiB, total/8)",
                                  "provider_requests": 0, "download_bytes": 0, "timing_samples": 0},
              "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "script_sha256": {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in
                                (Path(__file__).name, "fci_first_use_contract.py", "test_fci_first_use_contract.py")},
              "status": "started"}
    validation = json.loads((OUT / "fci-limb-correction-validation.json").read_text())
    ledger["runtime_sha256"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                for name in validation["runtime_sha256"]}
    assert ledger["runtime_sha256"] == validation["runtime_sha256"], "Runtime changed since checkpoint"
    previous_seconds = 0.0
    if args.previous_run:
        if not args.previous_run.replace("-", "").isalnum():
            raise ValueError("Unsafe previous run id")
        previous = json.loads((OUT / (args.previous_run + ".json")).read_text())
        previous_seconds = previous["combined_child_seconds"]
        ledger["previous_run"] = args.previous_run
        ledger["previous_consumed_child_seconds"] = previous_seconds
    write(ledger_path, ledger)
    total = previous_seconds
    for phase in ("contracts", "quality"):
        memory = psutil.virtual_memory()
        if memory.available < max(4 * GIB, memory.total // 8):
            ledger["status"] = "stopped-before-phase-for-host-headroom"
            write(ledger_path, ledger)
            return 2
        log = work / (phase + ".log")
        with log.open("w", encoding="utf-8") as stream:
            started = time.monotonic()
            process = subprocess.Popen([sys.executable, "-B", str(Path(__file__)), "--run-id", args.run_id,
                                        "--phase", phase], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
            monitor = psutil.Process(process.pid)
            peak, minimum, scratch, reason = 0, memory.available, 0, None
            while process.poll() is None:
                try:
                    peak = max(peak, sum(p.memory_info().rss for p in [monitor, *monitor.children(recursive=True)]))
                    memory = psutil.virtual_memory()
                    minimum = min(minimum, memory.available)
                    scratch = sum(p.stat().st_size for p in work.rglob("*") if p.is_file())
                    if (total + time.monotonic() - started > 900 or peak > 6 * GIB
                            or memory.available < max(4 * GIB, memory.total // 8) or scratch > 2 * GIB):
                        reason = "resource-bound"
                        process.kill()
                        break
                except psutil.NoSuchProcess:
                    break
                time.sleep(0.05)
            code = process.wait()
            elapsed = time.monotonic() - started
            total += elapsed
        ledger["phases"].append({"phase": phase, "exit_code": code, "stop_reason": reason,
                                  "child_seconds": elapsed, "peak_sampled_child_rss": peak,
                                  "minimum_sampled_host_available": minimum, "scratch_bytes": scratch,
                                  "log": log.relative_to(ROOT).as_posix()})
        ledger["combined_child_seconds"] = total
        if code or reason:
            ledger["status"] = "failed-or-stopped"
            write(ledger_path, ledger)
            print(log.read_text(encoding="utf-8")[-5000:])
            return 1
        ledger[phase] = json.loads((work / (phase + ".json")).read_text())
        write(ledger_path, ledger)
        print(f"{phase} passed; consumed {total:.2f}/900 child seconds", flush=True)
    ledger["status"] = "passed"
    write(ledger_path, ledger)
    print(json.dumps({"status": "passed", "tests": ledger["contracts"]["tests"],
                      "exact_quality_cases": len(ledger["quality"]["cases"]),
                      "cold_live_activation_recommended": False}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
