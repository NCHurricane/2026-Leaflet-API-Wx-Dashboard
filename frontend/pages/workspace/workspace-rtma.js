import {
    baseDistKm,
    createRtmaEngine,
    dataRegionForMapRegion,
} from '../rtma/rtma-engine.js?v=20260802b';

const AUTO_REFRESH_INTERVAL_MS = 15 * 60 * 1000;
const STREAM = 'rtma_rapid_update';

export const WORKSPACE_RTMA_PRODUCTS = Object.freeze([
    { value: 'temperature', label: 'Temperature', product: 'temperature' },
    { value: 'apparent_temperature', label: 'Feels Like', product: 'apparent_temperature' },
    { value: 'dew_point', label: 'Dew Point', product: 'dew_point' },
    { value: 'winds', label: 'Winds', product: 'wind_speed', secondaryProduct: 'wind_direction' },
    { value: 'wind_gust', label: 'Wind Gust', product: 'wind_gust' },
    { value: 'visibility', label: 'Visibility', product: 'visibility' },
]);

const PRODUCT_BY_VALUE = new Map(WORKSPACE_RTMA_PRODUCTS.map((item) => [item.value, item]));

export function createWorkspaceRtma({
    api,
    mapCore,
    legend,
    status,
    getRegion,
    gradientPaneName,
    pointPaneName,
    elements,
}) {
    const {
        enabledInput,
        controls,
        productPills,
        modePills,
        densityInput,
        densityLabel,
        opacityInput,
        opacityLabel,
    } = elements;
    const lifecycle = new AbortController();
    const engine = createRtmaEngine({
        api,
        mapCore,
        legend,
        status,
        gradientPaneName,
        pointPaneName,
    });
    let activeProduct = '';
    let showValues = true;
    let showGradient = false;
    let lastAutoRefreshMs = 0;
    let refreshPending = false;

    const productConfig = () => PRODUCT_BY_VALUE.get(activeProduct) || null;
    const selection = () => ({
        region: dataRegionForMapRegion(getRegion()),
        stream: STREAM,
        product: productConfig()?.product || '',
    });
    const hasSelection = () => Boolean(productConfig());
    const supportsCurrentRegion = () => dataRegionForMapRegion(getRegion()) === 'CONUS';

    function updateDensityLabel() {
        const zoom = mapCore.map?.getZoom() ?? 5;
        const density = Math.max(0.01, Math.min(2, Number(densityInput.value) || 0.25));
        densityLabel.textContent = `Value Density (${Math.round(baseDistKm(zoom) / density)} km)`;
    }

    function syncPills(root, attribute, activeValue, disabled) {
        root.querySelectorAll(`[data-${attribute}]`).forEach((button) => {
            const active = button.getAttribute(`data-${attribute}`) === activeValue;
            button.disabled = disabled;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
    }

    function syncModeState() {
        const enabled = enabledInput.checked;
        const available = enabled && supportsCurrentRegion() && hasSelection();
        syncPills(modePills, 'rtma-mode', showValues ? 'values' : '', !available);
        const gradientButton = modePills.querySelector('[data-rtma-mode="gradient"]');
        gradientButton?.classList.toggle('is-active', showGradient);
        gradientButton?.setAttribute('aria-pressed', String(showGradient));
        densityInput.disabled = !available || !showValues;
        opacityInput.disabled = !available || !showGradient;
        engine.setShowValues(showValues);
        engine.setShowGradient(showGradient);
        engine.setDensity(densityInput.value);
        updateDensityLabel();
    }

    function syncControls() {
        const enabled = enabledInput.checked;
        const supported = supportsCurrentRegion();
        controls.hidden = !enabled;
        controls.classList.toggle('is-disabled', !enabled);
        syncPills(productPills, 'rtma-product', activeProduct, !enabled || !supported);
        syncModeState();
    }

    async function loadSecondaryValues() {
        const secondaryProduct = productConfig()?.secondaryProduct;
        if (showValues && secondaryProduct) {
            await engine.loadSecondary(selection(), secondaryProduct);
        } else {
            engine.clearSecondary();
        }
    }

    async function refresh({ auto = false } = {}) {
        if (!enabledInput.checked || !hasSelection() || (!showValues && !showGradient)) return false;
        if (!supportsCurrentRegion()) {
            status.setMessage('RTMA-RU is available for CONUS only.', 'error');
            return false;
        }
        const nowMs = Date.now();
        if (auto && !refreshPending && nowMs - lastAutoRefreshMs < AUTO_REFRESH_INTERVAL_MS) return false;
        lastAutoRefreshMs = nowMs;
        const result = await engine.loadLatest(selection());
        await loadSecondaryValues();
        refreshPending = Boolean(result?.refreshing);
        return true;
    }

    function clear({ message = '' } = {}) {
        refreshPending = false;
        engine.clear();
        if (message) status.setMessage(message);
    }

    function reset({ announce = false } = {}) {
        enabledInput.checked = false;
        activeProduct = '';
        showValues = true;
        showGradient = false;
        clear({ message: announce ? 'RTMA-RU layer disabled.' : '' });
        syncControls();
    }

    async function setRegion() {
        clear();
        syncControls();
        if (!enabledInput.checked) return;
        if (!supportsCurrentRegion()) {
            status.setMessage('RTMA-RU is available for CONUS only.', 'error');
            return;
        }
        if (hasSelection()) await refresh();
    }

    enabledInput.addEventListener('change', () => {
        if (!enabledInput.checked) clear({ message: 'RTMA-RU layer disabled.' });
        else if (!supportsCurrentRegion()) status.setMessage('RTMA-RU is available for CONUS only.', 'error');
        else if (!hasSelection()) status.setMessage('Select an RTMA-RU field.');
        else void refresh();
        syncControls();
    }, { signal: lifecycle.signal });

    productPills.addEventListener('click', (event) => {
        const button = event.target.closest('[data-rtma-product]');
        if (!button || button.disabled || button.dataset.rtmaProduct === activeProduct) return;
        activeProduct = button.dataset.rtmaProduct;
        showValues = true;
        showGradient = false;
        clear();
        syncControls();
        void refresh();
    }, { signal: lifecycle.signal });

    modePills.addEventListener('click', (event) => {
        const button = event.target.closest('[data-rtma-mode]');
        if (!button || button.disabled) return;
        if (button.dataset.rtmaMode === 'values') showValues = !showValues;
        if (button.dataset.rtmaMode === 'gradient') showGradient = !showGradient;
        syncModeState();
        if (!showValues && !showGradient) {
            clear();
        } else if (button.dataset.rtmaMode === 'gradient' && showGradient) {
            void refresh();
        } else if (button.dataset.rtmaMode === 'values' && showValues) {
            void engine.reloadPoints(selection()).then(loadSecondaryValues);
        }
    }, { signal: lifecycle.signal });

    densityInput.addEventListener('input', () => {
        engine.setDensity(densityInput.value);
        updateDensityLabel();
    }, { signal: lifecycle.signal });

    opacityInput.addEventListener('input', () => {
        const value = Math.max(0.1, Math.min(1, Number(opacityInput.value) || 0.7));
        engine.setGradientOpacity(value);
        opacityLabel.textContent = `RTMA Opacity (${value.toFixed(2).replace(/\.?0+$/, '')})`;
    }, { signal: lifecycle.signal });

    const onMoveEnd = () => {
        if (enabledInput.checked && hasSelection() && showValues) {
            void engine.reloadPoints(selection()).then(loadSecondaryValues);
        }
    };
    const onZoomEnd = () => {
        updateDensityLabel();
        engine.renderPoints();
    };
    mapCore.map.on('moveend', onMoveEnd);
    mapCore.map.on('zoomend', onZoomEnd);

    engine.setGradientOpacity(opacityInput.value);
    syncControls();

    return Object.freeze({
        refresh,
        reset,
        setRegion,
        isEnabled: () => enabledInput.checked,
        hasSelection,
        destroy() {
            lifecycle.abort();
            mapCore.map.off('moveend', onMoveEnd);
            mapCore.map.off('zoomend', onZoomEnd);
            engine.destroy();
        },
    });
}
