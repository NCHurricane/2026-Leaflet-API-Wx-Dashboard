// Page-local detail panel for SPC outlook areas, mesoscale discussions, and
// watches. Floats inside the map panel; one panel open at a time.

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
}

// Convert NWS plain text to safe HTML: preserve paragraphs, join wrapped lines.
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

// "MOST PROBABLE PEAK …" chips from MD bulletins; returns cleaned text too.
function extractMdPeakChips(rawText) {
    let text = String(rawText || '');
    if (!text) return { chips: [], cleanedText: '' };
    text = text.replace(/\r\n?/g, '\n');
    const specs = [
        { label: 'Tornado', re: /MOST\s+PROBABLE\s+PEAK\s+TORNADO\s+INTENSITY\.{3}\s*([^\n\r]+?)(?=\s+MOST\s+PROBABLE\s+PEAK\s+|$)/i },
        { label: 'Wind Gust', re: /MOST\s+PROBABLE\s+PEAK\s+WIND\s+GUST\.{3}\s*([^\n\r]+?)(?=\s+MOST\s+PROBABLE\s+PEAK\s+|$)/i },
        { label: 'Hail Size', re: /MOST\s+PROBABLE\s+PEAK\s+HAIL\s+SIZE\.{3}\s*([^\n\r]+?)(?=\s+MOST\s+PROBABLE\s+PEAK\s+|$)/i },
    ];
    const chips = [];
    for (const spec of specs) {
        const match = text.match(spec.re);
        if (!match) continue;
        const value = String(match[1] || '').replace(/\s+/g, ' ').trim();
        if (value) chips.push({ label: spec.label, value });
        text = text.replace(match[0], ' ');
    }
    return {
        chips,
        cleanedText: text.replace(/[^\S\n]{2,}/g, ' ').replace(/\n{3,}/g, '\n\n').trim(),
    };
}

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
        ? `<section class="spc-detail-section"><h4>Summary</h4>${formatTextBlock(sections.summary)}</section>` : '';
    const discussionHtml = sections.discussion
        ? `<section class="spc-detail-section"><h4>Discussion</h4>${formatTextBlock(sections.discussion)}</section>` : '';
    if (!summaryHtml && !discussionHtml) return formatTextBlock(text);
    return `${prefaceHtml}${summaryHtml}${discussionHtml}`;
}

function buildWatchChips(p) {
    const probabilities = p?.probabilities || {};
    const chips = [];
    const push = (label, key) => {
        const value = String(probabilities?.[key] || '').trim();
        if (value) chips.push({ label, value });
    };
    push('2+ Tornadoes', 'tor2');
    push('EF2+ Tornado', 'tor_strong');
    push('10+ Wind Events', 'wind10');
    push('Wind 65+ kt', 'wind65');
    push('10+ Hail Events', 'hail10');
    push('Hail 2+ in', 'hail2');
    push('6+ Combined', 'combined6');
    return chips;
}

function watchTitle(p) {
    const event = String(p?.watch_type || p?.event || 'Watch').trim() || 'Watch';
    const rawNumber = String(p?.watch_number || p?.id || '').trim();
    if (!rawNumber) return event;
    const normalized = /^\d+$/.test(rawNumber) ? String(Number(rawNumber)) : rawNumber;
    return `${event} #${normalized}`;
}

function chipGroupHtml(heading, chips) {
    if (!chips.length) return '';
    const chipHtml = chips.map((chip) => (
        `<span class="spc-detail-chip"><strong>${escapeHtml(chip.label)}:</strong> ${escapeHtml(chip.value)}</span>`
    )).join('');
    return `<h4 class="spc-detail-chips-title">${escapeHtml(heading)}</h4><div class="spc-detail-chips">${chipHtml}</div>`;
}

