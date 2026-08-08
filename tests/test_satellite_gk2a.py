from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from config.satellite_v2_config import (
    ami_supported_products,
    satellite_v2_render_version_for_satellite,
)
from satellite_v2 import ami_nc, composites, provider_gk2a, providers, renderer


GK2A_COMPOSITES = (
    "GeoColor",
    "GeoColorBlkMar",
    "TrueColor",
    "NaturalColor",
    "DayCloudPhase",
    "DaySnowFog",
)


def test_gk2a_exposes_only_proven_products():
    root = Path(__file__).resolve().parents[1]
    page = (root / "frontend/pages/satellite/satellite.html").read_text("utf-8")
    script = (root / "frontend/pages/satellite/satellite-page.js").read_text("utf-8")
    assert 'data-satellite-sat="gk2a"' in page
    assert '<option value="asia-pacific">Asia-Pacific</option>' in page
    assert "gk2a: new Set([" in script
    assert "'Channel01', 'Channel02', 'Channel03', 'Channel05'" in script
    assert "'Channel07', 'Channel07Fire'" in script
    assert "'Channel08RAMSDIS', 'Channel09RAMSDIS'" in script
    assert "'Channel13', 'Channel14'" in script
    assert "'GeoColor', 'GeoColorBlkMar', 'TrueColor', 'NaturalColor'" in script
    assert "'DayCloudPhase', 'DaySnowFog'" in script
    assert "'gk2a:FullDisk': 'asia-pacific'" in script


def test_gk2a_ami_capability_filter_includes_only_valid_composites():
    supported = set(ami_supported_products())

    assert supported == {
        "Channel01",
        "Channel02",
        "Channel03",
        "Channel05",
        "Channel07",
        "Channel07Fire",
        "Channel08RAMSDIS",
        "Channel09RAMSDIS",
        "Channel13",
        "Channel14",
        *GK2A_COMPOSITES,
    }
    assert satellite_v2_render_version_for_satellite("gk2a") == "products-ami2"
    assert satellite_v2_render_version_for_satellite("goes19") == "products-v8"


@pytest.mark.parametrize("product_key", GK2A_COMPOSITES)
def test_gk2a_valid_composite_recipe_renders_finite_rgb(product_key):
    y, x = np.mgrid[0:8, 0:8].astype(np.float32)
    channels = {
        "Channel01": 0.08 + x * 0.025,
        "Channel02": 0.12 + y * 0.035,
        "Channel03": 0.18 + (x + y) * 0.018,
        "Channel05": 0.10 + x * 0.045,
        "Channel07": 276.0 + x * 0.8,
        "Channel13": 220.0 + y * 7.0,
    }
    lon_grid = np.linspace(100.0, 155.0, 64, dtype=np.float32).reshape(8, 8)
    lat_grid = np.linspace(-25.0, 35.0, 64, dtype=np.float32).reshape(8, 8)

    rgb = composites.render_composite_rgb(
        product_key,
        channels,
        lon_grid=lon_grid,
        lat_grid=lat_grid,
        instrument="AMI",
        observation_time=datetime(2026, 7, 29, 6, tzinfo=timezone.utc),
        satellite_longitude=128.2,
        satellite_height_km=35_785.863,
    )

    assert rgb.shape == (8, 8, 3)
    assert np.isfinite(rgb).all()
    assert 0.0 <= float(rgb.min()) <= float(rgb.max()) <= 1.0
    assert float(np.ptp(rgb)) > 0.05


def test_gk2a_composite_catalog_requires_common_channel_timestamp(monkeypatch):
    prefix = "AMI/L1B/FD/202607/29/18/"
    keys = [
        (prefix + f"gk2a_ami_le1b_{channel}_fd020ge_202607291800.nc", 100)
        for channel in ("vi004", "vi006", "vi008", "sw038", "ir105")
    ]
    keys.append(
        (prefix + "gk2a_ami_le1b_vi006_fd005ge_202607291810.nc", 100)
    )
    monkeypatch.setattr(provider_gk2a, "_iter_hour_prefixes", lambda _hours: [prefix])
    monkeypatch.setattr(provider_gk2a, "_list_prefix_objects", lambda _prefix: keys)

    frames = provider_gk2a.list_recent_frames(
        "gk2a", "FULLDISK", "GeoColor", hours=1, max_frames=12
    )

    assert [frame.frame_key for frame in frames] == ["20260729T180000Z"]
    assert set(frames[0].source_keys) == {
        "Channel01",
        "Channel02",
        "Channel03",
        "Channel07",
        "Channel13",
    }


