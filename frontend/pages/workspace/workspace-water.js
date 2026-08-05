import { createWaterEngine } from '../water/water-engine.js?v=20260804a';

const AUTO_REFRESH_INTERVAL_MS = 5 * 60 * 1000;
const DEFAULT_NETWORKS = Object.freeze(['river', 'coastal', 'buoy']);

export function createWorkspaceWater({ api, mapCore, legend, status, paneName, detailRoot, elements, onBeforeDetail }) {
    const { enabledInput, controls, networkPills } = elements;
    const lifecycle = new AbortController();
    const engine = createWaterEngine({
        api, mapCore, legend, status, paneName, detailRoot, onBeforeDetail,
    });
    let lastAutoRefreshMs = 0;

    const isEnabled = () => enabledInput.checked;
    const selectedNetworks = () => [...networkPills.querySelectorAll('[data-water-network][aria-pressed="true"]')]
        .map((button) => button.dataset.waterNetwork);
    const hasSelection = () => selectedNetworks().length > 0;

    function syncControls() {
        const enabled = isEnabled();
        controls.hidden = !enabled;
        controls.classList.toggle('is-disabled', !enabled);
        networkPills.querySelectorAll('[data-water-network]').forEach((button) => {
            button.disabled = !enabled;
            button.classList.toggle('is-active', button.getAttribute('aria-pressed') === 'true');
        });
    }

    async function refresh({ auto = false, refresh = false } = {}) {
        if (!isEnabled() || !hasSelection()) return false;
        const nowMs = Date.now();
        if (auto && nowMs - lastAutoRefreshMs < AUTO_REFRESH_INTERVAL_MS) return false;
        lastAutoRefreshMs = nowMs;
        await engine.refresh({ force: refresh });
        return true;
    }

    function reset({ announce = false } = {}) {
        enabledInput.checked = false;
        networkPills.querySelectorAll('[data-water-network]').forEach((button) => {
            button.setAttribute('aria-pressed', String(DEFAULT_NETWORKS.includes(button.dataset.waterNetwork)));
        });
        void engine.setNetworks(DEFAULT_NETWORKS, { refresh: false });
        void engine.setEnabled(false);
        syncControls();
        if (announce) status.setMessage('Water layer disabled.');
    }

    function setRegion() {
        engine.setRegion();
    }

    enabledInput.addEventListener('change', () => {
        void engine.setEnabled(isEnabled());
        syncControls();
        if (!isEnabled()) status.setMessage('Water layer disabled.');
    }, { signal: lifecycle.signal });

    networkPills.addEventListener('click', (event) => {
        const button = event.target.closest('[data-water-network]');
        if (!button || button.disabled) return;
        button.setAttribute('aria-pressed', String(button.getAttribute('aria-pressed') !== 'true'));
        void engine.setNetworks(selectedNetworks());
        syncControls();
    }, { signal: lifecycle.signal });

    void engine.setNetworks(DEFAULT_NETWORKS, { refresh: false });
    syncControls();

    return Object.freeze({
        closeDetail: () => engine.closeDetail(),
        destroy() {
            lifecycle.abort();
            engine.destroy();
        },
        hasSelection,
        isEnabled,
        refresh,
        reset,
        setRegion,
    });
}
