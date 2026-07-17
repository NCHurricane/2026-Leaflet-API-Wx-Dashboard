const ALIGNMENTS = new Set(['left', 'center', 'right']);

export function createLegendHost(root, options = {}) {
    if (!root) throw new Error('Legend root is required.');
    root.classList.add('core-map-legend');

    function setAlign(value) {
        const alignment = ALIGNMENTS.has(value) ? value : 'left';
        root.dataset.legendAlign = alignment;
        return alignment;
    }

    function syncCollapseButton() {
        const header = root.querySelector('.core-legend-header');
        if (!header) return;
        let button = header.querySelector('[data-legend-collapse]');
        if (!button) {
            button = document.createElement('button');
            button.type = 'button';
            button.className = 'core-legend-collapse';
            button.dataset.legendCollapse = '';
            button.innerHTML = '<i class="fas fa-chevron-down" aria-hidden="true"></i>';
            header.appendChild(button);
        }
        const collapsed = root.classList.contains('is-collapsed');
        button.setAttribute('aria-expanded', String(!collapsed));
        button.setAttribute('aria-label', collapsed ? 'Expand legend' : 'Collapse legend');
        button.title = collapsed ? 'Expand legend' : 'Collapse legend';
    }

    function setCollapsed(value) {
        root.classList.toggle('is-collapsed', !!value);
        syncCollapseButton();
    }

    function onClick(event) {
        const button = event.target.closest('[data-legend-collapse]');
        if (!button || !root.contains(button)) return;
        setCollapsed(!root.classList.contains('is-collapsed'));
    }

    root.addEventListener('click', onClick);
    setAlign(options.align || root.dataset.legendAlign || 'left');
    setCollapsed(options.collapsed === true);

    return Object.freeze({
        clear() {
            root.replaceChildren();
            root.hidden = true;
        },
        setHtml(html) {
            root.innerHTML = html || '';
            root.hidden = !html;
            syncCollapseButton();
        },
        setAlign,
        setCollapsed,
        destroy() {
            root.removeEventListener('click', onClick);
        },
    });
}
