from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app_core import runtime
from routes import health
from services import tropical_service
from workers import optional_warmer, scheduler


class _FakeCoordinator:
    def __init__(self, snapshot: dict | None = None) -> None:
        self._snapshot = snapshot or {}
        self.calls: list[tuple[str, dict]] = []

    def register_periodic(self, **kwargs) -> None:
        self.calls.append(("register_periodic", kwargs))

    def start(self) -> None:
        self.calls.append(("start", {}))

    def snapshot(self) -> dict:
        return self._snapshot


def test_application_maintenance_owns_cache_cleanup() -> None:
    coordinator = _FakeCoordinator()

    runtime._start_application_maintenance(coordinator)

    action, payload = coordinator.calls[0]
    assert action == "register_periodic"
    assert payload["key"] == ("maintenance", "cache-cleanup")
    assert payload["interval_seconds"] == 6 * 60 * 60
    assert coordinator.calls[1] == ("start", {})


def test_scheduler_registers_no_fixed_worker_jobs(capsys) -> None:
    scheduler.start_scheduler()
    assert "no fixed worker schedule registered" in capsys.readouterr().out


def test_health_reports_application_sources_caches_and_maintenance(monkeypatch) -> None:
    coordinator = _FakeCoordinator(
        {
            "mode": "single_process",
            "running": True,
            "active_jobs": 1,
            "periodic_jobs": [["maintenance", "cache-cleanup"]],
            "states": [
                {
                    "key": ["alerts", "national"],
                    "provider": "nws-alerts",
                    "status": "running",
                    "last_success_at": "2026-07-24T12:00:00+00:00",
                }
            ],
        }
    )
    monkeypatch.setattr(health, "get_refresh_coordinator", lambda: coordinator)

    payload = health._coordinator_health_payload()

    assert payload["health_model"] == "application_owned"
    assert payload["sources"]["nws-alerts"]["status"] == "active"
    assert payload["caches"] == payload["states"]
    assert payload["maintenance"] == {
        "cache_cleanup_registered": True,
        "current_season_tropical": "request_driven",
    }


def test_current_season_tropical_refresh_is_request_driven(monkeypatch) -> None:
    class TropicalCoordinator:
        def __init__(self) -> None:
            self.submissions: list[dict] = []

        def record_presence(self, **_kwargs) -> None:
            return None

        def describe(self, _key):
            return None

        def submit(self, **kwargs) -> None:
            self.submissions.append(kwargs)

    coordinator = TropicalCoordinator()
    monkeypatch.setattr(
        tropical_service, "get_refresh_coordinator", lambda: coordinator
    )
    year = str(datetime.now(timezone.utc).year)

    tropical_service._maybe_schedule_current_season_refresh(
        {"seasons": [{"year": year}]}
    )

    assert coordinator.submissions[0]["key"] == (
        "tropical",
        "archive-current-season",
        year,
    )
    assert coordinator.submissions[0]["provider"] == "nhc"


def test_optional_warmer_exposes_supported_outcomes(monkeypatch) -> None:
    target = optional_warmer.WarmerTarget("one", "/test")
    monkeypatch.setitem(optional_warmer.PROFILES, "test", (target,))
    outcomes = iter(("already_running", "current"))
    monkeypatch.setattr(
        optional_warmer,
        "_request_target",
        lambda *_args, **_kwargs: next(outcomes),
    )

    result = optional_warmer.run_profile(
        "test", wait_seconds=0.2, poll_seconds=0.01
    )

    assert result == {
        "profile": "test",
        "outcome": "warmed",
        "targets": {"one": "warmed"},
    }
    assert optional_warmer._classify_payload({"cache_state": "backoff"}) == "backoff"
    assert optional_warmer._classify_payload({"refreshing": True}) == "already_running"
    assert optional_warmer.OUTCOMES == {
        "warmed",
        "current",
        "already_running",
        "backoff",
        "failed",
    }


def test_task_installer_defaults_to_non_mutating_preview() -> None:
    source = Path("tools/install_tasks.ps1").read_text(encoding="utf-8")

    assert "Preview only. No scheduled tasks were changed." in source
    assert "[switch]$InstallOptionalWarmers" in source
    assert "[switch]$UnregisterLegacyTasks" in source
    assert "workers.optional_warmer" in source
    assert "workers.alerts_worker" not in source
