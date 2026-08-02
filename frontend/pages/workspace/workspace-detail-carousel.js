export function createWorkspaceDetailCarousel(host, mapCore, { zoomToFeature } = {}) {
    const map = mapCore.map;
    let panel = null;
    let pages = [];
    let activeIndex = 0;
    let touchStartX = null;

    function close() {
        if (!panel) return;
        document.removeEventListener('keydown', onKeyDown);
        map.off('click', close);
        panel.remove();
        panel = null;
        pages = [];
        activeIndex = 0;
        touchStartX = null;
    }

    function normalizedIndex(index) {
        if (!pages.length) return 0;
        return (index + pages.length) % pages.length;
    }

    function showPage(index) {
        if (!panel || !pages.length) return;
        activeIndex = normalizedIndex(index);
        panel.querySelectorAll('[data-workspace-context-page]').forEach((page, pageIndex) => {
            page.hidden = pageIndex !== activeIndex;
        });
        panel.querySelectorAll('[data-workspace-context-dot]').forEach((dot, pageIndex) => {
            const selected = pageIndex === activeIndex;
            dot.classList.toggle('is-active', selected);
            dot.setAttribute('aria-selected', String(selected));
            dot.tabIndex = selected ? 0 : -1;
        });
        const status = panel.querySelector('[data-workspace-context-status]');
        if (status) status.textContent = `Page ${activeIndex + 1} of ${pages.length}: ${pages[activeIndex].label}`;
    }

    function onKeyDown(event) {
        if (!panel) return;
        if (event.key === 'Escape') {
            close();
            return;
        }
        if (pages.length < 2 || !panel.contains(event.target)
            || event.target.closest?.('input, select, textarea, a, button:not([data-workspace-context-dot])')) return;
        if (event.key === 'ArrowLeft') {
            event.preventDefault();
            showPage(activeIndex - 1);
        }
        if (event.key === 'ArrowRight') {
            event.preventDefault();
            showPage(activeIndex + 1);
        }
    }

    function positionPanel(latlng) {
        let preferRight = true;
        try {
            const point = map.latLngToContainerPoint(latlng);
            preferRight = point.x < (host.getBoundingClientRect().width / 2);
        } catch (_) { /* retain right-side default */ }
        panel.classList.toggle('is-right', preferRight);
        panel.classList.toggle('is-left', !preferRight);
    }

    function open(latlng, nextPages) {
        const validPages = (nextPages || []).filter((page) => page?.html && page?.feature);
        if (!latlng || !validPages.length) return;
        close();
        pages = validPages;
        panel = document.createElement('div');
        panel.className = 'spc-detail workspace-context-carousel';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-label', 'Workspace feature details');
        panel.tabIndex = -1;

        const views = document.createElement('div');
        views.className = 'workspace-context-views';
        pages.forEach((page, index) => {
            const view = document.createElement('section');
            view.className = 'workspace-context-page';
            view.dataset.workspaceContextPage = String(index);
            view.setAttribute('aria-label', page.label);
            view.hidden = index !== 0;
            view.innerHTML = page.html;
            page.wire?.(view, {
                close,
                zoom: () => { if (page.feature) zoomToFeature?.(page.feature); },
            });
            views.appendChild(view);
        });
        panel.appendChild(views);

        if (pages.length > 1) {
            const navigation = document.createElement('div');
            navigation.className = 'workspace-context-navigation';
            navigation.innerHTML = `
                <button type="button" class="workspace-context-arrow" data-workspace-context-direction="previous" aria-label="Previous detail page"><i class="fas fa-chevron-left" aria-hidden="true"></i></button>
                <div class="workspace-context-dots" role="tablist" aria-label="Feature detail pages"></div>
                <button type="button" class="workspace-context-arrow" data-workspace-context-direction="next" aria-label="Next detail page"><i class="fas fa-chevron-right" aria-hidden="true"></i></button>
                <span class="core-visually-hidden" data-workspace-context-status aria-live="polite"></span>`;
            const dots = navigation.querySelector('.workspace-context-dots');
            pages.forEach((page, index) => {
                const dot = document.createElement('button');
                dot.type = 'button';
                dot.className = 'workspace-context-dot';
                dot.dataset.workspaceContextDot = String(index);
                dot.setAttribute('role', 'tab');
                dot.setAttribute('aria-label', page.label);
                dot.addEventListener('click', () => showPage(index));
                dots.appendChild(dot);
            });
            navigation.querySelector('[data-workspace-context-direction="previous"]')
                .addEventListener('click', () => showPage(activeIndex - 1));
            navigation.querySelector('[data-workspace-context-direction="next"]')
                .addEventListener('click', () => showPage(activeIndex + 1));
            panel.appendChild(navigation);
        }

        ['pointerdown', 'dblclick', 'wheel'].forEach((type) => {
            panel.addEventListener(type, (event) => event.stopPropagation());
        });
        panel.addEventListener('touchstart', (event) => {
            touchStartX = event.touches[0]?.clientX ?? null;
        }, { passive: true });
        panel.addEventListener('touchend', (event) => {
            if (touchStartX == null || pages.length < 2) return;
            const endX = event.changedTouches[0]?.clientX ?? touchStartX;
            const delta = endX - touchStartX;
            touchStartX = null;
            if (Math.abs(delta) >= 40) showPage(activeIndex + (delta < 0 ? 1 : -1));
        }, { passive: true });

        host.appendChild(panel);
        positionPanel(latlng);
        showPage(0);
        panel.focus({ preventScroll: true });
        document.addEventListener('keydown', onKeyDown);
        setTimeout(() => { if (panel) map.on('click', close); }, 0);
    }

    return Object.freeze({ close, destroy: close, open });
}