const OUTLOOK_PRODUCT_LABELS = {
    cat: 'Categorical', torn: 'Tornado', wind: 'Wind', hail: 'Hail',
    prob: 'Probabilistic', windrh: 'Wind / RH', dryt: 'Dry Thunderstorm',
    windrhcat: 'Wind / RH Categorical', windrhprob: 'Wind / RH Probabilistic',
    drytcat: 'Dry Thunderstorm Categorical', drytprob: 'Dry Thunderstorm Probabilistic',
};

function outlookRiskKey(value) {
    const raw = String(value || '').trim().toUpperCase();
    const categorical = {
        TSTM: 'GENERAL THUNDERSTORMS', MRGL: 'MARGINAL', SLGT: 'SLIGHT', ENH: 'ENHANCED',
        MDT: 'MODERATE', HIGH: 'HIGH', ELEV: 'ELEVATED', CRIT: 'CRITICAL',
        EXTM: 'EXTREMELY CRITICAL', IDRT: 'ISOLATED DRY THUNDERSTORM',
        SDRT: 'SCATTERED DRY THUNDERSTORM',
    };
    if (categorical[raw]) return categorical[raw];
    const numeric = Number.parseFloat(raw);
    if (Number.isFinite(numeric)) return String(Math.round(numeric <= 1 ? numeric * 100 : numeric));
    const percent = raw.match(/(\d+(?:\.\d+)?)\s*%/);
    if (percent) return String(Number(percent[1]));
    return raw.replace(/\s+/g, ' ');
}

function outlookImpactsHtml(rows, clickedRisk) {
    if (!Array.isArray(rows) || !rows.length) {
        return '<p class="spc-detail-empty">SPC impact estimates are unavailable.</p>';
    }
    const clickedKey = outlookRiskKey(clickedRisk);
    const body = rows.map((row) => {
        const isSelected = outlookRiskKey(row?.risk) === clickedKey;
        const centers = Array.isArray(row?.population_centers) ? row.population_centers.join(' · ') : '';
        return `<tr${isSelected ? ' class="is-selected"' : ''}>
            <td>${escapeHtml(row?.risk || '')}</td>
            <td>${escapeHtml(row?.area_sq_mi || '')}</td>
            <td>${escapeHtml(row?.population || '')}</td>
            <td>${escapeHtml(centers)}</td>
        </tr>`;
    }).join('');
    return `<div class="spc-detail-table-wrap">
        <table class="spc-detail-table">
            <thead><tr><th scope="col">Risk</th><th scope="col">Area (sq. mi.)</th><th scope="col">Population</th><th scope="col">Population Centers</th></tr></thead>
            <tbody>${body}</tbody>
        </table>
    </div>`;
}

