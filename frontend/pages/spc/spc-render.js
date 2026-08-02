import {
    CIG_OVERLAY_BY_HAZARD,
    SPC_CAT_COLORS,
    SPC_FIRE_COLORS,
    SPC_PROB_COLORS,
    SPC_REPORT_COLORS,
    SPC_REPORT_FA_ICON,
    cigIntensity,
    convectiveLabel,
    featureIsCig,
    highestFeatureAtPoint,
    isCigOverlayHazard,
    isFireHazard,
    nonZeroDn,
    reportTypeKey,
} from './spc-engine.js';

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
}

// SVG hatch patterns for CIG (conditional intensity) zones. Patterns live in
// the map's overlay SVG <defs> and are re-created whenever Leaflet rebuilds it.
function ensureCigPatternDefs(svgRoot) {
    if (!svgRoot) return;
    let defs = svgRoot.querySelector('defs');
    if (!defs) {
        defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        svgRoot.insertBefore(defs, svgRoot.firstChild);
    }
    const hasPattern = (id) => !!defs.querySelector(`#${id}`);
    const makeLine = (x1, y1, x2, y2, dash) => {
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', String(x1));
        line.setAttribute('y1', String(y1));
        line.setAttribute('x2', String(x2));
        line.setAttribute('y2', String(y2));
        line.setAttribute('stroke', 'black');
        line.setAttribute('stroke-width', '4');
        if (dash) line.setAttribute('stroke-dasharray', dash);
        return line;
    };
    const makePattern = (id, size, rotate) => {
        const pattern = document.createElementNS('http://www.w3.org/2000/svg', 'pattern');
        pattern.setAttribute('id', id);
        pattern.setAttribute('patternUnits', 'userSpaceOnUse');
        pattern.setAttribute('width', String(size));
        pattern.setAttribute('height', String(size));
        pattern.setAttribute('patternTransform', `rotate(${rotate})`);
        return pattern;
    };

    if (!hasPattern('hatch-cig-1')) {
        // Intensity 1: dashed diagonal lines at 45°.
        const pattern = makePattern('hatch-cig-1', 10, 45);
        pattern.appendChild(makeLine(0, 0, 0, 10, '4,6'));
        defs.appendChild(pattern);
    }
    if (!hasPattern('hatch-cig-2')) {
        // Intensity 2: solid diagonal lines at -45°.
        const pattern = makePattern('hatch-cig-2', 18, -45);
        pattern.appendChild(makeLine(0, 0, 0, 18));
        defs.appendChild(pattern);
    }
    if (!hasPattern('hatch-cig-3')) {
        // Intensity 3: cross-hatch.
        const pattern = makePattern('hatch-cig-3', 18, 45);
        pattern.appendChild(makeLine(0, 0, 0, 18));
        pattern.appendChild(makeLine(0, 0, 18, 0));
        defs.appendChild(pattern);
    }
}

