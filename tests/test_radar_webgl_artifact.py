import json
import struct
from unittest.mock import patch

import numpy as np
import pytest
from fastapi import HTTPException

from config import radar_config
from radar import webgl_artifact
from services import radar_service
from workers import radar_live_worker


class FakeRadar:
    def __init__(self):
        values = np.ma.array(
            [[5.0, 5.5, 10.0, 20.0], [30.0, 40.0, 50.0, 60.0]],
            mask=[[False, True, False, False], [False, False, False, False]],
        )
        velocity = np.ma.array(
            [[-150.0, -64.0, 0.0, 64.0], [-100.0, -20.0, 30.0, 80.0]],
            mask=[[False, True, False, False], [False, False, False, False]],
        )
        storm_relative_velocity = np.ma.array(
            [[-100.0, -50.0, 0.0, 120.0], [-80.0, -10.0, 40.0, 160.0]],
            mask=[[False, True, False, False], [False, False, False, False]],
        )
        self.fields = {
            "reflectivity": {"data": values},
            "velocity": {"data": velocity},
            "storm_relative_velocity": {"data": storm_relative_velocity},
        }
        self.azimuth = {"data": np.array([180.0, 0.0])}
        self.range = {"data": np.array([2125.0, 2375.0, 2625.0, 2875.0])}
        self.latitude = {"data": np.array([48.2])}
        self.longitude = {"data": np.array([-106.6])}

    @staticmethod
    def get_slice(_sweep):
        return slice(0, 2)


def _enable(monkeypatch):
    monkeypatch.setattr(radar_config, "LIVE_RADAR_WEBGL_ENABLED", True)


