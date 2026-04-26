# PR #7 Step 4 — Tool-Path Resolvability Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a static semantic validator that, at compile time, confirms every tool-reference dot-path on `LLMPhase.agent_tools`, `LLMPhase.validator`, `LLMPhase.steps[*].tools`, `LLMPhase.steps[*].validator`, `LogicPhase.execute_steps`, `LogicPhase.validator`, and `AgentSkillDef.agent_tools` resolves to an existing Python module on disk (relative to the parent SKILL.md) or an installed `graph_agent.tools.builtin` package member. Emit `F-tool-path-not-found` or `F-tool-path-invalid-format` from `compile_skill()`.

**Architecture:** A new sibling module `core/validators/tool_paths.py` exports `check_tool_paths(manifest, *, base_dir) -> list[CompileIssue]`. The validator iterates every tool-reference field on the manifest and runs a **non-executing** static check on each ref string: parse "module.func", verify the module file exists (relative path) or the importable spec exists (`builtin.*`). The validator deliberately does **not** call `loader._resolve_tool_reference` — that loader executes module code on import, which is acceptable at runtime but a side-effect risk at compile-time (Studio "save validate" would run arbitrary user code). Function-name verification (does the module actually define the named symbol?) is out of scope for step 4 and stays at load time.

**Tech Stack:** Python 3.11+, `importlib.util.find_spec` (non-executing), `Path.exists()`, existing `CompileIssue`.

---

## Why this validator exists

`loader._resolve_tool_reference` (loader.py:40) catches typo'd tool refs at load time, but only for skills that actually load. Compile-time scanning catches them in Studio "save validate" without executing anything. Function-name typos (e.g. `tools.helpers.misnamed_fn` when the module defines `correctly_named_fn`) still surface at first load — that's a known limitation noted in the plan rationale.

---

## Scope decisions