export function buildSpcOutlookDetailHtml(feat, context) {
    const p = feat?.properties || {};
    const detail = context?.detail || {};
    const day = Number(context?.day || 1);
    const hazard = String(context?.hazard || 'cat');
    const productLabel = OUTLOOK_PRODUCT_LABELS[hazard] || 'Outlook';
    const clickedRisk = String(p.LABEL || p.label || p.LABEL2 || p.label2 || '').trim();
    const riskLabel = String(p.LABEL2 || p.label2 || p.LABEL || p.label || 'Outlook Area').trim();
    const significantLabel = String(
        context?.significantFeature?.properties?.LABEL
        || context?.significantFeature?.properties?.label || '',
    ).trim();
    const { sent, expires } = formatSentExpires({
        sent: p.ISSUE_ISO || p.issue_iso,
        expires: p.EXPIRE_ISO || p.expire_iso,
    });
    const color = String(p.stroke || p.fill || '#fbbf24');
    const title = context?.isFire
        ? `Day ${day} Fire Weather Outlook`
        : `Day ${day} ${productLabel} Outlook`;
    const chips = day >= 4
        ? [{ label: 'Probability', value: riskLabel }]
        : [
            { label: 'Risk', value: riskLabel },
            { label: 'Product', value: productLabel },
            ...(significantLabel ? [{ label: 'Significant', value: significantLabel }] : []),
        ];
    const chipsHtml = `<div class="spc-detail-chips">${chips.map((chip) => (
        `<span class="spc-detail-chip"><strong>${escapeHtml(chip.label)}:</strong> ${escapeHtml(chip.value)}</span>`
    )).join('')}</div>`;
    const hasImpactsTab = day <= 3;
    const tabsHtml = hasImpactsTab
        ? `<div class="spc-detail-tabs" role="tablist" aria-label="SPC outlook details">
            <button type="button" class="spc-detail-tab is-active" role="tab" aria-selected="true" data-spc-outlook-tab="outlook">Outlook</button>
            <button type="button" class="spc-detail-tab" role="tab" aria-selected="false" data-spc-outlook-tab="impacts">Impacts</button>
        </div>`
        : '';
    const outlookText = detail?.text ? formatTextBlock(detail.text) : '<p>SPC outlook text is unavailable.</p>';
    const sourceUrl = String(detail?.source_url || '');
    const linkHtml = sourceUrl
        ? `<a class="spc-detail-fulllink" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">View Full SPC ${context?.isFire ? 'Fire Weather ' : ''}Outlook</a>`
        : '';

    return [
        `<div class="spc-detail-header" style="border-color:${escapeHtml(color)}">`,
        `  <div class="spc-detail-title" style="color:${escapeHtml(color)}">${escapeHtml(title)}</div>`,
        `  <button type="button" class="spc-detail-close" aria-label="Close">×</button>`,
        `</div>`,
        sent ? `<div class="spc-detail-issued">Issued ${escapeHtml(sent)}${expires ? ` · Valid until ${escapeHtml(expires)}` : ''}</div>` : '',
        `<div class="spc-detail-meta">${chipsHtml}</div>`,
        tabsHtml,
        `<div class="spc-detail-scroll">`,
        `<section role="tabpanel" data-spc-outlook-panel="outlook">${outlookText}</section>`,
        hasImpactsTab
            ? `<section role="tabpanel" data-spc-outlook-panel="impacts" hidden>${outlookImpactsHtml(detail?.impacts, clickedRisk)}</section>`
            : '',
        `</div>`,
        `<div class="spc-detail-footer">${linkHtml}<button type="button" class="spc-detail-zoomlink" data-spc-zoom="1">Zoom to Outlook Area</button></div>`,
    ].join('');
}

export function buildSpcTextDetailHtml(feat) {
    const p = feat?.properties || {};
    const baseEvent = p.event || 'SPC Product';
    const isWatch = /(?:tornado|severe thunderstorm)\s+watch/i.test(String(p.watch_type || baseEvent || ''));
    const isTornadoWatch = /tornado/i.test(String(p.watch_type || baseEvent || ''));
    const title = isWatch ? watchTitle(p) : baseEvent;
    const color = isWatch ? (isTornadoWatch ? '#ffe066' : '#ff8ec7') : '#63d8ff';
    const { sent, expires } = formatSentExpires(p);
    const expRel = relExpires(p?.expires);
    const senderName = String(p.senderName || '').trim();
    const issuedLine = [
        sent ? `Issued ${escapeHtml(sent)}` : '',
        expires ? `until ${escapeHtml(expires)}` : '',
        senderName ? `by ${escapeHtml(senderName)}` : '',
    ].filter(Boolean).join(' ');
    const expiresLine = expires
        ? `Expires: ${escapeHtml(expires)}${expRel ? ` <span class="spc-detail-countdown">(in ${escapeHtml(expRel)})</span>` : ''}`
        : '';
    const mdPeak = extractMdPeakChips(p.description);
    const bodyText = mdPeak.cleanedText || String(p.description || '');
    const isMd = /mesoscale discussion/i.test(String(p.event || ''));
    const bodyHtml = isMd ? renderMdBodyHtml(bodyText) : formatTextBlock(bodyText);
    const instructionHtml = formatTextBlock(p.instruction || '');
    const chipsHtml = [
        chipGroupHtml('Most Probable Peak', mdPeak.chips),
        isWatch ? chipGroupHtml('Watch Probabilities', buildWatchChips(p)) : '',
    ].filter(Boolean).join('');
    const sourceUrl = String(p.source_url || '').trim();
    const linkHtml = sourceUrl
        ? `<a class="spc-detail-fulllink" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">View Full SPC ${isWatch ? 'Watch' : 'Discussion'} Text</a>`
        : '';

    return [
        `<div class="spc-detail-header" style="border-color:${color}">`,
        `  <div class="spc-detail-title" style="color:${color}">${escapeHtml(title)}</div>`,
        `  <button type="button" class="spc-detail-close" aria-label="Close">×</button>`,
        `</div>`,
        issuedLine ? `<div class="spc-detail-issued">${issuedLine}</div>` : '',
        expiresLine ? `<div class="spc-detail-expires">${expiresLine}</div>` : '',
        chipsHtml ? `<div class="spc-detail-meta">${chipsHtml}</div>` : '',
        `<div class="spc-detail-scroll">`,
        bodyHtml ? `<section class="spc-detail-section">${bodyHtml}</section>` : '',
        instructionHtml ? `<section class="spc-detail-section"><h4>Precautionary / Preparedness Actions</h4>${instructionHtml}</section>` : '',
        `</div>`,
        `<div class="spc-detail-footer">${linkHtml}<button type="button" class="spc-detail-zoomlink" data-spc-zoom="1">Zoom to Area</button></div>`,
    ].join('');
}

