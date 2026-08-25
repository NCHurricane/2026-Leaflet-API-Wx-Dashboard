import importlib
import json
import os
from collections import OrderedDict
from concurrent.futures import Future
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from satellite_v2 import bench
from satellite_v2.cache import source_path, tile_path
from satellite_v2 import renderer, service, tiler
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


def test_source_grid_memory_estimate_uses_zoom_and_product_channel_count():
    z4_single = renderer.estimate_source_grid_bytes(
        "meteosat12", "Channel13", destination_zoom=4
    )
    z5_single = renderer.estimate_source_grid_bytes(
        "meteosat12", "Channel13", destination_zoom=5
    )
    z7_single = renderer.estimate_source_grid_bytes(
        "meteosat12", "Channel13", destination_zoom=7
    )
    z5_three_channel = renderer.estimate_source_grid_bytes(
        "meteosat12", "NighttimeMicrophysics", destination_zoom=5
    )

    assert z4_single == 2048 * 2048 * 4
    assert z5_single == 4096 * 4096 * 4
    assert z7_single == 5568 * 5568 * 4
    assert z5_three_channel == z5_single * 3


def test_goes_memory_estimate_keeps_conservative_platform_cap():
    assert renderer.estimate_source_grid_bytes(
        "goes19", "Channel13", destination_zoom=4
    ) == 10848 * 10848 * 4


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


def _write_tile_png(path, color):
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (4, 4), color).save(path)


def test_golden_tolerance_mode_measures_delta_instead_of_hash(tmp_path):
    context = {
        "sat_id": "meteosat12",
        "sector": "FULLDISK",
        "product": "Channel13",
        "frame_key": "frame-a",
        "z": 5,
    }
    coords = [(1, 2)]
    target = tile_path(tmp_path, "meteosat12", "FULLDISK", "Channel13", "frame-a", 5, 1, 2)
    _write_tile_png(target, (10, 20, 30, 255))

    golden_dir = tmp_path / "goldens"
    bench._write_golden("capture", golden_dir, tmp_path, context, coords)

    _write_tile_png(target, (12, 20, 30, 255))
    rows = bench._write_golden(
        "compare", golden_dir, tmp_path, context, coords, tolerance=2
    )

    assert rows[0]["sha_equal"] is False
    assert rows[0]["max_delta"] == 2
    assert rows[0]["diff_fraction"] == 1.0

    # The same shifted tile still fails the strict gate the other platforms keep.
    with pytest.raises(RuntimeError, match="Golden comparison failed"):
        bench._write_golden("compare", golden_dir, tmp_path, context, coords)

    _write_tile_png(target, (40, 20, 30, 255))
    with pytest.raises(RuntimeError, match="Golden tolerance comparison failed"):
        bench._write_golden("compare", golden_dir, tmp_path, context, coords, tolerance=2)


def test_golden_version_override_targets_prebump_capture(tmp_path):
    context = {
        "sat_id": "meteosat12",
        "sector": "FULLDISK",
        "product": "Channel13",
        "frame_key": "frame-v",
        "z": 5,
    }
    coords = [(1, 2)]
    target = tile_path(tmp_path, "meteosat12", "FULLDISK", "Channel13", "frame-v", 5, 1, 2)
    _write_tile_png(target, (10, 20, 30, 255))
    golden_dir = tmp_path / "goldens"
    bench._write_golden(
        "capture", golden_dir, tmp_path, context, coords, version_override="products-fci-prebump"
    )

    assert (golden_dir / "products-fci-prebump").is_dir()
    # Without the override the compare looks under the live version and finds nothing.
    with pytest.raises(FileNotFoundError):
        bench._write_golden("compare", golden_dir, tmp_path, context, coords)
    bench._write_golden(
        "compare", golden_dir, tmp_path, context, coords, version_override="products-fci-prebump"
    )


