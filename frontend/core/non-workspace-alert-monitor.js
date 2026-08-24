import { fetchJson } from './api.js';

export const MONITORED_ALERT_EVENTS = Object.freeze([
    'Tornado Warning',
    'Severe Thunderstorm Warning',
    'Flash Flood Warning',
    'Tornado Watch',
    'Severe Thunderstorm Watch',
    'Flash Flood Watch',
]);

export const MONITORED_ALERT_COLORS = Object.freeze({
    'Tornado Warning': '#FF0000',
    'Severe Thunderstorm Warning': '#FFA500',
    'Flash Flood Warning': '#8B0000',
    'Tornado Watch': '#FFFF00',
    'Severe Thunderstorm Watch': '#DB7093',
    'Flash Flood Watch': '#2E8B57',
});

const EVENT_PRIORITY = new Map(MONITORED_ALERT_EVENTS.map((event, index) => [event, index]));
const MONITORED_EVENT_SET = new Set(MONITORED_ALERT_EVENTS);
const CHANNEL_NAME = 'nch-non-workspace-alert-monitor-v1';
const STORAGE_PREFIX = 'nch:non-workspace-alert-monitor:v1';
const ENABLED_KEY = `${STORAGE_PREFIX}:enabled`;
const STATE_KEY = `${STORAGE_PREFIX}:state`;
const PRESENCE_PREFIX = `${STORAGE_PREFIX}:presence:`;
const HEARTBEAT_MS = 2_000;
const PEER_TTL_MS = 7_000;
const POLL_MS = 20_000;
const MIN_POLL_MS = 500;
const REFRESH_RETRY_MAX = 30;
const SEEN_TTL_MS = 48 * 60 * 60 * 1_000;
const NOTICE_MS = 20_000;
const INITIAL_ELECTION_MS = 150;
const MAX_NOTICES = 3;

function parseTimestamp(value, fallback = 0) {
    const parsed = Date.parse(value || '');
    return Number.isFinite(parsed) ? parsed : fallback;
}

function vtecAction(feature) {
    const values = feature?.properties?.parameters?.VTEC;
    const match = Array.isArray(values) ? String(values[0] || '').match(/\/O\.([A-Z]{3})\./) : null;
    return match?.[1] || '';
}

export function sharedAlertFeatureId(feature) {
    const props = feature?.properties || {};
    return String(feature?.id || `${props.event || ''}|${props.sent || ''}|${props.areaDesc || ''}`);
}

export function monitoredAlertPriority(feature) {
    return EVENT_PRIORITY.get(feature?.properties?.event) ?? Number.MAX_SAFE_INTEGER;
}

export function sortMonitoredAlerts(features) {
    return [...(Array.isArray(features) ? features : [])].sort((left, right) => (
        monitoredAlertPriority(left) - monitoredAlertPriority(right)
        || parseTimestamp(right?.properties?.sent || right?.properties?.effective)
            - parseTimestamp(left?.properties?.sent || left?.properties?.effective)
        || sharedAlertFeatureId(left).localeCompare(sharedAlertFeatureId(right))
    ));
}

export function monitoredAlertBatchPresentation(features) {
    const alerts = sortMonitoredAlerts(features);
    const highestPriorityAlert = alerts[0] || null;
    return Object.freeze({
        alerts,
        highestPriorityAlert,
        flashColor: highestPriorityAlert
            ? MONITORED_ALERT_COLORS[highestPriorityAlert?.properties?.event] || '#ffffff'
            : '',
    });
}

export function filterMonitoredAlerts(features, now = Date.now()) {
    const byId = new Map();
    (Array.isArray(features) ? features : []).forEach((feature) => {
        const props = feature?.properties || {};
        const event = String(props.event || '');
        const status = String(props.status || '').toLowerCase();
        const messageType = String(props.messageType || '').toLowerCase();
        const headline = String(props.headline || '').toLowerCase();
        const expiresAt = parseTimestamp(props.expires || props.ends);
        if (!MONITORED_EVENT_SET.has(event)) return;
        if (status === 'test' || messageType === 'test' || event.toLowerCase() === 'test message') return;
        if (headline.startsWith('test message') || messageType === 'cancel') return;
        if (['CAN', 'EXP'].includes(vtecAction(feature))) return;
        if (expiresAt && expiresAt <= now) return;
        const id = sharedAlertFeatureId(feature);
        const existing = byId.get(id);
        const issuedAt = parseTimestamp(props.sent || props.effective || props.onset || props.issued);
        const existingIssuedAt = parseTimestamp(
            existing?.properties?.sent
            || existing?.properties?.effective
            || existing?.properties?.onset
            || existing?.properties?.issued,
        );
        if (!existing || issuedAt >= existingIssuedAt) byId.set(id, feature);
    });
    return sortMonitoredAlerts([...byId.values()]);
}