export function wireSpcDetailContent(root, { close, zoom } = {}) {
    root.querySelector('.spc-detail-close')?.addEventListener('click', () => close?.());
    root.querySelector('[data-spc-zoom]')?.addEventListener('click', () => zoom?.());
    root.querySelectorAll('[data-spc-outlook-tab]').forEach((button) => {
        button.addEventListener('click', () => {
            const key = button.getAttribute('data-spc-outlook-tab') || 'outlook';
            root.querySelectorAll('[data-spc-outlook-tab]').forEach((tabButton) => {
                const isActive = tabButton.getAttribute('data-spc-outlook-tab') === key;
                tabButton.classList.toggle('is-active', isActive);
                tabButton.setAttribute('aria-selected', isActive ? 'true' : 'false');
            });
            root.querySelectorAll('[data-spc-outlook-panel]').forEach((tabPanel) => {
                tabPanel.hidden = tabPanel.getAttribute('data-spc-outlook-panel') !== key;
            });
        });
    });
}

export function createSpcDetailPanel(host, mapCore, { zoomToFeature } = {}) {
    const map = mapCore.map;
    let panel = null;
    let activeFeature = null;

    function close() {
        if (!panel) return;
        document.removeEventListener('keydown', onKeyDown);
        map.off('click', close);
        panel.remove();
        panel = null;
        activeFeature = null;
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

    function wirePanel() {
        wireSpcDetailContent(panel, {
            close,
            zoom() {
                if (activeFeature) zoomToFeature?.(activeFeature);
            },
        });
        // Keep map interactions from bleeding through the panel.
        ['pointerdown', 'dblclick', 'wheel'].forEach((type) => {
            panel.addEventListener(type, (event) => event.stopPropagation());
        });
    }

    function open(latlng, feat, html) {
        close();
        panel = document.createElement('div');
        panel.className = 'spc-detail';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-label', 'SPC product detail');
        panel.innerHTML = html;
        host.appendChild(panel);
        activeFeature = feat;
        positionPanel(latlng);
        wirePanel();
        document.addEventListener('keydown', onKeyDown);
        // Defer so the opening click does not immediately close the panel.
        setTimeout(() => { if (panel) map.on('click', close); }, 0);
    }

    return Object.freeze({
        openOutlook(latlng, feat, context) {
            if (!latlng || !feat) return;
            open(latlng, feat, buildSpcOutlookDetailHtml(feat, context));
        },
        openText(latlng, feat) {
            if (!latlng || !feat) return;
            open(latlng, feat, buildSpcTextDetailHtml(feat));
        },
        close,
        destroy: close,
    });
}
