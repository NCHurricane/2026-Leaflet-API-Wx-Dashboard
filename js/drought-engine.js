(function () {
    'use strict';

    const byId = (id) => document.getElementById(id);

    const DROUGHT_COLORS = { 0: '#ffff00', 1: '#fcd37f', 2: '#ffaa00', 3: '#e60000', 4: '#730000' };
    const DROUGHT_LABELS = {
        0: 'D0 — Abnormally Dry',
        1: 'D1 — Moderate Drought',
        2: 'D2 — Severe Drought',
        3: 'D3 — Extreme Drought',
        4: 'D4 — Exceptional Drought',
    };

    function createDroughtEngine(context) {
        async function fetchStateStats(date, stateCode) {
            if (!date || !stateCode) return null;
            const cache = context.getDroughtStateStatsCache();
            const cacheKey = `${stateCode}|${date}`;
            if (cache.has(cacheKey)) return cache.get(cacheKey);
            const resp = await fetch(
                context.apiUrl(`/api/data/drought/state-stats?date=${encodeURIComponent(date)}&state=${encodeURIComponent(stateCode)}`)
            );
            if (!resp.ok) throw new Error(`state stats ${resp.status}`);
            const data = await resp.json();
            cache.set(cacheKey, data);
            return data;
        }

        async function loadDroughtDates() {
            const statusEl = byId('weather-drought-date-status');
            let droughtDates = context.getDroughtDates();
            if (droughtDates.length) {
                context.renderDateButtons();
                return droughtDates;
            }

            try {
                const resp = await fetch(context.apiUrl('/api/data/drought/dates'));
                if (resp.ok) {
                    const data = await resp.json();
                    droughtDates = data.dates || [];
                    context.setDroughtDates(droughtDates);
                    context.renderDateButtons();
                }
            } catch (_) { /* ignore */ }

            if (!droughtDates.length && statusEl) {
                statusEl.textContent = 'No dates available.';
            }
            return droughtDates;
        }

        async function loadDroughtLayer() {
            const statusEl = byId('weather-drought-date-status');

            await loadDroughtDates();

            const date = context.getActiveDroughtDate() || (context.getDroughtDates()[0] ?? null);
            if (!date) {
                if (statusEl) statusEl.textContent = 'No dates available.';
                return;
            }

            if (statusEl) statusEl.textContent = 'Loading…';

            try {
                const resp = await fetch(
                    context.apiUrl(`/api/data/drought?date=${encodeURIComponent(date)}`)
                );
                if (!resp.ok) {
                    if (statusEl) statusEl.textContent = `Error ${resp.status}`;
                    return;
                }
                const geojson = await resp.json();
                const enabledCats = context.activeDroughtCategories();
                const opacity = parseFloat(byId('weather-opacity-drought')?.value ?? 0.75);

                const oldLayer = context.getDroughtLayer();
                if (oldLayer && context.map.hasLayer(oldLayer)) context.map.removeLayer(oldLayer);

                const newLayer = context.leaflet.geoJSON(geojson, {
                    filter: (feature) => enabledCats.includes(Number(feature.properties?.DM)),
                    style: (feature) => {
                        const dm = Number(feature.properties?.DM);
                        return {
                            fillColor: DROUGHT_COLORS[dm] ?? '#cccccc',
                            fillOpacity: opacity,
                            color: DROUGHT_COLORS[dm] ?? '#cccccc',
                            weight: 0.5,
                            opacity: 0.8,
                        };
                    },
                    onEachFeature: (feature, layer) => {
                        const dm = Number(feature.properties?.DM);
                        layer.bindTooltip(
                            `<strong>${DROUGHT_LABELS[dm] ?? `DM ${dm}`}</strong>`,
                            { sticky: true, className: 'wx-tooltip' },
                        );
                    },
                }).addTo(context.map);
                context.setDroughtLayer(newLayer);

                const stateCode = context.activeDroughtRegionState();
                let stateStats = null;
                if (stateCode) {
                    try { stateStats = await fetchStateStats(date, stateCode); }
                    catch (err) { console.warn('[drought] state stats unavailable', err); }
                }

                context.setLastDroughtState(stateCode, stateStats);
                context.buildDroughtLegend(enabledCats, stateStats, stateCode);

                const tsMs = context.resolveTimestampMs(date + 'T12:00:00Z');
                context.setViewerTimestamp(tsMs);
                context.setReliability('drought', 'USDM Drought', 'USDM/NDMC', tsMs);
                context.setTimestampSource('drought', 'usdm_valid_date', tsMs);
                if (statusEl) statusEl.textContent = `Valid: ${date}`;
            } catch (err) {
                if (statusEl) statusEl.textContent = 'Load failed.';
                console.error('[drought] load failed', err);
            }
        }

        function applyDroughtFilter() {
            const layer = context.getDroughtLayer();
            if (!layer) { loadDroughtLayer(); return; }
            const enabledCats = context.activeDroughtCategories();
            const opacity = context.getDroughtOpacity();
            layer.eachLayer((l) => {
                const dm = Number(l.feature?.properties?.DM);
                if (enabledCats.includes(dm)) {
                    l.setStyle({ fillOpacity: opacity, opacity: 0.8 });
                    if (!context.map.hasLayer(layer)) layer.addTo(context.map);
                } else {
                    l.setStyle({ fillOpacity: 0, opacity: 0, weight: 0 });
                }
            });
            const { code, stats } = context.getLastDroughtState();
            context.buildDroughtLegend(enabledCats, stats, code);
        }

        return Object.freeze({ applyDroughtFilter, loadDroughtDates, loadDroughtLayer });
    }

    window.NCHDroughtEngine = Object.freeze({ createDroughtEngine });
}());
