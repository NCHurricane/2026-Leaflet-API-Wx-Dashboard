import { createWpcEngine } from '../wpc/wpc-engine.js?v=20260804a';

const AUTO_REFRESH_INTERVAL_MS = 30 * 60 * 1000;
const GROUPS = Object.freeze([
    { value: 'ero', label: 'Excess Rain' },
    { value: 'qpf', label: 'QPF' },
    { value: 'mpd', label: 'Meso Disc' },
    { value: 'winter', label: 'Winter' },
]);
const GROUP_VALUES = new Set(GROUPS.map((group) => group.value));
const PILL_GROUPS = new Set(['ero', 'qpf']);
const QPF_PRODUCT_LABELS = new Map([
    ['qpf48_day1_2', '1–2'],
    ['qpf72_day1_3', '1–3'],
    ['qpf120_day1_5', '1–5'],
    ['qpf168_day1_7', '1–7'],
]);

function productDay(product) {
    const match = String(product?.days || '').match(/\d+/);
    return match ? Number(match[0]) : 1;
}

function curatedProducts(group, catalogGroups) {
    const products = catalogGroups.get(group)?.products || [];
    if (group === 'ero') return products.filter((product) => productDay(product) <= 3);
    if (group === 'qpf') return products.filter((product) => QPF_PRODUCT_LABELS.has(product.id));
    if (group === 'mpd') return products.filter((product) => product.id === 'mpd_active');
    if (group === 'winter') return products.filter((product) => productDay(product) <= 3);
    return [];
}

