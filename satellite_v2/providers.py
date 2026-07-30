"""Provider dispatch for Satellite v2.

Routes frame listing and source downloads to the provider module declared in
the platform descriptor (config.satellite_platforms). Call sites should
import from here instead of a concrete provider module.
"""

from __future__ import annotations

from pathlib import Path
import threading
from types import ModuleType

from config.satellite_platforms import (
    PROVIDER_AWS_GK2A,
    PROVIDER_AWS_GOES,
    PROVIDER_AWS_HIMAWARI,
    PROVIDER_EUMETSAT,
    platform_descriptor,
)
from satellite_v2 import (
    provider_aws,
    provider_eumetsat,
    provider_gk2a,
    provider_himawari,
)
from satellite_v2.models import SourceFrame

_PROVIDER_MODULES: dict[str, ModuleType] = {
    PROVIDER_AWS_GOES: provider_aws,
    PROVIDER_AWS_GK2A: provider_gk2a,
    PROVIDER_AWS_HIMAWARI: provider_himawari,
    PROVIDER_EUMETSAT: provider_eumetsat,
}
_SOURCE_DOWNLOAD_LOCKS: dict[tuple[str, ...], threading.Lock] = {}
_SOURCE_DOWNLOAD_LOCKS_GUARD = threading.Lock()


def provider_capability(sat_id: str) -> dict[str, str]:
    descriptor = platform_descriptor(sat_id)
    provider = str(descriptor.get("provider") or "")
    if provider == PROVIDER_EUMETSAT and not provider_eumetsat.credentials_available():
        return {
            "status": "credentials_required",
            "provider": provider,
            "message": (
                "EUMETSAT credentials are required for this platform. Configure "
                "the consumer key and secret after accepting the applicable licence."
            ),
        }
    return {"status": "available", "provider": provider, "message": ""}


def classify_provider_error(sat_id: str, error: Exception) -> dict[str, str] | None:
    capability = provider_capability(sat_id)
    if capability["status"] != "available":
        return capability
    if capability["provider"] != PROVIDER_EUMETSAT:
        return None
    text = str(error).lower()
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code == 403 or "403" in text or "licen" in text or "terms" in text:
        return {
            "status": "license_required",
            "provider": PROVIDER_EUMETSAT,
            "message": (
                "EUMETSAT access is configured, but this product requires an "
                "accepted data licence or additional account permission."
            ),
        }
    return None


def _source_download_lock(key: tuple[str, ...]) -> threading.Lock:
    with _SOURCE_DOWNLOAD_LOCKS_GUARD:
        lock = _SOURCE_DOWNLOAD_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _SOURCE_DOWNLOAD_LOCKS[key] = lock
        if len(_SOURCE_DOWNLOAD_LOCKS) > 256:
            for old_key, old_lock in list(_SOURCE_DOWNLOAD_LOCKS.items()):
                if old_key != key and not old_lock.locked():
                    _SOURCE_DOWNLOAD_LOCKS.pop(old_key, None)
                if len(_SOURCE_DOWNLOAD_LOCKS) <= 256:
                    break
        return lock


def _provider_module(sat_id: str) -> ModuleType:
    provider = str(platform_descriptor(sat_id).get("provider") or "")
    module = _PROVIDER_MODULES.get(provider)
    if module is None:
        raise ValueError(
            f"Satellite platform '{sat_id}' has no implemented provider "
            f"('{provider}')."
        )
    return module


def list_recent_frames(
    sat_id: str,
    sector: str,
    channel_key: str,
    hours: int,
    max_frames: int,
) -> list[SourceFrame]:
    return _provider_module(sat_id).list_recent_frames(
        sat_id=sat_id,
        sector=sector,
        channel_key=channel_key,
        hours=hours,
        max_frames=max_frames,
    )


def download_product_source_frames(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    channel_key: str,
    frame: SourceFrame | dict,
) -> dict[str, Path]:
    frame_key = str(
        frame.frame_key if isinstance(frame, SourceFrame) else frame.get("frame_key")
    )
    key = (
        str(Path(cache_root).resolve()),
        str(sat_id).strip().lower(),
        str(sector).strip().upper(),
        frame_key,
    )
    with _source_download_lock(key):
        return _provider_module(sat_id).download_product_source_frames(
            cache_root=cache_root,
            sat_id=sat_id,
            sector=sector,
            channel_key=channel_key,
            frame=frame,
        )