def _enable_velocity(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(radar_config, "LIVE_RADAR_WEBGL_VELOCITY_ENABLED", True)


def test_feature_config_bounds_animation_window(monkeypatch):
    monkeypatch.setattr(radar_config, "LIVE_RADAR_WEBGL_ENABLED", True)
    monkeypatch.setattr(radar_config, "LIVE_RADAR_WEBGL_ANIMATION_ENABLED", True)
    monkeypatch.setattr(radar_config, "LIVE_RADAR_WEBGL_VELOCITY_ENABLED", False)

    config = webgl_artifact.feature_config()

    assert config["animation_enabled"] is True
    assert config["products"] == ["L2_REF"]
    assert config["animation_products"] == ["L2_REF"]
    assert config["texture_budget"] == 4
    assert config["min_forward_textures"] == 2
    assert config["max_concurrent_loads"] == 2

    monkeypatch.setattr(radar_config, "LIVE_RADAR_WEBGL_ENABLED", False)
    assert webgl_artifact.feature_config()["animation_enabled"] is False
    assert webgl_artifact.feature_config()["products"] == []


def test_velocity_family_has_separate_product_and_animation_gates(monkeypatch):
    _enable_velocity(monkeypatch)
    monkeypatch.setattr(
        radar_config, "LIVE_RADAR_WEBGL_VELOCITY_ANIMATION_ENABLED", False
    )

    config = webgl_artifact.feature_config()
    assert set(config["products"]) == {"L2_REF", "L2_VEL", "L2_SRV"}
    assert "L2_VEL" not in config["animation_products"]
    assert "L2_SRV" not in config["animation_products"]

    monkeypatch.setattr(
        radar_config, "LIVE_RADAR_WEBGL_VELOCITY_ANIMATION_ENABLED", True
    )
    assert {"L2_VEL", "L2_SRV"}.issubset(
        webgl_artifact.feature_config()["animation_products"]
    )


def test_polar_artifact_is_versioned_compact_and_round_trips(tmp_path, monkeypatch):
    _enable(monkeypatch)
    path = webgl_artifact.write_artifact(
        tmp_path,
        "KGGW",
        "2026_07_26_02_32_50",
        0.5,
        FakeRadar(),
        "reflectivity",
        0,
        radar_config.LIVE_RADAR_PRODUCTS["L2_REF"],
    )

    assert path is not None
    assert path.parent.name == "0p5"
    assert path.parents[4].name == "v2"
    assert path.stat().st_size < 2_000_000
    header, texture_bytes = webgl_artifact.read_artifact(path)
    assert header["product"] == "L2_REF"
    assert header["ray_count"] == 2
    assert header["gate_count"] == 4
    assert header["max_quantization_error"] == 0.0

    texture = np.frombuffer(texture_bytes, dtype=np.uint8).reshape(
        header["texture_height"], header["texture_width"]
    )
    # Rays are sorted by native azimuth; the 0-degree row comes first.
    assert int(texture[0, 0]) + int(texture[0, 1]) * 256 == 0
    assert texture[0, 2:6].tolist() == [124, 144, 164, 184]
    assert texture[1, 2:6].tolist() == [74, 255, 84, 104]
    assert texture[header["ray_count"], 255 * 4 : 256 * 4].tolist() == [0, 0, 0, 0]

    metadata = webgl_artifact.artifact_metadata(
        tmp_path, "KGGW", "L2_REF", 0.5, "2026_07_26_02_32_50"
    )
    assert metadata["bytes"] == path.stat().st_size
    assert metadata["product"] == "L2_REF"
    assert metadata["variant"] == "default"
    assert metadata["url"].startswith("/api/radar/live/webgl/v2/L2_REF/KGGW/0p5/")
    assert metadata["url"].endswith("?variant=default")
    assert webgl_artifact.resolve_artifact(
        tmp_path, "v2", "L2_REF", "KGGW", "0p5", "2026_07_26_02_32_50"
    ) == path.resolve()


@pytest.mark.parametrize(
    ("product", "field_name"),
    [
        ("L2_VEL", "velocity"),
        ("L2_SRV", "storm_relative_velocity"),
    ],
)
def test_velocity_family_uses_bounded_u16_value_encoding(
    tmp_path, monkeypatch, product, field_name
):
    from config.radar_colortable_utils import get_radar_colortable
    from matplotlib.colors import Normalize

    _enable_velocity(monkeypatch)
    product_cfg = dict(radar_config.LIVE_RADAR_PRODUCTS[product])
    path = webgl_artifact.write_artifact(
        tmp_path,
        "KGGW",
        "2026_07_26_02_32_50",
        0.5,
        FakeRadar(),
        field_name,
        0,
        product_cfg,
        product,
    )

    assert path is not None
    assert path.stat().st_size < 3_000_000
    header, texture_bytes = webgl_artifact.read_artifact(path)
    assert header["product"] == product
    assert header["code_bytes"] == 2
    assert header["palette_entries"] == 512
    assert header["missing_code"] == 65535
    assert header["max_quantization_error"] <= header["value_scale"] / 2 + 1e-6

    texture = np.frombuffer(texture_bytes, dtype=np.uint8).reshape(
        header["texture_height"], header["texture_width"]
    )
    # The zero-degree ray is the second source row; its four values are unmasked.
    low = texture[0, 2 : 2 + header["gate_count"] * 2 : 2].astype(np.uint16)
    high = texture[0, 3 : 2 + header["gate_count"] * 2 : 2].astype(np.uint16)
    codes = low + high * 256
    assert np.all(codes != header["missing_code"])

    values = np.asarray(FakeRadar().fields[field_name]["data"][1], dtype=float)
    decoded = header["value_offset"] + codes.astype(float) * header["value_scale"]
    np.testing.assert_allclose(
        decoded,
        np.minimum(values, product_cfg["vmax"]),
        atol=header["value_scale"] / 2 + 1e-6,
    )

    cmap = get_radar_colortable(
        product_cfg["palette"], product_cfg["vmin"], product_cfg["vmax"]
    )["cmap"]
    expected_rgba = cmap(
        Normalize(product_cfg["vmin"], product_cfg["vmax"])(values),
        bytes=True,
    )
    palette = texture[
        header["ray_count"], : header["palette_entries"] * 4
    ].reshape(-1, 4)
    palette_indexes = np.minimum(
        np.floor(
            codes.astype(float)
            / (header["missing_code"] - 1)
            * header["palette_entries"]
        ).astype(int),
        header["palette_entries"] - 1,
    )
    np.testing.assert_array_equal(palette[palette_indexes], expected_rgba)


def test_srv_motion_variants_are_isolated(tmp_path, monkeypatch):
    _enable_velocity(monkeypatch)
    first_cfg = dict(radar_config.LIVE_RADAR_PRODUCTS["L2_SRV"])
    second_cfg = dict(first_cfg)
    first_cfg["cache_variant"] = "nst_cell_a_025kt_to045_v1"
    second_cfg["cache_variant"] = "nst_cell_b_040kt_to090_v1"

    first = webgl_artifact.write_artifact(
        tmp_path,
        "KGGW",
        "2026_07_26_02_32_50",
        0.5,
        FakeRadar(),
        "storm_relative_velocity",
        0,
        first_cfg,
        "L2_SRV",
    )
    second = webgl_artifact.write_artifact(
        tmp_path,
        "KGGW",
        "2026_07_26_02_32_50",
        0.5,
        FakeRadar(),
        "storm_relative_velocity",
        0,
        second_cfg,
        "L2_SRV",
    )

    assert first != second
    assert first_cfg["cache_variant"] in first.parts
    assert second_cfg["cache_variant"] in second.parts
    metadata = webgl_artifact.artifact_metadata(
        tmp_path,
        "KGGW",
        "L2_SRV",
        0.5,
        "2026_07_26_02_32_50",
        first_cfg["cache_variant"],
    )
    assert f"variant={first_cfg['cache_variant']}" in metadata["url"]
    assert webgl_artifact.resolve_artifact(
        tmp_path,
        "v2",
        "L2_SRV",
        "KGGW",
        "0p5",
        "2026_07_26_02_32_50",
        first_cfg["cache_variant"],
    ) == first.resolve()


@pytest.mark.parametrize(
    ("product_code", "product_key"),
    [("REF", "L2_REF"), ("VEL", "L2_VEL"), ("SRV", "L2_SRV")],
)
def test_worker_publishes_only_the_bounded_webgl_family(product_code, product_key):
    with patch.object(radar_live_worker, "write_artifact", return_value=None) as write:
        radar_live_worker._publish_webgl_artifact(
            "KGGW",
            product_code,
            "2026_07_26_02_32_50",
            0.5,
            FakeRadar(),
            "reflectivity",
            0,
            radar_config.LIVE_RADAR_PRODUCTS[product_key],
        )
    assert write.call_args.args[-1] == product_key


def test_service_metadata_selects_the_requested_srv_motion_variant(
    tmp_path, monkeypatch
):
    _enable_velocity(monkeypatch)
    monkeypatch.setattr(radar_service, "CACHE_ROOT", str(tmp_path))
    variant = "nst_cell_a_025kt_to045_v1"
    product_cfg = dict(radar_config.LIVE_RADAR_PRODUCTS["L2_SRV"])
    product_cfg["cache_variant"] = variant
    path = webgl_artifact.write_artifact(
        tmp_path,
        "KGGW",
        "2026_07_26_02_32_50",
        0.5,
        FakeRadar(),
        "storm_relative_velocity",
        0,
        product_cfg,
        "L2_SRV",
    )
    metadata = radar_service._radar_webgl_artifact_metadata(
        {"frame_key": "2026_07_26_02_32_50", "selected_elevation": 0.5},
        "KGGW",
        "L2_SRV",
        "0.5",
        {
            "speed_kt": 25.0,
            "motion_to_degrees": 45.0,
            "cache_variant": variant,
            "source": "NST",
            "cell_id": "A",
        },
    )
    assert metadata["variant"] == variant
    assert metadata["bytes"] == path.stat().st_size


def test_srv_variant_rejects_path_traversal(tmp_path, monkeypatch):
    _enable_velocity(monkeypatch)
    assert webgl_artifact.resolve_artifact(
        tmp_path,
        "v2",
        "L2_SRV",
        "KGGW",
        "0p5",
        "2026_07_26_02_32_50",
        "../../L2_REF",
    ) is None


def test_disabled_feature_does_not_publish_or_expose_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(radar_config, "LIVE_RADAR_WEBGL_ENABLED", False)
    path = webgl_artifact.write_artifact(
        tmp_path,
        "KGGW",
        "2026_07_26_02_32_50",
        0.5,
        FakeRadar(),
        "reflectivity",
        0,
        radar_config.LIVE_RADAR_PRODUCTS["L2_REF"],
    )
    assert path is None
    assert webgl_artifact.artifact_metadata(
        tmp_path, "KGGW", "L2_REF", 0.5, "2026_07_26_02_32_50"
    ) is None
    assert webgl_artifact.resolve_artifact(
        tmp_path, "v2", "L2_REF", "KGGW", "0p5", "2026_07_26_02_32_50"
    ) is None


def test_artifact_wire_header_matches_documented_layout(monkeypatch):
    _enable(monkeypatch)
    header, texture = webgl_artifact.build_artifact(
        FakeRadar(),
        "reflectivity",
        0,
        "KGGW",
        "2026_07_26_02_32_50",
        0.5,
        radar_config.LIVE_RADAR_PRODUCTS["L2_REF"],
    )
    encoded = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    payload = webgl_artifact.MAGIC + struct.pack("<I", len(encoded)) + encoded + texture
    assert payload[:8] == b"RWPOLAR1"
    assert struct.unpack_from("<I", payload, 8)[0] == len(encoded)


def test_versioned_endpoint_is_unreachable_when_feature_is_disabled(
    tmp_path, monkeypatch
):
    _enable(monkeypatch)
    monkeypatch.setattr(radar_service, "CACHE_ROOT", str(tmp_path))
    webgl_artifact.write_artifact(
        tmp_path,
        "KGGW",
        "2026_07_26_02_32_50",
        0.5,
        FakeRadar(),
        "reflectivity",
        0,
        radar_config.LIVE_RADAR_PRODUCTS["L2_REF"],
    )

    response = radar_service.get_radar_live_webgl_artifact_data(
        "v2", "L2_REF", "KGGW", "0p5", "2026_07_26_02_32_50", "default"
    )
    assert str(response.path).endswith("2026_07_26_02_32_50.rwp")

    monkeypatch.setattr(radar_config, "LIVE_RADAR_WEBGL_ENABLED", False)
    with pytest.raises(HTTPException, match="Radar WebGL artifact unavailable"):
        radar_service.get_radar_live_webgl_artifact_data(
            "v2", "L2_REF", "KGGW", "0p5", "2026_07_26_02_32_50", "default"
        )
