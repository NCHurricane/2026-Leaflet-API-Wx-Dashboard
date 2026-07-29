import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from radar import radar_nodd_utils
from workers import radar_live_worker as worker


def test_same_sweep_products_reuse_one_quadmesh(tmp_path, monkeypatch):
    first_data = object()
    second_data = object()
    third_data = object()
    radar = SimpleNamespace(
        fields={
            "reflectivity": {"data": first_data},
            "differential_reflectivity": {"data": second_data},
            "velocity": {"data": third_data},
        }
    )
    mesh = SimpleNamespace(
        arrays=[],
        cmaps=[],
        clims=[],
        set_array=lambda value: mesh.arrays.append(value),
        set_cmap=lambda value: mesh.cmaps.append(value),
        set_clim=lambda vmin, vmax: mesh.clims.append((vmin, vmax)),
    )

    class FakeDisplay:
        plot_calls = 0

        def __init__(self, current_radar):
            self.radar = current_radar
            self.plots = []

        def plot_ppi_map(self, *_args, **_kwargs):
            type(self).plot_calls += 1
            self.plots.append(mesh)

        def _get_data(self, field_name, *_args):
            return self.radar.fields[field_name]["data"]

    axis = SimpleNamespace(
        patch=SimpleNamespace(set_alpha=lambda _value: None),
        set_axis_off=lambda: None,
        set_extent=lambda *_args, **_kwargs: None,
    )
    saves = []
    figure = SimpleNamespace(
        patch=SimpleNamespace(set_alpha=lambda _value: None),
        add_axes=lambda *_args, **_kwargs: axis,
        savefig=lambda path, **_kwargs: saves.append(path),
    )
    figure_calls = []
    closed = []

    monkeypatch.setitem(
        sys.modules,
        "pyart",
        SimpleNamespace(graph=SimpleNamespace(RadarMapDisplay=FakeDisplay)),
    )
    monkeypatch.setattr(
        worker,
        "ccrs",
        SimpleNamespace(epsg=lambda _code: object(), PlateCarree=lambda: object()),
    )
    monkeypatch.setattr(
        worker.plt,
        "figure",
        lambda **_kwargs: figure_calls.append(True) or figure,
    )
    monkeypatch.setattr(worker.plt, "close", lambda value: closed.append(value))
    monkeypatch.setattr(
        worker,
        "_figure_size_for_extent",
        lambda *_args, **_kwargs: (22.0, 22.0),
    )
    monkeypatch.setattr(
        worker,
        "_prepare_field_data",
        lambda value, *_args, **_kwargs: value,
    )
    monkeypatch.setattr(
        "config.radar_colortable_utils.get_radar_colortable",
        lambda *_args, **_kwargs: {"cmap": object()},
    )

    render_cache = {}
    first = worker._render_overlay_png_reusing_mesh(
        radar,
        "reflectivity",
        [-85.0, -80.0, 32.0, 37.0],
        tmp_path / "ref.png",
        "REF",
        {"figure_size_inches": 22, "palette": "BR", "vmin": -30, "vmax": 90},
        2,
        render_cache,
    )
    second = worker._render_overlay_png_reusing_mesh(
        radar,
        "differential_reflectivity",
        [-85.0, -80.0, 32.0, 37.0],
        tmp_path / "zdr.png",
        "ZDR",
        {"figure_size_inches": 22, "palette": "ZDR", "vmin": -8, "vmax": 8},
        2,
        render_cache,
    )
    third = worker._render_overlay_png_reusing_mesh(
        radar,
        "velocity",
        [-85.0, -80.0, 32.0, 37.0],
        tmp_path / "vel.png",
        "VEL",
        {"figure_size_inches": 22, "palette": "BV", "vmin": -120, "vmax": 120},
        3,
        render_cache,
    )

    assert first is True
    assert second is True
    assert third is True
    assert len(figure_calls) == 2
    assert FakeDisplay.plot_calls == 2
    assert mesh.arrays == [second_data]
    assert mesh.clims == [(-8.0, 8.0)]
    assert len(saves) == 3

    worker._close_reusable_overlay_cache(render_cache)
    assert render_cache == {}
    assert closed == [figure, figure]


