import * as api from '../../core/api.js';
import { createLegendHost } from '../../core/legend.js';
import { createMapCore, REGION_LABELS } from '../../core/map-core.js';
import { renderProductNav } from '../../core/nav.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { loadDefaultSettings, loadPageSettings } from '../../core/settings.js';
import { createStatusReporter } from '../../core/status.js?v=20260725e';
import { createSpcDetailPanel } from './spc-detail.js';
import {
    CIG_OVERLAY_BY_HAZARD,
    allowedConvectiveHazards,
    convectiveLabel,
    createSpcEngine,
} from './spc-engine.js?v=20260725e';
import { createSpcRenderer } from './spc-render.js';

const byId = (id) => document.getElementById(id);
const SELECT_PRODUCT_MESSAGE = 'Select an SPC product to load outlooks.';
const AUTO_REFRESH_MS = 60_000;
const BASE_HAZARDS = ['cat', 'torn', 'wind', 'hail'];

// ── Selection readers ───────────────────────────────────────────────────────
function getDay() {
    return parseInt(byId('spc-day')?.value || '1', 10);
}

function getFireDay() {
    return parseInt(byId('spc-fire-day')?.value || '1', 10);
}

function checkedConvectiveHazards() {
    return [...document.querySelectorAll('.spc-convective-toggle:checked')].map((el) => el.value);
}

function checkedFireHazards() {
    return [...document.querySelectorAll('.spc-fire-toggle:checked')].map((el) => el.value);
}

function selectedHazards(day = getDay()) {
    const fireHazards = checkedFireHazards();
    if (fireHazards.length) return fireHazards;
    const allowed = new Set(allowedConvectiveHazards(day));
    return checkedConvectiveHazards().filter((hazard) => allowed.has(hazard));
}

function supplementalSelections() {
    const reportsDays = [];
    if (byId('spc-reports-today')?.checked) reportsDays.push('today');
    if (byId('spc-reports-yesterday')?.checked) reportsDays.push('yesterday');
    const reportTypes = [];
    if (byId('spc-report-type-torn')?.checked) reportTypes.push('torn');
    if (byId('spc-report-type-wind')?.checked) reportTypes.push('wind');
    if (byId('spc-report-type-hail')?.checked) reportTypes.push('hail');
    const watchLayers = [];
    if (byId('spc-watch-tor-polygon')?.checked) watchLayers.push({ type: 'tor', mode: 'polygon' });
    else if (byId('spc-watch-tor-counties')?.checked) watchLayers.push({ type: 'tor', mode: 'counties' });
    if (byId('spc-watch-svr-polygon')?.checked) watchLayers.push({ type: 'svr', mode: 'polygon' });
    else if (byId('spc-watch-svr-counties')?.checked) watchLayers.push({ type: 'svr', mode: 'counties' });
    return {
        reportsEnabled: reportsDays.length > 0 && reportTypes.length > 0,
        reportsDays,
        reportTypes,
        mdsEnabled: !!byId('spc-show-mds')?.checked,
        watchesEnabled: watchLayers.length > 0,
        watchLayers,
    };
}

function currentSelection() {
    const day = getDay();
    return {
        day,
        fireDay: getFireDay(),
        hazards: selectedHazards(day),
        supplemental: supplementalSelections(),
    };
}

function hasAnySelection(selection) {
    return selection.hazards.length > 0
        || selection.supplemental.reportsEnabled
        || selection.supplemental.mdsEnabled
        || selection.supplemental.watchesEnabled;
}

// ── Exclusive product families ──────────────────────────────────────────────
// Only one SPC family renders at a time: convective outlooks, fire weather
// outlooks, watches, MDs, or storm reports.
function clearConvectiveSelections() {
    document.querySelectorAll('.spc-convective-toggle').forEach((el) => { el.checked = false; });
}

function clearWatchSelections() {
    ['spc-watch-tor-polygon', 'spc-watch-tor-counties', 'spc-watch-svr-polygon', 'spc-watch-svr-counties']
        .forEach((id) => { const el = byId(id); if (el) el.checked = false; });
}

function clearMdSelection() {
    const el = byId('spc-show-mds');
    if (el) el.checked = false;
}

function updateReportFilterState() {
    const hasReportDay = !!byId('spc-reports-today')?.checked || !!byId('spc-reports-yesterday')?.checked;
    ['spc-report-type-torn', 'spc-report-type-wind', 'spc-report-type-hail'].forEach((filterId) => {
        const filterEl = byId(filterId);
        if (!filterEl) return;
        if (!hasReportDay) filterEl.checked = false;
        filterEl.disabled = !hasReportDay;
    });
}

