(function () {
    'use strict';

    function createSurfaceEngine(context) {
        async function loadSurface(region, product) {
            if (!context.isTypeEnabled('current')) return;
            if (!context.canApplySurfaceResponse(region, product)) return;

            const requestSeq = context.nextRequestSeq();
            context.setStatus(`Loading surface ${product} for ${region}...`);

            try {
                const url = context.apiUrl(
                    `/api/data/surface?region=${encodeURIComponent(region)}&product=${encodeURIComponent(product)}`
                );
                const resp = await fetch(url);
                if (!resp.ok) {
                    const e = await resp.json().catch(() => ({}));
                    throw new Error(e.detail || resp.statusText);
                }
                const data = await resp.json();
                if (!context.isCurrentRequestSeq(requestSeq) || !context.canApplySurfaceResponse(region, product)) return;

                const stations = Array.isArray(data?.stations) ? data.stations : [];
                context.setSurfaceStations(stations);
                context.renderSurfaceMarkers(stations);
                context.buildSurfaceLegend(product, stations);

                const countEl = document.getElementById('weather-surface-count');
                if (countEl) countEl.textContent = `${stations.length} station(s)`;

                const tsMs = context.resolveTimestampMs(data?.timestamp);
                const staleNote = context.staleNoteForTimestamp(tsMs);
                const validLabel = context.formatValidTimeLabel(tsMs);
                context.setStatus(`Surface ${product} for ${region} valid ${validLabel}.${staleNote}`);
                context.setViewerTimestamp(tsMs);
                context.setReliability('surface', `Surface ${product}`, 'IEM', tsMs);
                context.setTimestampSource('surface', data?.timestamp_source || 'station_valid', tsMs);

                await context.ensureGradientStations(product, region, stations);
                const before = context.hasGradientCache(product, region);
                await context.primeSurfaceGradientCache(product, region);
                const after = context.hasGradientCache(product, region);
                if (!before && after && context.canApplySurfaceResponse(region, product) && context.activeSurfaceGradient()) {
                    context.renderSurfaceMarkers(context.getSurfaceStations());
                }
            } catch (err) {
                if (!context.isCurrentRequestSeq(requestSeq)) return;
                console.error('[surface] Load error:', err);
                context.setStatus(`Surface error: ${err.message}`);
            }
        }

        async function applyGradientChange() {
            if (!context.isTypeEnabled('current') || !context.getSurfaceStations().length) return;
            const product = context.activeSurfaceProduct();
            const region = context.getRegionValue() || 'CONUS';
            if (!product) return;
            if (context.activeSurfaceGradient()) {
                await context.ensureGradientStations(product, region);
                await context.primeSurfaceGradientCache(product, region);
            }
            context.renderSurfaceMarkers(context.getSurfaceStations());
        }

        async function loadArchive() {
            const region = context.getRegionValue() || 'NC';
            const product = context.activeSurfaceProduct() || 'temperature';
            context.setArchiveProduct(product);

            const rawFrom = context.getArchiveFromValue();
            const rawTo = context.getArchiveToValue() || rawFrom;
            const snappedFrom = context.snapToHour(rawFrom, 'floor');
            const snappedTo = context.snapToHour(rawTo, 'ceil');
            if (snappedFrom) context.setArchiveFromValue(snappedFrom);
            if (snappedTo) context.setArchiveToValue(snappedTo);

            const apiFrom = context.toArchiveApiDatetime(snappedFrom || rawFrom);
            const apiTo = context.toArchiveApiDatetime(snappedTo || rawTo);
            const url = context.apiUrl(
                `/api/archive/surface?region=${encodeURIComponent(region)}` +
                `&product=${encodeURIComponent(product)}` +
                `&date_from=${encodeURIComponent(apiFrom)}` +
                `&date_to=${encodeURIComponent(apiTo)}` +
                '&max_frames=24&source=iem&network=ASOS'
            );

            try {
                context.setArchiveProgress(true, 40, 'Fetching archived surface observations...');
                const resp = await fetch(url);
                if (!resp.ok) {
                    const e = await resp.json().catch(() => ({}));
                    throw new Error(e.detail || resp.statusText);
                }
                const data = await resp.json();
                context.onArchiveFramesReady(data.frames || []);
            } catch (err) {
                context.setArchiveProgress(true, 0, `Error: ${err.message}`);
                context.setStatus(`Archive Surface error: ${err.message}`);
            }
        }

        return Object.freeze({ applyGradientChange, loadArchive, loadSurface });
    }

    window.NCHSurfaceEngine = Object.freeze({ createSurfaceEngine });
}());
