from pathlib import Path
from datetime import datetime, timezone

import app_core.server_session as server_session
import routes.alerts as alerts_routes


BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND = BASE_DIR / "frontend"

NON_WORKSPACE_ENTRIES = (
    "alerts/alerts-page.js",
    "radar/radar-page.js",
    "satellite/satellite-page.js",
    "spc/spc-page.js",
    "surface/surface-page.js",
    "mrms/mrms-page.js",
    "rtma/rtma-page.js",
    "drought/drought-page.js",
    "tropical/tropical-app.js",
    "wpc/wpc-page.js",
    "water/water-app.js",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_every_non_workspace_page_starts_shared_monitor_and_workspace_does_not():
    for relative_path in NON_WORKSPACE_ENTRIES:
        source = _read(FRONTEND / "pages" / relative_path)
        assert "non-workspace-alert-monitor.js?v=20260824a" in source
        assert "startNonWorkspaceAlertMonitor" in source

    workspace = _read(FRONTEND / "pages/workspace/workspace-app.js")
    assert "non-workspace-alert-monitor" not in workspace
    assert "startNonWorkspaceAlertMonitor" not in workspace


def test_shared_monitor_uses_national_feed_deduplication_and_fixed_event_scope():
    monitor = _read(FRONTEND / "core/non-workspace-alert-monitor.js")
    assert "/api/data/alerts?geometry_mode=display&zoom_bucket=low" in monitor
    assert "BroadcastChannel" in monitor
    assert "localStorage" in monitor
    assert "cohortStartedAt" in monitor
    assert "baselineNextPoll" in monitor
    assert "serverStartedAt: payload?._server_started_at" in monitor
    assert "new windowRef.Audio('/sounds/weather_alert.mp3')" in monitor
    assert "cache_ttl_seconds" in monitor
    assert "audio.preload = 'auto'" in monitor
    assert "audio.load()" in monitor
    assert "unlockAudio" in monitor
    for event in (
        "Tornado Warning",
        "Severe Thunderstorm Warning",
        "Flash Flood Warning",
        "Tornado Watch",
        "Severe Thunderstorm Watch",
        "Flash Flood Watch",
    ):
        assert event in monitor
    assert "Special Marine Warning" not in monitor


def test_alerts_api_exposes_current_server_session_boundary(monkeypatch):
    monkeypatch.setattr(
        alerts_routes,
        "get_alerts_data",
        lambda **_kwargs: {"type": "FeatureCollection", "features": []},
    )
    monkeypatch.setattr(
        alerts_routes,
        "server_started_at",
        lambda: "2026-08-14T16:00:00+00:00",
    )

    payload = alerts_routes.get_data_alerts()

    assert payload["_server_started_at"] == "2026-08-14T16:00:00+00:00"


def test_server_session_boundary_is_recorded_as_utc(monkeypatch):
    monkeypatch.setattr(server_session, "_server_started_at", None)
    started = server_session.mark_server_started(
        datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
    )

    assert started == "2026-08-14T12:00:00.000+00:00"
    assert server_session.server_started_at() == started


def test_alerts_page_uses_shared_toggle_and_deep_link_selection():
    page = _read(FRONTEND / "pages/alerts/alerts.html")
    controller = _read(FRONTEND / "pages/alerts/alerts-page.js")
    assert "Shared Alert Notifications" in page
    assert 'name="alerts-shared-notifications"' in page
    assert 'name="alerts-notification-mode"' not in page
    assert 'id="alerts-notifications"' not in page
    assert "sharedAlertFeatureId" in controller
    assert "engine.showSelectedAlert(feature)" in controller
    assert "engine.zoomTo(feature, { maxZoom: 9 })" in controller
    assert "/api/data/alerts?geometry_mode=full&zoom_bucket=high" in controller
    assert "railScope: 'national'" in controller
    assert "window.history.replaceState" in controller
    assert "onNewAlert" not in controller


def test_workspace_resolves_shared_alert_deep_link_without_joining_monitor():
    controller = _read(FRONTEND / "pages/workspace/workspace-app.js")
    assert "new URLSearchParams(window.location.search).get('alert')" in controller
    assert "/api/data/alerts?geometry_mode=full&zoom_bucket=high" in controller
    assert "alertFeatureId(item) === pendingSharedAlertId" in controller
    assert "selectAlert(feature, { maxZoom: 9 })" in controller
    assert "window.history.replaceState" in controller


def test_alert_flash_is_shared_color_aware_and_old_page_copies_are_removed():
    core_css = _read(FRONTEND / "core/core.css")
    assert ".core-alert-monitor-border.is-active" in core_css
    assert "@keyframes core-alert-monitor-border-flash" in core_css
    assert "border-color: var(--core-alert-flash-color)" in core_css
    assert "prefers-reduced-motion: reduce" in core_css

    old_selector = "wx-new-alert-border-flash"
    css_sources = list(FRONTEND.rglob("*.css"))
    assert all(old_selector not in _read(path) for path in css_sources)


def test_shared_core_css_is_cache_busted_on_every_product_page():
    pages = list((FRONTEND / "pages").glob("*/*.html"))
    assert len(pages) == 12
    for page in pages:
        assert "/frontend/core/core.css?v=20260809a" in _read(page)
