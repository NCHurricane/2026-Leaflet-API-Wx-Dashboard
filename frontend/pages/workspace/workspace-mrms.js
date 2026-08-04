import {
    createMrmsEngine,
    formatValidTimeLabel,
    timestampMs,
} from '../mrms/mrms-engine.js?v=20260802a';
import { workspaceFrameIndexAtOrBefore } from './workspace-timeline.js?v=20260803b';

const AUTO_REFRESH_INTERVAL_MS = 2 * 60 * 1000;
const HISTORY_POLL_INTERVAL_MS = 5_000;
const LOOKBACK_HOURS = 1;
const FRAME_CAP = 64;

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
    onFrames = null,
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
    let timelineFrames = [];
    let visibleFrameIndex = -1;
    let visibleFrameIdentity = '';
    let historyToken = 0;
    let historyPollTimer = null;

    const productConfig = () => PRODUCT_BY_VALUE.get(activeProduct) || null;
    const hasSelection = () => Boolean(productConfig());
    const supportsCurrentRegion = () => String(getRegion() || '').toUpperCase() === 'CONUS';

    function frameIdentity(frame) {
        return `${frame?.frame_key || frame?.source_data_key || ''}|${frame?.timestamp || ''}`;
    }

    function emitFrames(options = {}) {
        onFrames?.(timelineFrames.map((frame) => ({
            ...frame,
            label: formatValidTimeLabel(timestampMs(frame.timestamp)),
        })), options);
    }

    function clearHistory() {
        historyToken += 1;
        clearTimeout(historyPollTimer);
        historyPollTimer = null;
        timelineFrames = [];
        visibleFrameIndex = -1;
        visibleFrameIdentity = '';
        emitFrames();
    }

    function mergeFrames(nextFrames, { replace = false } = {}) {
        const combined = replace ? nextFrames : [...timelineFrames, ...nextFrames];
        timelineFrames = [...new Map(combined.map((frame) => [frameIdentity(frame), frame])).values()]
            .sort((left, right) => timestampMs(left.timestamp) - timestampMs(right.timestamp))
            .slice(-FRAME_CAP);
    }

    function scheduleHistoryPoll(token) {
        clearTimeout(historyPollTimer);
        historyPollTimer = setTimeout(async () => {
            historyPollTimer = null;
            await syncHistory({ token });
        }, HISTORY_POLL_INTERVAL_MS);
    }

    async function syncHistory({ reset = false, token = historyToken } = {}) {
        const selected = productConfig();
        if (!enabledInput.checked || !selected || !supportsCurrentRegion() || token !== historyToken) return false;
        try {
            const batch = reset
                ? await engine.loadFrames(selected.product, LOOKBACK_HOURS)
                : await engine.fetchNewFrames(selected.product, LOOKBACK_HOURS, timelineFrames);
            if (!batch || token !== historyToken) return false;
            mergeFrames(batch.frames || [], { replace: reset });
            refreshPending = Boolean(batch.refreshing);
            emitFrames(reset && timelineFrames.length ? { index: timelineFrames.length - 1 } : {});
            if (refreshPending) scheduleHistoryPoll(token);
            return refreshPending;
        } catch (error) {
            if (token === historyToken) console.warn('[workspace MRMS] history load failed', error);
            return false;
        }
    }

    function startHistory() {
        clearHistory();
        const token = historyToken;
        void syncHistory({ reset: true, token });
    }

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
        if (auto && timelineFrames.length) {
            void syncHistory({ token: historyToken });
            return true;
        }
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
        if (timelineFrames.length) void syncHistory({ token: historyToken });
        return true;
    }

    function clear({ message = '' } = {}) {
        refreshPending = false;
        clearHistory();
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
        if (hasSelection() && await refresh()) startHistory();
    }

    enabledInput.addEventListener('change', () => {
        if (!enabledInput.checked) clear({ message: 'MRMS layer disabled.' });
        else if (!supportsCurrentRegion()) status.setMessage('MRMS Workspace products are available for CONUS only.', 'error');
        else if (!hasSelection()) status.setMessage('Select an MRMS field.');
        else void refresh().then((loaded) => { if (loaded) startHistory(); });
        syncControls();
    }, { signal: lifecycle.signal });

    productPills.addEventListener('click', (event) => {
        const button = event.target.closest('[data-mrms-product]');
        if (!button || button.disabled || button.dataset.mrmsProduct === activeProduct) return;
        activeProduct = button.dataset.mrmsProduct;
        clear();
        syncControls();
        void refresh().then((loaded) => { if (loaded) startHistory(); });
    }, { signal: lifecycle.signal });

    opacityInput.addEventListener('input', () => {
        const value = Math.max(0.1, Math.min(1, Number(opacityInput.value) || 0.7));
        engine.setOpacity(value);
        opacityLabel.textContent = `MRMS Opacity (${value.toFixed(2).replace(/\.?0+$/, '')})`;
    }, { signal: lifecycle.signal });

    engine.setOpacity(opacityInput.value);
    syncControls();

    async function showFrameAt(index, { force = false } = {}) {
        if (!enabledInput.checked || !timelineFrames.length) return false;
        const safeIndex = Math.max(0, Math.min(timelineFrames.length - 1, Number(index) || 0));
        const nextIdentity = frameIdentity(timelineFrames[safeIndex]);
        if (!force && nextIdentity === visibleFrameIdentity) return true;
        visibleFrameIndex = safeIndex;
        visibleFrameIdentity = nextIdentity;
        const rendered = await engine.renderFrame(timelineFrames[safeIndex]);
        if (!rendered) visibleFrameIdentity = '';
        if (rendered) engine.prefetchFrames(timelineFrames, safeIndex);
        return rendered;
    }

    function showFrameForTimestamp(timestamp) {
        const index = workspaceFrameIndexAtOrBefore(timelineFrames, timestamp);
        if (index < 0) {
            visibleFrameIndex = -1;
            visibleFrameIdentity = '';
            engine.clear();
            return Promise.resolve(false);
        }
        return showFrameAt(index);
    }

    return Object.freeze({
        refresh,
        reset,
        setRegion,
        isEnabled: () => enabledInput.checked,
        hasSelection,
        getFrames: () => [...timelineFrames],
        showFrameAt,
        showFrameForTimestamp,
        destroy() {
            lifecycle.abort();
            clearHistory();
            engine.destroy();
        },
    });
}
