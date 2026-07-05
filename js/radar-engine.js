(function () {
    'use strict';

    function requireContextFunction(context, name) {
        if (typeof context?.[name] !== 'function') {
            throw new Error(`Radar engine context missing function: ${name}`);
        }
        return context[name];
    }

    function createRadarEngine(context) {
        const isArchiveMode = requireContextFunction(context, 'isArchiveMode');
        const isTypeEnabled = requireContextFunction(context, 'isTypeEnabled');
        const activeSite = requireContextFunction(context, 'activeSite');
        const activeProduct = requireContextFunction(context, 'activeProduct');
        const activeElevation = requireContextFunction(context, 'activeElevation');
        const hasMultiSites = requireContextFunction(context, 'hasMultiSites');
        const multiSitesHas = requireContextFunction(context, 'multiSitesHas');
        const isCurrentLiveRequestSeq = requireContextFunction(context, 'isCurrentLiveRequestSeq');
        const isCurrentScrubLoadSeq = requireContextFunction(context, 'isCurrentScrubLoadSeq');

        function canApplyResponse(site, product) {
            if (isArchiveMode() || !isTypeEnabled('radar')) return false;
            if (activeProduct() !== product) return false;
            if (hasMultiSites()) return multiSitesHas(site);
            return activeSite() === site;
        }

        function stormMotionLabel(data) {
            const motion = data?.storm_motion;
            const speed = Number(motion?.speed_kt);
            const direction = Number(motion?.motion_to_degrees);
            if (!Number.isFinite(speed) || !Number.isFinite(direction)) return '';
            const cell = String(motion?.cell_id || '').trim();
            const source = String(motion?.source || '').trim() || 'motion';
            return cell
                ? ` — SRV ${source} cell ${cell}: ${Math.round(speed)} kt toward ${Math.round(direction)}°`
                : ` — SRV ${source}: ${Math.round(speed)} kt toward ${Math.round(direction)}°`;
        }

        async function loadLiveLatest() {
            const site = activeSite();
            const product = activeProduct();
            const elevation = activeElevation();
            const siteConfigured = context.isSiteConfigured(site);
            const requestSeq = context.nextLiveRequestSeq();
            if (context.hasLatestRetryForOtherSelection(site, product)) {
                context.clearLatestRetry();
            }
            context.syncSiteLayerVisibility();
            context.ensureBackdropLayer();

            if (!site) {
                context.clearLatestRetry();
                context.clearLiveLayers();
                context.setRadarStatus('');
                context.setGlobalStatus('Select a radar site to load live radar.');
                context.buildSiteMarkerLegend();
                return;
            }

            context.setRadarStatus(
                siteConfigured
                    ? `Loading ${site} ${product} live radar...`
                    : `Loading ${site} ${product} live radar (on-demand L3 render)...`,
            );
            context.setGlobalStatus(`Loading radar site ${site} (${product})...`);

            try {
                const params = new URLSearchParams({ site, product, elevation });
                context.appendSrvMotionParams?.(params);
                if (!siteConfigured) params.set('force', '1');
                const resp = await context.fetchFn(context.apiUrl(`/api/radar/live/latest?${params.toString()}`), {
                    cache: 'no-store',
                });

                if (!isCurrentLiveRequestSeq(requestSeq) || !canApplyResponse(site, product)) return;

                let data = null;
                try {
                    data = await resp.json();
                } catch (_) {
                    data = null;
                }

                if (!resp.ok) {
                    const detail = String(data?.detail || data?.error || `HTTP ${resp.status}`);
                    throw new Error(detail);
                }

                if (typeof data?.configured === 'boolean') {
                    context.setSiteConfigured(site, data.configured);
                }
                context.updateElevationOptions(data);

                const imageUrl = data?.image_url;
                const bounds = Array.isArray(data?.bounds) ? data.bounds : null;
                if (!imageUrl || !bounds || bounds.length !== 4) {
                    throw new Error('Live radar image/bounds unavailable.');
                }

                await context.renderLiveLatestFrame({ data, site, product, requestSeq });

                if (!isCurrentLiveRequestSeq(requestSeq) || !canApplyResponse(site, product)) return;
                context.clearLatestRetry();
                context.loadStormTracks?.(data?.timestamp);

                const timestampMs = context.resolveDataTimestampMs(data?.timestamp);
                context.setViewerTimestamp(timestampMs);
                context.setReliability('radar', `Radar ${product}`, data?.full_name || `Radar ${product}`, timestampMs);
                context.buildProductLegend(product);
                context.setTimestampSource('radar', 'radar_live_latest', timestampMs);

                const provider = String(data?.source || 'live_cache').replaceAll('_', ' ');
                const motionLabel = stormMotionLabel(data);
                context.setRadarStatus(`${site} ${product} live radar loaded${motionLabel}.`);
                context.setGlobalStatus(`${site} ${product} ${context.formatValidTimeLabel(timestampMs)} (${provider})${motionLabel}.`);

                if (data.history_filling) {
                    context.startHistoryPoll(site, product);
                } else {
                    context.stopHistoryPoll();
                    context.setAnimateButtonFilling(false);
                }
            } catch (err) {
                if (!isCurrentLiveRequestSeq(requestSeq) || !canApplyResponse(site, product)) return;
                context.clearLiveLayers();
                const detail = String(err?.message || '');
                const noFrameYet = /no live radar frame cached yet|latest live radar image is missing/i.test(detail);
                if (noFrameYet) {
                    context.setRadarStatus(`Warming ${site} ${product} live radar...`);
                    context.setGlobalStatus(`Radar ${site}/${product} is warming cache. Retrying automatically...`);
                    context.scheduleLatestRetry(site, product);
                    return;
                }
                context.setRadarStatus(`Unable to load ${site} ${product} live radar.`);
                context.setGlobalStatus(`Radar live load failed for ${site}/${product}: ${err.message}`);
            }
        }

        async function loadScrubberFrames() {
            context.exitRtmaScrubMode(false);
            context.exitMrmsScrubMode(false);
            context.stopScrubWarmPoll();

            const loadSeq = context.nextScrubLoadSeq();
            const site = activeSite();
            const product = activeProduct();
            const elevation = activeElevation();
            const contextKey = context.currentScrubContextKey(product);
            if (!site) {
                context.setArchiveScrubber(true);
                context.setScrubberControlsEnabled(false);
                context.setRtmaScrubberStatus('Select a radar site to animate scrubber frames.');
                context.setRadarStatus(`Select a radar site to animate ${product}.`);
                context.setGlobalStatus('Select a radar site first (National Composite has no frame scrubber).');
                return;
            }

            context.stopScrubPlay();
            context.incrementScrubRenderSeq();
            context.clearScrubOverlayPool?.();
            context.setScrubFrames([]);
            context.setScrubContextKey(contextKey);
            context.setScrubFrameIndex(0);
            context.setArchiveScrubber(true);
            context.showLookbackSlider(true);
            context.setArchiveProgress(true, 10, 'Loading Radar frame list...');
            context.setScrubberControlsEnabled(false);
            context.setRadarStatus(`Loading ${site} ${product} radar animation frames...`);
            context.updateRtmaScrubberUi();

            const maxHours = context.radarLookbackHours();

            try {
                const params = new URLSearchParams({
                    site,
                    product,
                    elevation,
                    hours: String(maxHours),
                });
                context.appendSrvMotionParams?.(params);
                const resp = await context.fetchFn(context.apiUrl(`/api/radar/live/frames?${params.toString()}`), {
                    cache: 'no-store',
                });
                if (!isCurrentScrubLoadSeq(loadSeq) || !isTypeEnabled('radar')) return;

                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                    throw new Error(err.detail || resp.statusText);
                }

                const data = await resp.json();
                context.updateElevationOptions(data);
                // For elevation-selectable products (L2), updateElevationOptions can
                // change the elevation <select> from '' (auto) to a resolved default
                // the moment the first response arrives. The warm poll re-derives its
                // context key from the live DOM value on every tick and bails out if it
                // no longer matches the key captured above -- re-sync it now so the
                // resolved elevation doesn't look like an unrelated context switch.
                context.setScrubContextKey(context.currentScrubContextKey(product));
                const frames = context.normalizeScrubFrames(data.frames, site, product);
                context.setScrubFrames(frames);

                if (!isCurrentScrubLoadSeq(loadSeq) || !isTypeEnabled('radar')) return;
                if (!frames.length) {
                    context.setArchiveProgress(false);
                    context.setArchiveScrubber(true);
                    context.setScrubberControlsEnabled(false);
                    context.updateRtmaScrubberUi();
                    context.setRtmaScrubberStatus('No radar frames found for selected site/product/window.');
                    context.setRadarStatus(`No radar animation frames for ${site} ${product}.`);
                    context.setGlobalStatus(`No radar frames found for ${site} ${product} (${maxHours}h window).`);
                    context.startScrubWarmPoll(site, product);
                    return;
                }

                context.setArchiveProgress(false);
                context.setScrubberControlsEnabled(true);
                const motionLabel = stormMotionLabel(data);
                context.setRtmaScrubberStatus(`${frames.length} radar frames loaded (${site} ${product}, ${maxHours}h window)${motionLabel}.`);
                context.setRadarStatus(`${site} ${product} radar animation loaded${motionLabel}.`);
                context.showAutoUpdateRow(true);
                await context.renderScrubFrame(frames.length - 1);
                context.startScrubWarmPoll(site, product);
            } catch (err) {
                if (!isCurrentScrubLoadSeq(loadSeq) || !isTypeEnabled('radar')) return;
                context.setArchiveProgress(false);
                context.setScrubberControlsEnabled(false);
                context.setRtmaScrubberStatus(`Error: ${err.message}`);
                context.setRadarStatus(`Unable to load ${site} ${product} radar animation.`);
                context.setGlobalStatus(`Radar scrubber load error: ${err.message}`);
            }
        }

        return Object.freeze({
            canApplyResponse,
            loadLiveLatest,
            loadScrubberFrames,
        });
    }

    window.NCHRadarEngine = Object.freeze({
        createRadarEngine,
    });
}());
