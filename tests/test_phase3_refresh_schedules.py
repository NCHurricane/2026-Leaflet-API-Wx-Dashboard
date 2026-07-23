import asyncio
from datetime import datetime, timedelta, timezone

from config.refresh_schedules import (
    GTWO_SCHEDULE,
    SPC_OUTLOOK_SCHEDULES,
    TROPICAL_INTERMEDIATE_SCHEDULE,
    TROPICAL_ROUTINE_SCHEDULE,
    latest_usdm_valid_date,
    wpc_schedule_for,
)
from config.wpc_config import WPC_PRODUCTS
from workers import spc_worker
from workers import tropical_worker
import services.drought_service as drought_service


UTC = timezone.utc


def test_spc_local_clock_boundaries_follow_cst_and_cdt() -> None:
    day2 = SPC_OUTLOOK_SCHEDULES["2_cat"]

    assert day2.latest_boundary(datetime(2026, 1, 15, 7, 5, tzinfo=UTC)) == datetime(
        2026, 1, 15, 7, 0, tzinfo=UTC
    )
    assert day2.latest_boundary(datetime(2026, 7, 15, 6, 5, tzinfo=UTC)) == datetime(
        2026, 7, 15, 6, 0, tzinfo=UTC
    )


def test_spc_grace_retries_until_source_advances() -> None:
    schedule = SPC_OUTLOOK_SCHEDULES["1_cat"]
    now = datetime(2026, 7, 23, 13, 5, tzinfo=UTC)

    assert schedule.refresh_due(
        now=now,
        source_issued_at=datetime(2026, 7, 23, 6, 0, tzinfo=UTC),
        last_checked_at=datetime(2026, 7, 23, 13, 2, tzinfo=UTC),
    )
    assert not schedule.refresh_due(
        now=now,
        source_issued_at=datetime(2026, 7, 23, 13, 0, tzinfo=UTC),
        last_checked_at=None,
    )
    assert not schedule.refresh_due(
        now=now,
        source_issued_at=datetime(2026, 7, 23, 6, 0, tzinfo=UTC),
        last_checked_at=datetime(2026, 7, 23, 13, 4, tzinfo=UTC),
    )


def test_tropical_and_gtwo_boundaries_are_separate() -> None:
    now = datetime(2026, 7, 23, 12, 5, tzinfo=UTC)

    assert TROPICAL_ROUTINE_SCHEDULE.latest_boundary(now) == datetime(
        2026, 7, 23, 9, 0, tzinfo=UTC
    )
    assert TROPICAL_INTERMEDIATE_SCHEDULE.latest_boundary(now) == datetime(
        2026, 7, 23, 12, 0, tzinfo=UTC
    )
    assert GTWO_SCHEDULE.latest_boundary(now) == datetime(
        2026, 7, 23, 12, 0, tzinfo=UTC
    )


def test_wpc_products_do_not_share_one_universal_stale_window() -> None:
    ero = wpc_schedule_for({"id": "ero_day1", "group": "ero", "day": 1})
    qpf = wpc_schedule_for(
        {"id": "qpf48_day4_5", "group": "qpf", "days": (4, 5)}
    )
    mpd = wpc_schedule_for({"id": "mpd_active", "group": "mpd", "days": (1,)})

    assert ero.boundaries != qpf.boundaries
    assert mpd.retry_seconds == 90
    assert mpd.grace_seconds == 120


def test_usdm_latest_key_changes_only_after_official_release() -> None:
    assert latest_usdm_valid_date(
        datetime(2026, 7, 23, 12, 29, tzinfo=UTC)
    ).isoformat() == "2026-07-14"
    assert latest_usdm_valid_date(
        datetime(2026, 7, 23, 12, 30, tzinfo=UTC)
    ).isoformat() == "2026-07-21"


def test_every_spc_and_wpc_registry_boundary_has_a_grace_window() -> None:
    schedules = list(SPC_OUTLOOK_SCHEDULES.values())
    schedules.extend(
        wpc_schedule_for(product)
        for products in WPC_PRODUCTS.values()
        for product in products
    )

    for schedule in schedules:
        for boundary_rule in schedule.boundaries:
            local_boundary = datetime(
                2026,
                7,
                22,
                boundary_rule.hour,
                boundary_rule.minute,
                tzinfo=boundary_rule.timezone,
            )
            boundary = local_boundary.astimezone(UTC)
            assert schedule.refresh_due(
                now=boundary + timedelta(seconds=30),
                source_issued_at=boundary - timedelta(hours=1),
                last_checked_at=boundary - timedelta(minutes=3),
            )


def test_spc_targeted_refresh_ignores_global_sentinel(
    tmp_path,
    monkeypatch,
) -> None:
    calls = []

    def _fetch(day, hazard):
        calls.append((day, hazard))
        return (
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"ISSUE_ISO": "2026-07-23T13:00:00+00:00"},
                        "geometry": None,
                    }
                ],
            },
            "SPC",
        )

    monkeypatch.setattr(spc_worker, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(spc_worker, "is_cache_fresh", lambda *_args: True)
    monkeypatch.setattr("spc.spc_utils.fetch_outlook_geojson", _fetch)
    monkeypatch.setattr("spc.spc_utils.fetch_fire_wx_geojson", _fetch)

    result = spc_worker.run_spc_worker(product_ids={"1_cat"})

    assert calls == [(1, "cat")]
    assert result["products"] == ["1_cat"]
    assert (tmp_path / "1_cat.geojson").is_file()


def test_tropical_gtwo_refresh_does_not_fetch_storm_advisories(
    tmp_path,
    monkeypatch,
) -> None:
    calls = []
    monkeypatch.setattr(tropical_worker, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        tropical_worker,
        "CURRENT_STORMS_FILE",
        tmp_path / "current_storms.json",
    )
    monkeypatch.setattr(tropical_worker, "SUMMARY_FILE", tmp_path / "summary.json")
    tropical_worker.CURRENT_STORMS_FILE.write_text(
        '{"activeStorms":[{"id":"AL012026"}]}',
        encoding="utf-8",
    )

    def _feeds(_force, _raw_dir, **kwargs):
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(tropical_worker, "_fetch_basin_feeds", _feeds)
    monkeypatch.setattr(
        tropical_worker,
        "_fetch_storm",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("storm advisories should not be fetched")
        ),
    )

    result = tropical_worker.run_tropical_worker(scopes={"gtwo"})

    assert calls == [{"include_feeds": False, "include_gtwo": True}]
    assert result["scopes"] == ["gtwo"]


def test_dated_drought_cache_is_immutable(tmp_path, monkeypatch) -> None:
    calls = []

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return b'{"type":"FeatureCollection","features":[]}'

    def _urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        return _Response()

    monkeypatch.setattr(drought_service, "CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(drought_service, "urlopen", _urlopen)

    first = asyncio.run(drought_service.get_drought_geojson("2026-07-14"))
    second = asyncio.run(drought_service.get_drought_geojson("2026-07-14"))

    assert first.body == second.body
    assert len(calls) == 1
