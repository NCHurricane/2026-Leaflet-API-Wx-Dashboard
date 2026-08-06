from pathlib import Path

from app_core import upstream_ledger
from app_core.paths import CACHE_ROOT
from workers import _freshness
from workers import cache_cleanup_worker


def test_default_upstream_ledger_is_under_cache(monkeypatch):
    monkeypatch.delenv("WX_UPSTREAM_LEDGER_PATH", raising=False)

    assert upstream_ledger.ledger_path() == (
        Path(CACHE_ROOT) / "metrics" / "upstream_requests.jsonl"
    )


def test_upstream_ledger_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("WX_UPSTREAM_LEDGER", raising=False)
    monkeypatch.delenv("WX_UPSTREAM_LEDGER_PATH", raising=False)

    assert upstream_ledger._enabled() is False


def test_upstream_ledger_path_explicitly_enables_measurement(monkeypatch, tmp_path):
    monkeypatch.delenv("WX_UPSTREAM_LEDGER", raising=False)
    monkeypatch.setenv("WX_UPSTREAM_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))

    assert upstream_ledger._enabled() is True


def test_headless_worker_logs_are_under_cache():
    assert _freshness._LOG_DIR == Path(CACHE_ROOT) / "logs" / "scheduled"


def test_worker_log_rotation_keeps_one_backup(tmp_path):
    log_path = tmp_path / "worker.log"
    backup_path = tmp_path / "worker.log.1"
    backup_path.write_text("older", encoding="utf-8")
    log_path.write_text("current log", encoding="utf-8")

    assert _freshness._rotate_log_if_needed(log_path, 5) is True
    assert not log_path.exists()
    assert backup_path.read_text(encoding="utf-8") == "current log"


def test_generated_diagnostics_have_bounded_retention():
    policies = dict(cache_cleanup_worker._RETENTION_POLICIES)

    assert policies["archive"] == 7 * 24
    assert policies["logs"] == 7 * 24
    assert policies["metrics"] == 7 * 24