function normalizeSharedState(value) {
    const seen = value?.seen && typeof value.seen === 'object' ? { ...value.seen } : {};
    return {
        cohortStartedAt: Number(value?.cohortStartedAt) || 0,
        updatedAt: Number(value?.updatedAt) || 0,
        seen,
    };
}

export function reconcileMonitoredAlertSnapshot(previousState, features, options = {}) {
    const now = Number(options.now) || Date.now();
    const baseline = options.baseline === true;
    const serverStartedAt = parseTimestamp(options.serverStartedAt);
    const current = filterMonitoredAlerts(features, now);
    const state = normalizeSharedState(previousState);
    if (baseline || !state.cohortStartedAt) {
        state.cohortStartedAt = now;
        state.seen = {};
    }
    Object.entries(state.seen).forEach(([id, observedAt]) => {
        if (!Number.isFinite(Number(observedAt)) || Number(observedAt) < now - SEEN_TTL_MS) delete state.seen[id];
    });
    const fresh = [];
    const notificationStartedAt = Math.max(state.cohortStartedAt, serverStartedAt);
    current.forEach((feature) => {
        const id = sharedAlertFeatureId(feature);
        const issuedAt = parseTimestamp(
            feature?.properties?.sent
            || feature?.properties?.effective
            || feature?.properties?.onset
            || feature?.properties?.issued,
        );
        if (
            !baseline
            && serverStartedAt
            && issuedAt > notificationStartedAt
            && !(id in state.seen)
        ) {
            fresh.push(feature);
        }
        state.seen[id] = now;
    });
    state.updatedAt = now;
    return { state, current, fresh: sortMonitoredAlerts(fresh) };
}

function peerScore(peer) {
    if (peer?.visible && peer?.focused) return 2;
    if (peer?.visible) return 1;
    return 0;
}

export function chooseAlertMonitorOwner(peers, now = Date.now()) {
    return [...(Array.isArray(peers) ? peers : [])]
        .filter((peer) => peer?.tabId && now - Number(peer.heartbeatAt || 0) <= PEER_TTL_MS)
        .sort((left, right) => (
            peerScore(right) - peerScore(left)
            || Number(right.focusAt || 0) - Number(left.focusAt || 0)
            || Number(left.startedAt || 0) - Number(right.startedAt || 0)
            || String(left.tabId).localeCompare(String(right.tabId))
        ))[0]?.tabId || '';
}

export function monitoredAlertPollDelayMs(payload, failureCount = 0, refreshAttempt = 0) {
    if (failureCount > 0) return Math.min(60_000, 5_000 * (2 ** Math.min(4, failureCount - 1)));
    if (payload?.refreshing === true) {
        if (refreshAttempt >= REFRESH_RETRY_MAX) return POLL_MS;
        const retrySeconds = Number(payload?.retry_after_seconds);
        return Math.max(500, Math.min(5_000, Math.round((retrySeconds > 0 ? retrySeconds : 1) * 1_000)));
    }
    const cacheAgeSeconds = Number(payload?.cache_age_seconds);
    const cacheTtlSeconds = Number(payload?.cache_ttl_seconds);
    if (
        Number.isFinite(cacheAgeSeconds)
        && cacheAgeSeconds >= 0
        && Number.isFinite(cacheTtlSeconds)
        && cacheTtlSeconds > 0
    ) {
        const untilStaleMs = Math.round((cacheTtlSeconds - cacheAgeSeconds) * 1_000);
        return Math.max(MIN_POLL_MS, Math.min(POLL_MS, untilStaleMs));
    }
    return POLL_MS;
}

export function monitoredAlertActivationUrl(feature) {
    return `/workspace?alert=${encodeURIComponent(sharedAlertFeatureId(feature))}`;
}

function safeJsonParse(value, fallback = null) {
    try { return JSON.parse(value); }
    catch (_) { return fallback; }
}

function storageAvailable(windowRef) {
    try {
        const storage = windowRef.localStorage;
        storage.getItem(ENABLED_KEY);
        return storage;
    } catch (_) {
        return null;
    }
}

function channelAvailable(windowRef) {
    try {
        return typeof windowRef.BroadcastChannel === 'function'
            ? new windowRef.BroadcastChannel(CHANNEL_NAME) : null;
    } catch (_) {
        return null;
    }
}

