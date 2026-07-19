// Preserved Phase 27 radar-dependent tools. The implementation is injected
// below from the validated legacy workspace and wrapped in this narrow API.
export function createWorkspaceTools(options) {
    const { map, leaflet: L, apiUrl, setStatus } = options;
    const byId = (id) => document.getElementById(id);
    const _escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
    let _allAlertFeatures = [];

    let _stormTrackLayer = L.layerGroup().addTo(map);
    let _stormTrackProjectionLayer = L.layerGroup().addTo(_stormTrackLayer);
    let _stormTrackHandleLayer = L.layerGroup().addTo(_stormTrackLayer);
    let _stormTrackDrawMode = false;
    let _stormTrackBaseLatLngs = [];
    let _stormTrackSelectedAlert = null;
    let _stormTrackMotion = null;
    let _stormTrackActiveBearingDeg = null;
    let _stormTrackPivotKeyDown = false;
    let _stormTrackDragAnchor = null;
    let _stormTrackDragHandle = null;
    let _stormTrackPlacesOverlayEl = null;
    let _stormTrackPlacesDataPromise = null;
    let _stormTrackPlacesComputeSeq = 0;
    let _stormTrackPlaceRows = [];
    const _STORM_TRACK_PLACE_TYPES = [
        { key: 'city', label: 'Cities' },
        { key: 'town', label: 'Towns' },
        { key: 'village', label: 'Villages' },
        { key: 'hamlet', label: 'Hamlets' },
    ];
    const _stormTrackPlaceTypeFilter = new Set(_STORM_TRACK_PLACE_TYPES.map((t) => t.key));
    let _stormTrackLastCorridorLatLngs = [];
    let _stormTrackOutlineLayer = null;
    const _STORM_TRACK_INTERVAL_MIN = 15;
    const _STORM_TRACK_WIDTH_GROWTH_PER_INTERVAL = 0.10;
    const _STORM_TRACK_PIVOT_MAX_DEG = 45;
    const _STORM_TRACK_MAX_PLACE_ROWS = 50;
    // ── Preserved workspace storm-motion tools ───────────────────────────────
    function _ringContainsPoint(ring, lng, lat) {
        let inside = false;
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
            const [xi, yi] = ring[i];
            const [xj, yj] = ring[j];
            const intersects = ((yi > lat) !== (yj > lat))
                && (lng < ((xj - xi) * (lat - yi)) / ((yj - yi) || Number.EPSILON) + xi);
            if (intersects) inside = !inside;
        }
        return inside;
    }

    const _CARDINAL_TO_BEARING = {
        N: 0,
        NNE: 22.5,
        NE: 45,
        ENE: 67.5,
        E: 90,
        ESE: 112.5,
        SE: 135,
        SSE: 157.5,
        S: 180,
        SSW: 202.5,
        SW: 225,
        WSW: 247.5,
        W: 270,
        WNW: 292.5,
        NW: 315,
        NNW: 337.5,
    };

    function _normalizeMotionDirection(rawDir) {
        return String(rawDir || '')
            .toUpperCase()
            .replace(/[^A-Z]/g, '');
    }

    function _directionToBearing(rawDir) {
        const norm = _normalizeMotionDirection(rawDir);
        if (_CARDINAL_TO_BEARING[norm] !== undefined) return _CARDINAL_TO_BEARING[norm];

        const words = String(rawDir || '').toUpperCase().replace(/[^A-Z\s]/g, ' ').replace(/\s+/g, ' ').trim();
        const alias = {
            NORTH: 'N',
            NORTHEAST: 'NE',
            EAST: 'E',
            SOUTHEAST: 'SE',
            SOUTH: 'S',
            SOUTHWEST: 'SW',
            WEST: 'W',
            NORTHWEST: 'NW',
        };
        if (alias[words] && _CARDINAL_TO_BEARING[alias[words]] !== undefined) {
            return _CARDINAL_TO_BEARING[alias[words]];
        }
        return null;
    }

    function _extractAlertMotion(feat) {
        const p = feat?.properties || {};
        const params = p.parameters || {};
        // Prefer the human-readable alert text direction first because it is
        // generally the best "storm moving toward" source for this workflow.
        const desc = String(p.description || '');
        const descMatch = desc.match(/MOVING\s+([A-Z\-\s]+?)\s+AT\s+(\d{1,3})\s*(MPH|KTS?|KT)\b/i);
        if (descMatch) {
            const bearing = _directionToBearing(descMatch[1]);
            const speed = Number(descMatch[2]);
            const unit = String(descMatch[3] || '').toUpperCase();
            if (Number.isFinite(bearing) && Number.isFinite(speed) && speed > 0) {
                const speedMps = unit.startsWith('MPH') ? speed * 0.44704 : speed * 0.514444;
                return { bearingDeg: bearing, speedMps, source: 'description' };
            }
        }

        const emd = Array.isArray(params.eventMotionDescription) ? String(params.eventMotionDescription[0] || '') : '';
        const emdMatch = emd.match(/(\d{1,3})\s*DEG[\s.]*?(\d{1,3})\s*K[TN]/i);
        if (emdMatch) {
            const bearing = Number(emdMatch[1]);
            const speedKt = Number(emdMatch[2]);
            if (Number.isFinite(bearing) && Number.isFinite(speedKt) && speedKt > 0) {
                // eventMotionDescription bearings can be encoded opposite the
                // intuitive "toward" direction. Flip by 180 so projected drag
                // aligns with storm-forward motion on the map.
                return {
                    bearingDeg: (((bearing + 180) % 360) + 360) % 360,
                    speedMps: speedKt * 0.514444,
                    source: 'eventMotionDescription',
                };
            }
        }
        return null;
    }

    function _stormTrackFallbackAlert() {
        if (featIsValid(_stormTrackSelectedAlert)) return _stormTrackSelectedAlert;
        const severe = (_allAlertFeatures || []).find((f) => {
            const evt = String(f?.properties?.event || '');
            return evt === 'Tornado Warning' || evt === 'Severe Thunderstorm Warning' || evt === 'Flash Flood Warning';
        });
        return severe || (_allAlertFeatures || [])[0] || null;
    }

    function featIsValid(feat) {
        return !!(feat && feat.type === 'Feature' && feat.properties);
    }

    function _offsetLatLngGeodesic(latlng, bearingDeg, distanceMeters) {
        const R = 6371000;
        const br = (bearingDeg * Math.PI) / 180;
        const lat1 = (latlng.lat * Math.PI) / 180;
        const lon1 = (latlng.lng * Math.PI) / 180;
        const dr = distanceMeters / R;

        const lat2 = Math.asin(
            Math.sin(lat1) * Math.cos(dr)
            + Math.cos(lat1) * Math.sin(dr) * Math.cos(br),
        );
        const lon2 = lon1 + Math.atan2(
            Math.sin(br) * Math.sin(dr) * Math.cos(lat1),
            Math.cos(dr) - Math.sin(lat1) * Math.sin(lat2),
        );

        return L.latLng((lat2 * 180) / Math.PI, (lon2 * 180) / Math.PI);
    }

    function _bearingBetweenLatLng(fromLatLng, toLatLng) {
        const lat1 = (fromLatLng.lat * Math.PI) / 180;
        const lat2 = (toLatLng.lat * Math.PI) / 180;
        const dLon = ((toLatLng.lng - fromLatLng.lng) * Math.PI) / 180;
        const y = Math.sin(dLon) * Math.cos(lat2);
        const x = Math.cos(lat1) * Math.sin(lat2)
            - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
        const br = (Math.atan2(y, x) * 180) / Math.PI;
        return ((br % 360) + 360) % 360;
    }

    function _signedBearingDeltaDeg(fromBearing, toBearing) {
        let d = (((toBearing - fromBearing) % 360) + 360) % 360;
        if (d > 180) d -= 360;
        return d;
    }

    function _normalizeBearingDeg(bearingDeg) {
        return (((Number(bearingDeg) % 360) + 360) % 360);
    }

    function _pivotedBearingDeg(rawBearingDeg) {
        const baseBearing = _stormTrackMotion?.bearingDeg;
        if (!Number.isFinite(baseBearing)) return null;
        if (!_stormTrackPivotKeyDown) return _normalizeBearingDeg(baseBearing);
        const raw = _normalizeBearingDeg(rawBearingDeg);
        const delta = _signedBearingDeltaDeg(baseBearing, raw);
        const clamped = Math.max(-_STORM_TRACK_PIVOT_MAX_DEG, Math.min(_STORM_TRACK_PIVOT_MAX_DEG, delta));
        return _normalizeBearingDeg(baseBearing + clamped);
    }

    function _projectMetersOnMotion(anchor, point, motionBearingDeg) {
        const distance = anchor.distanceTo(point);
        if (!Number.isFinite(distance) || distance <= 0) return 0;
        const ptBearing = _bearingBetweenLatLng(anchor, point);
        const delta = _signedBearingDeltaDeg(motionBearingDeg, ptBearing);
        const alongPrimary = distance * Math.cos((delta * Math.PI) / 180);
        return Math.max(0, alongPrimary);
    }

    function _stormTrackAnchor(basePts) {
        if (!Array.isArray(basePts) || !basePts.length) return null;
        let sumLat = 0;
        let sumLng = 0;
        for (const pt of basePts) {
            sumLat += pt.lat;
            sumLng += pt.lng;
        }
        return L.latLng(sumLat / basePts.length, sumLng / basePts.length);
    }

    function _stateAbbrFromPlaceRecord(rec) {
        const iso = String(rec?.address?.['ISO3166-2-lvl4'] || '').toUpperCase();
        const m = iso.match(/^US-([A-Z]{2})$/);
        if (m) return m[1];
        return '';
    }

    function _parseNdjsonPlaces(text) {
        const rows = [];
        const lines = String(text || '').split(/\r?\n/);
        for (const line of lines) {
            const raw = line.trim();
            if (!raw) continue;
            try {
                const rec = JSON.parse(raw);
                const loc = Array.isArray(rec?.location) ? rec.location : [];
                const lng = Number(loc[0]);
                const lat = Number(loc[1]);
                if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
                const name = String(rec?.name || '').trim();
                if (!name) continue;
                const popRaw = Number(rec?.population);
                rows.push({
                    name,
                    state: _stateAbbrFromPlaceRecord(rec),
                    lat,
                    lng,
                    type: String(rec?.type || '').toLowerCase(),
                    population: Number.isFinite(popRaw) ? popRaw : null,
                });
            } catch (_) {
                // Skip malformed lines.
            }
        }
        return rows;
    }

    async function _loadStormTrackPlacesData() {
        if (_stormTrackPlacesDataPromise) return _stormTrackPlacesDataPromise;
        _stormTrackPlacesDataPromise = (async () => {
            // Categorize by source file, not by each record's heterogeneous OSM
            // `type` (city records are tagged "administrative", etc.).
            const sources = [
                { path: 'data/place_city.ndjson', category: 'city' },
                { path: 'data/place-town.ndjson', category: 'town' },
                { path: 'data/place-village.ndjson', category: 'village' },
                { path: 'data/place-hamlet.ndjson', category: 'hamlet' },
            ];
            const urls = sources.map((s) => apiUrl(s.path));
            const responses = await Promise.all(urls.map((u) => fetch(u, { cache: 'force-cache' })));
            const texts = await Promise.all(responses.map(async (resp, idx) => {
                if (!resp.ok) {
                    const path = sources[idx]?.path || 'places file';
                    throw new Error(`Failed loading ${path} (${resp.status}).`);
                }
                return resp.text();
            }));
            const merged = [];
            texts.forEach((txt, idx) => {
                const category = sources[idx].category;
                for (const rec of _parseNdjsonPlaces(txt)) {
                    rec.type = category;
                    merged.push(rec);
                }
            });
            return merged;
        })().catch((err) => {
            _stormTrackPlacesDataPromise = null;
            const baseMsg = String(err?.message || err || 'unknown error');
            if (window.location.protocol === 'file:') {
                throw new Error(`${baseMsg} Open the workspace via http://127.0.0.1:8000/workspace (run python main.py), not via file://.`);
            }
            throw err;
        });
        return _stormTrackPlacesDataPromise;
    }

    function _stormTrackPlaceTimeZone(place) {
        try {
            if (typeof window.tzlookup === 'function') {
                return String(window.tzlookup(place.lat, place.lng) || '').trim();
            }
        } catch (_) {
            // fallback below
        }
        return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    }

    function _formatStormTrackArrivalMs(ms, ianaTz) {
        const d = new Date(ms);
        try {
            return new Intl.DateTimeFormat(undefined, {
                hour: 'numeric',
                minute: '2-digit',
                timeZone: ianaTz,
                timeZoneName: 'short',
            }).format(d);
        } catch (_) {
            return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
        }
    }

    function _ensureStormTrackPlacesOverlay() {
        const wrap = document.querySelector('.weather-map-wrap');
        if (!wrap) return null;
        if (_stormTrackPlacesOverlayEl?.parentElement === wrap) return _stormTrackPlacesOverlayEl;

        const panel = document.createElement('div');
        panel.className = 'wx-stormtrack-places';
        panel.innerHTML = [
            '<div class="wx-stormtrack-places-head"><span class="wx-stormtrack-places-head-title">Projected Arrival Times</span><button type="button" class="wx-stormtrack-places-close" aria-label="Close projected arrival times">X</button>',
            '<div class="wx-small">Times are approximate</div></div>',
            '<div class="wx-stormtrack-places-body"><div class="wx-stormtrack-empty">No projected arrival times yet.</div></div>',
        ].join('');
        wrap.appendChild(panel);

        const head = panel.querySelector('.wx-stormtrack-places-head');
        const closeBtn = panel.querySelector('.wx-stormtrack-places-close');
        let drag = null;
        const onMove = (evt) => {
            if (!drag) return;
            const x = evt.clientX - drag.wrapLeft - drag.dx;
            const y = evt.clientY - drag.wrapTop - drag.dy;
            panel.style.left = `${x}px`;
            panel.style.top = `${y}px`;
            panel.style.right = 'auto';
        };
        const onUp = () => {
            drag = null;
            document.removeEventListener('pointermove', onMove);
            document.removeEventListener('pointerup', onUp);
        };
        head?.addEventListener('pointerdown', (evt) => {
            if (evt.target && evt.target.closest('.wx-stormtrack-places-close')) return;
            const wrapRect = wrap.getBoundingClientRect();
            const rect = panel.getBoundingClientRect();
            drag = {
                dx: evt.clientX - rect.left,
                dy: evt.clientY - rect.top,
                wrapLeft: wrapRect.left,
                wrapTop: wrapRect.top,
            };
            evt.preventDefault();
            document.addEventListener('pointermove', onMove);
            document.addEventListener('pointerup', onUp);
        });
        closeBtn?.addEventListener('click', (evt) => {
            evt.preventDefault();
            evt.stopPropagation();
            panel.remove();
            if (_stormTrackPlacesOverlayEl === panel) {
                _stormTrackPlacesOverlayEl = null;
            }
        });

        _stormTrackPlacesOverlayEl = panel;
        return panel;
    }

    function _renderStormTrackPlacesRows(rows) {
        const panel = _ensureStormTrackPlacesOverlay();
        if (!panel) return;
        const body = panel.querySelector('.wx-stormtrack-places-body');
        if (!body) return;

        if (!Array.isArray(rows) || !rows.length) {
            body.innerHTML = '<div class="wx-stormtrack-empty">No places inside the current projected polygon.</div>';
            return;
        }

        const knownTypes = new Set(_STORM_TRACK_PLACE_TYPES.map((t) => t.key));
        const visible = rows.filter((r) => !knownTypes.has(r.type) || _stormTrackPlaceTypeFilter.has(r.type));

        const filterBar = _STORM_TRACK_PLACE_TYPES.map((t) => {
            const active = _stormTrackPlaceTypeFilter.has(t.key);
            return `<button type="button" class="wx-stormtrack-filter${active ? ' is-active' : ''}" data-place-type="${t.key}" aria-pressed="${active}">${t.label}</button>`;
        }).join('');

        const listItems = visible.map((r) => {
            const state = r.state ? `, ${r.state}` : '';
            return [
                '<li>',
                `<span class="wx-stormtrack-place-name">${_escapeHtml(r.name)}${_escapeHtml(state)}</span>`,
                `<span class="wx-stormtrack-place-time">${_escapeHtml(r.arrivalLabel)}</span>`,
                '</li>',
            ].join('');
        }).join('');

        const listHtml = visible.length
            ? `<ol class="wx-stormtrack-places-list">${listItems}</ol>`
            : '<div class="wx-stormtrack-empty">No places match the selected types.</div>';
        body.innerHTML = `<div class="wx-stormtrack-filters">${filterBar}</div>${listHtml}`;

        body.querySelectorAll('.wx-stormtrack-filter').forEach((btn) => {
            btn.addEventListener('click', () => {
                const key = btn.getAttribute('data-place-type');
                if (!key) return;
                if (_stormTrackPlaceTypeFilter.has(key)) {
                    _stormTrackPlaceTypeFilter.delete(key);
                } else {
                    _stormTrackPlaceTypeFilter.add(key);
                }
                _renderStormTrackPlacesRows(_stormTrackPlaceRows);
            });
        });
    }

    async function _computeStormTrackPlaceRows(motion, activeBearing, minsAhead, corridorLatLngs) {
        const places = await _loadStormTrackPlacesData();
        const anchor = _stormTrackDragAnchor;
        if (!anchor || !Array.isArray(corridorLatLngs) || corridorLatLngs.length < 3) return [];

        const ring = corridorLatLngs.map((pt) => [pt.lng, pt.lat]);
        const nowMs = Date.now();
        const maxMins = Math.max(0, Number(minsAhead) || 0);
        const speedMps = Number(motion?.speedMps);
        if (!Number.isFinite(speedMps) || speedMps <= 0) return [];

        const rows = [];
        for (const place of places) {
            if (!_ringContainsPoint(ring, place.lng, place.lat)) continue;
            const meters = _projectMetersOnMotion(anchor, L.latLng(place.lat, place.lng), activeBearing);
            const mins = Math.max(0, meters / (speedMps * 60));
            if (mins > maxMins + 1e-6) continue;
            const arrivalMs = nowMs + (mins * 60_000);
            const tz = _stormTrackPlaceTimeZone(place);
            rows.push({
                name: place.name,
                state: place.state,
                arrivalMins: mins,
                arrivalLabel: `${_formatStormTrackArrivalMs(arrivalMs, tz)} (+${Math.round(mins)}m)`,
                population: place.population,
                type: place.type,
            });
        }

        rows.sort((a, b) => {
            const dt = a.arrivalMins - b.arrivalMins;
            if (Math.abs(dt) > 1e-6) return dt;
            const ap = Number.isFinite(a.population) ? a.population : -1;
            const bp = Number.isFinite(b.population) ? b.population : -1;
            return bp - ap;
        });

        return rows.slice(0, _STORM_TRACK_MAX_PLACE_ROWS);
    }

    function _scalePolylineFromCentroid(latLngs, scaleFactor) {
        if (!Array.isArray(latLngs) || latLngs.length < 2) return latLngs;
        const scale = Number(scaleFactor);
        if (!Number.isFinite(scale) || scale <= 0) return latLngs;
        if (Math.abs(scale - 1) < 1e-6) return latLngs.map((pt) => L.latLng(pt.lat, pt.lng));

        const centroid = _stormTrackAnchor(latLngs);
        if (!centroid) return latLngs;

        return latLngs.map((pt) => {
            const distanceMeters = centroid.distanceTo(pt);
            if (!Number.isFinite(distanceMeters) || distanceMeters <= 0) {
                return L.latLng(pt.lat, pt.lng);
            }
            const bearingDeg = _bearingBetweenLatLng(centroid, pt);
            return _offsetLatLngGeodesic(centroid, bearingDeg, distanceMeters * scale);
        });
    }

    function _clearStormTrackProjection() {
        _stormTrackProjectionLayer.clearLayers();
    }

    function _clearStormTrackLayer() {
        _stormTrackProjectionLayer.clearLayers();
        _stormTrackHandleLayer.clearLayers();
        _stormTrackDragHandle = null;
        _stormTrackDragAnchor = null;
        _stormTrackMotion = null;
        _stormTrackActiveBearingDeg = null;
        _stormTrackLastCorridorLatLngs = [];
        _stormTrackPlaceRows = [];
        if (_stormTrackPlacesOverlayEl) {
            _stormTrackPlacesOverlayEl.remove();
            _stormTrackPlacesOverlayEl = null;
        }
        if (_stormTrackOutlineLayer) {
            try { map.removeLayer(_stormTrackOutlineLayer); } catch (_) { /* ignore */ }
            _stormTrackOutlineLayer = null;
        }
    }

    function _setStormTrackDrawMode(enabled) {
        _stormTrackDrawMode = !!enabled;
        const startBtn = byId('wx-stormtrack-start');
        if (startBtn) startBtn.classList.toggle('is-active', _stormTrackDrawMode);
        const container = map?.getContainer?.();
        if (container) container.style.cursor = _stormTrackDrawMode ? 'crosshair' : '';
        if (_stormTrackDrawMode) {
            setStatus('Storm track draw mode: click map points, then click Finish Line.');
        }
    }

    function _renderStormTrackProjectionFromMinutes(aheadMinutes, bearingOverrideDeg = null) {
        if (_stormTrackBaseLatLngs.length < 2) {
            setStatus('Draw at least two points before projecting storm track.');
            return null;
        }
        const motion = _stormTrackMotion;
        if (!motion || !Number.isFinite(motion.speedMps) || motion.speedMps <= 0) {
            setStatus('No valid motion vector available for storm-track projection.');
            return null;
        }

        const basePts = _stormTrackBaseLatLngs.map((pt) => L.latLng(pt.lat, pt.lng));
        const minsAhead = Math.max(0, Number(aheadMinutes) || 0);
        const activeBearing = Number.isFinite(bearingOverrideDeg)
            ? _normalizeBearingDeg(bearingOverrideDeg)
            : (Number.isFinite(_stormTrackActiveBearingDeg)
                ? _normalizeBearingDeg(_stormTrackActiveBearingDeg)
                : _normalizeBearingDeg(motion.bearingDeg));
        _stormTrackActiveBearingDeg = activeBearing;
        const currentMeters = motion.speedMps * minsAhead * 60;
        const widthScaleNow = 1 + (_STORM_TRACK_WIDTH_GROWTH_PER_INTERVAL * (minsAhead / _STORM_TRACK_INTERVAL_MIN));
        const currentFrontRaw = basePts.map((pt) => _offsetLatLngGeodesic(pt, activeBearing, currentMeters));
        const currentFront = _scalePolylineFromCentroid(currentFrontRaw, widthScaleNow);
        const fadeSpanMins = Math.max(_STORM_TRACK_INTERVAL_MIN, minsAhead || _STORM_TRACK_INTERVAL_MIN);
        const nowFadeT = Math.max(0, Math.min(1, minsAhead / fadeSpanMins));
        const currentFrontOpacity = 0.99 - (0.75 * nowFadeT);
        const currentFrontFillOpacity = 0.50 - (0.18 * nowFadeT);

        _clearStormTrackProjection();
        let corridor = [];
        if (minsAhead > 0 && basePts.length >= 2 && currentFront.length === basePts.length) {
            corridor = [...basePts, ...[...currentFront].reverse()];
            L.polygon(corridor, {
                color: '#22e8ff',
                weight: 1,
                opacity: 0.5,
                fillColor: '#22e8ff',
                fillOpacity: Math.max(0.12, currentFrontFillOpacity),
                interactive: false,
            }).addTo(_stormTrackProjectionLayer);
        }
        L.polyline(basePts, {
            color: '#cbd5e1',
            weight: 1.5,
            opacity: 0.55,
            dashArray: '2 6',
        }).addTo(_stormTrackProjectionLayer);

        L.polyline(currentFront, {
            color: '#22e8ff',
            weight: 2.5,
            opacity: Math.max(0.35, currentFrontOpacity),
            dashArray: '9 6',
        }).addTo(_stormTrackProjectionLayer);

        if (minsAhead > 0) {
            const liveAnchor = currentFront[currentFront.length - 1];
            L.marker(liveAnchor, {
                interactive: false,
                icon: L.divIcon({
                    className: 'wx-stormtrack-label',
                    html: `+${Math.round(minsAhead)}m`,
                }),
            }).addTo(_stormTrackProjectionLayer);
        }

        const maxInterval = Math.floor(minsAhead / _STORM_TRACK_INTERVAL_MIN) * _STORM_TRACK_INTERVAL_MIN;
        for (let mins = _STORM_TRACK_INTERVAL_MIN; mins <= maxInterval; mins += _STORM_TRACK_INTERVAL_MIN) {
            const distanceMeters = motion.speedMps * mins * 60;
            const widthScale = 1 + (_STORM_TRACK_WIDTH_GROWTH_PER_INTERVAL * (mins / _STORM_TRACK_INTERVAL_MIN));
            const shiftedRaw = basePts.map((pt) => _offsetLatLngGeodesic(pt, activeBearing, distanceMeters));
            const shifted = _scalePolylineFromCentroid(shiftedRaw, widthScale);
            const fadeT = Math.max(0, Math.min(1, mins / fadeSpanMins));
            const shiftedOpacity = 0.92 - (0.55 * fadeT);
            L.polyline(shifted, {
                color: '#7dd3fc',
                weight: 2,
                opacity: Math.max(0.35, shiftedOpacity),
                dashArray: '7 7',
            }).addTo(_stormTrackProjectionLayer);
            const labelAnchor = shifted[shifted.length - 1];
            L.marker(labelAnchor, {
                interactive: false,
                icon: L.divIcon({
                    className: 'wx-stormtrack-label',
                    html: `+${mins}m`,
                }),
            }).addTo(_stormTrackProjectionLayer);
        }

        _stormTrackLastCorridorLatLngs = corridor;
        return {
            minsAhead,
            activeBearing,
            corridorLatLngs: corridor,
        };
    }

    function _installStormTrackDragHandle() {
        if (!_stormTrackDragAnchor) return;
        _stormTrackHandleLayer.clearLayers();
        const initialMinutes = _STORM_TRACK_INTERVAL_MIN;
        const initialMeters = _stormTrackMotion
            ? _stormTrackMotion.speedMps * initialMinutes * 60
            : 0;
        const initialPos = (_stormTrackMotion && initialMeters > 0)
            ? _offsetLatLngGeodesic(_stormTrackDragAnchor, _stormTrackMotion.bearingDeg, initialMeters)
            : _stormTrackDragAnchor;

        _stormTrackDragHandle = L.marker(initialPos, {
            draggable: true,
            keyboard: false,
            icon: L.divIcon({
                className: 'wx-stormtrack-drag-handle',
                html: '\u25c9',
                iconSize: [32, 32],
                iconAnchor: [16, 16],
            }),
        });
        _stormTrackDragHandle.addTo(_stormTrackHandleLayer);
        _stormTrackDragHandle.on('drag', (evt) => {
            if (!_stormTrackMotion || !_stormTrackDragAnchor) return;
            const handleLatLng = evt?.target?.getLatLng?.();
            if (!handleLatLng) return;
            const rawBearing = _bearingBetweenLatLng(_stormTrackDragAnchor, handleLatLng);
            const activeBearing = _pivotedBearingDeg(rawBearing);
            const meters = Math.max(0, _projectMetersOnMotion(_stormTrackDragAnchor, handleLatLng, activeBearing));
            const snappedLatLng = _offsetLatLngGeodesic(_stormTrackDragAnchor, activeBearing, meters);
            evt.target.setLatLng(snappedLatLng);
            const mins = meters / (_stormTrackMotion.speedMps * 60);
            _renderStormTrackProjectionFromMinutes(mins, activeBearing);
        });
        _stormTrackDragHandle.on('dragend', async (evt) => {
            if (!_stormTrackMotion || !_stormTrackDragAnchor) return;
            const handleLatLng = evt?.target?.getLatLng?.();
            if (!handleLatLng) return;
            const rawBearing = _bearingBetweenLatLng(_stormTrackDragAnchor, handleLatLng);
            const activeBearing = _pivotedBearingDeg(rawBearing);
            const meters = Math.max(0, _projectMetersOnMotion(_stormTrackDragAnchor, handleLatLng, activeBearing));
            const snappedLatLng = _offsetLatLngGeodesic(_stormTrackDragAnchor, activeBearing, meters);
            evt.target.setLatLng(snappedLatLng);
            const mins = meters / (_stormTrackMotion.speedMps * 60);
            const renderState = _renderStormTrackProjectionFromMinutes(mins, activeBearing);
            const baseBearing = _stormTrackMotion?.bearingDeg;
            const pivotDelta = Number.isFinite(baseBearing)
                ? Math.round(_signedBearingDeltaDeg(baseBearing, activeBearing))
                : 0;
            setStatus(`Storm-track projection updated to +${Math.round(mins)} minutes (pivot ${pivotDelta >= 0 ? '+' : ''}${pivotDelta}\u00b0).`);

            if (!renderState?.corridorLatLngs?.length) {
                _stormTrackPlaceRows = [];
                _renderStormTrackPlacesRows(_stormTrackPlaceRows);
                return;
            }
            const reqSeq = ++_stormTrackPlacesComputeSeq;
            setStatus(`Storm-track projection updated to +${Math.round(mins)} minutes (pivot ${pivotDelta >= 0 ? '+' : ''}${pivotDelta}deg). Computing place arrivals...`);
            try {
                const rows = await _computeStormTrackPlaceRows(_stormTrackMotion, activeBearing, mins, renderState.corridorLatLngs);
                if (reqSeq !== _stormTrackPlacesComputeSeq) return;
                _stormTrackPlaceRows = rows;
                _renderStormTrackPlacesRows(rows);
                setStatus(`Storm-track projection updated to +${Math.round(mins)} minutes (pivot ${pivotDelta >= 0 ? '+' : ''}${pivotDelta}deg). ${rows.length} place${rows.length === 1 ? '' : 's'} listed.`);
            } catch (err) {
                if (reqSeq !== _stormTrackPlacesComputeSeq) return;
                _stormTrackPlaceRows = [];
                _renderStormTrackPlacesRows(_stormTrackPlaceRows);
                const msg = String(err?.message || err || 'unknown error');
                setStatus(`Place arrival computation failed: ${msg}`);
            }
        });
    }

    function _activateStormTrackDragProjection() {
        if (_stormTrackBaseLatLngs.length < 2) {
            setStatus('Draw at least two points before finishing storm track.');
            return;
        }
        const alertFeat = _stormTrackFallbackAlert();
        const motion = _extractAlertMotion(alertFeat);
        if (!motion) {
            setStatus('No motion vector found on the selected alert. Open an alert detail first, then try again.');
            return;
        }

        // Apply manual speed override if the field has a valid value.
        const overrideKt = parseFloat(byId('wx-speed-override')?.value || '');
        if (Number.isFinite(overrideKt) && overrideKt > 0) {
            motion.speedMps = overrideKt * 0.514444;
        }

        _stormTrackMotion = motion;
        _stormTrackActiveBearingDeg = motion.bearingDeg;
        _stormTrackDragAnchor = _stormTrackAnchor(_stormTrackBaseLatLngs);
        _renderStormTrackProjectionFromMinutes(_STORM_TRACK_INTERVAL_MIN);
        _installStormTrackDragHandle();

        // Draw cyan selection outline on the alert polygon being used.
        if (_stormTrackOutlineLayer) {
            try { map.removeLayer(_stormTrackOutlineLayer); } catch (_) { /* ignore */ }
            _stormTrackOutlineLayer = null;
        }
        if (alertFeat?.geometry) {
            try {
                _stormTrackOutlineLayer = L.geoJSON({ type: 'Feature', geometry: alertFeat.geometry }, {
                    style: { color: '#22e8ff', weight: 3, opacity: 0.9, fillOpacity: 0 },
                    interactive: false,
                }).addTo(map);
            } catch (_) { /* ignore malformed geometry */ }
        }

        const evt = String(alertFeat?.properties?.event || 'alert');
        const speedNote = (Number.isFinite(overrideKt) && overrideKt > 0)
            ? ` [speed override: ${Math.round(overrideKt)} kt]` : '';
        setStatus(`Drag the marker forward to project ${evt} at ${_STORM_TRACK_INTERVAL_MIN}-minute intervals (${motion.source}).${speedNote} Hold Shift to pivot up to \u00b1${_STORM_TRACK_PIVOT_MAX_DEG}\u00b0.`);
    }

    function _clearSpeedOverride() {
        const input = byId('wx-speed-override');
        if (input) input.value = '';
    }

    byId('wx-stormtrack-start')?.addEventListener('click', () => {
        _clearStormTrackLayer();
        _stormTrackBaseLatLngs = [];
        _setStormTrackDrawMode(true);
    });

    byId('wx-stormtrack-finish')?.addEventListener('click', () => {
        _setStormTrackDrawMode(false);
        _activateStormTrackDragProjection();
    });

    byId('wx-stormtrack-clear')?.addEventListener('click', () => {
        _setStormTrackDrawMode(false);
        _stormTrackBaseLatLngs = [];
        _clearStormTrackLayer();
        setStatus('Storm track projection cleared.');
    });

    byId('wx-speed-override-clear')?.addEventListener('click', () => {
        _clearSpeedOverride();
    });

    document.addEventListener('keydown', (evt) => {
        if (evt.key === 'Shift') _stormTrackPivotKeyDown = true;
    });
    document.addEventListener('keyup', (evt) => {
        if (evt.key === 'Shift') _stormTrackPivotKeyDown = false;
    });

    map.on('click', (evt) => {
        if (!_stormTrackDrawMode) {
            const hasProjection = !!_stormTrackMotion
                || !!_stormTrackDragHandle
                || (_stormTrackProjectionLayer.getLayers().length > 0)
                || !!_stormTrackPlacesOverlayEl;
            if (hasProjection) {
                _stormTrackBaseLatLngs = [];
                _clearStormTrackLayer();
                setStatus('Storm track projection cleared.');
            }
            return;
        }
        const latlng = evt?.latlng;
        if (!latlng) return;
        _stormTrackBaseLatLngs.push(L.latLng(latlng.lat, latlng.lng));
        _clearStormTrackProjection();
        _stormTrackHandleLayer.clearLayers();
        if (_stormTrackBaseLatLngs.length >= 2) {
            L.polyline(_stormTrackBaseLatLngs, {
                color: '#f8fafc',
                weight: 2.5,
                opacity: 0.95,
            }).addTo(_stormTrackProjectionLayer);
        } else {
            L.circleMarker(_stormTrackBaseLatLngs[0], {
                radius: 4,
                color: '#f8fafc',
                fillColor: '#f8fafc',
                fillOpacity: 1,
                weight: 1,
            }).addTo(_stormTrackProjectionLayer);
        }
    });

    return Object.freeze({
        setAlerts(features) { _allAlertFeatures = Array.isArray(features) ? features : []; },
        setSelectedAlert(feature) { _stormTrackSelectedAlert = feature || null; },
        isDrawing() { return _stormTrackDrawMode; },
        clear() { _clearStormTrackLayer(); },
    });
}
