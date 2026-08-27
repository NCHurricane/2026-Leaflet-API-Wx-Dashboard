from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from config.satellite_platforms import PROVIDER_AWS_GMGSI, platform_descriptor
from config.satellite_v2_config import (
    SATELLITE_V2_SUPPORTED_SATELLITES,
    SATELLITE_V2_SUPPORTED_SECTORS,
    satellite_v2_render_version_for_satellite,
)
from satellite_v2 import provider_gmgsi
from satellite_v2.gmgsi_nc import load_gmgsi_raster
from satellite_v2.models import SourceFrame
from satellite_v2.renderer import _is_gmgsi_file


def _synthetic_dataset(title: str) -> xr.Dataset:
    lon_row = np.array([179.999, -179.928, -90.0, 0.0], dtype=np.float32)
    lat_col = np.array([50.0, -50.0], dtype=np.float32)
    lon = np.broadcast_to(lon_row, (2, 4)).copy()
    lat = np.broadcast_to(lat_col[:, None], (2, 4)).copy()
    return xr.Dataset(
        data_vars={
            "data": (
                ("time", "yc", "xc"),
                np.array([[[10, 20, 176, 200], [30, 40, 255, 0]]], np.float32),
            ),
            "dqf": (
                ("time", "yc", "xc"),
                np.array([[[0, 0, 0, 0], [0, 10, 20, 0]]], np.float32),
            ),
        },
        coords={
            "time": np.array(["2026-07-31T20:00:00"], dtype="datetime64[s]"),
            "lon": (("yc", "xc"), lon),
            "lat": (("yc", "xc"), lat),
        },
        attrs={"title": title},
    )


def test_gmgsi_platform_and_frontend_are_separately_bounded() -> None:
    root = Path(__file__).resolve().parents[1]
    page = (root / "frontend/pages/satellite/satellite.html").read_text("utf-8")
    script = (root / "frontend/pages/satellite/satellite-page.js").read_text(
        "utf-8"
    )
    engine = (root / "frontend/pages/satellite/satellite-engine.js").read_text(
        "utf-8"
    )
    descriptor = platform_descriptor("gmgsi")
    assert descriptor["provider"] == PROVIDER_AWS_GMGSI
    assert descriptor["sectors"] == ["GLOBAL"]
    assert "gmgsi" in SATELLITE_V2_SUPPORTED_SATELLITES
    assert "GLOBAL" in SATELLITE_V2_SUPPORTED_SECTORS
    assert satellite_v2_render_version_for_satellite("gmgsi") == "products-gmgsi2"
    assert 'data-satellite-sat="gmgsi"' in page
    assert 'data-satellite-sector="Global"' in page
    assert "gmgsi: new Set(['Channel02', 'Channel07', 'Channel09RAMSDIS', 'Channel13'])" in script
    assert "'gmgsi:Global': 'global'" in script
    assert "return Math.min(FRAME_REQUEST_MAX, safeHours + 1);" in script
    assert "gmgsi: 'GMGSI Global Mosaic'" in engine
    assert "satellite-page.js?v=20260826i" in page


def test_gmgsi_provider_lists_the_hourly_product(monkeypatch) -> None:
    prior_prefix = "GMGSI_LW/2026/07/31/19/"
    current_prefix = "GMGSI_LW/2026/07/31/20/"
    prior_key = (
        prior_prefix
        + "GLOBCOMPLIR_v3r0_blend_s202607311900000_"
        "e202607311909599_c202607311935012.nc"
    )
    current_key = (
        current_prefix
        + "GLOBCOMPLIR_v3r0_blend_s202607312000000_"
        "e202607312009599_c202607312035012.nc"
    )
    monkeypatch.setattr(
        provider_gmgsi,
        "_iter_hour_prefixes",
        lambda product, hours: [current_prefix, prior_prefix],
    )
    monkeypatch.setattr(
        provider_gmgsi,
        "_list_prefix_objects",
        lambda listed: [
            (current_key, 7_374_067)
            if listed == current_prefix
            else (prior_key, 7_300_000)
        ],
    )
    frames = provider_gmgsi.list_recent_frames(
        "gmgsi", "GLOBAL", "Channel13", hours=1, max_frames=2
    )
    assert [frame.frame_key for frame in frames] == [
        "20260731T190000Z",
        "20260731T200000Z",
    ]
    assert frames[-1].source_keys == {"Channel13": current_key}
    assert frames[-1].file_sizes == {"Channel13": 7_374_067}


def test_gmgsi_provider_downloads_to_the_independent_source_cache(
    tmp_path, monkeypatch
) -> None:
    key = (
        "GMGSI_VIS/2026/07/31/20/"
        "GLOBCOMPVIS_v3r0_blend_s202607312000000_"
        "e202607312009599_c202607312042476.nc"
    )
    frame = SourceFrame(
        frame_key="20260731T200000Z",
        timestamp_utc="2026-07-31T20:00:00Z",
        provider="aws",
        source_key=key,
        source_url=f"s3://noaa-gmgsi-pds/{key}",
        source_keys={"Channel02": key},
    )

    class FakeClient:
        def download_file(self, bucket: str, source_key: str, target: str) -> None:
            assert bucket == "noaa-gmgsi-pds"
            assert source_key == key
            Path(target).write_bytes(b"gmgsi")

    monkeypatch.setattr(provider_gmgsi, "_s3_client", lambda: FakeClient())
    paths = provider_gmgsi.download_product_source_frames(
        tmp_path, "gmgsi", "GLOBAL", "Channel02", frame
    )
    assert paths["Channel02"].read_bytes() == b"gmgsi"
    assert "gmgsi" in paths["Channel02"].parts
    assert "GLOBAL" in paths["Channel02"].parts


def test_gmgsi_loader_decodes_visible_counts_and_quality() -> None:
    raster = load_gmgsi_raster(_synthetic_dataset("GLOBCOMPVIS"), "Channel02")
    np.testing.assert_allclose(
        raster.values[0],
        np.array([20, 176, 200, 10], dtype=np.float32) / 255.0,
    )
    assert np.isnan(raster.values[1, 0])
    assert np.isnan(raster.values[1, 1])
    assert raster.src_crs.to_epsg() == 3857
    assert raster.observation_time == datetime(2026, 7, 31, 20, tzinfo=timezone.utc)


def test_gmgsi_loader_decodes_ir_brightness_counts_to_kelvin() -> None:
    raster = load_gmgsi_raster(_synthetic_dataset("GLOBCOMPLIR"), "Channel13")
    np.testing.assert_allclose(
        raster.values[0],
        np.array([320.0, 242.0, 218.0, 325.0], dtype=np.float32),
    )
    assert _is_gmgsi_file(Path("GLOBCOMPLIR_v3r0_blend_s202607312000000.nc"))
