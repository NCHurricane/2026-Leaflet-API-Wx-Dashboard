// Satellite tile-layer animator: per-frame Leaflet tile layers with a pooled
// hot-frame window, ready-gated swaps, progressive redraw retries, tile-error
// backoff, and viewport tile prefetch. Ported from the shell's satellite
// animation machinery; this page is always in "animate" mode, so the shell's
// scrub-mode conditionals collapse to the enabled() gate.

const LAYER_PANE = 'satellite-overlays';
const CROSSFADE_MS = 5;
const TILE_READY_TIMEOUT_MS = 15000;
const HOT_FRAME_RADIUS = 3;
const PROGRESSIVE_REDRAW_DELAYS_MS = [2500];
const RETAIN_LAYER_LIMIT = 72;
const PREFETCH_AHEAD_FRAMES = 8;
const PREFETCH_BEHIND_FRAMES = 2;
const PREFETCH_MAX_CONCURRENT = 2;
const PREFETCH_MAX_TILES_PER_FRAME = 32;
const PREFETCH_MAX_QUEUE_TILES = 180;
const PREFETCH_TILE_BUFFER = 1;
const PREFETCH_DEBOUNCE_MS = 220;
const PREFETCH_RETRY_AFTER_MS = 20000;
const PREFETCH_SEEN_LIMIT = 1200;
const TILE_SIZE = 256;

