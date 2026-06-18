(function () {
    'use strict';

    const byId = (id) => document.getElementById(id);
    const ARCHIVE_SCRUB_BASE_MS = 900;
    const DEFAULT_ARCHIVE_SPEED_INDEX = 2;
    const FLOATER_BASE = 'https://cdn.star.nesdis.noaa.gov/FLOATER';
    const FLOATER_LABELS = {
        GEOCOLOR: 'GeoColor',
        13: 'Clean IR (Band 13)',
        '02': 'Red Visible (Band 02)',
    };
    let pageContext = null;
    let archiveControlsWired = false;
    let archiveScrubberWired = false;
    let archiveAdvisories = [];
    let archiveFixes = [];
    let archiveMode = 'advisory';
    let archiveAdvisoryIndex = 0;
    let archiveFixIndex = 0;
    let archivePlaying = false;
    let archiveSpeedIndex = DEFAULT_ARCHIVE_SPEED_INDEX;
    let activeDetail = null;
    let floaterControlsWired = false;
    let floaterStormId = null;

    function configureTropicalPage(context) {
        pageContext = context || null;
    }

    function requirePageContext() {
        if (!pageContext) {
            throw new Error('Tropical page context has not been configured.');
        }
        return pageContext;
    }

    function stormLabel(storm) {
        const name = storm?.name || storm?.stormName || storm?.systemName || storm?.id || 'Unnamed';
        const type = storm?.classification || storm?.systemType || storm?.type || '';
        const basin = storm?.basinName || storm?.basin || '';
        return `${name}${type ? ` (${type})` : ''}${basin ? ` - ${basin}` : ''}`;
    }

    function archiveBasinName(catalog, basin) {
        return (catalog?.basinNames || {})[basin] || basin;
    }

    function formatArchiveDate(iso, withYear = false) {
        const date = new Date(`${iso}T00:00:00Z`);
        if (Number.isNaN(date.getTime())) return iso;
        return date.toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric',
            timeZone: 'UTC',
            ...(withYear ? { year: 'numeric' } : {}),
        });
    }

    function archiveDateRange(data) {
        const start = data?.startDate;
        const end = data?.endDate;
        if (!start) return null;
        return start === end
            ? formatArchiveDate(start, true)
            : `${formatArchiveDate(start, true)} – ${formatArchiveDate(end, true)}`;
    }

    function renderSummaryHeader(head, name, category) {
        if (!head) return;
        const context = requirePageContext();
        head.innerHTML = `<span class="wx-tropical-sum-name">${context.escapeHtml(name)}</span>`
            + `<span class="wx-tropical-cat-badge" style="--tc-cat:${category.color}">`
            + `<span class="wx-tropical-cat-dot" aria-hidden="true"></span>${context.escapeHtml(category.label)}</span>`;
    }

    function renderSummaryMetrics(summary, rows) {
        if (!summary) return;
        const context = requirePageContext();
        summary.innerHTML = rows.map(([label, value, modifier = '', isHtml = false]) => (
            `<div class="wx-tropical-metric${modifier}"><span>${context.escapeHtml(label)}</span>`
            + (isHtml ? value : `<strong>${context.escapeHtml(value)}</strong>`) + '</div>'
        )).join('');
    }

    function renderArchiveSummaryHead(data, head, summary) {
        const context = requirePageContext();
        const storm = data?.storm || {};
        const winds = (Array.isArray(data?.track) ? data.track : [])
            .map((point) => point.windKt)
            .filter((value) => Number.isFinite(value) && value > 0);
        const peakKt = winds.length ? Math.max(...winds) : null;
        const pressures = (data?.gis_layers?.best_track_points?.geojson?.features || [])
            .map((feature) => feature.properties?.MSLP)
            .filter((value) => Number.isFinite(value) && value > 0);
        const minimumPressure = pressures.length ? Math.min(...pressures) : null;
        const category = context.categoryFromWind(peakKt);
        const name = storm.name || data?.stormId || 'System';

        renderSummaryHeader(head, name, category);
        const peakMph = context.ktToMph(peakKt);
        const fixes = Array.isArray(data?.track) ? data.track.length : 0;
        renderSummaryMetrics(summary, [
            ['Dates', archiveDateRange(data) || '--', ' is-wide'],
            ['Peak wind', peakMph != null ? `${peakMph} mph` : '--'],
            ['Min pressure', Number.isFinite(minimumPressure) ? `${minimumPressure} mb` : '--'],
            ['Peak category', category.label],
            ['Track fixes', String(fixes)],
            ...(data?.gis_advisory ? [['Forecast', `Adv ${data.gis_advisory} (peak)`]] : []),
            ['Source', 'HURDAT2 best track', ' is-wide'],
        ]);
    }

    function renderArchiveAdvisorySummaryHead(data, head, summary) {
        const context = requirePageContext();
        const advisory = data.advisory || {};
        const mph = advisory.maxWindMph;
        const windKt = Number.isFinite(mph) ? Math.round(mph / 1.15078) : null;
        const category = context.categoryFromWind(windKt);
        const name = context.getArchiveStormName() || data.stormId || 'System';
        const step = data.advisoryStep || '—';

        renderSummaryHeader(head, name, category);
        const motion = advisory.motion
            ? `${advisory.motion.text || ''}${Number.isFinite(advisory.motion.mph) ? ` at ${advisory.motion.mph} mph` : ''}`.trim()
            : '--';
        const options = archiveAdvisories.map((advisoryStep, index) => (
            `<option value="${index}"${index === archiveAdvisoryIndex ? ' selected' : ''}>`
            + `Advisory ${context.escapeHtml(advisoryStep)}</option>`
        )).join('');
        const stepper = `<div class="wx-adv-stepper" role="group" aria-label="Select advisory">`
            + `<select class="wx-adv-select" aria-label="Choose advisory">${options}</select>`
            + '</div>';

        renderSummaryMetrics(summary, [
            ['Issued', data.issued || '--', ' is-wide'],
            ['Wind', Number.isFinite(mph) ? `${mph} mph` : '--'],
            ['Pressure', Number.isFinite(advisory.pressureMb) ? `${advisory.pressureMb} mb` : '--'],
            ['Motion', motion || '--'],
            ['Advisory', stepper, '', true],
            ['Location', advisory.location?.text || '--', ' is-wide'],
        ]);
    }

    function renderArchiveFixSummaryHead(data, head, summary) {
        const context = requirePageContext();
        const properties = data._fixFeature?.properties || {};
        const windKt = Number(properties.INTENSITY);
        const mph = Number.isFinite(windKt) ? Math.round(windKt * 1.15078) : null;
        const category = context.categoryFromProperties(properties);
        const name = context.getArchiveStormName() || data.stormId || 'System';

        renderSummaryHeader(head, name, category);
        const pressure = Number(properties.MSLP);
        const options = archiveFixes.map((fix, index) => (
            `<option value="${index}"${index === archiveFixIndex ? ' selected' : ''}>`
            + `${context.escapeHtml(context.formatFixDate(fix.properties?.DTG || ''))} `
            + `(${index + 1}/${archiveFixes.length})</option>`
        )).join('');
        const stepper = `<div class="wx-adv-stepper is-wide" role="group" aria-label="Select fix">`
            + `<select class="wx-adv-select" aria-label="Choose fix">${options}</select>`
            + '</div>';

        renderSummaryMetrics(summary, [
            ['Time', context.formatFixDate(properties.DTG), ' is-wide'],
            ['Wind', Number.isFinite(mph) ? `${mph} mph` : '--'],
            ['Pressure', Number.isFinite(pressure) && pressure > 0 ? `${pressure} mb` : '--'],
            ['Category', category.label, ' is-wide'],
            ['Fix', stepper, '', true, ' is-wide'],
            ['Position', context.formatLatLon(properties.LAT, properties.LON), ' is-wide'],
        ]);
    }

    function categoryShort(categoryKey) {
        return categoryKey === 'OTHER' ? '—' : categoryKey;
    }

    function tropicalTrackRows(data) {
        const context = requirePageContext();
        const geoJson = context.getTropicalGisGeoJson(data, 'forecast_points');
        if (Array.isArray(geoJson?.features) && geoJson.features.length) {
            return geoJson.features.map((feature) => {
                const properties = feature.properties || {};
                const coordinates = feature.geometry?.coordinates || [];
                const tau = Number(properties.TAU);
                return {
                    tau: Number.isFinite(tau) ? String(tau) : '--',
                    tauNum: Number.isFinite(tau) ? tau : 0,
                    time: properties.DATELBL || properties.FLDATELBL || properties.VALIDTIME || '--',
                    pos: context.formatLatLon(coordinates[1], coordinates[0]),
                    wind: Number.isFinite(Number(properties.MAXWIND))
                        ? `${Number(properties.MAXWIND)} kt`
                        : '--',
                    cat: categoryShort(context.categoryKeyFromProperties(properties)),
                };
            }).sort((first, second) => first.tauNum - second.tauNum);
        }

        return (Array.isArray(data?.track) ? data.track : []).map((point) => ({
            tau: String(point.hour ?? '--'),
            tauNum: point.hour === 'INIT' ? 0 : (Number(point.hour) || 0),
            time: point.time || '--',
            pos: context.formatLatLon(point.lat, point.lon),
            wind: Number.isFinite(Number(point.windKt)) ? `${Number(point.windKt)} kt` : '--',
            cat: categoryShort(context.categoryKeyFromWind(point.windKt)),
        }));
    }

    function renderTropicalTrack(data) {
        const context = requirePageContext();
        const box = byId('weather-tropical-track');
        if (!box) return;
        const rows = tropicalTrackRows(data).slice(0, 12);
        box.innerHTML = rows.length
            ? `<div class="wx-tropical-track-scroll"><table class="wx-tropical-track-table"><thead><tr><th>F TIME</th><th>Time</th><th>Position</th><th>Wind</th><th>Cat</th></tr></thead><tbody>${rows.map((row) => (
                `<tr><td>${context.escapeHtml(row.tau)}</td><td>${context.escapeHtml(row.time)}</td>`
                + `<td>${context.escapeHtml(row.pos)}</td><td>${context.escapeHtml(row.wind)}</td>`
                + `<td>${context.escapeHtml(row.cat)}</td></tr>`
            )).join('')}</tbody></table></div>`
            : '';
    }

    function renderTropicalProducts(data) {
        const context = requirePageContext();
        const box = byId('weather-tropical-products');
        if (!box) return;
        const products = data?.products || {};
        box.innerHTML = Object.keys(products)
            .filter((code) => products[code]?.text)
            .map((code) => (
                `<button type="button" data-tropical-product="${context.escapeHtml(code)}">`
                + `${context.escapeHtml(products[code].label || code)}</button>`
            )).join('');
        box.querySelectorAll('[data-tropical-product]').forEach((button) => {
            button.addEventListener('click', () => {
                context.openProductDetail(button.getAttribute('data-tropical-product'));
            });
        });
    }

    function renderTropicalGraphics(data) {
        const context = requirePageContext();
        const box = byId('weather-tropical-graphics');
        if (!box) return;
        const graphics = Array.isArray(data?.graphics) ? data.graphics : [];
        if (!graphics.length) {
            box.innerHTML = '';
            return;
        }

        box.innerHTML = '<div class="wx-tc-graphics-empty">Checking available graphics…</div>'
            + graphics.map((graphic, index) => (
                `<button type="button" class="wx-tc-graphic-btn" data-graphic-idx="${index}" hidden>`
                + `${context.escapeHtml(graphic.label || 'Graphic')}</button>`
            )).join('');

        const emptyNote = box.querySelector('.wx-tc-graphics-empty');
        let anyShown = false;
        graphics.forEach((graphic, index) => {
            const button = box.querySelector(`[data-graphic-idx="${index}"]`);
            if (!button || !graphic.url) return;
            button.addEventListener('click', () => {
                context.openGraphicDetail(graphic.url, graphic.label);
            });
            const probe = context.createImage();
            probe.onload = () => {
                button.hidden = false;
                if (!anyShown) {
                    anyShown = true;
                    emptyNote?.remove();
                }
            };
            probe.src = graphic.url;
        });

        context.setTimeoutFn(() => {
            if (!anyShown && emptyNote?.isConnected) {
                emptyNote.textContent = 'No graphics issued for this system yet.';
            }
        }, 8000);
    }

    function clearTropicalDetailLists() {
        ['weather-tropical-track', 'weather-tropical-products', 'weather-tropical-graphics']
            .forEach((id) => {
                const element = byId(id);
                if (element) element.innerHTML = '';
            });
    }

    function closeTropicalDetail() {
        if (!activeDetail) return;
        const { panel, keyHandler, dragCleanup } = activeDetail;
        document.removeEventListener('keydown', keyHandler);
        dragCleanup?.();
        panel?.remove();
        activeDetail = null;
    }

    function openTropicalDetailPanel(title, subtitle, bodyHtml, extraClass = '') {
        const context = requirePageContext();
        context.closeAlertDetail();
        closeTropicalDetail();

        const wrap = document.querySelector('.weather-map-wrap');
        if (!wrap) return null;
        const panel = document.createElement('div');
        panel.id = 'wx-tropical-detail';
        panel.className = `wx-new-alert-detail is-right${extraClass ? ` ${extraClass}` : ''}`;
        panel.innerHTML = [
            '<div class="wx-nad-header">',
            `<div class="wx-nad-title">${context.escapeHtml(title)}</div>`,
            '<button type="button" class="wx-nad-close" aria-label="Close tropical detail">X</button>',
            '</div>',
            subtitle ? `<div class="wx-nad-issued">${context.escapeHtml(subtitle)}</div>` : '',
            bodyHtml,
        ].join('');
        panel.addEventListener('click', (event) => event.stopPropagation());
        wrap.appendChild(panel);

        let drag = null;
        const onDragMove = (event) => {
            if (!drag) return;
            panel.style.left = `${event.clientX - drag.wrapLeft - drag.dx}px`;
            panel.style.top = `${event.clientY - drag.wrapTop - drag.dy}px`;
            panel.style.right = 'auto';
            panel.style.transform = 'none';
            panel.classList.remove('is-right', 'is-left');
        };
        const onDragUp = () => {
            drag = null;
            document.removeEventListener('pointermove', onDragMove);
            document.removeEventListener('pointerup', onDragUp);
        };
        const dragCleanup = () => {
            document.removeEventListener('pointermove', onDragMove);
            document.removeEventListener('pointerup', onDragUp);
        };
        const keyHandler = (event) => {
            if (event.key === 'Escape') closeTropicalDetail();
        };
        document.addEventListener('keydown', keyHandler);
        panel.querySelector('.wx-nad-close')?.addEventListener('click', closeTropicalDetail);
        panel.querySelector('.wx-nad-header')?.addEventListener('pointerdown', (event) => {
            if (event.target?.closest('.wx-nad-close, a, button')) return;
            const wrapRect = wrap.getBoundingClientRect();
            const panelRect = panel.getBoundingClientRect();
            panel.style.left = `${panelRect.left - wrapRect.left}px`;
            panel.style.top = `${panelRect.top - wrapRect.top}px`;
            panel.style.right = 'auto';
            panel.style.transform = 'none';
            panel.classList.remove('is-right', 'is-left');
            drag = {
                dx: event.clientX - panelRect.left,
                dy: event.clientY - panelRect.top,
                wrapLeft: wrapRect.left,
                wrapTop: wrapRect.top,
            };
            event.preventDefault();
            document.addEventListener('pointermove', onDragMove);
            document.addEventListener('pointerup', onDragUp);
        });
        activeDetail = { panel, keyHandler, dragCleanup };
        return panel;
    }

    function openTropicalProductDetail(productCode = 'TCP') {
        const context = requirePageContext();
        const data = context.getActiveStorm();
        const product = data?.products?.[productCode] || data?.products?.TCP;
        if (!data || !product?.text) {
            context.setStatus('No advisory text is available for this system yet.');
            return;
        }
        const title = `${data.stormId} ${product.label || product.code}`;
        const subtitle = product.meta?.pubDate || data.updated || '';
        openTropicalDetailPanel(
            title,
            subtitle,
            `<div class="wx-tropical-detail-body">${context.escapeHtml(product.text)}</div>`,
        );
    }

    function openTropicalGraphicDetail(url, label) {
        if (!url) return;
        const context = requirePageContext();
        const displayLabel = label || 'Storm graphic';
        const body = '<div class="wx-tropical-graphic-body">'
            + `<img src="${context.escapeHtml(url)}" alt="${context.escapeHtml(displayLabel)}" class="wx-tropical-graphic-img">`
            + '</div>';
        openTropicalDetailPanel(
            displayLabel,
            '',
            body,
            'wx-tropical-detail-graphic',
        );
    }

    function floaterUrl(stormId, product, size, cacheBust) {
        return `${FLOATER_BASE}/${stormId}/${product}/${size}.jpg?t=${cacheBust}`;
    }

    function hideTropicalFloater() {
        floaterStormId = null;
        const section = byId('wx-tropical-inspector-floater');
        if (section) section.hidden = true;
    }

    function renderTropicalFloater(stormId) {
        const context = requirePageContext();
        const section = byId('wx-tropical-inspector-floater');
        if (!section) return;
        const id = String(stormId || '').toUpperCase();
        if (!/^(AL|EP|CP)\d{6}$/.test(id)) {
            hideTropicalFloater();
            return;
        }

        floaterStormId = id;
        const probe = context.createImage();
        probe.onload = () => {
            if (floaterStormId === id) section.hidden = false;
        };
        probe.onerror = () => {
            if (floaterStormId === id) hideTropicalFloater();
        };
        probe.src = floaterUrl(id, 'GEOCOLOR', '250x250', context.floaterCacheBust());
    }

    function openFloaterModal(product) {
        if (!floaterStormId || !product) return;
        const context = requirePageContext();
        const url = floaterUrl(
            floaterStormId,
            product,
            '2000x2000',
            context.floaterCacheBust(),
        );
        openTropicalGraphicDetail(
            url,
            `Satellite Floater — ${FLOATER_LABELS[product] || product}`,
        );
    }

    function wireFloaterControls() {
        if (floaterControlsWired) return;
        floaterControlsWired = true;
        byId('wx-floater-pills')?.addEventListener('click', (event) => {
            const product = event.target?.getAttribute?.('data-floater-product');
            if (product) openFloaterModal(product);
        });
    }

    function archiveBadge(category) {
        const key = String(category || 'OTHER').toUpperCase();
        if (['1', '2', '3', '4', '5'].includes(key)) return `CAT ${key}`;
        return key === 'OTHER' ? '—' : key;
    }

    function archiveCardHtml(entry) {
        const context = requirePageContext();
        const color = context.categoryColor(entry.peakCategory);
        const badge = archiveBadge(entry.peakCategory);
        const wind = Number.isFinite(Number(entry.peakWindKt)) ? `${entry.peakWindKt} kt` : '—';
        const dates = entry.startDate === entry.endDate
            ? formatArchiveDate(entry.startDate)
            : `${formatArchiveDate(entry.startDate)} – ${formatArchiveDate(entry.endDate)}`;
        const landfall = entry.landfall ? 'landfall' : 'open water';

        return `<button type="button" class="wx-tropical-card" data-atcf-id="${context.escapeHtml(entry.id)}" style="--tc-cat-color:${color};">
                <span class="wx-tropical-card-bar"></span>
                <span class="wx-tropical-card-body">
                    <span class="wx-tropical-card-head">
                        <span class="wx-tropical-card-name">${context.escapeHtml(entry.name)}</span>
                        <span class="wx-tropical-card-badge">${context.escapeHtml(badge)}</span>
                        <span class="wx-tropical-card-class">${context.escapeHtml(entry.id)}</span>
                    </span>
                    <span class="wx-tropical-card-metrics">
                        <span class="wx-tropical-card-metric"><small>peak</small>${context.escapeHtml(wind)}</span>
                        <span class="wx-tropical-card-metric"><small>${context.escapeHtml(landfall)}</small>${context.escapeHtml(dates)}</span>
                    </span>
                </span>
            </button>`;
    }

    function highlightSelectedArchiveCard() {
        const context = requirePageContext();
        const selectedId = context.getSelectedArchiveId();
        document.querySelectorAll('#wx-archive-card-list .wx-tropical-card').forEach((card) => {
            const isSelected = card.getAttribute('data-atcf-id') === selectedId;
            card.classList.toggle('is-selected', isSelected);
            card.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
        });
    }

    function renderArchiveList() {
        const context = requirePageContext();
        const catalog = context.getArchiveCatalog();
        const box = byId('wx-archive-card-list');
        if (!box || !catalog) return;

        const basin = String(byId('wx-archive-basin')?.value || 'AL').toUpperCase();
        const year = String(byId('wx-archive-season')?.value || '');
        const entries = ((catalog.basins || {})[basin] || {})[year] || [];
        const sorted = [...entries].sort((a, b) => String(a.startDate).localeCompare(String(b.startDate)));
        const basinName = archiveBasinName(catalog, basin);

        if (!sorted.length) {
            box.innerHTML = `
                <div class="wx-tropical-empty-card">
                    <div class="wx-tropical-empty-title">No systems</div>
                    <div class="wx-tropical-empty-note">
                        No tropical systems recorded for the ${context.escapeHtml(basinName)} basin in ${context.escapeHtml(year)}.
                    </div>
                </div>`;
            context.setArchiveStatus(`No systems · ${year} ${basinName} season`);
            return;
        }

        box.innerHTML = sorted.map(archiveCardHtml).join('');
        box.querySelectorAll('.wx-tropical-card[data-atcf-id]').forEach((card) => {
            card.addEventListener('click', () => {
                context.selectArchiveStorm(card.getAttribute('data-atcf-id'));
            });
        });

        context.setArchiveStatus(
            `${sorted.length} storm${sorted.length === 1 ? '' : 's'} · ${year} ${basinName} season`,
        );
        highlightSelectedArchiveCard();
    }

    function populateArchiveSeasons() {
        const context = requirePageContext();
        const catalog = context.getArchiveCatalog();
        if (!catalog) return;

        const seasonSelect = byId('wx-archive-season');
        const basin = String(byId('wx-archive-basin')?.value || 'AL').toUpperCase();
        // Always offer the current year in every basin so the selection survives a
        // basin switch (an empty current season then shows "No systems" rather than
        // silently falling back to the basin's latest year with storms).
        const seasonSet = new Set(
            Object.keys((catalog.basins || {})[basin] || {}).map(Number),
        );
        seasonSet.add(new Date().getUTCFullYear());
        const seasons = [...seasonSet].sort((a, b) => b - a);

        if (seasonSelect) {
            const previous = seasonSelect.value;
            seasonSelect.innerHTML = '';
            seasons.forEach((year) => {
                const option = document.createElement('option');
                option.value = String(year);
                option.textContent = String(year);
                seasonSelect.appendChild(option);
            });
            if (seasons.includes(Number(previous))) seasonSelect.value = previous;
        }
        renderArchiveList();
    }

    function renderArchiveCatalog(catalog) {
        const basinSelect = byId('wx-archive-basin');
        const basins = Object.keys(catalog?.basins || {});

        if (basinSelect && basins.length) {
            const previous = basinSelect.value;
            basinSelect.innerHTML = '';
            basins.forEach((basin) => {
                const option = document.createElement('option');
                option.value = basin;
                option.textContent = archiveBasinName(catalog, basin);
                basinSelect.appendChild(option);
            });
            if (basins.includes(previous)) basinSelect.value = previous;
        }
        populateArchiveSeasons();
    }

    function wireArchiveControls() {
        if (archiveControlsWired) return;
        archiveControlsWired = true;
        byId('wx-archive-basin')?.addEventListener('change', populateArchiveSeasons);
        byId('wx-archive-season')?.addEventListener('change', renderArchiveList);
    }

    function archiveItems() {
        return archiveMode === 'besttrack' ? archiveFixes : archiveAdvisories;
    }

    function archiveScrubCount() {
        return archiveItems().length;
    }

    function archiveScrubIndex() {
        return archiveMode === 'besttrack' ? archiveFixIndex : archiveAdvisoryIndex;
    }

    function setArchiveScrubIndex(index) {
        if (archiveMode === 'besttrack') archiveFixIndex = index;
        else archiveAdvisoryIndex = index;
    }

    function archiveScrubDelay() {
        const context = requirePageContext();
        const speeds = context.getPlaybackSpeeds();
        const speed = speeds[archiveSpeedIndex] || 1;
        return Math.max(150, Math.round(ARCHIVE_SCRUB_BASE_MS / speed));
    }

    function updateArchiveScrubSpeedUi() {
        const context = requirePageContext();
        const speeds = context.getPlaybackSpeeds();
        const label = byId('adv-scrub-speed-label');
        if (label) label.textContent = context.formatPlaybackSpeed(speeds[archiveSpeedIndex] || 1);
    }

    function adjustArchiveScrubSpeed(delta) {
        const speeds = requirePageContext().getPlaybackSpeeds();
        const next = Math.max(
            0,
            Math.min(speeds.length - 1, archiveSpeedIndex + (Number(delta) || 0)),
        );
        if (next === archiveSpeedIndex) return;
        archiveSpeedIndex = next;
        updateArchiveScrubSpeedUi();
    }

    function renderArchiveScrubModeToggle() {
        const wrap = byId('adv-scrub-mode');
        if (!wrap) return;
        wrap.hidden = !(archiveAdvisories.length && archiveFixes.length);
        wrap.querySelectorAll('[data-scrub-mode]').forEach((button) => {
            const active = button.getAttribute('data-scrub-mode') === archiveMode;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
    }

    async function loadArchiveScrubIndex(index, options = {}) {
        const context = requirePageContext();
        if (archiveMode === 'besttrack') {
            return context.loadArchiveFix(index, options);
        }
        return context.loadArchiveAdvisory(archiveAdvisories[index], options);
    }

    function setArchiveScrubMode(mode) {
        if (mode === archiveMode) return;
        if (mode === 'advisory' && !archiveAdvisories.length) return;
        if (mode === 'besttrack' && !archiveFixes.length) return;
        stopArchiveScrubPlay();
        archiveMode = mode;
        setArchiveScrubIndex(0);
        loadArchiveScrubIndex(0, { fit: false, initial: true });
    }

    function renderArchiveScrubberBar() {
        const context = requirePageContext();
        const bar = byId('wx-tropical-adv-scrubber');
        if (!bar) return;
        const total = archiveScrubCount();
        if (!total) {
            hideArchiveScrubberBar();
            return;
        }

        bar.hidden = false;
        const index = archiveScrubIndex();
        const slider = byId('adv-scrub-slider');
        if (slider) {
            slider.max = String(total - 1);
            slider.value = String(index);
        }

        const label = byId('adv-scrub-label');
        if (label) {
            if (archiveMode === 'besttrack') {
                const dtg = archiveFixes[index]?.properties?.DTG;
                label.textContent = `Fix ${index + 1}/${total} · ${context.formatFixDate(dtg)}`;
            } else {
                const activeStorm = context.getActiveStorm();
                const step = activeStorm?.advisoryStep || archiveAdvisories[index] || '--';
                const issued = activeStorm?.issued || '';
                label.textContent = `Adv ${step} · ${index + 1}/${total}${issued ? ` · ${issued}` : ''}`;
            }
        }

        byId('adv-scrub-prev')?.toggleAttribute('disabled', index <= 0);
        byId('adv-scrub-first')?.toggleAttribute('disabled', index <= 0);
        byId('adv-scrub-next')?.toggleAttribute('disabled', index >= total - 1);
        byId('adv-scrub-last')?.toggleAttribute('disabled', index >= total - 1);
        updateArchiveScrubSpeedUi();
        renderArchiveScrubModeToggle();
    }

    function stopArchiveScrubPlay() {
        archivePlaying = false;
        const button = byId('adv-scrub-play');
        if (button) {
            button.classList.remove('is-playing');
            button.setAttribute('aria-pressed', 'false');
            button.innerHTML = '&#9654;';
        }
    }

    function hideArchiveScrubberBar() {
        stopArchiveScrubPlay();
        requirePageContext().clearArchiveFixHighlight();
        const bar = byId('wx-tropical-adv-scrubber');
        if (bar) bar.hidden = true;
    }

    async function startArchiveScrubPlay() {
        if (archivePlaying) return;
        const total = archiveScrubCount();
        if (total < 2) return;
        if (archiveScrubIndex() >= total - 1) setArchiveScrubIndex(0);

        archivePlaying = true;
        const button = byId('adv-scrub-play');
        if (button) {
            button.classList.add('is-playing');
            button.setAttribute('aria-pressed', 'true');
            button.innerHTML = '&#10073;&#10073;';
        }

        const sleep = (milliseconds) => new Promise((resolve) => {
            setTimeout(resolve, milliseconds);
        });
        while (archivePlaying && archiveScrubIndex() < archiveScrubCount() - 1) {
            setArchiveScrubIndex(archiveScrubIndex() + 1);
            await loadArchiveScrubIndex(archiveScrubIndex(), { fit: false });
            if (!archivePlaying) break;
            await sleep(archiveScrubDelay());
        }
        stopArchiveScrubPlay();
    }

    function stepArchiveScrub(delta) {
        stopArchiveScrubPlay();
        const total = archiveScrubCount();
        if (!total) return;
        const next = Math.max(0, Math.min(total - 1, archiveScrubIndex() + delta));
        if (next === archiveScrubIndex()) return;
        setArchiveScrubIndex(next);
        loadArchiveScrubIndex(next, { fit: false });
    }

    function jumpArchiveScrub(index) {
        stopArchiveScrubPlay();
        const total = archiveScrubCount();
        if (!total) return;
        const next = Math.max(0, Math.min(total - 1, Number(index) || 0));
        if (next === archiveScrubIndex()) return;
        setArchiveScrubIndex(next);
        loadArchiveScrubIndex(next, { fit: false });
    }

    function setArchiveAdvisoryMode(advisories) {
        archiveAdvisories = Array.isArray(advisories) ? advisories : [];
        archiveMode = 'advisory';
        archiveAdvisoryIndex = 0;
    }

    function setArchiveBestTrackMode() {
        archiveAdvisories = [];
        archiveMode = 'besttrack';
        archiveFixIndex = 0;
    }

    function setArchiveFixes(fixes) {
        archiveFixes = Array.isArray(fixes) ? fixes : [];
    }

    function resetArchiveScrubber() {
        archiveAdvisories = [];
        archiveFixes = [];
        archiveMode = 'advisory';
        archiveAdvisoryIndex = 0;
        archiveFixIndex = 0;
        hideArchiveScrubberBar();
    }

    function wireArchiveScrubberControls() {
        if (archiveScrubberWired) return;
        archiveScrubberWired = true;

        document.addEventListener('change', (event) => {
            if (event.target.classList.contains('wx-adv-select')) {
                jumpArchiveScrub(Number(event.target.value));
            }
        });
        byId('adv-scrub-first')?.addEventListener('click', () => jumpArchiveScrub(0));
        byId('adv-scrub-prev')?.addEventListener('click', () => stepArchiveScrub(-1));
        byId('adv-scrub-next')?.addEventListener('click', () => stepArchiveScrub(1));
        byId('adv-scrub-last')?.addEventListener('click', () => jumpArchiveScrub(archiveScrubCount() - 1));
        byId('adv-scrub-play')?.addEventListener('click', () => {
            if (archivePlaying) stopArchiveScrubPlay();
            else startArchiveScrubPlay();
        });
        byId('adv-scrub-speed-down')?.addEventListener('click', () => adjustArchiveScrubSpeed(-1));
        byId('adv-scrub-speed-up')?.addEventListener('click', () => adjustArchiveScrubSpeed(1));
        byId('adv-scrub-slider')?.addEventListener('input', (event) => {
            jumpArchiveScrub(Number(event.target.value));
        });
        byId('adv-scrub-mode')?.addEventListener('click', (event) => {
            const mode = event.target?.getAttribute?.('data-scrub-mode');
            if (mode) setArchiveScrubMode(mode);
        });
    }

    function syncSystemOptions(storms) {
        const select = byId('weather-tropical-system');
        if (!select) return;

        const list = Array.isArray(storms) ? storms : [];
        const previousId = String(select.value || '').toUpperCase();
        select.innerHTML = '';

        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = list.length ? 'Select a system' : 'No active systems';
        select.appendChild(placeholder);

        list.forEach((storm) => {
            const option = document.createElement('option');
            option.value = String(storm?.id || '').toUpperCase();
            option.textContent = stormLabel(storm);
            select.appendChild(option);
        });

        select.value = list.some((storm) => String(storm?.id || '').toUpperCase() === previousId)
            ? previousId
            : '';
    }

    function stormCardHtml(storm) {
        const context = requirePageContext();
        const stormId = String(storm?.id || '').toUpperCase();
        const name = storm?.name || stormId || 'Unnamed';
        const type = storm?.classification || storm?.systemType || '';
        const windMph = context.ktToMph(storm?.intensity);
        const pressure = Number(storm?.pressure);
        const color = context.pointColor(storm?.intensity);
        const metrics = [
            ['Wind', windMph != null ? `${windMph} mph` : '--'],
            ['Pressure', Number.isFinite(pressure) ? `${pressure} mb` : '--'],
            ['Motion', context.motionText(storm) || '--'],
        ];

        return `
            <button type="button" class="wx-tropical-card" data-storm-id="${context.escapeHtml(stormId)}" aria-pressed="false" style="--tc-cat-color:${color};">
                <span class="wx-tropical-card-bar" aria-hidden="true"></span>
                <span class="wx-tropical-card-body">
                    <span class="wx-tropical-card-head">
                        <span class="wx-tropical-card-name">${context.escapeHtml(name)}</span>
                        ${type ? `<span class="wx-tropical-card-badge">${context.escapeHtml(type)}</span>` : ''}
                    </span>
                    <span class="wx-tropical-card-class">${context.escapeHtml(context.windClass(storm?.intensity))}</span>
                    <span class="wx-tropical-card-metrics">${metrics.map(([label, value]) => (
        `<span class="wx-tropical-card-metric"><small>${context.escapeHtml(label)}</small>${context.escapeHtml(value)}</span>`
    )).join('')}</span>
                </span>
            </button>`;
    }

    function highlightSelectedCard() {
        const selectedId = String(byId('weather-tropical-system')?.value || '').trim().toUpperCase();
        document.querySelectorAll('#weather-tropical-system-cards .wx-tropical-card').forEach((card) => {
            const isSelected = card.getAttribute('data-storm-id') === selectedId;
            card.classList.toggle('is-selected', isSelected);
            card.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
        });
    }

    function renderStormList(storms) {
        const context = requirePageContext();
        const list = Array.isArray(storms) ? storms : [];
        syncSystemOptions(list);

        const box = byId('weather-tropical-system-cards');
        if (!box) return;

        const count = byId('weather-tropical-system-count');
        if (count) count.textContent = String(list.length);

        if (!list.length) {
            box.innerHTML = `
                <div class="wx-tropical-empty-card">
                    <div class="wx-tropical-empty-title">No active systems</div>
                    <div class="wx-tropical-empty-note">
                        The selected basin has no active tropical cyclones.
                    </div>
                </div>`;
            return;
        }

        box.innerHTML = list.map((storm) => stormCardHtml(storm)).join('');
        box.querySelectorAll('.wx-tropical-card').forEach((card) => {
            card.addEventListener('click', () => {
                context.selectStorm(card.getAttribute('data-storm-id'));
            });
        });
        highlightSelectedCard();
    }

    window.NCHTropicalPage = Object.freeze({
        archiveAdvisories: () => [...archiveAdvisories],
        archiveFixes: () => [...archiveFixes],
        archiveScrubCount,
        archiveScrubIndex,
        archiveScrubMode: () => archiveMode,
        closeTropicalDetail,
        configureTropicalPage,
        clearTropicalDetailLists,
        hideTropicalFloater,
        hideArchiveScrubberBar,
        highlightSelectedCard,
        highlightSelectedArchiveCard,
        jumpArchiveScrub,
        openFloaterModal,
        openTropicalGraphicDetail,
        openTropicalProductDetail,
        populateArchiveSeasons,
        renderArchiveCatalog,
        renderArchiveAdvisorySummaryHead,
        renderArchiveFixSummaryHead,
        renderArchiveList,
        renderArchiveSummaryHead,
        renderArchiveScrubberBar,
        renderStormList,
        renderTropicalGraphics,
        renderTropicalFloater,
        renderTropicalProducts,
        renderTropicalTrack,
        resetArchiveScrubber,
        setArchiveAdvisoryMode,
        setArchiveBestTrackMode,
        setArchiveFixes,
        setArchiveScrubMode,
        startArchiveScrubPlay,
        stepArchiveScrub,
        stopArchiveScrubPlay,
        syncSystemOptions,
        wireArchiveControls,
        wireArchiveScrubberControls,
        wireFloaterControls,
    });

    window.NCHProductPageShell?.registerProductPageEntry('tropical', {
        label: 'Tropical',
        title: 'Tropical — NCHurricane Dashboard',
        controller: window.NCHTropicalPage,
    });
}());
