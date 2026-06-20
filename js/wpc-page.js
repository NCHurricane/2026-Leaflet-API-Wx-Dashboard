(function () {
    'use strict';

    const byId = (id) => document.getElementById(id);
    let pageContext = null;
    let catalogGroups = new Map();
    let wpcScrubber = null;

    // ── State ────────────────────────────────────────────────────────────────

    const state = {
        group:       'ero',
        eroDay:      1,
        qpfTab:      '6hr',
        qpf24hrId:   '',
        qpf6hrIndex: 0,
        qpfMultiId:  '',
        winterTab:   'snow',
        snowDay:     1,
        snowId:      '',
        iceId:       '',
        sigwxId:      'sigwx_day1',
        surfaceIndex:  0,
        forecastIndex: 0,
    };

    // ── Helpers ───────────────────────────────────────────────────────────────

    function configureWpcPage(context) {
        pageContext = context || null;
    }

    // Legacy API — used by engine / external callers
    function activeWpcDay() {
        if (state.group === 'ero')     return state.eroDay;
        if (state.group === 'winter')  return state.winterTab === 'snow' ? state.snowDay : 1;
        return 1;
    }

    function activeWpcGroup() { return state.group; }

    function activeWpcProduct() {
        switch (state.group) {
            case 'qpf':
                if (state.qpfTab === '24hr')     return state.qpf24hrId;
                if (state.qpfTab === 'multiday') return state.qpfMultiId;
                return state.qpf6hrId || '';
            case 'winter':
                return state.winterTab === 'snow' ? state.snowId : state.iceId;
            case 'sigwx':
                return state.sigwxId;
            case 'surface':
                return state.surfaceId || '';
            case 'forecast':
                return state.forecastId || '';
            default:
                return '';
        }
    }

    // current frame product id for surface (used by engine)
    Object.defineProperty(state, 'surfaceId', {
        get() {
            const products = catalogGroups.get('surface')?.products || [];
            return products[state.surfaceIndex]?.id || '';
        },
    });

    // current frame product id for forecast scrubber (used by engine)
    Object.defineProperty(state, 'forecastId', {
        get() {
            const products = catalogGroups.get('forecast')?.products || [];
            return products[state.forecastIndex]?.id || '';
        },
    });

    // current frame product id for qpf 6hr (used by engine)
    Object.defineProperty(state, 'qpf6hrId', {
        get() {
            const products = _qpf6hrProducts();
            return products[state.qpf6hrIndex]?.id || '';
        },
    });

    function _qpf6hrProducts() {
        return (catalogGroups.get('qpf')?.products || []).filter((p) => p.id.startsWith('qpf6_'));
    }

    function _reload() {
        if (!pageContext?.isTypeEnabled?.('wpc')) return;
        pageContext.loadWpcLayer?.();
    }

    // ── Pill toggle helpers ───────────────────────────────────────────────────

    function _selectPill(container, selectedBtn) {
        container.querySelectorAll('[aria-selected]').forEach((btn) => {
            btn.setAttribute('aria-selected', btn === selectedBtn ? 'true' : 'false');
        });
    }

    function _showPanel(parentEl, activeId) {
        parentEl.querySelectorAll('.wpc-group-panel, .wpc-subtab-panel').forEach((panel) => {
            panel.classList.toggle('is-active', panel.id === activeId);
        });
    }

    // ── Group pills ───────────────────────────────────────────────────────────

    function _wireGroupPills() {
        const pills = document.querySelectorAll('.wpc-group-pill');
        const panelsRoot = byId('weather-wpc-opts');
        pills.forEach((pill) => {
            pill.addEventListener('click', () => {
                const group = pill.dataset.wpcGroup;
                state.group = group;
                _selectPill(pill.closest('.wpc-group-pills'), pill);
                _showPanel(panelsRoot, `wpc-panel-${group}`);
                if (group === 'qpf') {
                    byId('wpc-panel-qpf')?.querySelector('[data-wpc-qpf-tab="6hr"]')?.click();
                } else if (group === 'winter') {
                    byId('wpc-panel-winter')?.querySelector('[data-wpc-winter-tab="snow"]')?.click();
                }
                _activateScrubber();
                _reload();
            });
        });
    }

    // ── ERO day pills ─────────────────────────────────────────────────────────

    function _wireEroDayPills() {
        const container = byId('wpc-panel-ero');
        container?.querySelectorAll('[data-wpc-ero-day]').forEach((btn) => {
            btn.addEventListener('click', () => {
                state.eroDay = Number(btn.dataset.wpcEroDay);
                _selectPill(btn.closest('.wpc-day-pills'), btn);
                if (state.group === 'ero') _reload();
            });
        });
    }

    // ── QPF sub-tabs ──────────────────────────────────────────────────────────

    function _wireQpfSubtabs() {
        const panel = byId('wpc-panel-qpf');
        panel?.querySelectorAll('[data-wpc-qpf-tab]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.wpcQpfTab;
                state.qpfTab = tab;
                _selectPill(btn.closest('.wpc-subtabs'), btn);
                panel.querySelectorAll('.wpc-subtab-panel').forEach((p) => {
                    p.classList.toggle('is-active', p.id === `wpc-qpf-panel-${tab}`);
                });
                _activateScrubber();
                if (state.group === 'qpf') _reload();
            });
        });
    }

    function _wireQpfRadioList(listId, stateKey, tab) {
        const ul = byId(listId);
        ul?.addEventListener('change', (e) => {
            if (e.target.name === listId) {
                state[stateKey] = e.target.value;
                if (state.group === 'qpf' && state.qpfTab === tab) _reload();
            }
        });
    }

    // ── Winter sub-tabs & day pills ───────────────────────────────────────────

    function _wireWinterSubtabs() {
        const panel = byId('wpc-panel-winter');
        panel?.querySelectorAll('[data-wpc-winter-tab]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.wpcWinterTab;
                state.winterTab = tab;
                _selectPill(btn.closest('.wpc-subtabs'), btn);
                panel.querySelectorAll('.wpc-subtab-panel').forEach((p) => {
                    p.classList.toggle('is-active', p.id === `wpc-winter-panel-${tab}`);
                });
                if (state.group === 'winter') _reload();
            });
        });

        panel?.querySelectorAll('[data-wpc-snow-day]').forEach((btn) => {
            btn.addEventListener('click', () => {
                state.snowDay = Number(btn.dataset.wpcSnowDay);
                _selectPill(btn.closest('.wpc-day-pills'), btn);
                _populateWinterSnowList();
                if (state.group === 'winter' && state.winterTab === 'snow') _reload();
            });
        });
    }

    // ── SigWx radio list ──────────────────────────────────────────────────────

    function _wireSignificantWeather() {
        byId('wpc-sigwx-list')?.addEventListener('change', (e) => {
            if (e.target.name === 'wpc-sigwx') {
                state.sigwxId = e.target.value;
                if (state.group === 'sigwx') _reload();
            }
        });
    }

    // ── Shared bottom scrubber ────────────────────────────────────────────────

    const _scrubFrames = { surface: [], forecast: [], qpf6hr: [] };

    function _scrubberKey() {
        if (state.group === 'forecast') return 'forecast';
        if (state.group === 'qpf' && state.qpfTab === '6hr') return 'qpf6hr';
        return null;
    }

    function _syncSidebarRadio(listId, index) {
        const ul = byId(listId);
        if (!ul) return;
        const inputs = ul.querySelectorAll('input[type="radio"]');
        inputs.forEach((input, i) => { input.checked = i === index; });
    }

    function _initWpcScrubber() {
        const el = byId('wpc-bottom-scrubber');
        if (!el || wpcScrubber) return;
        wpcScrubber = window.NCHScrubber?.createScrubber(el, {
            onFrame(frame, index) {
                const key = _scrubberKey();
                if (key === 'forecast') {
                    state.forecastIndex = index;
                    _syncSidebarRadio('wpc-forecast-list', index);
                }
                if (key === 'qpf6hr') {
                    state.qpf6hrIndex = index;
                    _syncSidebarRadio('wpc-qpf-6hr-list', index);
                }
                _reload();
            },
        });
    }

    function _activateScrubber() {
        const key = _scrubberKey();
        const bar = byId('wpc-scrubber-bar');
        if (!bar) return;
        bar.hidden = !key;
        if (!key) return;
        if (!wpcScrubber) _initWpcScrubber();
        const savedIndex = key === 'surface'  ? state.surfaceIndex
                         : key === 'forecast' ? state.forecastIndex
                         : state.qpf6hrIndex;
        wpcScrubber?.setFrames(_scrubFrames[key]);
        wpcScrubber?.goTo(savedIndex);
    }

    function _populateAllScrubberFrames() {
        _scrubFrames.surface  = (catalogGroups.get('surface')?.products  || []).map((p) => ({ label: p.label, id: p.id }));
        _scrubFrames.forecast = (catalogGroups.get('forecast')?.products || []).map((p) => ({ label: p.label, id: p.id }));
        _scrubFrames.qpf6hr   = _qpf6hrProducts().map((p) => ({ label: p.label, id: p.id }));

        const forecastProducts = catalogGroups.get('forecast')?.products || [];
        _buildRadioList(byId('wpc-forecast-list'), forecastProducts, 'wpc-forecast-list', forecastProducts[state.forecastIndex]?.id || '');

        const qpf6hrProducts = _qpf6hrProducts();
        _buildRadioList(byId('wpc-qpf-6hr-list'), qpf6hrProducts, 'wpc-qpf-6hr-list', qpf6hrProducts[state.qpf6hrIndex]?.id || '');

        _activateScrubber();
    }

    function _wireScrubberSidebarList(listId, indexKey) {
        byId(listId)?.addEventListener('change', (e) => {
            if (e.target.name !== listId) return;
            const ul = byId(listId);
            const inputs = [...ul.querySelectorAll('input[type="radio"]')];
            const index = inputs.indexOf(e.target);
            if (index < 0) return;
            state[indexKey] = index;
            wpcScrubber?.goTo(index);
        });
    }

    // ── Radio list population helpers ─────────────────────────────────────────

    function _buildRadioList(ulEl, products, name, currentId) {
        if (!ulEl) return;
        ulEl.replaceChildren(...products.map((p, i) => {
            const inputId = `${name}-${p.id}`;
            const li = document.createElement('li');
            li.className = 'wpc-radio-item';
            const label = document.createElement('label');
            label.htmlFor = inputId;
            label.textContent = p.label;
            const input = document.createElement('input');
            input.type = 'radio';
            input.id = inputId;
            input.name = name;
            input.value = p.id;
            input.checked = currentId ? p.id === currentId : i === 0;
            li.appendChild(label);
            li.appendChild(input);
            return li;
        }));
        return !currentId && products.length ? products[0].id : currentId;
    }

    function _populateQpf24hrList() {
        const products = (catalogGroups.get('qpf')?.products || []).filter((p) => p.id.startsWith('qpf24_'));
        const first = _buildRadioList(byId('wpc-qpf-24hr-list'), products, 'wpc-qpf-24hr-list', state.qpf24hrId);
        if (!state.qpf24hrId && first) state.qpf24hrId = first;
    }

    function _populateQpfMultiList() {
        const products = (catalogGroups.get('qpf')?.products || []).filter(
            (p) => !p.id.startsWith('qpf24_') && !p.id.startsWith('qpf6_'),
        );
        const first = _buildRadioList(byId('wpc-qpf-multiday-list'), products, 'wpc-qpf-multiday-list', state.qpfMultiId);
        if (!state.qpfMultiId && first) state.qpfMultiId = first;
    }

    function _populateWinterSnowList() {
        const day = state.snowDay;
        const products = (catalogGroups.get('winter')?.products || []).filter(
            (p) => p.id.includes('_snow') && (p.days || []).includes(day),
        );
        const first = _buildRadioList(byId('wpc-winter-snow-list'), products, 'wpc-winter-snow-list', state.snowId);
        if (!state.snowId && first) state.snowId = first;
    }

    function _populateWinterIceList() {
        const products = (catalogGroups.get('winter')?.products || []).filter((p) => p.id.includes('_ice'));
        const first = _buildRadioList(byId('wpc-winter-ice-list'), products, 'wpc-winter-ice-list', state.iceId);
        if (!state.iceId && first) state.iceId = first;
    }

    // ── Catalog update ────────────────────────────────────────────────────────

    function updateWpcCatalog(catalog) {
        catalogGroups = new Map(
            (catalog?.groups || []).map((g) => [g.group, g]),
        );
        _populateQpf24hrList();
        _populateQpfMultiList();
        _populateWinterSnowList();
        _populateWinterIceList();
        _populateAllScrubberFrames();
    }

    // ── Wire everything ───────────────────────────────────────────────────────

    function wireControls() {
        _wireGroupPills();
        _wireEroDayPills();
        _wireQpfSubtabs();
        _wireQpfRadioList('wpc-qpf-24hr-list', 'qpf24hrId', '24hr');
        _wireQpfRadioList('wpc-qpf-multiday-list', 'qpfMultiId', 'multiday');
        _wireWinterSubtabs();
        _wireSignificantWeather();
        // Winter snow/ice radio lists
        byId('wpc-winter-snow-list')?.addEventListener('change', (e) => {
            if (e.target.name === 'wpc-winter-snow-list') {
                state.snowId = e.target.value;
                if (state.group === 'winter' && state.winterTab === 'snow') _reload();
            }
        });
        byId('wpc-winter-ice-list')?.addEventListener('change', (e) => {
            if (e.target.name === 'wpc-winter-ice-list') {
                state.iceId = e.target.value;
                if (state.group === 'winter' && state.winterTab === 'ice') _reload();
            }
        });
        _wireScrubberSidebarList('wpc-forecast-list', 'forecastIndex');
        _wireScrubberSidebarList('wpc-qpf-6hr-list', 'qpf6hrIndex');
        byId('weather-refresh-wpc')?.addEventListener('click', _reload);
    }

    // ── Public API ────────────────────────────────────────────────────────────

    window.NCHWpcPage = Object.freeze({
        activeWpcDay,
        activeWpcGroup,
        activeWpcProduct,
        configureWpcPage,
        updateWpcCatalog,
        wireControls,
    });

    window.NCHProductPageShell?.registerProductPageEntry('wpc', {
        label: 'WPC',
        title: 'WPC Excessive Rainfall — NCHurricane Dashboard',
        controller: window.NCHWpcPage,
    });
}());
