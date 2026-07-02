(function () {
    'use strict';

    const SATELLITE_LOOKBACK_HOURS_MAX = 12;
    const SATELLITE_FRAME_REQUEST_MAX = 360;

    // Sectors available per platform. Values match data-satellite-sector attributes.
    const PLATFORM_SECTORS = {
        goes18:     ['FullDisk', 'CONUS', 'Meso1', 'Meso2'],
        goes19:     ['FullDisk', 'CONUS', 'Meso1', 'Meso2'],
        himawari9:  ['FullDisk'],
        meteosat12: ['FullDisk'],
        meteosat9:  ['FullDisk'],
    };

    // Channels available per non-GOES platform. null = all channels shown (GOES default).
    const PLATFORM_CHANNELS = {
        himawari9:  null,
        meteosat12: new Set(['Channel13']),
        meteosat9:  new Set([
            'Channel02',
            'Channel03',
            'Channel07',
            'Channel07Fire',
            'Channel08RAMSDIS',
            'Channel09RAMSDIS',
            'Channel13',
            'AirMass',
            'DayCloudPhase',
            'DaySnowFog',
            'NighttimeMicrophysics',
            'Dust',
            'Ash',
            'SulfurDioxide',
        ]),
    };

    // Platforms with a live data pipeline.
    const IMPLEMENTED_SATELLITES = new Set(['goes18', 'goes19', 'himawari9', 'meteosat12', 'meteosat9']);
    const SATELLITE_VIEW_PRESETS = {
        'goes18:FullDisk': [[-55, -220], [60, -55]],
        'goes18:CONUS': [[23.0, -127.0], [50.5, -65.0]],
        'goes18:Meso1': [[23.0, -127.0], [50.5, -65.0]],
        'goes18:Meso2': [[23.0, -127.0], [50.5, -65.0]],
        'goes19:FullDisk': [[-55, -155], [60, -15]],
        'goes19:CONUS': [[23.0, -127.0], [50.5, -65.0]],
        'goes19:Meso1': [[23.0, -127.0], [50.5, -65.0]],
        'goes19:Meso2': [[23.0, -127.0], [50.5, -65.0]],
        'himawari9:FullDisk': [[-55, 80], [60, 200]],
        'meteosat12:FullDisk': [[-55, -70], [70, 70]],
        'meteosat9:FullDisk': [[-55, -15], [55, 105]],
    };

    const byId = (id) => document.getElementById(id);
    let pageContext = null;

    function configureSatellitePage(context) {
        pageContext = context || null;
    }

    function activeSatId() {
        return String(byId('weather-satellite-sat-id')?.value || '').trim();
    }

    function activeSector() {
        return String(byId('weather-satellite-sector')?.value || '').trim();
    }

    function activeChannel() {
        return String(byId('weather-satellite-channel')?.value || 'Channel13').trim() || 'Channel13';
    }

    function satelliteViewPresetKey(satId, sector) {
        return `${String(satId || '').trim()}:${String(sector || '').trim()}`;
    }

    function satelliteViewPreset(satId, sector) {
        return SATELLITE_VIEW_PRESETS[satelliteViewPresetKey(satId, sector)] || null;
    }

    function syncSectorVisibility() {
        const satId = activeSatId();
        if (!satId) return;
        const allowed = new Set(PLATFORM_SECTORS[satId] || ['FullDisk', 'CONUS', 'Meso1', 'Meso2']);
        const currentSector = activeSector();
        const needsReset = !!currentSector && !allowed.has(currentSector);

        document.querySelectorAll('.satellite-subtab-button[data-satellite-sector]').forEach((btn) => {
            const supported = allowed.has(btn.dataset.satelliteSector);
            btn.style.display = supported ? '' : 'none';
        });

        if (needsReset) {
            const defaultSector = Array.from(allowed)[0] || 'FullDisk';
            const select = byId('weather-satellite-sector');
            if (select) select.value = defaultSector;
        }
    }

    function syncChannelVisibility() {
        const satId = activeSatId();
        const allowed = satId ? (PLATFORM_CHANNELS[satId] || null) : null;
        const select = byId('weather-satellite-channel');
        if (!select) return;

        Array.from(select.options).forEach((opt) => {
            opt.style.display = (!allowed || allowed.has(opt.value)) ? '' : 'none';
        });

        if (satId && allowed && !allowed.has(activeChannel())) {
            const fallback = allowed.has('Channel13') ? 'Channel13' : Array.from(allowed)[0];
            if (fallback) select.value = fallback;
        }
    }

    function syncSubtabs() {
        const satId = activeSatId();
        const sector = activeSector();
        document.querySelectorAll('.satellite-subtab-button[data-satellite-sat]').forEach((button) => {
            const isSelected = button.dataset.satelliteSat === satId;
            button.setAttribute('aria-selected', isSelected ? 'true' : 'false');
            button.tabIndex = isSelected ? 0 : -1;
        });
        syncSectorVisibility();
        syncChannelVisibility();
        document.querySelectorAll('.satellite-subtab-button[data-satellite-sector]').forEach((button) => {
            if (button.style.display === 'none') {
                button.setAttribute('aria-selected', 'false');
                button.tabIndex = -1;
                return;
            }
            const isSelected = button.dataset.satelliteSector === sector;
            button.setAttribute('aria-selected', isSelected ? 'true' : 'false');
            button.tabIndex = isSelected ? 0 : -1;
        });
    }

    function setSelectValue(selectId, value) {
        const select = byId(selectId);
        if (!select || select.value === value) return;
        select.value = value;
        syncSubtabs();
        select.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function recommendedLookbackHours() {
        const sector = activeSector().toUpperCase();
        if (sector === 'MESO1' || sector === 'MESO2') return 1;
        return 1;
    }

    function activeLookbackHours() {
        const slider = byId('weather-satellite-lookback-slider');
        const hours = Number(slider?.value || recommendedLookbackHours());
        if (!Number.isFinite(hours) || hours <= 0) return recommendedLookbackHours();
        return Math.max(1, Math.min(SATELLITE_LOOKBACK_HOURS_MAX, Math.round(hours)));
    }

    function setLookbackHours(hours) {
        const slider = byId('weather-satellite-lookback-slider');
        const displayEl = byId('weather-satellite-lookback-value');
        const safeHours = Math.max(1, Math.min(SATELLITE_LOOKBACK_HOURS_MAX, Math.round(Number(hours) || 1)));
        if (slider) slider.value = String(safeHours);
        if (displayEl) displayEl.textContent = `${safeHours}h`;
    }

    function maxFramesForRequest(hours) {
        const sector = activeSector().toUpperCase();
        const safeHours = Math.max(1, Math.min(SATELLITE_LOOKBACK_HOURS_MAX, Math.round(Number(hours) || 1)));
        if (sector === 'MESO1' || sector === 'MESO2') {
            return Math.min(SATELLITE_FRAME_REQUEST_MAX, safeHours * 60);
        }
        if (sector === 'FULLDISK') {
            return Math.min(SATELLITE_FRAME_REQUEST_MAX, safeHours * 6);
        }
        return Math.min(SATELLITE_FRAME_REQUEST_MAX, safeHours * 12);
    }

    function currentFrameRequestWindow() {
        const hours = activeLookbackHours();
        return {
            hours,
            maxFrames: maxFramesForRequest(hours),
        };
    }

    function currentFrameRequestWindows() {
        const activeHours = activeLookbackHours();
        const candidates = [activeHours, 3, 6, SATELLITE_LOOKBACK_HOURS_MAX];
        const seen = new Set();
        return candidates
            .map((hours) => Math.max(1, Math.min(SATELLITE_LOOKBACK_HOURS_MAX, Math.round(Number(hours) || 1))))
            .filter((hours) => {
                if (seen.has(hours)) return false;
                seen.add(hours);
                return true;
            })
            .map((hours) => ({
                hours,
                maxFrames: maxFramesForRequest(hours),
            }));
    }

    function activeWarmZoomMax() {
        const sector = activeSector().toUpperCase();
        if (sector === 'FULLDISK') return 6;
        return (sector === 'MESO1' || sector === 'MESO2') ? 10 : 8;
    }

    function bindSubtabGroup(selector, selectId, dataKey) {
        const buttons = Array.from(document.querySelectorAll(selector));
        buttons.forEach((button, index) => {
            button.addEventListener('click', () => {
                setSelectValue(selectId, button.dataset[dataKey]);
            });
            button.addEventListener('keydown', (event) => {
                if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                event.preventDefault();

                let nextIndex = index;
                if (event.key === 'ArrowLeft') nextIndex = index === 0 ? buttons.length - 1 : index - 1;
                if (event.key === 'ArrowRight') nextIndex = index === buttons.length - 1 ? 0 : index + 1;
                if (event.key === 'Home') nextIndex = 0;
                if (event.key === 'End') nextIndex = buttons.length - 1;

                const nextButton = buttons[nextIndex];
                if (!nextButton) return;
                setSelectValue(selectId, nextButton.dataset[dataKey]);
                nextButton.focus();
            });
        });
    }

    function wireControls() {
        bindSubtabGroup(
            '.satellite-subtab-button[data-satellite-sat]',
            'weather-satellite-sat-id',
            'satelliteSat'
        );
        bindSubtabGroup(
            '.satellite-subtab-button[data-satellite-sector]',
            'weather-satellite-sector',
            'satelliteSector'
        );
        syncSubtabs();

        [
            'weather-satellite-sat-id',
            'weather-satellite-sector',
            'weather-satellite-channel',
        ].forEach((id) => {
            byId(id)?.addEventListener('change', () => {
                syncSubtabs();
                if (!pageContext?.isTypeEnabled?.('satellite')) return;
                const satId = activeSatId();
                const sector = activeSector();
                if (!satId || !sector) {
                    pageContext.clearSatelliteLayerPool?.();
                    return;
                }
                if (!IMPLEMENTED_SATELLITES.has(satId)) {
                    const statusEl = byId('weather-satellite-status');
                    if (statusEl) statusEl.textContent = 'Data pipeline coming soon for this platform.';
                    return;
                }
                pageContext.updateLegend?.();
                pageContext.clearSatelliteLayerPool?.();
                if (id === 'weather-satellite-sat-id' || id === 'weather-satellite-sector') {
                    const preset = satelliteViewPreset(satId, sector);
                    if (preset) pageContext.fitSatelliteViewPreset?.(preset);
                }
                if (pageContext.isScrubMode?.()) {
                    pageContext.loadScrubberFrames?.();
                    return;
                }
                pageContext.loadCurrentFrame?.({ silent: false });
            });
        });

        byId('weather-satellite-lookback-slider')?.addEventListener('input', (event) => {
            const hours = parseInt(event.target.value, 10);
            setLookbackHours(hours);
            if (pageContext?.isScrubMode?.() && pageContext?.isTypeEnabled?.('satellite')) {
                pageContext.scheduleScrubberReload?.();
            }
        });
    }

    window.NCHSatellitePage = Object.freeze({
        activeChannel,
        activeLookbackHours,
        activeSatId,
        activeSector,
        activeWarmZoomMax,
        configureSatellitePage,
        currentFrameRequestWindow,
        currentFrameRequestWindows,
        maxFramesForRequest,
        recommendedLookbackHours,
        satelliteViewPreset,
        setLookbackHours,
        setSelectValue,
        syncSubtabs,
        wireControls,
    });

    window.NCHProductPageShell?.registerProductPageEntry('satellite', {
        label: 'Satellite',
        title: 'Satellite — NCHurricane Dashboard',
        controller: window.NCHSatellitePage,
    });
}());
