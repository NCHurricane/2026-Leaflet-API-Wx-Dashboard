import json
import os

from services import tropical_service


def _write_old_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(path, (1, 1))


def test_tropical_page_reads_do_not_refresh_existing_worker_cache(tmp_path, monkeypatch):
    cache_dir = tmp_path / "tropical"
    summary_path = cache_dir / "summary.json"
    _write_old_json(
        summary_path,
        {
            "updated": "2026-07-19T12:00:00Z",
            "interval_minutes": 30,
            "storms": [{"id": "AL012026", "basin": "AL"}],
            "errors": [],
        },
    )

    basin_dir = cache_dir / "basins" / "AL"
    for name in ("index", "gis", "assets", "gtwo"):
        _write_old_json(basin_dir / f"{name}.json", {"kind": name})

    storm_path = cache_dir / "storms" / "AL012026" / "storm.json"
    _write_old_json(storm_path, {"id": "AL012026", "gis_layers": {}})

    monkeypatch.setattr(tropical_service, "_TROPICAL_CACHE_DIR", cache_dir)
    monkeypatch.setattr(tropical_service, "_TROPICAL_SUMMARY_CACHE", summary_path)

    def fail_if_refreshed(force=False):
        raise AssertionError(f"page read unexpectedly invoked worker (force={force})")

    monkeypatch.setattr(tropical_service, "_run_tropical_worker_once", fail_if_refreshed)

    storms = tropical_service.get_tropical_storms_data("AL")
    feeds = tropical_service.get_tropical_basin_feeds_data("AL")
    storm = tropical_service.get_tropical_storm_data("AL012026")

    assert storms["source"] == "worker-cache"
    assert storms["count"] == 1
    assert feeds["gis"] == {"kind": "gis"}
    assert storm["gis_layers"] == {}


def test_tropical_storm_read_upgrades_retired_cone_urls(tmp_path, monkeypatch):
    cache_dir = tmp_path / "tropical"
    storm_path = cache_dir / "storms" / "EP062026" / "storm.json"
    _write_old_json(
        storm_path,
        {
            "id": "EP062026",
            "graphics": [
                {
                    "label": "3-Day Cone",
                    "url": (
                        "https://www.nhc.noaa.gov/storm_graphics/EP06/"
                        "EP062026_3day_cone_no_line_and_wind.png"
                    ),
                },
                {
                    "label": "5-Day Cone",
                    "url": (
                        "https://www.nhc.noaa.gov/storm_graphics/EP06/"
                        "EP062026_5day_cone_no_line_and_wind.png"
                    ),
                },
            ],
        },
    )
    monkeypatch.setattr(tropical_service, "_TROPICAL_CACHE_DIR", cache_dir)
    monkeypatch.setattr(tropical_service, "_maybe_schedule_tropical_refresh", lambda: None)

    storm = tropical_service.get_tropical_storm_data("EP062026")

    urls = [graphic["url"] for graphic in storm["graphics"]]
    assert urls[0].endswith("EP062026_3day_cone_sm2.png")
    assert urls[1].endswith("EP062026_5day_cone_sm2.png")
    cached = json.loads(storm_path.read_text(encoding="utf-8"))
    assert "cone_no_line_and_wind" in cached["graphics"][0]["url"]