def test_golden_tolerance_mode_rejects_geometry_change(tmp_path):
    from PIL import Image

    context = {
        "sat_id": "meteosat12",
        "sector": "FULLDISK",
        "product": "Channel13",
        "frame_key": "frame-b",
        "z": 5,
    }
    coords = [(1, 2)]
    target = tile_path(tmp_path, "meteosat12", "FULLDISK", "Channel13", "frame-b", 5, 1, 2)
    _write_tile_png(target, (10, 20, 30, 255))
    golden_dir = tmp_path / "goldens"
    bench._write_golden("capture", golden_dir, tmp_path, context, coords)

    Image.new("RGBA", (8, 8), (10, 20, 30, 255)).save(target)
    with pytest.raises(RuntimeError, match="geometry changed"):
        bench._write_golden("compare", golden_dir, tmp_path, context, coords, tolerance=2)


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


def test_catalog_frame_lookup_is_memoized_until_the_catalog_changes(tmp_path, monkeypatch):
    from satellite_v2.cache import catalog_path

    path = catalog_path(tmp_path, "meteosat12", "FULLDISK", "Channel13")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"frames": [{"frame_key": "frame-a", "source_key": "one"}]}),
        encoding="utf-8",
    )
    reads = []
    real_read_json = service.read_json

    def counting_read_json(target):
        reads.append(target)
        return real_read_json(target)

    monkeypatch.setattr(service, "read_json", counting_read_json)
    monkeypatch.setattr(service, "_CATALOG_FRAME_INDEX", OrderedDict())

    first = service._catalog_frame_for_tile(tmp_path, "meteosat12", "FULLDISK", "Channel13", "frame-a")
    second = service._catalog_frame_for_tile(tmp_path, "meteosat12", "FULLDISK", "Channel13", "frame-a")

    assert first == {"frame_key": "frame-a", "source_key": "one"}
    assert second == first
    assert first is not second  # copied, so a caller cannot corrupt the index
    assert len(reads) == 1

    path.write_text(
        json.dumps({"frames": [{"frame_key": "frame-a", "source_key": "two"}]}),
        encoding="utf-8",
    )
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    assert service._catalog_frame_for_tile(
        tmp_path, "meteosat12", "FULLDISK", "Channel13", "frame-a"
    )["source_key"] == "two"
    assert len(reads) == 2


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
        "render_supertile": True,
    }

    first, first_submitted = service._submit_tile_render(target, **render_kwargs)
    second, second_submitted = service._submit_tile_render(target, **render_kwargs)

    assert first is second
    assert first_submitted is True
    assert second_submitted is False
    assert len(submitted) == 1
    assert submitted[0][1]["render_supertile"] is True

    first.set_result((target, {"cache_status": "miss"}))
    assert service._IN_FLIGHT_TILE_RENDERS == {}


def test_resolve_tile_can_skip_neighbor_fanout_for_explicit_prefetch(
    tmp_path, monkeypatch
):
    submitted = []

    def fake_submit(target, **kwargs):
        submitted.append((target, kwargs))
        future = Future()
        future.set_result(
            (
                target,
                {
                    "cache_status": "miss",
                    "download_elapsed_ms": 120,
                    "decode_elapsed_ms": 45,
                    "render_elapsed_ms": 8,
                },
            )
        )
        return future, True

    monkeypatch.setattr(service, "_submit_tile_render", fake_submit)
    monkeypatch.setattr(
        service,
        "_catalog_frame_for_tile",
        lambda *_args: {"frame_key": "frame-a"},
    )
    _, stats = service.resolve_tile(
        tmp_path,
        "goes19",
        "CONUS",
        "Channel13",
        "frame-a",
        7,
        1,
        2,
        render_neighbors=False,
    )

    assert len(submitted) == 1
    assert submitted[0][1]["render_supertile"] is False
    assert stats["supertile_radius"] == 0
    assert stats["supertile_submitted"] == 0
    assert stats["download_elapsed_ms"] == 120
    assert stats["decode_elapsed_ms"] == 45
    assert stats["render_elapsed_ms"] == 8


