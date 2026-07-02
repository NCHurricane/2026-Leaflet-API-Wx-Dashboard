"""Provider dispatch for Satellite v2.

Routes frame listing and source downloads to the provider module declared in
the platform descriptor (config.satellite_platforms). Call sites should
import from here instead of a concrete provider module.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

from config.satellite_platforms import (
    PROVIDER_AWS_GOES,
    PROVIDER_AWS_HIMAWARI,
    PROVIDER_EUMETSAT,
    platform_descriptor,
)
from satellite_v2 import provider_aws, provider_eumetsat, provider_himawari
from satellite_v2.models import SourceFrame

_PROVIDER_MODULES: dict[str, ModuleType] = {
    PROVIDER_AWS_GOES: provider_aws,
    PROVIDER_AWS_HIMAWARI: provider_himawari,
    PROVIDER_EUMETSAT: provider_eumetsat,
}


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
    return _provider_module(sat_id).download_product_source_frames(
        cache_root=cache_root,
        sat_id=sat_id,
        sector=sector,
        channel_key=channel_key,
        frame=frame,
    )
