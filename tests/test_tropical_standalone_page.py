from pathlib import Path

from app_core.paths import BASE_DIR
from routes.pages import read_tropical_page


def test_tropical_route_serves_standalone_page():
    response = read_tropical_page()
    expected = Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical.html"

    assert Path(response.path) == expected
    assert expected.exists()


def test_tropical_page_uses_only_new_frontend_boundary():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical.html"
    ).read_text(encoding="utf-8")

    assert "/frontend/core/core.css" in page
    assert "/frontend/pages/tropical/tropical-engine.js" in page
    assert "/frontend/pages/tropical/tropical-controller.js" in page
    assert "/frontend/pages/tropical/tropical-app.js" in page
    assert "js/weather.js" not in page
    assert "js/tropical-engine.js" not in page
    assert "js/tropical-page.js" not in page
    assert "css/dashboard.css" not in page


def test_tropical_page_contains_required_workspace_targets():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical.html"
    ).read_text(encoding="utf-8")

    for target_id in (
        "weather-map",
        "tropical-panel-live",
        "tropical-panel-archive",
        "weather-tropical-system-cards",
        "tropical-system-inspector",
        "tropical-system-close",
        "tropical-system-open",
        "weather-tropical-inspector",
        "tropical-city-density",
        "tropical-city-font-size",
        "wx-archive-season",
        "wx-tropical-adv-scrubber",
    ):
        assert f'id="{target_id}"' in page

    assert 'id="tropical-system-tab"' not in page
    assert 'data-sidebar-tab="live"' in page
    assert 'data-sidebar-tab="archive"' in page
    assert page.count("data-live-basin=") == 4
    assert 'data-live-basin="WORLD" aria-pressed="true"' in page


def test_tropical_live_filter_does_not_auto_select_first_storm():
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical-engine.js"
    ).read_text(encoding="utf-8")

    assert "context.filterStorms" in engine
    assert "context.clearFilteredStorm" in engine
    assert "context.renderActiveStorms" in engine
    assert "featuredStormId" not in engine


def test_tropical_live_basin_pills_are_single_select():
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical-app.js"
    ).read_text(encoding="utf-8")

    assert "_selectedTropicalBasins = new Set([basin]);" in app
    assert "_selectedTropicalBasins.size === 1" in app
    assert "_selectedTropicalBasins.has(basin)" in app


def test_tropical_archive_tab_clears_live_map_context():
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical-app.js"
    ).read_text(encoding="utf-8")

    assert "core:sidebar-tab-change" in app
    assert "if (tab === 'archive')" in app
    assert "_clearActiveSystemsOverview();" in app
    assert "_clearTropicalOutlookLayer();" in app
    assert "_setTropicalMapViewMode('none');" in app


def test_tropical_advisory_scrubber_serializes_source_reads():
    controller = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical-controller.js"
    ).read_text(encoding="utf-8")

    assert "archiveScrubLoading" in controller
    assert "archiveScrubPending = { index, options };" in controller
    assert "async function requestArchiveScrubIndex" in controller
    assert "if (archiveMode === 'advisory' && archiveScrubLoading)" in controller
    assert "slider.disabled = false;" in controller
    assert "pending.index !== archiveScrubIndex()" in controller
    assert "byId('adv-scrub-slider')?.addEventListener('input'" in controller


def test_tropical_archive_warming_is_bounded_and_progressive():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical.html"
    ).read_text(encoding="utf-8")
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical-app.js"
    ).read_text(encoding="utf-8")
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical-engine.js"
    ).read_text(encoding="utf-8")
    controller = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical-controller.js"
    ).read_text(encoding="utf-8")

    assert 'id="wx-archive-warm-status"' in page
    assert "_startTropicalArchiveWarm" in app
    assert "Warm status unavailable" in app
    assert "context.startArchiveWarm('window', data.advisories[0]);" in engine
    assert "startArchiveWarm(\n                'full'" in controller


def test_tropical_archive_global_timestamp_uses_product_time():
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical-app.js"
    ).read_text(encoding="utf-8")

    assert "status.clear();" in app
    assert "function _archiveFixTimestamp(feature)" in app
    assert "feature?.properties?.DTG" in app
    assert "const issuedAt = advisory.issued_at || null;" in app
    assert "base.updated || Date.now()" not in app


def test_tropical_legend_uses_refactored_core_shell():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical.html"
    ).read_text(encoding="utf-8")
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical-app.js"
    ).read_text(encoding="utf-8")

    assert 'class="tropical-legend" data-legend-align="left" hidden' in page
    assert 'class="core-legend-header"' in app
    assert 'class="core-legend-provider">NHC' in app
    assert 'class="core-legend-body"' in app


def test_tropical_archive_scrubber_is_anchored_to_map_bottom():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical.html"
    ).read_text(encoding="utf-8")
    styles = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical.css"
    ).read_text(encoding="utf-8")

    assert '<div id="wx-tropical-adv-scrubber" hidden>' in page
    assert ".weather-map-wrap > #wx-tropical-adv-scrubber" in styles
    assert "position: absolute;" in styles
    assert "bottom: 8px;" in styles
