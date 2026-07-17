const API_DEV_ORIGIN = 'http://127.0.0.1:8000';

function resolveApiOrigin() {
    if (window.location.protocol === 'file:') return API_DEV_ORIGIN;
    const localHosts = new Set(['localhost', '127.0.0.1', '[::1]']);
    return localHosts.has(window.location.hostname) && window.location.port !== '8000'
        ? API_DEV_ORIGIN
        : '';
}

const API_ORIGIN = resolveApiOrigin();

export function apiUrl(path = '') {
    if (!path) return API_ORIGIN;
    if (/^https?:\/\//i.test(path)) return path;
    if (path.startsWith('/')) return `${API_ORIGIN}${path}`;
    return API_ORIGIN ? `${API_ORIGIN}/${path}` : `/${path}`;
}

export async function fetchJson(path, options = {}) {
    const response = await fetch(apiUrl(path), options);
    if (!response.ok) {
        let detail = '';
        try {
            const payload = await response.json();
            detail = payload?.detail ? `: ${payload.detail}` : '';
        } catch (_) { /* response was not JSON */ }
        throw new Error(`HTTP ${response.status}${detail}`);
    }
    return response.json();
}

export async function fetchCachedJson(path, cacheName = 'nch-static-map-v1') {
    const url = apiUrl(path);
    let storage = null;
    try {
        if ('caches' in window) {
            storage = await window.caches.open(cacheName);
            const cached = await storage.match(url);
            if (cached) return cached.json();
        }
    } catch (_) { /* fall back to the HTTP cache */ }

    const response = await fetch(url, { cache: 'force-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    if (storage) {
        try { await storage.put(url, response.clone()); }
        catch (_) { /* quota or browser policy; HTTP cache remains available */ }
    }
    return response.json();
}

export function createRequestGate() {
    let sequence = 0;
    let controller = null;

    return Object.freeze({
        begin() {
            sequence += 1;
            controller?.abort();
            controller = new AbortController();
            return { sequence, signal: controller.signal };
        },
        isCurrent(value) {
            return value === sequence;
        },
        cancel() {
            sequence += 1;
            controller?.abort();
            controller = null;
        },
    });
}
