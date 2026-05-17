"""Data models for Satellite v2 manifests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


@dataclass(frozen=True)
class SourceFrame:
    frame_key: str
    timestamp_utc: str
    provider: str
    source_key: str
    source_url: str
    file_size: int | None = None
    source_keys: dict[str, str] = field(default_factory=dict)
    source_urls: dict[str, str] = field(default_factory=dict)
    file_sizes: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_key": self.frame_key,
            "timestamp_utc": self.timestamp_utc,
            "provider": self.provider,
            "source_key": self.source_key,
            "source_url": self.source_url,
            "file_size": self.file_size,
            "source_keys": self.source_keys,
            "source_urls": self.source_urls,
            "file_sizes": self.file_sizes,
        }


@dataclass
class CatalogFrame:
    frame_key: str
    timestamp_utc: str
    provider: str
    source_key: str
    source_url: str
    source_keys: dict[str, str] = field(default_factory=dict)
    source_urls: dict[str, str] = field(default_factory=dict)
    file_sizes: dict[str, int] = field(default_factory=dict)
    available_zooms: list[int] = field(default_factory=list)
    tile_counts: dict[str, int] = field(default_factory=dict)
    max_native_zoom: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_key": self.frame_key,
            "timestamp_utc": self.timestamp_utc,
            "provider": self.provider,
            "source_key": self.source_key,
            "source_url": self.source_url,
            "source_keys": self.source_keys,
            "source_urls": self.source_urls,
            "file_sizes": self.file_sizes,
            "available_zooms": self.available_zooms,
            "tile_counts": self.tile_counts,
            "max_native_zoom": self.max_native_zoom,
        }
