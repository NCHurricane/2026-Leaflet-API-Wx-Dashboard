import * as api from '../../core/api.js';
import { createLegendHost } from '../../core/legend.js';
import { createMapCore, REGION_LABELS } from '../../core/map-core.js';
import { renderProductNav } from '../../core/nav.js';
import { createScrubber } from '../../core/scrubber.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { loadDefaultSettings, loadPageSettings } from '../../core/settings.js';
import { createStatusReporter } from '../../core/status.js';
import {
    SAT_DISPLAY_NAMES,
    SAT_SOURCES,
    createSatelliteEngine,
    formatFrameLabel,
    frameIndexForReload,
    frameTileCount,
} from './satellite-engine.js';
import { createSatelliteAnimator } from './satellite-anim.js';

const byId = (id) => document.getElementById(id);
const SELECT_CHAIN_MESSAGE = 'Pick a satellite, sector, and product to load imagery.';
const LOOKBACK_HOURS_MAX = 12;
const FRAME_REQUEST_MAX = 360;
const LOOKBACK_RELOAD_DEBOUNCE_MS = 250;
const AUTO_UPDATE_INTERVAL_MS = 5 * 60 * 1000; // matches the shell's satellite cadence
const INITIAL_TILE_READY_TIMEOUT_MS = 45000;

// ── Platform capability tables (ported unchanged from the shell) ────────────
const PLATFORM_SECTORS = {
    goes18:     ['FullDisk', 'CONUS', 'Meso1', 'Meso2'],
    goes19:     ['FullDisk', 'CONUS', 'Meso1', 'Meso2'],
    himawari9:  ['FullDisk', 'Japan', 'Target'],
    meteosat12: ['FullDisk'],
    meteosat9:  ['FullDisk'],
    meteosat11: ['RSS'],
};

// Channels available per non-GOES platform. null = all channels shown (GOES
// default). Himawari uses identical ABI to GOES, so shows the full list.
const METEOSAT_CHANNELS = [
    'Channel02', 'Channel03', 'Channel05', 'Channel07', 'Channel07Fire',
    'Channel08RAMSDIS', 'Channel09RAMSDIS', 'Channel13',
    'NighttimeMicrophysics', 'Dust', 'Ash',
];
const PLATFORM_CHANNELS = {
    himawari9: null,
    meteosat12: new Set(['Channel01', 'Channel06', ...METEOSAT_CHANNELS]),
    meteosat9: new Set(METEOSAT_CHANNELS),
    meteosat11: new Set(METEOSAT_CHANNELS),
};

// GOES ABI L2 aerosol products; no AHI/SEVIRI/FCI equivalent is published.
const GOES_ONLY_CHANNELS = new Set(['AerosolDetection', 'AerosolOpticalDepth', 'FireRadiativePower']);
const isGoesPlatform = (satId) => satId === 'goes18' || satId === 'goes19';

const IMPLEMENTED_SATELLITES = new Set(['goes18', 'goes19', 'himawari9', 'meteosat12', 'meteosat9', 'meteosat11']);

const AUTO_VIEW_PRESETS = {
    'goes18:FullDisk': 'goes-west-full-disk',
    'goes18:CONUS': 'conus',
    'goes18:Meso1': 'conus',
    'goes18:Meso2': 'conus',
    'goes19:FullDisk': 'goes-east-full-disk',
    'goes19:CONUS': 'conus',
    'goes19:Meso1': 'conus',
    'goes19:Meso2': 'conus',
    'himawari9:FullDisk': 'west-pacific',
    'himawari9:Japan': 'himawari-japan',
    'himawari9:Target': 'west-pacific',
    'meteosat12:FullDisk': 'europe-africa',
    'meteosat9:FullDisk': 'indian-ocean',
    'meteosat11:RSS': 'europe-rss',
};

