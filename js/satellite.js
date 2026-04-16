(function () {
    'use strict';

    const DEFAULT_CONTROLS = {
        'satellite-sat-id': 'goes19',
        'satellite-sector': 'CONUS',
        'satellite-channel': 'Channel13',
        'satellite-source': 'aws',
        'satellite-quick-range': 'current',
        'satellite-user-tz': 'America/New_York',
        'satellite-single-frame': false,
        'satellite-frames': '240',
        'satellite-fps': '4',
        'satellite-extent-mode': '0'
    };

    const SATELLITE_ARCHIVE_MAX_FRAMES = '240';
    const SATELLITE_CURRENT_LOOKBACK_HOURS = 0.25;

    let mapInstance = null;
    let drawLayer = null;

    let scrubberFrames = [];
    let scrubberIndex = 0;
    let scrubberFramesPath = '';
    let scrubberPrefetchCache = new Map();
    const SCRUBBER_PREFETCH_RADIUS = 2;
    let quickRangeSetting = false;

    // Layer control state
    let currentFrameLayers = null;
    let layerVisibility = {
        background: true,
        satellite: true,
        borders: true,
        cities: true,
        hud: true,
        logo: true
    };
    let layerOrder = ['background', 'satellite', 'borders', 'cities', 'hud', 'logo'];
    let compositeRenderToken = 0;
    let compositeBlobUrl = '';

    function byId(id) { return document.getElementById(id); }
    function value(id) { const el = byId(id); return el ? el.value : ''; }
    function checked(id) { const el = byId(id); return !!(el && el.checked); }

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

    function toLocalInputString(date) {
        const offsetMs = date.getTimezoneOffset() * 60000;
        return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
    }

    function updateUtcPreview() {
        const preview = byId('satellite-utc-preview');
        if (!preview) { return; }

        const fromLocal = value('satellite-date-from');
        const toLocal = value('satellite-date-to');
        const singleFrame = checked('satellite-single-frame');
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

    function setSatelliteFrames(frameValue) {
        const framesInput = byId('satellite-frames');
        if (framesInput) {
            framesInput.value = String(frameValue);
        }
        window.bindRangeValueLabels?.();
    }

    function applyQuickRange() {
        const quickRange = value('satellite-quick-range');
        if (quickRange === 'custom' || !quickRange) {
            return;
        }

        const now = new Date();
        now.setSeconds(0, 0);
        quickRangeSetting = true;
        try {
            const singleFrameEl = byId('satellite-single-frame');
            const fromInput = byId('satellite-date-from');
            const toInput = byId('satellite-date-to');
            const lookbackHours = quickRange === 'current'
                ? SATELLITE_CURRENT_LOOKBACK_HOURS
                : parseFloat(quickRange);
            const from = new Date(now.getTime() - lookbackHours * 3600 * 1000);

            if (fromInput) {
                fromInput.value = toLocalInputString(from);
            }
            if (toInput) {
                toInput.value = toLocalInputString(now);
            }
            if (singleFrameEl) {
                singleFrameEl.checked = quickRange === 'current';
            }
            setSatelliteFrames(quickRange === 'current' ? '1' : SATELLITE_ARCHIVE_MAX_FRAMES);
        } finally {
            quickRangeSetting = false;
        }

        syncSingleFrameMode();
        updateUtcPreview();
    }

    function syncSingleFrameMode() {
        const singleFrame = checked('satellite-single-frame');
        const fromInput = byId('satellite-date-from');
        const toInput = byId('satellite-date-to');
        const toGroup = byId('satellite-date-to-group');
        const framesInput = byId('satellite-frames');
        if (!toInput) {
            return;
        }

        if (singleFrame) {
            if (fromInput?.value && !toInput.value) {
                toInput.value = fromInput.value;
            }
            toInput.disabled = true;
            if (framesInput) {
                framesInput.value = '1';
            }
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
        updateUtcPreview();
    }

    function applyExtentBounds(bounds) {
        byId('satellite-n').value = bounds.getNorth().toFixed(4);
        byId('satellite-s').value = bounds.getSouth().toFixed(4);
        byId('satellite-e').value = bounds.getEast().toFixed(4);
        byId('satellite-w').value = bounds.getWest().toFixed(4);
        setExtentMode(true);
    }

    function setExtentMode(isCustom) {
        const slider = byId('satellite-extent-mode');
        const customControls = byId('satellite-extent-custom-controls');
        if (!slider) {
            return;
        }
        slider.value = isCustom ? '1' : '0';
        if (customControls) {
            customControls.style.display = isCustom ? 'block' : 'none';
        }
    }

    function isCustomExtentMode() {
        return byId('satellite-extent-mode')?.value === '1';
    }

    function bindExtentInputs() {
        ['n', 's', 'e', 'w'].forEach((axis) => {
            byId(`satellite-${axis}`)?.addEventListener('input', () => {
                const hasAnyBounds = ['n', 's', 'e', 'w'].some((a) => value(`satellite-${a}`) !== '');
                setExtentMode(hasAnyBounds);
            });
        });
    }

    function openMapModal() {
        const modal = byId('map-modal');
        if (!modal) { return; }

        if (!mapInstance) {
            mapInstance = L.map('leaflet-map').setView([35.5, -79.0], 6);
            L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; OpenStreetMap &copy; CartoDB',
                subdomains: 'abcd',
                maxZoom: 19
            }).addTo(mapInstance);
            drawLayer = new L.FeatureGroup();
            mapInstance.addLayer(drawLayer);
            mapInstance.addControl(new L.Control.Draw({
                draw: { marker: false, circle: false, circlemarker: false, polyline: false, polygon: false, rectangle: true },
                edit: { featureGroup: drawLayer, edit: true, remove: true }
            }));

            mapInstance.on(L.Draw.Event.CREATED, (event) => {
                drawLayer.clearLayers();
                drawLayer.addLayer(event.layer);
                applyExtentBounds(event.layer.getBounds());
            });
            mapInstance.on(L.Draw.Event.EDITED, (event) => {
                event.layers.eachLayer((layer) => applyExtentBounds(layer.getBounds()));
            });
        }

        modal.style.display = 'flex';
        setTimeout(() => {
            mapInstance.invalidateSize();
            window.refreshExtentSelectorOverlays?.(mapInstance);
        }, 100);
    }

    function closeMapModal() {
        byId('map-modal').style.display = 'none';
    }

    function hideScrubberOutput() {
        const container = byId('result-scrubber-container');
        const controls = byId('scrubber-controls');
        const img = byId('result-scrubber-image');
        scrubberFrames = [];
        scrubberIndex = 0;
        scrubberFramesPath = '';
        scrubberPrefetchCache = new Map();
        if (img) { img.src = ''; }
        if (container) { container.style.display = 'none'; }
        if (controls) { controls.style.display = 'none'; }
    }

    function scrubberFrameSrc(index) {
        const frame = scrubberFrames[index];
        const url = frame?.url || '';
        return url ? apiUrl(url) : '';
    }

    function prefetchScrubberFrame(index) {
        if (index < 0 || index >= scrubberFrames.length) { return; }
        const src = scrubberFrameSrc(index);
        if (!src || scrubberPrefetchCache.has(src)) { return; }
        const img = new Image();
        img.decoding = 'async';
        img.src = src;
        scrubberPrefetchCache.set(src, img);
    }

    function prefetchScrubberNeighbors(centerIndex) {
        for (let offset = -SCRUBBER_PREFETCH_RADIUS; offset <= SCRUBBER_PREFETCH_RADIUS; offset += 1) {
            if (offset !== 0) {
                prefetchScrubberFrame(centerIndex + offset);
            }
        }
    }

    function updateScrubberFrame(index) {
        const img = byId('result-scrubber-image');
        const timestamp = byId('scrubber-timestamp');
        const scrubber = byId('scrubber-range');
        if (!img || !timestamp || !scrubber || !scrubberFrames.length) { return; }

        const clamped = Math.max(0, Math.min(scrubberFrames.length - 1, Number(index) || 0));
        scrubberIndex = clamped;
        const frame = scrubberFrames[clamped];
        scrubber.value = String(clamped);
        timestamp.textContent = frame.timestamp_local || frame.timestamp_utc || `Frame ${clamped + 1}`;
        prefetchScrubberNeighbors(clamped);
        
        // Update layer controls and recompose if layers are available
        if (frame && frame.layers && Object.keys(frame.layers).length) {
            buildLayerControls();
            recomposeScrubberFrame();
        } else {
            img.src = scrubberFrameSrc(clamped);
        }
    }

    function buildLayerControls() {
        const listEl = byId('satellite-layer-list');
        const saveBtn = byId('satellite-save-layer-order');
        if (!listEl) { return; }

        // Clear existing controls
        listEl.innerHTML = '';

        // Check if current frame has layers
        const frame = scrubberFrames[scrubberIndex];
        if (!frame || !frame.layers || typeof frame.layers !== 'object' || !Object.keys(frame.layers).length) {
            listEl.innerHTML = '<p class="zorder-hint">No layer data available for this frame.</p>';
            if (saveBtn) { saveBtn.style.display = 'none'; }
            return;
        }

        currentFrameLayers = frame.layers;

        // Build control rows for each layer (in order)
        layerOrder.forEach((layerName) => {
            if (!currentFrameLayers || !currentFrameLayers[layerName]) {
                return; // Skip layers not in currentFrameLayers
            }

            const row = document.createElement('div');
            row.className = 'layer-control-row';
            row.setAttribute('data-layer', layerName);
            row.setAttribute('draggable', 'true');

            // Visibility checkbox
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `layer-${layerName}-visible`;
            checkbox.checked = layerVisibility[layerName] !== false;
            checkbox.addEventListener('change', () => {
                layerVisibility[layerName] = checkbox.checked;
                recomposeScrubberFrame();
            });

            const checkLabel = document.createElement('label');
            checkLabel.htmlFor = checkbox.id;
            checkLabel.className = 'layer-control-label';
            checkLabel.textContent = layerName.charAt(0).toUpperCase() + layerName.slice(1);

            row.appendChild(checkbox);
            row.appendChild(checkLabel);

            listEl.appendChild(row);
        });

        // Show save button
        if (saveBtn) { saveBtn.style.display = 'inline-block'; }

        // Add drag-to-reorder handlers
        attachLayerDragHandlers();
    }

    function attachLayerDragHandlers() {
        const rows = document.querySelectorAll('#satellite-layer-list [data-layer]');
        let draggedEl = null;

        rows.forEach((row) => {
            row.addEventListener('dragstart', (e) => {
                draggedEl = row;
                row.style.opacity = '0.5';
                e.dataTransfer.effectAllowed = 'move';
            });

            row.addEventListener('dragend', () => {
                rows.forEach((r) => { r.style.opacity = '1'; });
                draggedEl = null;
            });

            row.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
            });

            row.addEventListener('drop', (e) => {
                e.preventDefault();
                if (!draggedEl || draggedEl === row) { return; }

                const draggedLayer = draggedEl.getAttribute('data-layer');
                const targetLayer = row.getAttribute('data-layer');

                // Swap in layerOrder
                const dragIdx = layerOrder.indexOf(draggedLayer);
                const targetIdx = layerOrder.indexOf(targetLayer);

                if (dragIdx > -1 && targetIdx > -1) {
                    [layerOrder[dragIdx], layerOrder[targetIdx]] = [layerOrder[targetIdx], layerOrder[dragIdx]];
                    // Immediately recompose and rebuild controls
                    recomposeScrubberFrame();
                    buildLayerControls();
                }
            });
        });
    }

    async function composeScrubberFrameLayers() {
        const frame = scrubberFrames[scrubberIndex];
        if (!frame || !frame.layers) {
            return scrubberFrameSrc(scrubberIndex); // Fall back to original image URL
        }

        // Create an off-screen canvas for compositing
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        if (!ctx) { return scrubberFrameSrc(scrubberIndex); }

        // Load first available layer to determine canvas dimensions
        const firstLayer = layerOrder.find((layerName) => frame.layers[layerName]);
        const baseSrc = firstLayer ? frame.layers[firstLayer] : '';
        if (!baseSrc) { return scrubberFrameSrc(scrubberIndex); }

        const baseImg = new Image();
        baseImg.crossOrigin = 'anonymous';

        return new Promise((resolve) => {
            baseImg.onload = async () => {
                canvas.width = baseImg.width;
                canvas.height = baseImg.height;

                // Composite layers in order
                for (const layerName of layerOrder) {
                    if (!layerVisibility[layerName] || !frame.layers[layerName]) {
                        continue;
                    }

                    const layerUrl = frame.layers[layerName];
                    const img = new Image();
                    img.crossOrigin = 'anonymous';

                    await new Promise((resolve) => {
                        img.onload = () => {
                            ctx.globalAlpha = 1;
                            ctx.drawImage(img, 0, 0);
                            resolve();
                        };
                        img.onerror = () => {
                            console.warn(`Failed to load layer image: ${layerUrl}`);
                            resolve();
                        };
                        img.src = apiUrl(layerUrl);
                    });
                }

                // Convert canvas to blob URL
                canvas.toBlob((blob) => {
                    const url = URL.createObjectURL(blob);
                    resolve(url);
                }, 'image/png');
            };

            baseImg.onerror = () => {
                console.warn(`Failed to load base layer: ${baseSrc}`);
                resolve(scrubberFrameSrc(scrubberIndex)); // Fall back
            };

            baseImg.src = apiUrl(baseSrc);
        });
    }

    async function recomposeScrubberFrame() {
        const img = byId('result-scrubber-image');
        if (!img || !scrubberFrames.length) { return; }
        const renderToken = ++compositeRenderToken;

        // Check if current frame has layers
        const frame = scrubberFrames[scrubberIndex];
        if (!frame || !frame.layers || !Object.keys(frame.layers).length) {
            // No layers, use original image
            if (compositeBlobUrl) {
                URL.revokeObjectURL(compositeBlobUrl);
                compositeBlobUrl = '';
            }
            img.src = scrubberFrameSrc(scrubberIndex);
            return;
        }

        // Compose layers
        const compositeUrl = await composeScrubberFrameLayers();
        if (renderToken !== compositeRenderToken) {
            if (compositeUrl.startsWith('blob:')) {
                URL.revokeObjectURL(compositeUrl);
            }
            return;
        }
        if (compositeBlobUrl) {
            URL.revokeObjectURL(compositeBlobUrl);
            compositeBlobUrl = '';
        }
        if (compositeUrl.startsWith('blob:')) {
            compositeBlobUrl = compositeUrl;
        }
        img.src = compositeUrl;
    }

    function displayScrubberResult(data) {
        const container = byId('result-scrubber-container');
        const controls = byId('scrubber-controls');
        const scrubber = byId('scrubber-range');
        const image = byId('result-image');
        const video = byId('result-video');

        if (!container || !controls || !scrubber || !image || !video) { return false; }

        const frames = Array.isArray(data?.frames) ? data.frames.filter((frame) => frame && frame.url) : [];
        scrubberFramesPath = String(data?.frames_path || '');
        if (!frames.length) { return false; }

        image.style.display = 'none';
        video.style.display = 'none';

        scrubberPrefetchCache = new Map();
        scrubberFrames = frames;
        scrubber.min = '0';
        scrubber.max = String(frames.length - 1);
        scrubber.step = '1';

        updateScrubberFrame(0);
        prefetchScrubberFrame(0);
        buildLayerControls();

        container.style.display = 'block';
        controls.style.display = 'grid';
        return true;
    }

    async function saveCurrentScrubberFrame() {
        if (!scrubberFrames.length) { return; }

        const frame = scrubberFrames[scrubberIndex] || {};
        const suffix = String(frame.timestamp_utc || scrubberIndex).replace(/[^0-9A-Za-z_-]/g, '_');
        const filename = `satellite_frame_${suffix}.png`;

        let fileHandle = null;
        if (typeof window.showSaveFilePicker === 'function') {
            try {
                fileHandle = await window.showSaveFilePicker({
                    suggestedName: filename,
                    types: [{ description: 'PNG Image', accept: { 'image/png': ['.png'] } }]
                });
            } catch (err) {
                if (err?.name === 'AbortError') { return; }
                throw err;
            }
        }

        const src = scrubberFrameSrc(scrubberIndex);
        const res = await fetch(src);
        if (!res.ok) { throw new Error(`Image fetch failed (HTTP ${res.status})`); }
        const blob = await res.blob();

        if (fileHandle) {
            const writable = await fileHandle.createWritable();
            await writable.write(blob);
            await writable.close();
        } else {
            const blobUrl = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = blobUrl;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
        }
    }

    async function exportScrubberAnimation() {
        if (!scrubberFramesPath) {
            throw new Error('No scrubber output is available to export yet.');
        }

        const fallbackFilename = 'satellite_export.mp4';
        let fileHandle = null;
        if (typeof window.showSaveFilePicker === 'function') {
            try {
                fileHandle = await window.showSaveFilePicker({
                    suggestedName: fallbackFilename,
                    types: [{ description: 'MP4 Video', accept: { 'video/mp4': ['.mp4'] } }]
                });
            } catch (err) {
                if (err?.name === 'AbortError') { return; }
                throw err;
            }
        }

        showProgress(12, 'Preparing animation export...');
        setStatus('Exporting satellite animation...');

        const params = new URLSearchParams({
            frames_path: scrubberFramesPath,
            fps: value('satellite-fps') || '4'
        });

        const response = await fetch(apiUrl(`/api/satellite/archive/export-animation?${params.toString()}`));
        const data = await response.json();
        if (!response.ok || data.status === 'error') {
            throw new Error(data.message || 'Satellite export failed');
        }
        if (!data.image_url) {
            throw new Error(data.message || 'Export did not return a video URL');
        }

        showProgress(80, 'Downloading exported video...');

        const videoUrl = apiUrl(data.image_url);
        const filename = data.image_url.split('/').pop() || 'satellite_export.mp4';
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

    function clearExtent() {
        byId('satellite-n').value = '';
        byId('satellite-s').value = '';
        byId('satellite-e').value = '';
        byId('satellite-w').value = '';
        drawLayer?.clearLayers();
        setExtentMode(false);
    }

    async function generate() {
        try {
            syncSingleFrameMode();
            const requestId = `satellite-${Date.now()}`;
            const dateFrom = toUtcDateValue(value('satellite-date-from'));
            const dateTo = toUtcDateValue(value('satellite-date-to'));
            if (!dateFrom || !dateTo) {
                throw new Error('Date From and Date To are required.');
            }

            const quickRange = value('satellite-quick-range') || 'current';
            const params = new URLSearchParams({
                request_id: requestId,
                sat_id: value('satellite-sat-id') || 'goes19',
                sector: value('satellite-sector') || 'CONUS',
                channel: value('satellite-channel') || 'Channel13',
                date_from: dateFrom,
                date_to: dateTo,
                fps: value('satellite-fps') || '4',
                frames: value('satellite-frames') || SATELLITE_ARCHIVE_MAX_FRAMES,
                show_places: 'false',
                user_tz: value('satellite-user-tz') || 'America/New_York',
                source: value('satellite-source') || 'aws',
                view_mode: 'scrubber'
            });

            if (isCustomExtentMode()) {
                ['n', 's', 'e', 'w'].forEach((axis) => {
                    const axisValue = value(`satellite-${axis}`);
                    if (axisValue !== '') {
                        params.set(axis, axisValue);
                    }
                });
            }

            showProgress(5, 'Submitting satellite request...');
            setStatus('Generating satellite output...');
            window.setOutputMeta?.({ state: 'running' });
            hideScrubberOutput();

            const progressLoop = pollProgress(requestId, (progress) => {
                showProgress(progress.percent || 0, progress.message || 'Working...');
            });

            const response = await fetch(apiUrl(`/api/satellite/archive?${params.toString()}`));
            const data = await response.json();
            await progressLoop;

            if (!response.ok || data.status === 'error') {
                throw new Error(data.message || data.detail?.error || 'Satellite generation failed');
            }

            const uiDataMode = quickRange === 'current' ? 'current' : 'archive';
            window.setOutputMeta?.({
                source: data.source_used || data.source || data.data_source || value('satellite-source'),
                requestedSource: value('satellite-source'),
                dataMode: uiDataMode
            });

            const successMessage = quickRange === 'current'
                ? 'Current satellite frame generated.'
                : (data.message || 'Satellite archive generated.');

            if (data.view_mode === 'scrubber' && Array.isArray(data.frames) && data.frames.length) {
                const displayed = displayScrubberResult(data);
                if (displayed) {
                    showProgress(100, 'Completed');
                    setStatus(successMessage);
                    return;
                }
            }

            if (!data.image_url) {
                setStatus(data.message || 'No output generated.');
                return;
            }

            hideScrubberOutput();
            if (data.image_url.toLowerCase().endsWith('.mp4')) {
                displayVideo(data.image_url);
            } else {
                displayImage(data.image_url);
            }

            showProgress(100, 'Completed');
            setStatus(successMessage);
        } catch (error) {
            setStatus(`Error: ${error.message}`);
            window.setOutputMeta?.({ state: 'unavailable' });
        } finally {
            setTimeout(hideProgress, 1800);
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        byId('satellite-generate')?.addEventListener('click', generate);
        byId('satellite-quick-range')?.addEventListener('change', applyQuickRange);
        byId('satellite-single-frame')?.addEventListener('change', syncSingleFrameMode);
        byId('satellite-date-from')?.addEventListener('change', () => {
            if (!quickRangeSetting) {
                const quickRangeEl = byId('satellite-quick-range');
                if (quickRangeEl) {
                    quickRangeEl.value = 'custom';
                }
                const singleFrameEl = byId('satellite-single-frame');
                if (singleFrameEl) {
                    singleFrameEl.checked = false;
                }
                setSatelliteFrames(SATELLITE_ARCHIVE_MAX_FRAMES);
            }
            syncSingleFrameMode();
        });
        byId('satellite-date-to')?.addEventListener('change', () => {
            if (!quickRangeSetting) {
                const quickRangeEl = byId('satellite-quick-range');
                if (quickRangeEl) {
                    quickRangeEl.value = 'custom';
                }
                const singleFrameEl = byId('satellite-single-frame');
                if (singleFrameEl) {
                    singleFrameEl.checked = false;
                }
                setSatelliteFrames(SATELLITE_ARCHIVE_MAX_FRAMES);
                syncSingleFrameMode();
            }
            updateUtcPreview();
        });
        byId('satellite-open-map')?.addEventListener('click', openMapModal);
        byId('satellite-extent-mode')?.addEventListener('input', (event) => {
            const customMode = event.target.value === '1';
            if (!customMode) {
                clearExtent();
            } else {
                setExtentMode(true);
            }
        });
        byId('map-modal-close')?.addEventListener('click', closeMapModal);

        byId('scrubber-range')?.addEventListener('input', (event) => {
            updateScrubberFrame(event.target.value);
        });
        byId('scrubber-step-back')?.addEventListener('click', () => {
            if (scrubberIndex > 0) {
                updateScrubberFrame(scrubberIndex - 1);
            }
        });
        byId('scrubber-step-fwd')?.addEventListener('click', () => {
            if (scrubberIndex < scrubberFrames.length - 1) {
                updateScrubberFrame(scrubberIndex + 1);
            }
        });
        byId('scrubber-save-current')?.addEventListener('click', async () => {
            try {
                await saveCurrentScrubberFrame();
            } catch (error) {
                setStatus(`Error: ${error.message}`);
            }
        });
        byId('scrubber-export-animation')?.addEventListener('click', async () => {
            try {
                await exportScrubberAnimation();
            } catch (error) {
                setStatus(`Error: ${error.message}`);
            } finally {
                setTimeout(hideProgress, 1400);
            }
        });

        bindExtentInputs();
        applyControlDefaults();
        setExtentMode(isCustomExtentMode());
        applyQuickRange();
        syncSingleFrameMode();
        updateUtcPreview();
        hideScrubberOutput();
    });
})();

