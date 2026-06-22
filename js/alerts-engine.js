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
        const isLsrEnabled = requireContextFunction(context, 'isLsrEnabled');
        let lsrRequestSeq = 0;
        let _lsrCurrentFeatures = null;

        function canApplyLiveResponse() {
            return !isArchiveMode()
                && !hasRtmaScrubFrames()
                && isTypeEnabled('alerts')
                && getCheckedCategories().length > 0;
        }

        const LSR_CATEGORY_COLORS = {
            tornado: '#ef4444',
            hail: '#22c55e',
            wind: '#f59e0b',
            flood: '#1d4ed8',
            rain: '#38bdf8',
            winter: '#a78bfa',
            fire: '#f97316',
            heat: '#fbbf24',
            other: '#94a3b8',
        };

        const LSR_CATEGORY_FA_ICON = {
            tornado: 'fa-solid fa-tornado',
            hail: 'fa-solid fa-caret-up',
            wind: 'fa-solid fa-wind',
            flood: 'fa-solid fa-house-flood-water',
            rain: 'fa-solid fa-cloud-showers-water',
            winter: 'fa-solid fa-snowflake',
            fire: 'fa-solid fa-fire',
            heat: 'fa-solid fa-temperature-arrow-up',
        };

        function lsrCategory(eventText) {
            const event = String(eventText || '').toLowerCase();
            if (event.includes('torn') || event.includes('funnel') || event.includes('waterspout')) return 'tornado';
            if (event.includes('hail')) return 'hail';
            if (event.includes('wind') || event.includes('wnd') || event.includes('downburst')) return 'wind';
            // winter before flood/rain to catch "freezing rain", "ice storm" etc.
            if (event.includes('snow') || event.includes('blizzard') || event.includes('ice') || event.includes('sleet') || event.includes('freez') || event.includes('winter')) return 'winter';
            if (event.includes('flood')) return 'flood';
            if (event.includes('rain')) return 'rain';
            if (event.includes('fire') || event.includes('smoke') || event.includes('wildfire')) return 'fire';
            if (event.includes('heat')) return 'heat';
            return 'other';
        }

        function lsrColor(eventText) {
            return LSR_CATEGORY_COLORS[lsrCategory(eventText)];
        }

        function lsrSizeAtZoom(zoom) {
            const extra = Math.max(0, (zoom ?? 7) - 7);
            return Math.round(16 * Math.pow(1.1, extra));
        }

        function lsrMarker(feature, latlng, leaflet, zoom) {
            const cat = lsrCategory(feature?.properties?.event);
            const color = LSR_CATEGORY_COLORS[cat] || LSR_CATEGORY_COLORS.other;
            const faClass = LSR_CATEGORY_FA_ICON[cat];
            const size = lsrSizeAtZoom(zoom);
            if (faClass) {
                const half = Math.round(size / 2);
                return leaflet.marker(latlng, {
                    icon: leaflet.divIcon({
                        className: '',
                        html: `<i class="${faClass}" style="color:${color};font-size:${size}px;-webkit-text-stroke:0.5px #08111d;text-shadow:0 0 3px rgba(0,0,0,0.7);"></i>`,
                        iconSize: [size, size],
                        iconAnchor: [half, half],
                        popupAnchor: [0, -(half + 2)],
                    }),
                });
            }
            const radius = Math.round(6 * Math.pow(1.1, Math.max(0, (zoom ?? 7) - 7)));
            return leaflet.circleMarker(latlng, {
                radius,
                color: '#08111d',
                weight: 1.5,
                fillColor: color,
                fillOpacity: 0.95,
                opacity: 1,
            });
        }

        function lsrTooltip(feature) {
            const props = feature?.properties || {};
            const esc = context.escapeHtml;
            const event = esc(props.event || 'Local Storm Report');
            const mag = props.magnitude_label ? ` (${esc(props.magnitude_label)})` : '';
            const place = [props.location, props.state].filter(Boolean).map(esc).join(', ');
            const when = props.time
                ? esc(new Date(props.time).toLocaleString(undefined, {
                    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
                }))
                : '';
            const office = props.wfo_id ? esc(props.wfo_id) : '';
            const meta = [when, office].filter(Boolean).join(' · ');
            return `<strong>${event}${mag}</strong>${place ? `<br>${place}` : ''}${meta ? `<br>${meta}` : ''}`;
        }

        const LSR_CATEGORY_LABELS = {
            tornado: 'Tornado / Waterspout',
            hail: 'Hail',
            wind: 'Wind',
            flood: 'Flash Flood / Flood',
            rain: 'Heavy Rain',
            winter: 'Winter Weather',
            fire: 'Fire / Smoke',
            heat: 'Heat',
            other: 'Other',
        };

        function buildLsrLegendHtml(checkedCategories) {
            const rows = Object.entries(LSR_CATEGORY_LABELS)
                .filter(([cat]) => checkedCategories.has(cat))
                .map(([cat, label]) => {
                    const color = LSR_CATEGORY_COLORS[cat];
                    const faClass = LSR_CATEGORY_FA_ICON[cat];
                    if (faClass) {
                        return `<div class="legend-item"><i class="legend-swatch is-icon ${faClass}" style="color:${color};font-size:14px;text-align:center;"></i><span class="legend-text">${label}</span></div>`;
                    }
                    return `<div class="legend-item"><span class="legend-swatch" style="background:${color}"></span><span class="legend-text">${label}</span></div>`;
                })
                .join('');
            return `<h4 class="legend-title">Local Storm Reports</h4><div class="legend-flow">${rows}</div>`;
        }

        function buildLsrLayer(features, leaflet, zoom) {
            return leaflet.geoJSON(
                { type: 'FeatureCollection', features },
                {
                    pointToLayer: (feature, latlng) => lsrMarker(feature, latlng, leaflet, zoom),
                    onEachFeature: (feature, marker) => {
                        marker.bindPopup(lsrPopup(feature));
                        marker.bindTooltip(lsrTooltip(feature), {
                            sticky: true,
                            opacity: 0.9,
                            className: 'wx-alert-hover-tip',
                        });
                    },
                },
            );
        }

        function rerenderLsrAtZoom(zoom) {
            if (!_lsrCurrentFeatures) return;
            const { leaflet, swapLsrLayer } = context;
            if (!leaflet?.geoJSON || typeof swapLsrLayer !== 'function') return;
            swapLsrLayer(buildLsrLayer(_lsrCurrentFeatures, leaflet, zoom));
        }

        function lsrPopup(feature) {
            const props = feature?.properties || {};
            const escapeHtml = context.escapeHtml;
            const event = escapeHtml(props.event || 'Local Storm Report');
            const magnitude = props.magnitude_label
                ? ` (${escapeHtml(props.magnitude_label)})`
                : '';
            const place = [props.location, props.state].filter(Boolean).join(', ');
            const when = props.time
                ? `<br><em>Time:</em> ${escapeHtml(new Date(props.time).toLocaleString())}`
                : '';
            const where = place ? `<br><em>Location:</em> ${escapeHtml(place)}` : '';
            const office = props.wfo_id
                ? `<br><em>Office:</em> ${escapeHtml(props.wfo_id)}`
                : '';
            const remarks = props.remarks
                ? `<br><small>${escapeHtml(props.remarks)}</small>`
                : '';
            return `<strong>${event}${magnitude}</strong>${when}${where}${office}${remarks}`;
        }

        async function loadLocalStormReports(options = {}) {
            const {
                apiUrl,
                escapeHtml,
                fetchFn = fetch,
                getCheckedLsrCategories,
                getMapBounds,
                leaflet,
                setLsrCount,
                setStatus,
                swapLsrLayer,
            } = context;
            [
                apiUrl,
                escapeHtml,
                getCheckedLsrCategories,
                getMapBounds,
                setLsrCount,
                setStatus,
                swapLsrLayer,
            ].forEach((fn) => {
                if (typeof fn !== 'function') throw new Error('Alerts LSR context is incomplete.');
            });
            if (!leaflet?.geoJSON || !leaflet?.circleMarker) {
                throw new Error('Alerts LSR Leaflet context is incomplete.');
            }

            const checkedCategories = getCheckedLsrCategories();
            if (!isTypeEnabled('alerts') || !isLsrEnabled() || !checkedCategories.size) {
                lsrRequestSeq += 1;
                _lsrCurrentFeatures = null;
                swapLsrLayer(null);
                setLsrCount(0);
                context.setLsrLegend?.(null);
                return;
            }

            const requestSeq = ++lsrRequestSeq;
            const bounds = getMapBounds();
            const hours = context.getLsrHours?.() ?? 24;
            const params = new URLSearchParams({
                west: Number(bounds.west).toFixed(4),
                east: Number(bounds.east).toFixed(4),
                south: Number(bounds.south).toFixed(4),
                north: Number(bounds.north).toFixed(4),
                hours: String(hours),
            });
            if (!options.silentStatus) setStatus('Loading Local Storm Reports...');

            try {
                const resp = await fetchFn(apiUrl(`/api/data/alerts/lsr?${params.toString()}`), {
                    cache: 'no-store',
                });
                if (!resp.ok) {
                    const payload = await resp.json().catch(() => ({}));
                    throw new Error(payload.detail || `HTTP ${resp.status}`);
                }
                const data = await resp.json();
                if (
                    requestSeq !== lsrRequestSeq
                    || !isTypeEnabled('alerts')
                    || !isLsrEnabled()
                ) return;

                const allFeatures = Array.isArray(data.features) ? data.features : [];
                const features = allFeatures.filter(
                    (f) => checkedCategories.has(lsrCategory(f?.properties?.event))
                );
                _lsrCurrentFeatures = features;
                const zoom = context.getZoom?.() ?? 7;
                swapLsrLayer(buildLsrLayer(features, leaflet, zoom));
                setLsrCount(features.length);
                context.setLsrLegend?.(buildLsrLegendHtml(checkedCategories));
                if (!options.silentStatus) {
                    const stale = data._stale ? ' (cached)' : '';
                    setStatus(`${features.length} Local Storm Report(s) in view${stale}.`);
                }
            } catch (err) {
                if (requestSeq !== lsrRequestSeq) return;
                console.error('[alerts lsr] Load error:', err);
                if (!options.silentStatus) setStatus(`Local Storm Reports error: ${err.message}`);
            }
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
            loadLocalStormReports,
            refreshDisplayLayer,
            rerenderLsrAtZoom,
        });
    }

    window.NCHAlertsEngine = Object.freeze({
        createAlertsEngine,
    });
}());
