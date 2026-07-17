export function createSidebarTabs(root, options = {}) {
    if (!root) throw new Error('Sidebar tab root is required.');
    const buttons = [...root.querySelectorAll('[data-sidebar-tab]')];
    const panels = [...root.querySelectorAll('[data-sidebar-panel]')];
    let activeTab = null;

    function availableButtons() {
        return buttons.filter((button) => !button.hidden && !button.disabled);
    }

    function activate(name, { focus = false } = {}) {
        const button = buttons.find((candidate) => candidate.dataset.sidebarTab === name);
        const panel = panels.find((candidate) => candidate.dataset.sidebarPanel === name);
        if (!button || !panel || button.hidden || button.disabled) return false;

        activeTab = name;
        buttons.forEach((candidate) => {
            const selected = candidate === button;
            candidate.classList.toggle('is-active', selected);
            candidate.setAttribute('aria-selected', String(selected));
            candidate.tabIndex = selected ? 0 : -1;
        });
        panels.forEach((candidate) => {
            candidate.hidden = candidate !== panel;
        });
        if (focus) button.focus();
        root.dispatchEvent(new CustomEvent('core:sidebar-tab-change', { detail: { tab: name } }));
        return true;
    }

    function onClick(event) {
        const button = event.target.closest('[data-sidebar-tab]');
        if (button && root.contains(button)) activate(button.dataset.sidebarTab);
    }

    function onKeyDown(event) {
        const button = event.target.closest('[data-sidebar-tab]');
        if (!button || !root.contains(button)) return;
        const available = availableButtons();
        const currentIndex = available.indexOf(button);
        if (currentIndex < 0) return;
        let nextIndex = null;
        if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % available.length;
        else if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + available.length) % available.length;
        else if (event.key === 'Home') nextIndex = 0;
        else if (event.key === 'End') nextIndex = available.length - 1;
        if (nextIndex === null) return;
        event.preventDefault();
        activate(available[nextIndex].dataset.sidebarTab, { focus: true });
    }

    root.addEventListener('click', onClick);
    root.addEventListener('keydown', onKeyDown);
    const requestedDefault = options.defaultTab || 'data';
    if (!activate(requestedDefault)) {
        const first = availableButtons()[0];
        if (first) activate(first.dataset.sidebarTab);
    }

    return Object.freeze({
        activate,
        get activeTab() { return activeTab; },
        destroy() {
            root.removeEventListener('click', onClick);
            root.removeEventListener('keydown', onKeyDown);
        },
    });
}
