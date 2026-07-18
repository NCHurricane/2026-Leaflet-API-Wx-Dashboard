// Page-local detail panel for WPC mesoscale precipitation discussions and
// ERO/winter forecast areas. Floats inside the map panel; supports prev/next
// navigation when several detail features are supplied (winter probabilities).

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
}

function formatTextBlock(text) {
    const paras = String(text || '')
        .split(/\n\s*\n/)
        .map((para) => para.replace(/\s*\n\s*/g, ' ').trim())
        .filter(Boolean);
    return paras.map((para) => `<p>${escapeHtml(para)}</p>`).join('');
}

function formatSentExpires(p) {
    const fmt = (iso) => {
        if (!iso) return '';
        try {
            return new Date(iso).toLocaleString([], {
                month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
            });
        } catch (_) { return ''; }
    };
    return { sent: fmt(p?.sent), expires: fmt(p?.expires) };
}

function relExpires(isoStr) {
    if (!isoStr) return '';
    const diffMs = Date.parse(isoStr) - Date.now();
    if (!Number.isFinite(diffMs) || diffMs < 0) return 'expired';
    const mins = Math.round(diffMs / 60_000);
    if (mins < 60) return `${mins} min`;
    const hrs = Math.floor(mins / 60);
    const rem = mins % 60;
    return rem ? `${hrs}h ${rem}m` : `${hrs}h`;
}

// MPD bulletins use the SUMMARY... / DISCUSSION... section layout.
function extractMdSections(text) {
    const raw = String(text || '').replace(/\r\n?/g, '\n').trim();
    if (!raw) return { preface: '', summary: '', discussion: '' };
    const summaryMatch = raw.match(/\bSUMMARY\.{3}\s*([\s\S]*?)(?=\n\s*DISCUSSION\.{3}|$)/i);
    const discussionMatch = raw.match(/\bDISCUSSION\.{3}\s*([\s\S]*?)(?=\n\s*\.\.[A-Za-z]|\n\s*ATTN\.{3}|\n\s*LAT\.{3}|$)/i);
    const summaryIdx = raw.search(/\bSUMMARY\.{3}/i);
    return {
        preface: summaryIdx > 0 ? raw.slice(0, summaryIdx).trim() : '',
        summary: summaryMatch ? String(summaryMatch[1] || '').trim() : '',
        discussion: discussionMatch ? String(discussionMatch[1] || '').trim() : '',
    };
}

function renderMdBodyHtml(text) {
    const sections = extractMdSections(text);
    const prefaceHtml = sections.preface ? formatTextBlock(sections.preface) : '';
    const summaryHtml = sections.summary
        ? `<section class="wpc-detail-section"><h4>Summary</h4>${formatTextBlock(sections.summary)}</section>` : '';
    const discussionHtml = sections.discussion
        ? `<section class="wpc-detail-section"><h4>Discussion</h4>${formatTextBlock(sections.discussion)}</section>` : '';
    if (!summaryHtml && !discussionHtml) return formatTextBlock(text);
    return `${prefaceHtml}${summaryHtml}${discussionHtml}`;
}

function chipGroupHtml(heading, chips) {
    const kept = (chips || []).filter(Boolean);
    if (!kept.length) return '';
    const chipHtml = kept.map((chip) => (
        `<span class="wpc-detail-chip"><strong>${escapeHtml(chip.label)}:</strong> ${escapeHtml(chip.value)}</span>`
    )).join('');
    return `<h4 class="wpc-detail-chips-title">${escapeHtml(heading)}</h4><div class="wpc-detail-chips">${chipHtml}</div>`;
}

