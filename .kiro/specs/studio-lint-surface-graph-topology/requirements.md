# Requirements — Surface engine topology diagnostics on the canvas (realtime-lint)

## Introduction

Compile-time topology diagnostics (e.g. `[F-v3-graph-phase-island]`) already
exist and are FATAL, but during **editing** they did not appear on the canvas
**node badge** or as a **GRAPH.md inline marker** — the realtime-lint node
projection silently dropped GRAPH.md-located diagnostics. The goal is to make
these *already-emitted* diagnostics show in realtime-lint exactly like a
SKILL.md `<role>`/`<goal>` error does.

This is **frontend-primary**. The only engine touch is **additive**: emit a
node locator (`field_path`) on node-scoped topology diagnostics so the existing
projection can attribute them — no new rule, no `[F-v3-*]` code change, no
contract change.

**Scope boundary (read first).** The diagnostic **line axis** (file-absolute
`diag_line`) and **collect-all** are a SEPARATE spec —
`.kiro/specs/engine-lint-diagnostic-line-axis-and-collect-all/`. This spec does
NOT own loader.py line/collect-all work; it only depends on `diag_line` existing
and adds the `field_path` locator (see coordination in `tasks.md`).

**Evidence-first 铁律.** Source of truth stays the engine lint payload — the
frontend never invents diagnostics (`lint-monaco-markers.ts:12`). This spec only
re-projects the existing payload.

## Requirements

### R1 — Realtime-lint node badge attribution (parity with manual Compile)
**User story.** As a skill author, when a topology error makes a node invalid, I
want its node badge to light up while I edit, not only after a manual Compile.
- 1.1 The realtime-lint node projection (`lintErrorsByNode`) SHALL resolve a
  diagnostic's node id by the same channel as the manual-Compile
  `compileErrorNodeId`: `phase_name` → `phases/<id>/` file path → `field_path`
  node-id prefix (`<node_id>.<x>`).
- 1.2 A GRAPH.md-located diagnostic carrying a node locator (e.g. island with
  `field_path="<phase>.depends_on"`) SHALL attribute to that node's badge.
- 1.3 A diagnostic with no resolvable node locator SHALL still be omitted from the
  node channel (degrade to GRAPH.md markers + compile drawer) — no regression for
  per-file phase diagnostics, which keep matching by `file`.

### R2 — GRAPH.md inline marker
- 2.1 A GRAPH.md-located, line-bearing diagnostic SHALL render as a Monaco marker
  when GRAPH.md is open (via the existing `lintErrorsForFile` / `lintErrorsToMarkers`
  path). (Already works; locked by a test.)
- 2.2 A line-less diagnostic SHALL degrade to the file-level/drawer surface.

### R3 — Engine node locator (additive only)
- 3.1 Node-scoped topology diagnostics (starting with `[F-v3-graph-phase-island]`)
  SHALL carry `field_path="<phase>.<x>"` so R1 can attribute them. The diagnostic
  **line** stays owned by the line-axis spec (`ref.diag_line`); this spec adds only
  the `field_path` argument.
- 3.2 No `[F-v3-*]` code SHALL change; round28 bijection / features.yaml intact.

### R4 — No invention, gates green, TDD
- 4.1 No diagnostic-inventing logic in the frontend (display-only projection).
- 4.2 TDD: failing tests first (engine: island payload carries the locator;
  frontend: GRAPH.md diagnostic attributes to the node + renders a marker).
- 4.3 Gates for the touched scope green: engine `pytest`/`mypy --strict`; frontend
  `lint`/`typecheck`/`test`/`build` (for the changed files); studio backend `pytest`
  (diagnostics flow through `_lint_error_from_exception` unchanged).
