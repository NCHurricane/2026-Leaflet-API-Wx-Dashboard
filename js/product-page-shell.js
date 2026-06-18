(function () {
    'use strict';

    const ALL_PRODUCT_TYPES = Object.freeze([
        'current',
        'alerts',
        'radar',
        'satellite',
        'spc',
        'rtma',
        'mrms',
        'drought',
        'tropical',
    ]);

    const STANDALONE_PRODUCT_BY_PATH = Object.freeze({
        '/tropical': 'tropical',
        '/alerts': 'alerts',
        '/spc': 'spc',
        '/surface': 'current',
        '/drought': 'drought',
        '/satellite': 'satellite',
        '/radar': 'radar',
        '/mrms': 'mrms',
        '/rtma': 'rtma',
    });

    const productPageEntries = new Map();

    function normalizedPath() {
        return window.location.pathname.replace(/\/$/, '');
    }

    function standaloneProductType() {
        return STANDALONE_PRODUCT_BY_PATH[normalizedPath()] || null;
    }

    function isStandaloneProductPage(type = standaloneProductType()) {
        return !!type;
    }

    function registerProductPageEntry(productType, config = {}) {
        if (!productType) return null;
        const entry = Object.freeze({
            productType,
            ...config,
        });
        productPageEntries.set(productType, entry);
        return entry;
    }

    function productPageEntry(productType = standaloneProductType()) {
        if (!productType) return null;
        return productPageEntries.get(productType) || null;
    }

    function configureStandaloneProductPage(options = {}) {
        const productType = standaloneProductType();
        if (!productType) return null;

        const {
            allTypes = ALL_PRODUCT_TYPES,
            labels = {},
            bodyClass = 'wx-standalone-product',
            getElementById = (id) => document.getElementById(id),
            querySelectorAll = (sel) => document.querySelectorAll(sel),
        } = options;
        const entry = productPageEntry(productType);
        const productLabel = entry?.label || labels[productType] || 'Weather';

        document.body.classList.add(bodyClass);
        document.title = entry?.title || `${productLabel} — NCHurricane Dashboard`;

        allTypes.forEach((type) => {
            const el = getElementById(`weather-type-${type}`);
            if (!el) return;
            el.defaultChecked = type === productType;
            el.checked = el.defaultChecked;
            el.disabled = type !== productType;
        });

        // Highlight active product in navigation bar
        const navLinks = querySelectorAll('.product-nav-link');
        navLinks.forEach((link) => {
            const linkProduct = link.getAttribute('data-product');
            if (linkProduct === productType) {
                link.classList.add('is-active');
            } else {
                link.classList.remove('is-active');
            }
        });

        return productType;
    }

    window.NCHProductPageShell = Object.freeze({
        ALL_PRODUCT_TYPES,
        STANDALONE_PRODUCT_BY_PATH,
        configureStandaloneProductPage,
        isStandaloneProductPage,
        productPageEntry,
        registerProductPageEntry,
        standaloneProductType,
    });
}());
