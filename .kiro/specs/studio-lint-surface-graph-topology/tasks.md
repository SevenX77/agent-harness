# Implementation Plan — Surface engine topology diagnostics on the canvas

> Single source of truth for the **realtime-lint surfacing** work. Frontend-primary;
> the ONLY engine edit is the additive `field_path` locator on the island diagnostic.
> **Boundary:** the diagnostic line axis (`diag_line`) + collect-all belong to
> `.kiro/specs/engine-lint-diagnostic-line-axis-and-collect-all/` — do NOT redo them
> here. **One owner per file** with that spec; see "Coordination" below.

## In scope (this spec owns)
- Frontend (PR 3, this spec's own PR): `node-compile-errors.ts`
  (`lintErrorNodeId` + `lintErrorsByNode`) + `node-compile-errors.test.ts`. ONLY these.
- Engine `field_path` locator on the island `_graph_fatal` — AUTHORED here, but it
  rides the **engine PR (PR 1)**; this spec never cuts a `loader.py` PR.
- GRAPH.md-marker test in `field-compile-errors.test.ts` — AUTHORED here, but it
  rides the **lint-scoping PR (PR 2)** because it consumes that PR's `lintErrorsForFile`
  (keeps the shared test file single-PR). Not in this spec's PR 3.

## Out of scope (the line-axis spec owns — do not touch here)
- `BodyPhaseRef.diag_line`, `_body_file_line`, collect-all (`exc.compile_result.issues`),
  multi-node cycle line, `test_compiler_line_locations.py`, parser
  `scan_forbidden_topology_tags`. (= line-axis spec tasks 1-15.)
- The in-flight frontend `lintErrorsForFile` helper (separate frontend stream;
  my marker test only consumes it).

## DONE (implemented + locally verified; pending landing decision)
- [x] 1. **(Red→Green) Frontend node projection.** `lintErrorNodeId` mirrors
  `compileErrorNodeId` (`phase_name` → `phases/<id>/` → `field_path` prefix);
  `lintErrorsByNode` uses it. Tests: GRAPH.md diagnostic attributes via `phase_name`
  and via `field_path` prefix; no-locator diagnostic still omitted. _R1.1, R1.2, R1.3_
- [x] 2. **(Red→Green) Engine locator.** Island `_graph_fatal` carries
  `field_path=f"{phase_id}.depends_on"`; line uses `ref.diag_line` (line-axis spec's
  field). Test (`test_round14_skill_compilation_cutover.py::test_unreachable_phase_uses_island_code`)
  asserts `payload.field_path == "orphan.depends_on"`. _R3.1_
- [x] 3. **GRAPH.md marker lock.** Test in `field-compile-errors.test.ts`:
  GRAPH.md-located island diagnostic with a line → `lintErrorsForFile` keeps it →
  `lintErrorsToMarkers` renders it at that line. _R2.1_
- [x] 4. **Gates (touched scope) green.** engine topology/cutover/e2e 74 passed +
  `mypy --strict` clean; frontend node/field/marker tests 41 passed; backend pytest
  exit 0; eslint scoped to my files clean. Full-suite reds are pre-existing
  (Windows gbk / hash-locks / sbom / GraphCanvas+GeneralTab lint-tc), proven via
  stashed baseline. _R4.1, R4.2, R4.3_

## OPEN
- [x] 5. **Coordination handshake — RESOLVED (2026-06-29).** `loader.py` has a single
  owner = the line-axis spec's PR. Its tasks 11-13 rewrote `_validate_no_islands`
  (shared `line_by_name` map) and **preserved `field_path=f"{phase_id}.depends_on"`**
  — verified still at `loader.py:1437`. The island `field_path` line therefore rides
  the engine PR, not a separate loader.py PR from here. _D5_
- [x] 6. **`lintErrorsForFile` dependency — RESOLVED (owner identified).** It is NOT a
  third stream: it is the **#1 frontend lint-scoping** work
  (`field-compile-errors.ts::lintErrorsForFile`, currently uncommitted), owned by that
  author. It lands in **PR 2** (see Landing order); the GRAPH.md-marker test homes
  there too (it consumes `lintErrorsForFile` — keeps that shared test file single-PR). _D4_
- [ ] 7. **Land — follow the Landing order below.** This spec's PR = `node-compile-errors.ts`
  + its test ONLY (PR 3). No `loader.py` edit from here. No direct push to `main`. _R4_
- [ ] 8. **Independent re-audit** (a DIFFERENT agent than the implementer), mirroring
  the line-axis spec's discipline. _parity with their R4.4_

## Landing order (3 PRs — shared across line-axis + lint-scoping + surfacing)
1. **Engine PR** (line-axis spec): `loader.py` (line-axis + multi-node cycle, tasks
   11-13 DONE) + `parser.py` + `test_compiler_line_locations.py` + round14 fixture
   **+ this spec's island `field_path` line riding along** (single owner). → emits
   `diag_line` + `field_path`. Then its task 14 re-audit + task 15 PR.
2. **Frontend lint-scoping PR** (#1 author): `field-compile-errors.ts`
   (`lintErrorsForFile`) + `applyLintMarkers(filePath)` + the GRAPH.md-marker test.
   Frontend-only, independently green.
3. **Surfacing PR** (this spec): `node-compile-errors.ts` + `node-compile-errors.test.ts`.
   Depends on PR 1 (engine `field_path` for node attribution). Lands last.

Post-merge: after PR 1, re-grep `field_path=` survived (it did at release); after PR 2,
confirm `lintErrorsForFile` is on `main` before PR 3.

## Coordination (the one shared file: `loader.py::_validate_no_islands`)
| Concern | Owner | Status |
|---|---|---|
| island **line** = `ref.diag_line` | line-axis spec (its task 7, credited "concurrent agent") | in tree |
| island **`field_path`** locator | THIS spec (task 2) | in tree |
| re-thread `{name: diag_line}` map (task 12) | line-axis spec | OPEN — must keep `field_path=` |

Both edits already coexist in the working tree. The only live risk is the line-axis
spec's task 12 rewriting the function and dropping `field_path` — flagged above.

## Ownership log
- Frontend (`node-compile-errors.ts` + tests, marker test): this agent. Verified clean
  (`node-compile-errors.ts` diff vs HEAD = only this change).
- Engine island `field_path` + `diag_line` line: this agent (= the line-axis spec's
  "concurrent agent" on its task 7).
