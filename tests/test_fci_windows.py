from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import os
from types import SimpleNamespace

import netCDF4
import numpy as np
from PIL import Image
import pytest

from app_core import render_budget
from satellite_v2 import fci_windows as windows, renderer, service, tiler
from satellite_v2.fci_nc import load_fci_rasters
from test_satellite_meteosat import _write_fci_chunk


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    monkeypatch.setattr(windows, "_FRAMES", windows.OrderedDict())
    monkeypatch.setattr(windows, "_ARRAYS", windows.OrderedDict())
    monkeypatch.setattr(windows, "_ARRAY_BYTES", 0)
    monkeypatch.setattr(windows, "_OWNER", render_budget._ByteBudget(1))
    monkeypatch.setattr(windows.psutil, "virtual_memory", lambda: SimpleNamespace(total=16*1024**3, available=8*1024**3))


@pytest.fixture
def source(tmp_path):
    paths = [tmp_path / f"FCI-1C-RRAD-FDHSI-CHK-BODY-{index:04d}.nc" for index in (1, 2)]
    for index, path in enumerate(paths):
        _write_fci_chunk(path, 1 + index*2, np.full((2, 4), 80.0 + index*10),
                         np.arange(8, dtype=np.float32).reshape(2, 4) + 1 + index*8)
    return tuple(paths)


def test_native_window_matches_full_calibrated_grid_and_transform(source):
    frame = windows.Frame(source, windows._signature(source))
    grids = frame.grids_for(("vis_06", "ir_105"), complete=True)
    selected = {ch: (1, 1, 3, 3) for ch in grids}
    actual = windows._load(frame, tuple(grids), grids, selected, False, 1024)
    full = load_fci_rasters(source, tuple(grids), max_grid=4)
    for ch in grids:
        np.testing.assert_array_equal(actual[ch].cmi, full[ch].values[1:3, 1:3])
        assert actual[ch].src_transform == full[ch].src_transform * windows.Affine.translation(1, 1)
    assert windows._ARRAY_BYTES == 32


def test_lazy_renderer_does_not_decode_until_canvas_and_caches_physical_alias(source, monkeypatch):
    original = windows._calibrate_radiance
    calls = []

    def calibrate(*args):
        calls.append(args[2])
        return original(*args)

    monkeypatch.setattr(windows, "_calibrate_radiance", calibrate)
    handle = renderer.SatelliteTileRenderer.from_sources("Channel13", {"Channel13": source[0]}, sat_id="meteosat12")
    assert handle.source_rasters == {} and calls == []
    first = handle.render_zoom_canvas(8, 127, 127, 128, 128)
    count = len(calls)
    assert count == 2
    alias = renderer.SatelliteTileRenderer.from_sources("Channel14", {"Channel14": source[0]}, sat_id="meteosat12")
    alias.render_zoom_canvas(8, 127, 127, 128, 128).close()
    assert len(calls) == count
    assert len(windows._ARRAYS) == 1 and windows._ARRAY_BYTES == 64
    first.close()


