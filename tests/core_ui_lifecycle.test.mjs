import assert from 'node:assert/strict';
import test from 'node:test';

import { createLegendHost } from '../frontend/core/legend.js';
import { createScrubber } from '../frontend/core/scrubber.js';

class FakeClassList {
    constructor() { this.values = new Set(); }
    add(value) { this.values.add(value); }
    contains(value) { return this.values.has(value); }
    toggle(value, force) {
        const enabled = force === undefined ? !this.values.has(value) : !!force;
        if (enabled) this.values.add(value);
        else this.values.delete(value);
        return enabled;
    }
}

class FakeButton {
    constructor() {
        this.attributes = new Map();
        this.className = '';
        this.dataset = {};
        this.innerHTML = '';
        this.textContent = '';
        this.title = '';
        this.type = '';
        this.listeners = new Map();
    }
    addEventListener(event, handler) { this.listeners.set(event, handler); }
    setAttribute(name, value) { this.attributes.set(name, String(value)); }
    getAttribute(name) { return this.attributes.get(name); }
    closest(selector) {
        return selector === '[data-legend-collapse]' && 'legendCollapse' in this.dataset
            ? this : null;
    }
    dispatch(event) { this.listeners.get(event)?.({ target: this }); }
}

class FakeLegendHeader {
    constructor(root) {
        this.root = root;
        this.button = null;
    }
    querySelector(selector) {
        return selector === '[data-legend-collapse]' ? this.button : null;
    }
    appendChild(button) {
        this.button = button;
        this.root.nodes.add(button);
    }
}

class FakeLegendRoot {
    constructor() {
        this.classList = new FakeClassList();
        this.dataset = {};
        this.hidden = false;
        this.listeners = new Map();
        this.nodes = new Set();
        this.header = null;
        this._html = '';
    }
    set innerHTML(value) {
        this._html = String(value);
        this.nodes.clear();
        this.header = this._html.includes('core-legend-header')
            ? new FakeLegendHeader(this) : null;
    }
    get innerHTML() { return this._html; }
    addEventListener(event, handler) { this.listeners.set(event, handler); }
    removeEventListener(event, handler) {
        if (this.listeners.get(event) === handler) this.listeners.delete(event);
    }
    querySelector(selector) {
        return selector === '.core-legend-header' ? this.header : null;
    }
    contains(node) { return this.nodes.has(node); }
    replaceChildren() {
        this.innerHTML = '';
    }
    click(target) { this.listeners.get('click')?.({ target }); }
}

class FakeScrubberContainer {
    constructor() {
        this.elements = new Map();
        this._html = '';
    }
    set innerHTML(value) {
        this._html = String(value);
        this.elements.clear();
        if (!this._html) return;
        const add = (selector) => {
            const element = new FakeButton();
            this.elements.set(selector, element);
            return element;
        };
        add('[data-scrub="play"]');
        add('[data-scrub="back"]');
        add('[data-scrub="fwd"]');
        add('[data-scrub="slower"]');
        add('[data-scrub="faster"]');
        add('.nch-scrubber-speed-label');
        add('.nch-scrubber-slider');
        add('.nch-scrubber-timestamp');
        add('.nch-scrubber-frame-count');
    }
    get innerHTML() { return this._html; }
    querySelector(selector) { return this.elements.get(selector) || null; }
}

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

function useFakeTimers() {
    const originalSetTimeout = globalThis.setTimeout;
    const originalClearTimeout = globalThis.clearTimeout;
    let nextId = 1;
    const timers = new Map();
    globalThis.setTimeout = (callback, delay) => {
        const id = nextId;
        nextId += 1;
        timers.set(id, { callback, delay });
        return id;
    };
    globalThis.clearTimeout = (id) => timers.delete(id);
    return {
        timers,
        async fireNext() {
            const entry = timers.entries().next().value;
            assert.ok(entry, 'expected a pending timer');
            const [id, timer] = entry;
            timers.delete(id);
            await timer.callback();
            return timer.delay;
        },
        restore() {
            globalThis.setTimeout = originalSetTimeout;
            globalThis.clearTimeout = originalClearTimeout;
        },
    };
}

globalThis.document = { createElement: () => new FakeButton() };

