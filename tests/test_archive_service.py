from datetime import datetime, timezone

from services.archive_service import _parse_archive_dt


def test_archive_datetime_accepts_browser_iso_timestamp():
    assert _parse_archive_dt("2026-08-05T20:00:00.000Z") == datetime(
        2026, 8, 5, 20, tzinfo=timezone.utc
    )


def test_archive_datetime_normalizes_offsets_to_utc():
    assert _parse_archive_dt("2026-08-05T16:00:00-04:00") == datetime(
        2026, 8, 5, 20, tzinfo=timezone.utc
    )