def test_secondary_chunk_replacement_invalidates_native_cache(source):
    handle = renderer.SatelliteTileRenderer.from_sources("Channel02", {"Channel02": source[0]}, sat_id="meteosat12")
    handle.render_zoom_canvas(8, 127, 127, 128, 128).close()
    previous = next(iter(windows._ARRAYS.values())).cmi.copy()
    stat = source[1].stat()
    _write_fci_chunk(source[1], 3, np.full((2, 4), 90.0), np.full((2, 4), 100.0))
    os.utime(source[1], ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    handle.render_zoom_canvas(8, 127, 127, 128, 128).close()
    assert len(windows._FRAMES) == 1 and len(windows._ARRAYS) == 1
    assert not np.array_equal(previous, next(iter(windows._ARRAYS.values())).cmi)


def test_eviction_zero_cache_and_source_change_during_read(source, monkeypatch):
    frame = windows.Frame(source, windows._signature(source))
    grids = frame.grids_for(("vis_06",), complete=True)
    first = windows._load(frame, ("vis_06",), grids, {"vis_06": (0, 0, 2, 2)}, False, 16)
    original = first["vis_06"].cmi.copy()
    windows._load(frame, ("vis_06",), grids, {"vis_06": (2, 2, 4, 4)}, False, 16)
    assert windows._ARRAY_BYTES == 16 and len(windows._ARRAYS) == 1
    np.testing.assert_array_equal(first["vis_06"].cmi, original)
    windows._trim(0)
    windows._load(frame, ("vis_06",), grids, {"vis_06": (0, 0, 2, 2)}, False, 0)
    assert not windows._ARRAYS and windows._ARRAY_BYTES == 0
    monkeypatch.setattr(windows, "_signature", lambda paths: ("changed",))
    with pytest.raises(ValueError, match="changed during"):
        windows._load(frame, ("vis_06",), grids, {"vis_06": (0, 0, 2, 2)}, False, 16)
    assert not windows._ARRAYS


def test_gap_fails_window_index_and_full_fallback(source):
    _write_fci_chunk(source[1], 4, np.ones((2, 4))*80, np.ones((2, 4)))
    frame = windows.Frame(source, windows._signature(source))
    with pytest.raises(ValueError, match="gap or overlap"):
        frame.grids_for(("vis_06",), complete=True)
    with pytest.raises(ValueError, match="gap or overlap"):
        load_fci_rasters(source, ("vis_06",), max_grid=8)


def test_full_fallback_rejects_inconsistent_native_axes(source):
    with netCDF4.Dataset(source[1], "a") as ds:
        ds.groups["data"].groups["vis_06"].groups["measured"].variables["x"].scale_factor = -0.02
    with pytest.raises(ValueError, match="native axes"):
        load_fci_rasters(source, ("vis_06",), max_grid=4)


def test_outside_stored_grid_uses_native_fallback_and_budget_includes_transients(source, monkeypatch):
    handle = renderer.SatelliteTileRenderer.from_sources("Channel02", {"Channel02": source[0]}, sat_id="meteosat12")
    actual = renderer._load_fci_source_rasters
    caps = []
    weights = []

    def full(path, channels, max_grid):
        caps.append(max_grid)
        return actual(path, channels, max_grid)

    monkeypatch.setattr(renderer, "_load_fci_source_rasters", full)
    monkeypatch.setattr(windows, "satellite_render_slot", lambda weight, **kwargs: weights.append(weight) or nullcontext(True))
    with windows.render_context() as state:
        handle.render_zoom_canvas(8, 183, 127, 185, 129).close()
    assert caps == [4]  # Synthetic grid covers only the center; never invent coverage.
    assert state["estimated_memory_bytes"] == weights[0] > 128*1024**2


@pytest.mark.parametrize("sweep", ["x", "y"])
@pytest.mark.parametrize("origin", [0, 140.7])
@pytest.mark.parametrize("longitude,latitude", [((67.5, 90), (-22, 0)), ((-90, -67.5), (55, 67)),
                                              ((-180, 180), (-85, 85)), ((-23, 23), (75, 85))])
def test_limb_bounds_enclose_dense_visible_projection(longitude, latitude, sweep, origin):
    crs = windows.CRS.from_proj4(f"+proj=geos +h=35786400 +lon_0={origin} +sweep={sweep} +ellps=WGS84")
    longitude = tuple(value + origin for value in longitude)
    bounds = windows._limb_bounds(crs, longitude, latitude)
    x, y = windows.Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(
        *np.meshgrid(np.linspace(*longitude, 401), np.linspace(*latitude, 401)))
    valid = np.isfinite(x) & np.isfinite(y)
    assert valid.any() and bounds is not None
    assert x[valid].min() >= bounds[0][0] and x[valid].max() <= bounds[0][1]
    assert y[valid].min() >= bounds[1][0] and y[valid].max() <= bounds[1][1]


def test_off_disk_does_not_decode_and_still_honors_ownership(source, monkeypatch):
    monkeypatch.setattr(windows, "_load", lambda *args: pytest.fail("Off-disk work must not read radiance"))
    handle = renderer.SatelliteTileRenderer.from_sources("Channel02", {"Channel02": source[0]}, sat_id="meteosat12")
    for y in range(4, 9):
        with windows.render_context() as state:
            image = handle.render_tile(4, 12, y)
        assert image.getbbox() is None
        assert state["estimated_memory_bytes"] < 32*1024**2
        assert image.getpixel((0, 0)) == (255, 255, 255, 0)
        image.close()
    assert not windows._ARRAYS and windows._OWNER.snapshot()["active"] == 0
    with windows.render_context(lambda: False), pytest.raises(windows.FciRenderCancelled):
        handle.render_tile(4, 12, 8)


def test_world_canvas_with_invalid_corners_keeps_disk(source):
    frame = windows.Frame(source, windows._signature(source))
    grids, selected, full = frame.plan(("vis_06",), (0, 0, 0, 0, 0), 256)
    assert selected == {"vis_06": (0, 0, 4, 4)}
    assert grids["vis_06"].strips and not full


def test_low_memory_defers_before_geometry_or_decode(source, monkeypatch):
    monkeypatch.setattr(windows.psutil, "virtual_memory", lambda: SimpleNamespace(total=8*1024**3, available=128*1024**2))
    monkeypatch.setattr(windows.Frame, "plan", lambda *args: pytest.fail("Must defer before geometry allocation"))
    handle = renderer.SatelliteTileRenderer.from_sources("Channel02", {"Channel02": source[0]}, sat_id="meteosat12")
    with pytest.raises(windows.FciRenderCancelled, match="memory"):
        handle.render_zoom_canvas(8, 127, 127, 128, 128)
    assert windows._OWNER.snapshot()["active"] == 0


def test_waiting_request_can_cancel_without_loading(source, monkeypatch):
    acquired, weight = windows._OWNER.acquire(1)
    assert acquired
    monkeypatch.setattr(windows.Frame, "plan", lambda *args: pytest.fail("Cancelled work must not plan"))

    def wait():
        handle = renderer.SatelliteTileRenderer.from_sources("Channel02", {"Channel02": source[0]}, sat_id="meteosat12")
        with windows.render_context(lambda: False):
            with pytest.raises(windows.FciRenderCancelled):
                handle.render_zoom_canvas(8, 127, 127, 128, 128)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(wait).result(timeout=1)
    windows._OWNER.release(weight)
    assert windows._OWNER.snapshot()["queued"] == 0


def test_service_reserves_inside_m12_render_and_translates_deferral(source, tmp_path, monkeypatch):
    monkeypatch.setattr(tiler, "download_product_source_frames", lambda *args: {"Channel02": source[0]})
    path, stats = service._render_tile_with_budget(cache_root=tmp_path, sat_id="meteosat12", sector="FULLDISK",
                                                 channel_key="Channel02", frame={"frame_key": "test"}, z=8, x=127, y=127)
    assert "products-fci6" in path.parts and path.exists()
    assert stats["estimated_memory_bytes"] > 128*1024**2
    with Image.open(path) as image:
        assert image.size == (256, 256)
    monkeypatch.setattr(service, "render_frame_tile", lambda **kwargs: (_ for _ in ()).throw(windows.FciRenderCancelled("pressure")))
    with pytest.raises(service._TileRenderCancelled, match="pressure"):
        service._render_tile_with_budget(sat_id="meteosat12")


def test_m12_warming_splits_canvases_and_yields_without_child_pool(tmp_path, monkeypatch):
    coords = [(x, y) for x in range(7) for y in range(5)]
    seen = []
    monkeypatch.setattr(tiler, "planning_tile_coords", lambda *args, **kwargs: coords)
    monkeypatch.setattr(tiler, "download_product_source_frames", lambda *args: {"Channel02": "unused"})
    monkeypatch.setattr(tiler, "_render_warm_zoom_canvas_task", lambda task: seen.append(task) or {"rendered": len(task["coords"])})
    stats = tiler.warm_frame_tiles_from_canvas(tmp_path, "meteosat12", "FULLDISK", "Channel02",
                                              {"frame_key": "test"}, [4], render_workers=4, pool=object(),
                                              wait_until_ready=lambda: len(seen) < 2)
    assert len(seen) == 2 and stats["cancelled"] == 1
    for task in seen:
        assert max(x for x, _ in task["coords"]) - min(x for x, _ in task["coords"]) <= 2
        assert max(y for _, y in task["coords"]) - min(y for _, y in task["coords"]) <= 2


def test_cache_limit_adapts_without_reducing_source_dimensions(monkeypatch):
    monkeypatch.setattr(windows, "SATELLITE_V2_FCI_WINDOW_CACHE_MB", 256)
    gib = 1024**3
    assert windows.cache_limit_bytes(SimpleNamespace(total=8*gib, available=4*gib)) == 64*1024**2
    assert windows.cache_limit_bytes(SimpleNamespace(total=16*gib, available=8*gib)) == 128*1024**2
    assert windows.cache_limit_bytes(SimpleNamespace(total=128*gib, available=100*gib)) == 256*1024**2
    assert windows.cache_limit_bytes(SimpleNamespace(total=8*gib, available=32*1024**2)) == 1024**2