function clearReportSelections() {
    ['spc-reports-today', 'spc-reports-yesterday'].forEach((id) => {
        const el = byId(id);
        if (el) el.checked = false;
    });
    updateReportFilterState();
}

function clearFireSelections(keepTarget = null) {
    document.querySelectorAll('.spc-fire-toggle').forEach((el) => {
        if (keepTarget && el === keepTarget) return;
        el.checked = false;
    });
}

function clearExclusivePeers(group, options = {}) {
    if (group !== 'convective') clearConvectiveSelections();
    if (group !== 'watches') clearWatchSelections();
    if (group !== 'mds') clearMdSelection();
    if (group !== 'reports') clearReportSelections();
    if (group !== 'fire') clearFireSelections(options.keepFireTarget || null);
}

// ── Day-dependent option visibility ─────────────────────────────────────────
function syncConvectiveOptions(resetSelection = false) {
    const day = getDay();
    const allowed = new Set(allowedConvectiveHazards(day));
    const cigParents = Object.fromEntries(
        Object.entries(CIG_OVERLAY_BY_HAZARD).map(([base, cig]) => [cig, base]),
    );
    const checked = new Set(checkedConvectiveHazards());
    document.querySelectorAll('.spc-convective-row').forEach((row) => {
        const hazard = row.dataset.hazard || '';
        const parentHazard = cigParents[hazard] || null;
        const dependencyMet = !parentHazard || checked.has(parentHazard);
        const visible = allowed.has(hazard);
        const enabled = visible && dependencyMet;
        row.style.display = visible ? '' : 'none';
        row.style.opacity = enabled ? '' : '0.55';
        const input = row.querySelector('.spc-convective-toggle');
        if (input) {
            input.disabled = !enabled;
            if (!enabled) input.checked = false;
            else if (resetSelection) input.checked = false;
        }
        const label = row.querySelector('.spc-convective-label');
        if (label) label.textContent = convectiveLabel(hazard, day);
    });
    if (resetSelection) {
        document.querySelectorAll('.spc-fire-toggle').forEach((el) => { el.checked = false; });
    }
}

function syncFireWeatherOptions(resetSelection = false) {
    const fireDay = getFireDay();
    const fireList = byId('spc-fire-list');
    if (!fireList) return;
    // Base products exist on Days 1-2; categorical/probabilistic products
    // replace them on Days 3-8.
    fireList.querySelectorAll('.spc-fire-row').forEach((row) => {
        const categorical = row.dataset.categorical === '1';
        const visible = categorical ? fireDay >= 3 && fireDay <= 8 : fireDay <= 2;
        row.style.display = visible ? '' : 'none';
        const input = row.querySelector('input[type="checkbox"]');
        if (input) {
            input.disabled = !visible;
            if (!visible) input.checked = false;
        }
    });
    if (resetSelection) {
        fireList.querySelectorAll('.spc-fire-toggle').forEach((el) => { el.checked = false; });
    }
}

function hasActiveSupplementalSelections() {
    const supplemental = supplementalSelections();
    return supplemental.reportsEnabled || supplemental.mdsEnabled || supplemental.watchesEnabled;
}

function shouldResetConvectiveDaySelection() {
    return !checkedFireHazards().length && !hasActiveSupplementalSelections();
}

function shouldResetFireDaySelection() {
    return !checkedConvectiveHazards().length && !hasActiveSupplementalSelections();
}