const NAMED_VIEW_PRESETS = {
    conus: { bounds: [[23.0, -127.0], [50.5, -65.0]], platforms: new Set(['goes18', 'goes19']) },
    'southeast-us': {
        bounds: [[24.0, -92.5], [38.0, -74.0]],
        platforms: new Set(['goes19']),
        sectors: new Set(['CONUS']),
    },
    'goes-west-full-disk': { bounds: [[-55, -220], [60, -55]], platforms: new Set(['goes18']) },
    'goes-east-full-disk': { bounds: [[-55, -155], [60, -15]], platforms: new Set(['goes19']) },
    'west-pacific': { bounds: [[-55, 80], [60, 200]], platforms: new Set(['himawari9']) },
    'europe-africa': { bounds: [[-38, -35], [62, 48]], platforms: new Set(['meteosat12']) },
    'indian-ocean': { bounds: [[-55, -15], [55, 105]], platforms: new Set(['meteosat9']) },
    'europe-rss': { bounds: [[25, -15], [65, 35]], platforms: new Set(['meteosat11']) },
    'himawari-japan': { bounds: [[18, 100], [55, 157]], platforms: new Set(['himawari9']) },
    'himawari-target-current': { bounds: null, platforms: new Set(['himawari9']), dynamic: true },
};

function activeSatId() {
    return String(byId('satellite-sat-id')?.value || '').trim();
}

function activeSector() {
    return String(byId('satellite-sector')?.value || '').trim();
}

function activeChannel() {
    return String(byId('satellite-channel')?.value || '').trim();
}

function activeSelection() {
    return { satId: activeSatId(), sector: activeSector(), channel: activeChannel() };
}

function activeLookbackHours() {
    const hours = Number(byId('satellite-lookback')?.value || 1);
    if (!Number.isFinite(hours) || hours <= 0) return 1;
    return Math.max(1, Math.min(LOOKBACK_HOURS_MAX, Math.round(hours)));
}

function setLookbackHours(hours) {
    const safeHours = Math.max(1, Math.min(LOOKBACK_HOURS_MAX, Math.round(Number(hours) || 1)));
    const slider = byId('satellite-lookback');
    if (slider) slider.value = String(safeHours);
    const display = byId('satellite-lookback-value');
    if (display) display.textContent = `${safeHours}h`;
}

// Frame budget scales with the sector's scan cadence (Meso ~1 min,
// CONUS ~5 min, FullDisk ~10 min).
function maxFramesForRequest(hours) {
    const sector = activeSector().toUpperCase();
    const safeHours = Math.max(1, Math.min(LOOKBACK_HOURS_MAX, Math.round(Number(hours) || 1)));
    if (sector === 'MESO1' || sector === 'MESO2') {
        return Math.min(FRAME_REQUEST_MAX, safeHours * 60);
    }
    if (sector === 'FULLDISK') {
        return Math.min(FRAME_REQUEST_MAX, safeHours * 6);
    }
    return Math.min(FRAME_REQUEST_MAX, safeHours * 12);
}

function currentFrameRequestWindow() {
    const hours = activeLookbackHours();
    return { hours, maxFrames: maxFramesForRequest(hours) };
}

// ── Selection chain sync (Satellite → Sector → View → Product) ──────────────
function syncSectorVisibility() {
    const satId = activeSatId();
    if (!satId) return;
    const allowed = new Set(PLATFORM_SECTORS[satId] || ['FullDisk', 'CONUS', 'Meso1', 'Meso2']);
    const currentSector = activeSector();
    const needsReset = !!currentSector && !allowed.has(currentSector);

    document.querySelectorAll('.satellite-subtab-button[data-satellite-sector]').forEach((btn) => {
        btn.style.display = allowed.has(btn.dataset.satelliteSector) ? '' : 'none';
    });

    if (needsReset) {
        const defaultSector = Array.from(allowed)[0] || 'FullDisk';
        const select = byId('satellite-sector');
        if (select) select.value = defaultSector;
    }
}

function syncViewPresetVisibility() {
    const satId = activeSatId();
    const sector = activeSector();
    const select = byId('satellite-view-preset');
    if (!select) return;
    select.disabled = !satId;

    Array.from(select.options).forEach((opt) => {
        if (!opt.value) {
            opt.style.display = '';
            return;
        }
        const preset = NAMED_VIEW_PRESETS[opt.value];
        const platformMatches = !satId || preset?.platforms?.has(satId);
        const sectorMatches = !preset?.sectors || preset.sectors.has(sector);
        opt.style.display = platformMatches && sectorMatches ? '' : 'none';
    });

    const selectedPreset = NAMED_VIEW_PRESETS[select.value];
    if (!satId
        || (selectedPreset?.platforms && !selectedPreset.platforms.has(satId))
        || (selectedPreset?.sectors && !selectedPreset.sectors.has(sector))) {
        select.value = '';
    }
}