export function createSatelliteAnimator({ mapCore, apiUrl, getSelection, getCatalog }) {
    const leaflet = mapCore.leaflet;
    const map = mapCore.map;

    if (!map.getPane(LAYER_PANE)) {
        const pane = map.createPane(LAYER_PANE);
        pane.style.zIndex = '330';
        pane.style.pointerEvents = 'none';
    }

    let frames = [];
    let frameIndex = 0;
    let activeLayer = null;
    let opacity = 1.0;
    let enabled = true;
    let renderSeq = 0;
    let pendingSwapToken = 0;
    let tileRefreshToken = 0;
    let layerZCounter = 0;
    let progressiveRedrawSeq = 0;
    let progressiveRedrawTimers = [];
    let prefetchTimer = null;
    let prefetchSeq = 0;
    let prefetchQueue = [];
    let prefetchActive = 0;
    let prefetchController = null;
    let prefetchContextKey = '';
    const prefetchSeenUrls = new Map();
    const layerPool = new Map(); // poolKey → L.tileLayer

    function selectionKey() {
        const { satId, sector, channel } = getSelection();
        return `${satId}|${sector}|${channel}`;
    }

    function poolKey(frameKey) {
        return `${selectionKey()}|${String(frameKey || '')}`;
    }

    function tileTemplate(frameKey, options = {}) {
        const { satId, sector, channel } = getSelection();
        const renderLive = options?.renderLive !== false;
        const params = new URLSearchParams({
            sat_id: satId,
            sector,
            channel,
            frame_key: String(frameKey || ''),
            render_live: renderLive ? '1' : '0',
            rv: String(getCatalog()?.render_version || 'products'),
            t: String(tileRefreshToken || 0),
        });
        return apiUrl(`/api/satellite-v2/tile/{z}/{x}/{y}?${params.toString()}`);
    }

    function tileUrlForCoords(frameKey, zoomLevel, tileX, tileY, options = {}) {
        return tileTemplate(frameKey, options)
            .replace('{z}', String(zoomLevel))
            .replace('{x}', String(tileX))
            .replace('{y}', String(tileY));
    }

    function frameByKey(frameKey) {
        return frames.find((frame) => String(frame?.frame_key || '') === String(frameKey || '')) || null;
    }

    function frameMaxNativeZoom(frame) {
        const configuredZoom = Number(frame?.max_native_zoom ?? getCatalog()?.max_native_zoom);
        if (Number.isFinite(configuredZoom)) return configuredZoom;
        const zooms = Array.isArray(frame?.available_zooms)
            ? frame.available_zooms.map(Number).filter(Number.isFinite)
            : [];
        if (zooms.length) return Math.max(...zooms);
        const counts = frame?.tile_counts || {};
        const countZooms = Object.entries(counts)
            .filter(([, count]) => Number(count) > 0)
            .map(([zoom]) => Number(zoom))
            .filter(Number.isFinite);
        return countZooms.length ? Math.max(...countZooms) : null;
    }

    function minNativeZoomForSector() {
        const sector = String(getSelection().sector || '').toUpperCase();
        if (sector === 'FULLDISK') return 1;
        if (sector === 'MESO1' || sector === 'MESO2') return 7;
        return 5; // CONUS
    }

    function effectiveTileZoom(frame = null) {
        const maxNativeZoom = Number(frameMaxNativeZoom(frame));
        const minNativeZoom = Number(minNativeZoomForSector());
        let zoomLevel = Math.round(map.getZoom());
        if (Number.isFinite(maxNativeZoom)) zoomLevel = Math.min(zoomLevel, maxNativeZoom);
        if (Number.isFinite(minNativeZoom)) zoomLevel = Math.max(zoomLevel, minNativeZoom);
        return Math.max(0, zoomLevel);
    }

    // ── Layer readiness ─────────────────────────────────────────────────────
    function layerTargetZoom(layer, zoomLevel) {
        const maxNativeZoom = Number(layer?.options?.maxNativeZoom);
        const minNativeZoom = Number(layer?.options?.minNativeZoom);
        let targetZoom = Math.round(zoomLevel);
        if (Number.isFinite(maxNativeZoom)) targetZoom = Math.min(targetZoom, maxNativeZoom);
        if (Number.isFinite(minNativeZoom)) targetZoom = Math.max(targetZoom, minNativeZoom);
        return targetZoom;
    }

    function layerHasLoadedTilesForZoom(layer, zoomLevel) {
        if (!layer || !Number.isFinite(zoomLevel)) return false;
        const targetZoom = layerTargetZoom(layer, zoomLevel);
        const targetTiles = Object.values(layer._tiles || {}).filter((rec) => (
            rec?.coords?.z === targetZoom && rec.current !== false
        ));
        if (!targetTiles.length) return false;
        return targetTiles.every((rec) => {
            const element = rec?.el;
            const imageOk = !element || (element.complete !== false && Number(element.naturalWidth || 0) > 0);
            return rec?.loaded && imageOk;
        });
    }

    function layerHasAnyLoadedTileForZoom(layer, zoomLevel) {
        if (!layer || !Number.isFinite(zoomLevel)) return false;
        const targetZoom = layerTargetZoom(layer, zoomLevel);
        return Object.values(layer._tiles || {}).some((rec) => {
            if (rec?.coords?.z !== targetZoom || rec.current === false || !rec?.loaded) return false;
            const element = rec?.el;
            return !element || (element.complete !== false && Number(element.naturalWidth || 0) > 0);
        });
    }

    function layerReadyForSwap(layer, zoomLevel) {
        return layerHasLoadedTilesForZoom(layer, zoomLevel) && layer._loading !== true;
    }

    function setLayerZIndex(layer, active = false) {
        if (!layer || typeof layer.setZIndex !== 'function') return;
        if (active) {
            layerZCounter += 1;
            layer.setZIndex(1000 + layerZCounter);
            return;
        }
        layer.setZIndex(1);
    }

    // ── Layer pool / hot-frame window ───────────────────────────────────────
    function getOrCreateLayer(frameKey) {
        const key = poolKey(frameKey);
        if (!layerPool.has(key)) {
            const frame = frameByKey(frameKey);
            const maxNativeZoom = frameMaxNativeZoom(frame);
            const layer = leaflet.tileLayer(tileTemplate(frameKey), {
                pane: LAYER_PANE,
                maxZoom: 19,
                ...(Number.isFinite(maxNativeZoom) ? { maxNativeZoom } : {}),
                minNativeZoom: minNativeZoomForSector(),
                opacity,
                updateWhenIdle: false,
                updateWhenZooming: false,
                keepBuffer: 4,
                crossOrigin: true,
            });
            layer.on('tileerror', () => {
                layer._satLoadCompleteKey = '';
                const retryCount = Number(layer._satTileErrorCount || 0) + 1;
                layer._satTileErrorCount = retryCount;
                if (retryCount > 8 || !enabled || !map.hasLayer(layer)) return;
                if (layer._satTileErrorRetryTimer) clearTimeout(layer._satTileErrorRetryTimer);
                const retryDelayMs = Math.min(6000, 900 + retryCount * 500);
                layer._satTileErrorRetryTimer = setTimeout(() => {
                    layer._satTileErrorRetryTimer = null;
                    if (!enabled || !map.hasLayer(layer)) return;
                    tileRefreshToken = Date.now();
                    layer.setUrl(tileTemplate(frameKey), false);
                    scheduleProgressiveRedraws(layer, frameKey, { force: true });
                }, retryDelayMs);
            });
            layerPool.set(key, layer);
        }
        return layerPool.get(key);
    }

    function shouldRetainLayers() {
        return frames.length > 0 && frames.length <= RETAIN_LAYER_LIMIT;
    }

    function hotFrameIndexes(activeIndex = frameIndex) {
        const count = frames.length;
        const indexes = new Set();
        if (!count) return indexes;
        const center = Math.max(0, Math.min(count - 1, Number(activeIndex) || 0));
        const radius = Math.max(0, Math.min(HOT_FRAME_RADIUS, count - 1));
        if (count <= radius * 2 + 1) {
            for (let idx = 0; idx < count; idx += 1) indexes.add(idx);
            return indexes;
        }
        for (let offset = -radius; offset <= radius; offset += 1) {
            indexes.add((center + offset + count) % count);
        }
        return indexes;
    }

    function refreshHotFrameWindow(activeIndex = frameIndex, keepLayers = new Set()) {
        if (!frames.length || !enabled) return;
        const active = Math.max(0, Math.min(frames.length - 1, Number(activeIndex) || 0));
        const hotLayers = new Set(keepLayers);
        hotFrameIndexes(active).forEach((idx) => {
            const frameKey = frames[idx]?.frame_key || '';
            if (!frameKey) return;
            const layer = getOrCreateLayer(frameKey);
            if (!map.hasLayer(layer)) layer.addTo(map);
            layer.setOpacity(idx === active ? opacity : 0);
            setLayerZIndex(layer, idx === active);
            hotLayers.add(layer);
        });
        layerPool.forEach((layer) => {
            if (!layer || hotLayers.has(layer)) return;
            if (shouldRetainLayers() && map.hasLayer(layer)) {
                layer.setOpacity(0);
                setLayerZIndex(layer, false);
                return;
            }
            if (map.hasLayer(layer)) map.removeLayer(layer);
        });
    }

    function hideInactiveLayers(currentLayer, previousLayer = null) {
        refreshHotFrameWindow(frameIndex, new Set([currentLayer, previousLayer].filter(Boolean)));
    }

    // ── Progressive redraw retries ──────────────────────────────────────────
    function cancelProgressiveRedraws() {
        progressiveRedrawSeq += 1;
        progressiveRedrawTimers.forEach((timerId) => clearTimeout(timerId));
        progressiveRedrawTimers = [];
    }

    function scheduleProgressiveRedraws(layer, frameKey, options = {}) {
        if (!layer || !frameKey || !enabled) return;
        const forceRetry = options?.force === true;
        const retryKey = `${frameKey}|${Math.round(map.getZoom())}`;
        const retainLayers = shouldRetainLayers();
        if (forceRetry) {
            layer._satProgressiveRetryKey = '';
            layer._satLoadCompleteKey = '';
        }
        if (!forceRetry && retainLayers && layer._satProgressiveRetryKey === retryKey) return;
        if (!forceRetry && layer._satLoadCompleteKey === retryKey) return;
        if (!retainLayers) cancelProgressiveRedraws();
        layer._satProgressiveRetryKey = retryKey;
        const markLayerLoaded = () => {
            if (!layerReadyForSwap(layer, map.getZoom())) return;
            layer._satLoadCompleteKey = retryKey;
            layer._satTileErrorCount = 0;
            layer.off('load', markLayerLoaded);
        };
        if (layerReadyForSwap(layer, map.getZoom())) {
            markLayerLoaded();
            return;
        }
        layer.on('load', markLayerLoaded);
        const redrawSeq = progressiveRedrawSeq;
        const timers = PROGRESSIVE_REDRAW_DELAYS_MS.map((delayMs) => setTimeout(() => {
            if (redrawSeq !== progressiveRedrawSeq) return;
            if (!enabled || !map.hasLayer(layer)) return;
            if (!retainLayers && activeLayer !== layer) return;
            if (layer._satLoadCompleteKey === retryKey) return;
            tileRefreshToken = Date.now();
            layer.setUrl(tileTemplate(frameKey), false);
        }, delayMs));
        progressiveRedrawTimers.push(...timers);
    }

    // ── Crossfade ───────────────────────────────────────────────────────────
    async function crossfadeLayers(oldLayer, newLayer, canContinue) {
        if (!oldLayer || !newLayer || !enabled) return true;
        newLayer.setOpacity(0);
        await new Promise((resolve) => requestAnimationFrame(resolve));
        await new Promise((resolve) => requestAnimationFrame(resolve));
        if (!canContinue()) {
            if (map.hasLayer(newLayer)) map.removeLayer(newLayer);
            return false;
        }
        const transitionElements = (overlay) => {
            const elements = [];
            const root = overlay._container || null;
            if (root) elements.push(root);
            Object.values(overlay._tiles || {}).forEach((rec) => {
                if (rec?.el) elements.push(rec.el);
            });
            return elements;
        };
        const oldElements = transitionElements(oldLayer);
        const newElements = transitionElements(newLayer);
        oldElements.forEach((el) => { el.style.transition = `opacity ${CROSSFADE_MS}ms linear`; });
        newElements.forEach((el) => { el.style.transition = `opacity ${CROSSFADE_MS}ms linear`; });
        // The old layer stays in the pool underneath (never removed here), so
        // scrub playback stays blink-free even on slow tile fills.
        if (map.hasLayer(oldLayer)) oldLayer.setOpacity(0);
        newLayer.setOpacity(opacity);
        setTimeout(() => {
            oldElements.forEach((el) => { el.style.transition = ''; });
            newElements.forEach((el) => { el.style.transition = ''; });
        }, CROSSFADE_MS);
        return true;
    }

    // ── Frame swap ──────────────────────────────────────────────────────────
    function canApplyFrame(seq) {
        return seq === renderSeq && enabled;
    }

    async function waitForLayerReady(layer, zoomLevel, seq, timeoutMs = TILE_READY_TIMEOUT_MS) {
        if (!layer || layerReadyForSwap(layer, zoomLevel)) return true;
        return new Promise((resolve) => {
            let settled = false;
            let timeoutId = null;
            const finish = (ready) => {
                if (settled) return;
                settled = true;
                layer.off('load', onLoad);
                clearTimeout(timeoutId);
                resolve(ready);
            };
            const onLoad = () => finish(layerHasLoadedTilesForZoom(layer, zoomLevel));
            timeoutId = setTimeout(() => {
                finish(layerHasLoadedTilesForZoom(layer, zoomLevel));
            }, timeoutMs);
            if (!canApplyFrame(seq)) {
                finish(false);
                return;
            }
            layer.on('load', onLoad);
        });
    }

    async function showFrame(index, options = {}) {
        if (!frames.length || !enabled) return false;
        const waitForTiles = options?.waitForTiles === true;
        const forceReloadSameLayer = options?.forceReloadSameLayer === true;
        const requestedTileTimeoutMs = Number(options?.tileTimeoutMs);
        const tileTimeoutMs = Number.isFinite(requestedTileTimeoutMs)
            ? Math.max(1000, requestedTileTimeoutMs)
            : TILE_READY_TIMEOUT_MS;
        const clamped = Math.max(0, Math.min(frames.length - 1, Number(index) || 0));
        const frame = frames[clamped];
        const frameKey = frame?.frame_key || '';
        if (!frameKey) return false;

        const nextLayer = getOrCreateLayer(frameKey);
        const targetZoom = map.getZoom();
        const prevLayer = activeLayer;
        const seq = ++renderSeq;

        const applyFrame = () => {
            activeLayer = nextLayer;
            frameIndex = clamped;
            scheduleProgressiveRedraws(nextLayer, frameKey);
            schedulePrefetch();
        };

        if (prevLayer === nextLayer) {
            if (forceReloadSameLayer) {
                nextLayer.setUrl(tileTemplate(frameKey), false);
                if (typeof nextLayer.redraw === 'function') nextLayer.redraw();
            }
            if (!canApplyFrame(seq)) return false;
            applyFrame();
            return true;
        }

        const swapToken = ++pendingSwapToken;

        if (!map.hasLayer(nextLayer)) nextLayer.addTo(map);
        nextLayer.setOpacity(prevLayer ? 0 : opacity);
        setLayerZIndex(nextLayer, true);
        hideInactiveLayers(nextLayer, prevLayer);

        const ready = waitForTiles
            ? await waitForLayerReady(nextLayer, targetZoom, seq, tileTimeoutMs)
            : true;
        if (!ready || swapToken !== pendingSwapToken || !canApplyFrame(seq)) {
            if (!prevLayer && ready === false && layerHasAnyLoadedTileForZoom(nextLayer, targetZoom)
                && swapToken === pendingSwapToken && canApplyFrame(seq)) {
                applyFrame();
                return true;
            }
            if (map.hasLayer(nextLayer)) map.removeLayer(nextLayer);
            return false;
        }

        if (prevLayer && map.hasLayer(prevLayer)) {
            const applied = await crossfadeLayers(
                prevLayer,
                nextLayer,
                () => swapToken === pendingSwapToken && canApplyFrame(seq),
            );
            if (!applied) return false;
        } else {
            nextLayer.setOpacity(opacity);
        }

        if (swapToken !== pendingSwapToken || !canApplyFrame(seq)) return false;
        applyFrame();
        hideInactiveLayers(nextLayer);
        return true;
    }

    // ── Viewport tile prefetch ──────────────────────────────────────────────
    function viewportTileCoords(zoomLevel) {
        if (!Number.isFinite(zoomLevel) || !map.getBounds) return [];
        const bounds = map.getBounds();
        const northWest = map.project(bounds.getNorthWest(), zoomLevel);
        const southEast = map.project(bounds.getSouthEast(), zoomLevel);
        const maxTileIndex = Math.max(0, (2 ** Math.round(zoomLevel)) - 1);
        const pad = PREFETCH_TILE_BUFFER;
        const minTileX = Math.max(0, Math.floor(Math.min(northWest.x, southEast.x) / TILE_SIZE) - pad);
        const maxTileX = Math.min(maxTileIndex, Math.floor(Math.max(northWest.x, southEast.x) / TILE_SIZE) + pad);
        const minTileY = Math.max(0, Math.floor(Math.min(northWest.y, southEast.y) / TILE_SIZE) - pad);
        const maxTileY = Math.min(maxTileIndex, Math.floor(Math.max(northWest.y, southEast.y) / TILE_SIZE) + pad);
        const centerPoint = map.project(map.getCenter(), zoomLevel);
        const centerTileX = centerPoint.x / TILE_SIZE;
        const centerTileY = centerPoint.y / TILE_SIZE;
        const coords = [];
        for (let tileY = minTileY; tileY <= maxTileY; tileY += 1) {
            for (let tileX = minTileX; tileX <= maxTileX; tileX += 1) {
                coords.push({ tileX, tileY });
            }
        }
        coords.sort((left, right) => {
            const leftDistance = Math.abs(left.tileX - centerTileX) + Math.abs(left.tileY - centerTileY);
            const rightDistance = Math.abs(right.tileX - centerTileX) + Math.abs(right.tileY - centerTileY);
            return leftDistance - rightDistance;
        });
        return coords.slice(0, PREFETCH_MAX_TILES_PER_FRAME);
    }

    function prefetchFrameIndexes(activeIndex = frameIndex) {
        const frameCount = frames.length;
        const indexes = [];
        if (frameCount < 2) return indexes;
        const active = Math.max(0, Math.min(frameCount - 1, Number(activeIndex) || 0));
        const seen = new Set([active]);
        for (let offset = 1; offset <= PREFETCH_AHEAD_FRAMES; offset += 1) {
            const idx = (active + offset) % frameCount;
            if (!seen.has(idx)) { seen.add(idx); indexes.push(idx); }
        }
        for (let offset = 1; offset <= PREFETCH_BEHIND_FRAMES; offset += 1) {
            const idx = (active - offset + frameCount) % frameCount;
            if (!seen.has(idx)) { seen.add(idx); indexes.push(idx); }
        }
        return indexes;
    }

    function currentPrefetchContextKey() {
        if (!frames.length || !enabled) return '';
        const zoomLevel = Math.round(map.getZoom());
        const bounds = map.getBounds();
        const northWest = map.project(bounds.getNorthWest(), zoomLevel);
        const southEast = map.project(bounds.getSouthEast(), zoomLevel);
        const minTileX = Math.floor(Math.min(northWest.x, southEast.x) / TILE_SIZE);
        const maxTileX = Math.floor(Math.max(northWest.x, southEast.x) / TILE_SIZE);
        const minTileY = Math.floor(Math.min(northWest.y, southEast.y) / TILE_SIZE);
        const maxTileY = Math.floor(Math.max(northWest.y, southEast.y) / TILE_SIZE);
        return [selectionKey(), zoomLevel, minTileX, maxTileX, minTileY, maxTileY].join('|');
    }

    function cancelPrefetch() {
        prefetchSeq += 1;
        if (prefetchTimer) {
            clearTimeout(prefetchTimer);
            prefetchTimer = null;
        }
        if (prefetchController) {
            try { prefetchController.abort(); } catch (_) { /* ignore */ }
            prefetchController = null;
        }
        prefetchQueue = [];
        prefetchActive = 0;
        prefetchContextKey = '';
        prefetchSeenUrls.clear();
    }

    function enqueuePrefetch(seq) {
        if (seq !== prefetchSeq || !frames.length || !enabled) return;
        const nowMs = Date.now();
        const queuedUrls = new Set(prefetchQueue.map((item) => item.url));
        for (const idx of prefetchFrameIndexes(frameIndex)) {
            const frame = frames[idx];
            const frameKey = frame?.frame_key || '';
            if (!frameKey) continue;
            const zoomLevel = effectiveTileZoom(frame);
            for (const coord of viewportTileCoords(zoomLevel)) {
                if (prefetchQueue.length >= PREFETCH_MAX_QUEUE_TILES) return;
                // Prefetch skips live rendering: cached tiles only, so playback
                // warm-up never triggers heavy on-demand renders.
                const url = tileUrlForCoords(frameKey, zoomLevel, coord.tileX, coord.tileY, { renderLive: false });
                const lastSeenMs = Number(prefetchSeenUrls.get(url));
                if (queuedUrls.has(url) || (Number.isFinite(lastSeenMs) && nowMs - lastSeenMs < PREFETCH_RETRY_AFTER_MS)) continue;
                queuedUrls.add(url);
                prefetchSeenUrls.set(url, nowMs);
                if (prefetchSeenUrls.size > PREFETCH_SEEN_LIMIT) {
                    const oldestUrl = prefetchSeenUrls.keys().next().value;
                    if (oldestUrl) prefetchSeenUrls.delete(oldestUrl);
                }
                prefetchQueue.push({ url });
            }
        }
    }

    function pumpPrefetch(seq) {
        if (seq !== prefetchSeq || !enabled) return;
        if (!prefetchController) prefetchController = new AbortController();
        const { signal } = prefetchController;
        while (prefetchActive < PREFETCH_MAX_CONCURRENT && prefetchQueue.length) {
            const item = prefetchQueue.shift();
            prefetchActive += 1;
            fetch(item.url, { cache: 'force-cache', signal })
                .then((response) => (response.ok ? response.blob() : null))
                .catch(() => { })
                .finally(() => {
                    if (seq !== prefetchSeq) return;
                    prefetchActive = Math.max(0, prefetchActive - 1);
                    pumpPrefetch(seq);
                });
        }
    }

    function schedulePrefetch(delayMs = PREFETCH_DEBOUNCE_MS) {
        if (!frames.length || !enabled) {
            cancelPrefetch();
            return;
        }
        const contextKey = currentPrefetchContextKey();
        if (!contextKey) return;
        if (contextKey !== prefetchContextKey) {
            cancelPrefetch();
            prefetchContextKey = contextKey;
        }
        if (prefetchTimer) clearTimeout(prefetchTimer);
        const seq = prefetchSeq;
        prefetchTimer = setTimeout(() => {
            prefetchTimer = null;
            enqueuePrefetch(seq);
            pumpPrefetch(seq);
        }, Math.max(0, Number(delayMs) || 0));
    }

    // ── Lifecycle ───────────────────────────────────────────────────────────
    function cancelPendingSwap() {
        pendingSwapToken += 1;
    }

    function invalidate() {
        renderSeq += 1;
        cancelPendingSwap();
        cancelProgressiveRedraws();
        cancelPrefetch();
    }

    function clearPool() {
        invalidate();
        layerPool.forEach((layer) => {
            if (layer?._satTileErrorRetryTimer) {
                clearTimeout(layer._satTileErrorRetryTimer);
                layer._satTileErrorRetryTimer = null;
            }
            if (map.hasLayer(layer)) map.removeLayer(layer);
        });
        layerPool.clear();
        layerZCounter = 0;
        activeLayer = null;
    }

    return Object.freeze({
        setFrames(newFrames) {
            frames = Array.isArray(newFrames) ? newFrames : [];
            if (frameIndex >= frames.length) frameIndex = Math.max(0, frames.length - 1);
        },
        getFrameIndex: () => frameIndex,
        showFrame,
        primeLayers: (activeIndex) => refreshHotFrameWindow(activeIndex),
        schedulePrefetch,
        cancelPendingSwap,
        invalidate,
        clearPool,
        bumpTileRefreshToken() {
            tileRefreshToken = Date.now();
        },
        setOpacity(value) {
            opacity = Math.max(0.1, Math.min(1, Number(value) || 1));
            if (activeLayer) activeLayer.setOpacity(opacity);
        },
        destroy() {
            enabled = false;
            clearPool();
        },
    });
}
