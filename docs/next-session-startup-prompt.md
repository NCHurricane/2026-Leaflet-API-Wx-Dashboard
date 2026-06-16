# Next Session Startup Prompt

Date prepared: 2026-06-16

Start in:

```text
F:\Python\dashboard_2026_frontend_pages
```

Use this prompt:

```text
We are continuing the frontend product-page split in F:\Python\dashboard_2026_frontend_pages on branch codex/frontend-product-pages.

Current status:
- The fixed dashboard shell is accepted.
- Tropical reference UI is accepted.
- Route-level standalone candidates are working and accepted for this pass:
  /tropical, /alerts, /spc, /surface, /drought, /satellite, /radar, /mrms, /rtma.
- /surface maps to the existing current product mode.
- All split pages still share weather.html and js/weather.js through product-only route mode. No true per-product JS/HTML clean cut has been done yet.
- Phase 15A prep has started: js/product-page-shell.js now owns standalone product route/bootstrap setup, and js/alerts-page.js registers Alerts standalone entry metadata.
- Phase 15B prep has started: /alerts is served through serve_product_shell_page("alerts"), which injects product-page metadata into the shared weather shell without copying weather.html. js/alerts-page.js now owns Alerts category default/master/checked-category helpers, warning-filter visibility, and active-warning panel rendering/wiring.
- Phase 15C prep has started: js/product-app-context.js provides a product context registry, and js/weather.js registers the Alerts app context used by the extracted Alerts modules.
- js/alerts-engine.js now owns the context-backed Alerts live-response eligibility check, live Alerts loading orchestration, in-memory category refiltering, display-geometry refresh, Leaflet alert style/layer construction, and archive Alerts loading/frame slicing. js/weather.js still injects popup/detail presentation and new-alert notification banners.
- Do not remove combined-workspace code until the Phase 15 clean-cut strategy is confirmed.

Important SPC note:
- /spc initially failed to show Day 1 Categorical on hard refresh.
- The fix was to normalize SPC controls for standalone /spc and run _updateSpcReportFilterState() before the first refreshActiveLayers() call.
- Keep this startup ordering intact. If Day 1 Categorical only appears after toggling the checkbox, this ordering regressed.

Relevant files changed in this phase:
- routes/pages.py
- app_core/static_assets.py
- weather.html
- js/product-page-shell.js
- js/product-app-context.js
- js/alerts-engine.js
- js/alerts-page.js
- js/weather.js
- docs/product-page-shell-plan.md
- docs/refactor-playbook.md
- docs/next-session-startup-prompt.md

Verification already run:
- node --check js/weather.js
- python py_compile checks for main.py and routes/pages.py earlier in the split
- route smoke checks earlier returned 200 for /weather.html, /tropical, /alerts, /spc, /surface, /drought, /satellite, /radar, /mrms, /rtma
- manual browser testing confirmed all split pages working after the SPC startup fix

Known workspace note:
- start_server.txt may appear as untracked. Leave it alone unless explicitly asked.

Next agenda:
1. Review Phase 15 clean-cut strategy before editing.
2. Decide whether to split products into true per-product files one at a time or first extract shared frontend utilities from weather.js.
3. Start with the lowest-risk accepted page only after confirming the approach.
4. Keep /weather.html working until the user explicitly approves retiring or reducing the combined workspace.

Before making code changes, restate the proposed Phase 15 step and ask for confirmation if the request could change scope.
```
