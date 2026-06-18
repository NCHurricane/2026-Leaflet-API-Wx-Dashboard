(function () {
    'use strict';

    const SATELLITE_LOOKBACK_HOURS_MAX = 12;
    const SATELLITE_FRAME_REQUEST_MAX = 360;

    const byId = (id) => document.getElementById(id);
    let pageContext = null;

    function configureSatellitePage(context) {
        pageContext = context || null;
    }

    function activeSatId() {
        return String(byId('weather-satellite-sat-id')?.value || 'goes19').trim() || 'goes19';
    }

    function activeSector() {
        return String(byId('weather-satellite-sector')?.value || 'CONUS').trim() || 'CONUS';
    }

    function activeChannel() {
        return String(byId('weather-satellite-channel')?.value || 'Channel13').trim() || 'Channel13';
    }

    function syncSubtabs() {
        const satId = activeSatId();
        const sector = activeSector();
        document.querySelectorAll('.satellite-subtab-button[data-satellite-sat]').forEach((button) => {
            const isSelected = button.dataset.satelliteSat === satId;
            button.setAttribute('aria-selected', isSelected ? 'true' : 'false');
            button.tabIndex = isSelected ? 0 : -1;
        });
        document.querySelectorAll('.satellite-subtab-button[data-satellite-sector]').forEach((button) => {
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
                pageContext.clearSatelliteLayerPool?.();
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
