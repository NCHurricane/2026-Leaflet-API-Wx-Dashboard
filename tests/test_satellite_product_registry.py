import pytest

from config.satellite_v2_config import (
    ABI_CHANNELS,
    SATELLITE_V2_DASHBOARD_PRODUCTS,
    SATELLITE_V2_PRODUCTS,
    normalize_channel,
)


REMOVED_PRODUCT_KEYS = {
    "BlowingSnow",
    "Channel07MetPyDRGB",
    "Channel08",
    "Channel08MetPyTPC",
    "Channel08SatpyWV2",
    "Channel09",
    "Channel09MetPyTPC",
    "Channel09SatpyWV2",
    "Channel10",
    "Channel10MetPyTPC",
    "Channel10RAMSDIS",
    "Channel10SatpyWV2",
    "Channel11",
    "Channel13CIRAWinter",
    "Channel13MetPyBD",
    "Channel13MetPyDRGB",
    "Channel13MetPyRGBV",
    "Channel13MetPyTPC",
    "Channel13MetPyTV1",
    "Channel13Satpy",
    "Channel14CIRA",
    "Channel14CIRAWinter",
    "Channel14MetPyBD",
    "Channel14MetPyTV1",
    "Channel15",
    "DayCloudConvection",
    "DayCloudPhaseEUMETSAT",
    "DayConvection",
    "DayLandCloud",
    "DayNightHybrid",
    "DifferentialWaterVapor",
    "NightFogDifference",
    "Sandwich",
    "SeaSpray",
    "SplitWindowDifference",
    "WaterVapor",
}


def test_satellite_registry_contains_only_dashboard_products():
    assert set(ABI_CHANNELS) == set(SATELLITE_V2_DASHBOARD_PRODUCTS)
    assert tuple(SATELLITE_V2_PRODUCTS) == SATELLITE_V2_DASHBOARD_PRODUCTS
    assert len(SATELLITE_V2_PRODUCTS) == 28


@pytest.mark.parametrize("product_key", sorted(REMOVED_PRODUCT_KEYS))
def test_removed_satellite_product_is_rejected(product_key):
    with pytest.raises(ValueError, match="Unsupported satellite channel"):
        normalize_channel(product_key)
