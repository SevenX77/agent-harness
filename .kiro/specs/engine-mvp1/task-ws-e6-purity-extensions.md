---
ws_id: WS-E6-purity-extensions
task_type: implementation
implementer: Gemini
author: Codex
status: drafted
created: 2026-06-06
requirements: .kiro/specs/engine-mvp1/requirements-ws-e6-purity-extensions.md
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
related_backlog: docs/engine/mvp1/_impl-backlog.md
spec_ssot:
  - docs/engine/mvp1/02-mechanism/01-compile/mvp1-alignment.md §2/§6/§8
  - docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md §2.1/§6
  - docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md §2/§5/§8
  - docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md §2.3.3/§6
approved_red_tests:
  - packages/graph-agent/tests/core/test_purity_characterization.py
  - packages/graph-agent/tests/core/validators/test_tool_paths_escape.py
  - packages/graph-agent/tests/core/validators/test_purity_le2.py
red_result: "uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_tool_paths_escape.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q -> 12 failed, 22 passed"
owns_files:
  - packages/graph-agent/src/graph_agent/core/purity.py
  - packages/graph-agent/tests/core/test_purity_characterization.py
  - packages/graph-agent/tests/core/validators/test_tool_paths_escape.py
  - packages/graph-agent/tests/core/validators/test_purity_le2.py
