from pathlib import Path

from app_core import upstream_ledger
from app_core.paths import CACHE_ROOT
from workers import _freshness


def test_default_upstream_ledger_is_under_cache(monkeypatch):
    monkeypatch.delenv("WX_UPSTREAM_LEDGER_PATH", raising=False)

    assert upstream_ledger.ledger_path() == (
        Path(CACHE_ROOT) / "metrics" / "upstream_requests.jsonl"
    )


def test_headless_worker_logs_are_under_cache():
    assert _freshness._LOG_DIR == Path(CACHE_ROOT) / "logs" / "scheduled"
