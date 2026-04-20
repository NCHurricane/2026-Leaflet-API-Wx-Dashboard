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

## Open Questions

- Should international alerts get their own hazard categories or map into existing NWS categories?
- Should the worker poll frequency differ per source (e.g., ECCC every 2 min, WMO every 10 min)?
- Should the Region dropdown filter alerts by geographic bounds, or always show all alerts regardless of region?
- Archive support: IEM is US-only — what archive source for international alerts?