def test_nodd_level2_uses_site_owned_volume_spool(tmp_path, monkeypatch):
    monkeypatch.setattr(radar_nodd_utils, "get_s3_client", lambda: object())
    monkeypatch.setattr(radar_nodd_utils, "list_nexrad_files", lambda **_kwargs: [])

    level2_dir, _, _ = radar_nodd_utils.download_radar_data(
        "Level 2", "KGSP", "REF", 1, str(tmp_path)
    )
    level3_dir, _, _ = radar_nodd_utils.download_radar_data(
        "Level 3", "KGSP", "N0B", 1, str(tmp_path)
    )

    assert Path(level2_dir) == (
        tmp_path
        / "radar_level2_downloads"
        / radar_nodd_utils.LEVEL2_SOURCE_SPOOL
        / "KGSP"
    )
    assert Path(level3_dir) == tmp_path / "radar_level3_downloads" / "N0B" / "KGSP"


def test_level2_source_lookup_keeps_legacy_product_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "_RADAR_ROOT", tmp_path)
    canonical, legacy = worker._radar_source_download_dirs(
        "KGSP", "Level 2", "VEL"
    )

    assert canonical == (
        tmp_path
        / "radar_level2_downloads"
        / radar_nodd_utils.LEVEL2_SOURCE_SPOOL
        / "KGSP"
    )
    assert legacy == tmp_path / "radar_level2_downloads" / "VEL" / "KGSP"


def test_level2_volume_worker_decodes_once_for_multiple_products(tmp_path):
    source = tmp_path / "KGSP20260725_120000_V06"
    source.write_bytes(b"volume")
    requests = [
        {
            "product_key": "L2_REF",
            "product_code": "REF",
            "product_cfg": {},
            "elevation": "0.5",
            "temp_render_path": str(tmp_path / "ref.png"),
        },
        {
            "product_key": "L2_VEL",
            "product_code": "VEL",
            "product_cfg": {},
            "elevation": "0.5",
            "temp_render_path": str(tmp_path / "vel.png"),
        },
    ]
    radar = object()

    with (
        patch.object(worker, "_read_radar", return_value=radar) as read,
        patch.object(
            worker,
            "_consume_decoded_l2_volume",
            return_value=[{"success": True}, {"success": True}],
        ) as consume,
    ):
        source_key, results = worker._render_l2_volume_products_worker(
            str(source), [-85.0, -80.0, 32.0, 37.0], requests
        )

    assert source_key == source.name
    assert len(results) == 2
    read.assert_called_once_with("Level 2", str(source))
    consume.assert_called_once_with(
        radar, source, [-85.0, -80.0, 32.0, 37.0], requests
    )


def test_reflectivity_artifact_reuses_single_frame_decode(tmp_path):
    source = tmp_path / "KGGW20260726_023250_V06"
    source.write_bytes(b"volume")
    radar = SimpleNamespace(fields={"reflectivity": {"data": object()}})

    with (
        patch.object(worker, "_read_radar", return_value=radar) as read,
        patch.object(
            worker,
            "_field_for_product",
            return_value="reflectivity",
        ),
        patch.object(worker, "_ensure_derived_field", return_value="reflectivity"),
        patch.object(
            worker,
            "_frame_dt_from_radar",
            return_value=datetime(2026, 7, 26, 2, 32, 50, tzinfo=timezone.utc),
        ),
        patch.object(worker, "_select_sweep", return_value=(0, [0.5], 0.5)),
        patch.object(worker, "_render_overlay_png", return_value=True),
        patch.object(worker, "_publish_webgl_artifact") as publish,
    ):
        result = worker._render_single_frame_worker(
            str(source),
            "Level 2",
            "REF",
            [-114.1, -99.1, 43.2, 53.2],
            str(tmp_path / "frame.png"),
            {"palette": "BR"},
            "0.5",
            "KGGW",
        )

    assert result[0] is True
    read.assert_called_once_with("Level 2", str(source))
    publish.assert_called_once()
    assert publish.call_args.args[4] is radar


def test_decoded_level2_consumers_isolate_product_failure(tmp_path):
    radar = SimpleNamespace(fields={"reflectivity": {}, "velocity": {}})
    source = tmp_path / "KGSP20260725_120000_V06"
    requests = [
        {
            "product_key": "L2_REF",
            "product_code": "REF",
            "product_cfg": {},
            "elevation": "0.5",
            "temp_render_path": str(tmp_path / "ref.png"),
        },
        {
            "product_key": "L2_VEL",
            "product_code": "VEL",
            "product_cfg": {},
            "elevation": "0.5",
            "temp_render_path": str(tmp_path / "vel.png"),
        },
    ]

    def render(**kwargs):
        if kwargs["product_code"] == "VEL":
            raise RuntimeError("velocity failed")
        return True

    with (
        patch.object(
            worker,
            "_frame_dt_from_radar",
            return_value=datetime(2026, 7, 25, 12, tzinfo=timezone.utc),
        ),
        patch.object(
            worker,
            "_field_for_product",
            side_effect=lambda _level, code, _fields, _cfg: {
                "REF": "reflectivity",
                "VEL": "velocity",
            }[code],
        ),
        patch.object(worker, "_ensure_derived_field", side_effect=lambda _r, f, _c: f),
        patch.object(worker, "_select_sweep", return_value=(0, [0.5], 0.5)),
        patch.object(worker, "_render_overlay_png", side_effect=render),
    ):
        results = worker._consume_decoded_l2_volume(
            radar, source, [-85.0, -80.0, 32.0, 37.0], requests
        )

    assert results[0]["success"] is True
    assert results[1]["success"] is False
    assert "velocity failed" in results[1]["error"]


