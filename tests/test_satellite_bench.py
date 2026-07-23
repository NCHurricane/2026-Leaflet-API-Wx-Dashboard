import importlib
import json
import os
from collections import OrderedDict
from concurrent.futures import Future
from pathlib import Path

import pytest

from satellite_v2 import bench
from satellite_v2.cache import source_path, tile_path
from satellite_v2 import renderer, service
from satellite_v2.composites import COMPOSITES_REQUIRING_LONLAT


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


class _FakeDataset:
    def __init__(self, name):
        self.name = name
        self.close_count = 0

    def close(self):
        self.close_count += 1


def test_netcdf_cache_is_lru_and_closes_evicted_dataset(tmp_path, monkeypatch):
    paths = [tmp_path / f"source-{index}.nc" for index in range(3)]
    for path in paths:
        path.write_bytes(b"netcdf")
    opened = []

    def fake_open(path, **_kwargs):
        dataset = _FakeDataset(Path(path).name)
        opened.append(dataset)
        return dataset

    monkeypatch.setattr(renderer, "_NETCDF_CACHE", OrderedDict())
    monkeypatch.setattr(renderer, "_NETCDF_CACHE_MAX", 2)
    monkeypatch.setattr(renderer.xr, "open_dataset", fake_open)

    first = renderer._load_netcdf_dataset(paths[0])
    second = renderer._load_netcdf_dataset(paths[1])
    assert renderer._load_netcdf_dataset(paths[0]) is first
    renderer._load_netcdf_dataset(paths[2])

    assert list(renderer._NETCDF_CACHE) == [str(paths[0].resolve()), str(paths[2].resolve())]
    assert first.close_count == 0
    assert second.close_count == 1


def test_netcdf_cache_closes_same_path_dataset_on_mtime_replace(tmp_path, monkeypatch):
    path = tmp_path / "source.nc"
    path.write_bytes(b"netcdf")
    opened = []

    def fake_open(source, **_kwargs):
        dataset = _FakeDataset(Path(source).name)
        opened.append(dataset)
        return dataset

    monkeypatch.setattr(renderer, "_NETCDF_CACHE", OrderedDict())
    monkeypatch.setattr(renderer, "_NETCDF_CACHE_MAX", 2)
    monkeypatch.setattr(renderer.xr, "open_dataset", fake_open)

    original = renderer._load_netcdf_dataset(path)
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    replacement = renderer._load_netcdf_dataset(path)

    assert replacement is not original
    assert original.close_count == 1
    assert replacement.close_count == 0


def test_resolve_tile_png_signature_skips_deep_validation(tmp_path, monkeypatch):
    path = tile_path(tmp_path, "goes19", "CONUS", "Channel13", "frame-a", 7, 1, 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(service._PNG_SIGNATURE + b"cached-tile")

    def fail_deep_validation(_path):
        raise AssertionError("deep validation should not run for a PNG cache hit")

    monkeypatch.setattr(service, "is_valid_tile_file", fail_deep_validation)
    resolved, stats = service.resolve_tile(
        tmp_path, "goes19", "CONUS", "Channel13", "frame-a", 7, 1, 2,
        allow_render=False,
    )

    assert resolved == path
    assert stats["cache_status"] == "hit"


def test_resolve_tile_bad_signature_falls_back_to_deep_validation(tmp_path, monkeypatch):
    path = tile_path(tmp_path, "goes19", "CONUS", "Channel13", "frame-a", 7, 1, 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not-a-png")
    validated = []

    def accept_deep_validation(candidate):
        validated.append(candidate)
        return True

    monkeypatch.setattr(service, "is_valid_tile_file", accept_deep_validation)
    _, stats = service.resolve_tile(
        tmp_path, "goes19", "CONUS", "Channel13", "frame-a", 7, 1, 2,
        allow_render=False,
    )

    assert validated == [path]
    assert stats["cache_status"] == "hit"


def test_resolve_tile_invalid_file_remains_a_cache_miss(tmp_path, monkeypatch):
    path = tile_path(tmp_path, "goes19", "CONUS", "Channel13", "frame-a", 7, 1, 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"invalid")
    monkeypatch.setattr(service, "is_valid_tile_file", lambda _path: False)

    _, stats = service.resolve_tile(
        tmp_path, "goes19", "CONUS", "Channel13", "frame-a", 7, 1, 2,
        allow_render=False,
    )

    assert stats["cache_status"] == "empty"
    assert stats["miss_reason"] == "invalid"


def test_only_geometry_consuming_composites_allocate_lonlat_mesh():
    assert "GeoColor" in COMPOSITES_REQUIRING_LONLAT
    assert "GeoColorBlkMar" in COMPOSITES_REQUIRING_LONLAT
    assert "TrueColor" not in COMPOSITES_REQUIRING_LONLAT
    assert "NighttimeMicrophysics" not in COMPOSITES_REQUIRING_LONLAT


def test_submit_tile_render_deduplicates_in_flight_target(tmp_path, monkeypatch):
    submitted = []

    class _FakePool:
        def submit(self, function, **kwargs):
            future = Future()
            submitted.append((function, kwargs, future))
            return future

    monkeypatch.setattr(service, "_ON_DEMAND_TILE_RENDER_POOL", _FakePool())
    monkeypatch.setattr(service, "_IN_FLIGHT_TILE_RENDERS", {})
    target = tmp_path / "tile.png"
    render_kwargs = {
        "cache_root": tmp_path,
        "sat_id": "goes19",
        "sector": "CONUS",
        "channel_key": "Channel13",
        "frame": {"frame_key": "frame-a"},
        "z": 7,
        "x": 1,
        "y": 2,
    }

    first, first_submitted = service._submit_tile_render(target, **render_kwargs)
    second, second_submitted = service._submit_tile_render(target, **render_kwargs)

    assert first is second
    assert first_submitted is True
    assert second_submitted is False
    assert len(submitted) == 1
    assert submitted[0][1]["render_supertile"] is False

    first.set_result((target, {"cache_status": "miss"}))
    assert service._IN_FLIGHT_TILE_RENDERS == {}


def test_renderer_batches_fci_channels_from_shared_chunk_directory(tmp_path, monkeypatch):
    source_files = {
        channel: tmp_path / f"FCI-1C-RRAD-FDHSI-CHK-BODY-{channel}.nc"
        for channel in ("Channel07", "Channel13", "Channel15")
    }
    loaded = {channel: object() for channel in source_files}
    calls = []

    def fake_batch(primary, channels):
        calls.append((primary, tuple(channels)))
        return {channel: loaded[channel] for channel in channels}

    monkeypatch.setattr(renderer, "_load_fci_source_rasters", fake_batch)
    monkeypatch.setattr(
        renderer,
        "_load_source_raster",
        lambda *_args, **_kwargs: pytest.fail("FCI channels should use one batch load"),
    )

    result = renderer._load_renderer_uncached(
        renderer.SatelliteTileRenderer,
        "NighttimeMicrophysics",
        source_files,
        tuple(source_files),
        "FCI",
    )

    assert calls == [(source_files["Channel07"], tuple(source_files))]
    assert result.source_rasters == loaded
