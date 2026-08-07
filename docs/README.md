# Dashboard Documentation

This directory separates current operating truth from historical evidence.

## Start here

- [`next-session-startup-prompt.md`](next-session-startup-prompt.md) — concise
  handoff for a new work session.
- [`dashboard-change-and-enhancement-superfile.md`](dashboard-change-and-enhancement-superfile.md)
  — canonical decision, cleanup, enhancement, Version 2, and evidence ledger.
- [`architecture.md`](architecture.md) — implemented system architecture.
- [`patterns.md`](patterns.md) — reusable patterns already used by the project.

The superfile is the only active roadmap. A proposal appearing in an archived
file is not authorization and is not active unless the current superfile says
so.

## Historical records

- [`archive/`](archive/) contains completed, superseded, or source documents.
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
- Put exact completed/superseded records in `archive/`.
- Put measured artifacts and their reproduction notes in `perf/`.
- Do not maintain parallel active roadmaps.

Directory-audit findings are read-only candidates until a bounded slice is
selected with dependencies and verification. Preserve unrelated working-tree
changes, and do not commit documentation or code unless explicitly requested.