def test_live_render_uses_one_canvas_for_the_whole_supertile(tmp_path, monkeypatch):
    calls = []

    class _FakeRenderer:
        def render_zoom_canvas(
            self, z, x_min, y_min, x_max, y_max, tile_size=256
        ):
            calls.append((z, x_min, y_min, x_max, y_max, tile_size))
            return Image.new(
                "RGBA",
                ((x_max - x_min + 1) * tile_size, (y_max - y_min + 1) * tile_size),
                (10, 20, 30, 255),
            )

    class _FakeRendererFactory:
        @staticmethod
        def from_sources(_channel, _sources, *, sat_id, destination_zoom):
            assert sat_id == "goes19"
            assert destination_zoom == 3
            return _FakeRenderer()

    monkeypatch.setattr(tiler, "SatelliteTileRenderer", _FakeRendererFactory)
    monkeypatch.setattr(tiler, "SATELLITE_V2_LIVE_SUPERTILE_RADIUS", 1)
    monkeypatch.setattr(
        tiler,
        "download_product_source_frames",
        lambda *_args: {"Channel13": tmp_path / "source.nc"},
    )

    target, stats = tiler.render_frame_tile(
        tmp_path,
        "goes19",
        "CONUS",
        "Channel13",
        {"frame_key": "frame-a"},
        3,
        4,
        4,
    )

    assert calls == [(3, 3, 3, 5, 5, 256)]
    assert target.is_file()
    assert stats["rendered"] == 1
    assert stats["supertile_rendered"] == 8
    assert sum(1 for path in tmp_path.rglob("*.png") if path.is_file()) == 9


@pytest.mark.parametrize(
    ("zoom", "expected"),
    [(3, 2048), (4, 2048), (5, 4096), (6, 4096), (7, 10848)],
)
def test_source_grid_cap_has_three_zoom_bands(tmp_path, zoom, expected):
    source = tmp_path / "OR_ABI-L2-CMIPF-M6C13_G19_s20262360000000.nc"

    assert renderer._source_raster_grid_cap(source, "Channel13", zoom) == expected


def test_source_cache_keeps_zoom_decimation_levels_separate(tmp_path, monkeypatch):
    source = tmp_path / "OR_ABI-L2-CMIPF-M6C13_G19_s20262360000000.nc"
    source.write_bytes(b"source")
    _reset_source_raster_cache(monkeypatch, 1024)
    calls = []

    def fake_load(path, channel, max_grid=None):
        calls.append((path, channel, max_grid))
        return renderer.SourceRaster(
            cmi=np.zeros((2, 2), dtype=np.float32),
            src_transform=object(),
            src_crs=object(),
        )

    monkeypatch.setattr(renderer, "_load_source_raster", fake_load)

    low, _ = renderer._load_source_raster_cached(source, "Channel13", 4)
    middle, _ = renderer._load_source_raster_cached(source, "Channel13", 6)
    low_again, parsed = renderer._load_source_raster_cached(source, "Channel13", 3)

    assert low is low_again
    assert low is not middle
    assert parsed is False
    assert calls == [
        (source, "Channel13", 2048),
        (source, "Channel13", 4096),
    ]


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
    monkeypatch.setattr(renderer, "_SOURCE_RASTER_CACHE_MAX_BYTES", 0)
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


def _reset_source_raster_cache(monkeypatch, max_bytes):
    monkeypatch.setattr(renderer, "_SOURCE_RASTER_CACHE", OrderedDict())
    monkeypatch.setattr(renderer, "_SOURCE_RASTER_CACHE_BYTES", 0)
    monkeypatch.setattr(renderer, "_SOURCE_RASTER_KEY_LOCKS", {})
    monkeypatch.setattr(renderer, "_SOURCE_RASTER_CACHE_MAX_BYTES", max_bytes)
    monkeypatch.setattr(renderer, "_RENDERER_CACHE", OrderedDict())
    monkeypatch.setattr(renderer, "_RENDERER_KEY_LOCKS", {})


