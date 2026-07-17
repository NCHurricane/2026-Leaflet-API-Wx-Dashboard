import * as api from '../../core/api.js';
import { createLegendHost } from '../../core/legend.js';
import { createMapCore, REGION_LABELS } from '../../core/map-core.js';
import { renderProductNav } from '../../core/nav.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { loadDefaultSettings, loadPageSettings } from '../../core/settings.js';
import { createStatusReporter } from '../../core/status.js';
import { createDroughtEngine } from './drought-engine.js';

const byId = (id) => document.getElementById(id);
const ALL_CATEGORIES = [0, 1, 2, 3, 4];

function selectedCategories() {
    return [...document.querySelectorAll('[data-drought-category]:checked')]
        .map((input) => Number(input.value));
}

function selectedStateCode() {
    const value = String(byId('drought-region').value || '').toUpperCase();
    return /^[A-Z]{2}$/.test(value) ? value : null;
}

function populateRegions(select) {
    select.replaceChildren(...Object.entries(REGION_LABELS).map(([code, label]) => {
        const option = document.createElement('option');
        option.value = code;
        option.textContent = label;
        return option;
    }));
}

function renderDateButtons(dates, activeDate, onSelect) {
    const root = byId('drought-dates');
    root.replaceChildren(...dates.map((date) => {
        const button = document.createElement('button');
        const [, month, day] = date.split('-');
        button.type = 'button';
        button.textContent = `${month}/${day}`;
        button.title = date;
        button.dataset.date = date;
        button.className = 'drought-date-button';
        button.classList.toggle('is-active', date === activeDate);
        button.addEventListener('click', () => onSelect(date));
        return button;
    }));
}

async function initialize() {
    renderProductNav(byId('product-nav'), 'Drought');
    const sidebarTabs = createSidebarTabs(byId('drought-sidebar-tabs'), { defaultTab: 'data' });
    const settings = await loadPageSettings('drought', { mapView: 'CONUS', autoLoad: false });
    const defaults = await loadDefaultSettings().catch(() => ({}));
    const cityDefaults = defaults?.global?.cityLabels || {};
    const regionSelect = byId('drought-region');
    populateRegions(regionSelect);
    regionSelect.value = REGION_LABELS[settings.mapView] ? settings.mapView : 'CONUS';

    const mapCore = createMapCore(byId('drought-map'), {
        region: regionSelect.value,
        basemap: 'Dark (No Labels)',
    });
    const legend = createLegendHost(byId('drought-legend'), { align: 'left' });
    const status = createStatusReporter({
        globalTimestamp: byId('global-timestamp'),
        message: byId('drought-message'),
        updated: byId('drought-updated'),
        age: byId('drought-age'),
        provider: byId('drought-provider'),
        source: byId('drought-source'),
    });
    const engine = createDroughtEngine({ api, mapCore, legend, status });
    let dates = [];
    let activeDate = null;

    const citySource = ['us', 'world'].includes(cityDefaults.source) ? cityDefaults.source : 'off';
    const cityDensity = Number(cityDefaults.density);
    const cityFontSize = Number(cityDefaults.fontSize);
    const cityDensityInput = byId('drought-city-density');
    const cityFontSizeInput = byId('drought-city-font-size');
    cityDensityInput.value = String(cityDensity >= 0.01 && cityDensity <= 1 ? cityDensity : 0.25);
    cityFontSizeInput.value = String(cityFontSize >= 0.4 && cityFontSize <= 1.2 ? cityFontSize : 0.6);
    const initialCitySourceInput = document.querySelector(`input[name="drought-cities-source"][value="${citySource}"]`);
    if (initialCitySourceInput) initialCitySourceInput.checked = true;

    function selectedCitySource() {
        return document.querySelector('input[name="drought-cities-source"]:checked')?.value || 'off';
    }

    function updateCityControlLabels() {
        const source = selectedCitySource();
        const disabled = source === 'off';
        document.querySelectorAll('[data-city-adjustment]').forEach((row) => {
            row.classList.toggle('is-disabled', disabled);
            row.querySelector('input').disabled = disabled;
        });
        const distanceKm = Math.round(mapCore.getCityMinDistanceKm(source, cityDensityInput.value));
        byId('drought-city-density-label').textContent = `City Density (${distanceKm} km)`;
        const fontSizeLabel = Number(cityFontSizeInput.value).toFixed(2).replace(/\.?0+$/, '');
        byId('drought-city-font-size-label').textContent = `City Font Size (${fontSizeLabel})`;
    }

    document.querySelectorAll('input[name="drought-cities-source"]').forEach((input) => {
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
    mapCore.map.on('zoomend', updateCityControlLabels);
    mapCore.setCityDensity(cityDensityInput.value);
    mapCore.setCityFontSize(cityFontSizeInput.value);
    updateCityControlLabels();
    void mapCore.setCitySource(citySource).catch((error) => {
        status.setMessage(`City overlay unavailable: ${error.message}`, 'error');
    });

    const viewOptions = () => ({
        date: activeDate,
        categories: selectedCategories(),
        stateCode: selectedStateCode(),
        opacity: Number(byId('drought-opacity').value),
    });

    async function loadActive() {
        if (!activeDate) activeDate = dates[0] || null;
        if (!activeDate) return;
        renderDateButtons(dates, activeDate, selectDate);
        try {
            await engine.load(viewOptions());
        } catch (error) {
            console.error('[drought] load failed', error);
        }
    }

    function selectDate(date) {
        activeDate = date;
        document.querySelectorAll('[data-drought-category]').forEach((input) => { input.checked = true; });
        void loadActive();
    }

    document.querySelectorAll('[data-drought-category]').forEach((input) => {
        input.addEventListener('change', () => {
            if (!engine.setFilter(viewOptions())) void loadActive();
        });
    });
    byId('drought-opacity').addEventListener('input', () => engine.setFilter(viewOptions()));
    byId('drought-refresh').addEventListener('click', () => void loadActive());
    byId('drought-region').addEventListener('change', () => {
        mapCore.fitRegion(regionSelect.value);
        if (activeDate) void loadActive();
    });
    byId('drought-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));
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

    status.setMessage('Loading available U.S. Drought Monitor dates…');
    try {
        dates = await engine.loadDates();
        activeDate = settings.autoLoad ? (dates[0] || null) : null;
        renderDateButtons(dates, activeDate, selectDate);
        byId('drought-date-note').textContent = dates.length
            ? `${dates.length} weekly releases available. Select a date to load.`
            : 'No release dates are available.';
        status.setMessage(settings.autoLoad ? 'Loading latest release…' : 'Select a release date or press Refresh.');
        if (settings.autoLoad) await loadActive();
    } catch (error) {
        status.setMessage(`Could not load release dates: ${error.message}`, 'error');
    }

    window.addEventListener('beforeunload', () => {
        sidebarTabs.destroy();
        legend.destroy();
        mapCore.map.off('zoomend', updateCityControlLabels);
        engine.destroy();
        mapCore.destroy();
    }, { once: true });
}

initialize().catch((error) => {
    console.error('[drought] startup failed', error);
    const message = byId('drought-message');
    if (message) message.textContent = `Startup failed: ${error.message}`;
});