def test_decoded_level2_consumers_restore_source_field_between_products(tmp_path):
    original_velocity = object()
    radar = SimpleNamespace(fields={"velocity": {"data": original_velocity}})
    source = tmp_path / "KGSP20260725_120000_V06"
    requests = [
        {
            "product_key": "L2_VEL",
            "product_code": "VEL",
            "product_cfg": {},
            "elevation": "0.5",
            "temp_render_path": str(tmp_path / "vel.png"),
        },
        {
            "product_key": "L2_SRV",
            "product_code": "SRV",
            "product_cfg": {"derived_field": "storm_relative_velocity"},
            "elevation": "0.5",
            "temp_render_path": str(tmp_path / "srv.png"),
        },
    ]

    def ensure_derived(current_radar, field_name, product_cfg):
        if product_cfg.get("derived_field"):
            assert current_radar.fields["velocity"]["data"] is original_velocity
            current_radar.fields["storm_relative_velocity"] = {
                "data": object()
            }
            return "storm_relative_velocity"
        return field_name

    def render(**kwargs):
        kwargs["radar"].fields[kwargs["field_name"]]["data"] = object()
        return True

    with (
        patch.object(
            worker,
            "_frame_dt_from_radar",
            return_value=datetime(2026, 7, 25, 12, tzinfo=timezone.utc),
        ),
        patch.object(worker, "_field_for_product", return_value="velocity"),
        patch.object(worker, "_ensure_derived_field", side_effect=ensure_derived),
        patch.object(worker, "_select_sweep", return_value=(0, [0.5], 0.5)),
        patch.object(worker, "_render_overlay_png", side_effect=render),
    ):
        results = worker._consume_decoded_l2_volume(
            radar, source, [-85.0, -80.0, 32.0, 37.0], requests
        )

    assert [result["success"] for result in results] == [True, True]
    assert radar.fields["velocity"]["data"] is original_velocity


def test_scheduled_run_batches_flat_level2_products_once():
    products = {
        "L2_REF": {"level": "Level 2", "product": "REF"},
        "L2_VEL": {"level": "Level 2", "product": "VEL"},
        "L3_N0B": {"level": "Level 3", "product": "N0B"},
    }
    nodd = SimpleNamespace(__name__="radar.radar_nodd_utils")
    render_pool = object()

    with (
        patch.object(worker, "LIVE_RADAR_SITES", ("KGSP",)),
        patch.object(worker, "LIVE_RADAR_PRODUCTS", products),
        patch.object(worker, "is_cache_fresh", return_value=False),
        patch.object(worker, "_resolve_radar_data_utils", return_value=nodd),
        patch.object(
            worker, "_render_site_l2_products", return_value=(2, 0)
        ) as render_l2,
        patch.object(worker, "_render_site_product", return_value=1) as render_one,
        patch.object(worker, "mark_run_complete"),
    ):
        worker._run_radar_live_worker_unbounded(
            force=True,
            render_pool=render_pool,
        )

    render_l2.assert_called_once()
    assert [item[0] for item in render_l2.call_args.args[2]] == [
        "L2_REF",
        "L2_VEL",
    ]
    assert render_l2.call_args.kwargs["render_pool"] is render_pool
    render_one.assert_called_once()
    assert render_one.call_args.args[3] == "L3_N0B"


def test_level2_product_batch_is_bounded():
    products = [
        (f"L2_TEST_{index}", {"level": "Level 2", "product": "REF"})
        for index in range(worker._MAX_L2_VOLUME_CONSUMERS + 1)
    ]

    with pytest.raises(ValueError, match="product batch exceeds"):
        worker._render_site_l2_products(
            SimpleNamespace(__name__="radar.radar_nodd_utils"),
            "KGSP",
            products,
            elevation="0.5",
        )
