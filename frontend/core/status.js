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
    const { age, globalTimestamp, message, updated, provider, source } = elements;

    return Object.freeze({
        setMessage(value, tone = '') {
            if (!message) return;
            message.textContent = value || '';
            message.dataset.tone = tone;
        },
        setDataInfo(info = {}) {
            const formatted = formatTimestamp(info.timestamp);
            if (updated) updated.textContent = formatted;
            if (age) age.textContent = formatAge(info.timestamp);
            if (globalTimestamp) globalTimestamp.textContent = `Last Updated: ${formatted}`;
            if (provider) provider.textContent = info.provider || '—';
            if (source) source.textContent = info.source || '—';
        },
        clear() {
            if (message) message.textContent = '';
            if (updated) updated.textContent = '—';
            if (age) age.textContent = '—';
            if (globalTimestamp) globalTimestamp.textContent = 'Last Updated: —';
            if (provider) provider.textContent = '—';
            if (source) source.textContent = '—';
        },
    });
}
