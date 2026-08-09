import { createSatelliteAnimator } from '../satellite/satellite-anim.js?v=20260809a';
import {
    SAT_DISPLAY_NAMES,
    createSatelliteEngine,
} from '../satellite/satellite-engine.js?v=20260809a';
import { workspaceFrameIndexAtOrBefore } from './workspace-timeline.js?v=20260803b';

const AUTO_REFRESH_INTERVAL_MS = 5 * 60 * 1000;
const INITIAL_TILE_READY_TIMEOUT_MS = 45_000;
const PLAYBACK_FIRST_TILE_TIMEOUT_MS = 30_000;

const SOURCE_SECTOR_BY_REGION = Object.freeze({
    CONUS: 'CONUS',
    AK: 'FullDisk',
    HI: 'FullDisk',
    PR: 'FullDisk',
});

const PRODUCTS = Object.freeze([
    ['GeoColor', 'GeoColor'],
    ['Channel13', 'Clean IR'],
    ['Channel09RAMSDIS', 'Water Vapor'],
    ['Channel07Fire', 'Shortwave IR / Fire'],
    ['Channel02', 'Visible'],
]);

function selectionKey(selection) {
    return `${selection.satId}|${selection.region}|${selection.sector}|${selection.channel}`;
}

function maxFramesForSector(sector) {
    return String(sector || '').toUpperCase() === 'CONUS' ? 12 : 6;
}

export function satelliteFrameIndexAtOrBefore(frames, timestamp) {
    return workspaceFrameIndexAtOrBefore(frames, timestamp);
}

