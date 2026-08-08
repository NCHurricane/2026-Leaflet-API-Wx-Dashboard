function formatTimestamp(value) {
    if (value == null || value === '') return '—';
    const date = value instanceof Date ? value : new Date(value);
    if (!Number.isFinite(date.getTime())) return '—';
    return date.toLocaleString([], {
        month: 'short', day: 'numeric', year: 'numeric',
        hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
    });
}

function formatAge(value) {
    if (value == null || value === '') return '—';
    const timestamp = new Date(value).getTime();
    if (!Number.isFinite(timestamp)) return '—';
    const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    if (hours < 48) return `${hours} hr`;
    const days = Math.floor(hours / 24);
    return `${days} day${days === 1 ? '' : 's'}`;
}

export function createStatusReporter(elements = {}) {
    const { age, globalTimestamp, message, updated, provider } = elements;
    let globalTimestampTime = null;
    let globalTimestampState = null;

    function ensureGlobalTimestamp() {
        if (!globalTimestamp) return {};
        if (!globalTimestampTime || !globalTimestampState) {
            const initialTime = globalTimestamp.textContent?.trim() || 'Last Updated: —';
            globalTimestampTime = document.createElement('span');
            globalTimestampTime.className = 'core-global-timestamp-time';
            globalTimestampTime.textContent = initialTime;
            globalTimestampState = document.createElement('span');
            globalTimestampState.className = 'core-global-timestamp-state';
            globalTimestampState.hidden = true;
            globalTimestamp.replaceChildren(globalTimestampTime, globalTimestampState);
            globalTimestamp.setAttribute('aria-live', 'polite');
        }
        return { time: globalTimestampTime, state: globalTimestampState };
    }

    function writeDataState(value, tone = '') {
        const parts = ensureGlobalTimestamp();
        if (!parts.state) return;
        parts.state.textContent = value || '';
        parts.state.hidden = !value;
        globalTimestamp.dataset.stateTone = value ? tone : '';
    }

    return Object.freeze({
        setMessage(value, tone = '') {
            if (!message) return;
            message.textContent = value || '';
            message.dataset.tone = tone;
            if (/\b(?:loading|refreshing|warming|fetching|requesting|discovering)\b/i.test(String(value || ''))) {
                writeDataState('Loading…', 'loading');
            }
        },
        setDataState(value, tone = '') {
            writeDataState(value, tone);
        },
        setDataInfo(info = {}) {
            const formatted = formatTimestamp(info.timestamp);
            if (updated) updated.textContent = formatted;
            if (age) age.textContent = formatAge(info.timestamp);
            const parts = ensureGlobalTimestamp();
            if (parts.time) parts.time.textContent = `Last Updated: ${formatted}`;
            if (provider) provider.textContent = info.provider || '—';
            if (info.updateState !== false) {
                writeDataState(
                    info.stale ? 'Stale data' : 'Ready',
                    info.stale ? 'stale' : 'fresh',
                );
            }
        },
        clear() {
            if (message) message.textContent = '';
            if (updated) updated.textContent = '—';
            if (age) age.textContent = '—';
            const parts = ensureGlobalTimestamp();
            if (parts.time) parts.time.textContent = 'Last Updated: —';
            if (parts.state) {
                parts.state.textContent = '';
                parts.state.hidden = true;
            }
            if (globalTimestamp) globalTimestamp.dataset.stateTone = '';
            if (provider) provider.textContent = '—';
        },
    });
}
