// Shared frame scrubber component (promoted from pages/wpc in Phase 22).
// Per-page instances only — no global modes. Pages own the container element
// and the frame objects ({label, ...}); onFrame receives (frame, index).

const SPEED_STEPS = [0.5, 1, 2, 4, 6, 8];
const BASE_INTERVAL_MS = 1000;
const LOOP_HOLD_MULTIPLIER = 2;

export function createScrubber(containerEl, options = {}) {
    const onFrame = options.onFrame || (() => {});
    const holdAtEnd = options.holdAtEnd === true;

    let frames = [];
    let currentIndex = 0;
    let playing = false;
    let playTimer = null;
    let speedIndex = 1;

    containerEl.innerHTML = [
        '<div class="nch-scrubber">',
        '  <div class="nch-scrubber-controls">',
        '    <button class="nch-scrubber-btn" data-scrub="back" title="Previous frame">&#9664;</button>',
        '    <button class="nch-scrubber-btn" data-scrub="play" title="Play/Pause">&#9654;</button>',
        '    <button class="nch-scrubber-btn" data-scrub="fwd" title="Next frame">&#9654;&#9654;</button>',
        '    <div class="nch-scrubber-speed">',
        '      <button class="nch-scrubber-btn nch-scrubber-speed-btn" data-scrub="slower" title="Slower">&minus;</button>',
        '      <span class="nch-scrubber-speed-label">1x</span>',
        '      <button class="nch-scrubber-btn nch-scrubber-speed-btn" data-scrub="faster" title="Faster">+</button>',
        '    </div>',
        '  </div>',
        '  <input class="nch-scrubber-slider" type="range" min="0" max="0" value="0" step="1">',
        '  <div class="nch-scrubber-info">',
        '    <span class="nch-scrubber-timestamp">--</span>',
        '    <span class="nch-scrubber-frame-count"></span>',
        '  </div>',
        '</div>',
    ].join('');

    const els = {
        play: containerEl.querySelector('[data-scrub="play"]'),
        back: containerEl.querySelector('[data-scrub="back"]'),
        fwd: containerEl.querySelector('[data-scrub="fwd"]'),
        slower: containerEl.querySelector('[data-scrub="slower"]'),
        faster: containerEl.querySelector('[data-scrub="faster"]'),
        speedLabel: containerEl.querySelector('.nch-scrubber-speed-label'),
        slider: containerEl.querySelector('.nch-scrubber-slider'),
        timestamp: containerEl.querySelector('.nch-scrubber-timestamp'),
        frameCount: containerEl.querySelector('.nch-scrubber-frame-count'),
    };

    function interval() {
        return Math.round(BASE_INTERVAL_MS / SPEED_STEPS[speedIndex]);
    }

    function updateUI() {
        const count = frames.length;
        els.slider.max = Math.max(0, count - 1);
        els.slider.value = currentIndex;
        els.frameCount.textContent = count ? `${currentIndex + 1} / ${count}` : '';
        els.timestamp.textContent = count ? (frames[currentIndex].label || '--') : '--';
        els.play.textContent = playing ? '⏸' : '▶';
    }

    function goTo(index) {
        if (!frames.length) return;
        currentIndex = Math.max(0, Math.min(frames.length - 1, index));
        updateUI();
        onFrame(frames[currentIndex], currentIndex);
    }

    function stopPlay() {
        if (playTimer) { clearTimeout(playTimer); playTimer = null; }
        playing = false;
        if (els.play) els.play.textContent = '▶';
    }

    function tick() {
        if (!playing || !frames.length) return;
        const next = currentIndex + 1;
        if (next >= frames.length) {
            goTo(0);
            playTimer = setTimeout(tick, holdAtEnd ? interval() : interval() * LOOP_HOLD_MULTIPLIER);
        } else {
            goTo(next);
            const delay = holdAtEnd && next === frames.length - 1
                ? interval() * LOOP_HOLD_MULTIPLIER
                : interval();
            playTimer = setTimeout(tick, delay);
        }
    }

    function startPlay() {
        if (playing || frames.length < 2) return;
        playing = true;
        if (els.play) els.play.textContent = '⏸';
        playTimer = setTimeout(tick, interval());
    }

    els.play.addEventListener('click', () => { if (playing) stopPlay(); else startPlay(); });
    els.back.addEventListener('click', () => { stopPlay(); goTo(currentIndex - 1); });
    els.fwd.addEventListener('click', () => { stopPlay(); goTo(currentIndex + 1); });
    els.slower.addEventListener('click', () => {
        speedIndex = Math.max(0, speedIndex - 1);
        els.speedLabel.textContent = `${SPEED_STEPS[speedIndex]}x`;
    });
    els.faster.addEventListener('click', () => {
        speedIndex = Math.min(SPEED_STEPS.length - 1, speedIndex + 1);
        els.speedLabel.textContent = `${SPEED_STEPS[speedIndex]}x`;
    });
    els.slider.addEventListener('input', () => {
        stopPlay();
        goTo(Number(els.slider.value));
    });

    return Object.freeze({
        setFrames(newFrames, options = {}) {
            const { index = 0, silent = false, keepPlaying = false } = options;
            if (!keepPlaying) stopPlay();
            frames = Array.isArray(newFrames) ? newFrames : [];
            currentIndex = Math.max(0, Math.min(frames.length - 1, index));
            updateUI();
            if (frames.length && !silent) onFrame(frames[currentIndex], currentIndex);
        },
        getIndex() {
            return currentIndex;
        },
        isPlaying() {
            return playing;
        },
        goTo,
        play: startPlay,
        pause: stopPlay,
        destroy() { stopPlay(); containerEl.innerHTML = ''; },
    });
}
