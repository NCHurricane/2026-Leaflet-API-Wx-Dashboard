import { ALERT_COLORS, ALERT_DEFAULT_COLOR, ALERT_TEXT_COLORS } from './alerts-config.js?v=20260719a';

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
}

function formatTime(value) {
    const time = Date.parse(value || '');
    return Number.isFinite(time) ? new Date(time).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—';
}

function expiresIn(value) {
    const minutes = Math.round((Date.parse(value || '') - Date.now()) / 60_000);
    if (!Number.isFinite(minutes)) return '';
    if (minutes <= 0) return 'expired';
    if (minutes < 60) return `in ${minutes} min`;
    const hours = Math.floor(minutes / 60); const remainder = minutes % 60;
    return `in ${hours}h${remainder ? ` ${remainder}m` : ''}`;
}

function firstParameter(props, key) {
    const values = props?.parameters?.[key];
    return Array.isArray(values) ? String(values[0] || '').trim() : '';
}

function threatChips(props) {
    const chips = [];
    const push = (label, value) => { if (value && String(value).toLowerCase() !== 'none') chips.push({ label, value: String(value) }); };
    push('Tornado', firstParameter(props, 'tornadoDetection') || firstParameter(props, 'tornadoThreat'));
    const hailThreat = firstParameter(props, 'hailThreat'); const hailSize = firstParameter(props, 'maxHailSize');
    if (hailThreat || hailSize) push('Hail', [hailThreat, hailSize ? `max ${hailSize}${/[″"]$/.test(hailSize) ? '' : '″'}` : ''].filter(Boolean).join(' · '));
    const windThreat = firstParameter(props, 'windThreat'); const windGust = firstParameter(props, 'maxWindGust');
    if (windThreat || windGust) push('Wind', [windThreat, windGust ? `max ${windGust}` : ''].filter(Boolean).join(' · '));
    push('Flash Flood', firstParameter(props, 'flashFloodDetection'));
    return chips;
}

function splitDescription(rawDescription) {
    const text = String(rawDescription || '').replace(/\r\n?/g, '\n').trim();
    if (!text) return { body: '', locations: '' };
    const match = text.match(/(?:^|\n)\s*\*?\s*LOCATIONS IMPACTED INCLUDE[.\s]*([\s\S]*)$/i);
    if (!match) return { body: text, locations: '' };
    return { body: text.slice(0, match.index).trim(), locations: String(match[1] || '').trim() };
}

function formatText(text) {
    const marked = String(text || '').replace(/(?:^|\n)\s*\*?\s*(HAZARD|SOURCE|IMPACT)\.{2,}\s*/gi, '\n\n$1:::');
    return marked.split(/\n\s*\n/).map((paragraph) => paragraph.replace(/\s*\n\s*/g, ' ').trim()).filter(Boolean).map((paragraph) => {
        const label = paragraph.match(/^(HAZARD|SOURCE|IMPACT):::\s*(.*)$/i);
        return label ? `<p><strong>${escapeHtml(label[1])}:</strong> ${escapeHtml(label[2])}</p>` : `<p>${escapeHtml(paragraph)}</p>`;
    }).join('');
}

function cwaCode(props) {
    const awips = firstParameter(props, 'AWIPSidentifier').toUpperCase();
    if (awips.length >= 6) return awips.slice(-3);
    const wmo = firstParameter(props, 'WMOidentifier').toUpperCase();
    const wmoMatch = wmo.match(/\bK([A-Z]{3})\b/);
    if (wmoMatch) return wmoMatch[1];
    return String(props?.sender || '').toUpperCase().match(/([A-Z]{3})@/)?.[1] || '';
}

