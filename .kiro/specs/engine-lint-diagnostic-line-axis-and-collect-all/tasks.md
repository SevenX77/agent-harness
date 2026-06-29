# Implementation Plan — Engine lint: file-absolute diagnostic lines + collect-all

> Single source of truth for this work. **One owner per open task — no concurrent
> edits to `loader.py`.** Done items are recorded for the audit trail; only the
> OPEN items below need action.

## DONE (shipped + locally verified; pending independent re-audit)
- [x] 1. P1 — role/goal/action diagnostics file-absolute (`_body_file_line`,
  `_missing_block_line`). _R1.1, R1.2_
- [x] 2. P2 — collect-all via `exc.compile_result.issues`; first defect stays primary
  payload; structural errors keep fail-fast. _R2.1, R2.2, R2.3_
- [x] 3. P5 — empty `<action></action>` flagged beside a filled one. _R3.1_
- [x] 4. Sibling body-tag migration — agent unknown-tag / `<steps>` / `<exit_contract>`
  / step / protocol / example / mention → `_body_file_line`. _R1.3_
- [x] 5. GRAPH.md `[F-v3-graph-phase-id-invalid]` → `_body_file_line`. _R1.3_
- [x] 6. `BodyPhaseRef.diag_line`; phase-cycle (self-dep) + depends-unknown →
  `ref.diag_line`. _R1.3, D2_
- [x] 7. `[F-v3-graph-phase-island]` → `ref.diag_line` (done by the concurrent agent). _R1.3_
- [x] 8. parser `scan_forbidden_topology_tags` → `_body_offset_to_file_line`. _R1.3_
- [x] 9. round14 Windows fixture: `re.sub` repl → `lambda` (unblocks the located-code
  matrix on Windows; 21/21). _R4.2_
- [x] 10. Regression tests in `test_compiler_line_locations.py` for tasks 1-9
  (role/goal/action lines, unknown-tag, forbidden-topology, collect-all). _R4.2_

## OPEN — claim before editing `loader.py` (avoid the prior collision)

- [x] 11. **(Red) Failing test** — multi-node cycle line attribution.
  Added `test_graph_multinode_cycle_points_to_phase_tag_file_line` in
  `test_compiler_line_locations.py` (real `a`↔`b` cycle, agent phases; asserts
  cycle-detected reports a `<phase>` file line {15,16}, not 1). Confirmed RED
  (`GRAPH.md:1 cycle detected: a -> b -> a`). _R1.3, R4.2_
- [x] 12. **(Green) Fix** — `_validate_graph_topology` now builds
  `line_by_name = {ref.name: ref.diag_line for ref in body_phase_refs}` once and
  passes it to BOTH `_validate_acyclic_graph` (multi-node cycle → `line_by_name.get(cycle[0], 1)`)
  and `_validate_no_islands` (island map de-duplicated to the shared dict). The
  island `field_path=f"{phase_id}.depends_on"` (studio-lint-surface owner) was
  preserved verbatim. PhaseTokenInfo.line_start/end and serialized values untouched. _R1.3_
  - ⚠️ **HANDSHAKE — do NOT drop a co-located line.** `_validate_no_islands` already
    carries `field_path=f"{phase_id}.depends_on"` on the island `_graph_fatal`
    (loader.py:1431). That field_path is owned by the **studio-lint-surface-graph-topology**
    spec (node-badge attribution), not this one. When you refactor/unify the island
    map here, **preserve that `field_path=` argument verbatim.** `loader.py` has ONE
    owner (this task) per D5 — so this line rides along; don't delete it.
- [x] 13. **Gates** — full suite `14 failed, 1370 passed, 0 errors` (was 1369 passed;
  +1 = the new test; the 14 failures are the documented pre-existing Windows/env noise,
  unchanged — none topology/line/`[F-v3-*]`). `mypy --strict packages/graph-agent/src`
  clean, `ruff` clean, round14 **21/21**. No `[F-v3-*]` code changed; no serialized
  value touched (only `diag_line` line-args, which are non-serialized). _R4.1, R4.2_
- [ ] 14. **Independent re-audit** (a DIFFERENT agent than the implementer): verify
  R1-R4, reproduce the gate numbers, confirm `diag_line`/`BodyPhaseRef`-not-serialized
  reasoning, and that no `[F-v3-*]` code or hash-locked value shifted. Return the
  verdict to the user. _R4.4_
- [ ] 15. **Land via PR to `main`** per AGENTS.md Workflow Pipeline (protected,
  auto-merge on green). Do not push to `main` directly.

## Ownership log
- Tasks 1-6, 8-10: implemented by the auditor-turned-implementer (overstep, kept by user).
- Task 7: the concurrent engine agent.
- Tasks 11-13: **assign to exactly ONE implementer.** 14: a separate auditor.
- Tasks 11-13: **DONE + RELEASED 2026-06-29 by the engine implementer agent.**
  `loader.py` ownership released — free for the next owner. Touched files:
  `loader.py` (3 edits: shared `line_by_name` in `_validate_graph_topology`,
  threaded into `_validate_acyclic_graph` + `_validate_no_islands`),
  `tests/core/test_compiler_line_locations.py` (1 new test + helper), this `tasks.md`.
  Awaiting task 14 (independent re-audit by a DIFFERENT agent) → then task 15 (PR).
  - HANDSHAKE VERIFIED 2026-06-29: the task-12 rewrite of `_validate_no_islands`
    **preserved** the surfacing spec's `field_path=f"{phase_id}.depends_on"` (still at
    `loader.py:1437`). The collision risk is closed.

## Coordination & landing order (cross-spec — authoritative for all 3 streams)
Three streams touch this area; they land as **3 sequential PRs**:
1. **Engine PR (this spec)** — `loader.py` (line-axis + multi-node cycle, tasks 1-13)
   + `parser.py` + `test_compiler_line_locations.py` + round14 fixture, **AND the
   surfacing spec's island `field_path=f"{phase_id}.depends_on"` line riding along**
   (`loader.py` = single owner = this PR; preserved — see handshake above). Then this
   spec's task 14 (independent re-audit) → task 15 (PR). Gates: engine pytest /
   mypy --strict / ruff / round14 21-21.
2. **Frontend lint-scoping PR** — owner = the #1 frontend lint-scoping author (NOT a
   mystery third stream). `field-compile-errors.ts::lintErrorsForFile` (uncommitted) +
   `applyLintMarkers(filePath)` + the GRAPH.md-marker test (it consumes
   `lintErrorsForFile`, so that shared test file homes here). Frontend-only.
3. **Surfacing PR** (`studio-lint-surface-graph-topology`) — `node-compile-errors.ts`
   + its test only; depends on PR 1's `field_path`. Lands last.

No `loader.py` edits outside PR 1. No direct push to `main` (AGENTS.md).
