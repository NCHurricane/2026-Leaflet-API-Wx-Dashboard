import json
import os
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

from services import tropical_service
from workers import tropical_archive_worker


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


class _ImmediateWarmCoordinator:
    def __init__(self):
        self.states = {}
        self.provider_entries = []

    @contextmanager
    def provider_budget(self, provider):
        self.provider_entries.append(provider)
        yield

    def describe(self, key):
        return self.states.get(tuple(key))

    def submit(self, *, key, provider, function, **_kwargs):
        normalized = tuple(key)
        self.states[normalized] = {"status": "running"}
        function()
        self.states[normalized] = {"status": "succeeded"}
        return tropical_service.Submission(True, "queued")


def test_archive_warm_prefetches_window_then_full_storm_sequentially(
    tmp_path,
    monkeypatch,
):
    storms_dir = tmp_path / "storms"
    sid = "AL012020"
    storm_dir = storms_dir / sid
    steps = [f"{index:03d}" for index in range(1, 8)]
    _write_old_json(storm_dir / "storm.json", {"advisories": steps})
    coordinator = _ImmediateWarmCoordinator()
    built = []

    def build_cached_advisory(storm_id, step, force=False):
        assert storm_id == sid
        assert force is False
        built.append(step)
        _write_old_json(
            storms_dir / storm_id / "advisories" / f"{step}.json",
            {"stormId": storm_id, "advisoryStep": step},
        )
        return {"stormId": storm_id, "advisoryStep": step}

    monkeypatch.setattr(tropical_service, "_TROPICAL_ARCHIVE_STORMS_DIR", storms_dir)
    monkeypatch.setattr(tropical_archive_worker, "STORMS_DIR", storms_dir)
    monkeypatch.setattr(
        tropical_archive_worker,
        "get_advisory_payload",
        build_cached_advisory,
    )
    monkeypatch.setattr(tropical_service, "get_refresh_coordinator", lambda: coordinator)
    monkeypatch.setattr(tropical_service, "_TROPICAL_ARCHIVE_WARM_TARGETS", {})
    monkeypatch.setattr(tropical_service._time, "sleep", lambda _seconds: None)

    window = tropical_service.start_tropical_archive_warm_data(
        sid,
        mode="window",
        anchor="003",
    )

    assert built == ["004", "002", "005", "001", "003"]
    assert window["mode"] == "window"
    assert window["cached"] == 5
    assert window["total"] == 5
    assert window["complete"] is True

    full = tropical_service.start_tropical_archive_warm_data(
        sid,
        mode="full",
        anchor="003",
    )

    assert built == ["004", "002", "005", "001", "003", "006", "007"]
    assert coordinator.provider_entries == ["nhc"] * 7
    assert full["mode"] == "full"
    assert full["cached"] == 7
    assert full["total"] == 7
    assert full["complete"] is True


def test_archive_warm_window_fills_forward_at_start_of_storm():
    steps = [f"{index:03d}" for index in range(1, 8)]

    assert tropical_service._tropical_archive_window_steps(steps, "001") == [
        "002",
        "003",
        "004",
        "005",
        "001",
    ]


def test_archive_warm_rejects_invalid_mode(tmp_path, monkeypatch):
    storms_dir = tmp_path / "storms"
    _write_old_json(
        storms_dir / "AL012020" / "storm.json",
        {"advisories": ["001"]},
    )
    monkeypatch.setattr(tropical_service, "_TROPICAL_ARCHIVE_STORMS_DIR", storms_dir)

    try:
        tropical_service.start_tropical_archive_warm_data(
            "AL012020",
            mode="everything",
        )
    except tropical_service.HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("invalid archive warm mode was accepted")


def test_archive_advisory_cache_is_atomic_and_deduplicates_concurrent_reads(
    tmp_path,
    monkeypatch,
):
    calls = []

    def build_payload(storm_id, step):
        calls.append((storm_id, step))
        return {"stormId": storm_id, "advisoryStep": step}

    monkeypatch.setattr(tropical_archive_worker, "STORMS_DIR", tmp_path)
    monkeypatch.setattr(
        tropical_archive_worker,
        "_ADVISORY_CACHE_LOCKS",
        {},
    )
    monkeypatch.setattr(
        tropical_archive_worker,
        "build_advisory_payload",
        build_payload,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _index: tropical_archive_worker.get_advisory_payload(
                    "AL012020", "001"
                ),
                range(2),
            )
        )

    cache = tmp_path / "AL012020" / "advisories" / "001.json"
    assert calls == [("AL012020", "001")]
    assert results == [
        {"stormId": "AL012020", "advisoryStep": "001"},
        {"stormId": "AL012020", "advisoryStep": "001"},
    ]
    assert cache.exists()
    assert not cache.with_suffix(".json.tmp").exists()


def test_archive_advisory_issuance_normalizes_to_offset_aware_iso():
    assert tropical_archive_worker.parse_archive_issued_iso(
        "500 PM AST Sun Aug 20 2023"
    ) == "2023-08-20T17:00:00-04:00"
    assert tropical_archive_worker.parse_archive_issued_iso(
        "1100 AM HST Tue Jul 29 2025"
    ) == "2025-07-29T11:00:00-10:00"


def test_cached_archive_advisory_response_adds_authoritative_issuance(
    tmp_path,
    monkeypatch,
):
    storms_dir = tmp_path / "storms"
    cache = storms_dir / "AL082023" / "advisories" / "001.json"
    _write_old_json(cache, {"issued": "500 PM AST Sun Aug 20 2023"})
    monkeypatch.setattr(tropical_service, "_TROPICAL_ARCHIVE_STORMS_DIR", storms_dir)
    monkeypatch.setattr(
        tropical_archive_worker,
        "get_advisory_payload",
        lambda _sid, _step: {"issued": "500 PM AST Sun Aug 20 2023"},
    )

    payload = tropical_service.get_tropical_archive_advisory_data(
        "AL082023",
        "001",
    )

    assert payload["issued_at"] == "2023-08-20T17:00:00-04:00"