export function createWorkspaceSatellite({
    api,
    mapCore,
    legend,
    status,
    elements,
    onFrames = null,
}) {
    const {
        enabledInput,
        controls,
        platformPills,
        satSelect,
        sectorStage,
        sectorPills,
        sectorSelect,
        productStage,
        productSelect,
        opacityInput,
        opacityLabel,
        frameCount,
    } = elements;
    const lifecycle = new AbortController();
    const clientId = globalThis.crypto?.randomUUID?.()
        || `workspace-satellite-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const engine = createSatelliteEngine({
        api,
        clientId,
    });

    let catalog = null;
    let frames = [];
    let loadSeq = 0;
    let loadController = null;
    let lastAutoRefreshMs = 0;

    const selection = () => ({
        satId: String(satSelect.value || '').trim(),
        region: String(sectorSelect.value || '').trim(),
        sector: SOURCE_SECTOR_BY_REGION[String(sectorSelect.value || '').trim()] || '',
        channel: String(productSelect.value || '').trim(),
    });
    const hasCompleteSelection = () => {
        const current = selection();
        return Boolean(current.satId && current.sector && current.channel);
    };

    const animator = createSatelliteAnimator({
        mapCore,
        apiUrl: api.apiUrl,
        clientId,
        getSelection: selection,
        getCatalog: () => catalog,
        onFrameVisible(frameKey) {
            const frame = frames.find((item) => String(item?.frame_key || '') === String(frameKey || ''));
            if (!frame) return;
            frameCount.textContent = String(frames.length);
            status.setDataInfo({
                timestamp: frame.timestamp_utc || null,
                provider: `${SAT_DISPLAY_NAMES[selection().satId] || selection().satId} — ${selection().channel}`,
            });
            status.setDataState('Ready', 'fresh');
        },
    });

    function setOptions(select, rows, placeholder) {
        select.replaceChildren(
            new Option(placeholder, ''),
            ...rows.map(([value, label]) => new Option(label, value)),
        );
    }

    function syncPillGroup(root, dataAttribute, value, disabled) {
        const buttons = [...root.querySelectorAll(`[data-${dataAttribute}]`)];
        buttons.forEach((button, index) => {
            const selected = button.getAttribute(`data-${dataAttribute}`) === value;
            button.disabled = disabled;
            button.classList.toggle('is-active', selected);
            button.setAttribute('aria-selected', String(selected));
            button.tabIndex = selected || (!value && index === 0) ? 0 : -1;
        });
    }

    function syncControls() {
        const enabled = enabledInput.checked;
        const { satId, region } = selection();
        controls.hidden = !enabled;
        controls.classList.toggle('is-disabled', !enabled);
        satSelect.disabled = !enabled;
        syncPillGroup(platformPills, 'workspace-satellite-platform', satId, !enabled);
        sectorStage.hidden = !satId;
        sectorSelect.disabled = !enabled || !satId;
        syncPillGroup(sectorPills, 'workspace-satellite-region', region, !enabled || !satId);
        productStage.hidden = !region;
        productSelect.disabled = !enabled || !region;
        opacityInput.disabled = !enabled;
    }

    function abortLoad() {
        loadSeq += 1;
        if (loadController) {
            loadController.abort();
            loadController = null;
        }
    }

    function clearImagery({ message = '', releaseSelection = true } = {}) {
        abortLoad();
        if (releaseSelection) engine.releaseSelection();
        frames = [];
        catalog = null;
        animator.setFrames([]);
        animator.clearPool();
        legend.clear();
        frameCount.textContent = '0';
        onFrames?.([], { index: 0 });
        if (message) status.setMessage(message);
    }

    async function updateLegend(expectedSelectionKey, signal) {
        try {
            const channel = selection().channel;
            const legendData = await engine.fetchLegend(channel);
            if (signal.aborted || selectionKey(selection()) !== expectedSelectionKey) return;
            const html = engine.legendHtmlFor(legendData);
            if (html) legend.setHtml(html);
            else legend.clear();
        } catch (error) {
            if (error?.name !== 'AbortError') console.warn('[workspace satellite] legend unavailable:', error);
            if (!signal.aborted && selectionKey(selection()) === expectedSelectionKey) legend.clear();
        }
    }

    async function refresh({ refresh = false, auto = false } = {}) {
        if (!enabledInput.checked || !hasCompleteSelection()) return false;
        const nowMs = Date.now();
        if (auto && nowMs - lastAutoRefreshMs < AUTO_REFRESH_INTERVAL_MS) return false;

        const expectedSelection = selection();
        const expectedSelectionKey = selectionKey(expectedSelection);
        const previousCatalog = catalog;
        const previousFrames = frames;
        const previousFrameIndex = animator.getFrameIndex();
        const previousFrameKey = String(previousFrames[previousFrameIndex]?.frame_key || '');
        const wasAtNewestFrame = !previousFrames.length || previousFrameIndex >= previousFrames.length - 1;
        abortLoad();
        const seq = loadSeq;
        loadController = new AbortController();
        const { signal } = loadController;
        animator.invalidate();
        status.setMessage('Loading satellite timeline…');
        status.setDataState('Loading satellite frames…', 'loading');
        void updateLegend(expectedSelectionKey, signal);

        try {
            const frameSet = await engine.fetchFrameSet(expectedSelection, {
                hours: 1,
                maxFrames: maxFramesForSector(expectedSelection.sector),
                minFrames: 0,
                refresh,
                signal,
            });
            if (signal.aborted || seq !== loadSeq || selectionKey(selection()) !== expectedSelectionKey) return false;
            catalog = frameSet.catalog;
            const nextFrames = frameSet.frames.slice(-maxFramesForSector(expectedSelection.sector));
            if (!nextFrames.length) {
                if (previousFrames.length) {
                    catalog = previousCatalog;
                    status.setMessage('No newer satellite frame is available; retaining the current frame.');
                    status.setDataState('Current frame retained', 'stale');
                    return false;
                }
                legend.clear();
                status.setMessage('No current satellite frame is available for this selection.', 'error');
                status.setDataState('Unavailable', 'error');
                return false;
            }

            frames = nextFrames;
            animator.setFrames(frames);
            frameCount.textContent = String(frames.length);
            const preservedIndex = previousFrameKey
                ? frames.findIndex((frame) => String(frame?.frame_key || '') === previousFrameKey)
                : -1;
            const nextIndex = !wasAtNewestFrame && preservedIndex >= 0
                ? preservedIndex
                : frames.length - 1;
            const shown = await animator.showFrame(nextIndex, {
                waitForTiles: false,
                tileTimeoutMs: INITIAL_TILE_READY_TIMEOUT_MS,
            });
            if (signal.aborted || seq !== loadSeq) return false;
            animator.schedulePrefetch();
            onFrames?.([...frames], { index: nextIndex });
            lastAutoRefreshMs = nowMs;
            const capabilityMessage = String(catalog?.capability_message || '').trim();
            if (catalog?.capability_status && catalog.capability_status !== 'available') {
                status.setMessage(`${frames.length} cached satellite frames loaded; ${capabilityMessage || 'live provider access is unavailable.'}`);
                status.setDataState('Cached only', 'stale');
            } else {
                status.setMessage(shown
                    ? `${frames.length} satellite frames available on the Workspace timeline.`
                    : 'The newest satellite frame could not be displayed.',
                shown ? 'success' : 'error');
            }
            return shown;
        } catch (error) {
            if (error?.name === 'AbortError' || signal.aborted || seq !== loadSeq) return false;
            console.error('[workspace satellite] frame load failed', error);
            if (previousFrames.length) {
                frames = previousFrames;
                catalog = previousCatalog;
                animator.setFrames(frames);
                status.setMessage(`Satellite refresh failed; retaining the current frame. ${error.message}`, 'error');
                status.setDataState('Current frame retained', 'stale');
            } else {
                frames = [];
                animator.setFrames([]);
                legend.clear();
                frameCount.textContent = '0';
                status.setMessage(`Satellite load failed: ${error.message}`, 'error');
                status.setDataState('Load failed', 'error');
            }
            return false;
        } finally {
            if (loadController?.signal === signal) loadController = null;
        }
    }

    function reset({ announce = false } = {}) {
        enabledInput.checked = false;
        satSelect.value = '';
        sectorSelect.value = '';
        setOptions(productSelect, PRODUCTS, 'Select product');
        clearImagery({ message: announce ? 'Satellite layer disabled.' : '' });
        syncControls();
    }

    async function showFrameAt(index, { waitForVisibleTile = false } = {}) {
        if (!enabledInput.checked || !frames.length) return false;
        const safeIndex = Math.max(0, Math.min(frames.length - 1, Number(index) || 0));
        const shown = await animator.showFrame(safeIndex, {
            waitForVisibleTile,
            tileTimeoutMs: PLAYBACK_FIRST_TILE_TIMEOUT_MS,
        });
        if (shown) animator.schedulePrefetch();
        return shown;
    }

    function showFrameForTimestamp(timestamp, options = {}) {
        const index = satelliteFrameIndexAtOrBefore(frames, timestamp);
        if (index < 0) {
            animator.clearPool();
            return Promise.resolve(false);
        }
        return showFrameAt(index, options);
    }

    function setSelectValue(select, value) {
        if (select.value === value) return;
        select.value = value;
        select.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function bindPillGroup(root, dataAttribute, select) {
        root.addEventListener('click', (event) => {
            const button = event.target.closest(`[data-${dataAttribute}]`);
            if (!button || button.disabled) return;
            setSelectValue(select, button.getAttribute(`data-${dataAttribute}`));
        }, { signal: lifecycle.signal });
        root.addEventListener('keydown', (event) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            const buttons = [...root.querySelectorAll(`[data-${dataAttribute}]:not(:disabled)`)]
                .filter((button) => !button.hidden);
            const currentIndex = buttons.indexOf(event.target.closest(`[data-${dataAttribute}]`));
            if (currentIndex < 0 || !buttons.length) return;
            event.preventDefault();
            let nextIndex = currentIndex;
            if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + buttons.length) % buttons.length;
            if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % buttons.length;
            if (event.key === 'Home') nextIndex = 0;
            if (event.key === 'End') nextIndex = buttons.length - 1;
            const nextButton = buttons[nextIndex];
            setSelectValue(select, nextButton.getAttribute(`data-${dataAttribute}`));
            nextButton.focus();
        }, { signal: lifecycle.signal });
    }

    enabledInput.addEventListener('change', () => {
        if (!enabledInput.checked) {
            clearImagery({ message: 'Satellite layer disabled.' });
        } else if (!hasCompleteSelection()) {
            status.setMessage('Select a satellite, region, and product.');
        } else {
            void refresh();
        }
        syncControls();
    }, { signal: lifecycle.signal });

    satSelect.addEventListener('change', () => {
        sectorSelect.value = '';
        setOptions(productSelect, PRODUCTS, 'Select product');
        clearImagery();
        syncControls();
        status.setMessage(satSelect.value ? 'Select a satellite region and product.' : 'Select a satellite.');
    }, { signal: lifecycle.signal });

    sectorSelect.addEventListener('change', () => {
        productSelect.value = '';
        clearImagery();
        syncControls();
        status.setMessage(sectorSelect.value ? 'Select a satellite product.' : 'Select a satellite region.');
    }, { signal: lifecycle.signal });

    productSelect.addEventListener('change', () => {
        const complete = hasCompleteSelection();
        clearImagery({ releaseSelection: !complete });
        if (complete) void refresh();
        else status.setMessage('Select a satellite product.');
    }, { signal: lifecycle.signal });

    opacityInput.addEventListener('input', () => {
        const value = Math.max(0.1, Math.min(1, Number(opacityInput.value) || 1));
        animator.setOpacity(value);
        opacityLabel.textContent = `Satellite Opacity (${value.toFixed(2).replace(/\.?0+$/, '')})`;
    }, { signal: lifecycle.signal });

    const onZoomStart = () => animator.prepareForZoom();
    const onZoomEnd = () => {
        if (enabledInput.checked && frames.length) void animator.showFrame(animator.getFrameIndex());
    };
    mapCore.map.on('zoomstart', onZoomStart);
    mapCore.map.on('zoomend', onZoomEnd);

    bindPillGroup(platformPills, 'workspace-satellite-platform', satSelect);
    bindPillGroup(sectorPills, 'workspace-satellite-region', sectorSelect);
    setOptions(productSelect, PRODUCTS, 'Select product');
    syncControls();
    animator.setOpacity(opacityInput.value);

    return Object.freeze({
        refresh,
        reset,
        getFrames: () => [...frames],
        isEnabled: () => enabledInput.checked,
        hasSelection: hasCompleteSelection,
        showFrameAt,
        showFrameForTimestamp,
        destroy() {
            lifecycle.abort();
            abortLoad();
            engine.releaseSelection({ beacon: true });
            mapCore.map.off('zoomstart', onZoomStart);
            mapCore.map.off('zoomend', onZoomEnd);
            animator.destroy();
        },
    });
}
