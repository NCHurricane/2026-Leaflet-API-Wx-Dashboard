(function () {
    'use strict';

    const DEFAULT_ALERT_CATEGORY = 'Severe Weather Warnings';

    const byId = (id) => document.getElementById(id);
    let warningsPanelContext = null;

    function getCategoryCheckboxes() {
        return [...document.querySelectorAll('.weather-alerts-category')];
    }

    function setAllCategories(checked) {
        getCategoryCheckboxes().forEach((el) => {
            el.checked = checked;
        });
    }

    function syncMaster() {
        const allEl = byId('weather-alerts-all');
        if (!allEl) return;

        const childEls = getCategoryCheckboxes().filter((el) => el !== allEl);
        const allChecked = childEls.length > 0 && childEls.every((el) => el.checked);
        const noneChecked = childEls.every((el) => !el.checked);
        allEl.checked = allChecked;
        allEl.indeterminate = !allChecked && !noneChecked;
    }

    function applyDefaultSelection() {
        const allEl = byId('weather-alerts-all');

        getCategoryCheckboxes().forEach((el) => {
            if (el === allEl) return;
            el.checked = el.value === DEFAULT_ALERT_CATEGORY;
        });

        document.querySelectorAll('.wx-warn-filter-ck').forEach((el) => {
            el.checked = true;
        });

        syncMaster();
    }

    function getCheckedCategories() {
        return [...document.querySelectorAll('.weather-alerts-category:checked')]
            .map((el) => el.value)
            .filter((val) => val !== 'All Alerts');
    }

    function updateWarningFilterRowVisibility() {
        const filterRow = byId('wx-warn-filter-row');
        if (!filterRow) return;

        const checkedCategories = getCheckedCategories();
        const onlyShowSevereWarnings = checkedCategories.length === 1
            && checkedCategories[0] === DEFAULT_ALERT_CATEGORY;
        filterRow.style.display = onlyShowSevereWarnings ? 'flex' : 'none';
    }

    function updateFilterOptionsVisibility() {
        const filterContainer = byId('weather-alerts-filter-options');
        if (!filterContainer) return;
        filterContainer.hidden = false;
        updateWarningFilterRowVisibility();
    }

    function requireWarningPanelContext() {
        if (!warningsPanelContext) {
            throw new Error('Alerts warnings panel context has not been configured.');
        }
        return warningsPanelContext;
    }

    function configureWarningsPanel(context) {
        warningsPanelContext = context || null;
    }

    function renderActiveWarningsPanel() {
        const context = requireWarningPanelContext();
        const {
            activeAlertsForWarningsPanel,
            alertColors,
            alertDefaultColor,
            escapeHtml,
            formatExpiresInVerbose,
            formatLocalTimeWithTz,
            formatRelativeTime,
            getWarningsKnownIds,
            getWarningsPanelFilter,
            isTypeEnabled,
            severeWarningEvents,
            summarizeAreaDesc,
            updateWarningFilterCounts,
            warningPanelEmptyText,
        } = context;

        const list = byId('wx-warnings-list');
        const empty = byId('wx-warnings-empty');
        const countEl = byId('wx-warnings-count');
        const tabBtn = byId('wx-right-tab-btn-warnings');
        if (!list) return;

        const warningsKnownIds = getWarningsKnownIds();
        const alertsEnabled = isTypeEnabled('alerts');
        const items = alertsEnabled ? activeAlertsForWarningsPanel() : [];

        updateWarningFilterCounts(alertsEnabled);

        document.querySelectorAll('#wx-right-pane-warnings [data-warn-filter], #wx-right-pane-warnings [data-warn-panel-filter]').forEach((el) => {
            const key = el.getAttribute('data-warn-panel-filter') || el.getAttribute('data-warn-filter');
            const isActive = key === getWarningsPanelFilter();
            el.classList.toggle('is-active', isActive);
            el.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });

        if (countEl) {
            if (items.length > 0) {
                countEl.textContent = String(items.length);
                countEl.hidden = false;
            } else {
                countEl.hidden = true;
            }
        }

        if (items.length === 0) {
            list.innerHTML = '';
            if (empty) empty.textContent = warningPanelEmptyText();
            if (empty) empty.style.display = 'block';
            if (tabBtn) tabBtn.classList.remove('has-attention');
            warningsKnownIds.clear();
            return;
        }
        if (empty) empty.style.display = 'none';

        const previousIds = new Set(warningsKnownIds);
        const hasNewSevere = items.some((feat) => {
            const props = feat?.properties || {};
            const id = feat.id || `${props.event || ''}|${props.sent || ''}|${props.areaDesc || ''}`;
            return severeWarningEvents.has(String(props.event || '')) && !previousIds.has(id);
        });
        if (tabBtn) {
            const active = tabBtn.classList.contains('is-active');
            if (hasNewSevere && !active) tabBtn.classList.add('has-attention');
        }

        const now = Date.now();
        const seenIdsThisRender = new Set();
        list.innerHTML = items.map((feat) => {
            const props = feat.properties || {};
            const id = feat.id || `${props.event || ''}|${props.sent || ''}|${props.areaDesc || ''}`;
            seenIdsThisRender.add(id);
            const isNew = !warningsKnownIds.has(id);
            const event = props.event || 'Unknown Alert';
            const color = alertColors[event] || alertDefaultColor;
            const area = summarizeAreaDesc(props.areaDesc);
            const expiresMs = props.expires ? Date.parse(props.expires) : NaN;
            const sentMs = props.sent ? Date.parse(props.sent) : NaN;
            const countdownMs = Number.isFinite(expiresMs) ? expiresMs - now : NaN;
            const urgent = Number.isFinite(countdownMs) && countdownMs <= 15 * 60_000;
            const issuedRel = Number.isFinite(sentMs) ? `Issued ${formatRelativeTime(now - sentMs)} ago at ${formatLocalTimeWithTz(sentMs)}` : '';
            return [
                `<div class="wx-warn-row${isNew ? ' is-new' : ''}" data-feat-id="${escapeHtml(id)}" style="border-left-color:${color}">`,
                '  <div class="wx-warn-row-head">',
                `    <span class="wx-warn-event" style="color:${color}">${escapeHtml(event)}</span>`,
                '  </div>',
                area ? `  <div class="wx-warn-area">${escapeHtml(area)}</div>` : '',
                '  <div class="wx-warn-actions">',
                `    <span class="wx-warn-issued">${escapeHtml(issuedRel)}</span>`,
                `    <span class="wx-warn-expires${urgent ? ' is-urgent' : ''}">${escapeHtml(formatExpiresInVerbose(countdownMs))}</span>`,
                `    <button type="button" class="wx-warn-zoom" data-warn-zoom="${escapeHtml(id)}">Zoom To Alert</button>`,
                '  </div>',
                '</div>',
            ].join('');
        }).join('');

        warningsKnownIds.clear();
        seenIdsThisRender.forEach((id) => warningsKnownIds.add(id));
    }

    function wireActiveWarningsPanel() {
        const context = requireWarningPanelContext();
        const pane = byId('wx-right-pane-warnings');
        const list = byId('wx-warnings-list');
        if (!pane || !list) return;

        const filterBtns = pane.querySelectorAll('[data-warn-filter], [data-warn-panel-filter]');
        filterBtns.forEach((btn) => {
            btn.addEventListener('click', () => {
                const key = btn.getAttribute('data-warn-panel-filter') || btn.getAttribute('data-warn-filter');
                if (key !== 'all' && key !== 'tor' && key !== 'svr' && key !== 'ffw') return;
                context.setWarningsPanelFilter(key);
                context.getWarningsKnownIds().clear();
                renderActiveWarningsPanel();
            });
        });

        list.addEventListener('click', (evt) => {
            const row = evt.target.closest('.wx-warn-row');
            if (!row) return;
            evt.preventDefault();
            const id = row.getAttribute('data-feat-id');
            if (!id) return;
            const idMatch = (feature) => {
                const featureId = feature.id || `${feature.properties?.event || ''}|${feature.properties?.sent || ''}|${feature.properties?.areaDesc || ''}`;
                return featureId === id;
            };
            const feat = (context.getAlertsFullBaseFeatures() || []).find(idMatch)
                || (context.getAllAlertFeatures() || []).find(idMatch);
            if (!feat) return;

            const event = feat?.properties?.event || '';
            const checkedCategories = getCheckedCategories();
            const isVisible = !context.alertCategoryEventSet.has(event)
                || checkedCategories.some((cat) => (context.alertCategories[cat] || []).includes(event));
            if (!isVisible) {
                const matchingCategory = Object.entries(context.alertCategories)
                    .find(([, events]) => events.includes(event))?.[0];
                if (matchingCategory) {
                    const checkbox = [...document.querySelectorAll('.weather-alerts-category')]
                        .find((el) => el.value === matchingCategory);
                    if (checkbox) {
                        checkbox.checked = true;
                        syncMaster();
                        context.applyInMemoryAlertCategoryFilter();
                    }
                }
            }

            const center = context.alertFeatureCenterLatLng(feat);
            if (!center) return;
            context.setRegionAlertLocationState();
            context.map.flyTo(center, Math.max(context.map.getZoom(), 9), { duration: 1.0 });
            context.map.once('moveend', () => {
                context.openAlertsPagerAt(center);
            });
        });
    }

    function wireSidebarWarningFilterCheckboxes() {
        const context = requireWarningPanelContext();
        const filterCheckboxes = document.querySelectorAll('.wx-warn-filter-ck');
        if (!filterCheckboxes.length) return;
        filterCheckboxes.forEach((ck) => {
            ck.addEventListener('change', () => {
                const key = ck.getAttribute('data-warn-filter');
                if (ck.checked) {
                    context.getWarningsFilterEnabled().add(key);
                } else {
                    context.getWarningsFilterEnabled().delete(key);
                }
                context.getWarningsKnownIds().clear();
                if (context.hasAlertBaseFeatures()) {
                    context.applyInMemoryAlertCategoryFilter();
                } else {
                    renderActiveWarningsPanel();
                }
            });
        });
    }

    window.NCHAlertsPage = Object.freeze({
        applyDefaultSelection,
        configureWarningsPanel,
        getCategoryCheckboxes,
        getCheckedCategories,
        renderActiveWarningsPanel,
        setAllCategories,
        syncMaster,
        updateFilterOptionsVisibility,
        updateWarningFilterRowVisibility,
        wireActiveWarningsPanel,
        wireSidebarWarningFilterCheckboxes,
    });

    window.NCHProductPageShell?.registerProductPageEntry('alerts', {
        label: 'Alerts',
        title: 'Alerts — NCHurricane Dashboard',
        controller: window.NCHAlertsPage,
    });
}());
