(function () {
    'use strict';

    const DEFAULT_CONTROLS = {
        'satellite-sat-id': 'goes19',
        'satellite-sector': 'CONUS',
        'satellite-channel': 'Channel13',
        'satellite-source': 'aws',
        'satellite-lookback-hours': '2'
    };

    const SATELLITE_AUTO_REFRESH_MS = 300000; // 5 minutes

    let mapInstance = null;
    let baseLayer = null;
    let satelliteLayer = null;

    let scrubberFrames = [];
    let scrubberIndex = 0;

    let autoRefreshTimer = null;
    let hasLoadedFrames = false;
    let isLoadingFrames = false;
    let tileRefreshToken = 0;
    let catalogRenderVersion = 'products';

    function byId(id) { return document.getElementById(id); }
    function value(id) { const el = byId(id); return el ? el.value : ''; }

    function applyControlDefaults() {
        Object.entries(DEFAULT_CONTROLS).forEach(([id, controlValue]) => {
            const el = byId(id);
            if (!el) {
                return;
            }
            el.value = controlValue;
        });
    }

    function ensureMap() {
        if (mapInstance) {
            return;
        }

        mapInstance = L.map('satellite-map', {
            zoomControl: true,
            preferCanvas: true,
            worldCopyJump: true,
        }).setView([35.5, -79.0], 5);

        baseLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap &copy; CartoDB',
            subdomains: 'abcd',
            maxZoom: 19,
        }).addTo(mapInstance);

        setTimeout(() => mapInstance.invalidateSize(), 75);
    }

    function tileTemplateForFrame(frameKey) {
        const params = new URLSearchParams({
            sat_id: value('satellite-sat-id') || 'goes19',
            sector: value('satellite-sector') || 'CONUS',
            channel: value('satellite-channel') || 'Channel13',
            frame_key: frameKey,
            rv: catalogRenderVersion,
            t: String(tileRefreshToken || 0),
        });
        return apiUrl(`/api/satellite-v2/tile/{z}/{x}/{y}?${params.toString()}`);
    }

    function updateFrameMeta() {
        const meta = byId('satellite-frame-meta');
        if (!meta) {
            return;
        }
        if (!scrubberFrames.length) {
            meta.textContent = 'No frames loaded.';
            return;
        }
        meta.textContent = `Loaded ${scrubberFrames.length} frames. Current index: ${scrubberIndex + 1}.`;
    }

    function frameKeyAt(index, frames = scrubberFrames) {
        const frame = frames[index];
        return frame && frame.frame_key ? String(frame.frame_key) : '';
    }

    function displayedFrameKey() {
        return frameKeyAt(scrubberIndex);
    }

    function latestFrameKey(frames = scrubberFrames) {
        return frames.length ? frameKeyAt(frames.length - 1, frames) : '';
    }

    function isDisplayingLatestFrame() {
        if (!scrubberFrames.length) {
            return true;
        }
        return scrubberIndex >= scrubberFrames.length - 1 || displayedFrameKey() === latestFrameKey();
    }

    function indexForFrameKey(frames, frameKey) {
        const key = String(frameKey || '');
        if (!key) {
            return -1;
        }
        return frames.findIndex((frame) => String(frame?.frame_key || '') === key);
    }

    function updateScrubberFrame(index) {
        const scrubber = byId('scrubber-range');
        const timestamp = byId('scrubber-timestamp');
        if (!scrubber || !timestamp || !scrubberFrames.length) {
            return;
        }

        const clamped = Math.max(0, Math.min(scrubberFrames.length - 1, Number(index) || 0));
        scrubberIndex = clamped;
        scrubber.value = String(clamped);

        const frame = scrubberFrames[clamped];
        timestamp.textContent = frame.timestamp_utc || `Frame ${clamped + 1}`;

        const urlTemplate = tileTemplateForFrame(frame.frame_key);
        if (!satelliteLayer) {
            satelliteLayer = L.tileLayer(urlTemplate, {
                maxZoom: 19,
                opacity: 0.92,
                updateWhenIdle: false,
                updateWhenZooming: false,
                keepBuffer: 4,
                crossOrigin: true,
            }).addTo(mapInstance);
        } else {
            satelliteLayer.setUrl(urlTemplate, false);
        }

        updateFrameMeta();
    }

    function showScrubber() {
        const controls = byId('scrubber-controls');
        const scrubber = byId('scrubber-range');
        if (!controls || !scrubber) {
            return;
        }

        scrubber.min = '0';
        scrubber.max = String(Math.max(0, scrubberFrames.length - 1));
        scrubber.step = '1';
        controls.style.display = scrubberFrames.length ? 'grid' : 'none';
    }

    async function loadFrames(options = {}) {
        const silent = Boolean(options.silent);
        const refresh = Boolean(options.refresh);
        const preserveFrameKey = String(options.preserveFrameKey || '');
        const preferLatest = options.preferLatest !== false;

        if (isLoadingFrames) {
            return;
        }
        isLoadingFrames = true;

        try {
            ensureMap();

            const params = new URLSearchParams({
                sat_id: value('satellite-sat-id') || 'goes19',
                sector: value('satellite-sector') || 'CONUS',
                channel: value('satellite-channel') || 'Channel13',
                hours: value('satellite-lookback-hours') || '2',
                max_frames: '90',
                refresh: refresh ? 'true' : 'false',
            });

            if (!silent) {
                showProgress(8, 'Loading satellite frame timeline...');
                setStatus('Fetching live satellite frames...');
                window.setOutputMeta?.({ state: 'running' });
            }

            const response = await fetch(apiUrl(`/api/satellite-v2/catalog?${params.toString()}`));
            const data = await response.json();

            if (!response.ok || (data.status !== 'success' && data.status !== 'stale')) {
                throw new Error(data.detail || data.message || 'Failed to load satellite frames');
            }

            const nextFrames = Array.isArray(data.frames) ? data.frames.filter((f) => f && f.frame_key) : [];
            catalogRenderVersion = String(data.render_version || catalogRenderVersion || 'products');
            if (silent && !nextFrames.length && scrubberFrames.length) {
                return;
            }

            const previousFrameKey = displayedFrameKey();
            const nextLatestKey = latestFrameKey(nextFrames);
            let nextIndex = Math.max(0, nextFrames.length - 1);

            if (!preferLatest && preserveFrameKey) {
                const preservedIndex = indexForFrameKey(nextFrames, preserveFrameKey);
                if (preservedIndex >= 0) {
                    nextIndex = preservedIndex;
                }
            }

            scrubberFrames = nextFrames;
            showScrubber();

            if (silent && nextLatestKey && nextLatestKey === previousFrameKey) {
                tileRefreshToken = Date.now();
            }

            window.setOutputMeta?.({
                source: 'aws',
                requestedSource: 'aws',
                dataMode: 'current',
            });

            if (!scrubberFrames.length) {
                if (satelliteLayer) {
                    mapInstance.removeLayer(satelliteLayer);
                    satelliteLayer = null;
                }
                setStatus('No satellite frames available for this selection.');
                hasLoadedFrames = false;
                updateFrameMeta();
                return;
            }

            updateScrubberFrame(nextIndex);
            if (!silent) {
                setStatus(`Satellite frames loaded (${scrubberFrames.length}).`);
            } else if (preferLatest && nextLatestKey && nextLatestKey !== previousFrameKey) {
                const frame = scrubberFrames[scrubberIndex];
                setStatus(`Satellite auto-updated to ${frame.timestamp_utc || nextLatestKey}.`);
            }
            hasLoadedFrames = true;
            ensureAutoRefreshTimer();

            if (!silent) {
                showProgress(100, 'Completed');
            }
        } catch (error) {
            if (!silent) {
                hasLoadedFrames = false;
                setStatus(`Error: ${error.message}`);
                window.setOutputMeta?.({ state: 'unavailable' });
            } else {
                console.warn('Satellite auto-refresh failed:', error);
            }
        } finally {
            isLoadingFrames = false;
            if (!silent) {
                setTimeout(hideProgress, 1500);
            }
        }
    }

    function refreshSatelliteForActiveMode(options = {}) {
        const followLatest = isDisplayingLatestFrame();
        return loadFrames({
            ...options,
            refresh: true,
            preferLatest: followLatest,
            preserveFrameKey: followLatest ? '' : displayedFrameKey(),
        });
    }

    function shouldAutoRefresh() {
        return hasLoadedFrames && !document.hidden;
    }

    function ensureAutoRefreshTimer() {
        if (autoRefreshTimer !== null) {
            return;
        }
        autoRefreshTimer = window.setInterval(() => {
            if (!shouldAutoRefresh()) {
                return;
            }
            refreshSatelliteForActiveMode({ silent: true });
        }, SATELLITE_AUTO_REFRESH_MS);
    }

    document.addEventListener('DOMContentLoaded', () => {
        applyControlDefaults();
        ensureMap();

        byId('satellite-generate')?.addEventListener('click', () => loadFrames({ refresh: true }));

        byId('scrubber-range')?.addEventListener('input', (event) => {
            updateScrubberFrame(event.target.value);
        });
        byId('scrubber-step-back')?.addEventListener('click', () => {
            updateScrubberFrame(scrubberIndex - 1);
        });
        byId('scrubber-step-fwd')?.addEventListener('click', () => {
            updateScrubberFrame(scrubberIndex + 1);
        });

        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && shouldAutoRefresh()) {
                refreshSatelliteForActiveMode({ silent: true });
            }
        });

        loadFrames({ refresh: true });
    });
})();