function syncViewPresetEnabled() {
    const select = byId('satellite-view-preset');
    if (select) select.disabled = !activeSector();
}

function syncChannelEnabled() {
    const select = byId('satellite-channel');
    if (!select) return;
    const sector = activeSector();
    select.disabled = !sector;
    if (!sector) select.value = '';
}

function syncChannelVisibility() {
    const satId = activeSatId();
    const allowed = satId ? (PLATFORM_CHANNELS[satId] || null) : null;
    const select = byId('satellite-channel');
    if (!select) return;

    const goesOk = isGoesPlatform(satId);
    Array.from(select.options).forEach((opt) => {
        const platformOk = (!allowed || allowed.has(opt.value));
        const goesOnlyOk = (!GOES_ONLY_CHANNELS.has(opt.value) || goesOk);
        opt.style.display = (platformOk && goesOnlyOk) ? '' : 'none';
    });

    if (satId && allowed && activeChannel() && !allowed.has(activeChannel())) {
        select.value = allowed.has('Channel13') ? 'Channel13' : (Array.from(allowed)[0] || '');
    }
    // A GOES-only aerosol product selected while switching to a non-GOES
    // platform would otherwise stay hidden-but-selected; reset it.
    if (satId && !goesOk && GOES_ONLY_CHANNELS.has(activeChannel())) {
        select.value = 'Channel13';
    }
}

function syncSubtabs() {
    const satId = activeSatId();
    const sector = activeSector();
    byId('satellite-sector-controls').hidden = !satId;
    byId('satellite-view-controls').hidden = !sector;
    byId('satellite-product-controls').hidden = !sector;
    document.querySelectorAll('.satellite-subtab-button[data-satellite-sat]').forEach((button) => {
        const isSelected = button.dataset.satelliteSat === satId;
        button.setAttribute('aria-selected', isSelected ? 'true' : 'false');
        button.tabIndex = isSelected ? 0 : -1;
    });
    syncSectorVisibility();
    syncViewPresetVisibility();
    syncViewPresetEnabled();
    syncChannelVisibility();
    syncChannelEnabled();
    document.querySelectorAll('.satellite-subtab-button[data-satellite-sector]').forEach((button) => {
        if (button.style.display === 'none') {
            button.setAttribute('aria-selected', 'false');
            button.tabIndex = -1;
            return;
        }
        const isSelected = button.dataset.satelliteSector === sector;
        button.setAttribute('aria-selected', isSelected ? 'true' : 'false');
        button.tabIndex = isSelected ? 0 : -1;
    });
}

function setSelectValue(selectId, value) {
    const select = byId(selectId);
    if (!select || select.value === value) return;
    select.value = value;
    syncSubtabs();
    select.dispatchEvent(new Event('change', { bubbles: true }));
}