test('Shared legend owns alignment, collapse state, content, and click teardown', () => {
    const root = new FakeLegendRoot();
    const legend = createLegendHost(root, { align: 'right', collapsed: true });

    assert.equal(root.classList.contains('core-map-legend'), true);
    assert.equal(root.dataset.legendAlign, 'right');
    assert.equal(root.classList.contains('is-collapsed'), true);

    legend.setHtml('<div class="core-legend-header"></div><div class="core-legend-body">Data</div>');
    const button = root.header.button;
    assert.equal(root.hidden, false);
    assert.equal(button.getAttribute('aria-expanded'), 'false');
    assert.equal(button.getAttribute('aria-label'), 'Expand legend');

    root.click(button);
    assert.equal(root.classList.contains('is-collapsed'), false);
    assert.equal(button.getAttribute('aria-expanded'), 'true');
    assert.equal(button.getAttribute('aria-label'), 'Collapse legend');
    assert.equal(legend.setAlign('unsupported'), 'left');
    assert.equal(root.dataset.legendAlign, 'left');

    legend.destroy();
    root.click(button);
    assert.equal(root.classList.contains('is-collapsed'), false);

    legend.clear();
    assert.equal(root.hidden, true);
    assert.equal(root.innerHTML, '');
});

test('Shared scrubber plays frames and holds on the newest frame before looping', async () => {
    const clock = useFakeTimers();
    try {
        const container = new FakeScrubberContainer();
        const seen = [];
        const playing = [];
        const scrubber = createScrubber(container, {
            holdAtEnd: true,
            onFrame: (frame, index) => seen.push([frame.label, index]),
            onPlayingChange: (value) => playing.push(value),
        });
        scrubber.setFrames([{ label: 'A' }, { label: 'B' }, { label: 'C' }]);
        scrubber.play();

        assert.equal(await clock.fireNext(), 1000);
        assert.equal(await clock.fireNext(), 1000);
        assert.equal([...clock.timers.values()][0].delay, 2000);
        assert.equal(await clock.fireNext(), 2000);

        assert.deepEqual(seen, [['A', 0], ['B', 1], ['C', 2], ['A', 0]]);
        assert.equal(scrubber.getIndex(), 0);
        assert.equal(scrubber.isPlaying(), true);

        scrubber.pause();
        assert.equal(clock.timers.size, 0);
        assert.deepEqual(playing, [true, false]);
        scrubber.destroy();
        assert.equal(container.innerHTML, '');
    } finally {
        clock.restore();
    }
});

test('Shared scrubber teardown cancels playback while an async frame is pending', async () => {
    const clock = useFakeTimers();
    try {
        const container = new FakeScrubberContainer();
        const pendingFrame = deferred();
        const seen = [];
        const scrubber = createScrubber(container, {
            awaitFrameOnPlay: true,
            onFrame(frame) {
                seen.push(frame.label);
                return frame.label === 'B' ? pendingFrame.promise : undefined;
            },
        });
        scrubber.setFrames([{ label: 'A' }, { label: 'B' }]);
        scrubber.play();

        const tick = clock.fireNext();
        await Promise.resolve();
        assert.deepEqual(seen, ['A', 'B']);
        scrubber.destroy();
        pendingFrame.resolve();
        await tick;

        assert.equal(scrubber.isPlaying(), false);
        assert.equal(clock.timers.size, 0);
        assert.equal(container.innerHTML, '');
        assert.deepEqual(seen, ['A', 'B']);
    } finally {
        clock.restore();
    }
});

test('Shared scrubber coalesces drag input to the resting frame', async () => {
    const clock = useFakeTimers();
    try {
        const container = new FakeScrubberContainer();
        const seen = [];
        const scrubber = createScrubber(container, {
            scrubDebounceMs: 160,
            onFrame: (frame, index) => seen.push([frame.label, index]),
        });
        scrubber.setFrames(
            [{ label: 'A' }, { label: 'B' }, { label: 'C' }],
            { silent: true },
        );
        const slider = container.querySelector('.nch-scrubber-slider');

        slider.value = 1;
        slider.dispatch('input');
        slider.value = 2;
        slider.dispatch('input');

        assert.equal(clock.timers.size, 1);
        assert.deepEqual(seen, []);
        assert.equal(await clock.fireNext(), 160);
        assert.deepEqual(seen, [['C', 2]]);

        slider.value = 1;
        slider.dispatch('input');
        slider.dispatch('change');
        assert.equal(clock.timers.size, 0);
        assert.deepEqual(seen, [['C', 2], ['B', 1]]);
        scrubber.destroy();
    } finally {
        clock.restore();
    }
});
