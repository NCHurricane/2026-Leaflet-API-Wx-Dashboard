# Dashboard Documentation

This directory separates current operating truth from historical evidence.

## Start here

- [`next-session-startup-prompt.md`](next-session-startup-prompt.md) — concise
  handoff for a new work session.
- [`dashboard-change-and-enhancement-superfile.md`](dashboard-change-and-enhancement-superfile.md)
  — canonical decision, cleanup, enhancement, Version 2, and evidence ledger.
- [`nch-weather-studio-greenfield-plan.md`](nch-weather-studio-greenfield-plan.md)
  — parked design for the explicitly separate NCH Weather Studio project; its
  dashboard parity baseline must be reconciled before any phase is authorized.
- [`architecture.md`](architecture.md) — implemented system architecture.
- [`patterns.md`](patterns.md) — reusable patterns already used by the project.

The superfile is the only active roadmap for the current dashboard and Version
2 lane. The Greenfield plan is a separate parked project design because the
superfile explicitly routes to it; it is not part of the current-dashboard
backlog and is not implementation-ready against the current dashboard. Neither
document authorizes implementation by itself. A proposal appearing only in an
archived file is historical.

## Historical records

- [`archive/`](archive/) contains completed, superseded, or source documents.
- [`archive/meteosat-latency-overhaul-plan-2026-08-26.md`](archive/meteosat-latency-overhaul-plan-2026-08-26.md)
  is the completed Phase 0–5 execution record closed at `3773d47`.
- [`archive/next-session-startup-prompt-2026-08-26-pre-reconciliation.md`](archive/next-session-startup-prompt-2026-08-26-pre-reconciliation.md)
  preserves the superseded pre-`3773d47` handoff.
- [`archive/2026-08-07-consolidation-sources/`](archive/2026-08-07-consolidation-sources/README.md)
  preserves the former superfile/startup prompt and the proposal/audit sources
  used in the current consolidation, with SHA-256 hashes.
- [`perf/`](perf/) contains tracked performance evidence and phase READMEs. Keep
  evidence with its recorded environment and acceptance gate; a benchmark or
  static check is not browser proof.

Historical records should remain unchanged. Correct current decisions in the
active superfile, and add a new dated record when exact history must be kept.

## Local-only guide

`token-saver-maybe.md` is intentionally ignored. It is a short optional local
guide for concise ChatGPT/Codex collaboration, not an installed skill and not a
tracked project dependency. Tracked startup instructions must remain complete
without it.

## Document ownership rules

- Put implemented architecture in `architecture.md`, not future ideas.
- Put established reusable practices in `patterns.md`, not superseded runtime
  designs.
- Put active decisions, candidates, dependencies, and status in the superfile.
- Put NCH Weather Studio design and phases in its separate Greenfield plan; do
  not merge them into the current-dashboard or Version 2 backlog. Reconcile its
  dashboard parity baseline before changing its parked status.
- Put exact completed/superseded records in `archive/`.
- Put measured artifacts and their reproduction notes in `perf/`.
- Do not maintain parallel active roadmaps.

Directory-audit findings are read-only candidates until a bounded slice is
selected with dependencies and verification. Preserve unrelated working-tree
changes, and do not commit documentation or code unless explicitly requested.
