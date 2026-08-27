import * as api from '../../core/api.js';
import { createLegendHost } from '../../core/legend.js';
import { createMapCore, REGION_LABELS } from '../../core/map-core.js?v=20260826g';
import { renderProductNav } from '../../core/nav.js?v=20260826a';
import { startNonWorkspaceAlertMonitor } from '../../core/non-workspace-alert-monitor.js?v=20260824a';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { loadDefaultSettings } from '../../core/settings.js';
import { createStatusReporter } from '../../core/status.js?v=20260808a';
import { createWaterEngine } from './water-engine.js?v=20260804a';

const byId = (id) => document.getElementById(id);

async function initialize() {
    renderProductNav(byId('product-nav'), 'Water');
    startNonWorkspaceAlertMonitor();
    createSidebarTabs(byId('water-sidebar-tabs'), { defaultTab: 'live' });
    const defaults = await loadDefaultSettings().catch(() => ({}));
    const cityDefaults = defaults?.global?.cityLabels || {};
    const mapCore = createMapCore(byId('weather-map'), {
        region: 'CONUS', basemap: 'Dark', boundaryMode: 'conus',
    });
    const pane = mapCore.map.createPane('water-markers');
    pane.style.zIndex = '470';
    const legend = createLegendHost(byId('weather-colorbar'), { align: 'left' });
    const status = createStatusReporter({
        globalTimestamp: byId('global-timestamp'), message: byId('weather-water-status'),
        updated: byId('water-updated'), age: byId('water-age'),
        provider: byId('water-provider'),
    });
    const engine = createWaterEngine({
        api, mapCore, legend, status,
        detailRoot: byId('weather-water-detail'),
        paneName: 'water-markers',
    });

    const selectedNetworks = () => [...document.querySelectorAll('.weather-water-network-filter input:checked')]
        .map((input) => input.value);
    const syncFloodControls = () => {
        const riverEnabled = selectedNetworks().includes('river');
        byId('weather-water-flood-filter-row').hidden = !riverEnabled;
        document.querySelectorAll('.wx-water-flood-pill').forEach((pill) => {
            pill.setAttribute('aria-selected', String(pill.dataset.flood === engine.getFloodFilter()));
        });
    };

    const regionSelect = byId('weather-water-region');
    regionSelect.replaceChildren(...Object.entries(REGION_LABELS).map(([code, label]) => new Option(label, code)));
    regionSelect.value = 'CONUS';
    regionSelect.addEventListener('change', () => {
        mapCore.fitRegion(regionSelect.value);
        engine.setRegion();
    });
    byId('weather-refresh-water').addEventListener('click', () => void engine.refresh({ force: true }));
    byId('weather-clear-water').addEventListener('click', () => {
        engine.clear();
        status.setMessage('Water markers cleared.');
    });
    document.querySelectorAll('.weather-water-network-filter input').forEach((input) => {
        input.addEventListener('change', () => {
            void engine.setNetworks(selectedNetworks());
            syncFloodControls();
        });
    });
    byId('weather-water-flood-filters').addEventListener('click', (event) => {
        const pill = event.target.closest('.wx-water-flood-pill');
        if (!pill) return;
        engine.setFloodFilter(pill.dataset.flood || 'all');
        syncFloodControls();
    });

    byId('water-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));
    const citySource = ['us', 'world'].includes(cityDefaults.source) ? cityDefaults.source : 'off';
    const cityDensityInput = byId('water-city-density');
    const cityFontSizeInput = byId('water-city-font-size');
    cityDensityInput.value = String(Number(cityDefaults.density) || 0.25);
    cityFontSizeInput.value = String(Number(cityDefaults.fontSize) || 0.6);
    document.querySelector(`input[name="water-cities-source"][value="${citySource}"]`).checked = true;
    const selectedCitySource = () => document.querySelector('input[name="water-cities-source"]:checked')?.value || 'off';
    const updateCityControls = () => {
        const source = selectedCitySource();
        const disabled = source === 'off';
        document.querySelectorAll('[data-city-adjustment]').forEach((row) => {
            row.classList.toggle('is-disabled', disabled);
            row.querySelector('input').disabled = disabled;
        });
        byId('water-city-density-label').textContent = `City Density (${Math.round(mapCore.getCityMinDistanceKm(source, cityDensityInput.value))} km)`;
        byId('water-city-font-size-label').textContent = `City Font Size (${Number(cityFontSizeInput.value).toFixed(2).replace(/\.?0+$/, '')})`;
    };
    document.querySelectorAll('input[name="water-cities-source"]').forEach((input) => input.addEventListener('change', () => {
        updateCityControls();
        void mapCore.setCitySource(selectedCitySource()).catch((error) => status.setMessage(`City overlay unavailable: ${error.message}`, 'error'));
    }));
    cityDensityInput.addEventListener('input', () => { mapCore.setCityDensity(cityDensityInput.value); updateCityControls(); });
    cityFontSizeInput.addEventListener('input', () => { mapCore.setCityFontSize(cityFontSizeInput.value); updateCityControls(); });
    mapCore.setCityDensity(cityDensityInput.value);
    mapCore.setCityFontSize(cityFontSizeInput.value);
    updateCityControls();
    void mapCore.setCitySource(citySource).catch((error) => status.setMessage(`City overlay unavailable: ${error.message}`, 'error'));
    document.querySelectorAll('[data-map-overlay]').forEach((input) => {
        input.addEventListener('change', () => void mapCore.setOverlayVisible(input.dataset.mapOverlay, input.checked));
        if (input.checked) void mapCore.setOverlayVisible(input.dataset.mapOverlay, true);
    });

    await engine.setNetworks(selectedNetworks(), { refresh: false });
    syncFloodControls();
    await engine.setEnabled(true);
    window.addEventListener('beforeunload', () => engine.destroy(), { once: true });
}

initialize().catch((error) => {
    console.error('[water] startup failed', error);
    byId('weather-water-status').textContent = `Startup failed: ${error.message}`;
});
