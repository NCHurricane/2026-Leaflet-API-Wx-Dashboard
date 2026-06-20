(function () {
    'use strict';

    const byId = (id) => document.getElementById(id);

    // Mirrors config/wpc_config.py ERO_COLORS / ERO_CATEGORY_LABEL.
    const ERO_COLORS = { MRGL: '#00FF00', SLGT: '#FFFF00', MDT: '#EE2C2C', HIGH: '#FF00FF' };
    const ERO_LABELS = {
        MRGL: 'Marginal (≥5%)',
        SLGT: 'Slight (≥15%)',
        MDT: 'Moderate (≥40%)',
        HIGH: 'High (≥70%)',
    };
    const ERO_ORDER = ['MRGL', 'SLGT', 'MDT', 'HIGH'];

    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function wpcForecastDetailFeature(feature, geojson, group, day) {
        if (group === 'mpd') return feature;
        const properties = feature?.properties || {};
        const productLabel = geojson?.product_label || 'WPC Forecast';
        const label = properties.label || properties.category || 'Forecast Area';
        const detailByGroup = {
            ero: {
                event: productLabel,
                description: properties.discussion_text || '',
                severity: 'Excessive Rainfall Outlook',
                metricLabel: '',
                metricValue: '',
                color: '#38BDF8',
            },
            winter: {
                event: `${productLabel} — ${label}`,
                description: properties.discussion_text || '',
                severity: 'Winter Weather Probability',
                metricLabel: 'Probability',
                metricValue: label,
            },
        };
        const detail = detailByGroup[group];
        if (!detail) return null;
        return {
            ...feature,
            properties: {
                ...properties,
                event: detail.event,
                headline: detail.event,
                description: detail.description,
                color: detail.color || properties.color,
                sent: geojson?._updated || '',
                source_url: properties.discussion_url || '',
                senderName: 'NWS Weather Prediction Center',
                severity: detail.severity,
                certainty: 'Forecast',
                wpc_forecast: true,
                wpc_group: group,
                wpc_day: day,
                wpc_product: productLabel,
                wpc_metric_label: detail.metricLabel,
                wpc_metric_value: detail.metricValue,
            },
        };
    }

    function createWpcEngine(context) {
        async function loadWpcCatalog() {
            try {
                const resp = await fetch(context.apiUrl('/api/data/wpc/catalog'));
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                context.updateWpcCatalog(await resp.json());
            } catch (err) {
                console.error('[wpc] catalog load failed', err);
            }
        }

        async function loadWpcLayer() {
            const statusEl = byId('weather-wpc-status');
            const day = context.activeWpcDay();
            const group = context.activeWpcGroup();
            const product = context.activeWpcProduct();
            const selectionKey = `${group}:${day}:${product}`;
            const requestSeq = context.nextWpcRequestSeq();
            context.closeWpcDetail?.();
            if (statusEl) statusEl.textContent = 'Loading…';
            context.setMapEmptyMessage(null);

            try {
                const params = new URLSearchParams({ group, day: String(day) });
                if (product) params.set('product', product);
                const resp = await fetch(context.apiUrl(`/api/data/wpc?${params}`));
                if (!resp.ok) {
                    if (statusEl) statusEl.textContent = `Error ${resp.status}`;
                    context.setMapEmptyMessage(null);
                    return;
                }
                const geojson = await resp.json();

                // Latest-wins: ignore a stale response after a newer day select.
                if (requestSeq !== context.getWpcRequestSeq()
                    || !context.isTypeEnabled('wpc')
                    || selectionKey !== `${context.activeWpcGroup()}:${context.activeWpcDay()}:${context.activeWpcProduct()}`) {
                    return;
                }

                const opacity = context.getWpcOpacity();
                const oldLayer = context.getWpcLayer();
                if (oldLayer && context.map.hasLayer(oldLayer)) context.map.removeLayer(oldLayer);

                if (geojson.image_url) {
                    const bounds = geojson.bounds;
                    if (!geojson.image_url || !bounds) {
                        context.setWpcLayer(null);
                        context.setLegend(null);
                        const emptyMessage = `${geojson.product_label || 'WPC surface product'} is temporarily unavailable from WPC.`;
                        context.setMapEmptyMessage(emptyMessage);
                        if (statusEl) statusEl.textContent = emptyMessage;
                        return;
                    }
                    const leafletBounds = [
                        [Number(bounds.south), Number(bounds.west)],
                        [Number(bounds.north), Number(bounds.east)],
                    ];
                    const newLayer = context.leaflet.imageOverlay(
                        context.apiUrl(geojson.image_url),
                        leafletBounds,
                        { opacity, interactive: false, pane: 'overlayPane' },
                    ).addTo(context.map);
                    context.setWpcLayer(newLayer);
                    context.setLegend(null);
                    context.setMapEmptyMessage(null);
                    const updated = geojson._updated;
                    if (updated) {
                        const tsMs = context.resolveTimestampMs(updated);
                        context.setViewerTimestamp(tsMs);
                        context.setReliability('wpc', geojson.product_label || 'WPC Surface Forecast', 'NOAA/WPC', tsMs);
                        context.setTimestampSource('wpc', 'wpc_updated', tsMs);
                    }
                    if (statusEl) {
                        const cacheNote = geojson.source_available === false
                            ? ' — showing cached data; WPC source is temporarily unavailable.'
                            : (geojson.stale ? ' — cached data may be stale.' : '');
                        statusEl.textContent = `${geojson.product_label || 'WPC Surface Forecast'} — transparent overlay.${cacheNote}`;
                    }
                    return;
                }

                const features = geojson.features || [];
                if (!features.length) {
                    context.setWpcLayer(null);
                    context.buildWpcLegend({
                        group,
                        day,
                        label: geojson.product_label,
                        features: [],
                    });
                    const emptyMessage = geojson.unavailable
                        ? `${geojson.product_label || 'WPC product'} is temporarily unavailable from WPC.`
                        : (
                            geojson.empty_message
                            || `No ${geojson.product_label || group.toUpperCase()} area issued.`
                        );
                    context.setMapEmptyMessage(emptyMessage);
                    if (statusEl) {
                        const cacheNote = geojson.source_available === false && !geojson.unavailable
                            ? ' Showing the last cached WPC result.'
                            : '';
                        statusEl.textContent = emptyMessage + cacheNote;
                    }
                    return;
                }

                context.setMapEmptyMessage(null);
                const detailFeatures = features
                    .map((feature) => wpcForecastDetailFeature(feature, geojson, group, day))
                    .filter(Boolean);
                const detailFeatureById = new Map(
                    detailFeatures.map((feature) => [feature.id, feature]),
                );
                const eroDetailFeature = group === 'ero' ? detailFeatures[0] : null;
                const newLayer = context.leaflet.geoJSON(geojson, {
                    style: (feature) => {
                        const color = feature.properties?.color || '#cccccc';
                        return {
                            fillColor: color,
                            fillOpacity: opacity,
                            color,
                            weight: group === 'mpd' ? 2 : 0.8,
                            opacity: 0.9,
                        };
                    },
                    onEachFeature: (feature, layer) => {
                        const label = feature.properties?.label
                            || feature.properties?.category || 'Risk';
                        layer.bindTooltip(
                            `<strong>${escapeHtml(label)}</strong>`,
                            { sticky: true, className: 'wx-tooltip' },
                        );
                        if (group === 'mpd') {
                            layer.on('click', (event) => {
                                context.openWpcDetail?.(event?.latlng, feature, [feature]);
                            });
                        } else if (group === 'ero' && eroDetailFeature) {
                            layer.on('click', (event) => {
                                context.openWpcDetail?.(event?.latlng, eroDetailFeature, [eroDetailFeature]);
                            });
                        } else if (group === 'winter') {
                            layer.on('click', (event) => {
                                const detailFeature = detailFeatureById.get(feature.id);
                                if (detailFeature) {
                                    context.openWpcDetail?.(event?.latlng, detailFeature, detailFeatures);
                                }
                            });
                        }
                    },
                }).addTo(context.map);
                context.setWpcLayer(newLayer);

                context.buildWpcLegend({
                    group,
                    day,
                    label: geojson.product_label,
                    features,
                });

                const updated = geojson._updated;
                if (updated) {
                    const tsMs = context.resolveTimestampMs(updated);
                    context.setViewerTimestamp(tsMs);
                    context.setReliability(
                        'wpc',
                        geojson.product_label || 'WPC Forecast',
                        'NOAA/WPC',
                        tsMs,
                    );
                    context.setTimestampSource('wpc', 'wpc_updated', tsMs);
                }
                if (statusEl) {
                    const cacheNote = geojson.source_available === false
                        ? ' — showing cached data; WPC source is temporarily unavailable.'
                        : (geojson.stale ? ' — cached data may be stale.' : '');
                    statusEl.textContent = (
                        `${geojson.product_label || `Day ${day}`} — ${features.length} `
                        + `${group === 'mpd' ? 'active discussion(s)' : 'contour(s)'}.`
                        + cacheNote
                    );
                }
            } catch (err) {
                if (statusEl) statusEl.textContent = 'Load failed.';
                context.setMapEmptyMessage(null);
                console.error('[wpc] load failed', err);
            }
        }

        return Object.freeze({
            loadWpcCatalog,
            loadWpcLayer,
            ERO_COLORS,
            ERO_LABELS,
            ERO_ORDER,
        });
    }

    window.NCHWpcEngine = Object.freeze({ createWpcEngine });
}());