async function initialize() {
    renderProductNav(byId('product-nav'), 'SPC');
    const sidebarTabs = createSidebarTabs(byId('spc-sidebar-tabs'), { defaultTab: 'live' });
    const settings = await loadPageSettings('spc', { mapView: 'CONUS', autoLoad: false });
    const defaults = await loadDefaultSettings().catch(() => ({}));
    const cityDefaults = defaults?.global?.cityLabels || {};
    const regionSelect = byId('spc-region');
    regionSelect.replaceChildren(...Object.entries(REGION_LABELS).map(([code, label]) => {
        const option = document.createElement('option');
        option.value = code;
        option.textContent = label;
        return option;
    }));
    regionSelect.value = REGION_LABELS[settings.mapView] ? settings.mapView : 'CONUS';

    const mapCore = createMapCore(byId('spc-map'), {
        region: regionSelect.value,
        basemap: 'Dark (No Labels)',
    });
    const legend = createLegendHost(byId('spc-legend'), { align: 'left' });
    const status = createStatusReporter({
        globalTimestamp: byId('global-timestamp'),
        message: byId('spc-message'),
        updated: byId('spc-updated'),
        age: byId('spc-age'),
        provider: byId('spc-provider'),
        source: byId('spc-source'),
    });
    const detail = createSpcDetailPanel(byId('spc-map-wrap'), mapCore, {
        zoomToFeature: (feat) => renderer.zoomToFeature(feat),
    });
    const renderer = createSpcRenderer(mapCore, {
        onOutlookDetail: (latlng, feat, context) => detail.openOutlook(latlng, feat, context),
        onTextDetail: (latlng, feat) => detail.openText(latlng, feat),
    });
    const emptyOverlay = byId('spc-map-empty');
    const engine = createSpcEngine({
        api,
        renderer,
        legend,
        status,
        onCount: (count) => { byId('spc-feature-count').textContent = String(count); },
        onEmptyMessage: (msg) => {
            emptyOverlay.textContent = msg || '';
            emptyOverlay.hidden = !msg;
        },
    });

    async function loadActive({ keepDetail = false } = {}) {
        if (!keepDetail) detail.close();
        const selection = currentSelection();
        if (!hasAnySelection(selection)) {
            engine.clear();
            status.setMessage(SELECT_PRODUCT_MESSAGE);
            return;
        }
        try {
            await engine.load(selection);
        } catch (error) {
            console.error('[spc] load failed', error);
        }
    }

    // ── SPC product-group subtabs (Outlooks / Watches / Reports+MDs / Fire) ──
    const subtabButtons = [...document.querySelectorAll('.spc-subtab-button')];
    function setSubtab(tabKey) {
        detail.close();
        const selectedKey = subtabButtons.some((button) => button.dataset.spcSubtab === tabKey)
            ? tabKey : 'outlooks';
        subtabButtons.forEach((button) => {
            const isSelected = button.dataset.spcSubtab === selectedKey;
            button.setAttribute('aria-selected', isSelected ? 'true' : 'false');
            button.tabIndex = isSelected ? 0 : -1;
        });
        document.querySelectorAll('.spc-subtab-panel').forEach((panel) => {
            panel.classList.toggle('is-active', panel.dataset.spcPanel === selectedKey);
        });
    }

    function syncSubtabForSelection(preferredTab = null) {
        if (preferredTab) {
            setSubtab(preferredTab);
            return;
        }
        const supplemental = supplementalSelections();
        if (checkedFireHazards().length) setSubtab('fire');
        else if (supplemental.watchesEnabled) setSubtab('watches');
        else if (supplemental.reportsEnabled || supplemental.mdsEnabled) setSubtab('reports');
        else setSubtab('outlooks');
    }

    subtabButtons.forEach((button, index) => {
        button.addEventListener('click', () => setSubtab(button.dataset.spcSubtab || 'outlooks'));
        button.addEventListener('keydown', (event) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault();
            let nextIndex = index;
            if (event.key === 'ArrowLeft') nextIndex = index === 0 ? subtabButtons.length - 1 : index - 1;
            if (event.key === 'ArrowRight') nextIndex = index === subtabButtons.length - 1 ? 0 : index + 1;
            if (event.key === 'Home') nextIndex = 0;
            if (event.key === 'End') nextIndex = subtabButtons.length - 1;
            const nextButton = subtabButtons[nextIndex];
            if (!nextButton) return;
            setSubtab(nextButton.dataset.spcSubtab || 'outlooks');
            nextButton.focus();
        });
    });

    // ── Day selects ──────────────────────────────────────────────────────────
    byId('spc-day').addEventListener('change', () => {
        syncConvectiveOptions(shouldResetConvectiveDaySelection());
        syncSubtabForSelection('outlooks');
        void loadActive();
    });
    byId('spc-fire-day').addEventListener('change', () => {
        syncFireWeatherOptions(shouldResetFireDaySelection());
        syncSubtabForSelection('fire');
        void loadActive();
    });

    // ── Convective hazard toggles ────────────────────────────────────────────
    document.querySelectorAll('.spc-convective-toggle').forEach((el) => {
        el.addEventListener('change', () => {
            if (el.checked) clearExclusivePeers('convective');
            syncSubtabForSelection('outlooks');
            const day = getDay();
            if (day === 3 && (el.value === 'cat' || el.value === 'prob')) {
                // Day 3 categorical and probabilistic are mutually exclusive.
                if (el.checked) {
                    document.querySelectorAll('.spc-convective-toggle').forEach((other) => {
                        if (other === el) return;
                        if ((other.value === 'cat' || other.value === 'prob') && other.checked) {
                            other.checked = false;
                        }
                    });
                }
            } else if (el.checked && BASE_HAZARDS.includes(el.value)) {
                // One base hazard at a time; keep only its own Sig overlay.
                const keepCig = CIG_OVERLAY_BY_HAZARD[el.value] || null;
                document.querySelectorAll('.spc-convective-toggle').forEach((other) => {
                    if (other === el) return;
                    const value = other.value;
                    if (BASE_HAZARDS.includes(value)) {
                        if (other.checked) other.checked = false;
                    } else if (value && value.startsWith('cig') && value !== keepCig) {
                        if (other.checked) other.checked = false;
                    }
                });
            }
            syncConvectiveOptions(false);
            if (el.checked && day <= 2) {
                // Probabilistic hazards auto-enable their Significant overlay.
                const cigHazard = CIG_OVERLAY_BY_HAZARD[el.value];
                const cigEl = cigHazard
                    ? document.querySelector(`.spc-convective-toggle[value="${cigHazard}"]`)
                    : null;
                if (cigEl && !cigEl.disabled) cigEl.checked = true;
            }
            void loadActive();
        });
    });

    // ── Watches: polygon/counties are mutually exclusive per watch type ──────
    function enforceMutuallyExclusiveWatches(idA, idB) {
        const elA = byId(idA);
        const elB = byId(idB);
        const wire = (self, other) => {
            self.addEventListener('change', () => {
                if (self.checked) {
                    other.checked = false;
                    clearExclusivePeers('watches');
                    syncSubtabForSelection('watches');
                }
                void loadActive();
            });
        };
        wire(elA, elB);
        wire(elB, elA);
    }
    enforceMutuallyExclusiveWatches('spc-watch-tor-polygon', 'spc-watch-tor-counties');
    enforceMutuallyExclusiveWatches('spc-watch-svr-polygon', 'spc-watch-svr-counties');

    // ── Storm reports ────────────────────────────────────────────────────────
    ['spc-reports-today', 'spc-reports-yesterday'].forEach((id) => {
        byId(id).addEventListener('change', (event) => {
            if (event.target.checked) {
                clearExclusivePeers('reports');
                ['spc-report-type-torn', 'spc-report-type-wind', 'spc-report-type-hail']
                    .forEach((filterId) => { byId(filterId).checked = true; });
            }
            updateReportFilterState();
            syncSubtabForSelection('reports');
            void loadActive();
        });
    });
    ['spc-show-mds', 'spc-report-type-torn', 'spc-report-type-wind', 'spc-report-type-hail'].forEach((id) => {
        byId(id).addEventListener('change', (event) => {
            if (id === 'spc-show-mds' && event.target.checked) clearExclusivePeers('mds');
            syncSubtabForSelection('reports');
            void loadActive();
        });
    });

    // ── Fire weather toggles (single selection) ──────────────────────────────
    document.querySelectorAll('.spc-fire-toggle').forEach((el) => {
        el.addEventListener('change', () => {
            if (el.checked) {
                document.querySelectorAll('.spc-fire-toggle').forEach((other) => {
                    if (other !== el) other.checked = false;
                });
                clearExclusivePeers('fire', { keepFireTarget: el });
                syncSubtabForSelection('fire');
            }
            void loadActive();
        });
    });

    // ── Style controls ───────────────────────────────────────────────────────
    function updateSliderLabel(inputId, baseLabel) {
        const value = Number(byId(inputId).value);
        const label = document.querySelector(`label[for="${inputId}"]`);
        if (label) label.textContent = `${baseLabel} (${value.toFixed(2).replace(/\.?0+$/, '') || '0'})`;
    }
    byId('spc-fill-opacity').addEventListener('input', () => {
        updateSliderLabel('spc-fill-opacity', 'Fill Opacity');
        renderer.setFillOpacity(byId('spc-fill-opacity').value);
    });
    byId('spc-stroke-opacity').addEventListener('input', () => {
        updateSliderLabel('spc-stroke-opacity', 'Stroke Opacity');
        renderer.setStrokeOpacity(byId('spc-stroke-opacity').value);
    });
    byId('spc-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));

    // ── Region / refresh ─────────────────────────────────────────────────────
    regionSelect.addEventListener('change', () => {
        mapCore.fitRegion(regionSelect.value);
    });
    byId('spc-refresh').addEventListener('click', () => void loadActive());

    // ── Cities ───────────────────────────────────────────────────────────────
    const citySource = ['us', 'world'].includes(cityDefaults.source) ? cityDefaults.source : 'off';
    const cityDensity = Number(cityDefaults.density);
    const cityFontSize = Number(cityDefaults.fontSize);
    const cityDensityInput = byId('spc-city-density');
    const cityFontSizeInput = byId('spc-city-font-size');
    cityDensityInput.value = String(cityDensity >= 0.01 && cityDensity <= 1 ? cityDensity : 0.25);
    cityFontSizeInput.value = String(cityFontSize >= 0.4 && cityFontSize <= 1.2 ? cityFontSize : 0.6);
    const initialCitySourceInput = document.querySelector(`input[name="spc-cities-source"][value="${citySource}"]`);
    if (initialCitySourceInput) initialCitySourceInput.checked = true;

    function selectedCitySource() {
        return document.querySelector('input[name="spc-cities-source"]:checked')?.value || 'off';
    }

    function updateCityControlLabels() {
        const source = selectedCitySource();
        const disabled = source === 'off';
        document.querySelectorAll('[data-city-adjustment]').forEach((row) => {
            row.classList.toggle('is-disabled', disabled);
            row.querySelector('input').disabled = disabled;
        });
        const distanceKm = Math.round(mapCore.getCityMinDistanceKm(source, cityDensityInput.value));
        byId('spc-city-density-label').textContent = `City Density (${distanceKm} km)`;
        const fontSizeLabel = Number(cityFontSizeInput.value).toFixed(2).replace(/\.?0+$/, '');
        byId('spc-city-font-size-label').textContent = `City Font Size (${fontSizeLabel})`;
    }

    document.querySelectorAll('input[name="spc-cities-source"]').forEach((input) => {
        input.addEventListener('change', () => {
            updateCityControlLabels();
            void mapCore.setCitySource(selectedCitySource()).catch((error) => {
                status.setMessage(`City overlay unavailable: ${error.message}`, 'error');
            });
        });
    });
    cityDensityInput.addEventListener('input', () => {
        mapCore.setCityDensity(cityDensityInput.value);
        updateCityControlLabels();
    });
    cityFontSizeInput.addEventListener('input', () => {
        mapCore.setCityFontSize(cityFontSizeInput.value);
        updateCityControlLabels();
    });
    mapCore.setCityDensity(cityDensityInput.value);
    mapCore.setCityFontSize(cityFontSizeInput.value);
    updateCityControlLabels();
    void mapCore.setCitySource(citySource).catch((error) => {
        status.setMessage(`City overlay unavailable: ${error.message}`, 'error');
    });

    // ── Map overlays ─────────────────────────────────────────────────────────
    document.querySelectorAll('[data-map-overlay]').forEach((input) => {
        input.addEventListener('change', () => {
            void mapCore.setOverlayVisible(input.dataset.mapOverlay, input.checked).catch((error) => {
                status.setMessage(`Map overlay unavailable: ${error.message}`, 'error');
            });
        });
    });
    void Promise.all([...document.querySelectorAll('[data-map-overlay]:checked')].map((input) => (
        mapCore.setOverlayVisible(input.dataset.mapOverlay, true)
    ))).catch((error) => status.setMessage(`Map overlay unavailable: ${error.message}`, 'error'));

    // ── Viewport-dependent watches legend ────────────────────────────────────
    const onMoveEnd = () => engine.refreshWatchesLegend();
    mapCore.map.on('moveend', onMoveEnd);

    // Keep active MD/watch overlays current so newly issued items appear and
    // expired products drop off without a manual refresh.
    const autoRefreshTimer = setInterval(() => {
        if (document.hidden) return;
        const supplemental = supplementalSelections();
        if (!supplemental.mdsEnabled && !supplemental.watchesEnabled) return;
        void loadActive({ keepDetail: true });
    }, AUTO_REFRESH_MS);

    // Startup ordering: normalize SPC controls and report-filter state before
    // any first load (guardrail carried over from the shared shell).
    syncConvectiveOptions(false);
    syncFireWeatherOptions(false);
    updateReportFilterState();
    syncSubtabForSelection();
    status.setMessage(SELECT_PRODUCT_MESSAGE);
    if (settings.autoLoad && hasAnySelection(currentSelection())) await loadActive();

    window.addEventListener('beforeunload', () => {
        clearInterval(autoRefreshTimer);
        mapCore.map.off('moveend', onMoveEnd);
        sidebarTabs.destroy();
        legend.destroy();
        detail.destroy();
        engine.destroy();
        mapCore.destroy();
    }, { once: true });
}

initialize().catch((error) => {
    console.error('[spc] startup failed', error);
    const message = byId('spc-message');
    if (message) message.textContent = `Startup failed: ${error.message}`;
});