export function textProductUrl(feature) {
    const props = feature?.properties || {};
    const awips = firstParameter(props, 'AWIPSidentifier').toUpperCase();
    const eventProducts = {
        'Tornado Warning': 'TOR', 'Severe Thunderstorm Warning': 'SVR',
        'Flash Flood Warning': 'FFW', 'Special Marine Warning': 'SMW',
        'Special Weather Statement': 'SPS', 'Severe Weather Statement': 'SVS',
    };
    // Continuation/update alerts may carry an SVS AWIPS identifier while their
    // event remains a Tornado/Severe/Flash Flood warning. The event owns the
    // canonical warning-product link; AWIPS is the fallback for other events.
    const product = eventProducts[props.event] || (awips.length >= 6 ? awips.slice(0, 3) : '');
    const office = cwaCode(props);
    if (product && office) {
        const params = new URLSearchParams({ site: office.toLowerCase(), issuedby: office, product });
        return `https://forecast.weather.gov/product.php?${params}`;
    }
    const sourceUrl = String(props.source_url || '').trim();
    if (/^https?:\/\//i.test(sourceUrl)) return sourceUrl;
    if (office && props.event) {
        const params = new URLSearchParams({ cwa: office, wwa: String(props.event).toLowerCase() });
        return `https://forecast.weather.gov/wwamap/wwatxtget.php?${params}`;
    }
    return '';
}

function installDrag(root, handle) {
    let drag = null;
    handle.addEventListener('pointerdown', (event) => {
        if (event.target.closest('button, a')) return;
        const parentRect = root.parentElement.getBoundingClientRect();
        const rect = root.getBoundingClientRect();
        root.style.left = `${rect.left - parentRect.left}px`;
        root.style.top = `${rect.top - parentRect.top}px`;
        root.style.right = 'auto';
        drag = { x: event.clientX, y: event.clientY, left: rect.left - parentRect.left, top: rect.top - parentRect.top };
        handle.setPointerCapture(event.pointerId);
        event.preventDefault();
    });
    handle.addEventListener('pointermove', (event) => {
        if (!drag) return;
        const parent = root.parentElement.getBoundingClientRect();
        const maxLeft = Math.max(0, parent.width - root.offsetWidth);
        const maxTop = Math.max(0, parent.height - root.offsetHeight);
        root.style.left = `${Math.max(0, Math.min(maxLeft, drag.left + event.clientX - drag.x))}px`;
        root.style.top = `${Math.max(0, Math.min(maxTop, drag.top + event.clientY - drag.y))}px`;
    });
    const end = () => { drag = null; };
    handle.addEventListener('pointerup', end);
    handle.addEventListener('pointercancel', end);
}

export function createAlertDetail(root, options = {}) {
    function close() { root.replaceChildren(); root.hidden = true; }
    function open(feature) {
        const props = feature?.properties || {};
        const event = props.event || 'Weather Alert';
        const color = ALERT_COLORS[event] || ALERT_DEFAULT_COLOR;
        const chips = threatChips(props);
        const { body, locations } = splitDescription(props.description);
        const link = textProductUrl(feature);
        const badges = [props.severity, props.urgency, props.certainty].filter(Boolean);
        root.style.setProperty('--alert-color', color);
        root.style.setProperty('--alert-text-color', ALERT_TEXT_COLORS[event] || color);
        root.style.left = 'auto'; root.style.right = '12px'; root.style.top = '12px';
        root.innerHTML = `<div class="alerts-detail-head"><div><div class="alerts-eyebrow">NWS Alert</div><h2>${escapeHtml(event)}</h2></div><button class="alerts-detail-close" type="button" aria-label="Close alert detail">×</button></div>
            <div class="alerts-detail-body">
                ${badges.length ? `<div class="alerts-detail-badges">${badges.map((badge) => `<span class="alerts-detail-badge">${escapeHtml(badge)}</span>`).join('')}</div>` : ''}
                <dl class="alerts-detail-grid"><dt>Area</dt><dd>${escapeHtml(props.areaDesc || '—')}</dd><dt>Issued</dt><dd>${escapeHtml(formatTime(props.sent || props.effective))}${props.senderName ? ` by ${escapeHtml(props.senderName)}` : ''}</dd><dt>Expires</dt><dd>${escapeHtml(formatTime(props.expires || props.ends))}${expiresIn(props.expires || props.ends) ? ` (${escapeHtml(expiresIn(props.expires || props.ends))})` : ''}</dd></dl>
                ${chips.length ? `<div class="alerts-threat-title">Threat Details</div><div class="alerts-threat-chips">${chips.map((chip) => `<span class="alerts-threat-chip"><strong>${escapeHtml(chip.label)}:</strong> ${escapeHtml(chip.value)}</span>`).join('')}</div>` : ''}
                ${props.headline ? `<div class="alerts-detail-section"><h3>Headline</h3><p>${escapeHtml(props.headline)}</p></div>` : ''}
                ${body ? `<div class="alerts-detail-section">${formatText(body)}</div>` : ''}
                ${locations ? `<div class="alerts-detail-section"><h3>Locations Impacted</h3>${formatText(locations)}</div>` : ''}
                ${props.instruction ? `<div class="alerts-detail-section"><h3>Precautionary / Preparedness Actions</h3>${formatText(props.instruction)}</div>` : ''}
                ${link ? `<a class="alerts-detail-link" href="${escapeHtml(link)}" target="_blank" rel="noopener">View Full NWS Alert Text</a>` : ''}
            </div>`;
        root.hidden = false;
        root.querySelector('.alerts-detail-close')?.addEventListener('click', close);
        installDrag(root, root.querySelector('.alerts-detail-head'));
        options.onOpen?.(feature);
    }
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape') close(); });
    return Object.freeze({ close, open });
}