def test_gk2a_provider_lists_only_requested_channel(monkeypatch):
    prefix = "AMI/L1B/FD/202607/29/18/"
    keys = [
        (
            prefix + "gk2a_ami_le1b_ir105_fd020ge_202607291800.nc",
            35_621_610,
        ),
        (
            prefix + "gk2a_ami_le1b_ir112_fd020ge_202607291800.nc",
            35_594_190,
        ),
        (
            prefix + "gk2a_ami_le1b_ir105_fd020ge_202607291810.nc",
            35_619_173,
        ),
        (
            prefix + "gk2a_ami_le1b_vi006_fd005ge_202607291800.nc",
            129_000_000,
        ),
        (
            prefix + "gk2a_ami_le1b_sw038_fd020ge_202607291800.nc",
            35_000_000,
        ),
        (
            prefix + "gk2a_ami_le1b_wv063_fd020ge_202607291800.nc",
            35_000_000,
        ),
        (
            prefix + "gk2a_ami_le1b_wv069_fd020ge_202607291800.nc",
            35_000_000,
        ),
    ]
    monkeypatch.setattr(provider_gk2a, "_iter_hour_prefixes", lambda _hours: [prefix])
    monkeypatch.setattr(provider_gk2a, "_list_prefix_objects", lambda _prefix: keys)

    frames = provider_gk2a.list_recent_frames(
        "gk2a", "FULLDISK", "Channel13", hours=1, max_frames=12
    )

    assert [frame.frame_key for frame in frames] == [
        "20260729T180000Z",
        "20260729T181000Z",
    ]
    assert all("_ir105_" in frame.source_key for frame in frames)
    assert frames[0].file_sizes == {"Channel13": 35_621_610}
    assert providers._provider_module("gk2a") is provider_gk2a

    channel14 = provider_gk2a.list_recent_frames(
        "gk2a", "FULLDISK", "Channel14", hours=1, max_frames=12
    )
    assert [frame.frame_key for frame in channel14] == ["20260729T180000Z"]
    assert "_ir112_" in channel14[0].source_key

    channel02 = provider_gk2a.list_recent_frames(
        "gk2a", "FULLDISK", "Channel02", hours=1, max_frames=12
    )
    assert [frame.frame_key for frame in channel02] == ["20260729T180000Z"]
    assert "_vi006_" in channel02[0].source_key

    channel07_fire = provider_gk2a.list_recent_frames(
        "gk2a", "FULLDISK", "Channel07Fire", hours=1, max_frames=12
    )
    assert [frame.frame_key for frame in channel07_fire] == ["20260729T180000Z"]
    assert "_sw038_" in channel07_fire[0].source_key

    channel08 = provider_gk2a.list_recent_frames(
        "gk2a", "FULLDISK", "Channel08RAMSDIS", hours=1, max_frames=12
    )
    channel09 = provider_gk2a.list_recent_frames(
        "gk2a", "FULLDISK", "Channel09RAMSDIS", hours=1, max_frames=12
    )
    assert [frame.frame_key for frame in channel08] == ["20260729T180000Z"]
    assert "_wv063_" in channel08[0].source_key
    assert [frame.frame_key for frame in channel09] == ["20260729T180000Z"]
    assert "_wv069_" in channel09[0].source_key


def test_gk2a_ami_loader_calibrates_ir_and_masks_quality(tmp_path):
    source = tmp_path / "gk2a_ami_le1b_ir105_fd020ge_202607291800.nc"
    packed = np.array([[3000, 4000], [0x8001, 5000]], dtype=np.uint16)
    dataset = xr.Dataset(
        {
            "image_pixel_values": (
                ("dim_image_y", "dim_image_x"),
                packed,
                {
                    "channel_name": "IR105",
                    "number_of_valid_bits_per_pixel": np.uint8(13),
                },
            )
        },
        attrs={
            "instrument_name": "AMI",
            "DN_to_Radiance_Gain": -0.0198196955025196,
            "DN_to_Radiance_Offset": 161.580139160156,
            "Teff_to_Tbb_c0": -0.142866448475177,
            "Teff_to_Tbb_c1": 1.00064069572049,
            "Teff_to_Tbb_c2": -5.50443294960498e-7,
            "light_speed": 299792458.0,
            "Plank_constant_h": 6.62606957e-34,
            "Boltzmann_constant_k": 1.3806488e-23,
            "channel_center_wavelength": 10.5,
            "earth_equatorial_radius": 6378137.0,
            "earth_polar_radius": 6356752.3,
            "nominal_satellite_height": 42164000.0,
            "sub_longitude": math.radians(128.2),
            "image_upperleft_x": -0.000028,
            "image_upperleft_y": 0.000028,
            "image_lowerright_x": 0.000028,
            "image_lowerright_y": -0.000028,
            "mission_reference_time": "20260729_180000",
        },
    )
    dataset.to_netcdf(source, engine="netcdf4")

    raster = renderer._load_source_raster(source, "Channel13")

    assert raster.cmi.shape == (2, 2)
    assert np.isfinite(raster.cmi[0, 0])
    assert np.isnan(raster.cmi[1, 0])
    assert 150.0 < float(raster.cmi[0, 0]) < 350.0
    assert raster.satellite_longitude == pytest.approx(128.2)
    assert raster.satellite_height_km == pytest.approx(35_785.863)
    assert raster.observation_time == datetime(2026, 7, 29, 18, tzinfo=timezone.utc)
    assert "lon_0=128.2" in raster.src_crs.to_proj4()


def test_gk2a_ami_loader_calibrates_reflectance_with_bounded_stride(monkeypatch):
    monkeypatch.setattr(ami_nc, "SATELLITE_V2_AMI_MAX_GRID", 2)
    dataset = xr.Dataset(
        {
            "image_pixel_values": (
                ("dim_image_y", "dim_image_x"),
                np.arange(16, dtype=np.uint16).reshape(4, 4),
                {
                    "channel_name": "VI006",
                    "number_of_valid_bits_per_pixel": np.uint8(13),
                },
            )
        },
        attrs={
            "instrument_name": "AMI",
            "DN_to_Radiance_Gain": 1.0,
            "DN_to_Radiance_Offset": 0.0,
            "Radiance_to_Albedo_c": 0.01,
            "earth_equatorial_radius": 6378137.0,
            "earth_polar_radius": 6356752.3,
            "nominal_satellite_height": 42164000.0,
            "sub_longitude": math.radians(128.2),
            "image_upperleft_x": -0.000084,
            "image_upperleft_y": 0.000084,
            "image_lowerright_x": 0.000084,
            "image_lowerright_y": -0.000084,
            "mission_reference_time": "20260729_180000",
        },
    )

    raster = ami_nc.load_ami_raster(dataset, "Channel02")

    assert raster.values.shape == (2, 2)
    np.testing.assert_allclose(
        raster.values,
        np.array([[0.05, 0.07], [0.13, 0.15]], dtype=np.float32),
    )