function makeTabId(windowRef) {
    try { return windowRef.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`; }
    catch (_) { return `${Date.now()}-${Math.random()}`; }
}

function makeNoopMonitor(enabled = false) {
    return Object.freeze({
        destroy() {},
        isEnabled: () => enabled,
        isOwner: () => false,
        setEnabled: () => enabled,
    });
}

function createPresentation(documentRef, windowRef, options) {
    const notices = documentRef.createElement('div');
    notices.className = 'core-alert-monitor-notifications';
    notices.setAttribute('aria-live', 'assertive');
    notices.setAttribute('aria-label', 'New weather alert notifications');
    const border = documentRef.createElement('div');
    border.className = 'core-alert-monitor-border';
    border.setAttribute('aria-hidden', 'true');
    documentRef.body.append(border, notices);
    const audio = typeof windowRef.Audio === 'function'
        ? new windowRef.Audio('/sounds/weather_alert.mp3') : null;
    let audioUnlocked = false;
    let flashTimer = null;

    function unlockAudio() {
        if (!audio || audioUnlocked) return;
        audio.muted = true;
        void audio.play().then(() => {
            audio.pause();
            audio.currentTime = 0;
            audio.muted = false;
            audioUnlocked = true;
        }).catch(() => { audio.muted = false; });
    }

    if (audio) {
        audio.preload = 'auto';
        audio.load();
        windowRef.addEventListener('pointerdown', unlockAudio, { once: true, capture: true });
        windowRef.addEventListener('keydown', unlockAudio, { once: true, capture: true });
    }

    function clear() {
        notices.replaceChildren();
        border.classList.remove('is-active');
        if (flashTimer) windowRef.clearTimeout(flashTimer);
        flashTimer = null;
    }

    function flash(feature) {
        const event = feature?.properties?.event;
        border.style.setProperty('--core-alert-flash-color', MONITORED_ALERT_COLORS[event] || '#ffffff');
        border.classList.remove('is-active');
        void border.offsetWidth;
        border.classList.add('is-active');
        if (flashTimer) windowRef.clearTimeout(flashTimer);
        flashTimer = windowRef.setTimeout(() => border.classList.remove('is-active'), 1_300);
    }

    function notificationNode(feature) {
        const props = feature?.properties || {};
        const eventName = props.event || 'Weather Alert';
        const wrapper = documentRef.createElement('div');
        wrapper.className = 'core-alert-monitor-notification';
        wrapper.style.setProperty('--core-alert-color', MONITORED_ALERT_COLORS[eventName] || '#6699cc');
        const activation = documentRef.createElement(options.onActivate ? 'button' : 'a');
        activation.className = 'core-alert-monitor-notification-main';
        if (options.onActivate) {
            activation.type = 'button';
            activation.addEventListener('click', () => {
                options.onActivate(feature);
                wrapper.remove();
            });
        } else {
            activation.href = monitoredAlertActivationUrl(feature);
            activation.target = '_blank';
            activation.rel = 'noopener';
        }
        const title = documentRef.createElement('strong');
        title.textContent = `NEW ${eventName.toUpperCase()}`;
        const area = documentRef.createElement('span');
        area.textContent = props.areaDesc || 'Area unavailable';
        activation.append(title, area);
        const close = documentRef.createElement('button');
        close.type = 'button';
        close.className = 'core-alert-monitor-notification-close';
        close.setAttribute('aria-label', `Dismiss ${eventName}`);
        close.textContent = '×';
        close.addEventListener('click', () => wrapper.remove());
        wrapper.append(activation, close);
        windowRef.setTimeout(() => wrapper.remove(), NOTICE_MS);
        return wrapper;
    }

    function present(features) {
        const batch = monitoredAlertBatchPresentation(features);
        if (!batch.alerts.length) return;
        const nodes = batch.alerts.map(notificationNode);
        notices.prepend(...nodes);
        while (notices.children.length > MAX_NOTICES) notices.lastElementChild.remove();
        flash(batch.highestPriorityAlert);
        if (audio) {
            audio.currentTime = 0;
            void audio.play().catch(() => {});
        }
    }

    function destroy() {
        clear();
        windowRef.removeEventListener('pointerdown', unlockAudio, { capture: true });
        windowRef.removeEventListener('keydown', unlockAudio, { capture: true });
        if (audio) {
            audio.pause();
            try { audio.currentTime = 0; }
            catch (_) { /* Metadata may not have loaded before teardown. */ }
        }
    }

    return Object.freeze({ clear, destroy, present });
}

export function startNonWorkspaceAlertMonitor(options = {}) {
    const windowRef = options.windowRef || globalThis.window;
    const documentRef = options.documentRef || globalThis.document;
    if (!windowRef || !documentRef?.body) return makeNoopMonitor();
    if (String(windowRef.location?.pathname || '').replace(/\/$/, '') === '/workspace') return makeNoopMonitor();

    const storage = storageAvailable(windowRef);
    const channel = channelAvailable(windowRef);
    if (!storage && !channel) {
        console.warn('[alert-monitor] Cross-tab coordination is unavailable; notifications are disabled.');
        return makeNoopMonitor();
    }

    const startedAt = Date.now();
    const tabId = makeTabId(windowRef);
    const peers = new Map();
    let focusAt = documentRef.hasFocus?.() ? startedAt : 0;
    let ownerId = '';
    let destroyed = false;
    let heartbeatTimer = null;
    let pollTimer = null;
    let pollController = null;
    let failureCount = 0;
    let refreshAttempt = 0;
    let sharedState = normalizeSharedState(safeJsonParse(storage?.getItem(STATE_KEY), {}));
    let baselineNextPoll = !sharedState.cohortStartedAt;
    let hadPeerAtStart = false;
    let enabled = storage?.getItem(ENABLED_KEY) !== 'false';
    const presentation = createPresentation(documentRef, windowRef, options);

    function selfPeer(now = Date.now()) {
        return {
            tabId,
            startedAt,
            heartbeatAt: now,
            focusAt,
            visible: documentRef.visibilityState !== 'hidden',
            focused: Boolean(documentRef.hasFocus?.()),
        };
    }

    function post(message) {
        try { channel?.postMessage({ ...message, sender: tabId }); }
        catch (_) { /* localStorage remains the transport fallback. */ }
    }

    function storeState() {
        try { storage?.setItem(STATE_KEY, JSON.stringify(sharedState)); }
        catch (_) { /* BroadcastChannel peers still receive the state. */ }
        post({ type: 'state', state: sharedState });
    }

    function readStoragePeers(now) {
        if (!storage) return;
        try {
            for (let index = storage.length - 1; index >= 0; index -= 1) {
                const key = storage.key(index);
                if (!key?.startsWith(PRESENCE_PREFIX)) continue;
                const peer = safeJsonParse(storage.getItem(key));
                if (!peer?.tabId || now - Number(peer.heartbeatAt || 0) > PEER_TTL_MS) {
                    storage.removeItem(key);
                    continue;
                }
                if (peer.tabId !== tabId) peers.set(peer.tabId, peer);
            }
        } catch (_) { /* BroadcastChannel peers still participate. */ }
    }

    function prunePeers(now) {
        peers.forEach((peer, id) => {
            if (id !== tabId && now - Number(peer.heartbeatAt || 0) > PEER_TTL_MS) peers.delete(id);
        });
    }

    function clearPoll() {
        if (pollTimer) windowRef.clearTimeout(pollTimer);
        pollTimer = null;
        pollController?.abort();
        pollController = null;
    }

    function schedulePoll(delay = 0) {
        if (destroyed || !enabled || ownerId !== tabId) return;
        if (pollTimer) windowRef.clearTimeout(pollTimer);
        pollTimer = windowRef.setTimeout(() => {
            pollTimer = null;
            void poll();
        }, delay);
    }

    function applyOwner(nextOwner) {
        const wasOwner = ownerId === tabId;
        ownerId = nextOwner;
        const isOwner = ownerId === tabId;
        if (wasOwner && !isOwner) clearPoll();
        if (!wasOwner && isOwner && enabled) {
            if (!hadPeerAtStart) baselineNextPoll = true;
            schedulePoll(INITIAL_ELECTION_MS);
        }
    }

    function electOwner(now = Date.now()) {
        readStoragePeers(now);
        prunePeers(now);
        peers.set(tabId, selfPeer(now));
        applyOwner(chooseAlertMonitorOwner([...peers.values()], now));
    }

    async function poll() {
        if (destroyed || !enabled || ownerId !== tabId) return;
        pollController?.abort();
        pollController = new AbortController();
        try {
            const payload = await (options.fetchAlerts || fetchJson)(
                '/api/data/alerts?geometry_mode=display&zoom_bucket=low',
                { cache: 'no-store', signal: pollController.signal },
            );
            if (destroyed || !enabled || ownerId !== tabId) return;
            const result = reconcileMonitoredAlertSnapshot(sharedState, payload?.features, {
                baseline: baselineNextPoll,
                serverStartedAt: payload?._server_started_at,
            });
            baselineNextPoll = false;
            failureCount = 0;
            refreshAttempt = payload?.refreshing === true ? refreshAttempt + 1 : 0;
            sharedState = result.state;
            storeState();
            options.onSnapshot?.(result.current);
            if (result.fresh.length && chooseAlertMonitorOwner([...peers.values()]) === tabId) {
                presentation.present(result.fresh);
            }
            schedulePoll(monitoredAlertPollDelayMs(payload, 0, refreshAttempt));
        } catch (error) {
            if (error?.name === 'AbortError' || destroyed || ownerId !== tabId) return;
            failureCount += 1;
            options.onError?.(error);
            schedulePoll(monitoredAlertPollDelayMs(null, failureCount));
        } finally {
            pollController = null;
        }
    }

    function heartbeat() {
        if (destroyed) return;
        const now = Date.now();
        const peer = selfPeer(now);
        peers.set(tabId, peer);
        try { storage?.setItem(`${PRESENCE_PREFIX}${tabId}`, JSON.stringify(peer)); }
        catch (_) { /* BroadcastChannel remains the transport fallback. */ }
        post({ type: 'heartbeat', peer });
        electOwner(now);
    }

    function applyEnabled(nextEnabled, broadcast = false) {
        const changed = enabled !== Boolean(nextEnabled);
        enabled = Boolean(nextEnabled);
        if (!enabled) {
            clearPoll();
            presentation.clear();
        } else if (changed) {
            baselineNextPoll = true;
            if (ownerId === tabId) schedulePoll();
        }
        options.onEnabledChange?.(enabled);
        if (broadcast) {
            try { storage?.setItem(ENABLED_KEY, String(enabled)); }
            catch (_) { /* BroadcastChannel still updates open peers. */ }
            post({ type: 'enabled', enabled });
        }
        return enabled;
    }

    function onMessage(event) {
        const message = event?.data || {};
        if (!message.type || message.sender === tabId) return;
        if (message.type === 'heartbeat' && message.peer?.tabId) {
            hadPeerAtStart = true;
            peers.set(message.peer.tabId, message.peer);
            electOwner();
        } else if (message.type === 'hello') {
            hadPeerAtStart = true;
            post({ type: 'heartbeat', peer: selfPeer() });
            if (sharedState.updatedAt) post({ type: 'state', state: sharedState });
        } else if (message.type === 'bye') {
            peers.delete(message.sender);
            electOwner();
        } else if (message.type === 'state') {
            const nextState = normalizeSharedState(message.state);
            if (nextState.updatedAt >= sharedState.updatedAt) sharedState = nextState;
        } else if (message.type === 'enabled') {
            applyEnabled(message.enabled);
        }
    }

    function onStorage(event) {
        if (event.key === ENABLED_KEY) applyEnabled(event.newValue !== 'false');
        else if (event.key === STATE_KEY) {
            const nextState = normalizeSharedState(safeJsonParse(event.newValue, {}));
            if (nextState.updatedAt >= sharedState.updatedAt) sharedState = nextState;
        } else if (event.key?.startsWith(PRESENCE_PREFIX)) electOwner();
    }

    function onFocus() {
        focusAt = Date.now();
        heartbeat();
    }

    function destroy() {
        if (destroyed) return;
        destroyed = true;
        clearPoll();
        if (heartbeatTimer) windowRef.clearInterval(heartbeatTimer);
        heartbeatTimer = null;
        presentation.destroy();
        try { storage?.removeItem(`${PRESENCE_PREFIX}${tabId}`); }
        catch (_) { /* stale presence expires after the short peer TTL. */ }
        post({ type: 'bye' });
        channel?.close();
        windowRef.removeEventListener('focus', onFocus);
        windowRef.removeEventListener('blur', heartbeat);
        windowRef.removeEventListener('storage', onStorage);
        windowRef.removeEventListener('pagehide', destroy);
        documentRef.removeEventListener('visibilitychange', heartbeat);
    }

    channel?.addEventListener('message', onMessage);
    windowRef.addEventListener('focus', onFocus);
    windowRef.addEventListener('blur', heartbeat);
    windowRef.addEventListener('storage', onStorage);
    windowRef.addEventListener('pagehide', destroy);
    documentRef.addEventListener('visibilitychange', heartbeat);
    readStoragePeers(startedAt);
    hadPeerAtStart = [...peers.values()].some((peer) => peer.tabId !== tabId);
    post({ type: 'hello' });
    windowRef.setTimeout(() => {
        if (destroyed) return;
        heartbeat();
        heartbeatTimer = windowRef.setInterval(heartbeat, HEARTBEAT_MS);
    }, INITIAL_ELECTION_MS);
    applyEnabled(enabled);

    return Object.freeze({
        destroy,
        isEnabled: () => enabled,
        isOwner: () => ownerId === tabId,
        setEnabled: (value) => applyEnabled(value, true),
    });
}
