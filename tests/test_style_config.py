import config.style_config as style_config


def test_style_config_retains_only_radar_and_mrms_contracts():
    public_names = {
        name
        for name in vars(style_config)
        if not name.startswith("_")
    }

    assert public_names == {
        "RADAR_FIXED_STYLE_CONFIG",
        "MRMS_FIXED_STYLE_CONFIG",
        "resolve_radar_style_config",
        "resolve_mrms_style_config",
    }


def test_retained_style_resolvers_copy_defaults_and_apply_overrides():
    radar = style_config.resolve_radar_style_config({"show_counties": True})
    mrms = style_config.resolve_mrms_style_config({"show_rivers": True})

    assert radar["show_counties"] is True
    assert style_config.RADAR_FIXED_STYLE_CONFIG["show_counties"] is False
    assert mrms["show_rivers"] is True
    assert style_config.MRMS_FIXED_STYLE_CONFIG["show_rivers"] is False