async function initialize() {
    renderProductNav(byId('product-nav'), 'Satellite');
    const sidebarTabs = createSidebarTabs(byId('satellite-sidebar-tabs'), { defaultTab: 'live' });
    const settings = await loadPageSettings('satellite', {
        mapView: 'WORLD', platform: '', sector: '', product: 'Channel13', hours: 1,
    });
    const defaults = await loadDefaultSettings().catch(() => ({}));
    const cityDefaults = defaults?.global?.cityLabels || {};
    const regionSelect = byId('satellite-region');
    regionSelect.replaceChildren(...Object.entries(REGION_LABELS).map(([code, label]) => {
        const option = document.createElement('option');
        option.value = code;
        option.textContent = label;
        return option;
    }));
    regionSelect.value = REGION_LABELS[settings.mapView] ? settings.mapView : 'WORLD';

    let resetSatelliteState = () => {};
    const mapCore = createMapCore(byId('satellite-map'), {
        region: regionSelect.value,
        basemap: 'Dark (No Labels)',
        onResetView: () => resetSatelliteState(),
    });
    const legend = createLegendHost(byId('satellite-legend'), { align: 'left' });
    const status = createStatusReporter({
        globalTimestamp: byId('global-timestamp'),
        message: byId('satellite-message'),
        updated: byId('satellite-updated'),
        age: byId('satellite-age'),
        provider: byId('satellite-provider'),
        source: byId('satellite-source'),
    });
    const engine = createSatelliteEngine({ api });

    let catalog = null;
    const animator = createSatelliteAnimator({
        mapCore,
        apiUrl: api.apiUrl,
        getSelection: activeSelection,
        getCatalog: () => catalog,
    });

    let frames = [];
    let loadToken = 0;
    let loadController = null;
    let lookbackReloadTimer = null;
    let autoUpdateInFlight = false;

    const scrubberBar = byId('satellite-scrubber-bar');
    const scrubber = createScrubber(byId('satellite-bottom-scrubber'), {
        holdAtEnd: true,
        onFrame(frame, index) {
            void showFrame(index);
        },
    });

    function showScrubber(visible) {
        scrubberBar.hidden = !visible;
    }

    function reportFrameInfo(frame) {
        const satId = activeSatId();
        const channel = activeChannel();
        status.setDataInfo({
            timestamp: frame?.timestamp_utc || null,
            provider: `${SAT_DISPLAY_NAMES[satId] || satId} — ${channel}`,
            source: SAT_SOURCES[satId] || 'NOAA',
        });
    }

    async function showFrame(index, options = {}) {
        const frame = frames[index];
        if (!frame) return false;
        const shown = await animator.showFrame(index, options);
        if (shown) reportFrameInfo(frame);
        return shown;
    }

    async function updateLegend() {
        const channel = activeChannel();
        if (!channel) {
            legend.clear();
            return;
        }
        try {
            const legendData = await engine.fetchLegend(channel);
            if (activeChannel() !== channel) return;
            const html = engine.legendHtmlFor(legendData);
            if (html) legend.setHtml(html);
            else legend.clear();
        } catch (err) {
            console.warn('[satellite] legend unavailable:', err?.message || err);
            if (activeChannel() === channel) legend.clear();
        }
    }

    function labeledFrames(rawFrames) {
        return rawFrames.map((frame) => ({ ...frame, label: formatFrameLabel(frame) }));
    }

    function clearFrames() {
        loadToken += 1;
        if (loadController) {
            loadController.abort();
            loadController = null;
        }
        frames = [];
        catalog = null;
        animator.clearPool();
        animator.setFrames([]);
        scrubber.setFrames([], { silent: true });
        showScrubber(false);
        legend.clear();
        status.setMessage(SELECT_CHAIN_MESSAGE);
    }

    resetSatelliteState = () => {
        byId('satellite-sat-id').value = '';
        byId('satellite-sector').value = '';
        byId('satellite-view-preset').value = '';
        byId('satellite-channel').value = '';
        syncSubtabs();
        clearFrames();
    };

    async function reloadFrames({ refresh = false, preserveFrameKey = '' } = {}) {
        const { satId, sector, channel } = activeSelection();
        if (!satId || !sector || !channel) {
            clearFrames();
            return;
        }
        if (!IMPLEMENTED_SATELLITES.has(satId)) {
            status.setMessage('Data pipeline coming soon for this platform.');
            return;
        }

        const token = ++loadToken;
        if (loadController) loadController.abort();
        loadController = new AbortController();
        const { signal } = loadController;
        animator.invalidate();
        void updateLegend();
        const requestWindow = currentFrameRequestWindow();
        status.setMessage(`Loading satellite frames (${requestWindow.hours}h window)…`);

        try {
            const frameSet = await engine.fetchFrameSet(activeSelection(), {
                hours: requestWindow.hours,
                maxFrames: requestWindow.maxFrames,
                signal,
                refresh,
                minFrames: 0,
            });
            if (token !== loadToken) return;
            catalog = frameSet.catalog;

            if (!frameSet.frames.length) {
                frames = [];
                animator.setFrames([]);
                scrubber.setFrames([], { silent: true });
                showScrubber(false);
                status.setMessage('No animation frames available for this selection.', 'error');
                return;
            }

            frames = labeledFrames(frameSet.frames);
            animator.setFrames(frames);
            const nextIndex = frameIndexForReload(frames, preserveFrameKey);
            showScrubber(true);
            scrubber.setFrames(frames, { index: nextIndex, silent: true });
            animator.primeLayers(nextIndex);
            let displayed = await showFrame(nextIndex, {
                waitForTiles: false,
                tileTimeoutMs: INITIAL_TILE_READY_TIMEOUT_MS,
            });
            if (token !== loadToken) return;
            if (!displayed && preserveFrameKey) {
                const fallbackIndex = frameIndexForReload(frames);
                if (fallbackIndex !== nextIndex) {
                    scrubber.setFrames(frames, { index: fallbackIndex, silent: true });
                    animator.primeLayers(fallbackIndex);
                    displayed = await showFrame(fallbackIndex, {
                        waitForTiles: false,
                        tileTimeoutMs: INITIAL_TILE_READY_TIMEOUT_MS,
                    });
                    if (token !== loadToken) return;
                }
            }
            const cachedTiles = frames.reduce((sum, frame) => sum + frameTileCount(frame), 0);
            status.setMessage(
                `${frames.length} frames loaded (${requestWindow.hours}h window, ${cachedTiles} cached tiles); tiles fill as they render.`,
                'success',
            );
        } catch (err) {
            if (err.name === 'AbortError') return;
            if (token !== loadToken) return;
            console.error('[satellite] frame load failed', err);
            frames = [];
            animator.setFrames([]);
            scrubber.setFrames([], { silent: true });
            showScrubber(false);
            status.setMessage(`Satellite load failed: ${err.message}`, 'error');
        } finally {
            if (loadController?.signal === signal) loadController = null;
        }
    }

    function scheduleLookbackReload() {
        if (!frames.length && !activeChannel()) return;
        if (lookbackReloadTimer) clearTimeout(lookbackReloadTimer);
        lookbackReloadTimer = setTimeout(() => {
            lookbackReloadTimer = null;
            void reloadFrames();
        }, LOOKBACK_RELOAD_DEBOUNCE_MS);
    }

    // ── Auto-update: refresh the catalog, keep playback position ────────────
    async function autoUpdateTick() {
        if (!byId('satellite-auto-update')?.checked) return;
        if (document.hidden || autoUpdateInFlight || !frames.length) return;
        const { satId, sector, channel } = activeSelection();
        if (!satId || !sector || !channel) return;
        autoUpdateInFlight = true;
        const token = loadToken;
        const previousKeys = new Set(frames.map((frame) => String(frame?.frame_key || '')).filter(Boolean));
        const previousFrameKey = frames[scrubber.getIndex()]?.frame_key || '';
        const requestWindow = currentFrameRequestWindow();
        try {
            const frameSet = await engine.fetchFrameSet(activeSelection(), {
                hours: requestWindow.hours,
                maxFrames: requestWindow.maxFrames,
                refresh: true,
                minFrames: 0,
            });
            if (token !== loadToken || !frames.length || !frameSet.frames.length) return;
            catalog = frameSet.catalog;
            const nextFrames = labeledFrames(frameSet.frames);
            const addedCount = nextFrames.filter((frame) => {
                const key = String(frame?.frame_key || '');
                return key && !previousKeys.has(key);
            }).length;
            frames = nextFrames;
            animator.setFrames(frames);
            // Jump to the newest frame when new imagery arrived; otherwise stay
            // on the frame the user was viewing.
            const nextIndex = addedCount > 0
                ? frameIndexForReload(frames)
                : frameIndexForReload(frames, previousFrameKey);
            const wasPlaying = scrubber.isPlaying();
            scrubber.setFrames(frames, { index: nextIndex, silent: true, keepPlaying: true });
            if (!wasPlaying) {
                animator.primeLayers(nextIndex);
                await showFrame(nextIndex);
            }
            animator.schedulePrefetch();
            if (addedCount > 0) {
                status.setMessage(`${addedCount} new satellite frame${addedCount === 1 ? '' : 's'} added to the loop.`, 'success');
            }
        } catch (_) { /* transient; next tick retries */ } finally {
            autoUpdateInFlight = false;
        }
    }

    const autoUpdateTimer = setInterval(() => { void autoUpdateTick(); }, AUTO_UPDATE_INTERVAL_MS);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) void autoUpdateTick();
    });

    // ── View presets ────────────────────────────────────────────────────────
    function fitPresetBounds(bounds) {
        mapCore.map.fitBounds(bounds, { animate: false, padding: [20, 20] });
    }

    async function fitDynamicViewPreset(presetKey) {
        if (presetKey !== 'himawari-target-current') return;
        const { satId, sector } = activeSelection();
        const channel = activeChannel() || 'Channel13';
        try {
            const params = new URLSearchParams({ sat_id: satId, sector, channel });
            const resp = await fetch(api.apiUrl(`/api/satellite-v2/frame-bounds?${params.toString()}`));
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const payload = await resp.json();
            const bounds = payload?.bounds;
            if (!bounds) {
                status.setMessage('No current Target Area is being observed right now.');
                return;
            }
            fitPresetBounds([[bounds.south, bounds.west], [bounds.north, bounds.east]]);
        } catch (_) {
            status.setMessage('Could not locate the current Target Area.');
        }
    }

    function setActiveViewPreset(presetKey, { fit = true } = {}) {
        const select = byId('satellite-view-preset');
        const safeKey = String(presetKey || '').trim();
        if (select) select.value = safeKey;
        const entry = NAMED_VIEW_PRESETS[safeKey];
        if (fit && entry?.dynamic) {
            void fitDynamicViewPreset(safeKey);
            return;
        }
        if (fit && entry?.bounds) fitPresetBounds(entry.bounds);
    }

    function setAutoViewPresetForSelection(satId, sector) {
        const presetKey = AUTO_VIEW_PRESETS[`${satId}:${sector}`] || '';
        setActiveViewPreset(presetKey, { fit: true });
    }

    // ── Selection chain wiring ──────────────────────────────────────────────
    function bindSubtabGroup(selector, selectId, dataKey) {
        const buttons = Array.from(document.querySelectorAll(selector));
        buttons.forEach((button, index) => {
            button.addEventListener('click', () => {
                setSelectValue(selectId, button.dataset[dataKey]);
            });
            button.addEventListener('keydown', (event) => {
                if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                event.preventDefault();
                let nextIndex = index;
                if (event.key === 'ArrowLeft') nextIndex = index === 0 ? buttons.length - 1 : index - 1;
                if (event.key === 'ArrowRight') nextIndex = index === buttons.length - 1 ? 0 : index + 1;
                if (event.key === 'Home') nextIndex = 0;
                if (event.key === 'End') nextIndex = buttons.length - 1;
                const nextButton = buttons[nextIndex];
                if (!nextButton) return;
                setSelectValue(selectId, nextButton.dataset[dataKey]);
                nextButton.focus();
            });
        });
    }

    bindSubtabGroup('.satellite-subtab-button[data-satellite-sat]', 'satellite-sat-id', 'satelliteSat');
    bindSubtabGroup('.satellite-subtab-button[data-satellite-sector]', 'satellite-sector', 'satelliteSector');
    syncSubtabs();

    ['satellite-sat-id', 'satellite-sector', 'satellite-channel'].forEach((id) => {
        byId(id)?.addEventListener('change', () => {
            if (id === 'satellite-sat-id') {
                const sectorSelect = byId('satellite-sector');
                if (sectorSelect) sectorSelect.value = '';
                const viewSelect = byId('satellite-view-preset');
                if (viewSelect) viewSelect.value = '';
            }
            syncSubtabs();
            const satId = activeSatId();
            const sector = activeSector();
            if (satId && sector && (id === 'satellite-sat-id' || id === 'satellite-sector')) {
                setAutoViewPresetForSelection(satId, sector);
                syncChannelEnabled();
            }
            const channel = activeChannel();
            if (!satId || !sector || !channel) {
                clearFrames();
                return;
            }
            animator.clearPool();
            void reloadFrames();
        });
    });

    byId('satellite-view-preset')?.addEventListener('change', (event) => {
        setActiveViewPreset(event.target.value, { fit: true });
        syncChannelEnabled();
    });

    // ── Lookback slider ─────────────────────────────────────────────────────
    const lookbackSlider = byId('satellite-lookback');
    lookbackSlider.addEventListener('input', () => {
        setLookbackHours(lookbackSlider.value);
        scheduleLookbackReload();
    });
    setLookbackHours(Number(settings.hours) || 1);

    // ── Map interaction: prefetch on pan, pause/re-render on zoom ───────────
    let resumePlayAfterZoom = false;
    mapCore.map.on('moveend', () => {
        if (frames.length) animator.schedulePrefetch(350);
    });
    mapCore.map.on('zoomstart', () => {
        if (!frames.length) return;
        resumePlayAfterZoom = scrubber.isPlaying();
        scrubber.pause();
        animator.cancelPendingSwap();
    });
    mapCore.map.on('zoomend', () => {
        if (!frames.length) return;
        void showFrame(scrubber.getIndex());
        animator.schedulePrefetch(450);
        if (resumePlayAfterZoom) {
            resumePlayAfterZoom = false;
            setTimeout(() => {
                if (frames.length && !scrubber.isPlaying()) scrubber.play();
            }, 450);
        }
    });

    // ── Style controls ──────────────────────────────────────────────────────
    const opacityInput = byId('satellite-opacity');
    function updateOpacityLabel() {
        const value = Number(opacityInput.value);
        const label = document.querySelector('label[for="satellite-opacity"]');
        if (label) label.textContent = `Imagery Opacity (${value.toFixed(2).replace(/\.?0+$/, '') || '0'})`;
    }
    opacityInput.addEventListener('input', () => {
        updateOpacityLabel();
        animator.setOpacity(opacityInput.value);
    });
    animator.setOpacity(opacityInput.value);
    byId('satellite-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));

    // ── Region / refresh ────────────────────────────────────────────────────
    regionSelect.addEventListener('change', () => {
        resetSatelliteState();
        mapCore.fitRegion(regionSelect.value);
    });
    byId('satellite-refresh').addEventListener('click', () => void reloadFrames({ refresh: true }));

    // ── Cities ──────────────────────────────────────────────────────────────
    const citySource = ['us', 'world'].includes(cityDefaults.source) ? cityDefaults.source : 'off';
    const cityDensity = Number(cityDefaults.density);
    const cityFontSize = Number(cityDefaults.fontSize);
    const cityDensityInput = byId('satellite-city-density');
    const cityFontSizeInput = byId('satellite-city-font-size');
    cityDensityInput.value = String(cityDensity >= 0.01 && cityDensity <= 1 ? cityDensity : 0.25);
    cityFontSizeInput.value = String(cityFontSize >= 0.4 && cityFontSize <= 1.2 ? cityFontSize : 0.6);
    const initialCitySourceInput = document.querySelector(`input[name="satellite-cities-source"][value="${citySource}"]`);
    if (initialCitySourceInput) initialCitySourceInput.checked = true;

    function selectedCitySource() {
        return document.querySelector('input[name="satellite-cities-source"]:checked')?.value || 'off';
    }

    function updateCityControlLabels() {
        const source = selectedCitySource();
        const disabled = source === 'off';
        document.querySelectorAll('[data-city-adjustment]').forEach((row) => {
            row.classList.toggle('is-disabled', disabled);
            row.querySelector('input').disabled = disabled;
        });
        const distanceKm = Math.round(mapCore.getCityMinDistanceKm(source, cityDensityInput.value));
        byId('satellite-city-density-label').textContent = `City Density (${distanceKm} km)`;
        const fontSizeLabel = Number(cityFontSizeInput.value).toFixed(2).replace(/\.?0+$/, '');
        byId('satellite-city-font-size-label').textContent = `City Font Size (${fontSizeLabel})`;
    }

    document.querySelectorAll('input[name="satellite-cities-source"]').forEach((input) => {
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

    // ── Map overlays ────────────────────────────────────────────────────────
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

    // ── Startup ─────────────────────────────────────────────────────────────
    // Configured page defaults may pre-select the chain (defaults ship empty,
    // so the page normally opens with nothing selected and no auto-load).
    const configuredPlatform = String(settings.platform || '').trim();
    const configuredSector = String(settings.sector || '').trim();
    if (configuredPlatform && PLATFORM_SECTORS[configuredPlatform]) {
        setSelectValue('satellite-sat-id', configuredPlatform);
        if (configuredSector && PLATFORM_SECTORS[configuredPlatform].includes(configuredSector)) {
            setSelectValue('satellite-sector', configuredSector);
        }
    }
    if (!activeChannel()) status.setMessage(SELECT_CHAIN_MESSAGE);

    window.addEventListener('beforeunload', () => {
        clearInterval(autoUpdateTimer);
        if (lookbackReloadTimer) clearTimeout(lookbackReloadTimer);
        sidebarTabs.destroy();
        legend.destroy();
        scrubber.destroy();
        animator.destroy();
        mapCore.destroy();
    }, { once: true });
}

initialize().catch((error) => {
    console.error('[satellite] startup failed', error);
    const message = byId('satellite-message');
    if (message) message.textContent = `Startup failed: ${error.message}`;
});
