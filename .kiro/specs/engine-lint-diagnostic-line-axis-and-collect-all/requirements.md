# Requirements Document — Engine lint: file-absolute diagnostic lines + collect-all

## Introduction

Compile/lint is **static analysis**, not the run phase. Two defects made the
authoring experience wrong:

1. **Wrong line attribution.** Body-tag diagnostics (agent `<role>`/`<goal>`/`<step>`/…
   and GRAPH.md `<phase>` errors) were pinned to **line 1** (the frontmatter `---`) or
   computed body-relative (`_xml_line`), while frontmatter errors are file-absolute.
   Studio forwards `error.line` verbatim onto a Monaco **full-file** view
   (`apps/studio/frontend/src/components/studio/lint-monaco-markers.ts`), so a
   body-relative / hardcoded-1 line marks the wrong row.
2. **Fail-fast.** The loader raised on the first defect (`_fatal` is `NoReturn`,
   ~89 call sites), so the user fixed one error, recompiled, hit the next — instead
   of seeing every independent defect in one pass.

**Authoritative-source constraint (evidence-first 铁律).** Lint is engine-owned;
the frontend never invents diagnostics ("Source of truth stays the engine lint
payload", `lint-monaco-markers.ts:12`). The fix is therefore an **engine change**
under `packages/graph-agent` — allowed under AGENTS.md KEEP-MAIN only when
explicitly scoped to the engine (it is), with **TDD (failing test first)** and
alignment to the MVP1 design (`docs/studio/mvp1/02_capabilities/compile-lint/mvp1-alignment.md`
F1 "real-time lint mark context only" / F2 "manual compile = full error list").

## Requirements

### R1 — Body-tag diagnostics use the FILE-absolute line
**User story.** As a skill author, when a body tag is wrong/missing, I want the
editor marker on that tag's real line (or the body start when absent), not on the
frontmatter `---`, so I can find it.
- 1.1 WHEN a required tag exists but is empty (`<role></role>`) THE diagnostic SHALL
  point at that tag's file line.
- 1.2 WHEN a required tag is entirely absent THE diagnostic SHALL point at the body
  start line (first line after the closing frontmatter `---`), never line 1.
- 1.3 ALL body-tag diagnostics SHALL share this file-absolute axis: agent
  role/goal/step/protocol/example/unknown-tag/mention; LOGIC `<action>`; GRAPH.md
  `<phase>` phase-id-invalid / phase-cycle (self **and** multi-node) /
  depends-unknown / phase-island; and parser `scan_forbidden_topology_tags`.
- 1.4 Token-span metadata that is NOT a diagnostic (`PhaseTokenInfo.line_start/end`,
  `PhaseAttributeSpan`) SHALL stay body-relative (serializer/cache round-trip is
  hash-locked); the diagnostic line rides a separate field.

### R2 — Collect-all (one pass, every independent defect)
- 2.1 A single compile SHALL surface every independent content/whitelist defect
  (e.g. missing `<role>` AND missing `<goal>`; defects in separate nodes), not abort
  at the first.
- 2.2 The full set SHALL ride `exc.compile_result.issues` (the seam Studio's compile
  drawer already projects — zero Studio change); the primary `payload` SHALL stay the
  first defect for single-error (realtime-lint) consumers.
- 2.3 Structural failures that make further parsing impossible (GRAPH.md parse,
  manifest, topology pre-reqs) MAY still fail-fast.

### R3 — Consistent empty-tag detection
- 3.1 An empty `<action></action>` SHALL be a defect even beside a filled one,
  matching the agent's strict `<role>`/`<goal>` non-empty check.

### R4 — No regression, codes stable, gates green
- 4.1 No `[F-v3-*]` code SHALL change; round28 bijection / features.yaml intact.
- 4.2 Engine TDD: failing tests first; `uv run pytest packages/graph-agent/tests`,
  `mypy --strict`, `ruff` green; round14 located-code matrix green.
- 4.3 Studio shell unchanged (diagnostics flow through `_compile_errors_from_exception`).
- 4.4 The implementation must be **independently audited** (not self-verified by the
  implementer).
