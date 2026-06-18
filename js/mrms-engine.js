(function () {
    'use strict';

    const MRMS_STALE_MS = 90 * 60 * 1000;

    function createMrmsEngine(context) {
        function isCurrentSeq(seq) {
            return context.isCurrentRequestSeq(seq);
        }

        async function loadMrms() {
            if (!context.isTypeEnabled('mrms')) return;
            const product = context.composeMrmsProductKey();
            if (!product) return;

            const requestSeq = context.nextRequestSeq();
            const statusEl = document.getElementById('weather-mrms-status');
            if (statusEl) statusEl.textContent = `Loading ${product}...`;
            context.setStatus(`Loading MRMS ${product}...`);

            try {
                await context.setWorkerProduct(product);

                let data = null;
                const overlayResp = await fetch(
                    context.apiUrl(
                        `/api/overlay/latest?family=mrms&region=CONUS&stream=default&product=${encodeURIComponent(product)}`
                    )
                );
                if (overlayResp.ok) {
                    const overlayData = await overlayResp.json();
                    data = {
                        image_url: overlayData?.render?.image_url ?? '',
                        bounds: overlayData?.bounds ?? [],
                        legend: overlayData?.legend ?? null,
                        full_name: overlayData?.full_name ?? product,
                        units: overlayData?.units ?? '',
                        vmin: overlayData?.vmin ?? null,
                        vmax: overlayData?.vmax ?? null,
                        timestamp: overlayData?.timestamp ?? null,
                    };
                    const overlayTsMs = context.resolveTimestampMs(data?.timestamp) || 0;
                    if (!overlayTsMs || (Date.now() - overlayTsMs) > MRMS_STALE_MS) {
                        data = null;
                    }
                }

                if (!data || !data.image_url) {
                    const legacyResp = await fetch(
                        context.apiUrl(
                            `/api/data/mrms?product=${encodeURIComponent(product)}&south=21.0&west=-130.0&north=52.0&east=-60.0`
                        )
                    );
                    if (!legacyResp.ok) {
                        const err = await legacyResp.json().catch(() => ({ detail: legacyResp.statusText }));
                        throw new Error(err.detail || legacyResp.statusText);
                    }
                    data = await legacyResp.json();
                }

                if (!isCurrentSeq(requestSeq) || !context.canApplyResponse()) return;

                const oldOverlay = context.getOverlay();
                if (oldOverlay) context.map.removeLayer(oldOverlay);

                const b = data.bounds;
                const leafletBounds = [[b[2], b[0]], [b[3], b[1]]];
                const newOverlay = context.leaflet.imageOverlay(context.apiUrl(data.image_url), leafletBounds, {
                    opacity: context.getOpacity(),
                });
                newOverlay._isMrmsOverlay = true;
                if (context.isTypeEnabled('mrms')) newOverlay.addTo(context.map);
                context.setOverlay(newOverlay);

                context.buildLegend(data);

                const dataTsMs = context.resolveTimestampMs(data?.timestamp);
                const staleNote = context.staleNoteForTimestamp(dataTsMs, MRMS_STALE_MS);
                if (statusEl) statusEl.textContent = `${data.full_name} valid ${context.formatValidTimeLabel(dataTsMs)}${staleNote}`;
                context.setStatus(`MRMS ${product} valid ${context.formatValidTimeLabel(dataTsMs)}.${staleNote}`);
                context.setViewerTimestamp(dataTsMs);
                context.setReliability('mrms', `MRMS ${product}`, 'NOAA MRMS', dataTsMs);
                context.setTimestampSource('mrms', data?.timestamp_source || 'grib_data_timestamp', dataTsMs);
            } catch (err) {
                if (!isCurrentSeq(requestSeq)) return;
                console.error('[mrms] Load error:', err);
                const statusEl2 = document.getElementById('weather-mrms-status');
                if (statusEl2) statusEl2.textContent = `Error: ${err.message}`;
                context.setStatus(`MRMS error: ${err.message}`);
            }
        }

        async function loadScrubberFrames() {
            if (!context.isTypeEnabled('mrms')) return;
            context.exitRtmaScrubMode(false);

            const product = context.composeMrmsProductKey();
            if (!product) {
                context.setStatus('Select an MRMS product first.');
                return;
            }

            const loadSeq = context.nextScrubLoadSeq();
            await context.setWorkerProduct(product);
            context.stopMrmsScrubPlay();
            context.incrementMrmsScrubRenderSeq();
            context.setMrmsScrubFrames([]);
            context.setMrmsScrubFrameIndex(0);
            context.setArchiveScrubber(true);
            context.showMrmsLookbackSlider(true);
            context.setArchiveProgress(true, 10, 'Loading MRMS frame list...');
            context.setScrubberControlsEnabled(false);
            context.updateRtmaScrubberUi();

            const maxHours = context.mrmsLookbackHours();

            try {
                const params = new URLSearchParams({ family: 'mrms', product, hours: String(maxHours) });
                const resp = await fetch(context.apiUrl(`/api/overlay/frames?${params.toString()}`), { cache: 'no-store' });
                if (!context.isCurrentScrubLoadSeq(loadSeq) || !context.isTypeEnabled('mrms')) return;
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                    throw new Error(err.detail || resp.statusText);
                }

                const data = await resp.json();
                const rawFrames = Array.isArray(data.frames) ? data.frames : [];
                const frames = rawFrames.map((f) => ({
                    frame_key: f.frame_key,
                    source_data_key: f.source_data_key || '',
                    image_url: f.image_url || '',
                    bounds: f.bounds || null,
                    timestamp: f.timestamp || '',
                    legend: f.legend || null,
                    full_name: f.full_name || product,
                    units: f.units || '',
                    vmin: f.vmin ?? null,
                    vmax: f.vmax ?? null,
                    product,
                }));
                context.setMrmsScrubFrames(frames);

                if (!context.isCurrentScrubLoadSeq(loadSeq) || !context.isTypeEnabled('mrms')) return;
                if (!frames.length) {
                    context.setArchiveProgress(false);
                    context.setArchiveScrubber(false);
                    context.setScrubberControlsEnabled(false);
                    context.updateRtmaScrubberUi();
                    context.setRtmaScrubberStatus('');
                    context.incrementMrmsScrubLoadSeq();
                    context.incrementMrmsScrubRenderSeq();
                    context.setStatus(`No MRMS animation frames found for ${product}; loading current overlay...`);
                    await loadMrms();
                    return;
                }

                context.setArchiveProgress(false);
                context.setScrubberControlsEnabled(true);
                context.setRtmaScrubberStatus(`${frames.length} MRMS frames from cache (${maxHours}h window).`);
                context.startMrmsAutoRefresh();
                await context.renderMrmsScrubFrame(0);
            } catch (err) {
                if (!context.isCurrentScrubLoadSeq(loadSeq) || !context.isTypeEnabled('mrms')) return;
                context.setArchiveProgress(false);
                context.setScrubberControlsEnabled(false);
                context.setRtmaScrubberStatus(`Error: ${err.message}`);
                context.setStatus(`MRMS scrubber load error: ${err.message}`);
            }
        }

        async function loadArchive(dtFrom, dtTo) {
            const product = context.composeMrmsProductKey();
            if (!product) {
                context.setStatus('Select an MRMS product first.');
                return;
            }

            const bounds = context.getMapBounds();
            const requestId = `arc_mrms_${Date.now()}`;
            const url = context.apiUrl(
                `/api/archive/mrms?product=${encodeURIComponent(product)}` +
                `&date_from=${encodeURIComponent(dtFrom)}` +
                `&date_to=${encodeURIComponent(dtTo)}` +
                `&max_frames=12&south=${bounds.south.toFixed(4)}&west=${bounds.west.toFixed(4)}` +
                `&north=${bounds.north.toFixed(4)}&east=${bounds.east.toFixed(4)}` +
                `&request_id=${requestId}`
            );

            try {
                const resp = await fetch(url);
                if (!resp.ok) {
                    const error = await resp.json().catch(() => ({}));
                    throw new Error(error.detail || resp.statusText);
                }

                const data = await resp.json();
                if (data.status === 'success') {
                    context.onArchiveFramesReady(data.frames);
                    return;
                }
                await context.pollArchiveProgress(data.request_id || requestId, data.session_id);
            } catch (err) {
                context.setArchiveProgress(true, 0, `Error: ${err.message}`);
                context.setStatus(`Archive MRMS error: ${err.message}`);
            }
        }

        return Object.freeze({ loadArchive, loadMrms, loadScrubberFrames });
    }

    window.NCHMrmsEngine = Object.freeze({ createMrmsEngine });
}());
