# Alerts Enhancements — Future Work

Status: Planning reference
Date: 2026-04-19

## Current State

- **Data sources:** NWS API (`api.weather.gov/alerts/active`) with IEM WatchWarn fallback (`mesonet.agron.iastate.edu`)
- **Coverage:** US-only (all 50 states + territories)
- **Alert taxonomy:** NWS VTEC system — 101 event types in `config/alerts_config.py`
- **Archive source:** IEM shapefile endpoint (sole source for historical alerts)
- **Worker:** `alerts_worker` runs every 2 min, caches to `cache/alerts/national.geojson`

---

## International Alert Sources

### Tier 1 — Easiest Integration

| Source | Coverage | Format | URL | Notes |
|---|---|---|---|---|
| **Environment Canada (ECCC)** | Canada | CAP XML | `https://dd.weather.gc.ca/alerts/cap/` | Closest to NWS format; free; well-structured polygons |

### Tier 2 — Moderate Effort

| Source | Coverage | Format | URL | Notes |
|---|---|---|---|---|
| **MeteoAlarm** | Europe (37 countries) | CAP XML / GeoJSON | `https://meteoalarm.org` | Official EUMETNET service; highest quality for EU |
| **Bureau of Meteorology** | Australia | CAP XML | `ftp://ftp.bom.gov.au/anon/gen/fwo/` | Standard CAP integration |
| **JMA** | Japan | CAP XML | Via WMO hub or direct feeds | Good polygon quality |

### Tier 3 — Broadest but Variable Quality

| Source | Coverage | Format | URL | Notes |
|---|---|---|---|---|
| **WMO Alerting Hub** | Global (all WMO members) | CAP 1.2 XML | `https://alert.wmo.int` | Single integration point for global coverage; alert detail and polygon quality varies widely by country |
| **GDACS** | Global | GeoJSON / RSS / CAP | `https://gdacs.org` | Natural disasters only (earthquakes, floods, cyclones); EU-funded |

---

## Integration Requirements (per source)

Each new international source would require:

1. **Fetch module** — New Python module (like `alerts_iem_utils.py`) with source-specific API/feed parsing
2. **CAP XML parser** — Common Alerting Protocol parser (shared across CAP-based sources)
3. **Alert type mapping** — Map foreign alert types into the existing color/priority system in `alerts_config.py`
4. **New entries in `ALERT_COLORS` and `ALERT_PRIORITY`** — For any alert types not in the NWS taxonomy
5. **New `HAZARD_CATEGORIES` entries** — Or mapping foreign types into existing categories
6. **Merged cache layer** — Combine multiple sources into a single GeoJSON cache for the frontend
7. **Worker update** — Extend `alerts_worker` or add new workers per source
8. **Frontend JS** — `ALERT_CATEGORIES` and `ALERT_COLORS` in `js/weather.js` must stay in sync with config

---

## Suggested Implementation Order

1. **ECCC (Canada)** — Lowest friction, geographically adjacent, same CAP format
2. **MeteoAlarm (Europe)** — Best quality-to-effort ratio for non-North American coverage
3. **WMO Alerting Hub** — True global coverage as a final tier

---

---

## Console Test Scripts (New Alert Banner)

Two functions are exposed on `window` in `js/weather.js` for testing the new-alert banner popup. They are **always present** (not gated behind a flag) — call them from the browser DevTools console.

### `_testAlertBanner(eventOrFeat, areaDesc, severity)`

Fires a single synthetic banner with a fake polygon centered on the current map view.

```js
// Default — Tornado Warning, Severe (triggers immersive detail panel)
_testAlertBanner()

// Custom event type and area
_testAlertBanner('Severe Thunderstorm Warning', 'Wake County, NC')
_testAlertBanner('Flash Flood Warning', 'Buncombe County, NC')

// Force a specific severity (e.g. test the fallback pager popup)
_testAlertBanner('Severe Thunderstorm Warning', 'Wake County, NC', 'Moderate')

// Pass a real GeoJSON Feature directly (optional severity override)
_testAlertBanner(someFeatureObject)
_testAlertBanner(someFeatureObject, null, 'Severe')
```

### `_testAlertBannerFromJson(sourceOrUrl, severityOverride)`

Fires banners for every feature in a FeatureCollection — accepts either a URL or a JS object. Pass `severityOverride` to force the immersive detail flow.

```js
// From a local API endpoint
_testAlertBannerFromJson('/api/data/alerts')

// Force immersive detail panel for every feature
_testAlertBannerFromJson('/api/data/alerts', 'Severe')

// From a local test fixture file (served statically)
_testAlertBannerFromJson('/data/test_severe_thunderstorm_warning.json')

// From an inline object
_testAlertBannerFromJson({ type: 'FeatureCollection', features: [ /* ... */ ] })
```

### Notes
- The banner auto-dismisses after its configured timeout (same as real alerts).
- `_knownAlertIds` state is **not** mutated by these test calls — real alert detection is unaffected.
- To test the pulse animation on alert polygons, load real alerts first then call `_testAlertBanner`.

---

## Open Questions

- Should international alerts get their own hazard categories or map into existing NWS categories?
- Should the worker poll frequency differ per source (e.g., ECCC every 2 min, WMO every 10 min)?
- Should the Region dropdown filter alerts by geographic bounds, or always show all alerts regardless of region?
- Archive support: IEM is US-only — what archive source for international alerts?
