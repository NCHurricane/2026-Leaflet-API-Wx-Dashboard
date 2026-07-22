import importlib
import json
from pathlib import Path

import pytest

from satellite_v2 import bench
from satellite_v2.cache import source_path, tile_path


def test_timing_collector_is_disabled_without_env(tmp_path, monkeypatch):
    monkeypatch.delenv("WX_SATELLITE_V2_BENCH", raising=False)
    from satellite_v2 import _bench_timing

    timing = importlib.reload(_bench_timing)
    token = timing.begin_timing(tmp_path, {"sat_id": "goes19"})
    timing.add_timing_ms("warp_ms{Channel13}", 2.5)
    timing.finish_timing(token, cache_status="hit")

    assert token is None
    assert not (tmp_path / "satellite" / ".bench").exists()


def test_timing_collector_writes_stage_record(tmp_path, monkeypatch):
    monkeypatch.setenv("WX_SATELLITE_V2_BENCH", "1")
    monkeypatch.setenv("WX_SATELLITE_V2_BENCH_RUN_ID", "test-run")
    monkeypatch.setenv("WX_SATELLITE_V2_BENCH_SCENARIO", "hit")
    monkeypatch.setenv("WX_SATELLITE_V2_BENCH_ITERATION", "2")
    from satellite_v2 import _bench_timing

    timing = importlib.reload(_bench_timing)
    token = timing.begin_timing(tmp_path, {"sat_id": "goes19", "x": 1, "y": 2})
    timing.add_timing_ms("validate_ms", 1.25)
    timing.finish_timing(token, cache_status="hit")

    sink = tmp_path / "satellite" / ".bench" / "test-run.jsonl"
    record = json.loads(sink.read_text(encoding="utf-8"))
    assert record["validate_ms"] == 1.25
    assert record["cache_status"] == "hit"
    assert record["scenario"] == "hit"
    assert record["iteration"] == 2
    assert record["total_ms"] >= 0

    monkeypatch.delenv("WX_SATELLITE_V2_BENCH", raising=False)
    importlib.reload(_bench_timing)


def test_purge_removes_only_exact_target_frame(tmp_path):
    target = tile_path(tmp_path, "goes19", "CONUS", "Channel13", "frame-a", 7, 1, 2)
    sibling = tile_path(tmp_path, "goes19", "CONUS", "Channel13", "frame-b", 7, 1, 2)
    source = source_path(tmp_path, "goes19", "CONUS", "Channel13", "frame-a", "source.nc")
    for path in (target, sibling, source):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"data")

    bench._purge_target_frame(tmp_path, "goes19", "CONUS", "Channel13", "frame-a")

    assert not target.exists()
    assert sibling.exists()
    assert source.exists()


def test_purge_rejects_path_traversal_frame(tmp_path):
    with pytest.raises(ValueError, match="Unsafe"):
        bench._purge_target_frame(tmp_path, "goes19", "CONUS", "Channel13", "..")


def test_default_full_disk_center_is_platform_specific():
    assert bench._default_center("goes19", "FULLDISK") == (-75.2, 0.0)
    assert bench._default_center("himawari9", "FULLDISK") == (140.7, 0.0)
    assert bench._default_center("meteosat9", "FULLDISK") == (45.5, 0.0)
    assert bench._default_center("goes19", "MESO1") == (-95.0, 38.0)


def test_golden_capture_and_compare_are_byte_exact(tmp_path):
    context = {
        "sat_id": "goes19",
        "sector": "CONUS",
        "product": "Channel13",
        "frame_key": "frame-a",
        "z": 7,
    }
    coords = [(1, 2), (2, 2)]
    for index, (x, y) in enumerate(coords):
        path = tile_path(tmp_path, "goes19", "CONUS", "Channel13", "frame-a", 7, x, y)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"png-{index}".encode())

    golden_dir = tmp_path / "goldens"
    bench._write_golden("capture", golden_dir, tmp_path, context, coords)
    bench._write_golden("compare", golden_dir, tmp_path, context, coords)

    tile_path(tmp_path, "goes19", "CONUS", "Channel13", "frame-a", 7, 1, 2).write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="Golden comparison failed"):
        bench._write_golden("compare", golden_dir, tmp_path, context, coords)


def test_summary_reports_stage_percentiles():
    summary = bench._summary_markdown(
        "run",
        [
            {"total_ms": 10.0, "warp_ms{Channel13}": 4.0},
            {"total_ms": 20.0, "warp_ms{Channel13}": 8.0},
        ],
        {
            "sat_id": "goes19", "sector": "CONUS", "product": "Channel13",
            "frame_key": "frame", "scenario": "hit", "z": 7, "x": 1, "y": 2,
        },
    )

    assert "| `total_ms` | 15.000 | 19.500 | 2 |" in summary
    assert "| `warp_ms{Channel13}` | 6.000 | 7.800 | 2 |" in summary


def test_baseline_index_aggregates_pinned_runs(tmp_path):
    for index, scenario in enumerate(("cold-parse", "hit"), start=1):
        run_id = f"run-{index}"
        manifest = {
            "git_sha": "abc",
            "benchmark": {
                "run_id": run_id, "sat_id": "goes19", "sector": "CONUS",
                "product": "Channel13", "frame_key": "frame-a", "z": 7,
                "scenario": scenario,
            },
        }
        (tmp_path / f"{run_id}-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (tmp_path / f"{run_id}.jsonl").write_text('{"total_ms":10.0}\n', encoding="utf-8")

    bench._update_baseline_index(tmp_path)

    matrix = json.loads((tmp_path / "matrix-manifest.json").read_text(encoding="utf-8"))
    assert len(matrix["benchmark_runs"]) == 2
    assert matrix["pinned_frame_keys"]["goes19/CONUS/Channel13/z7"] == "frame-a"
    assert "| `goes19/CONUS/Channel13/z7` | `hit` |" in (
        tmp_path / "baseline-summary.md"
    ).read_text(encoding="utf-8")

    bench._update_baseline_index(tmp_path)
    assert len(json.loads((tmp_path / "matrix-manifest.json").read_text())["benchmark_runs"]) == 2
