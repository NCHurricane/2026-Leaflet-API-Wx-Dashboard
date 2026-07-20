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
