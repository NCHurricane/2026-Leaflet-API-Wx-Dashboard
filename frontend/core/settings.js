import { fetchJson } from './api.js';

let defaultsPromise = null;

export function loadDefaultSettings() {
    if (!defaultsPromise) {
        defaultsPromise = fetchJson('/api/user-settings/defaults', { cache: 'no-store' })
            .catch((error) => {
                defaultsPromise = null;
                throw error;
            });
    }
    return defaultsPromise;
}

export async function loadPageSettings(pageName, fallback = {}) {
    try {
        const defaults = await loadDefaultSettings();
        return { ...fallback, ...(defaults?.pages?.[pageName] || {}) };
    } catch (_) {
        return { ...fallback };
    }
}
