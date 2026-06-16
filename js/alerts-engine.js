(function () {
    'use strict';

    function requireContextFunction(context, name) {
        if (typeof context?.[name] !== 'function') {
            throw new Error(`Alerts engine context missing function: ${name}`);
        }
        return context[name];
    }

    function createAlertsEngine(context) {
        const isArchiveMode = requireContextFunction(context, 'isArchiveMode');
        const hasRtmaScrubFrames = requireContextFunction(context, 'hasRtmaScrubFrames');
        const isTypeEnabled = requireContextFunction(context, 'isTypeEnabled');
        const getCheckedCategories = requireContextFunction(context, 'getCheckedCategories');

        function canApplyLiveResponse() {
            return !isArchiveMode()
                && !hasRtmaScrubFrames()
                && isTypeEnabled('alerts')
                && getCheckedCategories().length > 0;
        }

        async function loadLiveAlerts(options = {}) {
            const {
                alertsRequestScopeFromRegion,
                alertsZoomBucket,
                buildAlertsLayer,
                buildAlertsLegend,
                buildAlertsUrl,
                fetchFn = fetch,
                filterAlertsByCategories,
                formatValidTimeLabel,
                isCurrentRequestSeq,
                nextRequestSeq,
                renderActiveWarningsPanel,
                resolveDataTimestampMs,
                setAlertBaseFeatures,
                setAlertFeatureStateEmpty,
                setAlertKnownIds,
                setAlertLastZoomBucket,
                setAlertRenderedFeatures,
                setAlertsCount,
                setLegend,
                setReliability,
                setStatus,
                setTimestampSource,
                setViewerTimestamp,
                shouldNotifyNewAlert,
                showNewAlertBanner,
                staleNoteForTimestamp,
                stripInactiveAlerts,
                swapAlertsLayer,
            } = context;

            [
                alertsRequestScopeFromRegion,
                alertsZoomBucket,
                buildAlertsLayer,
                buildAlertsLegend,
                buildAlertsUrl,
                filterAlertsByCategories,
                formatValidTimeLabel,
                isCurrentRequestSeq,
                nextRequestSeq,
                renderActiveWarningsPanel,
                resolveDataTimestampMs,
                setAlertBaseFeatures,
                setAlertFeatureStateEmpty,
                setAlertKnownIds,
                setAlertLastZoomBucket,
                setAlertRenderedFeatures,
                setAlertsCount,
                setLegend,
                setReliability,
                setStatus,
                setTimestampSource,
                setViewerTimestamp,
                shouldNotifyNewAlert,
                showNewAlertBanner,
                staleNoteForTimestamp,
                stripInactiveAlerts,
                swapAlertsLayer,
            ].forEach((fn) => {
                if (typeof fn !== 'function') {
                    throw new Error('Alerts engine context is incomplete.');
                }
            });

            const { silentStatus = false } = options;
            const requestSeq = nextRequestSeq();
            const checkedCategories = getCheckedCategories();
            if (!checkedCategories.length) {
                setAlertFeatureStateEmpty();
                setAlertsCount(0);
                setLegend(null);
                renderActiveWarningsPanel();
                return;
            }
            if (!silentStatus) setStatus('Loading alerts...');

            try {
                const scope = alertsRequestScopeFromRegion();
                const zoomBucket = alertsZoomBucket();
                const fullUrl = buildAlertsUrl(scope.stateCode, {
                    geometry_mode: 'full',
                    zoom_bucket: zoomBucket,
                    ...scope.extraParams,
                });
                const displayUrl = buildAlertsUrl(scope.stateCode, {
                    geometry_mode: 'display',
                    zoom_bucket: zoomBucket,
                    ...scope.extraParams,
                });

                const [fullResp, displayResp] = await Promise.all([
                    fetchFn(fullUrl, { cache: 'no-store' }),
                    fetchFn(displayUrl, { cache: 'no-store' }),
                ]);

                if (!fullResp.ok) throw new Error(`HTTP ${fullResp.status}`);
                const fullGeojson = await fullResp.json();

                let displayGeojson = fullGeojson;
                if (displayResp.ok) {
                    try {
                        displayGeojson = await displayResp.json();
                    } catch (_) {
                        displayGeojson = fullGeojson;
                    }
                }

                if (!isCurrentRequestSeq(requestSeq) || !canApplyLiveResponse()) return;

                const fullBaseFeatures = stripInactiveAlerts(fullGeojson.features);
                const displayBaseFeatures = stripInactiveAlerts(displayGeojson.features);
                const fullFeatures = filterAlertsByCategories(fullBaseFeatures, checkedCategories);
                const displayFeatures = filterAlertsByCategories(displayBaseFeatures, checkedCategories);

                const prevIds = context.getAlertKnownIds?.() || null;
                const newIdSet = new Set(fullFeatures.map((feat) => feat.id).filter(Boolean));
                setAlertKnownIds(newIdSet);

                if (prevIds !== null) {
                    fullFeatures.forEach((feat) => {
                        if (!feat.id || prevIds.has(feat.id)) return;
                        if (shouldNotifyNewAlert(feat)) showNewAlertBanner(feat);
                    });
                }

                setAlertLastZoomBucket(zoomBucket);
                setAlertBaseFeatures(fullBaseFeatures, displayBaseFeatures);
                setAlertRenderedFeatures(fullFeatures, displayFeatures);

                const nextLayer = buildAlertsLayer(displayFeatures);
                swapAlertsLayer(nextLayer);
                buildAlertsLegend(fullFeatures);
                setAlertsCount(fullFeatures.length);
                renderActiveWarningsPanel();

                const alertsTsMs = resolveDataTimestampMs(fullGeojson?._updated || displayGeojson?._updated);
                const alertsStaleNote = staleNoteForTimestamp(alertsTsMs);
                if (!silentStatus) setStatus(`Alerts valid ${formatValidTimeLabel(alertsTsMs)}.${alertsStaleNote}`);
                setViewerTimestamp(alertsTsMs);
                setReliability('alerts', 'Alerts', 'NWS, IEM', alertsTsMs);
                setTimestampSource('alerts', 'alerts_cache_updated', alertsTsMs);
            } catch (err) {
                if (!isCurrentRequestSeq(requestSeq)) return;
                console.error('[alerts] Load error:', err);
                if (!silentStatus) setStatus(`Alerts error: ${err.message}`);
            }
        }

        function applyInMemoryCategoryFilter() {
            const {
                buildAlertsLayer,
                buildAlertsLegend,
                filterAlertsByCategories,
                getAlertBaseFeatures,
                renderActiveWarningsPanel,
                setAlertFeatureStateEmpty,
                setAlertRenderedFeatures,
                setAlertsCount,
                setLegend,
                swapAlertsLayer,
            } = context;

            [
                buildAlertsLayer,
                buildAlertsLegend,
                filterAlertsByCategories,
                getAlertBaseFeatures,
                renderActiveWarningsPanel,
                setAlertFeatureStateEmpty,
                setAlertRenderedFeatures,
                setAlertsCount,
                setLegend,
                swapAlertsLayer,
            ].forEach((fn) => {
                if (typeof fn !== 'function') {
                    throw new Error('Alerts engine context is incomplete.');
                }
            });

            const checkedCategories = getCheckedCategories();
            if (!checkedCategories.length) {
                setAlertFeatureStateEmpty();
                setAlertsCount(0);
                setLegend(null);
                renderActiveWarningsPanel();
                return;
            }

            const { fullBaseFeatures, displayBaseFeatures } = getAlertBaseFeatures();
            const fullFeatures = filterAlertsByCategories(fullBaseFeatures, checkedCategories);
            const displayFeatures = filterAlertsByCategories(displayBaseFeatures, checkedCategories);

            setAlertRenderedFeatures(fullFeatures, displayFeatures);

            const nextLayer = buildAlertsLayer(displayFeatures);
            swapAlertsLayer(nextLayer);
            buildAlertsLegend(fullFeatures);
            setAlertsCount(fullFeatures.length);
            renderActiveWarningsPanel();
        }

        async function refreshDisplayLayer() {
            const {
                alertsRequestScopeFromRegion,
                alertsZoomBucket,
                buildAlertsLayer,
                buildAlertsLegend,
                buildAlertsUrl,
                fetchFn = fetch,
                filterAlertsByCategories,
                getAlertBaseFeatures,
                renderActiveWarningsPanel,
                setAlertBaseFeatures,
                setAlertRenderedFeatures,
                setAlertsCount,
                stripInactiveAlerts,
                swapAlertsLayer,
            } = context;

            [
                alertsRequestScopeFromRegion,
                alertsZoomBucket,
                buildAlertsLayer,
                buildAlertsLegend,
                buildAlertsUrl,
                filterAlertsByCategories,
                getAlertBaseFeatures,
                renderActiveWarningsPanel,
                setAlertBaseFeatures,
                setAlertRenderedFeatures,
                setAlertsCount,
                stripInactiveAlerts,
                swapAlertsLayer,
            ].forEach((fn) => {
                if (typeof fn !== 'function') {
                    throw new Error('Alerts engine context is incomplete.');
                }
            });

            const { fullBaseFeatures } = getAlertBaseFeatures();
            if (!fullBaseFeatures.length || !canApplyLiveResponse()) return;

            const checkedCategories = getCheckedCategories();
            if (!checkedCategories.length) return;

            const scope = alertsRequestScopeFromRegion();
            const zoomBucket = alertsZoomBucket();

            try {
                const displayUrl = buildAlertsUrl(scope.stateCode, {
                    geometry_mode: 'display',
                    zoom_bucket: zoomBucket,
                    ...scope.extraParams,
                });
                const resp = await fetchFn(displayUrl, { cache: 'no-store' });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const displayGeojson = await resp.json();

                if (!canApplyLiveResponse()) return;

                const displayBaseFeatures = stripInactiveAlerts(displayGeojson.features);
                const displayFeatures = filterAlertsByCategories(displayBaseFeatures, checkedCategories);
                const fullFeatures = filterAlertsByCategories(fullBaseFeatures, checkedCategories);

                setAlertBaseFeatures(fullBaseFeatures, displayBaseFeatures);
                setAlertRenderedFeatures(fullFeatures, displayFeatures);

                const nextLayer = buildAlertsLayer(displayFeatures);
                swapAlertsLayer(nextLayer);
                buildAlertsLegend(fullFeatures);
                renderActiveWarningsPanel();
                setAlertsCount(fullFeatures.length);
            } catch (err) {
                console.warn('[alerts] Display layer refresh failed:', err.message);
            }
        }

        function sliceAlertsIntoFrames(features, isoFrom, isoTo) {
            const stepMs = 60_000;
            const from = new Date(isoFrom);
            const to = new Date(isoTo);
            const sourceFeatures = Array.isArray(features) ? features : [];
            if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) || to <= from) {
                return [{ timestamp: isoFrom, features: sourceFeatures, type: 'FeatureCollection' }];
            }

            const parseTimestamp = (value) => {
                if (!value) return null;
                const parsedDate = new Date(value);
                if (!Number.isNaN(parsedDate.getTime())) return parsedDate;
                const raw = String(value);
                if (/^\d{12}$/.test(raw)) {
                    const iemDate = new Date(Date.UTC(
                        Number(raw.slice(0, 4)),
                        Number(raw.slice(4, 6)) - 1,
                        Number(raw.slice(6, 8)),
                        Number(raw.slice(8, 10)),
                        Number(raw.slice(10, 12))
                    ));
                    if (!Number.isNaN(iemDate.getTime())) return iemDate;
                }
                return null;
            };

            const parsedFeatures = sourceFeatures.map((feature) => {
                const onset = parseTimestamp(feature?.properties?.onset);
                const expires = parseTimestamp(feature?.properties?.expires);
                return {
                    feature,
                    onset: onset || from,
                    expires: expires || to,
                };
            });

            const cursor = new Date(from);
            cursor.setSeconds(0, 0);
            if (cursor < from) cursor.setTime(cursor.getTime() + stepMs);

            const frames = [];
            while (cursor <= to) {
                const frameStart = new Date(cursor);
                const frameEnd = new Date(cursor.getTime() + stepMs);
                const active = parsedFeatures
                    .filter((item) => item.onset < frameEnd && item.expires > frameStart)
                    .map((item) => item.feature);
                frames.push({
                    timestamp: frameStart.toISOString(),
                    features: active,
                    type: 'FeatureCollection',
                });
                cursor.setTime(cursor.getTime() + stepMs);
            }

            if (!frames.length) {
                return [{ timestamp: isoFrom, features: sourceFeatures, type: 'FeatureCollection' }];
            }
            return frames;
        }

        async function loadArchiveAlerts(dtFrom, dtTo) {
            const {
                apiUrl,
                fetchFn = fetch,
                getRegionValue,
                onArchiveFramesReady,
                setArchiveProgress,
                setStatus,
            } = context;

            [
                apiUrl,
                getRegionValue,
                onArchiveFramesReady,
                setArchiveProgress,
                setStatus,
            ].forEach((fn) => {
                if (typeof fn !== 'function') {
                    throw new Error('Alerts engine archive context is incomplete.');
                }
            });

            const state = getRegionValue();
            const stateParam = state && state !== 'CONUS' ? `&state=${encodeURIComponent(state)}` : '';
            const url = apiUrl(
                `/api/archive/alerts?date_from=${encodeURIComponent(dtFrom)}` +
                `&date_to=${encodeURIComponent(dtTo)}${stateParam}`
            );
            try {
                setArchiveProgress(true, 50, 'Fetching archived alerts...');
                const resp = await fetchFn(url);
                if (!resp.ok) {
                    const errorPayload = await resp.json().catch(() => ({}));
                    throw new Error(errorPayload.detail || resp.statusText);
                }
                const data = await resp.json();
                const frames = sliceAlertsIntoFrames(data.features, data.date_from, data.date_to);
                onArchiveFramesReady(frames);
            } catch (err) {
                setArchiveProgress(true, 0, `Error: ${err.message}`);
                setStatus(`Archive Alerts error: ${err.message}`);
            }
        }

        function alertStyle(feat) {
            const {
                alertColors,
                alertDefaultColor,
                alertPriority,
                getAlertsOpacity,
            } = context;

            if (!alertColors || !alertPriority || typeof getAlertsOpacity !== 'function') {
                throw new Error('Alerts engine style context is incomplete.');
            }

            const event = feat?.properties?.event || '';
            const color = alertColors[event] || alertDefaultColor;
            const priority = alertPriority[event] || 200;
            const zIndex = 400 - priority;
            const opacity = getAlertsOpacity();
            return {
                color,
                weight: 1.5,
                fillColor: color,
                fillOpacity: opacity * 0.5,
                opacity,
                zIndex,
            };
        }

        function buildAlertsLayer(displayFeatures) {
            const {
                alertPulseEvents,
                leaflet,
                makeThrottledHoverHandler,
                openAlertsPagerAt,
                setRegionAlertLocationState,
            } = context;

            [
                makeThrottledHoverHandler,
                openAlertsPagerAt,
                setRegionAlertLocationState,
            ].forEach((fn) => {
                if (typeof fn !== 'function') {
                    throw new Error('Alerts engine layer context is incomplete.');
                }
            });
            if (!leaflet?.geoJSON || !alertPulseEvents) {
                throw new Error('Alerts engine layer context is incomplete.');
            }

            return leaflet.geoJSON({ type: 'FeatureCollection', features: displayFeatures }, {
                style: alertStyle,
                onEachFeature: (feat, layer) => {
                    layer.on('click', (event) => {
                        if (context.isStormTrackDrawMode?.()) return;
                        if (event?.latlng) {
                            setRegionAlertLocationState();
                            openAlertsPagerAt(event.latlng);
                        }
                    });
                    layer.on('mousemove', (event) => {
                        layer.bringToFront();
                        makeThrottledHoverHandler(() => feat, () => layer)(event);
                    });
                    layer.on('mouseout', () => {
                        layer.bringToBack();
                        layer.closeTooltip();
                    });
                    if (alertPulseEvents.has(feat?.properties?.event || '')) {
                        layer.on('add', () => layer.getElement?.()?.classList.add('wx-alert-pulse'));
                    }
                },
            });
        }

        return Object.freeze({
            applyInMemoryCategoryFilter,
            alertStyle,
            buildAlertsLayer,
            canApplyLiveResponse,
            loadArchiveAlerts,
            loadLiveAlerts,
            refreshDisplayLayer,
            sliceAlertsIntoFrames,
        });
    }

    window.NCHAlertsEngine = Object.freeze({
        createAlertsEngine,
    });
}());
