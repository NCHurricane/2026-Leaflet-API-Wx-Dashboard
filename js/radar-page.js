(function () {
    'use strict';

    const byId = (id) => document.getElementById(id);
    let pageContext = null;

    function configureRadarPage(context) {
        pageContext = context || null;
    }

    function activeSite() {
        return String(byId('weather-radar-site')?.value || '').trim().toUpperCase();
    }

    function activeProduct() {
        return String(byId('weather-radar-product')?.value || 'L3_N0B').trim().toUpperCase();
    }

    function activeElevation() {
        return String(byId('weather-radar-elevation')?.value || '').trim().toLowerCase();
    }

    function syncElevationControl() {
        const productOption = byId('weather-radar-product')?.selectedOptions?.[0];
        const enabled = productOption?.dataset?.elevationSelection === 'true';
        const wrap = byId('wx-radar-elevation-wrap');
        if (wrap) wrap.style.display = enabled ? '' : 'none';
        if (!enabled) {
            const select = byId('weather-radar-elevation');
            if (select) select.value = '';
        }
        syncElevationPills();
    }

    function syncElevationPills() {
        const selected = activeElevation();
        byId('weather-radar-elevation-pills')
            ?.querySelectorAll('.radar-elevation-pill')
            .forEach((button) => {
                const active = button.dataset.elevation === selected;
                button.setAttribute('aria-checked', active ? 'true' : 'false');
                button.tabIndex = active ? 0 : -1;
            });
    }

    function renderElevationPills() {
        const select = byId('weather-radar-elevation');
        const pills = byId('weather-radar-elevation-pills');
        if (!select || !pills) return;
        pills.innerHTML = '';
        Array.from(select.options).forEach((option) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'radar-elevation-pill';
            button.dataset.elevation = option.value;
            button.setAttribute('role', 'radio');
            button.setAttribute('aria-checked', 'false');
            button.textContent = option.textContent;
            button.addEventListener('click', () => {
                if (select.value === option.value) return;
                select.value = option.value;
                syncElevationPills();
                pageContext?.loadUnified?.();
            });
            pills.appendChild(button);
        });
        syncElevationPills();
    }

    function updateElevationOptions(data) {
        const select = byId('weather-radar-elevation');
        if (!select) return;
        const elevations = Array.isArray(data?.available_elevations)
            ? data.available_elevations
            : [];
        const currentValue = activeElevation();
        const selectedFromResponse = data?.selected_elevation != null
            ? Number(data.selected_elevation).toFixed(1)
            : null;
        select.innerHTML = '';
        elevations.forEach((elevation) => {
            const value = Number(elevation).toFixed(1);
            const option = document.createElement('option');
            option.value = value;
            option.textContent = `${value}°`;
            select.appendChild(option);
        });
        const availableValues = new Set(Array.from(select.options, (o) => o.value));
        select.value = availableValues.has(currentValue)
            ? currentValue
            : availableValues.has(selectedFromResponse)
                ? selectedFromResponse
                : select.options[0]?.value || '';
        renderElevationPills();
        syncElevationControl();
    }

    function setStatus(message) {
        const el = byId('weather-radar-status');
        if (el) el.textContent = message || '';
    }

    function radarLookbackHours() {
        const slider = byId('radar-animate-slider');
        const hours = slider ? Number(slider.value) : 1;
        return Math.max(0.5, Math.min(12, Number.isFinite(hours) ? hours : 1));
    }

    function updateLookbackDisplay() {
        const slider = byId('radar-animate-slider');
        if (!slider) return;
        const displayValue = Number(slider.value);
        const displayText = displayValue === 0.5
            ? '30M'
            : displayValue === Math.floor(displayValue)
            ? `${Math.floor(displayValue)}H`
            : `${displayValue}H`;
        const valueDisplay = byId('radar-animate-slider-value');
        if (valueDisplay) valueDisplay.textContent = displayText;
    }

    async function renderScrubFrame(index) {
        const frames = pageContext?.getScrubFrames?.() || [];
        if (!frames.length || !pageContext?.isTypeEnabled?.('radar')) return;

        const storedContextKey = pageContext.getScrubContextKey();
        const liveContextKey = pageContext.currentScrubContextKey();
        if (storedContextKey && liveContextKey && storedContextKey !== liveContextKey) return;

        const frameIndex = Math.max(0, Math.min(index, frames.length - 1));
        pageContext.setScrubFrameIndex(frameIndex);
        pageContext.updateScrubberUi();
        const renderSeq = pageContext.nextScrubRenderSeq();

        try {
            const frame = frames[frameIndex];
            // Refresh storm tracks for this frame up front: the crossfade below
            // can early-return when a render is superseded (e.g. the parallel
            // live + scrubber loads on a site switch), which previously skipped
            // the trailing loadStormTracks call and left the overlay stale.
            pageContext.loadStormTracks?.(frame?.timestamp);
            const imageUrl = frame?.image_url;
            const bounds = Array.isArray(frame?.bounds) ? frame.bounds : null;
            if (!imageUrl || !bounds || bounds.length !== 4) {
                throw new Error('Frame has no image/bounds.');
            }

            const overlayUrl = pageContext.radarOverlayUrl(imageUrl);
            await new Promise((resolve) => {
                const image = new Image();
                image.onload = resolve;
                image.onerror = resolve;
                image.src = overlayUrl;
            });
            if (!pageContext.isCurrentScrubRenderSeq(renderSeq)) return;

            const oldOverlay = pageContext.getLiveOverlay();
            const leafletBounds = [[bounds[2], bounds[0]], [bounds[3], bounds[1]]];
            const newOverlay = pageContext.getOrCreateScrubOverlay?.(frame, overlayUrl, bounds)
                || pageContext.leaflet.imageOverlay(overlayUrl, leafletBounds, {
                    opacity: oldOverlay ? 0 : 0.9,
                    pane: 'radar-overlays',
                    zIndex: 320,
                });
            if (pageContext.isTypeEnabled('radar')) {
                if (!pageContext.map.hasLayer(newOverlay)) newOverlay.addTo(pageContext.map);
                pageContext.bringSitesAboveOverlays();
            }

            if (oldOverlay && pageContext.isTypeEnabled('radar')) {
                const applied = await pageContext.crossfadeOverlays(
                    oldOverlay,
                    newOverlay,
                    () => pageContext.isCurrentScrubRenderSeq(renderSeq),
                    { removeOldAfterFade: !pageContext.isScrubOverlay?.(oldOverlay) },
                );
                if (!applied) return;
            } else if (oldOverlay && pageContext.map.hasLayer(oldOverlay)) {
                pageContext.map.removeLayer(oldOverlay);
            }

            if (pageContext.setScrubOverlayActive) {
                pageContext.setScrubOverlayActive(newOverlay);
            } else {
                pageContext.setLiveOverlay(newOverlay);
            }
            pageContext.setCurrentFrameMeta?.(frame);
            if (pageContext.getOrCreateScrubOverlay && frames.length > 1) {
                [1, 2, -1].forEach((offset) => {
                    const neighborIndex = (frameIndex + offset + frames.length) % frames.length;
                    if (neighborIndex === frameIndex) return;
                    const neighbor = frames[neighborIndex];
                    const neighborUrl = neighbor?.image_url ? pageContext.radarOverlayUrl(neighbor.image_url) : '';
                    const neighborBounds = Array.isArray(neighbor?.bounds) ? neighbor.bounds : null;
                    const neighborOverlay = pageContext.getOrCreateScrubOverlay(neighbor, neighborUrl, neighborBounds);
                    if (!neighborOverlay) return;
                    if (!pageContext.map.hasLayer(neighborOverlay)) neighborOverlay.addTo(pageContext.map);
                    if (typeof neighborOverlay.setOpacity === 'function') neighborOverlay.setOpacity(0);
                });
            }
            const timestampMs = pageContext.resolveDataTimestampMs(frame?.timestamp);
            pageContext.setViewerTimestamp(timestampMs);
            pageContext.setReliability(
                'radar',
                `Radar ${activeProduct()}`,
                'Radar live frames',
                timestampMs,
            );
            pageContext.setTimestampSource('radar', 'radar_live_frames', timestampMs);
            pageContext.setScrubberStatus(`${frameIndex + 1} / ${frames.length} frames.`);
            pageContext.setGlobalStatus(`Radar scrub ${pageContext.formatValidTimeLabel(timestampMs)}.`);
        } catch (err) {
            if (!pageContext.isCurrentScrubRenderSeq(renderSeq)) return;
            pageContext.setGlobalStatus(`Radar scrubber error: ${err.message}`);
            pageContext.setScrubberStatus(`Frame unavailable: ${err.message}`);
        }
    }

    function wireControls() {
        const radarSlider = byId('radar-animate-slider');
        if (radarSlider) {
            radarSlider.addEventListener('input', updateLookbackDisplay);
            radarSlider.addEventListener('change', () => {
                if (activeSite()) pageContext?.loadScrubberFrames?.();
            });
        }

        byId('weather-radar-site')?.addEventListener('change', () => {
            pageContext?.clearSelectedStormCell?.();
            if (pageContext?.hasMultiSites?.()) {
                pageContext.clearMultiSiteOverlays?.();
                pageContext.clearMultiSites?.();
            }
            if (!activeSite()) {
                pageContext?.setActiveWeatherType?.('radar');
                pageContext?.clearSiteAndZoomConus?.();
                pageContext?.updateTypeSections?.();
                pageContext?.syncSiteSelectionHighlight?.();
                return;
            }

            const siteId = activeSite();
            const coords = pageContext?.siteCoords?.(siteId);
            if (coords && pageContext?.isTypeEnabled?.('radar')) {
                const [lat, lon] = coords;
                pageContext.map?.flyTo([lat, lon], Math.max(pageContext.map.getZoom(), 9), { duration: 0.6 });
            }
            pageContext?.setRegionRadarSiteSelectedState?.();
            pageContext?.updateTypeSections?.();
            pageContext?.syncSiteSelectionHighlight?.();
            pageContext?.loadUnified?.();
        });

        byId('weather-radar-product')?.addEventListener('change', () => {
            pageContext?.clearSelectedStormCell?.();
            const elevation = byId('weather-radar-elevation');
            if (elevation) elevation.value = '';
            renderElevationPills();
            syncElevationControl();
            pageContext?.loadUnified?.();
        });

        byId('weather-radar-show-sites')?.addEventListener('change', () => {
            pageContext?.syncSiteLayerVisibility?.();
            if (pageContext?.isTypeEnabled?.('radar') && !activeSite()) {
                if (byId('weather-radar-show-sites')?.checked) pageContext?.buildSiteMarkerLegend?.();
                else pageContext?.setLegend?.(null);
            }
        });

        byId('weather-radar-show-storm-tracks')?.addEventListener('change', () => {
            pageContext?.loadStormTracks?.();
            pageContext?.syncNstLegend?.();
        });

        byId('weather-radar-inspector')?.addEventListener('change', () => {
            pageContext?.syncRadarInspectorState?.();
        });

        byId('weather-refresh-radar')?.addEventListener('click', () => {
            if (!pageContext?.isTypeEnabled?.('radar')) {
                pageContext?.setGlobalStatus?.('Enable the Radar tab first.');
                return;
            }
            pageContext?.loadUnified?.();
        });

        byId('weather-clear-radar')?.addEventListener('click', () => {
            if (!pageContext?.isTypeEnabled?.('radar')) {
                pageContext?.setGlobalStatus?.('Enable the Radar tab first.');
                return;
            }
            pageContext?.clearLoadedOverlaysOnly?.();
        });
    }

    window.NCHRadarPage = Object.freeze({
        activeElevation,
        activeProduct,
        activeSite,
        configureRadarPage,
        radarLookbackHours,
        renderScrubFrame,
        setStatus,
        renderElevationPills,
        syncElevationControl,
        updateElevationOptions,
        updateLookbackDisplay,
        wireControls,
    });

    window.NCHProductPageShell?.registerProductPageEntry('radar', {
        label: 'Radar',
        title: 'Radar — NCHurricane Dashboard',
        controller: window.NCHRadarPage,
    });
}());
