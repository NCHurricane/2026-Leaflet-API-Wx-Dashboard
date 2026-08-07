# Next Session Startup Prompt

Use this prompt to resume work in `F:\Python\dashboard_2026` without importing
the superseded chronological backlog into active context.

---

Work in `F:\Python\dashboard_2026`.

Read, in order:

1. `AGENTS.md`
2. `docs/next-session-startup-prompt.md`
3. `docs/dashboard-change-and-enhancement-superfile.md`
4. `docs/architecture.md` and `docs/patterns.md` only as needed for the selected
   slice
5. `git status --short --ignored` and the latest commits

`docs/token-saver-maybe.md` is an optional ignored local guide. It is not an
installed skill, does not auto-trigger, and tracked work must not depend on it.

The active plan is the current superfile. Older planning sources are preserved
unchanged under `docs/archive/2026-08-07-consolidation-sources/`; consult them
only when exact history is needed. Do not reactivate a historical proposal
merely because it appears there.

Current boundary:

- The repository-wide retained-tree audit and the documentation consolidation
  are complete.
- Audit findings are candidates, not authorization to delete or refactor.
- No whole tracked application source file was found safe for immediate
  deletion.
- Preserve unrelated dirty work. Do not commit unless explicitly asked.
- Greenfield NCH Weather Studio is a separate project.

Default next discussion:

- Select one Cleanup Wave A safety-net family and the bounded cleanup/correction
  it protects.
- Recommended options are route serialization plus `/api/mrms/products`, or
  Surface normalization/archive coverage plus its confirmed correctness issues.
- State exact scope, dependencies, verification, and exclusions before editing.

Decisions that must not drift:

- Radar WebGL’s retained expansion is exactly `L2_RHO`, `L3_N0C`, `L3_DPR`,
  `L3_DAA`, and `L3_DTA`; PNG remains authority/fallback. Broader WebGL is
  parked, and Radar PNG retirement/tile-server migration are rejected.
- Filtered Reflectivity and AWS notifications are removed from the plan.
- The shared Alerts proposal is browser-page-only, national, deduplicated across
  non-Workspace tabs, and active only while a non-Workspace dashboard page and
  the local server are open. It uses the existing six-event Workspace allowlist.
  Alerts-page clicks select/zoom in place; other-page clicks open `/alerts` in a
  new tab and select/zoom. Workspace keeps its own notifications. There is no
  Windows background service or OS notification path.
- Keep current bounded RTMA/MRMS history; only a measured bounded 24/48-hour
  option remains eligible. Unbounded retention is rejected.
- Remove unreachable Satellite registry recipes/branches as cleanup candidates;
  do not preserve them as speculative products.
- Keep `tl_2025_us_state.*`; only the separate dead international-boundary
  bundle is a removal candidate.
- Persistent cross-process leases are closed unless deployment changes.

Validation language must stay exact:

- Unit/static/API/native-decode tests are not controlled-browser proof.
- A static `browser_smoke` suite is not an executed browser test.
- Runtime checks should restart/probe the actual listener and use cache-busted
  assets before browser claims.
- Inspect frame/source metadata when diagnosing RTMA/MRMS fallback.

Begin by reporting the Git state and the bounded slice you intend to work on.
Ask only if a missing choice would materially change scope; otherwise inspect
and proceed within the selected authorization.

---

If the prior session did not commit the documentation consolidation, review its
diff before selecting new implementation work. The consolidation should show
the eight source documents as renames into the dated archive, plus new active
superfile/startup content and corrections to the documentation index,
architecture, patterns, and ignored local token guide.
