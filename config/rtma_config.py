"""RTMA UI/worker configuration.

Users can customize RTMA products here to control which products are prewarmed
and shown in RTMA scrubber workflows. Enabling more products increases worker
runtime and cache size.
"""

from __future__ import annotations

RTMA_STREAM_MAX_HOURS: dict[str, int] = {
    "rtma_hourly": 24,
    "rtma_rapid_update": 6,
}

RTMA_STREAMS: tuple[str, ...] = tuple(RTMA_STREAM_MAX_HOURS.keys())

RTMA_WORKER_REGIONS: tuple[str, ...] = ("CONUS", "AK", "HI", "PR")

# Keep this list aligned to available RTMA UI products.
RTMA_UI_PRODUCTS: list[str] = [
    "temperature",
    "temperature_change_24h",
    "dew_point",
    "surface_pressure",
    "wind_speed",
    "wind_gust",
    "wind_direction",
    "visibility",
    "total_cloud_cover",
]


def clamp_stream_hours(stream: str, requested_hours: int | None = None) -> int:
    """Clamp lookback to per-stream maximum hours."""
    max_hours = int(RTMA_STREAM_MAX_HOURS.get(stream, 24))
    if requested_hours is None:
        return max_hours
    return max(1, min(int(requested_hours), max_hours))