def test_source_raster_cache_reuses_same_file_channel(tmp_path, monkeypatch):
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    _reset_source_raster_cache(monkeypatch, 1024)
    calls = []

    def fake_load(path, channel):
        calls.append((path, channel))
        return renderer.SourceRaster(
            cmi=np.zeros((2, 2), dtype=np.float32),
            src_transform=object(),
            src_crs=object(),
        )

    monkeypatch.setattr(renderer, "_load_source_raster", fake_load)

    first, first_parsed = renderer._load_source_raster_cached(source, "Channel13")
    second, second_parsed = renderer._load_source_raster_cached(source, "Channel13")

    assert first is second
    assert first_parsed is True
    assert second_parsed is False
    assert calls == [(source, "Channel13")]
    assert renderer._SOURCE_RASTER_CACHE_BYTES == first.cmi.nbytes


def test_renderers_for_different_products_share_cached_source(tmp_path, monkeypatch):
    source = tmp_path / "source.nc"
    source.write_bytes(b"source")
    _reset_source_raster_cache(monkeypatch, 1024)
    monkeypatch.setattr(renderer, "_RENDERER_CACHE_MAX", 8)
    calls = []

    def fake_load(path, channel):
        calls.append((path, channel))
        return renderer.SourceRaster(
            cmi=np.zeros((2, 2), dtype=np.float32),
            src_transform=object(),
            src_crs=object(),
        )

    monkeypatch.setattr(renderer, "_load_source_raster", fake_load)
    monkeypatch.setattr(
        renderer,
        "source_channels_for_product",
        lambda _product: ("Channel13",),
    )

    first = renderer.SatelliteTileRenderer.from_sources(
        "Channel13", {"Channel13": source}
    )
    second = renderer.SatelliteTileRenderer.from_sources(
        "NighttimeMicrophysics", {"Channel13": source}
    )

    assert first is not second
    assert first.source_rasters["Channel13"] is second.source_rasters["Channel13"]
    assert calls == [(source, "Channel13")]
    assert len(renderer._RENDERER_CACHE) == 2


def test_oversized_source_does_not_leave_lock_or_cached_renderer(tmp_path, monkeypatch):
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    _reset_source_raster_cache(monkeypatch, 8)
    monkeypatch.setattr(renderer, "_RENDERER_CACHE_MAX", 8)
    monkeypatch.setattr(
        renderer,
        "_load_source_raster",
        lambda *_args: renderer.SourceRaster(
            cmi=np.zeros((2, 2), dtype=np.float32),
            src_transform=object(),
            src_crs=object(),
        ),
    )
    monkeypatch.setattr(
        renderer,
        "source_channels_for_product",
        lambda _product: ("Channel13",),
    )

    result = renderer.SatelliteTileRenderer.from_sources(
        "Channel13", {"Channel13": source}
    )

    assert result.source_rasters["Channel13"].cmi.nbytes == 16
    assert renderer._SOURCE_RASTER_CACHE == {}
    assert renderer._SOURCE_RASTER_KEY_LOCKS == {}
    assert renderer._RENDERER_CACHE == {}


def test_source_raster_eviction_removes_dependent_renderer(tmp_path, monkeypatch):
    first_path = tmp_path / "first.bin"
    second_path = tmp_path / "second.bin"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    _reset_source_raster_cache(monkeypatch, 16)

    monkeypatch.setattr(
        renderer,
        "_load_source_raster",
        lambda *_args: renderer.SourceRaster(
            cmi=np.zeros((2, 2), dtype=np.float32),
            src_transform=object(),
            src_crs=object(),
        ),
    )

    first, _ = renderer._load_source_raster_cached(first_path, "Channel13")
    renderer._RENDERER_CACHE[("first",)] = renderer.SatelliteTileRenderer(
        product_key="Channel13",
        source_rasters={"Channel13": first},
    )
    second, _ = renderer._load_source_raster_cached(second_path, "Channel13")

    assert first is not second
    assert list(renderer._SOURCE_RASTER_CACHE.values()) == [second]
    assert renderer._SOURCE_RASTER_CACHE_BYTES == 16
    assert renderer._RENDERER_CACHE == {}
