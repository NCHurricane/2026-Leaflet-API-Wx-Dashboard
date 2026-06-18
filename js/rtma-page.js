(function () {
    'use strict';

    const byId = (id) => document.getElementById(id);
    let pageContext = null;

    function configureRtmaPage(context) {
        pageContext = context || null;
    }

    function activeRtmaStream() {
        return document.querySelector('.weather-rtma-stream:checked')?.value || null;
    }

    function activeRtmaProduct() {
        return document.querySelector('.weather-rtma-product:checked')?.value || null;
    }

    function activeRtmaProducts() {
        return Array.from(document.querySelectorAll('.weather-rtma-product:checked')).map((el) => el.value);
    }

    function activeRtmaRegion() {
        const selected = String(byId('weather-region')?.value || 'CONUS').toUpperCase();
        const rtmaRegions = ['CONUS', 'AK', 'HI', 'PR'];
        return rtmaRegions.includes(selected) ? selected : 'CONUS';
    }

    function rtmaLookbackHours(stream) {
        const streamMax = pageContext?.getRtmaStreamMaxHours?.(stream) ?? 24;
        const slider = document.querySelector('#rtma-animate-slider');
        const val = slider ? Number(slider.value) : streamMax;
        return Math.max(1, Math.min(Math.round(val), streamMax));
    }

    function syncProductForStream() {
        const stream = activeRtmaStream();
        const delta24h = document.querySelector('.weather-rtma-product[value="temperature_change_24h"]');
        if (!delta24h) return;
        const supported = stream === 'rtma_hourly';
        delta24h.disabled = !supported;
        const row = delta24h.closest('.rtma-product-row');
        if (row) row.style.opacity = supported ? '' : '0.55';
        if (!supported && delta24h.checked) {
            delta24h.checked = false;
            const fallback = document.querySelector('.weather-rtma-product[value="temperature"]')
                || document.querySelector('.weather-rtma-product');
            if (fallback) fallback.checked = true;
            pageContext?.setStatus?.('24-hour temp change is only available on RTMA Hourly.');
        }
    }

    function syncStreamForRegion() {
        const region = activeRtmaRegion();
        const rapid = document.querySelector('.weather-rtma-stream[value="rtma_rapid_update"]');
        const hourly = document.querySelector('.weather-rtma-stream[value="rtma_hourly"]');
        if (!rapid) return;
        const rapidSupported = region === 'CONUS';
        rapid.disabled = !rapidSupported;
        if (!rapidSupported && rapid.checked) {
            rapid.checked = false;
            if (hourly) hourly.checked = true;
            pageContext?.setStatus?.('RTMA Rapid Update is only available for CONUS.');
        }
    }

    function wireControls() {
        document.querySelectorAll('.weather-rtma-stream').forEach((el) => {
            el.addEventListener('change', (evt) => {
                if (evt.target.checked) {
                    document.querySelectorAll('.weather-rtma-stream').forEach((other) => {
                        if (other !== evt.target) other.checked = false;
                    });
                }
                if (!activeRtmaStream()) evt.target.checked = true;
                syncStreamForRegion();
                syncProductForStream();
                if (pageContext?.isTypeEnabled?.('rtma') && activeRtmaStream() && activeRtmaProduct()) {
                    pageContext.loadUnified?.();
                    return;
                }
                pageContext?.refreshActiveLayers?.();
            });
        });

        document.querySelectorAll('.weather-rtma-product').forEach((el) => {
            el.addEventListener('change', (evt) => {
                if (evt.target.checked) {
                    if (evt.target.value === 'temperature_change_24h' && activeRtmaStream() !== 'rtma_hourly') {
                        const hourly = document.querySelector('.weather-rtma-stream[value="rtma_hourly"]');
                        const rapid = document.querySelector('.weather-rtma-stream[value="rtma_rapid_update"]');
                        if (hourly) hourly.checked = true;
                        if (rapid) rapid.checked = false;
                        syncProductForStream();
                    }
                    const isWindProduct = evt.target.value === 'wind_speed' || evt.target.value === 'wind_direction';
                    document.querySelectorAll('.weather-rtma-product').forEach((other) => {
                        if (other !== evt.target) {
                            const otherIsWind = other.value === 'wind_speed' || other.value === 'wind_direction';
                            if (isWindProduct && otherIsWind) return;
                            other.checked = false;
                        }
                    });
                }
                const checkedProducts = activeRtmaProducts();
                if (!checkedProducts.length) evt.target.checked = true;
                const windProds = checkedProducts.filter((p) => p === 'wind_speed' || p === 'wind_direction');
                if (windProds.length < 2) pageContext?.clearRtmaSecondaryWind?.();
                if (pageContext?.isTypeEnabled?.('rtma') && activeRtmaStream() && activeRtmaProduct()) {
                    pageContext.loadUnified?.();
                    return;
                }
                pageContext?.refreshActiveLayers?.();
            });
        });

        const slider = document.querySelector('#rtma-animate-slider');
        if (slider) {
            slider.addEventListener('input', () => {
                const displayValue = Number(slider.value);
                const displayText = displayValue === Math.floor(displayValue)
                    ? Math.floor(displayValue) + 'H' : displayValue + 'H';
                const valueDisplay = byId('rtma-animate-slider-value');
                if (valueDisplay) valueDisplay.textContent = displayText;
            });
            slider.addEventListener('change', () => {
                if (pageContext?.isScrubMode?.()) pageContext.loadUnified?.();
            });
        }
    }

    window.NCHRtmaPage = Object.freeze({
        activeRtmaProduct,
        activeRtmaProducts,
        activeRtmaRegion,
        activeRtmaStream,
        configureRtmaPage,
        rtmaLookbackHours,
        syncProductForStream,
        syncStreamForRegion,
        wireControls,
    });

    window.NCHProductPageShell?.registerProductPageEntry('rtma', {
        label: 'RTMA',
        title: 'RTMA — NCHurricane Dashboard',
        controller: window.NCHRtmaPage,
    });
}());
