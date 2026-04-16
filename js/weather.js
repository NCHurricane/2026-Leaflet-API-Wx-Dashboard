(function () {
    'use strict';

    // ── State ────────────────────────────────────────────────────────────────
    let currentData = null;        // last API response
    let currentFrames = [];        // frames[] array
    let currentLayersPath = '';    // session layers_path
    let _spcLastTouched = 'convective'; // which SPC dropdown was last changed
    let _spcItemBoundsMap = {};    // { itemId: {w,e,s,n} } from spc-items API

    const byId = (id) => document.getElementById(id);

    // ── MRMS sub-product dropdown helpers ────────────────────────────────────
    const _MRMS_SUB_GROUPS = {
        'RotationTrack': ['weather-mrms-rotation-group'],
        'MESH':          ['weather-mrms-mesh-group'],
        'AzShear':       ['weather-mrms-azshear-group'],
        'EchoTop':       ['weather-mrms-echotop-group'],
        'VIL':           ['weather-mrms-vil-group'],
        'QPE':           ['weather-mrms-qpe-group'],
        'Reflectivity':  ['weather-mrms-refl-group'],
        'Lightning':     ['weather-mrms-lightning-group'],
        'Model':         ['weather-mrms-model-group'],
    };
    const _ALL_MRMS_SUB_GROUPS = Object.values(_MRMS_SUB_GROUPS).flat();

    function updateMrmsSubControls() {
        const family = byId('weather-mrms-product')?.value || '';
        const activeGroups = _MRMS_SUB_GROUPS[family] || [];
        _ALL_MRMS_SUB_GROUPS.forEach((id) => {
            const el = byId(id);
            if (el) el.style.display = activeGroups.includes(id) ? '' : 'none';
        });
        // QPE: show/hide RadarOnly-specific period options
        const qpePeriod = byId('weather-mrms-qpe-period');
        const isRO = (byId('weather-mrms-qpe-source')?.value || '') === 'RO';
        if (qpePeriod) {
            for (const opt of qpePeriod.options) {
                if (opt.value === '15M' || opt.value === 'Since12Z') {
                    opt.style.display = isRO ? '' : 'none';
                    opt.disabled = !isRO;
                }
            }
            if (!isRO && (qpePeriod.value === '15M' || qpePeriod.value === 'Since12Z')) {
                qpePeriod.value = '01H';
            }
        }
    }

    function composeMrmsProductKey() {
        const family = byId('weather-mrms-product')?.value || '';
        switch (family) {
            case 'RotationTrack':
                return `RotationTrack_${byId('weather-mrms-rotation-level')?.value || 'LL'}_${byId('weather-mrms-rotation-time')?.value || '60min'}`;
            case 'MESH':
                return `MESH_${byId('weather-mrms-mesh-time')?.value || 'Instant'}`;
            case 'AzShear':
                return `AzShear_${byId('weather-mrms-azshear-level')?.value || 'Low'}`;
            case 'EchoTop':
                return `EchoTop_${byId('weather-mrms-echotop-threshold')?.value || '18'}`;
            case 'VIL':
                return `VIL_${byId('weather-mrms-vil-type')?.value || 'Instant'}`;
            case 'QPE':
                return `QPE_${byId('weather-mrms-qpe-source')?.value || 'MS2'}_${byId('weather-mrms-qpe-period')?.value || '01H'}`;
            case 'Reflectivity':
                return `Refl_${byId('weather-mrms-refl-variant')?.value || 'HSR'}`;
            case 'Lightning':
                return `Lightning_${byId('weather-mrms-lightning-window')?.value || '30min'}`;
            case 'Model':
                return `Model_${byId('weather-mrms-model-field')?.value || 'FreezingLevel'}`;
            default:
                return family; // standalone products (PrecipRate, PrecipFlag, SHI, POSH, RadarQualityIndex)
        }
    }

    // ── Product group switching ──────────────────────────────────────────────
    function updateProductOpts() {
        const group = byId('weather-product-group').value;
        document.querySelectorAll('.weather-product-opts').forEach((el) => {
            el.style.display = 'none';
        });
        const target = byId(`weather-${group}-opts`);
        if (target) {
            target.style.display = '';
        }
        updateSpcConvective();
        if (typeof updateReportDayVisibility === 'function') updateReportDayVisibility();
    }

    function getSelectedProduct() {
        const group = byId('weather-product-group').value;
        if (group === 'spc') {
            // SPC has three dropdowns; use whichever was last touched
            if (_spcLastTouched === 'other') {
                return byId('weather-spc-product')?.value || '';
            }
            if (_spcLastTouched === 'fire') {
                return byId('weather-spc-fire')?.value || '';
            }
            return byId('weather-spc-convective')?.value || '';
        }
        if (group === 'mrms') {
            return composeMrmsProductKey();
        }
        const sel = byId(`weather-${group}-product`);
        return sel ? sel.value : '';
    }

    // ── SPC day-driven convective outlook filtering ────────────────────────
    // Day determines which convective outlooks are available:
    //   Day 1-2: cat, torn, wind, hail
    //   Day 3:   cat, prob
    //   Day 4-8: cat only
    // Watches/MDs/Reports are in a separate dropdown, visible only on Day 1.
    const _SPC_CONVECTIVE_BY_DAY = {
        1: ['cat', 'torn', 'wind', 'hail'],
        2: ['cat', 'torn', 'wind', 'hail'],
        3: ['cat', 'prob'],
    };
    for (let d = 4; d <= 8; d++) {
        _SPC_CONVECTIVE_BY_DAY[d] = ['cat'];
    }

    const _SPC_CONVECTIVE_LABELS = {
        cat: 'Categorical',
        torn: 'Tornado',
        wind: 'Wind',
        hail: 'Hail',
        prob: 'Probabilistic',
    };

    function updateSpcConvective() {
        const sel = byId('weather-spc-convective');
        const daySel = byId('weather-spc-day');
        if (!sel || !daySel) return;

        const day = parseInt(daySel.value, 10) || 1;
        const allowed = _SPC_CONVECTIVE_BY_DAY[day] || ['cat'];
        const currentVal = sel.value;

        sel.innerHTML = '';
        // Always add placeholder first
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = '\u2014 Choose Product \u2014';
        placeholder.disabled = true;
        sel.appendChild(placeholder);
        allowed.forEach((val) => {
            const opt = document.createElement('option');
            opt.value = val;
            opt.textContent = _SPC_CONVECTIVE_LABELS[val] || val;
            sel.appendChild(opt);
        });

        if (allowed.includes(currentVal)) {
            sel.value = currentVal;
        } else {
            sel.value = '';
        }

        // Other Products (watches/mds/reports) only visible on Day 1
        const otherSel = byId('weather-spc-product');
        const otherLabel = otherSel?.previousElementSibling;
        const showOther = day === 1;
        if (otherSel) otherSel.style.display = showOther ? '' : 'none';
        if (otherLabel && otherLabel.tagName === 'LABEL') {
            otherLabel.style.display = showOther ? '' : 'none';
        }
        // If hiding other products, ensure last-touched falls back to convective
        // and hide any secondary sub-controls (report day, item selector)
        if (!showOther && _spcLastTouched === 'other') {
            _spcLastTouched = 'convective';
            if (otherSel) otherSel.value = '';
            updateSpcSubControls();
        }

        // Fire Weather Outlooks – available Day 1-8
        // (Day 1-2 via SPC static GeoJSON, Day 3-8 via NWS MapServer)
    }

    // ── Quick-range / custom date toggling ───────────────────────────────────
    function updateDateVisibility() {
        const quickRange = byId('weather-quick-range').value;
        const customDates = byId('weather-custom-dates');
        if (customDates) {
            customDates.style.display = quickRange === 'custom' ? '' : 'none';
        }
    }

    // ── Extent mode ──────────────────────────────────────────────────────────
    function updateExtentVisibility() {
        const mode = Number(byId('weather-extent-mode')?.value || 0);
        const custom = byId('weather-extent-custom-controls');
        if (custom) {
            custom.style.display = mode === 1 ? 'block' : 'none';
        }
    }

    // ── Build request params ─────────────────────────────────────────────────
    function buildParams(requestId) {
        const group = byId('weather-product-group').value;
        const product = getSelectedProduct();
        const region = byId('weather-region').value;
        const quickRange = byId('weather-quick-range').value;
        const fps = byId('weather-fps')?.value || '4';
        const frames = byId('weather-frames')?.value || '12';

        const params = new URLSearchParams();
        params.set('request_id', requestId);
        params.set('product_group', group);
        params.set('product', product);
        params.set('region', region);
        params.set('fps', fps);
        params.set('frames', frames);
        params.set('view_mode', 'layers');

        // SPC day parameter
        if (group === 'spc') {
            const day = byId('weather-spc-day')?.value || '1';
            params.set('day', day);
            if (product === 'reports') {
                params.set('report_day', byId('weather-report-day')?.value || 'today');
            }
            // Item selection for watches/mds
            if (product === 'watches' || product === 'mds') {
                const itemId = byId('weather-spc-item')?.value || 'all';
                if (itemId && itemId !== 'all' && itemId !== 'none') {
                    params.set('item_id', itemId);
                    // Auto-set custom extent from stored bounds + 1.5° padding
                    const bounds = _spcItemBoundsMap[itemId];
                    if (bounds) {
                        const pad = 1.5;
                        params.set('n', String(bounds.n + pad));
                        params.set('s', String(bounds.s - pad));
                        params.set('e', String(bounds.e + pad));
                        params.set('w', String(bounds.w - pad));
                    }
                }
            }
        }

        // Timezone
        try {
            params.set('user_tz', Intl.DateTimeFormat().resolvedOptions().timeZone);
        } catch (_) { /* ignore */ }

        // Date range
        if (quickRange === 'custom') {
            const dateFrom = byId('weather-date-from')?.value;
            const dateTo = byId('weather-date-to')?.value;
            if (dateFrom) params.set('date_from', dateFrom);
            if (dateTo) params.set('date_to', dateTo);
        } else if (quickRange !== 'current') {
            const hoursBack = parseFloat(quickRange);
            if (hoursBack > 0) {
                const now = new Date();
                const from = new Date(now.getTime() - hoursBack * 3600_000);
                params.set('date_from', from.toISOString().slice(0, 16));
                params.set('date_to', now.toISOString().slice(0, 16));
            }
        }

        // Custom extent
        const extentMode = Number(byId('weather-extent-mode')?.value || 0);
        if (extentMode === 1) {
            const n = byId('weather-n')?.value;
            const s = byId('weather-s')?.value;
            const e = byId('weather-e')?.value;
            const w = byId('weather-w')?.value;
            if (n) params.set('n', n);
            if (s) params.set('s', s);
            if (e) params.set('e', e);
            if (w) params.set('w', w);
        }

        return params;
    }

    // ── Layer visibility helpers ─────────────────────────────────────────────
    function applyLayerVisibility() {
        const layers = [
            { imgId: 'result-product-image', checkId: 'weather-show-product', opacityId: 'weather-opacity-product' },
            { imgId: 'result-legend-image', checkId: 'weather-show-legend', opacityId: 'weather-opacity-legend' },
            { imgId: 'result-hud-right-image', checkId: 'weather-show-hud-right', opacityId: 'weather-opacity-hud-right' },
        ];

        layers.forEach(({ imgId, checkId, opacityId }) => {
            const img = byId(imgId);
            const check = byId(checkId);
            const opacity = byId(opacityId);
            if (!img) return;
            if (check) {
                img.style.display = check.checked ? '' : 'none';
            }
            if (opacity) {
                img.style.opacity = opacity.value;
            }
        });
    }

    function bindLayerControls() {
        ['weather-show-product', 'weather-show-legend', 'weather-show-hud-right'].forEach((id) => {
            byId(id)?.addEventListener('change', applyLayerVisibility);
        });
        ['weather-opacity-product', 'weather-opacity-legend', 'weather-opacity-hud-right'].forEach((id) => {
            byId(id)?.addEventListener('input', applyLayerVisibility);
        });
    }

    // ── Scrubber ─────────────────────────────────────────────────────────────
    function updateScrubberFrame(index) {
        if (!currentFrames.length) return;
        const frameIndex = Math.max(0, Math.min(index, currentFrames.length - 1));
        const frame = currentFrames[frameIndex];

        const productImg = byId('result-product-image');
        const staticOverlayImg = byId('result-static-overlay-image');
        const hudImg = byId('result-hud-right-image');
        const legendImg = byId('result-legend-image');
        const tsLabel = byId('layered-timestamp');

        if (productImg && frame.product_url) {
            productImg.src = apiUrl(frame.product_url) + '?_ts=' + Date.now();
        }
        if (staticOverlayImg) {
            if (frame.static_overlay_url) {
                staticOverlayImg.src = apiUrl(frame.static_overlay_url) + '?_ts=' + Date.now();
                staticOverlayImg.style.display = '';
            } else {
                staticOverlayImg.src = '';
                staticOverlayImg.style.display = 'none';
            }
        }
        if (hudImg && frame.hud_right_url) {
            hudImg.src = apiUrl(frame.hud_right_url) + '?_ts=' + Date.now();
        }
        if (legendImg) {
            if (frame.legend_url) {
                legendImg.src = apiUrl(frame.legend_url) + '?_ts=' + Date.now();
                legendImg.style.display = '';
            } else {
                legendImg.src = '';
                legendImg.style.display = 'none';
            }
        }
        if (tsLabel) {
            tsLabel.textContent = frame.timestamp_local || frame.timestamp_utc || '';
        }
    }

    // ── Display layered result ───────────────────────────────────────────────
    function showLayeredResult(data) {
        currentData = data;
        currentFrames = data.frames || [];
        currentLayersPath = data.layers_path || '';

        // Hide flat image/video, show layered container
        const flatImg = byId('result-image');
        const flatVideo = byId('result-video');
        if (flatImg) flatImg.style.display = 'none';
        if (flatVideo) flatVideo.style.display = 'none';

        const container = byId('result-layered-container');
        if (container) container.style.display = 'block';

        // Basemap
        const basemapImg = byId('result-basemap-image');
        if (basemapImg && data.basemap_url) {
            basemapImg.src = apiUrl(data.basemap_url) + '?_ts=' + Date.now();
            basemapImg.style.display = '';
        }

        const staticOverlayImg = byId('result-static-overlay-image');
        if (staticOverlayImg) {
            staticOverlayImg.src = '';
            staticOverlayImg.style.display = 'none';
        }

        // Layer controls
        const layerControls = byId('weather-layer-controls');
        const layerNote = byId('weather-layer-controls-note');
        if (layerControls) layerControls.style.display = '';
        if (layerNote) layerNote.style.display = 'none';

        // Show/hide legend controls based on layer_defs
        const hasLegend = (data.layer_defs || []).some((d) => d.id === 'legend');
        const legendControlsRow = byId('weather-legend-controls');
        const legendOpacity = byId('weather-opacity-legend');
        if (legendControlsRow) legendControlsRow.style.display = hasLegend ? '' : 'none';
        if (legendOpacity) legendOpacity.style.display = hasLegend ? '' : 'none';

        // Scrubber
        const scrubber = byId('layered-scrubber');
        const scrubberControls = byId('layered-controls');
        if (currentFrames.length > 0) {
            if (scrubber) {
                scrubber.max = String(currentFrames.length - 1);
                scrubber.value = '0';
            }
            if (scrubberControls) scrubberControls.style.display = 'grid';
            updateScrubberFrame(0);
        } else {
            if (scrubberControls) scrubberControls.style.display = 'none';
        }

        applyLayerVisibility();
    }

    // ── Generate ─────────────────────────────────────────────────────────────
    async function generate() {
        const requestId = crypto.randomUUID();
        const params = buildParams(requestId);

        // Validate that a product is selected
        const product = params.get('product');
        if (!product) {
            setStatus('Please choose a product before generating.');
            return;
        }

        setStatus('');
        setOutputMeta({ state: 'running' });
        showProgress(0, 'Starting...');

        // Start progress polling
        const progressPromise = pollProgress(requestId, (progress) => {
            showProgress(progress.percent || 0, progress.message || '');
        });

        let response;
        try {
            response = await fetch(apiUrl(`/api/weather?${params.toString()}`));
        } catch (err) {
            hideProgress();
            setStatus(`Request failed: ${err.message}`);
            setOutputMeta({ state: 'unavailable' });
            return;
        }

        // Wait for progress polling to finish
        await progressPromise;
        hideProgress();

        let data;
        try {
            data = await response.json();
        } catch (err) {
            setStatus('Failed to parse response.');
            setOutputMeta({ state: 'unavailable' });
            return;
        }

        if (!response.ok) {
            const errMsg = data?.detail?.error || data?.error || data?.message || 'Unknown error';
            setStatus(`Error: ${errMsg}`);
            setOutputMeta({ state: 'unavailable' });
            return;
        }

        setOutputMetaFromResponse(data);

        if (data.status === 'warning') {
            setStatus(data.message || 'No output generated.');
            return;
        }

        if (data.output_mode === 'layers') {
            showLayeredResult(data);
            setStatus(data.message || 'Done.');
        } else if (data.image_url) {
            displayImage(data.image_url);
            setStatus(data.message || 'Done.');
        } else {
            setStatus(data.message || 'No output.');
        }
    }

    // ── Export frame ─────────────────────────────────────────────────────────
    async function exportCurrentFrame() {
        if (!currentLayersPath) {
            setStatus('No active session for export.');
            return;
        }
        const scrubber = byId('layered-scrubber');
        const frameIndex = scrubber ? parseInt(scrubber.value, 10) : 0;

        setStatus('Exporting frame...');
        try {
            const params = new URLSearchParams({
                layers_path: currentLayersPath,
                frame_index: String(frameIndex),
            });
            const response = await fetch(apiUrl(`/api/weather/export-frame?${params.toString()}`));
            const data = await response.json();

            if (data.status === 'warning' || !data.image_url) {
                setStatus(data.message || 'Export failed.');
                return;
            }

            // Open exported image in new tab
            window.open(apiUrl(data.image_url), '_blank');
            setStatus('Frame exported.');
        } catch (err) {
            setStatus(`Export failed: ${err.message}`);
        }
    }

    // ── Export animation ─────────────────────────────────────────────────────
    async function exportAnimation() {
        if (!currentLayersPath) {
            setStatus('No active session for export.');
            return;
        }

        const fps = byId('weather-fps')?.value || '4';
        setStatus('Exporting animation...');
        try {
            const params = new URLSearchParams({
                layers_path: currentLayersPath,
                fps: fps,
            });
            const response = await fetch(apiUrl(`/api/weather/export-animation?${params.toString()}`));
            const data = await response.json();

            if (data.status === 'warning' || !data.image_url) {
                setStatus(data.message || 'Export failed.');
                return;
            }

            displayVideo(data.image_url);
            setStatus('Animation exported.');
        } catch (err) {
            setStatus(`Export failed: ${err.message}`);
        }
    }

    // ── Reset ────────────────────────────────────────────────────────────────
    function resetControls() {
        byId('weather-product-group').value = 'surface';
        updateProductOpts();

        byId('weather-surface-product').value = 'Station Plot';
        byId('weather-region').value = 'CONUS';
        byId('weather-quick-range').value = 'current';
        updateDateVisibility();

        const daySel = byId('weather-spc-day');
        if (daySel) daySel.value = '1';
        _spcLastTouched = 'convective';
        const otherSel = byId('weather-spc-product');
        if (otherSel) otherSel.value = '';
        const fireSel = byId('weather-spc-fire');
        if (fireSel) fireSel.value = '';
        const reportDaySel = byId('weather-report-day');
        if (reportDaySel) reportDaySel.value = 'today';
        const itemSel = byId('weather-spc-item');
        if (itemSel) { itemSel.innerHTML = '<option value="all" selected>All</option>'; itemSel.style.display = 'none'; }
        const itemLabel = byId('weather-spc-item-label');
        if (itemLabel) itemLabel.style.display = 'none';
        _spcItemBoundsMap = {};
        updateSpcConvective();
        updateSpcSubControls();

        const fps = byId('weather-fps');
        if (fps) fps.value = '4';
        const frames = byId('weather-frames');
        if (frames) frames.value = '12';

        const extentMode = byId('weather-extent-mode');
        if (extentMode) extentMode.value = '0';
        updateExtentVisibility();

        ['weather-n', 'weather-s', 'weather-e', 'weather-w'].forEach((id) => {
            const el = byId(id);
            if (el) el.value = '';
        });

        if (typeof bindRangeValueLabels === 'function') {
            bindRangeValueLabels();
        }
    }

    // ── Extent modal ─────────────────────────────────────────────────────────
    function initExtentModal() {
        if (typeof createExtentSelectorModal !== 'function') return;

        const modal = createExtentSelectorModal({
            modalId: 'map-modal',
            mapId: 'leaflet-map',
            closeButtonId: 'map-modal-close',
            initialCenter: [35.5, -79.0],
            initialZoom: 6,
            onBoundsSelected: (bounds) => {
                byId('weather-n').value = bounds.getNorth().toFixed(2);
                byId('weather-s').value = bounds.getSouth().toFixed(2);
                byId('weather-e').value = bounds.getEast().toFixed(2);
                byId('weather-w').value = bounds.getWest().toFixed(2);
            },
            onOpen: (map) => {
                if (typeof refreshExtentSelectorOverlays === 'function') {
                    refreshExtentSelectorOverlays(map, {
                        region: byId('weather-region')?.value || 'CONUS',
                    });
                }
            },
        });

        byId('weather-open-map')?.addEventListener('click', () => modal.open());
    }

    // ── SPC sub-control visibility (report day + item selector) ───────────
    function updateReportDayVisibility() { updateSpcSubControls(); }

    async function updateSpcSubControls() {
        const group = byId('weather-product-group')?.value;
        const otherSel = byId('weather-spc-product');
        const product = otherSel?.value || '';

        // Report Day – visible only when reports selected
        const showReport = group === 'spc' && product === 'reports';
        const reportDaySel = byId('weather-report-day');
        const reportDayLabel = byId('weather-report-day-label');
        if (reportDaySel) reportDaySel.style.display = showReport ? '' : 'none';
        if (reportDayLabel) reportDayLabel.style.display = showReport ? '' : 'none';

        // Item selector – visible only when watches or mds selected
        const itemSel = byId('weather-spc-item');
        const itemLabel = byId('weather-spc-item-label');
        const showItem = group === 'spc' && (product === 'watches' || product === 'mds');

        if (!showItem) {
            if (itemSel) itemSel.style.display = 'none';
            if (itemLabel) itemLabel.style.display = 'none';
            _spcItemBoundsMap = {};
            return;
        }

        // Show and populate
        if (itemLabel) {
            itemLabel.style.display = '';
            itemLabel.textContent = product === 'watches' ? 'Select Watch' : 'Select MD';
        }
        if (itemSel) itemSel.style.display = '';

        // Fetch items from API
        try {
            const resp = await fetch(apiUrl(`/api/weather/spc-items?product=${encodeURIComponent(product)}`));
            const data = await resp.json();
            const items = data.items || [];

            _spcItemBoundsMap = {};
            if (itemSel) {
                itemSel.innerHTML = '';
                const allOpt = document.createElement('option');
                allOpt.value = 'all';
                allOpt.textContent = 'All';
                allOpt.selected = true;
                itemSel.appendChild(allOpt);

                if (items.length === 0) {
                    const noneOpt = document.createElement('option');
                    noneOpt.value = 'none';
                    noneOpt.textContent = product === 'watches'
                        ? 'No active watches' : 'No active MDs';
                    noneOpt.disabled = true;
                    itemSel.appendChild(noneOpt);
                } else {
                    items.forEach((item) => {
                        const opt = document.createElement('option');
                        opt.value = item.id;
                        opt.textContent = item.label || `#${item.id}`;
                        itemSel.appendChild(opt);
                        if (item.bounds) {
                            _spcItemBoundsMap[String(item.id)] = item.bounds;
                        }
                    });
                }
            }
        } catch (err) {
            console.warn('Failed to fetch SPC items:', err);
        }
    }

    // ── Init ─────────────────────────────────────────────────────────────────
    function init() {
        // Product group switching
        byId('weather-product-group')?.addEventListener('change', updateProductOpts);
        updateProductOpts();

        // MRMS sub-product controls
        byId('weather-mrms-product')?.addEventListener('change', updateMrmsSubControls);
        byId('weather-mrms-qpe-source')?.addEventListener('change', updateMrmsSubControls);
        updateMrmsSubControls();

        // SPC day change updates convective outlook list
        byId('weather-spc-day')?.addEventListener('change', updateSpcConvective);

        // SPC last-touched tracking: selecting one dropdown resets the others
        // to the placeholder so only one has an active selection at a time.
        byId('weather-spc-convective')?.addEventListener('change', () => {
            _spcLastTouched = 'convective';
            const otherSel = byId('weather-spc-product');
            if (otherSel) otherSel.value = '';
            const fireSel = byId('weather-spc-fire');
            if (fireSel) fireSel.value = '';
            updateSpcSubControls();
        });
        byId('weather-spc-fire')?.addEventListener('change', () => {
            _spcLastTouched = 'fire';
            const convSel = byId('weather-spc-convective');
            if (convSel) convSel.value = '';
            const otherSel = byId('weather-spc-product');
            if (otherSel) otherSel.value = '';
            updateSpcSubControls();
        });
        byId('weather-spc-product')?.addEventListener('change', () => {
            _spcLastTouched = 'other';
            const convSel = byId('weather-spc-convective');
            if (convSel) convSel.value = '';
            const fireSel = byId('weather-spc-fire');
            if (fireSel) fireSel.value = '';
            updateSpcSubControls();
        });

        // Quick range / date toggling
        byId('weather-quick-range')?.addEventListener('change', updateDateVisibility);
        updateDateVisibility();

        // Extent mode
        byId('weather-extent-mode')?.addEventListener('input', updateExtentVisibility);
        updateExtentVisibility();

        // Layer controls
        bindLayerControls();

        // Scrubber
        byId('layered-scrubber')?.addEventListener('input', (e) => {
            updateScrubberFrame(parseInt(e.target.value, 10));
        });
        byId('layered-step-back')?.addEventListener('click', () => {
            const scrubber = byId('layered-scrubber');
            if (!scrubber) return;
            const current = parseInt(scrubber.value || '0', 10);
            updateScrubberFrame(Math.max(0, current - 1));
        });
        byId('layered-step-fwd')?.addEventListener('click', () => {
            const scrubber = byId('layered-scrubber');
            if (!scrubber || !currentFrames.length) return;
            const current = parseInt(scrubber.value || '0', 10);
            updateScrubberFrame(Math.min(currentFrames.length - 1, current + 1));
        });

        // Buttons
        byId('weather-generate')?.addEventListener('click', generate);
        byId('weather-reset-controls')?.addEventListener('click', resetControls);
        byId('layered-save-current')?.addEventListener('click', exportCurrentFrame);
        byId('layered-export-animation')?.addEventListener('click', exportAnimation);

        // Extent modal
        initExtentModal();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})();
