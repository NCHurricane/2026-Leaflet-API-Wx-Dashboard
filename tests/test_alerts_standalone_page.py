from pathlib import Path

from app_core.paths import BASE_DIR
from routes.pages import read_alerts_page


def test_alerts_route_serves_standalone_page():
    response = read_alerts_page()
    expected = Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts.html"

    assert Path(response.path) == expected
    assert expected.exists()


def test_alerts_page_uses_only_new_frontend_boundary():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts.html"
    ).read_text(encoding="utf-8")

    assert "/frontend/core/core.css" in page
    assert "/frontend/pages/alerts/alerts-page.js" in page
    assert "js/weather.js" not in page
    assert "js/alerts-engine.js" not in page
    assert "js/alerts-page.js" not in page


def test_legacy_alerts_paths_are_removed_but_projected_arrival_is_preserved():
    workspace = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.html"
    ).read_text(encoding="utf-8")
    tools = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace-tools.js"
    ).read_text(encoding="utf-8")

    assert 'id="wx-stormtrack-start"' in workspace
    assert 'id="wx-radarcal-start"' not in workspace
    assert "function _activateStormTrackDragProjection" in tools
    assert "_radarCal" not in tools
    assert "setAlerts(features)" in tools


def test_shared_alert_detail_supports_local_storm_reports():
    page_app = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-page.js"
    ).read_text(encoding="utf-8")
    detail = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-detail.js"
    ).read_text(encoding="utf-8")
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-engine.js"
    ).read_text(encoding="utf-8")

    assert "function openLsr(feature)" in detail
    assert "Close storm report detail" in detail
    assert "onLsrDetail: (feature) => detail.openLsr(feature)" in page_app
    assert "onLsrDetail(feature)" in engine
    assert "alerts-hover-tip alerts-lsr-hover-tip" in engine


def test_alerts_cache_rejects_generations_older_than_latest_seen():
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-engine.js"
    ).read_text(encoding="utf-8")

    assert "let latestAlertGeneration = '';" in engine
    assert "version.generation === latestAlertGeneration" in engine
    assert "version.updatedMs > latestAlertUpdatedMs" in engine
    assert (
        "isCurrentAlertPayload(cachedMemoryPayloads) ? cachedMemoryPayloads : null"
        in engine
    )
    assert "isCurrentAlertPayload(persisted)" in engine
    assert "if (!isCurrentAlertPayload(freshPayloads)) return;" in engine


def test_live_alert_refresh_follows_stale_generation_until_publish():
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-engine.js"
    ).read_text(encoding="utf-8")

    assert "liveAlertRefreshRetryDelayMs" in engine
    assert "scheduleLiveRefreshRetry(freshPayloads" in engine
    assert "refreshAttempt: refreshAttempt + 1" in engine
    assert "cancelLiveRefreshRetry();" in engine


def test_new_alert_notifications_ignore_pre_start_and_previously_seen_alerts():
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-engine.js"
    ).read_text(encoding="utf-8")

    assert "const notificationStartedAtMs = Date.now();" in engine
    assert "issuedAfterNotificationStart(feature)" in engine
    assert "issuedMs > notificationStartedAtMs" in engine
    assert "new Set([...(knownAlertIds || []), ...nextIds])" in engine


def test_severe_alert_pulse_is_stroke_only_and_zoom_aware():
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-engine.js"
    ).read_text(encoding="utf-8")
    alerts_styles = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts.css"
    ).read_text(encoding="utf-8")
    workspace_styles = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.css"
    ).read_text(encoding="utf-8")

    assert "zoom >= 9 ? 7 : zoom >= 7 ? 4 : 3" in engine
    assert "map.on('zoomend', syncAlertPulseLayers)" in engine
    assert "map.off('zoomend', syncAlertPulseLayers)" in engine
    for styles in (alerts_styles, workspace_styles):
        assert "fill-opacity: var(--alerts-pulse" not in styles
        assert "stroke-width: var(--alerts-pulse-stroke-high, 7)" in styles


def test_polygon_tooltips_are_hidden_at_zoom_10_and_above_without_hiding_lsr():
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-engine.js"
    ).read_text(encoding="utf-8")
    alerts_styles = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts.css"
    ).read_text(encoding="utf-8")
    workspace_styles = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.css"
    ).read_text(encoding="utf-8")

    assert "Number(options.alertTooltipMinZoom) : 10" in engine
    assert "map.getZoom() >= alertTooltipMinZoom" in engine
    assert "map.on('zoomend', syncAlertTooltipZoom)" in engine
    assert "map.off('zoomend', syncAlertTooltipZoom)" in engine
    for styles in (alerts_styles, workspace_styles):
        assert (
            ".is-alert-tooltip-zoom-suppressed "
            ".leaflet-tooltip.alerts-hover-tip:not(.alerts-lsr-hover-tip)"
        ) in styles
