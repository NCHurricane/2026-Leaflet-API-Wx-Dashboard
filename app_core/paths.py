"""Filesystem paths and runtime directory setup for the app."""

from pathlib import Path

BASE_PATH = Path(__file__).resolve().parent.parent
BASE_DIR = str(BASE_PATH)
CACHE_ROOT = str(BASE_PATH / "cache")

_CACHE_SUBDIRS = (
    "alerts",
    "spc",
    "surface",
    "mrms",
    "rtma",
    "archive",
    "radar",
    "satellite",
)


def ensure_runtime_dirs() -> None:
    """Create cache directories expected by app routes and workers."""
    cache_root = Path(CACHE_ROOT)
    for subdir in _CACHE_SUBDIRS:
        (cache_root / subdir).mkdir(parents=True, exist_ok=True)
