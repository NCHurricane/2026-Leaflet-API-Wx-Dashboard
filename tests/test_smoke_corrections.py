from surface import surface_utils


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "features": [
                {
                    "properties": {
                        "sid": "1F0",
                        "sname": "Ardmore Downtown Executive Airport",
                    }
                }
            ]
        }


def test_surface_station_names_use_iem_network_sname(monkeypatch):
    surface_utils._get_station_names.cache_clear()
    monkeypatch.setattr(surface_utils.requests, "get", lambda *args, **kwargs: _FakeResponse())

    names = surface_utils._get_station_names("OK_ASOS")

    assert names["1F0"] == "Ardmore Downtown Executive Airport"
    surface_utils._get_station_names.cache_clear()
