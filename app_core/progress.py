"""Shared progress state for long-running endpoint tasks."""

from typing import Any

active_tasks: dict[str, dict[str, Any]] = {}
