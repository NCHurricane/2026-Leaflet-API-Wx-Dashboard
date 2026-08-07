from datetime import datetime, timezone

from fastapi import HTTPException
import pandas as pd
import pytest

import services.archive_service as archive_service
from services.archive_service import _parse_archive_dt


def test_archive_datetime_accepts_browser_iso_timestamp():
    assert _parse_archive_dt("2026-08-05T20:00:00.000Z") == datetime(
        2026, 8, 5, 20, tzinfo=timezone.utc
    )


def test_archive_datetime_normalizes_offsets_to_utc():
    assert _parse_archive_dt("2026-08-05T16:00:00-04:00") == datetime(
        2026, 8, 5, 20, tzinfo=timezone.utc
    )


def _surface_archive_frame(source: str, temperature: float) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "station_id": ["KAVL"],
            "name": ["Asheville Regional Airport"],
            "network": ["ASOS"],
            "latitude": [35.44],
            "longitude": [-82.54],
            "air_temperature": [temperature],
        }
    )
    frame.attrs["surface_source"] = source
    return frame


def test_surface_archive_reports_per_frame_and_mixed_actual_provenance(
    tmp_path, monkeypatch
):
    frames = [
        _surface_archive_frame("awc", 70.0),
        _surface_archive_frame("iem", 71.0),
    ]
    monkeypatch.setattr(archive_service, "_ARCHIVE_JSON_DIR", str(tmp_path))
    monkeypatch.setattr(
        archive_service,
        "fetch_surface_archive_frames",
        lambda *_args, **_kwargs: frames,
    )

    result = archive_service.get_archive_surface(
        region="NC",
        product="temperature",
        date_from="2026-08-07T12:00:00Z",
        date_to="2026-08-07T12:15:00Z",
        max_frames=2,
        source="iem",
    )

    assert result["source"] == "mixed"
    assert [frame["source"] for frame in result["frames"]] == ["awc", "iem"]
    assert [frame["stations"][0]["value"] for frame in result["frames"]] == [
        70.0,
        71.0,
    ]


def test_surface_archive_rejects_unsupported_source():
    with pytest.raises(HTTPException) as exc_info:
        archive_service.get_archive_surface(
            date_from="2026-08-07T12:00:00Z",
            date_to="2026-08-07T12:15:00Z",
            source="nws",
        )

    assert exc_info.value.status_code == 400
    assert "source must be 'auto' or 'iem'" in exc_info.value.detail


def test_surface_archive_rejects_unsupported_historical_world():
    with pytest.raises(HTTPException) as exc_info:
        archive_service.get_archive_surface(
            region="WORLD",
            date_from="2026-08-07T12:00:00Z",
            date_to="2026-08-07T12:15:00Z",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Historical WORLD surface archive is not supported."
