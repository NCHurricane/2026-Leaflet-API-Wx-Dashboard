from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from surface import surface_utils


def _raw_surface_frame(**overrides):
    data = {
        "station": ["COLD", "HOT"],
        "valid": ["2026-08-07T12:00:00Z", "2026-08-07T12:00:00Z"],
        "lat": [35.0, 36.0],
        "lon": [-80.0, -81.0],
        "tmpf": [40, 90],
        "dwpf": [35, 70],
        "sknt": [10, 5],
        "drct": [180, 190],
        "relh": [70, 60],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def test_process_dataframe_handles_integer_temperature_derived_values():
    actual = surface_utils.process_dataframe(_raw_surface_frame(), "NC")

    assert actual["feels_like"].dtype.kind == "f"
    assert np.isfinite(actual["feels_like"]).all()
    assert actual.loc[actual["station_id"] == "COLD", "feels_like"].iat[0] < 40
    assert actual.loc[actual["station_id"] == "HOT", "feels_like"].iat[0] > 90


def test_process_dataframe_fills_only_missing_relative_humidity_rows():
    raw = _raw_surface_frame(
        tmpf=[85.0, 90.0],
        dwpf=[70.0, 70.0],
        relh=[65.0, None],
    )

    actual = surface_utils.process_dataframe(raw, "NC")
    expected_rh = surface_utils.calc_relative_humidity(
        pd.Series([90.0]), pd.Series([70.0])
    ).iat[0]

    assert actual["relative_humidity"].iat[0] == 65.0
    assert actual["relative_humidity"].iat[1] == pytest.approx(expected_rh)
    assert np.isfinite(actual["heat_index"]).all()
    assert np.isfinite(actual["feels_like"]).all()


def test_process_dataframe_supplies_required_text_columns():
    raw = pd.DataFrame(
        {
            "station": ["KAVL"],
            "lat": [35.44],
            "lon": [-82.54],
            "tmpf": [72.0],
            "name": [None],
            "network": [""],
        }
    )

    actual = surface_utils.process_dataframe(raw, "NC")

    assert actual.loc[0, "station_id"] == "KAVL"
    assert actual.loc[0, "name"] == "KAVL"
    assert pd.isna(actual.loc[0, "valid"])
    assert actual.loc[0, "network"] == "ASOS"


def test_awc_records_normalize_through_the_shared_surface_schema(monkeypatch):
    monkeypatch.setattr(
        surface_utils,
        "_get_world_station_name_map",
        lambda: {"KAVL": "Asheville Regional Airport"},
    )
    records = [
        {
            "icaoId": "KAVL",
            "obsTime": int(datetime(2026, 8, 7, 12, tzinfo=timezone.utc).timestamp()),
            "temp": 20.0,
            "dewp": 10.0,
            "lat": 35.44,
            "lon": -82.54,
            "wspd": 8,
            "wdir": 220,
            "visib": "10+",
        }
    ]

    raw = surface_utils._awc_records_to_iem_df(records)
    actual = surface_utils.process_dataframe(raw, "NC")

    assert actual.loc[0, "station_id"] == "AVL"
    assert actual.loc[0, "name"] == "Asheville Regional Airport"
    assert actual.loc[0, "air_temperature"] == pytest.approx(68.0)
    assert actual.loc[0, "visibility"] == 10.0
    assert np.isfinite(actual.loc[0, "relative_humidity"])


def test_archive_frame_selection_preserves_provider_provenance():
    frame = surface_utils.process_dataframe(_raw_surface_frame(), "NC")
    frame.attrs["surface_source"] = "iem"

    selected = surface_utils._select_nearest_station_rows(
        frame,
        datetime(2026, 8, 7, 12, 15, tzinfo=timezone.utc),
    )

    assert not selected.empty
    assert selected.attrs["surface_source"] == "iem"
