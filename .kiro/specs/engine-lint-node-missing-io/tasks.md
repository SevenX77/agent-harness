# Implementation Plan — Engine lint: node missing input/output

> **Note (reframed).** This spec only ever asked "should there be a no-input /
> no-output RULE?" — answer below: NO (design wins; `output` optional + island
> covers no-input). The actual delivered work — **surfacing** existing topology
> diagnostics on the canvas/GRAPH.md in realtime-lint — lives in a separate spec:
> `.kiro/specs/studio-lint-surface-graph-topology/`. The engine line-axis +
> collect-all it rides on: `.kiro/specs/engine-lint-diagnostic-line-axis-and-collect-all/`.

> **BLOCKED — awaiting a direction decision (see `design.md` §6).**
> Evidence resolved the open decision to **(A) connectivity**, but under (A) the
> requirement has no design-aligned gap: "no input" is already
> `[F-v3-graph-phase-island]`, and "no output" is a non-defect (the `output`
> marker is OPTIONAL per `00-FORMAT-GROUND-TRUTH.md:132-138` + the committed
> leaf-terminal-fallback tests). The literal rule was prototyped, shown to break
> two committed tests, and reverted. The steps below apply **only if** the
> requester picks option 2/3/4 from `design.md` §6; option 1 (recommended) ships
> no new code.

The steps below assume a connectivity-style new code is approved (option 3/4).

- [ ] 1. **(Red) Failing engine test** — `packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py`
  - Add `_drop_output_marker(root)` mutating
    `<phase depends_on="score" output>expand</phase>` → `<phase depends_on="score">expand</phase>`.
  - Append `("phase-no-output", _drop_output_marker, "[F-v3-graph-phase-no-output]")`
    to `_LOCATED_ERROR_CASES`.
  - Run the parametrized error test; confirm it FAILS (graph compiles clean today).
  - _Requirements: 1.2, 1.5, 4.1_

- [ ] 2. **(Green) Engine rule** — `packages/graph-agent/src/graph_agent/core/loader.py`
  - Add `_validate_no_output_phases(graph_path, body_phase_refs, adjacency)`:
    terminal phases (`not adjacency[name]`) minus `output`-marked phases → dead
    ends; if any, `_graph_fatal(...)` with the embedded
    `[F-v3-graph-phase-no-output]` code, `line=<first dead-end phase token line>`,
    `field_path="<phase>.output"`, combined message listing the dead ends.
  - Call it from `_validate_graph_topology` right after `_validate_output_phases`.
  - Confirm the test from task 1 now PASSES and is the unique defect code.
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3_

- [ ] 3. **Register the code** — keep the round28 bijection intact
  - `core/error_registry.py`: add `ERROR_REGISTRY['[F-v3-graph-phase-no-output]']`
    (FATAL, `('编译期',)`, graph skill-syntax doc_link) **and** the aligned
    `(_DOMAIN_GRAPH, '标记 <phase … output> 或为该 phase 增加下游依赖')` row in
    `_CATALOG_METADATA_ROWS`.
  - `spec/features.yaml`: add the code to
    `F-graph-skill-loading.error_codes_primary` (alphabetical).
  - `tests/test_round28_invariant_guards.py`: `len(ERROR_REGISTRY) == 97` → `98`.
  - _Requirements: 4.4_

- [ ] 4. **Full engine gates** + fix any remaining cascade
  - `uv run pytest packages/graph-agent/tests`
  - `uv run mypy --strict packages/graph-agent/src`
  - If `11-error-code-spec.md` / round28 fixtures are flagged, sync them (and the
    contract hash-lock) deliberately.
  - _Requirements: 4.3, 4.4_

- [ ] 5. **Studio backend gate** (the diagnostic flows through the shell unchanged)
  - `uv run pytest apps/studio/backend/tests`
  - Confirm the engine payload (code / `source_path` / `line` / `field_path`)
    projects to `LintError`/`CompileError` with no new diagnostic-inventing logic.
  - _Requirements: 2.1, 2.2, 2.3, 4.2_

- [ ] 6. **Display verification** (display-only; frontend should need no change)
  - Confirm GRAPH.md inline marker + manual-Compile node badge via the existing
    `lint-monaco-markers` / `node-compile-errors` projections.
  - Run frontend gates (`npm run lint && npm run typecheck && npm test && npm run build`)
    only if any wiring changed.
  - _Requirements: 2.1, 2.2, 2.3, 4.2_

- [ ] 7. **Land via PR to `main`** per AGENTS.md Workflow Pipeline (protected,
  auto-merge on green). Do not push to `main` directly.