function buildDetailHtml(feat, index, total) {
    const p = feat?.properties || {};
    const event = p.event || 'WPC Product';
    const isMpd = /mesoscale precipitation discussion/i.test(String(event));
    const isForecast = !!p.wpc_forecast;
    const color = p.color || '#38BDF8';
    const badges = [p.severity, p.urgency, p.certainty]
        .filter(Boolean)
        .map((badge) => `<span class="wpc-detail-badge">${escapeHtml(String(badge))}</span>`)
        .join('');
    const { sent, expires } = formatSentExpires(p);
    const expRel = relExpires(p?.expires);
    const senderName = String(p.senderName || '').trim();
    const issuedLine = [
        sent ? `${isForecast ? 'Updated' : 'Issued'} ${escapeHtml(sent)}` : '',
        expires ? `until ${escapeHtml(expires)}` : '',
        senderName ? `by ${escapeHtml(senderName)}` : '',
    ].filter(Boolean).join(' ');
    const expiresLine = expires
        ? `Expires: ${escapeHtml(expires)}${expRel ? ` <span class="wpc-detail-countdown">(in ${escapeHtml(expRel)})</span>` : ''}`
        : '';
    const bodyHtml = isMpd
        ? renderMdBodyHtml(p.description)
        : formatTextBlock(p.description || '');
    const chipsHtml = [
        isMpd ? chipGroupHtml('Operational Areas', [
            p.wfo ? { label: 'WFOs', value: p.wfo } : null,
            p.rfc ? { label: 'RFCs', value: p.rfc } : null,
        ]) : '',
        isForecast ? chipGroupHtml('Forecast Details', [
            p.wpc_metric_value
                ? { label: p.wpc_metric_label || 'Category', value: p.wpc_metric_value }
                : null,
            p.wpc_day ? { label: 'Forecast Day', value: `Day ${p.wpc_day}` } : null,
        ]) : '',
    ].filter(Boolean).join('');
    const sourceUrl = String(p.source_url || '').trim();
    const linkLabel = isMpd ? 'View Full WPC Discussion' : 'View WPC Discussion';
    const linkHtml = sourceUrl
        ? `<a class="wpc-detail-fulllink" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">${linkLabel}</a>`
        : '';
    const navDisabled = total <= 1;
    const counter = total > 1 ? `<span class="wpc-detail-counter">${index + 1} / ${total}</span>` : '';

    return [
        `<div class="wpc-detail-header" style="border-color:${escapeHtml(color)}">`,
        `  <div class="wpc-detail-title" style="color:${escapeHtml(color)}">${escapeHtml(event)}</div>`,
        `  <button type="button" class="wpc-detail-close" aria-label="Close">×</button>`,
        `</div>`,
        badges ? `<div class="wpc-detail-badges">${badges}</div>` : '',
        issuedLine ? `<div class="wpc-detail-issued">${issuedLine}</div>` : '',
        expiresLine ? `<div class="wpc-detail-expires">${expiresLine}</div>` : '',
        chipsHtml ? `<div class="wpc-detail-meta">${chipsHtml}</div>` : '',
        `<div class="wpc-detail-scroll">`,
        bodyHtml ? `<section class="wpc-detail-section">${bodyHtml}</section>` : '',
        `</div>`,
        `<div class="wpc-detail-footer">${linkHtml}<button type="button" class="wpc-detail-zoomlink" data-wpc-zoom="1">Zoom to Area</button></div>`,
        !navDisabled
            ? `<div class="wpc-detail-nav">
                   <button type="button" class="wpc-detail-nav-btn" data-wpc-nav="prev" aria-label="Previous area">‹</button>
                   ${counter}
                   <button type="button" class="wpc-detail-nav-btn" data-wpc-nav="next" aria-label="Next area">›</button>
               </div>`
            : '',
    ].join('');
}

export function createWpcDetailPanel(host, mapCore, { zoomToFeature } = {}) {
    const map = mapCore.map;
    let panel = null;
    let features = [];
    let index = 0;
    let anchorLatLng = null;

    function close() {
        if (!panel) return;
        document.removeEventListener('keydown', onKeyDown);
        map.off('click', close);
        panel.remove();
        panel = null;
        features = [];
        index = 0;
        anchorLatLng = null;
    }

    function onKeyDown(event) {
        if (event.key === 'Escape') close();
    }

    function positionPanel(latlng) {
        if (!panel) return;
        let preferRight = true;
        try {
            const point = map.latLngToContainerPoint(latlng);
            preferRight = point.x < (host.getBoundingClientRect().width / 2);
        } catch (_) { /* fall back right */ }
        panel.classList.toggle('is-right', preferRight);
        panel.classList.toggle('is-left', !preferRight);
    }

    function render() {
        if (!panel || !features.length) return;
        panel.innerHTML = buildDetailHtml(features[index], index, features.length);
        panel.querySelector('.wpc-detail-close')?.addEventListener('click', close);
        panel.querySelector('[data-wpc-zoom]')?.addEventListener('click', () => {
            const feat = features[index];
            if (feat) zoomToFeature?.(feat);
        });
        panel.querySelectorAll('[data-wpc-nav]').forEach((button) => {
            button.addEventListener('click', () => {
                const delta = button.dataset.wpcNav === 'prev' ? -1 : 1;
                index = (index + delta + features.length) % features.length;
                render();
            });
        });
    }

    function open(latlng, feat, featureList) {
        if (!latlng || !feat) return;
        close();
        features = Array.isArray(featureList) && featureList.length ? featureList : [feat];
        index = Math.max(0, features.indexOf(feat));
        anchorLatLng = latlng;
        panel = document.createElement('div');
        panel.className = 'wpc-detail';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-label', 'WPC product detail');
        ['pointerdown', 'dblclick', 'wheel'].forEach((type) => {
            panel.addEventListener(type, (event) => event.stopPropagation());
        });
        host.appendChild(panel);
        positionPanel(anchorLatLng);
        render();
        document.addEventListener('keydown', onKeyDown);
        setTimeout(() => { if (panel) map.on('click', close); }, 0);
    }

    return Object.freeze({ open, close, destroy: close });
}
