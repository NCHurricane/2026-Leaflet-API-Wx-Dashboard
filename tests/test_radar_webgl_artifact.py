import json
import struct

import numpy as np
import pytest
from fastapi import HTTPException

from config import radar_config
from radar import webgl_artifact
from services import radar_service


class FakeRadar:
    def __init__(self):
        values = np.ma.array(
            [[5.0, 5.5, 10.0, 20.0], [30.0, 40.0, 50.0, 60.0]],
            mask=[[False, True, False, False], [False, False, False, False]],
        )
        self.fields = {"reflectivity": {"data": values}}
        self.azimuth = {"data": np.array([180.0, 0.0])}
        self.range = {"data": np.array([2125.0, 2375.0, 2625.0, 2875.0])}
        self.latitude = {"data": np.array([48.2])}
        self.longitude = {"data": np.array([-106.6])}

    @staticmethod
    def get_slice(_sweep):
        return slice(0, 2)


def _enable(monkeypatch):
    monkeypatch.setattr(radar_config, "LIVE_RADAR_WEBGL_ENABLED", True)


def test_feature_config_bounds_animation_window(monkeypatch):
    monkeypatch.setattr(radar_config, "LIVE_RADAR_WEBGL_ENABLED", True)
    monkeypatch.setattr(radar_config, "LIVE_RADAR_WEBGL_ANIMATION_ENABLED", True)

    config = webgl_artifact.feature_config()

    assert config["animation_enabled"] is True
    assert config["texture_budget"] == 4
    assert config["min_forward_textures"] == 2
    assert config["max_concurrent_loads"] == 2

    monkeypatch.setattr(radar_config, "LIVE_RADAR_WEBGL_ENABLED", False)
    assert webgl_artifact.feature_config()["animation_enabled"] is False


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
    assert path.parents[2].name == "v1"
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
    assert metadata["url"].startswith("/api/radar/live/webgl/v1/L2_REF/KGGW/0p5/")
    assert webgl_artifact.resolve_artifact(
        tmp_path, "v1", "L2_REF", "KGGW", "0p5", "2026_07_26_02_32_50"
    ) == path.resolve()


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
        tmp_path, "v1", "L2_REF", "KGGW", "0p5", "2026_07_26_02_32_50"
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
        "v1", "L2_REF", "KGGW", "0p5", "2026_07_26_02_32_50"
    )
    assert str(response.path).endswith("2026_07_26_02_32_50.rwp")

    monkeypatch.setattr(radar_config, "LIVE_RADAR_WEBGL_ENABLED", False)
    with pytest.raises(HTTPException, match="Radar WebGL artifact unavailable"):
        radar_service.get_radar_live_webgl_artifact_data(
            "v1", "L2_REF", "KGGW", "0p5", "2026_07_26_02_32_50"
        )
