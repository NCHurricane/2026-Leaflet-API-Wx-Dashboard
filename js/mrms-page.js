(function () {
    'use strict';

    const byId = (id) => document.getElementById(id);
    let pageContext = null;
    const SUBTAB_BY_PRODUCT = Object.freeze({
        PrecipFlag: 'precip',
        PrecipRate: 'precip',
        QPE: 'precip',
        Reflectivity: 'reflectivity',
        EchoTop: 'reflectivity',
        VIL: 'reflectivity',
        RotationTrack: 'storm',
        AzShear: 'storm',
        MESH: 'hail',
        SHI: 'hail',
        POSH: 'hail',
        Lightning: 'hail',
        Model: 'environment',
        RadarQualityIndex: 'environment',
    });

    function configureMrmsPage(context) {
        pageContext = context || null;
    }

    function activeMrmsProduct() {
        return document.querySelector('.mrms-product-check:checked')?.value || null;
    }

    function composeMrmsProductKey() {
        const family = activeMrmsProduct();
        if (!family) return null;
        const standalone = ['PrecipRate', 'PrecipFlag', 'SHI', 'POSH', 'RadarQualityIndex'];
        if (standalone.includes(family)) return family;

        if (family === 'QPE') {
            const src = document.querySelector('input[name="mrms-qpe-source"]:checked')?.value || 'MS2';
            const per = document.querySelector('input[name="mrms-qpe-period"]:checked')?.value || '01H';
            return `QPE_${src}_${per}`;
        }
        if (family === 'RotationTrack') {
            const lvl = document.querySelector('input[name="mrms-rotation-level"]:checked')?.value || 'LL';
            const time = document.querySelector('input[name="mrms-rotation-time"]:checked')?.value || '60min';
            return `RotationTrack_${lvl}_${time}`;
        }
        if (family === 'MESH') {
            const t = document.querySelector('input[name="mrms-mesh-time"]:checked')?.value || 'Instant';
            return t === 'Instant' ? 'MESH_Instant' : `MESH_${t}`;
        }
        if (family === 'AzShear') {
            const lvl = document.querySelector('input[name="mrms-azshear-level"]:checked')?.value || 'Low';
            return `AzShear_${lvl}`;
        }
        if (family === 'EchoTop') {
            const thr = document.querySelector('input[name="mrms-echotop-threshold"]:checked')?.value || '18';
            return `EchoTop_${thr}`;
        }
        if (family === 'VIL') {
            const t = document.querySelector('input[name="mrms-vil-type"]:checked')?.value || 'Instant';
            return `VIL_${t}`;
        }
        if (family === 'Reflectivity') {
            const v = document.querySelector('input[name="mrms-refl-variant"]:checked')?.value || 'HSR';
            return `Refl_${v}`;
        }
        if (family === 'Lightning') {
            const w = document.querySelector('input[name="mrms-lightning-window"]:checked')?.value || '30min';
            return `Lightning_${w}`;
        }
        if (family === 'Model') {
            const f = document.querySelector('input[name="mrms-model-field"]:checked')?.value || 'FreezingLevel';
            return `Model_${f}`;
        }
        return family;
    }

    function mrmsLookbackHours() {
        const slider = byId('mrms-animate-slider');
        return Math.max(1, Math.round(slider ? Number(slider.value) : 1));
    }

    function setSubtab(tabKey) {
        const buttons = Array.from(document.querySelectorAll('.mrms-subtab-button'));
        const panels = Array.from(document.querySelectorAll('.mrms-subtab-panel'));
        if (!buttons.length || !panels.length) return;

        const selectedKey = buttons.some((button) => button.dataset.mrmsSubtab === tabKey)
            ? tabKey
            : 'precip';

        buttons.forEach((button) => {
            const isSelected = button.dataset.mrmsSubtab === selectedKey;
            button.setAttribute('aria-selected', isSelected ? 'true' : 'false');
            button.tabIndex = isSelected ? 0 : -1;
        });

        panels.forEach((panel) => {
            panel.classList.toggle('is-active', panel.dataset.mrmsPanel === selectedKey);
        });
    }

    function syncSubtabForProduct(family = activeMrmsProduct()) {
        setSubtab(SUBTAB_BY_PRODUCT[family] || 'precip');
    }

    function updateSubControls() {
        const family = activeMrmsProduct();
        document.querySelectorAll('.mrms-sub-panel').forEach((element) => {
            element.style.display = 'none';
        });
        if (!family) return;

        syncSubtabForProduct(family);
        const subPanelByProduct = {
            QPE: 'mrms-sub-qpe',
            RotationTrack: 'mrms-sub-rotation',
            MESH: 'mrms-sub-mesh',
            AzShear: 'mrms-sub-azshear',
            EchoTop: 'mrms-sub-echotop',
            VIL: 'mrms-sub-vil',
            Reflectivity: 'mrms-sub-reflectivity',
            Lightning: 'mrms-sub-lightning',
            Model: 'mrms-sub-model',
        };
        const subPanel = byId(subPanelByProduct[family]);
        if (subPanel) subPanel.style.display = '';
    }

    function renderArchiveFrame(frame) {
        if (!frame?.image_url || !Array.isArray(frame.bounds) || frame.bounds.length < 4) return;

        const bounds = frame.bounds;
        const leafletBounds = [[bounds[2], bounds[0]], [bounds[3], bounds[1]]];
        const overlay = pageContext?.getOverlay?.();
        if (overlay) {
            overlay.setBounds(leafletBounds);
            overlay.setUrl(pageContext.apiUrl(frame.image_url));
            return;
        }

        const newOverlay = pageContext?.leaflet?.imageOverlay(
            pageContext.apiUrl(frame.image_url),
            leafletBounds,
            { opacity: pageContext.getOpacity() },
        );
        if (!newOverlay) return;
        newOverlay.addTo(pageContext.map);
        pageContext.setOverlay(newOverlay);
    }

    function wireControls() {
        document.querySelectorAll('.mrms-product-check').forEach((cb) => {
            cb.addEventListener('change', () => {
                if (cb.checked) {
                    document.querySelectorAll('.mrms-product-check').forEach((other) => {
                        if (other !== cb) other.checked = false;
                    });
                }
                updateSubControls();
                if (!pageContext?.isTypeEnabled?.('mrms')) return;
                if (!activeMrmsProduct()) {
                    pageContext?.exitMrmsScrubMode?.();
                    pageContext?.refreshActiveLayers?.();
                    return;
                }
                pageContext.loadScrubberFrames?.();
            });
        });

        [
            'mrms-qpe-source', 'mrms-qpe-period',
            'mrms-rotation-level', 'mrms-rotation-time',
            'mrms-mesh-time',
            'mrms-azshear-level',
            'mrms-echotop-threshold',
            'mrms-vil-type',
            'mrms-refl-variant',
            'mrms-lightning-window',
            'mrms-model-field',
        ].forEach((name) => {
            document.querySelectorAll(`input[name="${name}"]`).forEach((el) => {
                el.addEventListener('change', () => {
                    if (!pageContext?.isTypeEnabled?.('mrms')) return;
                    if (pageContext?.isScrubMode?.()) {
                        pageContext.loadScrubberFrames?.();
                    } else {
                        pageContext.loadMrms?.();
                    }
                });
            });
        });

        const slider = byId('mrms-animate-slider');
        if (slider) {
            slider.addEventListener('input', () => {
                const displayValue = Number(slider.value);
                const displayText = displayValue === Math.floor(displayValue)
                    ? Math.floor(displayValue) + 'H' : displayValue + 'H';
                const valueDisplay = byId('mrms-animate-slider-value');
                if (valueDisplay) valueDisplay.textContent = displayText;
            });
            slider.addEventListener('change', () => {
                if (!pageContext?.isTypeEnabled?.('mrms') || !activeMrmsProduct()) return;
                pageContext.loadScrubberFrames?.();
            });
        }

        const subtabButtons = Array.from(document.querySelectorAll('.mrms-subtab-button'));
        subtabButtons.forEach((button, index) => {
            button.addEventListener('click', () => {
                setSubtab(button.dataset.mrmsSubtab || 'precip');
            });
            button.addEventListener('keydown', (event) => {
                if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                event.preventDefault();

                let nextIndex = index;
                if (event.key === 'ArrowLeft') {
                    nextIndex = index === 0 ? subtabButtons.length - 1 : index - 1;
                }
                if (event.key === 'ArrowRight') {
                    nextIndex = index === subtabButtons.length - 1 ? 0 : index + 1;
                }
                if (event.key === 'Home') nextIndex = 0;
                if (event.key === 'End') nextIndex = subtabButtons.length - 1;

                const nextButton = subtabButtons[nextIndex];
                if (!nextButton) return;
                setSubtab(nextButton.dataset.mrmsSubtab || 'precip');
                nextButton.focus();
            });
        });

        syncSubtabForProduct();
        updateSubControls();
    }

    window.NCHMrmsPage = Object.freeze({
        activeMrmsProduct,
        composeMrmsProductKey,
        configureMrmsPage,
        mrmsLookbackHours,
        renderArchiveFrame,
        updateSubControls,
        wireControls,
    });

    window.NCHProductPageShell?.registerProductPageEntry('mrms', {
        label: 'MRMS',
        title: 'MRMS — NCHurricane Dashboard',
        controller: window.NCHMrmsPage,
    });
}());