export function createSpcRenderer(mapCore, { onOutlookDetail, onTextDetail, onDetailPages } = {}) {
    const leaflet = mapCore.leaflet;
    const map = mapCore.map;
    let layerGroup = null;
    let fillOpacity = 1.0;
    let strokeOpacity = 1.0;

    function featureColors(feat, fallback) {
        const stroke = feat?.properties?.stroke || feat?.properties?.STROKE || fallback.stroke;
        const fill = feat?.properties?.fill || feat?.properties?.FILL || fallback.fill;
        return { stroke, fill };
    }

    function catStyle(feat) {
        const label = (feat?.properties?.LABEL || feat?.properties?.label || '').toUpperCase();
        const c = featureColors(feat, SPC_CAT_COLORS[label] || { fill: '#aaaaaa', stroke: '#555' });
        return { color: c.stroke, weight: 1, fillColor: c.fill, fillOpacity, opacity: strokeOpacity };
    }

    function fireStyle(feat) {
        const label = feat?.properties?.LABEL || feat?.properties?.label || '';
        const c = featureColors(feat, SPC_FIRE_COLORS[label] || { fill: '#aaaaaa', stroke: '#555' });
        return { color: c.stroke, weight: 1, fillColor: c.fill, fillOpacity, opacity: strokeOpacity };
    }

    // Probability and CIG zones share one style fn: CIG zones get a heavier
    // stroke plus an SVG hatch fill applied after the path exists.
    function probCigStyle(feat) {
        const dn = String(feat?.properties?.dn ?? feat?.properties?.DN ?? '').trim();
        const label = String(feat?.properties?.LABEL || feat?.properties?.label || '').toUpperCase();
        const isCig = featureIsCig(feat);
        const labelDigits = (label.match(/CIG\s*([123])/) || [])[1] || '';
        const key = isCig ? `CIG${labelDigits || '1'}` : (dn || label.replace('%', ''));
        const c = featureColors(feat, SPC_PROB_COLORS[key] || { fill: '#aaaaaa', stroke: '#555555' });
        return {
            color: c.stroke,
            weight: isCig ? 2 : 1,
            fillColor: c.fill,
            fillOpacity,
            opacity: strokeOpacity,
        };
    }

    function watchStyle(feat) {
        const type = String(feat?.properties?.watch_type || feat?.properties?.event || '').toLowerCase();
        const color = type.includes('tornado') ? '#ffe066' : '#ff8ec7';
        return { color, weight: 2, fillColor: color, fillOpacity: 0.16, opacity: 1 };
    }

    function mdStyle() {
        return { color: '#63d8ff', weight: 1.8, fillColor: '#63d8ff', fillOpacity: 0.12, opacity: 1 };
    }

    function styleFnFor(hazard) {
        if (isFireHazard(hazard)) return fireStyle;
        if (['prob', 'torn', 'wind', 'hail'].includes(hazard) || isCigOverlayHazard(hazard)) {
            return probCigStyle;
        }
        return catStyle;
    }

    function applyCigPattern(feat, layer) {
        if (!featureIsCig(feat)) return;
        const label = String(feat?.properties?.LABEL || feat?.properties?.label || '').toUpperCase();
        const intensity = (label.match(/CIG\s*([123])/) || [])[1] || '1';
        if (layer?._path) {
            ensureCigPatternDefs(layer._path.ownerSVGElement);
            layer._path.setAttribute('fill', `url(#hatch-cig-${intensity})`);
            layer._path.setAttribute('fill-opacity', String(fillOpacity));
        }
    }

    function applyCigPatternsToGroup(group) {
        if (!group || typeof group.eachLayer !== 'function') return;
        group.eachLayer((child) => {
            if (typeof child.eachLayer === 'function') {
                child.eachLayer((sub) => applyCigPattern(sub?.feature, sub));
            } else {
                applyCigPattern(child?.feature, child);
            }
        });
    }

    function reportMarker(feat, latlng) {
        const key = reportTypeKey(feat?.properties?.event);
        const color = SPC_REPORT_COLORS[key] || SPC_REPORT_COLORS.other;
        const faClass = SPC_REPORT_FA_ICON[key];
        if (faClass) {
            const icon = leaflet.divIcon({
                className: '',
                html: `<i class="${faClass}" style="color:${color};font-size:16px;-webkit-text-stroke:0.5px #08111d;text-shadow:0 0 3px rgba(0,0,0,0.7);"></i>`,
                iconSize: [16, 16],
                iconAnchor: [8, 8],
                popupAnchor: [0, -10],
            });
            return leaflet.marker(latlng, { icon });
        }
        return leaflet.circleMarker(latlng, {
            radius: 5, color: '#08111d', weight: 1, fillColor: color, fillOpacity: 0.95, opacity: 1,
        });
    }

    function reportPopup(feat) {
        const p = feat?.properties || {};
        const magnitude = p.magnitude ? ` (${escapeHtml(p.magnitude)})` : '';
        const place = [p.location, p.county, p.state].filter(Boolean).join(', ');
        const when = p.time ? `<br><em>Time:</em> ${escapeHtml(p.time)}` : '';
        const where = place ? `<br><em>Location:</em> ${escapeHtml(place)}` : '';
        const remarks = p.remarks ? `<br><small>${escapeHtml(p.remarks)}</small>` : '';
        return `<strong>${escapeHtml(p.event || 'Storm Report')}${magnitude}</strong>${when}${where}${remarks}`;
    }

    function bindHoverTooltip(layer, text) {
        layer.bindTooltip(text, { sticky: true, opacity: 0.9, className: 'spc-hover-tip' });
    }

    function textFeatureKey(feature, kind) {
        const props = feature?.properties || {};
        return `${kind}:${String(
            props.watch_number || props.id || feature?.id || props.event || props.sent || '',
        )}`;
    }

    function featureContainsPoint(feature, latlng) {
        return Boolean(highestFeatureAtPoint([feature], latlng, () => 0));
    }

    function detailPagesAtPoint(bundle, latlng, preferredKey) {
        const outlookByHazard = new Map(
            (bundle.outlooks || []).map((payload) => [payload.hazard, payload.geojson]),
        );
        const pages = [];
        (bundle.outlooks || []).forEach((payload) => {
            if (isFireHazard(payload.hazard) || isCigOverlayHazard(payload.hazard)) return;
            const feature = highestFeatureAtPoint(
                (payload.geojson?.features || []).filter((candidate) => nonZeroDn(candidate) && !featureIsCig(candidate)),
                latlng,
                (candidate) => Number(candidate?.properties?.DN ?? candidate?.properties?.dn ?? 0),
            );
            if (!feature) return;
            const significantHazard = CIG_OVERLAY_BY_HAZARD[payload.hazard];
            const significantGeojson = outlookByHazard.get(significantHazard);
            const significantFeature = highestFeatureAtPoint(
                significantGeojson?.features || [], latlng, cigIntensity,
            );
            pages.push({
                kind: 'outlook',
                key: `outlook:${payload.hazard}`,
                label: `Day ${bundle.effectiveDay} ${convectiveLabel(payload.hazard, bundle.effectiveDay)}`,
                feature,
                context: {
                    day: bundle.effectiveDay,
                    hazard: payload.hazard,
                    detail: payload.geojson?._outlook_detail || {},
                    significantFeature,
                },
            });
        });

        const seenWatches = new Set();
        (bundle.watches?.features || []).forEach((feature) => {
            if (!featureContainsPoint(feature, latlng)) return;
            const key = textFeatureKey(feature, 'watch');
            if (seenWatches.has(key)) return;
            seenWatches.add(key);
            const props = feature?.properties || {};
            const watchNumber = props.watch_number ? ` #${Number(props.watch_number) || props.watch_number}` : '';
            pages.push({
                kind: 'text', key,
                label: `${props.watch_type || props.event || 'Watch'}${watchNumber}`,
                feature,
            });
        });

        const seenMds = new Set();
        (bundle.mds?.features || []).forEach((feature) => {
            if (!featureContainsPoint(feature, latlng)) return;
            const key = textFeatureKey(feature, 'md');
            if (seenMds.has(key)) return;
            seenMds.add(key);
            const props = feature?.properties || {};
            pages.push({
                kind: 'text', key,
                label: props.short_label || props.event || 'Mesoscale Discussion',
                feature,
            });
        });

        const preferredIndex = pages.findIndex((page) => page.key === preferredKey);
        if (preferredIndex > 0) pages.unshift(...pages.splice(preferredIndex, 1));
        return pages;
    }

    function openDetailPages(bundle, latlng, preferredKey) {
        const pages = detailPagesAtPoint(bundle, latlng, preferredKey);
        if (pages.length) onDetailPages?.(latlng, pages);
    }

    function buildOutlookLayer(payload, outlookByHazard, effectiveDay, bundle) {
        const { hazard, geojson } = payload;
        const fire = isFireHazard(hazard);
        const cigOverlay = isCigOverlayHazard(hazard);
        const baseProbOrCat = ['cat', 'torn', 'wind', 'hail', 'prob'].includes(hazard);
        const styleFn = cigOverlay ? probCigStyle : styleFnFor(hazard);

        const geoLayer = leaflet.geoJSON(geojson, {
            style: styleFn,
            filter: (feat) => {
                if (fire) return nonZeroDn(feat);
                if (cigOverlay) return nonZeroDn(feat);
                if (baseProbOrCat && !nonZeroDn(feat)) return false;
                // Base probabilistic layers frequently include embedded CIG
                // features; they render only via the dedicated cig layer.
                if (baseProbOrCat && featureIsCig(feat)) return false;
                return true;
            },
            onEachFeature: (feat, layer) => {
                if (fire) {
                    layer.on('click', (evt) => {
                        if (!evt?.latlng) return;
                        onOutlookDetail?.(evt.latlng, feat, {
                            day: effectiveDay,
                            hazard,
                            detail: geojson?._outlook_detail || {},
                            significantFeature: null,
                            isFire: true,
                        });
                    });
                    bindHoverTooltip(layer, String(
                        feat?.properties?.LABEL2 || feat?.properties?.LABEL || 'Fire Weather Outlook',
                    ));
                } else {
                    layer.on('click', (evt) => {
                        const clickLatLng = evt?.latlng;
                        if (!clickLatLng) return;

                        let modalFeature = feat;
                        let modalHazard = hazard;
                        let significantFeature = null;
                        let detail = geojson?._outlook_detail || {};

                        if (cigOverlay) {
                            // Clicking a hatched Sig zone opens the base outlook
                            // detail with the strongest Sig feature attached.
                            modalHazard = hazard.replace(/^cig/, '');
                            significantFeature = highestFeatureAtPoint(
                                geojson?.features || [], clickLatLng, cigIntensity,
                            ) || feat;
                            const baseGeojson = outlookByHazard.get(modalHazard);
                            const baseFeatures = (baseGeojson?.features || []).filter(
                                (candidate) => nonZeroDn(candidate) && !featureIsCig(candidate),
                            );
                            const baseFeature = highestFeatureAtPoint(
                                baseFeatures, clickLatLng,
                                (candidate) => Number(candidate?.properties?.DN || 0),
                            );
                            if (baseFeature) modalFeature = baseFeature;
                            if (baseGeojson?._outlook_detail) detail = baseGeojson._outlook_detail;
                        } else {
                            const significantHazard = CIG_OVERLAY_BY_HAZARD[hazard];
                            const significantGeojson = outlookByHazard.get(significantHazard);
                            significantFeature = highestFeatureAtPoint(
                                significantGeojson?.features || [], clickLatLng, cigIntensity,
                            );
                        }

                        if (onDetailPages) {
                            openDetailPages(bundle, clickLatLng, `outlook:${modalHazard}`);
                            return;
                        }
                        onOutlookDetail?.(clickLatLng, modalFeature, {
                            day: effectiveDay,
                            hazard: modalHazard,
                            detail,
                            significantFeature,
                        });
                    });
                    bindHoverTooltip(layer, String(
                        feat?.properties?.LABEL2 || feat?.properties?.LABEL || 'SPC Outlook',
                    ));
                }
                // _path exists only after the layer is added to the map.
                layer.on('add', () => applyCigPattern(feat, layer));
            },
        });
        geoLayer._spcHazard = hazard;
        geoLayer._spcStyleFn = styleFn;
        return geoLayer;
    }

    function render(bundle) {
        clear();
        const group = leaflet.layerGroup();
        const outlookByHazard = new Map(
            (bundle.outlooks || []).map((payload) => [payload.hazard, payload.geojson]),
        );

        (bundle.outlooks || []).forEach((payload) => {
            group.addLayer(buildOutlookLayer(payload, outlookByHazard, bundle.effectiveDay, bundle));
        });

        if (bundle.reports?.features?.length) {
            group.addLayer(leaflet.geoJSON(bundle.reports, {
                pointToLayer: (feat, latlng) => reportMarker(feat, latlng),
                onEachFeature: (feat, layer) => layer.bindPopup(reportPopup(feat)),
            }));
        }

        if (bundle.watches?.features?.length) {
            group.addLayer(leaflet.geoJSON(bundle.watches, {
                style: watchStyle,
                onEachFeature: (feat, layer) => {
                    layer.on('click', (evt) => {
                        if (onDetailPages) openDetailPages(bundle, evt?.latlng, textFeatureKey(feat, 'watch'));
                        else onTextDetail?.(evt?.latlng, feat);
                    });
                    bindHoverTooltip(layer, String(
                        feat?.properties?.short_label || feat?.properties?.event || 'Watch',
                    ));
                },
            }));
        }

        if (bundle.mds?.features?.length) {
            group.addLayer(leaflet.geoJSON(bundle.mds, {
                style: mdStyle,
                onEachFeature: (feat, layer) => {
                    layer.on('click', (evt) => {
                        if (onDetailPages) openDetailPages(bundle, evt?.latlng, textFeatureKey(feat, 'md'));
                        else onTextDetail?.(evt?.latlng, feat);
                    });
                    bindHoverTooltip(layer, String(
                        feat?.properties?.short_label || feat?.properties?.event || 'MD',
                    ));
                },
            }));
        }

        layerGroup = group;
        layerGroup.addTo(map);
        applyCigPatternsToGroup(layerGroup);
    }

    function restyle() {
        if (!layerGroup) return;
        layerGroup.eachLayer((layer) => {
            if (typeof layer.setStyle === 'function' && layer._spcStyleFn) {
                layer.setStyle(layer._spcStyleFn);
            }
        });
        applyCigPatternsToGroup(layerGroup);
    }

    function setFillOpacity(value) {
        const parsed = parseFloat(value);
        if (!Number.isFinite(parsed)) return;
        fillOpacity = parsed;
        restyle();
    }

    function setStrokeOpacity(value) {
        const parsed = parseFloat(value);
        if (!Number.isFinite(parsed)) return;
        strokeOpacity = parsed;
        restyle();
    }

    function featuresInView(features) {
        const bounds = map.getBounds();
        return (features || []).filter((feat) => {
            try {
                return leaflet.geoJSON(feat).getBounds().intersects(bounds);
            } catch {
                return false;
            }
        });
    }

    function zoomToFeature(feat) {
        try {
            const bounds = leaflet.geoJSON(feat).getBounds();
            if (bounds.isValid()) map.flyToBounds(bounds, { padding: [24, 24], duration: 0.9 });
        } catch { /* ignore invalid geometry */ }
    }

    function clear() {
        if (layerGroup && map.hasLayer(layerGroup)) map.removeLayer(layerGroup);
        layerGroup = null;
    }

    return Object.freeze({
        render,
        clear,
        destroy: clear,
        featuresInView,
        setFillOpacity,
        setStrokeOpacity,
        zoomToFeature,
    });
}
