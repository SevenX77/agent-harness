# Handoff prompt — finish the engine lint line-axis spec (OPEN tasks only)

Copy-paste brief to launch ONE implementer for the remaining task. Read
`tasks.md` (single source of truth) + `design.md` + `requirements.md` first.

> Context: most of this spec shipped (tasks 1-10, verified). Exactly ONE open
> code task remains. **Do not edit `loader.py` concurrently with anyone else** —
> claim task 12 in `tasks.md` first. This file is the one that two agents collided
> on; coordination is the whole point of this spec.

## Your task (tasks 11-13 in tasks.md)
The multi-node graph cycle diagnostic still pins the wrong line.

- **Defect:** `packages/graph-agent/src/graph_agent/core/loader.py:1388-1392`
  (`_validate_acyclic_graph` → `visit`) raises
  `[F-v3-graph-phase-cycle] cycle detected: a -> b -> c` with a **hardcoded `1`**,
  so the editor marks the frontmatter `---` instead of an offending `<phase>` line.
  Every sibling `<phase>` diagnostic (phase-id-invalid / self-dep cycle /
  depends-unknown / island) already uses the FILE-absolute `BodyPhaseRef.diag_line`.

- **TDD (red first):** in `packages/graph-agent/tests/core/test_compiler_line_locations.py`
  add a GRAPH.md with a real cycle (`a` depends_on `b`, `b` depends_on `a`) + valid
  agent phases; assert the cycle-detected error reports the `<phase>` **file line**,
  not `1`. Confirm it fails today.

- **Fix (green):** build `line_by_name = {ref.name: ref.diag_line for ref in body_phase_refs}`
  in `_validate_graph_topology`; pass it into `_validate_acyclic_graph`; report
  `line_by_name.get(cycle[0], 1)`. (Reuse the same map for the island map already
  in `_validate_no_islands`.) Do NOT touch `PhaseTokenInfo.line_start` /
  serialized values (hash-locked — see design.md D2).

- **Gates (task 13):** `uv run pytest packages/graph-agent/tests` (only the new test
  should newly pass; the 14 pre-existing Windows/env failures are unchanged),
  `mypy --strict packages/graph-agent/src`, `ruff`, round14 21/21.

## Then
- Task 14: a DIFFERENT agent re-audits the whole change (implementer ≠ auditor) and
  returns the verdict to the user.
- Task 15: land via PR to `main` (protected, auto-merge on green; no direct push).

KEEP-MAIN: this is an engine-scoped change, explicitly authorized. Evidence-first;
align to MVP1 compile-lint design, not to current code.
