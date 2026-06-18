(function () {
    'use strict';

    const byId = (id) => document.getElementById(id);
    let pageContext = null;

    function configureSpcPage(context) {
        pageContext = context || null;
    }

    function getSpcDay() {
        return parseInt(byId('weather-spc-day')?.value || '1', 10);
    }

    function getSpcFireDay() {
        return parseInt(byId('weather-spc-fire-day')?.value || '1', 10);
    }

    function getAllowedConvectiveHazards(day = getSpcDay()) {
        if (day <= 2) return ['cat', 'torn', 'cigtorn', 'wind', 'cigwind', 'hail', 'cighail'];
        if (day === 3) return ['cat', 'prob'];
        return ['cat'];
    }

    function getDefaultConvectiveHazards() {
        return ['cat'];
    }

    function getCheckedConvectiveHazards() {
        return Array.from(document.querySelectorAll('.weather-spc-convective-toggle:checked')).map((el) => el.value);
    }

    function getCheckedFireHazards() {
        return Array.from(document.querySelectorAll('.weather-spc-fire-toggle:checked')).map((el) => el.value);
    }

    function getSelectedHazards(day = getSpcDay()) {
        const fireHazards = getCheckedFireHazards();
        if (fireHazards.length) return fireHazards;
        const allowed = new Set(getAllowedConvectiveHazards(day));
        return getCheckedConvectiveHazards().filter((h) => allowed.has(h));
    }

    function getSupplementalSelections() {
        const reportsDays = [];
        if (byId('weather-spc-reports-today')?.checked) reportsDays.push('today');
        if (byId('weather-spc-reports-yesterday')?.checked) reportsDays.push('yesterday');
        const reportTypes = [];
        if (byId('weather-spc-report-type-torn')?.checked) reportTypes.push('torn');
        if (byId('weather-spc-report-type-wind')?.checked) reportTypes.push('wind');
        if (byId('weather-spc-report-type-hail')?.checked) reportTypes.push('hail');
        const watchLayers = [];
        if (byId('weather-spc-watch-tor-polygon')?.checked) watchLayers.push({ type: 'tor', mode: 'polygon' });
        else if (byId('weather-spc-watch-tor-counties')?.checked) watchLayers.push({ type: 'tor', mode: 'counties' });
        if (byId('weather-spc-watch-svr-polygon')?.checked) watchLayers.push({ type: 'svr', mode: 'polygon' });
        else if (byId('weather-spc-watch-svr-counties')?.checked) watchLayers.push({ type: 'svr', mode: 'counties' });
        return {
            reportsEnabled: reportsDays.length > 0 && reportTypes.length > 0,
            reportsDays,
            reportTypes,
            mdsEnabled: !!byId('weather-spc-show-mds')?.checked,
            watchesEnabled: watchLayers.length > 0,
            watchLayers,
        };
    }

    function spcSelectionKey(day, fireDay, hazards, supplemental) {
        const sortedHazards = (hazards || []).map((h) => String(h)).sort();
        const watchLayers = (supplemental?.watchLayers || [])
            .map((w) => `${String(w?.type || '').toLowerCase()}:${String(w?.mode || '').toLowerCase()}`)
            .sort();
        const reportsDays = [...(supplemental?.reportsDays || [])].map((d) => String(d)).sort();
        const reportTypes = [...(supplemental?.reportTypes || [])].map((t) => String(t)).sort();
        return JSON.stringify({
            day: Number(day || 1),
            fireDay: Number(fireDay || 1),
            hazards: sortedHazards,
            reportsDays,
            reportTypes,
            mdsEnabled: !!supplemental?.mdsEnabled,
            watchesEnabled: !!supplemental?.watchesEnabled,
            watchLayers,
        });
    }

    function updateReportFilterState() {
        const hasReportDay = !!byId('weather-spc-reports-today')?.checked
            || !!byId('weather-spc-reports-yesterday')?.checked;
        ['weather-spc-report-type-torn', 'weather-spc-report-type-wind', 'weather-spc-report-type-hail']
            .forEach((filterId) => {
                const filterEl = byId(filterId);
                if (!filterEl) return;
                if (!hasReportDay) filterEl.checked = false;
                filterEl.disabled = !hasReportDay;
            });
    }

    function syncConvectiveOptions(resetSelection = false) {
        const day = getSpcDay();
        const allowed = new Set(getAllowedConvectiveHazards(day));
        const defaults = new Set(getDefaultConvectiveHazards());
        const SPC_CONVECTIVE_LABELS = pageContext?.getSpcConvectiveLabels?.() || {};
        document.querySelectorAll('.weather-spc-convective-row').forEach((row) => {
            const hazard = row.dataset.hazard || '';
            const enabled = allowed.has(hazard);
            row.style.display = enabled ? '' : 'none';
            const input = row.querySelector('.weather-spc-convective-toggle');
            if (input) {
                if (!enabled) input.checked = false;
                else if (resetSelection) input.checked = defaults.has(hazard);
            }
            const label = row.querySelector('.weather-spc-convective-label');
            if (label && SPC_CONVECTIVE_LABELS[hazard]) {
                label.textContent = hazard === 'cat' && day >= 4 ? 'Severe Weather Outlook' : SPC_CONVECTIVE_LABELS[hazard];
            }
        });
        if (resetSelection) {
            document.querySelectorAll('.weather-spc-fire-toggle').forEach((el) => { el.checked = false; });
        }
    }

    function syncFireWeatherOptions(resetSelection = false) {
        const fireDay = getSpcFireDay();
        const fireList = byId('weather-spc-fire-list');
        if (!fireList) return;
        fireList.querySelectorAll('.weather-spc-fire-row[data-categorical="1"]').forEach((row) => {
            const visible = fireDay >= 3 && fireDay <= 8;
            row.style.display = visible ? '' : 'none';
            if (!visible) {
                const input = row.querySelector('input[type="checkbox"]');
                if (input) input.checked = false;
            }
        });
        if (resetSelection) {
            fireList.querySelectorAll('.weather-spc-fire-toggle').forEach((el) => { el.checked = false; });
        }
    }

    function shouldResetConvectiveDaySelection() {
        return !getCheckedFireHazards().length && !_hasActiveSupplementalSelections();
    }

    function shouldResetFireDaySelection() {
        return !getCheckedConvectiveHazards().length && !_hasActiveSupplementalSelections();
    }

    function _hasActiveSupplementalSelections() {
        const supplemental = getSupplementalSelections();
        return supplemental.reportsEnabled || supplemental.mdsEnabled || supplemental.watchesEnabled;
    }

    function renderArchiveFrame(frame) {
        const geojson = {
            type: 'FeatureCollection',
            features: frame?.features || [],
        };
        const currentLayer = pageContext?.getSpcLayer?.();
        if (currentLayer) pageContext.map.removeLayer(currentLayer);

        const hazard = pageContext?.getPrimarySpcHazard?.();
        const style = pageContext?.getSpcStyleFn?.(hazard);
        const layer = pageContext?.leaflet?.geoJSON(geojson, {
            style,
            onEachFeature(feature, featureLayer) {
                featureLayer.bindPopup(pageContext.spcPopup(feature));
                featureLayer.on('add', () => pageContext.applySpcCigPattern(feature, featureLayer));
            },
        });
        pageContext?.setSpcLayer?.(layer);

        if (!layer || !pageContext?.isSpcEnabled?.()) return;
        layer.addTo(pageContext.map);
        pageContext.applySpcCigPatternsToGroup(layer);
        pageContext.bringBoundaryLayersAboveSpcOverlays();
    }

    function _refreshIfEnabled() {
        if (!pageContext?.isSpcEnabled?.()) return;
        pageContext.refreshSpc?.();
    }

    function _enforceMutuallyExclusiveWatches(idA, idB) {
        const elA = byId(idA);
        const elB = byId(idB);
        if (!elA || !elB) return;
        elA.addEventListener('change', () => {
            if (elA.checked) {
                elB.checked = false;
                pageContext?.clearSpcExclusivePeers?.('watches');
                pageContext?.syncSpcSubtabForSelection?.('watches');
            }
            _refreshIfEnabled();
        });
        elB.addEventListener('change', () => {
            if (elB.checked) {
                elA.checked = false;
                pageContext?.clearSpcExclusivePeers?.('watches');
                pageContext?.syncSpcSubtabForSelection?.('watches');
            }
            _refreshIfEnabled();
        });
    }

    function wireControls() {
        // Subtab keyboard nav
        const spcSubtabButtons = Array.from(document.querySelectorAll('.spc-subtab-button'));
        spcSubtabButtons.forEach((button, index) => {
            button.addEventListener('click', () => {
                pageContext?.setSpcSubtab?.(button.dataset.spcSubtab || 'outlooks');
            });
            button.addEventListener('keydown', (event) => {
                if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                event.preventDefault();
                let nextIndex = index;
                if (event.key === 'ArrowLeft') nextIndex = index === 0 ? spcSubtabButtons.length - 1 : index - 1;
                if (event.key === 'ArrowRight') nextIndex = index === spcSubtabButtons.length - 1 ? 0 : index + 1;
                if (event.key === 'Home') nextIndex = 0;
                if (event.key === 'End') nextIndex = spcSubtabButtons.length - 1;
                const nextButton = spcSubtabButtons[nextIndex];
                if (!nextButton) return;
                pageContext?.setSpcSubtab?.(nextButton.dataset.spcSubtab || 'outlooks');
                nextButton.focus();
            });
        });
        pageContext?.syncSpcSubtabForSelection?.();

        byId('wx-section-spc')?.addEventListener('change', () => {
            pageContext?.closeAlertDetail?.();
        });

        // Day selects
        const spcDaySelect = byId('weather-spc-day');
        if (spcDaySelect) {
            spcDaySelect.addEventListener('change', () => {
                syncConvectiveOptions(shouldResetConvectiveDaySelection());
                pageContext?.syncSpcSubtabForSelection?.('outlooks');
                if (pageContext?.isSpcEnabled?.()) pageContext.refreshSpc?.();
            });
        }
        const fireDaySelect = byId('weather-spc-fire-day');
        if (fireDaySelect) {
            fireDaySelect.addEventListener('change', () => {
                syncFireWeatherOptions(shouldResetFireDaySelection());
                pageContext?.syncSpcSubtabForSelection?.('fire');
                if (pageContext?.isSpcEnabled?.()) pageContext.refreshSpc?.();
            });
        }

        // Convective toggles
        const BASE_HAZARDS = ['cat', 'torn', 'wind', 'hail'];
        document.querySelectorAll('.weather-spc-convective-toggle').forEach((el) => {
            el.addEventListener('change', () => {
                if (el.checked) pageContext?.clearSpcExclusivePeers?.('convective');
                pageContext?.syncSpcSubtabForSelection?.('outlooks');
                const day = getSpcDay();
                if (day === 3 && (el.value === 'cat' || el.value === 'prob')) {
                    if (el.checked) {
                        document.querySelectorAll('.weather-spc-convective-toggle').forEach((other) => {
                            if (other === el) return;
                            if ((other.value === 'cat' || other.value === 'prob') && other.checked) {
                                other.checked = false;
                            }
                        });
                    }
                } else if (el.checked && BASE_HAZARDS.includes(el.value)) {
                    const cigMap = pageContext?.getSpcCigOverlayByHazard?.() || {};
                    const keepCig = cigMap[el.value] || null;
                    document.querySelectorAll('.weather-spc-convective-toggle').forEach((other) => {
                        if (other === el) return;
                        const val = other.value;
                        if (BASE_HAZARDS.includes(val)) {
                            if (other.checked) other.checked = false;
                        } else if (val && val.startsWith('cig') && val !== keepCig) {
                            if (other.checked) other.checked = false;
                        }
                    });
                }
                if (el.checked && day <= 2) {
                    const cigMap = pageContext?.getSpcCigOverlayByHazard?.() || {};
                    const cigHazard = cigMap[el.value];
                    if (cigHazard) {
                        const cigEl = document.querySelector(`.weather-spc-convective-toggle[value="${cigHazard}"]`);
                        if (cigEl && !cigEl.checked && !cigEl.disabled) cigEl.checked = true;
                    }
                }
                _refreshIfEnabled();
            });
        });

        // Watch polygon/counties mutual exclusion
        _enforceMutuallyExclusiveWatches('weather-spc-watch-tor-polygon', 'weather-spc-watch-tor-counties');
        _enforceMutuallyExclusiveWatches('weather-spc-watch-svr-polygon', 'weather-spc-watch-svr-counties');

        // Storm reports day
        ['weather-spc-reports-today', 'weather-spc-reports-yesterday'].forEach((id) => {
            byId(id)?.addEventListener('change', (evt) => {
                if (evt?.target?.checked) {
                    pageContext?.clearSpcExclusivePeers?.('reports');
                    ['weather-spc-report-type-torn', 'weather-spc-report-type-wind', 'weather-spc-report-type-hail']
                        .forEach((filterId) => {
                            const filterEl = byId(filterId);
                            if (filterEl) filterEl.checked = true;
                        });
                }
                updateReportFilterState();
                pageContext?.syncSpcSubtabForSelection?.('reports');
                _refreshIfEnabled();
            });
        });

        // MDS + report type filters
        [
            'weather-spc-show-mds',
            'weather-spc-report-type-torn',
            'weather-spc-report-type-wind',
            'weather-spc-report-type-hail',
        ].forEach((id) => {
            byId(id)?.addEventListener('change', (evt) => {
                if (id === 'weather-spc-show-mds' && evt?.target?.checked) {
                    pageContext?.clearSpcExclusivePeers?.('mds');
                }
                pageContext?.syncSpcSubtabForSelection?.('reports');
                _refreshIfEnabled();
            });
        });

        // Fire weather toggles
        document.querySelectorAll('.weather-spc-fire-toggle').forEach((el) => {
            el.addEventListener('change', () => {
                if (el.checked) {
                    document.querySelectorAll('.weather-spc-fire-toggle').forEach((other) => {
                        if (other !== el) other.checked = false;
                    });
                    pageContext?.clearSpcExclusivePeers?.('fire', { keepFireTarget: el });
                    pageContext?.syncSpcSubtabForSelection?.('fire');
                }
                _refreshIfEnabled();
            });
        });
    }

    window.NCHSpcPage = Object.freeze({
        configureSpcPage,
        getAllowedConvectiveHazards,
        getCheckedConvectiveHazards,
        getCheckedFireHazards,
        getDefaultConvectiveHazards,
        getSelectedHazards,
        getSupplementalSelections,
        getSpcDay,
        getSpcFireDay,
        renderArchiveFrame,
        shouldResetConvectiveDaySelection,
        shouldResetFireDaySelection,
        spcSelectionKey,
        syncConvectiveOptions,
        syncFireWeatherOptions,
        updateReportFilterState,
        wireControls,
    });

    window.NCHProductPageShell?.registerProductPageEntry('spc', {
        label: 'SPC',
        title: 'SPC Outlooks — NCHurricane Dashboard',
        controller: window.NCHSpcPage,
    });
}());
