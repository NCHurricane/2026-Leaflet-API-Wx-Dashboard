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
            source: value('satellite-source') || 'aws',
            frame_key: frameKey,
        });
        return apiUrl(`/api/satellite/tile/{z}/{x}/{y}?${params.toString()}`);
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
                updateWhenIdle: true,
                updateWhenZooming: false,
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

        try {
            ensureMap();

            const params = new URLSearchParams({
                sat_id: value('satellite-sat-id') || 'goes19',
                sector: value('satellite-sector') || 'CONUS',
                channel: value('satellite-channel') || 'Channel13',
                source: value('satellite-source') || 'aws',
                hours: value('satellite-lookback-hours') || '2',
                max_frames: '90',
            });

            if (!silent) {
                showProgress(8, 'Loading satellite frame timeline...');
                setStatus('Fetching live satellite frames...');
                window.setOutputMeta?.({ state: 'running' });
            }

            const response = await fetch(apiUrl(`/api/satellite/live/frames?${params.toString()}`));
            const data = await response.json();

            if (!response.ok || data.status === 'error') {
                throw new Error(data.detail || data.message || 'Failed to load satellite frames');
            }

            scrubberFrames = Array.isArray(data.frames) ? data.frames.filter((f) => f && f.frame_key) : [];
            showScrubber();

            window.setOutputMeta?.({
                source: data.source || data.data_source || value('satellite-source'),
                requestedSource: value('satellite-source'),
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

            updateScrubberFrame(scrubberFrames.length - 1);
            setStatus(`Satellite frames loaded (${scrubberFrames.length}).`);
            hasLoadedFrames = true;
            ensureAutoRefreshTimer();

            if (!silent) {
                showProgress(100, 'Completed');
            }
        } catch (error) {
            hasLoadedFrames = false;
            setStatus(`Error: ${error.message}`);
            window.setOutputMeta?.({ state: 'unavailable' });
        } finally {
            if (!silent) {
                setTimeout(hideProgress, 1500);
            }
        }
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
            loadFrames({ silent: true });
        }, SATELLITE_AUTO_REFRESH_MS);
    }

    document.addEventListener('DOMContentLoaded', () => {
        applyControlDefaults();
        ensureMap();

        byId('satellite-generate')?.addEventListener('click', () => loadFrames());

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
                loadFrames({ silent: true });
            }
        });

        loadFrames();
    });
})();
