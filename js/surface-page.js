(function () {
    'use strict';

    let pageContext = null;
    let archiveProduct = 'temperature';

    function configureSurfacePage(context) {
        pageContext = context || null;
    }

    function activeSurfaceProduct() {
        return document.querySelector('.weather-surface-product:checked')?.value || null;
    }

    function activeSurfaceGradient() {
        const product = activeSurfaceProduct();
        if (!product) return false;
        const grad = document.querySelector(`.weather-surface-gradient[data-product="${product}"]`);
        return !!grad?.checked;
    }

    function renderArchiveFrame(frame) {
        const stations = frame?.stations || [];
        pageContext?.setSurfaceStations?.(stations);
        pageContext?.renderSurfaceMarkers?.(stations);

        const product = frame?.product || archiveProduct;
        pageContext?.buildSurfaceLegend?.(product, frame?.unit);
    }

    function setArchiveProduct(product) {
        archiveProduct = product || 'temperature';
    }

    function wireControls() {
        document.querySelectorAll('.weather-surface-product').forEach((el) => {
            el.addEventListener('change', (evt) => {
                if (evt.target.checked) {
                    document.querySelectorAll('.weather-surface-product').forEach((other) => {
                        if (other !== evt.target) {
                            other.checked = false;
                            const grad = document.querySelector(`.weather-surface-gradient[data-product="${other.value}"]`);
                            if (grad) grad.checked = false;
                        }
                    });
                }
                pageContext?.updateGradientBlurVisibility?.();
                if (!pageContext?.isTypeEnabled?.('current')) return;
                const product = activeSurfaceProduct();
                const region = pageContext?.getRegionValue?.();
                if (product && region) pageContext.loadSurface?.(region, product);
            });
        });

        document.querySelectorAll('.weather-surface-gradient').forEach((el) => {
            el.addEventListener('change', () => {
                pageContext?.updateGradientBlurVisibility?.();
                if (!pageContext?.isTypeEnabled?.('current')) return;
                pageContext.applyGradientChange?.();
            });
        });
    }

    window.NCHSurfacePage = Object.freeze({
        activeSurfaceGradient,
        activeSurfaceProduct,
        configureSurfacePage,
        renderArchiveFrame,
        setArchiveProduct,
        wireControls,
    });

    window.NCHProductPageShell?.registerProductPageEntry('surface', {
        label: 'Surface',
        title: 'Surface — NCHurricane Dashboard',
        controller: window.NCHSurfacePage,
    });
}());