export function createWorkspaceWpc({
    api,
    mapCore,
    legend,
    status,
    getRegion,
    paneName,
    elements,
    onDetail = null,
}) {
    const {
        enabledInput,
        controls,
        groupPills,
        productPillsWrap,
        productPills,
        winterDayWrap,
        winterDayPills,
        productSelectWrap,
        productSelect,
        opacityInput,
        opacityLabel,
    } = elements;
    const lifecycle = new AbortController();
    const engine = createWpcEngine({ api, mapCore, legend, status, onDetail, paneName });
    let catalogGroups = new Map();
    let catalogPromise = null;
    let activeGroup = '';
    let activeProductId = '';
    let activeWinterDay = 0;
    let lastAutoRefreshMs = 0;

    const isEnabled = () => enabledInput.checked;
    const supportsCurrentRegion = () => String(getRegion() || '').toUpperCase() === 'CONUS';
    const productsForActiveGroup = () => {
        const products = curatedProducts(activeGroup, catalogGroups);
        if (activeGroup !== 'winter') return products;
        return activeWinterDay
            ? products.filter((product) => productDay(product) === activeWinterDay)
            : [];
    };
    const selectedProduct = () => productsForActiveGroup()
        .find((product) => product.id === activeProductId) || null;
    const hasSelection = () => Boolean(activeGroup && selectedProduct());

    function selection() {
        const product = selectedProduct();
        if (!product) return null;
        return {
            group: activeGroup,
            day: productDay(product),
            product: ['qpf', 'winter'].includes(activeGroup) ? product.id : '',
        };
    }

    function productPillLabel(product) {
        if (activeGroup === 'qpf') return QPF_PRODUCT_LABELS.get(product.id) || product.label;
        return `Day ${productDay(product)}`;
    }

    function replaceProductControls() {
        const usesProductPills = PILL_GROUPS.has(activeGroup);
        productPillsWrap.hidden = !usesProductPills;
        winterDayWrap.hidden = activeGroup !== 'winter';
        productSelectWrap.hidden = activeGroup !== 'winter';

        const pillButtons = usesProductPills
            ? curatedProducts(activeGroup, catalogGroups).map((product) => {
                const button = document.createElement('button');
                button.type = 'button';
                button.dataset.wpcProduct = product.id;
                button.dataset.available = String(product.available !== false);
                button.textContent = productPillLabel(product);
                button.setAttribute('aria-pressed', String(product.id === activeProductId));
                return button;
            })
            : [];
        productPills.replaceChildren(...pillButtons);

        winterDayPills.querySelectorAll('[data-wpc-winter-day]').forEach((button) => {
            const active = Number(button.dataset.wpcWinterDay) === activeWinterDay;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });

        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = activeWinterDay ? 'Select winter product' : 'Select forecast day';
        const options = productsForActiveGroup().map((product) => {
            const option = document.createElement('option');
            option.value = product.id;
            option.textContent = product.label.replace(/\s+—\s+Day\s+\d+$/, '');
            option.disabled = product.available === false;
            return option;
        });
        productSelect.replaceChildren(placeholder, ...options);
        productSelect.value = options.some((option) => option.value === activeProductId)
            ? activeProductId
            : '';
        if (activeGroup === 'winter' && !productSelect.value) activeProductId = '';
    }

    function syncControls() {
        const enabled = isEnabled();
        const supported = supportsCurrentRegion();
        controls.hidden = !enabled;
        controls.classList.toggle('is-disabled', !enabled);
        groupPills.querySelectorAll('[data-wpc-group]').forEach((button) => {
            const active = button.dataset.wpcGroup === activeGroup;
            button.disabled = !enabled || !supported;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
        productPills.querySelectorAll('[data-wpc-product]').forEach((button) => {
            const active = button.dataset.wpcProduct === activeProductId;
            button.disabled = !enabled || !supported || button.dataset.available === 'false';
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
        winterDayPills.querySelectorAll('[data-wpc-winter-day]').forEach((button) => {
            button.disabled = !enabled || !supported;
        });
        productSelect.disabled = !enabled || !supported || activeGroup !== 'winter' || !activeWinterDay;
        opacityInput.disabled = !enabled || !supported || !hasSelection();
    }

    function showSelectionPrompt() {
        if (activeGroup === 'ero') status.setMessage('Select an Excess Rain forecast day.');
        else if (activeGroup === 'qpf') status.setMessage('Select a multi-day QPF period.');
        else if (activeGroup === 'winter' && !activeWinterDay) status.setMessage('Select a Winter forecast day.');
        else if (activeGroup === 'winter') status.setMessage(`Select a Winter product for Day ${activeWinterDay}.`);
        else status.setMessage('Select a WPC forecast family.');
    }

    async function ensureCatalog() {
        if (catalogGroups.size) return true;
        if (!catalogPromise) {
            catalogPromise = engine.loadCatalog()
                .then((catalog) => {
                    catalogGroups = new Map((catalog?.groups || [])
                        .filter((group) => GROUP_VALUES.has(group.group))
                        .map((group) => [group.group, group]));
                    replaceProductControls();
                    syncControls();
                    return true;
                })
                .catch((error) => {
                    catalogPromise = null;
                    status.setMessage(`WPC catalog failed: ${error.message}`, 'error');
                    status.setDataState?.('Catalog failed', 'error');
                    return false;
                });
        }
        return catalogPromise;
    }

    function clear({ message = '' } = {}) {
        engine.clear();
        if (message) status.setMessage(message);
    }

    async function refresh({ auto = false } = {}) {
        if (!isEnabled() || !hasSelection()) return false;
        if (!supportsCurrentRegion()) {
            status.setMessage('WPC Workspace products are available for CONUS only.', 'error');
            return false;
        }
        const nowMs = Date.now();
        if (auto && nowMs - lastAutoRefreshMs < AUTO_REFRESH_INTERVAL_MS) return false;
        lastAutoRefreshMs = nowMs;
        await engine.load(selection());
        return true;
    }

    function reset({ announce = false } = {}) {
        enabledInput.checked = false;
        activeGroup = '';
        activeProductId = '';
        activeWinterDay = 0;
        clear({ message: announce ? 'WPC layer disabled.' : '' });
        replaceProductControls();
        syncControls();
    }

    async function setRegion() {
        clear();
        syncControls();
        if (!isEnabled()) return;
        if (!supportsCurrentRegion()) {
            status.setMessage('WPC Workspace products are available for CONUS only.', 'error');
            return;
        }
        if (hasSelection()) await refresh();
    }

    enabledInput.addEventListener('change', async () => {
        if (!isEnabled()) {
            clear({ message: 'WPC layer disabled.' });
        } else if (!supportsCurrentRegion()) {
            status.setMessage('WPC Workspace products are available for CONUS only.', 'error');
        } else if (await ensureCatalog()) {
            if (hasSelection()) await refresh();
            else showSelectionPrompt();
        }
        syncControls();
    }, { signal: lifecycle.signal });

    groupPills.addEventListener('click', async (event) => {
        const button = event.target.closest('[data-wpc-group]');
        if (!button || button.disabled || button.dataset.wpcGroup === activeGroup) return;
        activeGroup = button.dataset.wpcGroup;
        activeProductId = '';
        activeWinterDay = 0;
        clear();
        if (await ensureCatalog()) {
            if (activeGroup === 'mpd') {
                activeProductId = productsForActiveGroup()[0]?.id || '';
            }
            replaceProductControls();
        }
        syncControls();
        if (hasSelection()) await refresh();
        else showSelectionPrompt();
    }, { signal: lifecycle.signal });

    productPills.addEventListener('click', (event) => {
        const button = event.target.closest('[data-wpc-product]');
        if (!button || button.disabled || button.dataset.wpcProduct === activeProductId) return;
        activeProductId = button.dataset.wpcProduct;
        clear();
        replaceProductControls();
        syncControls();
        void refresh();
    }, { signal: lifecycle.signal });

    winterDayPills.addEventListener('click', (event) => {
        const button = event.target.closest('[data-wpc-winter-day]');
        const day = Number(button?.dataset.wpcWinterDay);
        if (!button || button.disabled || day === activeWinterDay) return;
        activeWinterDay = day;
        activeProductId = '';
        clear();
        replaceProductControls();
        syncControls();
        showSelectionPrompt();
    }, { signal: lifecycle.signal });

    productSelect.addEventListener('change', () => {
        activeProductId = productSelect.value;
        clear();
        syncControls();
        if (hasSelection()) void refresh();
        else showSelectionPrompt();
    }, { signal: lifecycle.signal });

    opacityInput.addEventListener('input', () => {
        const value = Math.max(0.1, Math.min(1, Number(opacityInput.value) || 0.55));
        engine.setOpacity(value);
        opacityLabel.textContent = `WPC Opacity (${value.toFixed(2).replace(/\.?0+$/, '')})`;
    }, { signal: lifecycle.signal });

    engine.setOpacity(opacityInput.value);
    replaceProductControls();
    syncControls();

    return Object.freeze({
        refresh,
        reset,
        setRegion,
        isEnabled,
        hasSelection,
        destroy() {
            lifecycle.abort();
            engine.destroy();
        },
    });
}
