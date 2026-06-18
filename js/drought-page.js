(function () {
    'use strict';

    const byId = (id) => document.getElementById(id);
    let pageContext = null;

    function configureDroughtPage(context) {
        pageContext = context || null;
    }

    function activeDroughtCategories() {
        return Array.from(document.querySelectorAll('.drought-cat-check'))
            .filter((el) => el.checked)
            .map((el) => Number(el.value));
    }

    function activeDroughtRegionState() {
        const code = String(byId('weather-region')?.value || '').toUpperCase();
        return /^[A-Z]{2}$/.test(code) ? code : null;
    }

    function wireControls() {
        document.querySelectorAll('.drought-cat-check').forEach((el) => {
            el.addEventListener('change', () => {
                if (!pageContext?.isTypeEnabled?.('drought')) return;
                pageContext.applyDroughtFilter?.();
            });
        });
    }

    window.NCHDroughtPage = Object.freeze({
        activeDroughtCategories,
        activeDroughtRegionState,
        configureDroughtPage,
        wireControls,
    });

    window.NCHProductPageShell?.registerProductPageEntry('drought', {
        label: 'Drought',
        title: 'Drought — NCHurricane Dashboard',
        controller: window.NCHDroughtPage,
    });
}());
