(function () {
    'use strict';

    function createRtmaEngine(context) {
        async function loadRtma() {
            if (!context.isTypeEnabled('rtma')) return;
            const requestSeq = context.nextRequestSeq();
            const region = context.activeRegion();
            const stream = context.activeStream();
            const product = context.activeProduct();
            if (!region || !stream || !product) return;

            context.setStatus(`Loading ${region} ${stream} ${product}...`);

            let usedPrerender = false;
            let pointsSourceDataKey = '';

            try {
                if (product !== 'wind_direction') {
                    const overlayResp = await fetch(
                        context.apiUrl(
                            `/api/overlay/latest?family=rtma&region=${encodeURIComponent(region)}&stream=${encodeURIComponent(stream)}&product=${encodeURIComponent(product)}`
                        )
                    );
                    if (overlayResp.ok) {
                        const overlayData = await overlayResp.json();
                        if (!context.isCurrentRequestSeq(requestSeq) || !context.canApplyResponse()) return;

                        const imageUrl = overlayData?.render?.image_url;
                        const bounds = overlayData?.bounds;
                        pointsSourceDataKey = typeof overlayData?.source_data_key === 'string'
                            ? overlayData.source_data_key : '';

                        if (imageUrl && Array.isArray(bounds) && bounds.length === 4) {
                            context.clearGradientLayer();
                            context.clearRtmaOverlay();
                            const leafletBounds = [[bounds[2], bounds[0]], [bounds[3], bounds[1]]];
                            context.setGradientLayer(
                                context.leaflet.imageOverlay(context.apiUrl(imageUrl), leafletBounds, {
                                    opacity: context.getGradientOpacity(),
                                    className: 'surface-gradient-overlay',
                                }).addTo(context.map)
                            );
                            context.buildRtmaLegend(overlayData);
                            const dataTsMs = context.resolveTimestampMs(overlayData?.timestamp);
                            const staleNote = context.staleNoteForTimestamp(dataTsMs, context.rtmaStaleMs(stream, product));
                            const title = overlayData?.full_name || product;
                            context.setStatus(`RTMA ${title} valid ${context.formatValidTimeLabel(dataTsMs)}${staleNote}.`);
                            context.setViewerTimestamp(dataTsMs);
                            context.setReliability('rtma', `RTMA ${title}`, `NOAA ${stream}`, dataTsMs);
                            context.setTimestampSource('rtma', 'overlay_meta_timestamp', dataTsMs);
                            usedPrerender = true;
                        }
                    }
                }
            } catch (_preErr) {
                // fall through to on-demand path
            }

            if (!usedPrerender && product !== 'wind_direction') {
                try {
                    const bounds = context.getMapBounds();
                    const south = Number(bounds.south).toFixed(4);
                    const west = Number(bounds.west).toFixed(4);
                    const north = Number(bounds.north).toFixed(4);
                    const east = Number(bounds.east).toFixed(4);
                    const dataResp = await fetch(
                        context.apiUrl(
                            `/api/data/rtma?region=${encodeURIComponent(region)}&stream=${encodeURIComponent(stream)}` +
                            `&product=${encodeURIComponent(product)}&south=${south}&west=${west}&north=${north}&east=${east}`
                        )
                    );
                    if (dataResp.ok) {
                        const data = await dataResp.json();
                        if (!context.isCurrentRequestSeq(requestSeq) || !context.canApplyResponse()) return;

                        context.clearGradientLayer();
                        context.clearRtmaOverlay();
                        const b = data?.bounds;
                        const imageUrl = data?.image_url;
                        pointsSourceDataKey = typeof data?.source_data_key === 'string' ? data.source_data_key : '';

                        if (imageUrl && Array.isArray(b) && b.length === 4) {
                            const leafletBounds = [[b[2], b[0]], [b[3], b[1]]];
                            context.setGradientLayer(
                                context.leaflet.imageOverlay(context.apiUrl(imageUrl), leafletBounds, {
                                    opacity: context.getGradientOpacity(),
                                    className: 'surface-gradient-overlay',
                                }).addTo(context.map)
                            );
                            context.buildRtmaLegend(data);
                            const dataTsMs = context.resolveTimestampMs(data?.timestamp);
                            const staleNote = context.staleNoteForTimestamp(dataTsMs, context.rtmaStaleMs(stream, product));
                            const title = data?.full_name || product;
                            context.setStatus(`RTMA ${title} valid ${context.formatValidTimeLabel(dataTsMs)}${staleNote}.`);
                            context.setViewerTimestamp(dataTsMs);
                            context.setReliability('rtma', `RTMA ${title}`, `NOAA ${stream}`, dataTsMs);
                            context.setTimestampSource('rtma', data?.timestamp_source || 'rtma_data_endpoint', dataTsMs);
                            usedPrerender = true;
                        }
                    }
                } catch (_fallbackErr) {
                    // points-only fallback below still runs
                }
            }

            try {
                const url = context.apiUrl(
                    `/api/data/rtma/points?region=${encodeURIComponent(region)}&stream=${encodeURIComponent(stream)}&product=${encodeURIComponent(product)}` +
                    (pointsSourceDataKey ? `&source_data_key=${encodeURIComponent(pointsSourceDataKey)}` : '')
                );
                const resp = await fetch(url);
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                    throw new Error(err.detail || resp.statusText);
                }
                const data = await resp.json();
                if (!context.isCurrentRequestSeq(requestSeq) || !context.canApplyResponse()) return;

                if (!usedPrerender) context.clearRtmaOverlay();
                context.setRtmaPoints(data, region, stream, product, pointsSourceDataKey);
                context.renderRtmaPoints();

                if (!usedPrerender) {
                    context.buildRtmaLegend(data);
                    const dataTsMs = context.resolveTimestampMs(data?.timestamp);
                    const title = data?.full_name || product;
                    context.setStatus(`RTMA ${title} — overlay cache not yet built (markers only).`);
                    context.setViewerTimestamp(dataTsMs);
                    context.setReliability('rtma', `RTMA ${title}`, `NOAA ${stream}`, dataTsMs);
                    context.setTimestampSource('rtma', data?.timestamp_source || 'points_source_timestamp', dataTsMs);
                }
            } catch (err) {
                if (!context.isCurrentRequestSeq(requestSeq)) return;
                console.error('[rtma] Load error:', err);
                if (!usedPrerender) {
                    context.clearGradientLayer();
                    context.clearRtmaPointLayer();
                    context.setLegend(null);
                    context.setStatus(`RTMA error: ${err.message}`);
                }
            }
        }

        async function loadScrubberFrames() {
            if (!context.isTypeEnabled('rtma')) return;
            context.exitMrmsScrubMode(false);

            const loadSeq = context.nextScrubLoadSeq();
            const region = context.activeRegion();
            const stream = context.activeStream();
            const product = context.activeProduct();
            if (!region || !stream || !product) {
                context.setStatus('Select an RTMA stream and product first.');
                return;
            }

            context.stopRtmaScrubPlay();
            context.incrementRtmaScrubRenderSeq();
            context.setRtmaScrubFrames([]);
            context.clearRtmaScrubFrameErrors();
            context.setRtmaScrubFrameIndex(0);
            context.clearRtmaScrubFrameCache();
            context.setArchiveScrubber(true);
            context.showRtmaLookbackSlider(true);
            context.setArchiveProgress(true, 10, 'Loading RTMA frame list...');
            context.setScrubberControlsEnabled(false);
            context.updateRtmaScrubberUi();

            const maxHours = context.rtmaLookbackHours(stream);
            context.startRtmaHistoryPoll(region, stream, product, maxHours);

            try {
                let usedCache = false;
                try {
                    const cacheParams = new URLSearchParams({ family: 'rtma', region, stream, product, hours: String(maxHours) });
                    const cacheResp = await fetch(context.apiUrl(`/api/overlay/frames?${cacheParams.toString()}`), { cache: 'no-store' });
                    if (!context.isCurrentScrubLoadSeq(loadSeq) || !context.isTypeEnabled('rtma')) return;
                    if (cacheResp.ok) {
                        const cacheData = await cacheResp.json();
                        const rawFrames = Array.isArray(cacheData.frames) ? cacheData.frames : [];
                        if (rawFrames.length > 0) {
                            context.setRtmaScrubFrames(rawFrames.map((f) => ({
                                frame_key: f.frame_key,
                                source_data_key: f.source_data_key || '',
                                timestamp: f.timestamp || '',
                                region, stream, product,
                                _image_url: f.image_url || null,
                                _bounds: f.bounds || null,
                            })));
                            usedCache = true;
                        }
                    }
                } catch (_cacheErr) { /* fall through */ }

                if (!usedCache) {
                    const url = context.apiUrl(
                        `/api/data/rtma/frames?region=${encodeURIComponent(region)}` +
                        `&stream=${encodeURIComponent(stream)}&product=${encodeURIComponent(product)}` +
                        `&max_hours=${encodeURIComponent(maxHours)}`
                    );
                    const resp = await fetch(url);
                    if (!context.isCurrentScrubLoadSeq(loadSeq) || !context.isTypeEnabled('rtma')) return;
                    if (!resp.ok) {
                        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                        throw new Error(err.detail || resp.statusText);
                    }
                    const data = await resp.json();
                    context.setRtmaScrubFrames(Array.isArray(data.frames) ? data.frames : []);
                }

                if (!context.isCurrentScrubLoadSeq(loadSeq) || !context.isTypeEnabled('rtma')) return;

                if (!context.getRtmaScrubFrames().length) {
                    context.setArchiveProgress(false);
                    context.setArchiveScrubber(true);
                    context.setScrubberControlsEnabled(false);
                    context.updateRtmaScrubberUi();
                    context.setRtmaScrubberStatus('No frames found for selected product/stream/window.');
                    context.setStatus('No RTMA frames found for the selected settings.');
                    return;
                }

                context.setArchiveProgress(false);
                context.setArchiveScrubber(true);
                context.showRtmaLookbackSlider(true);
                context.setScrubberControlsEnabled(true);
                const sourceLabel = usedCache ? 'pre-rendered cache' : 'S3';
                context.setRtmaScrubberStatus(`${context.getRtmaScrubFrames().length} frames from ${sourceLabel} (${maxHours}h window).`);
                context.startRtmaAutoRefresh();
                await context.renderRtmaScrubFrame(0);
            } catch (err) {
                if (!context.isCurrentScrubLoadSeq(loadSeq) || !context.isTypeEnabled('rtma')) return;
                context.setArchiveProgress(false);
                context.setScrubberControlsEnabled(false);
                context.setRtmaScrubberStatus(`Error: ${err.message}`);
                context.setStatus(`RTMA scrubber load error: ${err.message}`);
            }
        }

        return Object.freeze({ loadRtma, loadScrubberFrames });
    }

    window.NCHRtmaEngine = Object.freeze({ createRtmaEngine });
}());
