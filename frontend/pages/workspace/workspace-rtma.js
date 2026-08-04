import {
    baseDistKm,
    createRtmaEngine,
    dataRegionForMapRegion,
    formatValidTimeLabel,
    timestampMs,
} from '../rtma/rtma-engine.js?v=20260802b';
import {
    workspaceFrameIndexAtOrBefore,
    workspaceFrameWindowWithPredecessor,
} from './workspace-timeline.js?v=20260803b';

const AUTO_REFRESH_INTERVAL_MS = 15 * 60 * 1000;
const HISTORY_POLL_INTERVAL_MS = 5_000;
const LOOKBACK_HOURS = 1;
const SOURCE_LOOKBACK_HOURS = 2;
const TIMELINE_WINDOW_MS = LOOKBACK_HOURS * 60 * 60 * 1000;
const FRAME_CAP = 12;
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
    onFrames = null,
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
    let timelineFrames = [];
    let timelineSourceFrames = [];
    let secondaryTimelineFrames = [];
    let visibleFrameIndex = -1;
    let visibleFrameIdentity = '';
    let historyToken = 0;
    let historyPollTimer = null;

    const productConfig = () => PRODUCT_BY_VALUE.get(activeProduct) || null;
    const selection = () => ({
        region: dataRegionForMapRegion(getRegion()),
        stream: STREAM,
        product: productConfig()?.product || '',
    });
    const hasSelection = () => Boolean(productConfig());
    const supportsCurrentRegion = () => dataRegionForMapRegion(getRegion()) === 'CONUS';

    function frameIdentity(frame) {
        return `${frame?.source_data_key || frame?.frame_key || ''}|${frame?.timestamp || ''}`;
    }

    function emitFrames(options = {}) {
        onFrames?.(timelineSourceFrames.map((frame) => ({
            ...frame,
            label: formatValidTimeLabel(timestampMs(frame.timestamp)),
        })), options);
    }

    function clearHistory() {
        historyToken += 1;
        clearTimeout(historyPollTimer);
        historyPollTimer = null;
        timelineFrames = [];
        timelineSourceFrames = [];
        secondaryTimelineFrames = [];
        visibleFrameIndex = -1;
        visibleFrameIdentity = '';
        emitFrames();
    }

    function mergeFrameSet(current, nextFrames, { replace = false } = {}) {
        const combined = replace ? nextFrames : [...current, ...nextFrames];
        return [...new Map(combined.map((frame) => [frameIdentity(frame), frame])).values()]
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
        const primarySelection = selection();
        try {
            const batch = reset
                ? await engine.loadFrames(primarySelection, SOURCE_LOOKBACK_HOURS)
                : await engine.fetchNewFrames(primarySelection, SOURCE_LOOKBACK_HOURS, timelineFrames);
            if (!batch || token !== historyToken) return false;
            timelineFrames = mergeFrameSet(timelineFrames, batch.frames || [], { replace: reset });
            const cutoffTimestamp = new Date(Date.now() - TIMELINE_WINDOW_MS).toISOString();
            const primaryWindow = workspaceFrameWindowWithPredecessor(timelineFrames, cutoffTimestamp);
            timelineFrames = primaryWindow.renderFrames;
            timelineSourceFrames = primaryWindow.timelineFrames;

            let secondaryRefreshing = false;
            if (selected.secondaryProduct) {
                const secondarySelection = { ...primarySelection, product: selected.secondaryProduct };
                const secondaryBatch = await engine.fetchNewFrames(
                    secondarySelection,
                    SOURCE_LOOKBACK_HOURS,
                    reset ? [] : secondaryTimelineFrames,
                );
                if (token !== historyToken) return false;
                secondaryTimelineFrames = mergeFrameSet(
                    secondaryTimelineFrames,
                    secondaryBatch.frames || [],
                    { replace: reset },
                );
                secondaryTimelineFrames = workspaceFrameWindowWithPredecessor(
                    secondaryTimelineFrames,
                    cutoffTimestamp,
                ).renderFrames;
                secondaryRefreshing = Boolean(secondaryBatch.refreshing);
            } else {
                secondaryTimelineFrames = [];
            }

            refreshPending = Boolean(batch.refreshing || secondaryRefreshing);
            emitFrames(reset && timelineSourceFrames.length ? { index: timelineSourceFrames.length - 1 } : {});
            if (refreshPending) scheduleHistoryPoll(token);
            return refreshPending;
        } catch (error) {
            if (token === historyToken) console.warn('[workspace RTMA] history load failed', error);
            return false;
        }
    }

    function startHistory() {
        clearHistory();
        const token = historyToken;
        void syncHistory({ reset: true, token });
    }

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
        if (auto && timelineFrames.length) {
            void syncHistory({ token: historyToken });
            return true;
        }
        const result = await engine.loadLatest(selection());
        await loadSecondaryValues();
        refreshPending = Boolean(result?.refreshing);
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
        if (hasSelection() && await refresh()) startHistory();
    }

    enabledInput.addEventListener('change', () => {
        if (!enabledInput.checked) clear({ message: 'RTMA-RU layer disabled.' });
        else if (!supportsCurrentRegion()) status.setMessage('RTMA-RU is available for CONUS only.', 'error');
        else if (!hasSelection()) status.setMessage('Select an RTMA-RU field.');
        else void refresh().then((loaded) => { if (loaded) startHistory(); });
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
        void refresh().then((loaded) => { if (loaded) startHistory(); });
    }, { signal: lifecycle.signal });

    modePills.addEventListener('click', (event) => {
        const button = event.target.closest('[data-rtma-mode]');
        if (!button || button.disabled) return;
        if (button.dataset.rtmaMode === 'values') showValues = !showValues;
        if (button.dataset.rtmaMode === 'gradient') showGradient = !showGradient;
        syncModeState();
        if (!showValues && !showGradient) {
            engine.clear();
        } else if (visibleFrameIndex >= 0 && timelineFrames.length) {
            void showStoredFrameAt(visibleFrameIndex, { force: true });
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
            if (visibleFrameIndex >= 0 && timelineFrames.length) {
                void showStoredFrameAt(visibleFrameIndex, { force: true });
            } else void engine.reloadPoints(selection()).then(loadSecondaryValues);
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

    function matchingSecondaryFrame(frame) {
        const sourceKey = String(frame?.source_data_key || '');
        const timestamp = String(frame?.timestamp || '');
        return secondaryTimelineFrames.find((candidate) => (
            (sourceKey && String(candidate?.source_data_key || '') === sourceKey)
            || (timestamp && String(candidate?.timestamp || '') === timestamp)
        )) || null;
    }

    async function showStoredFrameAt(index, { force = false } = {}) {
        if (!enabledInput.checked || !timelineFrames.length) return false;
        const safeIndex = Math.max(0, Math.min(timelineFrames.length - 1, Number(index) || 0));
        const secondaryFrame = productConfig()?.secondaryProduct
            ? matchingSecondaryFrame(timelineFrames[safeIndex])
            : null;
        const nextIdentity = `${frameIdentity(timelineFrames[safeIndex])}::${secondaryFrame ? frameIdentity(secondaryFrame) : ''}`;
        if (!force && nextIdentity === visibleFrameIdentity) return true;
        visibleFrameIndex = safeIndex;
        visibleFrameIdentity = nextIdentity;
        const rendered = await engine.renderFrame(timelineFrames[safeIndex], { secondaryFrame });
        if (!rendered) visibleFrameIdentity = '';
        if (rendered) {
            engine.prefetchFrames(timelineFrames, safeIndex);
            const secondaryIndex = secondaryFrame ? secondaryTimelineFrames.indexOf(secondaryFrame) : -1;
            if (secondaryIndex >= 0) engine.prefetchFrames(secondaryTimelineFrames, secondaryIndex);
        }
        return rendered;
    }

    function showFrameAt(index, options = {}) {
        if (!timelineSourceFrames.length) return Promise.resolve(false);
        const safeIndex = Math.max(0, Math.min(timelineSourceFrames.length - 1, Number(index) || 0));
        const identity = frameIdentity(timelineSourceFrames[safeIndex]);
        const storedIndex = timelineFrames.findIndex((frame) => frameIdentity(frame) === identity);
        return storedIndex >= 0 ? showStoredFrameAt(storedIndex, options) : Promise.resolve(false);
    }

    function showFrameForTimestamp(timestamp) {
        const index = workspaceFrameIndexAtOrBefore(timelineFrames, timestamp);
        if (index < 0) {
            visibleFrameIndex = -1;
            visibleFrameIdentity = '';
            engine.clear();
            return Promise.resolve(false);
        }
        return showStoredFrameAt(index);
    }

    return Object.freeze({
        refresh,
        reset,
        setRegion,
        isEnabled: () => enabledInput.checked,
        hasSelection,
        getFrames: () => [...timelineSourceFrames],
        showFrameAt,
        showFrameForTimestamp,
        destroy() {
            lifecycle.abort();
            mapCore.map.off('moveend', onMoveEnd);
            mapCore.map.off('zoomend', onZoomEnd);
            clearHistory();
            engine.destroy();
        },
    });
}
