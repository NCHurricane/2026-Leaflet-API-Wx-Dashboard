from pathlib import Path

import pytest
from fastapi import HTTPException

from services import spc_service
from workers.tropical_worker import _storm_graphics


BASE_DIR = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (BASE_DIR / relative_path).read_text(encoding="utf-8")


def test_empty_status_timestamp_does_not_render_unix_epoch() -> None:
    status = _read("frontend/core/status.js")

    assert "if (value == null || value === '') return '—';" in status


def test_spc_watch_empty_state_and_fire_day_product_split() -> None:
    engine = _read("frontend/pages/spc/spc-engine.js")
    page = _read("frontend/pages/spc/spc-page.js")

    assert "No active tornado or severe thunderstorm watches." in engine
    assert "const categorical = row.dataset.categorical === '1';" in page
    assert "categorical ? fireDay >= 3 && fireDay <= 8 : fireDay <= 2" in page
    assert "input.disabled = !visible;" in page


def test_spc_and_tropical_poll_background_refreshes() -> None:
    spc_engine = _read("frontend/pages/spc/spc-engine.js")
    tropical_engine = _read("frontend/pages/tropical/tropical-engine.js")
    tropical_app = _read("frontend/pages/tropical/tropical-app.js")

    assert "geojson?.cache_state === 'refreshing'" in spc_engine
    assert "refreshAttempt: refreshAttempt + 1" in spc_engine
    assert "Warming SPC Day" in spc_engine
    assert "SPC outlook issued" in spc_engine
    assert "STALE_CACHE_STATES.has" in spc_engine
    assert "STALE_THRESHOLD_MS" not in spc_engine
    assert "if (data.refreshing && refreshAttempt < 30)" in tropical_engine
    assert "loadStorms(false, refreshAttempt + 1)" in tropical_engine
    engine_context = tropical_app.split(
        "_tropicalEngine = _tropicalEngineFactory.createTropicalEngine({", 1
    )[1]
    assert "setTimeoutFn: (callback, delay) => setTimeout(callback, delay)," in engine_context


def test_surface_refresh_polling_honors_coordinator_retry_delay() -> None:
    engine = _read("frontend/pages/surface/surface-engine.js")

    assert "refreshPollDelayMs(data)" in engine
    assert "data?.retry_after_seconds" in engine
    assert "REFRESH_POLL_BUDGET_MS" in engine


def test_wpc_polls_cold_and_stale_background_refreshes() -> None:
    wpc_engine = _read("frontend/pages/wpc/wpc-engine.js")

    assert (
        "['refreshing', 'stale_refreshing'].includes(geojson.cache_state)"
        in wpc_engine
    )
    assert "refreshAttempt: refreshAttempt + 1" in wpc_engine


@pytest.mark.parametrize("hazard", ["windrh", "dryt"])
def test_spc_rejects_day_3_8_base_fire_products(hazard: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        spc_service.get_spc_outlook(day=3, hazard=hazard)

    assert exc_info.value.status_code == 400


def test_wpc_grouped_products_start_unselected_and_only_direct_groups_autoload() -> None:
    page = _read("frontend/pages/wpc/wpc-page.js")
    html = _read("frontend/pages/wpc/wpc.html")

    assert "eroDay: null" in page
    assert "qpf6hrIndex: -1" in page
    assert "sigwxId: ''" in page
    assert "forecastIndex: -1" in page
    assert "if (!canLoadSelection())" in page
    assert "if (['fop', 'surface'].includes(state.group)) reload();" in page
    assert "input.type = 'checkbox';" in page
    assert "state[stateKey] = e.target.checked ? e.target.value : '';" in page
    assert 'id="wpc-fop-toggle"' in html
    assert 'id="wpc-mpd-toggle"' in html
    assert 'id="wpc-surface-toggle"' in html


def test_wpc_sigwx_has_specific_legend_and_issued_empty_state() -> None:
    engine = _read("frontend/pages/wpc/wpc-engine.js")

    assert "if (group === 'sigwx')" in engine
    assert "geojson.issued_text" in engine
    assert "geojson.valid_text" in engine
    assert "Significant Weather" in engine


def test_drought_selected_date_uses_project_amber_style() -> None:
    css = _read("frontend/pages/drought/drought.css")

    assert ".drought-date-button.is-active" in css
    assert "background: #facc15;" in css
    assert "color: #211900;" in css


def test_tropical_standard_cones_use_current_nhc_filenames() -> None:
    graphics = _storm_graphics("EP062026")
    urls = {graphic["label"]: graphic["url"] for graphic in graphics}

    assert urls["3-Day Cone"].endswith("/EP062026_3day_cone_sm2.png")
    assert urls["5-Day Cone"].endswith("/EP062026_5day_cone_sm2.png")
    assert all("cone_no_line_and_wind" not in url for url in urls.values())