forbidden_files:
  - packages/graph-agent/src/graph_agent/core/error_registry.py
  - packages/graph-agent/src/graph_agent/core/loader.py
  - packages/graph-agent/src/graph_agent/core/module_sandbox.py
  - packages/graph-agent/src/graph_agent/core/graph_assembler.py
  - packages/graph-agent/src/graph_agent/core/exceptions.py
  - packages/graph-agent/src/graph_agent/core/result.py
  - packages/graph-agent/src/graph_agent/callbacks/events.py
  - packages/graph-agent/src/graph_agent/callbacks/emit.py
  - apps/studio/**
  - packages/graph-agent-gateway/**
---

# WS-E6 Purity Extensions Task

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` while implementing. The RED tests are already written and approved by the contract gate. Do not weaken them. Implement task-by-task until the approved RED suite is GREEN.

**Goal:** Extend the compile-time purity scanner so skill-local LOGIC action/tool Python files fail fast on `run_skill` orchestration, direct filesystem access, `sys.path` import-boundary hacks, and dynamic import escape paths.

**Architecture:** Keep the implementation local to `packages/graph-agent/src/graph_agent/core/purity.py`. `SkillLoader` already calls `scan_python_purity()` before loading action/tool modules, and `_purity_fatal()` already reports `[F-v3-logic-action-purity-violation]`; the scanner should emit precise `PurityViolation` records and let the existing loader path surface the FATAL payload. Do not add new error codes, do not alter loader/module sandbox behavior, and do not scan arbitrary repo files outside loader-selected skill-local Python sources.

**Tech Stack:** Python 3.12, `ast`, `pathlib.Path`, pytest, existing `SkillLoader` compile path.

---

## Phase 0: Grounding And Scope Lock

- [ ] Read the requirements file and SSOT pointers before editing.
  _Requirements: IR2 / IR5 grounding._
  Verify by reporting the current live symbols and behavior: `PurityViolation`, `scan_python_purity`, `scan_tool_imports_context`, `_collect_import_aliases`, `_violation_for_call`, `_raise_on_purity_violations`, and `_purity_fatal`.

- [ ] Confirm the implementation can stay inside `packages/graph-agent/src/graph_agent/core/purity.py`.
  _Requirements: IR1 file ownership / requirements §3._
  Verification command:
  `git status --short -- packages/graph-agent/src/graph_agent/core/purity.py packages/graph-agent/src/graph_agent/core/loader.py packages/graph-agent/src/graph_agent/core/error_registry.py packages/graph-agent/src/graph_agent/core/module_sandbox.py packages/graph-agent/src/graph_agent/core/graph_assembler.py`
  Expected before implementation: test files may be dirty from RED; forbidden production files must have no WS-E6 diff.

- [ ] Re-run the approved RED suite before implementing, and keep the failure shape unchanged.
  _Requirements: TDD RED evidence / requirements §8._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_tool_paths_escape.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q`
  Expected now: `12 failed, 22 passed`, with failures caused by missing LE2 scanner violations and compile-time purity FATALs.

## Phase 1: Scanner Building Blocks

- [ ] Extend import alias collection enough to recognize aliases used by the approved RED tests.
  _Requirements: requirements §5.1 / §5.4._
  Required alias behavior from approved RED:
  - `from graph_agent import run_skill` means the local name `run_skill` maps to `graph_agent.run_skill`.
  - `from graph_agent.core.runner import run_skill as call_child` means `call_child` maps to `graph_agent.core.runner.run_skill`.
  - `import sys` means `sys` maps to `sys`.
  - `import importlib` means `importlib` maps to `importlib`.
  - `from importlib import util` means `util` maps to `importlib.util`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py::test_scan_python_purity_reports_le2_hard_bans -q`
  Expected after later phases: this command passes.

- [ ] Keep pure standard-library data transforms non-violating.
  _Requirements: requirements §5.5 false-positive protection._
  Approved RED protection:
  `json.loads`, string normalization, `context.get(...)`, and ordinary pure calls must not produce a `PurityViolation`.
  Target test:
  `packages/graph-agent/tests/core/test_purity_characterization.py::test_scan_python_purity_allows_pure_data_transformations`
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py::test_scan_python_purity_allows_pure_data_transformations -q`

## Phase 2: run_skill Compile-Time Hard Ban

- [ ] Make direct and aliased `run_skill` calls produce `PurityViolation`.
  _Requirements: requirements §5.1 / §6 scanner unit._
  Approved RED scanner cases:
  - `run_skill("child.skill", workspace_dir="workspace")`
  - `call_child("child.skill", workspace_dir="workspace")` where `call_child` aliases `graph_agent.core.runner.run_skill`
  The emitted violation text must include `run_skill`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py::test_scan_python_purity_reports_le2_hard_bans -q`

- [ ] Verify the existing loader path turns the `run_skill` scanner violation into compile-time `[F-v3-logic-action-purity-violation]`.
  _Requirements: requirements §5.1 / §6 real compile path._
  Target test:
  `packages/graph-agent/tests/core/validators/test_purity_le2.py::test_le2_forbidden_action_code_fails_during_compile`
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/validators/test_purity_le2.py::test_le2_forbidden_action_code_fails_during_compile -q`
  Expected after later phases: all parametrized compile-path hard-ban cases pass.

## Phase 3: Filesystem Access Hard Ban

- [ ] Expand filesystem checks from local-write-only to direct filesystem access.
  _Requirements: requirements §5.2 / §6 scanner unit._
  Approved RED scanner cases:
  - `open("input.txt").read()` must violate even without explicit mode.
  - `Path("input.txt").read_text(encoding="utf-8")` must violate.
  - `os.listdir(".")` must violate.
  Existing local-write cases must remain violations:
  - write-mode `open(...)`
  - path mutation APIs
  - `os` / `shutil` mutation APIs
  - `tempfile` APIs
  Violation text for read cases must mention the API and `file`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py::test_scan_python_purity_reports_le2_hard_bans packages/graph-agent/tests/core/test_purity_characterization.py::test_violation_for_call_current_violations -q`

- [ ] Verify filesystem read and write cases fail during `SkillLoader.compile_skill`.
  _Requirements: requirements §5.2 / §6 real compile path._
  Approved RED compile-path cases:
  - action direct read: `open("input.txt").read()`
  - existing write regression: `open("out.txt", "w").write("bad")`
  Both must report `[F-v3-logic-action-purity-violation]` with source path and line semantics.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/validators/test_purity_le2.py::test_le2_forbidden_action_code_fails_during_compile -q`

## Phase 4: sys.path And Dynamic Import Escape Hard Bans

- [ ] Make `sys.path` mutation calls violate compile-time purity.
  _Requirements: requirements §5.3 / §6._
  Approved RED scanner / compile-path cases:
  - `sys.path.insert(0, "../outside")`
  - `sys.path.append("../outside")`
  Violation text must mention `sys.path`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py::test_scan_python_purity_reports_le2_hard_bans packages/graph-agent/tests/core/validators/test_purity_le2.py::test_le2_forbidden_action_code_fails_during_compile -q`

- [ ] Make high-risk dynamic import escape APIs violate compile-time purity.
  _Requirements: requirements §5.4 / §6._
  Approved RED scanner / compile-path cases:
  - `importlib.import_module("graph_agent.core.runner")`
  - `util.spec_from_file_location("escape", "../outside.py")`
  - compile-path action that dynamically imports `graph_agent.core.runner` and calls `runner.run_skill(...)`
  Violation text must mention the import API or `import`.
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py::test_scan_python_purity_reports_le2_hard_bans packages/graph-agent/tests/core/validators/test_purity_le2.py::test_le2_forbidden_action_code_fails_during_compile -q`

## Phase 5: Regression Protection And Full Verification

- [ ] Preserve the tool Context facade import regression.
  _Requirements: requirements §5.5 / §6._
  Target tests:
  `packages/graph-agent/tests/core/test_purity_characterization.py::test_scan_tool_imports_context_facade_regression`
  `packages/graph-agent/tests/core/validators/test_tool_paths_escape.py`
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py::test_scan_tool_imports_context_facade_regression packages/graph-agent/tests/core/validators/test_tool_paths_escape.py -q`

- [ ] Preserve pure compile path compatibility.
  _Requirements: requirements §5.5 / §8._
  Target tests:
  `packages/graph-agent/tests/core/validators/test_purity_le2.py::test_pure_action_still_compiles_under_le2_purity`
  `packages/graph-agent/tests/core/validators/test_tool_paths_escape.py::test_in_tree_action_reference_still_loads`
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/validators/test_purity_le2.py::test_pure_action_still_compiles_under_le2_purity packages/graph-agent/tests/core/validators/test_tool_paths_escape.py::test_in_tree_action_reference_still_loads -q`

- [ ] Preserve error-code registration and metadata shape by not editing `error_registry.py`.
  _Requirements: requirements §5.5 / §8._
  Target test:
  `packages/graph-agent/tests/core/validators/test_purity_le2.py::test_purity_violation_error_code_remains_compile_fatal`
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/validators/test_purity_le2.py::test_purity_violation_error_code_remains_compile_fatal -q`

- [ ] Run the approved WS-E6 suite to GREEN.
  _Requirements: requirements §8 hard exit._
  Verification command:
  `uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_tool_paths_escape.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q`
  Expected after implementation: all tests pass.

- [ ] Confirm forbidden production files are untouched.
  _Requirements: IR1 / IR7 scope lock._
  Verification command:
  `git diff -- packages/graph-agent/src/graph_agent/core/error_registry.py packages/graph-agent/src/graph_agent/core/loader.py packages/graph-agent/src/graph_agent/core/module_sandbox.py packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/core/exceptions.py packages/graph-agent/src/graph_agent/core/result.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py`
  Expected: no diff in these forbidden engine files. `apps/studio/**` and `packages/graph-agent-gateway/**` are outside this WS and may already be dirty in the shared worktree; do not edit them, and report any pre-existing status separately with:
  `git status --short -- apps/studio packages/graph-agent-gateway`

- [ ] Run diff hygiene.
  _Requirements: implementation quality gate._
  Verification command:
  `git diff --check -- packages/graph-agent/src/graph_agent/core/purity.py packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_tool_paths_escape.py packages/graph-agent/tests/core/validators/test_purity_le2.py`

## Phase 6: Baseline Handoff After GREEN

- [ ] Do not update baseline before implementation is GREEN and Codex review accepts hard exit.
  _Requirements: IR6 / requirements §10._
  After GREEN, report the exact scanner behavior so Codex can truthfully update:
  - `docs/engine/mvp1/02-mechanism/01-compile/baseline.md`
  - `docs/engine/mvp1/01-contract/03-compile-rules/baseline.md`
  - `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md`
  - `docs/engine/mvp1/01-contract/02-skill-syntax/baseline.md` only if the existing purity drift row needs a true-code update

## Hard Exit Checklist

- [ ] Approved RED suite is GREEN.
- [ ] `run_skill` direct and aliased action calls fail during `SkillLoader.compile_skill` with `[F-v3-logic-action-purity-violation]`.
- [ ] Direct filesystem reads, writes, mutations, and temporary-file APIs fail during compile-time purity scanning.
- [ ] `sys.path` mutation fails during compile-time purity scanning.
- [ ] Dynamic import escape APIs used in approved RED fail during compile-time purity scanning.
- [ ] Existing local-write checks and tool Context facade import checks still pass.
- [ ] Pure data-transform action and existing in-tree action compile path still pass.
- [ ] `ERROR_REGISTRY` key set and `ErrorCodeMetadata` shape are untouched.
- [ ] No WS-E1 runtime work was implemented: no LOGIC pure-return migration, no Context mutation removal, no iterate/SUBGRAPH migration.
- [ ] Forbidden files have no diff, and `apps/studio/**` / `packages/graph-agent-gateway/**` were not edited by this WS.

## Gemini Report Format

When finished, report:

1. Files changed.
2. The exact tests run and pass/fail output summary.
3. Confirmation that forbidden engine files have no diff and `apps/studio/**` / `packages/graph-agent-gateway/**` were not edited by this WS.
4. The final scanner hard-ban categories implemented in `scan_python_purity`.
5. Any remaining risk or reason a hard-exit item is not satisfied.
