(function () {
    'use strict';

    const DEFAULT_CONTROLS = {
        'radar-site': 'KMHX',
        'radar-level': 'Level 2',
        'radar-product-l3': 'N0B',
        'radar-product-l2': 'reflectivity',
        'radar-source': 'aws',
        'radar-quick-range': 'current',
        'radar-user-tz': 'America/New_York',
        'radar-single-frame': false,
        'radar-frames': '150',
        'radar-fps': '4',
        'radar-sm-speed': '30',
        'radar-sm-dir': '225',
        'radar-extent-mode': '0'
    };

    const RADAR_ARCHIVE_MAX_FRAMES = '150';
    const RADAR_CURRENT_LOOKBACK_HOURS = 0.25;
    const RADAR_AUTO_REFRESH_MS = 300000; // 5 minutes
    let radarAutoRefreshTimer = null;
    let hasGeneratedCurrentOutput = false;

    let extentSelector = null;
    let layeredFrames = [];
    let layeredIndex = 0;
    let layeredPath = '';
    let layeredStaticOverlaySrc = '';
    let layeredLegendOverlaySrc = '';
    let layeredCountiesOverlaySrc = '';
    let layeredStatesOverlaySrc = '';
    let layeredRingsOverlaySrc = '';
    let layeredPrefetchCache = new Map();
    const LAYERED_PREFETCH_RADIUS = 2;

    function byId(id) { return document.getElementById(id); }
    function value(id) { const el = byId(id); return el ? el.value : ''; }
    function checked(id) { const el = byId(id); return !!(el && el.checked); }

    function hideLayeredOutput() {
        const layeredContainer = byId('result-layered-container');
        const layeredControls = byId('layered-controls');
        const layeredLayerControls = byId('layered-layer-controls');
        const layerIds = ['result-basemap-image', 'result-alerts-image', 'result-radar-image', 'result-cities-image', 'result-counties-overlay-image', 'result-states-overlay-image', 'result-rings-overlay-image', 'result-static-overlay-image', 'result-legend-overlay-image', 'result-hud-right-image'];
        layeredFrames = [];
        layeredIndex = 0;
        layeredPath = '';
        layeredStaticOverlaySrc = '';
        layeredLegendOverlaySrc = '';
        layeredCountiesOverlaySrc = '';
        layeredStatesOverlaySrc = '';
        layeredRingsOverlaySrc = '';
        layeredPrefetchCache = new Map();
        layerIds.forEach((id) => {
            const img = byId(id);
            if (img) {
                img.src = '';
            }
        });
        if (layeredContainer) {
            layeredContainer.style.display = 'none';
        }
        if (layeredControls) {
            layeredControls.style.display = 'none';
        }
        if (layeredLayerControls) {
            layeredLayerControls.style.display = 'none';
        }
    }

    function layeredFrameSrc(index, key = 'url') {
        const frame = layeredFrames[index] || {};
        const value = frame?.[key] || '';
        return value ? apiUrl(value) : '';
    }

    function prefetchLayeredFrame(index) {
        if (index < 0 || index >= layeredFrames.length) {
            return;
        }
        const keys = ['alerts_url', 'radar_url', 'cities_url', 'legend_url', 'hud_right_url', 'states_url'];
        keys.forEach((key) => {
            const src = layeredFrameSrc(index, key);
            if (!src || layeredPrefetchCache.has(src)) {
                return;
            }
            const img = new Image();
            img.decoding = 'async';
            img.src = src;
            layeredPrefetchCache.set(src, img);
        });
    }

    function prefetchLayeredNeighbors(centerIndex) {
        for (let offset = -LAYERED_PREFETCH_RADIUS; offset <= LAYERED_PREFETCH_RADIUS; offset += 1) {
            if (offset === 0) {
                continue;
            }
            prefetchLayeredFrame(centerIndex + offset);
        }
    }

    function applyLayeredVisibility() {
        const radarLayer = byId('result-radar-image');
        const alertsLayer = byId('result-alerts-image');
        const citiesLayer = byId('result-cities-image');
        const countiesLayer = byId('result-counties-overlay-image');
        const statesLayer = byId('result-states-overlay-image');
        const ringsLayer = byId('result-rings-overlay-image');

        const setLayerState = (img, showId, opacityId) => {
            if (!img) {
                return;
            }
            const hasSource = !!img.getAttribute('src');
            const visible = checked(showId) && hasSource;
            img.style.display = visible ? 'block' : 'none';
            img.style.opacity = String(parseFloat(value(opacityId) || '1'));
        };

        setLayerState(radarLayer, 'layered-show-radar', 'layered-opacity-radar');
        setLayerState(alertsLayer, 'layered-show-alerts', 'layered-opacity-alerts');
        setLayerState(citiesLayer, 'layered-show-cities', 'layered-opacity-cities');
        setLayerState(countiesLayer, 'layered-show-counties', 'layered-opacity-counties');
        setLayerState(statesLayer, 'layered-show-states', 'layered-opacity-states');
        setLayerState(ringsLayer, 'layered-show-rings', 'layered-opacity-rings');
    }

    function updateLayeredFrame(index) {
        const alertsLayer = byId('result-alerts-image');
        const radarLayer = byId('result-radar-image');
        const citiesLayer = byId('result-cities-image');
        const countiesOverlayLayer = byId('result-counties-overlay-image');
        const statesOverlayLayer = byId('result-states-overlay-image');
        const ringsOverlayLayer = byId('result-rings-overlay-image');
        const staticOverlayLayer = byId('result-static-overlay-image');
        const legendOverlayLayer = byId('result-legend-overlay-image');
        const hudRightLayer = byId('result-hud-right-image');
        const timestamp = byId('layered-timestamp');
        const scrubber = byId('layered-scrubber');
        if (!timestamp || !scrubber || !layeredFrames.length) {
            return;
        }

        const clamped = Math.max(0, Math.min(layeredFrames.length - 1, Number(index) || 0));
        layeredIndex = clamped;
        const frame = layeredFrames[clamped];
        scrubber.value = String(clamped);

        const alertsSrc = layeredFrameSrc(clamped, 'alerts_url');
        const radarSrc = layeredFrameSrc(clamped, 'radar_url');
        const citiesSrc = layeredFrameSrc(clamped, 'cities_url');
        const countiesSrc = layeredFrameSrc(clamped, 'counties_url') || layeredCountiesOverlaySrc;
        const statesSrc = layeredFrameSrc(clamped, 'states_url') || layeredStatesOverlaySrc;
        const ringsSrc = layeredFrameSrc(clamped, 'rings_url') || layeredRingsOverlaySrc;
        const legendSrc = layeredFrameSrc(clamped, 'legend_url') || layeredLegendOverlaySrc;
        const hudRightSrc = layeredFrameSrc(clamped, 'hud_right_url');

        if (alertsLayer) {
            alertsLayer.src = alertsSrc;
            alertsLayer.style.display = alertsSrc ? 'block' : 'none';
        }
        if (radarLayer) {
            radarLayer.src = radarSrc;
            radarLayer.style.display = radarSrc ? 'block' : 'none';
        }
        if (citiesLayer) {
            citiesLayer.src = citiesSrc;
            citiesLayer.style.display = citiesSrc ? 'block' : 'none';
        }
        if (countiesOverlayLayer) {
            countiesOverlayLayer.src = countiesSrc;
            countiesOverlayLayer.style.display = countiesSrc ? 'block' : 'none';
        }
        if (statesOverlayLayer) {
            statesOverlayLayer.src = statesSrc;
            statesOverlayLayer.style.display = statesSrc ? 'block' : 'none';
        }
        if (ringsOverlayLayer) {
            ringsOverlayLayer.src = ringsSrc;
            ringsOverlayLayer.style.display = ringsSrc ? 'block' : 'none';
        }
        if (staticOverlayLayer) {
            staticOverlayLayer.src = layeredStaticOverlaySrc;
            staticOverlayLayer.style.display = layeredStaticOverlaySrc ? 'block' : 'none';
        }
        if (legendOverlayLayer) {
            legendOverlayLayer.src = legendSrc;
            legendOverlayLayer.style.display = legendSrc ? 'block' : 'none';
        }
        if (hudRightLayer) {
            hudRightLayer.src = hudRightSrc;
            hudRightLayer.style.display = hudRightSrc ? 'block' : 'none';
        }

        timestamp.textContent = frame.timestamp_local || frame.timestamp_utc || `Frame ${clamped + 1}`;
        applyLayeredVisibility();
        prefetchLayeredNeighbors(clamped);
    }

    function displayLayeredResult(data) {
        const layeredContainer = byId('result-layered-container');
        const layeredControls = byId('layered-controls');
        const layeredLayerControls = byId('layered-layer-controls');
        const basemap = byId('result-basemap-image');
        const alertsLayer = byId('result-alerts-image');
        const radarLayer = byId('result-radar-image');
        const citiesLayer = byId('result-cities-image');
        const countiesOverlayLayer = byId('result-counties-overlay-image');
        const statesOverlayLayer = byId('result-states-overlay-image');
        const ringsOverlayLayer = byId('result-rings-overlay-image');
        const staticOverlayLayer = byId('result-static-overlay-image');
        const legendOverlayLayer = byId('result-legend-overlay-image');
        const hudRightLayer = byId('result-hud-right-image');
        const scrubber = byId('layered-scrubber');
        const image = byId('result-image');
        const video = byId('result-video');

        if (!layeredContainer || !layeredControls || !layeredLayerControls || !basemap || !scrubber || !image || !video) {
            return false;
        }

        const basemapUrl = data?.basemap_url;
        const staticOverlayUrl = data?.static_overlay_url;
        const legendOverlayUrl = data?.layers?.legend || data?.legend_overlay_url || '';
        const countiesOverlayUrl = data?.layers?.counties || '';
        const statesOverlayUrl = data?.layers?.states || '';
        const ringsOverlayUrl = data?.layers?.range_rings || '';
        const frames = Array.isArray(data?.frames)
            ? data.frames.filter((f) => f && (f.radar_url || f.hud_right_url))
            : [];
        layeredPath = String(data?.layers_path || '');
        if (!basemapUrl || !frames.length) {
            return false;
        }

        image.style.display = 'none';
        video.style.display = 'none';

        layeredPrefetchCache = new Map();
        const syncLayeredAspect = () => {
            if (!layeredContainer || !basemap || !basemap.naturalWidth || !basemap.naturalHeight) {
                return;
            }
            layeredContainer.style.aspectRatio = `${basemap.naturalWidth} / ${basemap.naturalHeight}`;
        };
        basemap.onload = syncLayeredAspect;
        basemap.src = apiUrl(basemapUrl);
        syncLayeredAspect();
        layeredStaticOverlaySrc = staticOverlayUrl ? apiUrl(staticOverlayUrl) : '';
        layeredLegendOverlaySrc = legendOverlayUrl ? apiUrl(legendOverlayUrl) : '';
        layeredCountiesOverlaySrc = countiesOverlayUrl ? apiUrl(countiesOverlayUrl) : '';
        layeredStatesOverlaySrc = statesOverlayUrl ? apiUrl(statesOverlayUrl) : '';
        layeredRingsOverlaySrc = ringsOverlayUrl ? apiUrl(ringsOverlayUrl) : '';
        if (alertsLayer) {
            alertsLayer.src = '';
        }
        if (radarLayer) {
            radarLayer.src = '';
        }
        if (citiesLayer) {
            citiesLayer.src = '';
        }
        if (countiesOverlayLayer) {
            countiesOverlayLayer.src = '';
        }
        if (statesOverlayLayer) {
            statesOverlayLayer.src = '';
        }
        if (ringsOverlayLayer) {
            ringsOverlayLayer.src = '';
        }
        if (staticOverlayLayer) {
            staticOverlayLayer.src = '';
        }
        if (legendOverlayLayer) {
            legendOverlayLayer.src = '';
        }
        if (hudRightLayer) {
            hudRightLayer.src = '';
        }
        layeredFrames = frames;
        scrubber.min = '0';
        scrubber.max = String(frames.length - 1);
        scrubber.step = '1';

        updateLayeredFrame(0);
        prefetchLayeredFrame(0);
        applyLayeredVisibility();

        layeredContainer.style.display = 'block';
        layeredControls.style.display = 'grid';
        layeredLayerControls.style.display = 'block';
        return true;
    }

    async function saveCurrentLayeredFrame() {
        const layerStack = [
            byId('result-basemap-image'),
            byId('result-radar-image'),
            byId('result-alerts-image'),
            byId('result-counties-overlay-image'),
            byId('result-states-overlay-image'),
            byId('result-rings-overlay-image'),
            byId('result-cities-image'),
            byId('result-static-overlay-image'),
            byId('result-legend-overlay-image'),
            byId('result-hud-right-image')
        ].filter(Boolean);
        const basemap = byId('result-basemap-image');
        if (!basemap || !layeredFrames.length || !basemap.src) {
            return;
        }

        const frame = layeredFrames[layeredIndex] || {};
        const suffix = String(frame.timestamp_utc || layeredIndex).replace(/[^0-9A-Za-z_-]/g, '_');
        const filename = `radar_archive_frame_${suffix}.png`;

        // Must be called directly from the click gesture (before awaited work).
        let fileHandle = null;
        if (typeof window.showSaveFilePicker === 'function') {
            try {
                fileHandle = await window.showSaveFilePicker({
                    suggestedName: filename,
                    types: [{ description: 'PNG Image', accept: { 'image/png': ['.png'] } }]
                });
            } catch (err) {
                if (err?.name === 'AbortError') {
                    return;
                }
                throw err;
            }
        }

        // Fetch each image as a blob URL so the canvas is never cross-origin
        // tainted (happens when the page is opened as file:// but images are
        // served from http://127.0.0.1:8000).
        const fetchAsBlob = async (src) => {
            // Avoid conditional-cache responses (304) during export.
            let res = await fetch(src, { cache: 'no-store' });
            if (res.status === 304) {
                const separator = src.includes('?') ? '&' : '?';
                const bustedSrc = `${src}${separator}_export_ts=${Date.now()}`;
                res = await fetch(bustedSrc, { cache: 'reload' });
            }
            if (!res.ok) {
                throw new Error(`Image fetch failed (HTTP ${res.status}): ${src}`);
            }
            return URL.createObjectURL(await res.blob());
        };

        const loadBlobImage = (blobUrl) => new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = () => reject(new Error(`Blob image load failed: ${blobUrl}`));
            img.src = blobUrl;
        });

        const blobUrls = [];
        try {
            // Export layers in effective browser paint order by computed z-index.
            const srcs = layerStack
                .filter((img) => {
                    if (!img || !img.src) {
                        return false;
                    }
                    if (img.id === 'result-basemap-image') {
                        return true;
                    }
                    return img.style.display !== 'none';
                })
                .sort((a, b) => {
                    const za = parseInt(window.getComputedStyle(a).zIndex || '0', 10);
                    const zb = parseInt(window.getComputedStyle(b).zIndex || '0', 10);
                    return za - zb;
                })
                .map((img) => img.src);

            const blobs = await Promise.all(srcs.map(fetchAsBlob));
            blobs.forEach((u) => blobUrls.push(u));
            const images = await Promise.all(blobs.map(loadBlobImage));

            const baseImg = images[0];
            const canvas = document.createElement('canvas');
            canvas.width = baseImg.naturalWidth;
            canvas.height = baseImg.naturalHeight;
            const ctx = canvas.getContext('2d');
            // Fill canvas background so transparent margin areas (tick label strip,
            // colorbar strip) are the same dark colour as the dashboard canvas,
            // not transparent/white in the saved PNG.
            ctx.fillStyle = '#152238';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            images.forEach((img) => ctx.drawImage(img, 0, 0, canvas.width, canvas.height));

            const pngBlob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));

            if (fileHandle) {
                const writable = await fileHandle.createWritable();
                await writable.write(pngBlob);
                await writable.close();
            } else {
                // Fallback: <a download> for Firefox and other browsers.
                const blobUrl = URL.createObjectURL(pngBlob);
                const link = document.createElement('a');
                link.href = blobUrl;
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
            }
        } finally {
            blobUrls.forEach((u) => URL.revokeObjectURL(u));
        }
    }

    async function exportLayeredAnimation() {
        if (!layeredPath) {
            throw new Error('No layered output is available to export yet.');
        }

        const fallbackFilename = 'radar_archive_export.mp4';
        // Must be called directly from the click gesture (before awaited work).
        let fileHandle = null;
        if (typeof window.showSaveFilePicker === 'function') {
            try {
                fileHandle = await window.showSaveFilePicker({
                    suggestedName: fallbackFilename,
                    types: [{ description: 'MP4 Video', accept: { 'video/mp4': ['.mp4'] } }]
                });
            } catch (err) {
                if (err?.name === 'AbortError') {
                    return;
                }
                throw err;
            }
        }

        showProgress(12, 'Preparing animation export...');
        setStatus('Exporting layered animation...');

        const params = new URLSearchParams({
            layers_path: layeredPath,
            fps: value('radar-fps') || '4'
        });

        const response = await fetch(apiUrl(`/api/radar/archive/export-animation?${params.toString()}`));
        const data = await response.json();
        if (!response.ok || data.status === 'error') {
            throw new Error(data.message || 'Layered export failed');
        }

        if (!data.image_url) {
            throw new Error(data.message || 'Export did not return a video URL');
        }

        showProgress(80, 'Downloading exported video...');

        const videoUrl = apiUrl(data.image_url);
        const filename = data.image_url.split('/').pop() || 'radar_archive_export.mp4';

        // Fetch the video blob from the server.
        const videoResponse = await fetch(videoUrl);
        if (!videoResponse.ok) {
            throw new Error(`Failed to fetch exported video (HTTP ${videoResponse.status})`);
        }
        const blob = await videoResponse.blob();

        if (fileHandle) {
            const writable = await fileHandle.createWritable();
            await writable.write(blob);
            await writable.close();
        } else {
            // Fallback: <a download> prompts Save As in most browsers.
            const blobUrl = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = blobUrl;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
        }

        showProgress(100, 'Export complete');
        setStatus(data.message || 'Animation export complete.');
    }

    async function populateRadarSites() {
        const siteSelect = byId('radar-site');
        if (!siteSelect) {
            return;
        }

        // Use the existing HTML optgroups as the canonical grouping guide.
        const groupBySite = new Map();
        const guideGroupOrder = [];
        siteSelect.querySelectorAll('optgroup').forEach((group) => {
            const groupLabel = String(group.label || '').trim();
            if (groupLabel && !guideGroupOrder.includes(groupLabel)) {
                guideGroupOrder.push(groupLabel);
            }
            group.querySelectorAll('option').forEach((option) => {
                const siteId = String(option.value || '').trim().toUpperCase();
                if (siteId && groupLabel) {
                    groupBySite.set(siteId, groupLabel);
                }
            });
        });

        const currentSite = (siteSelect.value || 'KMHX').toUpperCase();
        try {
            const response = await fetch(apiUrl('/api/radar/sites'));
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            const siteOptions = Array.isArray(data?.sites) ? data.sites : [];
            if (!siteOptions.length) {
                return;
            }

            siteSelect.innerHTML = '';
            const groupedSites = new Map();
            siteOptions.forEach((site) => {
                const value = String(site.value || '').toUpperCase();
                const label = String(site.label || value);
                // Fallback group for any site not present in the HTML guide.
                const fallbackGroup = label.includes(',')
                    ? label.split(',').slice(-1)[0].trim()
                    : 'Other';
                const groupLabel = groupBySite.get(value) || fallbackGroup;
                if (!groupedSites.has(groupLabel)) {
                    groupedSites.set(groupLabel, []);
                }
                groupedSites.get(groupLabel).push({ label, value });
            });

            let selected = false;
            const appendGroup = (groupLabel, entries) => {
                const group = document.createElement('optgroup');
                group.label = groupLabel;
                entries.forEach((site) => {
                    const option = document.createElement('option');
                    option.value = site.value;
                    option.textContent = `${site.label} (${site.value})`;
                    if (option.value === currentSite || (!selected && option.value === 'KMHX')) {
                        option.selected = true;
                        selected = true;
                    }
                    group.appendChild(option);
                });
                siteSelect.appendChild(group);
            };

            // Render guided groups first in original HTML order.
            const renderedGroups = new Set();
            guideGroupOrder.forEach((groupLabel) => {
                const entries = groupedSites.get(groupLabel);
                if (!entries || !entries.length) {
                    return;
                }
                appendGroup(groupLabel, entries);
                renderedGroups.add(groupLabel);
            });

            // Render any new/unmapped groups after guided groups.
            Array.from(groupedSites.keys())
                .filter((groupLabel) => !renderedGroups.has(groupLabel))
                .sort((a, b) => a.localeCompare(b))
                .forEach((groupLabel) => appendGroup(groupLabel, groupedSites.get(groupLabel)));

            // Guarantee a selected option.
            if (!selected) {
                const fallback =
                    siteSelect.querySelector('option[value="KMHX"]') || siteSelect.options[0];
                if (fallback) {
                    fallback.selected = true;
                }
            }
        } catch (error) {
            console.warn('Could not load radar archive site options:', error);
        }
    }

    function updateRadarProductSelector() {
        const level = value('radar-level');
        const l3 = byId('radar-product-l3');
        const l2 = byId('radar-product-l2');
        const usingL2 = level === 'Level 2';

        if (l3) {
            l3.style.display = usingL2 ? 'none' : '';
        }
        if (l2) {
            l2.style.display = usingL2 ? '' : 'none';
        }

        updateStormMotionControlVisibility();
    }

    function shouldShowStormMotionControls() {
        const level = value('radar-level');
        if (level === 'Level 2') {
            return value('radar-product-l2') === 'velocity';
        }
        return value('radar-product-l3') === 'N0G';
    }

    function updateStormMotionControlVisibility() {
        const container = byId('radar-sm-inline-controls');
        if (!container) {
            return;
        }
        container.style.display = shouldShowStormMotionControls() ? '' : 'none';
    }

    function selectedRadarProduct() {
        return value('radar-level') === 'Level 2'
            ? value('radar-product-l2')
            : value('radar-product-l3');
    }

    function applyControlDefaults() {
        Object.entries(DEFAULT_CONTROLS).forEach(([id, controlValue]) => {
            const el = byId(id);
            if (!el) {
                return;
            }
            if (el.type === 'checkbox') {
                el.checked = Boolean(controlValue);
            } else {
                el.value = controlValue;
            }
        });
        window.bindRangeValueLabels?.();
    }

    function toUtcDateValue(localValue) {
        if (!localValue) { return ''; }
        const dt = new Date(localValue);
        return dt.toISOString().slice(0, 16);
    }

    // Convert a JS Date (UTC) to a YYYY-MM-DDTHH:MM string in local time
    // suitable for setting a datetime-local input value.
    function toLocalInputString(date) {
        const offsetMs = date.getTimezoneOffset() * 60000;
        return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
    }

    function updateRadarArchiveUtcPreview() {
        const preview = byId('radar-utc-preview');
        if (!preview) {
            return;
        }

        const fromLocal = value('radar-date-from');
        const toLocal = value('radar-date-to');
        const singleFrame = checked('radar-single-frame');
        const fromUtc = toUtcDateValue(fromLocal);
        const toUtc = singleFrame ? fromUtc : toUtcDateValue(toLocal);

        if (!fromUtc && !toUtc) {
            preview.textContent = '';
            return;
        }

        let text = 'UTC sent to API: ';
        if (fromUtc) {
            text += `${fromUtc.replace('T', ' ')}Z`;
        }
        if (!singleFrame && fromUtc && toUtc) {
            text += ' -> ';
        }
        if (!singleFrame && toUtc) {
            text += `${toUtc.replace('T', ' ')}Z`;
        }
        if (singleFrame && fromUtc) {
            text += ' (single-frame target window)';
        }
        preview.textContent = text;
    }

    let _quickRangeSetting = false;

    function setRadarArchiveFrames(frameValue) {
        const framesInput = byId('radar-frames');
        if (framesInput) {
            framesInput.value = String(frameValue);
        }
        window.bindRangeValueLabels?.();
    }

    function applyArchiveQuickRange() {
        const qr = value('radar-quick-range');
        if (qr === 'custom' || !qr) {
            return;
        }

        const now = new Date();
        now.setSeconds(0, 0);
        const toLocal = toLocalInputString(now);
        _quickRangeSetting = true;
        try {
            const sf = byId('radar-single-frame');
            const fromInput = byId('radar-date-from');
            const toInput = byId('radar-date-to');
            const lookbackHours = qr === 'current'
                ? RADAR_CURRENT_LOOKBACK_HOURS
                : parseFloat(qr);
            const from = new Date(now.getTime() - lookbackHours * 3600 * 1000);

            if (fromInput) {
                fromInput.value = toLocalInputString(from);
            }
            if (toInput) {
                toInput.value = toLocal;
            }
            if (sf) {
                sf.checked = qr === 'current';
            }
            setRadarArchiveFrames(qr === 'current' ? '1' : RADAR_ARCHIVE_MAX_FRAMES);
        } finally {
            _quickRangeSetting = false;
        }
        syncSingleFrameMode();
        updateRadarArchiveUtcPreview();
    }

    function syncSingleFrameMode() {
        const singleFrame = checked('radar-single-frame');
        const toInput = byId('radar-date-to');
        const toGroup = byId('radar-date-to-group');
        if (!toInput) {
            return;
        }

        if (singleFrame) {
            toInput.value = '';
            toInput.disabled = true;
            setRadarArchiveFrames('1');
            if (toGroup) {
                toGroup.style.display = 'none';
            }
        } else {
            toInput.disabled = false;
            if (toGroup) {
                toGroup.style.display = '';
            }
        }
        window.bindRangeValueLabels?.();
        updateRadarArchiveUtcPreview();
    }

    function applyExtentBounds(bounds) {
        byId('radar-n').value = bounds.getNorth().toFixed(4);
        byId('radar-s').value = bounds.getSouth().toFixed(4);
        byId('radar-e').value = bounds.getEast().toFixed(4);
        byId('radar-w').value = bounds.getWest().toFixed(4);
        setExtentMode(true);
    }

    function setExtentMode(isCustom) {
        const slider = byId('radar-extent-mode');
        const customControls = byId('radar-extent-custom-controls');
        if (!slider) {
            return;
        }
        slider.value = isCustom ? '1' : '0';
        if (customControls) {
            customControls.style.display = isCustom ? 'block' : 'none';
        }
    }

    function isCustomExtentMode() {
        return byId('radar-extent-mode')?.value === '1';
    }

    function bindExtentInputs() {
        ['n', 's', 'e', 'w'].forEach((axis) => {
            byId(`radar-${axis}`)?.addEventListener('input', () => {
                const hasAnyBounds = ['n', 's', 'e', 'w'].some((a) => value(`radar-${a}`) !== '');
                setExtentMode(hasAnyBounds);
            });
        });
    }

    function openMapModal() {
        extentSelector?.open();
    }

    function closeMapModal() {
        extentSelector?.close();
    }

    function clearExtent() {
        byId('radar-n').value = '';
        byId('radar-s').value = '';
        byId('radar-e').value = '';
        byId('radar-w').value = '';
        extentSelector?.clear();
        setExtentMode(false);
    }

    async function generate(options = {}) {
        const silent = Boolean(options?.silent);
        try {
            if (!silent) hideProgress();
            syncSingleFrameMode();
            const requestId = `radar-${Date.now()}`;
            const singleFrame = checked('radar-single-frame');
            const dateFrom = toUtcDateValue(value('radar-date-from'));
            const dateTo = singleFrame ? dateFrom : toUtcDateValue(value('radar-date-to'));
            if (!dateFrom || (!singleFrame && !dateTo)) {
                throw new Error(singleFrame ? 'Date From is required.' :
                    'Date From and Date To are required.\nDid you forget to check "Single Frame Only"?');
            }

            const params = new URLSearchParams({
                request_id: requestId,
                site: value('radar-site').trim().toUpperCase() || 'KMHX',
                product: selectedRadarProduct(),
                level: value('radar-level'),
                date_from: dateFrom,
                date_to: dateTo,
                frames: value('radar-frames') || RADAR_ARCHIVE_MAX_FRAMES,
                latest_only: String(singleFrame),
                user_tz: value('radar-user-tz') || 'America/New_York',
                fps: value('radar-fps') || '4',
                sm_speed: value('radar-sm-speed') || '30',
                sm_dir: value('radar-sm-dir') || '225',
                show_places: 'true',
                source: value('radar-source') || 'aws',
                view_mode: 'layers'
            });

            if (isCustomExtentMode()) {
                ['n', 's', 'e', 'w'].forEach((axis) => {
                    const axisValue = value(`radar-${axis}`);
                    if (axisValue !== '') {
                        params.set(axis, axisValue);
                    }
                });
            }

            if (!silent) {
                showProgress(5, 'Submitting radar archive request...');
                setStatus('Generating radar archive...');
                window.setOutputMeta?.({ state: 'running' });
                hideLayeredOutput();
            }

            const progressLoop = pollProgress(requestId, (progress) => {
                showProgress(progress.percent || 0, progress.message || 'Working...');
            });

            const response = await fetch(apiUrl(`/api/radar/archive?${params.toString()}`));
            const data = await response.json();
            await progressLoop;

            if (!response.ok || data.status === 'error') {
                throw new Error(data.message || data.detail?.error || 'Radar archive generation failed');
            }

            if (!silent) {
                window.setOutputMetaFromResponse?.(data, {
                    source: value('radar-source'),
                    dataMode: 'Archive'
                });
            }

            if (Array.isArray(data.frames) && data.frames.length) {
                const displayed = displayLayeredResult(data);
                if (displayed) {
                    if (!silent) {
                        showProgress(100, 'Completed');
                        setStatus(data.message || 'Radar archive generated.');
                    }
                    if (value('radar-quick-range') === 'current') {
                        hasGeneratedCurrentOutput = true;
                        ensureAutoRefreshTimer();
                    } else {
                        hasGeneratedCurrentOutput = false;
                    }
                    return;
                }
            }

            if (!data.image_url) {
                if (!silent) setStatus(data.message || 'No output generated.');
                return;
            }

            hideLayeredOutput();
            if (data.image_url.toLowerCase().endsWith('.mp4')) {
                displayVideo(data.image_url);
            } else {
                displayImage(data.image_url);
            }
            if (!silent) {
                showProgress(100, 'Completed');
                setStatus(data.message || 'Radar archive generated.');
            }
            if (value('radar-quick-range') === 'current') {
                hasGeneratedCurrentOutput = true;
                ensureAutoRefreshTimer();
            } else {
                hasGeneratedCurrentOutput = false;
            }
        } catch (error) {
            hasGeneratedCurrentOutput = false;
            if (!silent) {
                setStatus(`Error: ${error.message}`);
                window.setOutputMeta?.({ state: 'unavailable' });
            }
        } finally {
            if (!silent) setTimeout(hideProgress, 1800);
        }
    }

    function shouldAutoRefresh() {
        return hasGeneratedCurrentOutput
            && !document.hidden
            && value('radar-quick-range') === 'current';
    }

    function ensureAutoRefreshTimer() {
        if (radarAutoRefreshTimer !== null) return;
        radarAutoRefreshTimer = window.setInterval(() => {
            if (!shouldAutoRefresh()) return;
            generate({ silent: true });
        }, RADAR_AUTO_REFRESH_MS);
    }

    document.addEventListener('DOMContentLoaded', () => {
        extentSelector = window.createExtentSelectorModal?.({
            onBoundsSelected: applyExtentBounds,
            onOpen: (map) => window.refreshExtentSelectorOverlays?.(map)
        }) || null;

        byId('radar-generate')?.addEventListener('click', generate);
        byId('radar-level')?.addEventListener('change', updateRadarProductSelector);
        byId('radar-product-l3')?.addEventListener('change', updateStormMotionControlVisibility);
        byId('radar-product-l2')?.addEventListener('change', updateStormMotionControlVisibility);
        byId('radar-quick-range')?.addEventListener('change', applyArchiveQuickRange);
        byId('radar-single-frame')?.addEventListener('change', syncSingleFrameMode);
        byId('radar-date-from')?.addEventListener('change', () => {
            if (!_quickRangeSetting) {
                const qrEl = byId('radar-quick-range');
                if (qrEl && qrEl.value !== 'custom') {
                    qrEl.value = 'custom';
                }
                const singleFrame = byId('radar-single-frame');
                if (singleFrame) {
                    singleFrame.checked = false;
                }
                setRadarArchiveFrames(RADAR_ARCHIVE_MAX_FRAMES);
            }
            syncSingleFrameMode();
        });
        byId('radar-date-to')?.addEventListener('change', () => {
            if (!_quickRangeSetting) {
                const qrEl = byId('radar-quick-range');
                if (qrEl && qrEl.value !== 'custom') {
                    qrEl.value = 'custom';
                }
                const singleFrame = byId('radar-single-frame');
                if (singleFrame) {
                    singleFrame.checked = false;
                }
                setRadarArchiveFrames(RADAR_ARCHIVE_MAX_FRAMES);
                syncSingleFrameMode();
            }
            updateRadarArchiveUtcPreview();
        });
        byId('radar-open-map')?.addEventListener('click', openMapModal);
        byId('layered-scrubber')?.addEventListener('input', (event) => {
            updateLayeredFrame(event.target.value);
        });
        byId('layered-step-back')?.addEventListener('click', () => {
            updateLayeredFrame(Math.max(0, layeredIndex - 1));
        });
        byId('layered-step-fwd')?.addEventListener('click', () => {
            updateLayeredFrame(Math.min(layeredFrames.length - 1, layeredIndex + 1));
        });
        ['layered-show-radar', 'layered-show-alerts', 'layered-show-cities', 'layered-show-counties', 'layered-show-states', 'layered-show-rings', 'layered-opacity-radar', 'layered-opacity-alerts', 'layered-opacity-cities', 'layered-opacity-counties', 'layered-opacity-states', 'layered-opacity-rings']
            .forEach((id) => {
                byId(id)?.addEventListener('input', applyLayeredVisibility);
                byId(id)?.addEventListener('change', applyLayeredVisibility);
            });
        byId('layered-save-current')?.addEventListener('click', async () => {
            try {
                await saveCurrentLayeredFrame();
            } catch (error) {
                setStatus(`Error: ${error.message}`);
            }
        });
        byId('layered-export-animation')?.addEventListener('click', async () => {
            try {
                await exportLayeredAnimation();
            } catch (error) {
                setStatus(`Error: ${error.message}`);
            } finally {
                setTimeout(hideProgress, 1400);
            }
        });
        byId('radar-extent-mode')?.addEventListener('input', (event) => {
            const customMode = event.target.value === '1';
            if (!customMode) {
                clearExtent();
            } else {
                setExtentMode(true);
            }
        });
        bindExtentInputs();
        applyControlDefaults();
        setExtentMode(isCustomExtentMode());
        updateRadarProductSelector();
        populateRadarSites();
        applyArchiveQuickRange();
        syncSingleFrameMode();
        updateRadarArchiveUtcPreview();
        hideLayeredOutput();
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && shouldAutoRefresh()) {
                generate({ silent: true });
            }
        });
    });
})();

