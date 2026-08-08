from datetime import datetime, timezone

from app_core.http import parse_optional_utc_datetime


def test_optional_iso_parser_normalizes_naive_and_offset_values_to_utc():
    assert parse_optional_utc_datetime("2026-08-08T12:30:00") == datetime(
        2026, 8, 8, 12, 30, tzinfo=timezone.utc
    )
    assert parse_optional_utc_datetime("2026-08-08T08:30:00-04:00") == datetime(
        2026, 8, 8, 12, 30, tzinfo=timezone.utc
    )


def test_optional_iso_parser_rejects_empty_and_malformed_values():
    assert parse_optional_utc_datetime(None) is None
    assert parse_optional_utc_datetime("") is None
    assert parse_optional_utc_datetime("not-a-date") is None
