import {
    createMrmsEngine,
    formatValidTimeLabel,
} from '../mrms/mrms-engine.js?v=20260802a';

const AUTO_REFRESH_INTERVAL_MS = 2 * 60 * 1000;

export const WORKSPACE_MRMS_PRODUCTS = Object.freeze([
    { value: 'rotation', label: 'Rotation Track', product: 'RotationTrack_LL_30min' },
    { value: 'mesh_instant', label: 'Instant MESH', product: 'MESH_Instant' },
    { value: 'mesh_30min', label: '30m MESH', product: 'MESH_Max_30min' },
    { value: 'lightning_30min', label: '30m Lightning', product: 'Lightning_30min' },
    { value: 'precip_type', label: 'Precip Type', product: 'PrecipFlag' },
    { value: 'base_reflectivity', label: 'Base Reflectivity', product: 'Refl_BaseQC' },
]);

const PRODUCT_BY_VALUE = new Map(WORKSPACE_MRMS_PRODUCTS.map((item) => [item.value, item]));

export function createWorkspaceMrms({
    api,
    mapCore,
    legend,
    status,
    getRegion,
    paneName,
    elements,
}) {
    const {
        enabledInput,
        controls,
        productPills,
        opacityInput,
        opacityLabel,
    } = elements;
    const lifecycle = new AbortController();
    const engine = createMrmsEngine({ api, mapCore, legend, status, paneName });
    let activeProduct = '';
    let lastAutoRefreshMs = 0;
    let refreshPending = false;

    const productConfig = () => PRODUCT_BY_VALUE.get(activeProduct) || null;
    const hasSelection = () => Boolean(productConfig());
    const supportsCurrentRegion = () => String(getRegion() || '').toUpperCase() === 'CONUS';

    function syncControls() {
        const enabled = enabledInput.checked;
        const supported = supportsCurrentRegion();
        controls.hidden = !enabled;
        controls.classList.toggle('is-disabled', !enabled);
        productPills.querySelectorAll('[data-mrms-product]').forEach((button) => {
            const active = button.dataset.mrmsProduct === activeProduct;
            button.disabled = !enabled || !supported;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
        opacityInput.disabled = !enabled || !supported || !hasSelection();
    }

    async function refresh({ auto = false } = {}) {
        if (!enabledInput.checked || !hasSelection()) return false;
        if (!supportsCurrentRegion()) {
            status.setMessage('MRMS Workspace products are available for CONUS only.', 'error');
            return false;
        }
        const nowMs = Date.now();
        if (auto && !refreshPending && nowMs - lastAutoRefreshMs < AUTO_REFRESH_INTERVAL_MS) return false;
        lastAutoRefreshMs = nowMs;
        const selected = productConfig();
        const result = await engine.loadLatest(selected.product);
        refreshPending = Boolean(result?.refreshing);
        if (!result) return false;
        if (result.rendered === false) {
            status.setMessage(`${result.data.full_name || selected.label} could not be displayed.`, 'error');
            status.setDataState?.('Display failed', 'error');
            return false;
        }
        const staleNote = result.stale ? ' Cached data may be stale.' : '';
        status.setMessage(
            `${result.data.full_name || selected.label} valid ${formatValidTimeLabel(result.tsMs)}.${staleNote}`,
            result.stale ? 'error' : 'success',
        );
        status.setDataState?.(result.stale ? 'Stale data' : 'Ready', result.stale ? 'stale' : 'fresh');
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
        clear({ message: announce ? 'MRMS layer disabled.' : '' });
        syncControls();
    }

    async function setRegion() {
        clear();
        syncControls();
        if (!enabledInput.checked) return;
        if (!supportsCurrentRegion()) {
            status.setMessage('MRMS Workspace products are available for CONUS only.', 'error');
            return;
        }
        if (hasSelection()) await refresh();
    }

    enabledInput.addEventListener('change', () => {
        if (!enabledInput.checked) clear({ message: 'MRMS layer disabled.' });
        else if (!supportsCurrentRegion()) status.setMessage('MRMS Workspace products are available for CONUS only.', 'error');
        else if (!hasSelection()) status.setMessage('Select an MRMS field.');
        else void refresh();
        syncControls();
    }, { signal: lifecycle.signal });

    productPills.addEventListener('click', (event) => {
        const button = event.target.closest('[data-mrms-product]');
        if (!button || button.disabled || button.dataset.mrmsProduct === activeProduct) return;
        activeProduct = button.dataset.mrmsProduct;
        clear();
        syncControls();
        void refresh();
    }, { signal: lifecycle.signal });

    opacityInput.addEventListener('input', () => {
        const value = Math.max(0.1, Math.min(1, Number(opacityInput.value) || 0.7));
        engine.setOpacity(value);
        opacityLabel.textContent = `MRMS Opacity (${value.toFixed(2).replace(/\.?0+$/, '')})`;
    }, { signal: lifecycle.signal });

    engine.setOpacity(opacityInput.value);
    syncControls();

    return Object.freeze({
        refresh,
        reset,
        setRegion,
        isEnabled: () => enabledInput.checked,
        hasSelection,
        destroy() {
            lifecycle.abort();
            engine.destroy();
        },
    });
}