- **Non-executing check, not full import** — Studio's "save validate" cannot execute arbitrary user code as a side effect of validation. `_resolve_tool_reference` runs `exec(code, module.__dict__)` on every tool reference (loader.py:144); replicating that at compile time would let a malicious or buggy SKILL.md run code just by being saved. The validator only checks file existence (for relative refs) or `find_spec` (for `builtin.*` refs).
- **No function-name verification** — checking that `module.fn` actually defines a callable named `fn` would require either AST-parsing every file (expensive, brittle for dynamic/decorated symbols) or executing the module. Defer; load time still catches it.
- **One rule_id per failure shape, not one mega-rule** — `F-tool-path-invalid-format` (ref doesn't contain `.`) is a different fix from `F-tool-path-not-found` (file missing). Keeping them separate lets Studio show different fix hints.
- **Walk every field that takes a tool ref** — `LLMPhase.agent_tools`, `LLMPhase.validator`, `LLMPhase.steps[*].tools`, `LLMPhase.steps[*].validator`, `LogicPhase.execute_steps`, `LogicPhase.validator`, `AgentSkillDef.agent_tools`. Skipping any subset would leave silent gaps that PMs hit later.
- **`builtin.*` resolution uses `importlib.util.find_spec`** — does not execute the module, just checks the spec is locatable. Function-name verification on `builtin.*` is also skipped (parity with local refs).

---

## File Structure

| Path | Responsibility | New / Modified |
|---|---|---|
| `src/core/graph_agent/core/validators/tool_paths.py` | Public `check_tool_paths(manifest, *, base_dir) -> list[CompileIssue]`. Internal helpers walk per-field, classify failures into the rule_id catalogue. | Create |
| `src/core/graph_agent/core/compiler.py` | Add `check_tool_paths` to the validator chain in both the `GraphSkillDef` and `AgentSkillDef` branches. Update the TODO(PR#7) docstring. | Modify |
| `tests/graph_agent/core/validators/test_tool_paths.py` | Unit tests for every emitted-issue and every passing-skip path. | Create |
| `tests/graph_agent/core/test_compile_skill_tool_paths_integration.py` | One integration test asserting `compile_skill()` surfaces `F-tool-path-not-found` end-to-end. | Create |

---

## Issue catalogue

| rule_id | severity | trigger | location format |
|---|---|---|---|
| `F-tool-path-invalid-format` | FATAL | Tool ref string lacks a `.` separator (so it can't be split into module + function). | `SKILL.md:<field-path>.<index?>` (e.g. `phases.<phase_name>.agent_tools.0`) |
| `F-tool-path-not-found` | FATAL | Local ref's resolved `.py` file or package `__init__.py` does not exist under `base_dir`. For `builtin.*` refs, `importlib.util.find_spec("graph_agent.tools.builtin.<sub>")` returns `None`. | same |

---

## Public API contract

```python
# src/core/graph_agent/core/validators/tool_paths.py

from pathlib import Path
from ..compiler import CompileIssue
from ..manifest import AgentSkillDef, GraphSkillDef

def check_tool_paths(
    manifest: AgentSkillDef | GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    """Verify every tool-reference dot-path locates a real Python module."""
```

---

## Field-walking inventory (locked before coding)

For `AgentSkillDef`:
- `manifest.agent_tools` → list of refs

For `GraphSkillDef`, iterate `manifest.phases`:
- `LLMPhase.agent_tools` → list
- `LLMPhase.validator` → optional single ref
- `LLMPhase.steps` → list of `Step`; for each:
  - `Step.tools` → list
  - `Step.validator` → optional single ref
- `LogicPhase.execute_steps` → list (`min_length=1`, so always at least one)
- `LogicPhase.validator` → optional single ref
- `DelegatePhase` → no tool refs

`PersonaSkillDef` has none — falls through.

Each location string is anchored with the precise field path so Studio can highlight the right line.

---

## Tasks

### Task 1: Scaffold tool_paths stub

**Files:**
- Create: `src/core/graph_agent/core/validators/tool_paths.py`

- [ ] **Step 1: Stub**

```python
"""Static semantic validator: tool-path dot-reference resolvability.

See docs/superpowers/plans/2026-04-25-pr7-tool-paths-validator.md.
"""
from __future__ import annotations

from pathlib import Path

from ..compiler import CompileIssue
from ..manifest import AgentSkillDef, GraphSkillDef


def check_tool_paths(
    manifest: AgentSkillDef | GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    """Verify every tool-reference dot-path locates a real Python module."""
    raise NotImplementedError("filled in by Task 2 onward")
```

- [ ] **Step 2: Confirm test collection**

Run: `source .venv/bin/activate && pytest --collect-only tests/graph_agent/core/ 2>&1 | tail -3`

- [ ] **Step 3: Commit**

```bash
git add src/core/graph_agent/core/validators/tool_paths.py docs/superpowers/plans/2026-04-25-pr7-tool-paths-validator.md
git commit -m "feat(validators): scaffold tool_paths stub + plan"
```

---

### Task 2: Test happy path on AgentSkillDef.agent_tools (local + builtin) + impl

**Files:**
- Create: `tests/graph_agent/core/validators/test_tool_paths.py`
- Modify: `src/core/graph_agent/core/validators/tool_paths.py`

- [ ] **Step 1: Write helpers + happy-path test**

```python
"""Unit tests for the tool_paths validator."""
from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

from graph_agent.core.manifest import AgentSkillDef, GraphSkillDef, SkillManifest
from graph_agent.core.parser import parse_skill_file
from graph_agent.core.validators.tool_paths import check_tool_paths


def _stage_local_tool(tmp_path: Path, *, dotted: str) -> Path:
    """Materialise a no-op .py file at the dotted location under tmp_path."""
    parts = dotted.split(".")
    *dirs, leaf = parts
    cur = tmp_path
    for d in dirs:
        cur = cur / d
        cur.mkdir(exist_ok=True)
        (cur / "__init__.py").write_text("", encoding="utf-8")
    py_file = cur / f"{leaf}.py"
    py_file.write_text("def _placeholder() -> str: return ''\n", encoding="utf-8")
    return py_file


def _write_agent_with_tools(parent_dir: Path, *, name: str, tools: list[str]) -> Path:
    tools_block = "\n".join(f"  - {t}" for t in tools)
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: agent\n"
        f"name: {name}\n"
        f"description: agent {name}\n"
        "agent_profile:\n"
        "  role: tester\n"
        "  goal: be tested\n"
        "agent_tools:\n"
        f"{tools_block}\n"
        "---\n"
    )
    path = parent_dir / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _load(parent_path: Path):
    raw = parse_skill_file(parent_path)["frontmatter"]
    return TypeAdapter(SkillManifest).validate_python(raw)


def test_returns_empty_when_local_and_builtin_tools_resolve(tmp_path: Path) -> None:
    # Local: tools/helpers.py defines a placeholder
    _stage_local_tool(tmp_path, dotted="tools.helpers")
    agent_path = _write_agent_with_tools(
        tmp_path,
        name="my_agent",
        tools=["tools.helpers.placeholder", "builtin.parallel_map"],
    )

    manifest = _load(agent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert issues == []
```

- [ ] **Step 2: Run — expect FAIL with NotImplementedError**

- [ ] **Step 3: Implement**

Replace `tool_paths.py` body:

```python
from __future__ import annotations

import importlib.util
from collections.abc import Iterable
from pathlib import Path

from ..compiler import CompileIssue
from ..manifest import (
    AgentSkillDef,
    GraphSkillDef,
    LLMPhase,
    LogicPhase,
)


def check_tool_paths(
    manifest: AgentSkillDef | GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    issues: list[CompileIssue] = []

    if isinstance(manifest, AgentSkillDef):
        for idx, ref in enumerate(manifest.agent_tools):
            _check_one(
                ref,
                location=f"SKILL.md:agent_tools.{idx}",
                base_dir=base_dir,
                issues=issues,
            )
        return issues

    if isinstance(manifest, GraphSkillDef):
        for phase in manifest.phases:
            if isinstance(phase, LLMPhase):
                for idx, ref in enumerate(phase.agent_tools):
                    _check_one(
                        ref,
                        location=f"SKILL.md:phases.{phase.name}.agent_tools.{idx}",
                        base_dir=base_dir,
                        issues=issues,
                    )
                if phase.validator is not None:
                    _check_one(
                        phase.validator,
                        location=f"SKILL.md:phases.{phase.name}.validator",
                        base_dir=base_dir,
                        issues=issues,
                    )
                for s_idx, step in enumerate(phase.steps):
                    for t_idx, ref in enumerate(step.tools):
                        _check_one(
                            ref,
                            location=f"SKILL.md:phases.{phase.name}.steps.{s_idx}.tools.{t_idx}",
                            base_dir=base_dir,
                            issues=issues,
                        )
                    if step.validator is not None:
                        _check_one(
                            step.validator,
                            location=f"SKILL.md:phases.{phase.name}.steps.{s_idx}.validator",
                            base_dir=base_dir,
                            issues=issues,
                        )
            elif isinstance(phase, LogicPhase):
                for idx, ref in enumerate(phase.execute_steps):
                    _check_one(
                        ref,
                        location=f"SKILL.md:phases.{phase.name}.execute_steps.{idx}",
                        base_dir=base_dir,
                        issues=issues,
                    )
                if phase.validator is not None:
                    _check_one(
                        phase.validator,
                        location=f"SKILL.md:phases.{phase.name}.validator",
                        base_dir=base_dir,
                        issues=issues,
                    )
            # DelegatePhase has no tool refs.
    return issues


def _check_one(
    ref: str,
    *,
    location: str,
    base_dir: Path,
    issues: list[CompileIssue],
) -> None:
    if "." not in ref:
        issues.append(CompileIssue(
            rule_id="F-tool-path-invalid-format",
            severity="FATAL",
            location=location,
            message=(
                f"Tool reference '{ref}' has no '.' separator. "
                f"Expected format: module.path.function_name."
            ),
        ))
        return

    module_path_str, _func_name = ref.rsplit(".", 1)

    if module_path_str == "builtin" or module_path_str.startswith("builtin."):
        submod = module_path_str[len("builtin"):].lstrip(".")
        full_module = "graph_agent.tools.builtin"
        if submod:
            full_module = f"{full_module}.{submod}"
        try:
            spec = importlib.util.find_spec(full_module)
        except (ImportError, ValueError):
            spec = None
        if spec is None:
            issues.append(CompileIssue(
                rule_id="F-tool-path-not-found",
                severity="FATAL",
                location=location,
                message=(
                    f"Builtin tool reference '{ref}' resolves to module "
                    f"'{full_module}', which is not importable."
                ),
            ))
        return

    # Local path: derive base_dir / module/parts[/__init__.py | .py]
    module_file = base_dir / module_path_str.replace(".", "/")
    py_file = module_file.with_suffix(".py")
    init_file = module_file / "__init__.py"
    if not py_file.is_file() and not init_file.is_file():
        issues.append(CompileIssue(
            rule_id="F-tool-path-not-found",
            severity="FATAL",
            location=location,
            message=(
                f"Tool reference '{ref}' resolves to module file "
                f"'{py_file}' or package '{init_file}', neither of "
                f"which exists."
            ),
        ))
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/core/graph_agent/core/validators/tool_paths.py tests/graph_agent/core/validators/test_tool_paths.py
git commit -m "feat(validators): tool_paths happy path with first passing test"
```

---

### Task 3: Test invalid format FATAL (no dot)

**Files:** modify test file

```python
def test_fatal_when_ref_lacks_dot(tmp_path: Path) -> None:
    agent_path = _write_agent_with_tools(
        tmp_path, name="my_agent", tools=["nodot"],
    )

    manifest = _load(agent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-tool-path-invalid-format"
    assert "nodot" in issues[0].message
    assert issues[0].location == "SKILL.md:agent_tools.0"
```

Run + commit.

---

### Task 4: Test local module not found

**Files:** modify test file

```python
def test_fatal_when_local_module_missing(tmp_path: Path) -> None:
    agent_path = _write_agent_with_tools(
        tmp_path, name="my_agent", tools=["missing.fn"],
    )

    manifest = _load(agent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-tool-path-not-found"
    assert "missing.fn" in issues[0].message
```

Run + commit.

---

### Task 5: Test builtin module not found

**Files:** modify test file

```python
def test_fatal_when_builtin_module_missing(tmp_path: Path) -> None:
    agent_path = _write_agent_with_tools(
        tmp_path, name="my_agent",
        tools=["builtin.no_such_submodule.fn"],
    )

    manifest = _load(agent_path)
    issues = check_tool_paths(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-tool-path-not-found"
    assert "builtin.no_such_submodule.fn" in issues[0].message
```

Run + commit.

---

### Task 6: Test GraphSkillDef LLMPhase + LogicPhase tool fields

Helper `_write_graph_with_phases` + tests covering:
- `LLMPhase.agent_tools` typo
- `LLMPhase.validator` typo
- `LLMPhase.steps[0].tools[0]` typo
- `LogicPhase.execute_steps[0]` typo
- `LogicPhase.validator` typo

5 tests. Each asserts the right rule_id + location string. (See plan implementation below; tests follow same pattern as Tasks 3-5.)

- [ ] Run + commit (one commit covering all 5).

---

### Task 7: Wire validator into compile_skill + integration test

**Files:**
- Modify: `src/core/graph_agent/core/compiler.py`
- Create: `tests/graph_agent/core/test_compile_skill_tool_paths_integration.py`

In `compile_skill`, add `check_tool_paths` to both the `GraphSkillDef` and `AgentSkillDef` branches (same pattern as step 3). Update the docstring TODO list to mark tool-path resolvability shipped.

Integration test: stage an agent SKILL.md with one bad tool ref, assert `compile_skill().fatals` contains `F-tool-path-not-found`.

Run + commit.

---

### Task 8: Full pytest regression

Run: `pytest tests/ --ignore=tests/llm_client_manager -q`
Expected: previous baseline + ~10 new tests = green.

---

### Task 9: Send code review to Codex

Same protocol as steps 1-3. 3 narrow YES/NO questions:
1. Field-walking inventory completeness — any tool-ref field missed?
2. Non-executing static check — is `find_spec` + `Path.is_file` parity with loader's pre-exec checks OK, or is something stricter needed?
3. rule_id granularity — is splitting `F-tool-path-invalid-format` vs `F-tool-path-not-found` worth it, or should there be one combined rule?

---

## Self-Review

- **Spec coverage**: tool-path resolvability ✅ Tasks 1-7. Only `rules.yaml` (architectural, requires user) remains in PR #7 TODO.
- **Placeholder scan**: clean.
- **Field-walk inventory**: locked above; tests cover every walked field.
- **Non-execution invariant**: validator imports `importlib.util.find_spec` and `Path` only — no `import_module`, no `exec`. Stays a pure introspection pass.

---

## Pre-Execution Checkpoints

1. **Codex plan review** — narrow yes/no on the 3 scope decisions (non-exec / field inventory / rule_id split).
2. **Skip Gemini** (memory `project_gemini_unreliable_2026-04-25.md`).
3. **Confirm `.venv/` is active**.
