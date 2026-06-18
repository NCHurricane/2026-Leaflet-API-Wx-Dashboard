(function () {
    'use strict';

    function createTropicalEngine(context) {
        const layerToggles = {
            cone: true,
            forecast_track: true,
            forecast_points: true,
            watches_warnings: false,
            best_track: false,
            wind_radii: false,
            initial_wind_extent: false,
            storm_surge: false,
            peak_surge: false,
        };
        let activeLayer = null;

        function getGisGeoJson(data, layerId) {
            const geojson = data?.gis_layers?.[layerId]?.geojson;
            if (!geojson || geojson.type !== 'FeatureCollection' || !Array.isArray(geojson.features)) {
                return null;
            }
            return geojson;
        }

        function clearLayer() {
            if (activeLayer && context.map.hasLayer(activeLayer)) {
                context.map.removeLayer(activeLayer);
            }
            activeLayer = null;
        }

        function setLayerVisible(visible) {
            if (!activeLayer) return;
            if (visible && !context.map.hasLayer(activeLayer)) context.map.addLayer(activeLayer);
            if (!visible && context.map.hasLayer(activeLayer)) context.map.removeLayer(activeLayer);
        }

        function setLayerToggles(values, syncKeys = Object.keys(values || {})) {
            Object.entries(values || {}).forEach(([key, value]) => {
                if (key in layerToggles) layerToggles[key] = !!value;
            });
            context.syncLayerPills(syncKeys, layerToggles);
        }

        function renderGisLayers(data, layer) {
            const leaflet = context.leaflet;
            const addGeoJson = (layerId, options, toggleId = layerId) => {
                const geojson = getGisGeoJson(data, layerId);
                if (!geojson || !layerToggles[toggleId]) return null;
                return leaflet.geoJSON(geojson, options).addTo(layer);
            };

            addGeoJson('cone', {
                style: {
                    color: '#f8fafc', weight: 1.4, opacity: 0.9,
                    fillColor: '#facc15', fillOpacity: 0.16, dashArray: '4 4',
                },
            });
            addGeoJson('best_track_line', {
                style: (feature) => ({
                    color: context.categoryColor(context.categoryKey(feature?.properties || {})),
                    weight: 3,
                    opacity: 0.9,
                }),
            }, 'best_track');
            addGeoJson('best_track_points', {
                pointToLayer: (feature, latlng) => leaflet.circleMarker(latlng, {
                    radius: 4,
                    weight: 1,
                    color: '#020617',
                    fillColor: context.categoryColor(context.categoryKey(feature?.properties || {})),
                    fillOpacity: 0.95,
                }),
                onEachFeature: (feature, featureLayer) => {
                    const properties = feature?.properties || {};
                    const windKt = Number(properties.INTENSITY);
                    featureLayer.bindTooltip(
                        `${context.escapeHtml(context.windClass(windKt))} ${Number.isFinite(windKt) ? windKt : '--'} kt`,
                    );
                },
            }, 'best_track');
            addGeoJson('watches_warnings', {
                style: (feature) => {
                    const code = String(feature?.properties?.TCWW || '').toUpperCase();
                    const event = context.watchWarningEvent(code);
                    return {
                        color: (event && context.alertColors[event]) || context.alertDefault,
                        weight: 5,
                        opacity: 0.95,
                        lineCap: 'butt',
                    };
                },
                onEachFeature: (feature, featureLayer) => {
                    const code = String(feature?.properties?.TCWW || '').toUpperCase();
                    featureLayer.bindTooltip(
                        context.escapeHtml(context.watchWarningEvent(code) || code || 'Watch / Warning'),
                    );
                },
            });

            const forecastTrack = addGeoJson('forecast_track', {
                style: { color: '#fde68a', weight: 3, opacity: 0.95 },
            });
            forecastTrack?.on('click', () => context.openProductDetail('TCP'));

            addGeoJson('forecast_points', {
                pointToLayer: (feature, latlng) => (
                    leaflet.marker(latlng, { icon: context.categoryIcon(feature?.properties || {}) })
                ),
                onEachFeature: (feature, marker) => {
                    const properties = feature?.properties || {};
                    const label = properties.DATELBL || properties.FLDATELBL
                        || properties.VALIDTIME || 'Forecast point';
                    const wind = properties.MAXWIND ? `${properties.MAXWIND} kt` : '--';
                    marker.bindTooltip(
                        `${context.escapeHtml(label)}<br>${context.escapeHtml(context.pointCategory(properties))} ${context.escapeHtml(wind)}`,
                    );
                    marker.on('click', () => context.openProductDetail('TCP'));
                },
            });
            addGeoJson('wind_radii', {
                style: (feature) => {
                    const colors = { 34: '#1c54ff', 50: '#6cc343', 64: '#ffc309' };
                    const color = colors[Number(feature?.properties?.RADII)] || '#aaaaaa';
                    return {
                        color, weight: 1.5, opacity: 0.8,
                        fillColor: color, fillOpacity: 0.25,
                    };
                },
                onEachFeature: (feature, featureLayer) => {
                    const properties = feature?.properties || {};
                    const radii = properties.RADII ? `${properties.RADII} kt` : '--';
                    const tau = properties.TAU ? `τ${properties.TAU}` : '';
                    featureLayer.bindTooltip(context.escapeHtml(`Wind radii ${radii} ${tau}`.trim()));
                },
            });
            addGeoJson('initial_wind_extent', {
                style: (feature) => {
                    const color = feature?.properties?.color || '#9ca3af';
                    return {
                        color, weight: 1.5, opacity: 0.8,
                        fillColor: color, fillOpacity: 0.18, dashArray: '4 3',
                    };
                },
                onEachFeature: (feature, featureLayer) => {
                    const properties = feature?.properties || {};
                    featureLayer.bindTooltip(
                        context.escapeHtml(properties.label || `${properties.windField || ''} kt wind extent`.trim()),
                    );
                },
            });
            addGeoJson('storm_surge', {
                style: {
                    color: context.alertColors['Storm Surge Warning'] || '#e60000',
                    weight: 2,
                    opacity: 0.8,
                    fillColor: context.alertColors['Storm Surge Warning'] || '#e60000',
                    fillOpacity: 0.2,
                },
                onEachFeature: (feature, featureLayer) => {
                    featureLayer.bindTooltip(
                        context.escapeHtml(feature?.properties?.name || 'Storm Surge Watch/Warning'),
                    );
                },
            });
            addGeoJson('peak_surge', {
                filter: (feature) => feature?.properties?.feature_type !== 'breakpoint',
                style: (feature) => {
                    const color = feature?.properties?.color || '#9ca3af';
                    if ((feature?.properties?.feature_type || 'polygon') === 'linestring') {
                        return { color, weight: 4, opacity: 0.85, fillOpacity: 0 };
                    }
                    return {
                        color, weight: 1.5, opacity: 0.9,
                        fillColor: color, fillOpacity: 0.35,
                    };
                },
                onEachFeature: (feature, featureLayer) => {
                    const properties = feature?.properties || {};
                    const label = (properties.name || '').replace(/\.\.\./g, ':');
                    const range = properties.peak_surge_range ? ` (${properties.peak_surge_range})` : '';
                    featureLayer.bindTooltip(context.escapeHtml(`${label}${range}`.trim()));
                },
            });
        }

        function renderLayer(data, options = {}) {
            clearLayer();
            const leaflet = context.leaflet;
            const fitBounds = options.fitBounds !== false;
            const track = Array.isArray(data?.track) ? data.track : [];
            const location = data?.advisory?.location;
            const layer = leaflet.layerGroup();
            renderGisLayers(data, layer);

            const hasGisTrack = !!getGisGeoJson(data, 'forecast_track');
            const hasBestTrackLine = !!getGisGeoJson(data, 'best_track_line')
                && layerToggles.best_track;
            const hasGisGeometry = hasGisTrack || hasBestTrackLine
                || !!getGisGeoJson(data, 'cone')
                || !!getGisGeoJson(data, 'forecast_points');

            if (!hasGisTrack && !hasBestTrackLine && track.length >= 2) {
                leaflet.polyline(track.map((point) => [point.lat, point.lon]), {
                    color: '#f8fafc', weight: 2.5, opacity: 0.95, dashArray: '8 5',
                }).addTo(layer);
                track.forEach((point) => {
                    leaflet.circleMarker([point.lat, point.lon], {
                        radius: point.hour === 'INIT' ? 7 : 5,
                        color: '#020617',
                        weight: 1.5,
                        fillColor: context.pointColor(point.windKt),
                        fillOpacity: 0.95,
                    })
                        .bindTooltip(
                            `${context.escapeHtml(point.hour)} ${context.escapeHtml(point.time)}<br>`
                            + `${context.escapeHtml(context.windClass(point.windKt))} ${context.escapeHtml(point.windKt)} kt`,
                        )
                        .on('click', () => context.openProductDetail('TCM'))
                        .addTo(layer);
                });
            } else if (!hasGisGeometry && location?.lat != null && location?.lon != null) {
                leaflet.circleMarker([location.lat, location.lon], {
                    radius: 8, color: '#020617', weight: 1.8,
                    fillColor: '#f59e0b', fillOpacity: 0.95,
                })
                    .bindTooltip(context.escapeHtml(data?.stormId || 'Tropical system'))
                    .on('click', () => context.openProductDetail('TCP'))
                    .addTo(layer);
            }

            activeLayer = layer;
            if (!layer.getLayers().length) return;
            layer.addTo(context.map);
            const bounds = layer.getBounds?.();
            if (fitBounds && bounds?.isValid?.()) {
                context.map.fitBounds(bounds.pad(0.75), {
                    paddingTopLeft: [0, 0],
                    paddingBottomRight: [0, context.regionFitBottomPaddingPx],
                });
            }
        }

        function refreshLayer() {
            const storm = context.getActiveStorm();
            if (storm) renderLayer(storm, { fitBounds: false });
        }

        function handleLayerToggle(layerId, checked) {
            if (!(layerId in layerToggles)) return;
            layerToggles[layerId] = !!checked;
            context.renderLayerLegend(layerId, !!checked);
            refreshLayer();
        }

        async function loadArchiveCatalog() {
            const cachedCatalog = context.getArchiveCatalog();
            if (cachedCatalog) {
                context.renderArchiveCatalog(cachedCatalog);
                return;
            }

            context.setArchiveStatus('Loading archive catalog…');
            try {
                const resp = await context.fetchFn(
                    context.apiUrl('/api/tropical/archive/catalog'),
                    { cache: 'no-store' },
                );
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

                const catalog = await resp.json();
                context.setArchiveCatalog(catalog);
                context.renderArchiveCatalog(catalog);
            } catch (err) {
                console.error('[tropical-archive] Catalog load error:', err);
                context.setArchiveStatus(`Archive catalog error: ${err.message}`);
            }
        }

        async function loadArchiveAdvisory(atcfId, step, options = {}) {
            if (!atcfId || !step) return;

            const requestSeq = context.nextRequestSeq();
            context.setArchiveStatus(`Loading advisory ${step}…`);
            try {
                const url = `/api/tropical/archive/storm/${encodeURIComponent(atcfId)}/advisory/${encodeURIComponent(step)}`;
                const resp = await context.fetchFn(context.apiUrl(url), { cache: 'no-store' });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

                const advisory = await resp.json();
                if (!context.canApplyResponse(requestSeq)) return;

                const base = context.getArchiveStormBase() || {};
                const merged = {
                    ...advisory,
                    storm: base.storm,
                    gis_layers: {
                        ...(advisory.gis_layers || {}),
                        best_track_line: base.gis_layers?.best_track_line,
                        best_track_points: base.gis_layers?.best_track_points,
                    },
                };
                context.renderArchiveAdvisory(merged, advisory, options);
                context.updateArchiveAdvisoryMetadata(advisory, step, atcfId);
            } catch (err) {
                if (!context.isCurrentRequest(requestSeq)) return;
                console.error('[tropical-archive] Advisory load error:', err);
                context.setArchiveStatus(`Advisory error: ${err.message}`);
            }
        }

        async function loadArchiveStormDetail(atcfId) {
            if (!atcfId) return;

            const requestSeq = context.nextRequestSeq();
            context.setArchiveStatus('Loading best track…');
            try {
                const resp = await context.fetchFn(
                    context.apiUrl(`/api/tropical/archive/storm/${encodeURIComponent(atcfId)}`),
                    { cache: 'no-store' },
                );
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

                const data = await resp.json();
                if (!context.canApplyResponse(requestSeq)) return;

                context.prepareArchiveStorm(data, atcfId);
                if (data.hasAdvisories && Array.isArray(data.advisories) && data.advisories.length) {
                    context.prepareArchiveAdvisoryMode(data.advisories);
                    await loadArchiveAdvisory(atcfId, data.advisories[0], {
                        fit: true,
                        initial: true,
                    });
                    return;
                }

                context.prepareArchiveBestTrackMode();
                context.renderInitialArchiveFix();
                context.updateArchiveStormMetadata(data);
            } catch (err) {
                if (!context.isCurrentRequest(requestSeq)) return;
                console.error('[tropical-archive] Detail load error:', err);
                context.setArchiveStatus(`Archive error: ${err.message}`);
            }
        }

        async function loadStormDetail(stormId, options = {}) {
            if (!stormId) {
                context.clearLiveStormDetail();
                return;
            }

            const requestSeq = context.nextRequestSeq();
            context.setStatus('Loading advisory products...');

            try {
                const resp = await context.fetchFn(
                    context.apiUrl(`/api/tropical/storm/${encodeURIComponent(stormId)}`),
                    { cache: 'no-store' },
                );
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

                const data = await resp.json();
                if (!context.canApplyResponse(requestSeq)) return;

                context.setActiveStorm(data);
                context.resetLiveArchiveState();
                context.renderLiveStormDetail(data, options);
                context.setStatus(context.liveStormLabel(data));
                context.updateLiveStormMetadata(data);
            } catch (err) {
                if (!context.isCurrentRequest(requestSeq)) return;
                console.error('[tropical] Detail load error:', err);
                context.setStatus(`Tropical advisory error: ${err.message}`);
            }
        }

        async function loadStorms(force = false) {
            if (!context.isTypeEnabled('tropical')) return;

            const requestSeq = context.nextRequestSeq();
            const basin = context.getActiveBasin();
            context.setStatus('Loading active tropical systems...');
            context.renderOutlookLegend();

            try {
                const params = new URLSearchParams({ basin, _ts: String(Date.now()) });
                if (force) params.set('force', 'true');

                const resp = await context.fetchFn(
                    context.apiUrl(`/api/tropical/storms?${params.toString()}`),
                    { cache: 'no-store' },
                );
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

                const data = await resp.json();
                if (!context.canApplyResponse(requestSeq)) return;

                const storms = Array.isArray(data.storms) ? data.storms : [];
                context.setStorms(storms);
                context.renderStormList(storms);
                context.loadBasinFeeds();

                if (!storms.length) {
                    context.clearActiveStorm();
                    context.setHubMode('overview');
                    context.clearTropicalLayer();
                    context.renderSummary(null);
                    context.setStatus('No active NHC systems for the selected basin.');
                    return;
                }

                context.setStatus(`${storms.length} active system${storms.length === 1 ? '' : 's'} found.`);
            } catch (err) {
                if (!context.isCurrentRequest(requestSeq)) return;
                console.error('[tropical] Storm list error:', err);
                context.setStatus(`Tropical systems error: ${err.message}`);
            }
        }

        return Object.freeze({
            clearLayer,
            getGisGeoJson,
            getLayerToggles: () => ({ ...layerToggles }),
            handleLayerToggle,
            loadArchiveAdvisory,
            loadArchiveCatalog,
            loadArchiveStormDetail,
            loadStormDetail,
            loadStorms,
            refreshLayer,
            renderLayer,
            setLayerToggles,
            setLayerVisible,
        });
    }

    window.NCHTropicalEngine = Object.freeze({ createTropicalEngine });
}());
