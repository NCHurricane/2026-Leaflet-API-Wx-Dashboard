from __future__ import annotations

from fastapi.testclient import TestClient

import main
from app_core.refresh_coordinator import get_refresh_coordinator


def test_fastapi_lifespan_starts_and_stops_refresh_coordinator(monkeypatch):
    coordinator = get_refresh_coordinator()
    coordinator.stop()
    monkeypatch.setattr(main, "initialize_runtime", coordinator.start)
    monkeypatch.setattr(main, "shutdown_runtime", coordinator.stop)

    with TestClient(main.app) as client:
        response = client.get("/api/health/coordinator")
        assert response.status_code == 200
        assert response.json()["running"] is True
        assert response.json()["mode"] == "single_process"

    assert coordinator.running is False
