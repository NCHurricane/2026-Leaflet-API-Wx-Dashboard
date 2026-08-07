from __future__ import annotations

import numpy as np
import pytest

import mrms.mrms_utils as mrms_utils


class _DataArray:
    def __init__(self, values):
        self._values = np.asarray(values)

    @property
    def values(self):
        return self._values


class _FailingDataArray:
    @property
    def values(self):
        raise RuntimeError("materialization failed")


class _Dataset:
    def __init__(self, data_vars):
        self.data_vars = data_vars
        self.coords = {}
        self.dims = {}
        self.sizes = {}
        self.attrs = {"GRIB_gridType": "regular_ll"}
        self.close_calls = 0

    def __contains__(self, key):
        return key in self.data_vars or key in self.coords

    def __getitem__(self, key):
        if key in self.coords:
            return self.coords[key]
        return self.data_vars[key]

    def close(self):
        self.close_calls += 1


def _install_dataset(monkeypatch, dataset):
    calls = []

    def open_dataset(path, **kwargs):
        calls.append((path, kwargs))
        return dataset

    monkeypatch.setattr(mrms_utils, "CFGRIB_AVAILABLE", True)
    monkeypatch.setattr(mrms_utils.xr, "open_dataset", open_dataset)
    return calls


def test_mrms_decode_selects_product_variable_instead_of_first_dataset_variable(
    monkeypatch,
):
    dataset = _Dataset(
        {
            "auxiliary": _DataArray([[999.0]]),
            "refl_baseqc": _DataArray([[42.0]]),
        }
    )
    calls = _install_dataset(monkeypatch, dataset)

    data, metadata = mrms_utils.read_mrms_grib2(
        "fixture.grib2",
        "Refl_BaseQC",
    )

    assert data.tolist() == [[42.0]]
    assert metadata["projection"] == "regular_ll"
    assert dataset.close_calls == 1
    assert calls == [
        (
            "fixture.grib2",
            {
                "engine": "cfgrib",
                "backend_kwargs": {"indexpath": ""},
            },
        )
    ]


def test_mrms_decode_preserves_first_variable_fallback_when_product_is_absent(
    monkeypatch,
):
    dataset = _Dataset(
        {
            "unknown": _DataArray([[7.0]]),
            "secondary": _DataArray([[8.0]]),
        }
    )
    _install_dataset(monkeypatch, dataset)

    data, _metadata = mrms_utils.read_mrms_grib2(
        "fixture.grib2",
        "PrecipRate",
    )

    assert data.tolist() == [[7.0]]
    assert dataset.close_calls == 1


def test_mrms_decode_closes_dataset_when_data_materialization_fails(monkeypatch):
    dataset = _Dataset({"PrecipRate": _FailingDataArray()})
    _install_dataset(monkeypatch, dataset)

    with pytest.raises(ValueError, match="materialization failed"):
        mrms_utils.read_mrms_grib2("fixture.grib2", "PrecipRate")

    assert dataset.close_calls == 1


def test_mrms_decode_closes_dataset_when_no_data_variables_exist(monkeypatch):
    dataset = _Dataset({})
    _install_dataset(monkeypatch, dataset)

    with pytest.raises(ValueError, match="No data variables found"):
        mrms_utils.read_mrms_grib2("fixture.grib2", "PrecipRate")

    assert dataset.close_calls == 1
