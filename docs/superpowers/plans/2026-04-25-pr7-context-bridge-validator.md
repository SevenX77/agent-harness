# PR #7 Step 1 — `context_bridge` Static Type Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a static semantic validator that, at compile time, checks every `DelegatePhase.context_bridge` against the child skill's declared `io.inputs` / `io.outputs`, surfacing mismatched field names as `CompileIssue` FATALs / WARNINGs from `compile_skill()`. This is the first of the four PR #7 semantic checks listed in `core/compiler.py`'s module docstring (and the only one with no load-time fallback today).

**Architecture:** A new `core/validators/` package houses cross-file semantic checks that operate on already-Pydantic-validated `SkillManifest` instances. `validators/context_bridge.py` exports `check_context_bridge(parent: GraphSkillDef, *, base_dir: Path) -> list[CompileIssue]`. `compile_skill()` in `core/compiler.py` invokes it after Pydantic validation succeeds for `GraphSkillDef`. The validator opens each `DelegatePhase.subgraph` child SKILL.md, Pydantic-validates the **frontmatter only** (no recursive load, no tool resolution — those are separate PR #7 steps), and checks name overlap between the bridge's child-side names and the child's `io` declaration. Persona children are FATAL (delegating to a persona is structurally meaningless); agent children are WARNING (no `io` block to validate against — leave the runtime to fail loudly if names diverge).

**Tech Stack:** Python 3.11+, Pydantic v2 `TypeAdapter`, existing `core/parser.py::parse_skill_file`, existing `CompileIssue` dataclass.

---

## Why this validator exists (read first)

`subgraph.py` shows the runtime semantics — see lines 94 and 227:

```python
# inputs side
for parent_key, child_input in bridge.inputs.items():
    child_inputs[child_input] = parent_ctx.get(parent_key)

# outputs side
for child_key, parent_key in bridge.outputs.items():
    parent_ctx[parent_key] = child_ctx.get(child_key)
```

Therefore:

- `context_bridge.inputs` is a `dict[parent_ctx_key, child_input_name]`.
  The **value** side (the right-hand side of the YAML) is the child's input name and **must** appear in the child's `io.inputs[*].name`.
- `context_bridge.outputs` is a `dict[child_output_name, parent_ctx_key]`.
  The **key** side (the left-hand side of the YAML) is the child's output name and **must** appear in the child's `io.outputs[*].name`.
- Parent-context keys (the other side of each dict) are dynamic — populated by previous phases at runtime — so the validator has no static way to verify them. Out of scope.

Concrete example from `skills/story-deconstruction/SKILL.md`:

```yaml
mode: delegate
subgraph: ../global-synthesis/SKILL.md
context_bridge:
  inputs:
    all_batch_results: batch_outputs    # 'batch_outputs' must be declared in child's io.inputs
    final_accumulated: accumulated_context
    entity_registry: entity_registry
  outputs:
    story_framework: story_framework    # 'story_framework' (the key) must be declared in child's io.outputs
```

Without this check, a typo on the child-side name (e.g. `batch_output` instead of `batch_outputs`) silently passes the parent compile, the child receives `None` at runtime (subgraph.py only `logger.warning`s on the parent side — the child has no idea), and downstream phases fail with confusing NoneType errors. The validator catches this at compile time.

---

## File Structure

| Path | Responsibility | New / Modified |
|---|---|---|
| `src/core/graph_agent/core/validators/__init__.py` | Empty package marker. Exports nothing — callers import the specific validator module they need. | Create |
| `src/core/graph_agent/core/validators/context_bridge.py` | Public `check_context_bridge(parent, *, base_dir) -> list[CompileIssue]`. Private helpers for child-manifest parsing + per-phase rule emission. | Create |
| `src/core/graph_agent/core/compiler.py` | Wire `check_context_bridge` into `compile_skill` for `GraphSkillDef` manifests, after Pydantic validation succeeds. Update the TODO(PR#7) docstring block (cross off the context_bridge bullet, leave the other four). | Modify (`compile_skill` body around lines 148-167; module docstring lines 27-44) |
| `tests/graph_agent/core/validators/__init__.py` | Empty test-package marker. | Create |
| `tests/graph_agent/core/validators/test_context_bridge.py` | Unit tests for every emitted issue and every passing/skipping path. Uses `tmp_path` fixtures to stage parent + child SKILL.md files with deliberately controlled `io` declarations. | Create |
| `tests/graph_agent/core/test_compile_skill.py` (existing — verify) OR a new file `tests/graph_agent/core/test_compiler_context_bridge_integration.py` | One end-to-end integration test calling `compile_skill` against a tmp_path parent SKILL.md whose context_bridge has a typo, asserting the resulting `CompileResult.fatals` contains the validator's issue. | Decide in Task 11 — we'll grep for an existing compile_skill test file first. |

The validator package is named `validators/` (plural) so the next three PR #7 checks (`tool_paths.py`, `subgraph_cycle.py`, `persona_resolution.py`) drop in alongside it without rearrangement.

---

## Issue catalogue (rule_id table)

Every `CompileIssue` this validator emits uses one of these rule_ids — keep the table consistent across the implementation and tests:

| rule_id | severity | trigger | location format |
|---|---|---|---|
| `F-context-bridge-child-missing` | FATAL | `(base_dir / phase.subgraph).resolve()` does not exist as a regular file | `SKILL.md:phases.<phase_name>.subgraph` |
| `F-context-bridge-child-invalid` | FATAL | parser/Pydantic raises while parsing child SKILL.md frontmatter | `<child_path>:frontmatter` |
| `F-context-bridge-input-undeclared` | FATAL | a `child_input` value in `phase.context_bridge.inputs` is not in `{io.name for io in child.io.inputs}` | `SKILL.md:phases.<phase_name>.context_bridge.inputs.<parent_key>` |
| `F-context-bridge-output-undeclared` | FATAL | a `child_key` key in `phase.context_bridge.outputs` is not in `{io.name for io in child.io.outputs}` | `SKILL.md:phases.<phase_name>.context_bridge.outputs.<child_key>` |
| `W-context-bridge-agent-child` | WARNING | child manifest is `AgentSkillDef` — agent skills lack `io` declarations, so neither inputs nor outputs are statically verifiable. Emit once per such phase. | `SKILL.md:phases.<phase_name>.subgraph` |
| `F-context-bridge-persona-child` | FATAL | child manifest is `PersonaSkillDef` — personas have no execution semantics, so a `DelegatePhase` pointing at one is structurally broken. | `SKILL.md:phases.<phase_name>.subgraph` |
| `W-context-bridge-duplicate-child-input` | WARNING | two or more parent_keys in `phase.context_bridge.inputs` map to the **same** `child_input` value. Runtime (`subgraph.py:94`) iterates the dict and last-wins — silent data loss. Emit one issue per duplicated child_input naming all colliding parent_keys. | `SKILL.md:phases.<phase_name>.context_bridge.inputs` |
| `W-context-bridge-duplicate-parent-output` | WARNING | two or more child_keys in `phase.context_bridge.outputs` map to the **same** `parent_key` value. Runtime (`subgraph.py:227`) overwrites — only one child output reaches the parent context. Emit one issue per duplicated parent_key naming all colliding child_keys. | `SKILL.md:phases.<phase_name>.context_bridge.outputs` |

### Rules deliberately NOT in this validator

- **`F-context-bridge-child-escapes-base` (suggested by Codex plan-review)** — flag when `(base_dir / phase.subgraph).resolve()` lands outside `base_dir`. *Rejected* because legitimate cross-skill delegation already uses `../sibling/SKILL.md` (e.g. `skills/story-deconstruction/SKILL.md` → `../global-synthesis/SKILL.md`); a flat "no `..` past base_dir" rule would FATAL legitimate authors. Path-traversal confinement for untrusted SKILL.md uploads (Studio's "user uploaded a parent skill") belongs at the **upload-staging boundary** (whoever calls `compile_skill`), not inside this validator. The validator's contract is "trusted file tree on disk."

**Why agent-child is WARNING, not FATAL:** the runtime in `subgraph.py` doesn't reject agent children — `child.run(initial_context=child_inputs, ...)` works regardless of artifact type. Whether the agent's prompt template actually consumes those keys depends on `agent_profile` + `context_mapping` in a free-form way that we cannot statically verify. Issuing a FATAL would block legitimate authors who know what they're doing; a WARNING flags the gap so a future PR (or Studio's preview mode) can prompt the author to confirm.

**Why persona-child is FATAL:** `PersonaSkillDef` is intentionally pure metadata — no `phases`, no `io`, no execution. A `DelegatePhase` whose `subgraph:` resolves to a persona is a hard error: the runtime would fail when `child.run()` is called against a persona-derived harness, but the failure mode is opaque. Catch it at compile time.

---

## Public API contract (lock this before coding)

```python
# src/core/graph_agent/core/validators/context_bridge.py

from pathlib import Path
from ..compiler import CompileIssue
from ..manifest import GraphSkillDef

def check_context_bridge(
    parent: GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    """Statically validate every DelegatePhase.context_bridge in `parent`.

    For each `DelegatePhase` in `parent.phases`, resolve the child SKILL.md
    relative to `base_dir`, parse its frontmatter through `parse_skill_file`
    + the SkillManifest discriminated union, and compare the bridge's
    child-side names against the child's `io.inputs` / `io.outputs`
    declarations. Returns an empty list on full pass; otherwise one
    `CompileIssue` per mismatch. Does not raise — every error becomes an
    issue so callers (compile_skill, Studio) can aggregate diagnostics.
    """
```

The signature is keyword-only for `base_dir` to forbid accidental positional misuse — `check_context_bridge(parent, child_dir)` would otherwise look identical to `check_context_bridge(parent, base_dir)` to a caller who didn't read the docstring.

---

## Tasks

### Task 1: Create the validator package skeleton

**Files:**
- Create: `src/core/graph_agent/core/validators/__init__.py`
- Create: `src/core/graph_agent/core/validators/context_bridge.py`

- [ ] **Step 1: Write the package marker**

```python
# src/core/graph_agent/core/validators/__init__.py
```

(File is intentionally empty — validators are imported by their fully qualified module path, not re-exported, to keep the import surface explicit.)

- [ ] **Step 2: Write a stub validator with the docstring + signature**

```python
# src/core/graph_agent/core/validators/context_bridge.py
"""Static semantic validator: DelegatePhase.context_bridge ↔ child io.

See docs/superpowers/plans/2026-04-25-pr7-context-bridge-validator.md for
the full rule catalogue and rationale.
"""
from __future__ import annotations

from pathlib import Path

from ..compiler import CompileIssue
from ..manifest import GraphSkillDef


def check_context_bridge(
    parent: GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    """Run the context_bridge static type check on every DelegatePhase."""
    raise NotImplementedError("filled in by Task 2 onward")
```

- [ ] **Step 3: Confirm the import path resolves**

Run: `source .venv/bin/activate && pytest --collect-only tests/graph_agent/core/ 2>&1 | tail -5`
Expected: pytest's collection output includes existing tests cleanly (no `ImportError` or `collection failure`). The new `validators/` package is empty for tests; we'll add tests in Task 2. The point of this step is just to confirm the new `__init__.py` doesn't break the existing test collection — `from ..compiler import CompileIssue` is a relative import that resolves correctly when pytest runs (pyproject.toml: `pythonpath = ["src/core"]`).

- [ ] **Step 4: Commit**

```bash
git add src/core/graph_agent/core/validators/__init__.py src/core/graph_agent/core/validators/context_bridge.py
git commit -m "feat(validators): scaffold validators package with context_bridge stub"
```

---

### Task 2: Test the happy path — inputs and outputs both match

**Files:**
- Create: `tests/graph_agent/core/validators/__init__.py`
- Create: `tests/graph_agent/core/validators/test_context_bridge.py`

- [ ] **Step 1: Create the test package marker**

```python
# tests/graph_agent/core/validators/__init__.py
```

- [ ] **Step 2: Write `test_returns_empty_when_inputs_and_outputs_align`**

```python
# tests/graph_agent/core/validators/test_context_bridge.py
"""Unit tests for the context_bridge validator."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from graph_agent.core.manifest import GraphSkillDef, SkillManifest
from graph_agent.core.validators.context_bridge import (
    check_context_bridge,
)


def _write_child_graph(tmp_path: Path, *, name: str, inputs: list[str], outputs: list[str]) -> Path:
    """Stage a minimal valid GraphSkillDef SKILL.md and return its path.

    Note: hand-built column-0 string instead of textwrap.dedent. Mixing
    a dedented template with f-string-interpolated nested-indent blocks
    makes textwrap.dedent see different common-leading-whitespace and
    produces a left-shifted ``---`` line that breaks the frontmatter
    delimiter. Don't switch to dedent without reproving.
    """
    inputs_lines = "\n".join(f"    - name: {n}\n      source: runtime" for n in inputs)
    outputs_lines = "\n".join(
        f"    - name: {n}\n      target: artifact" for n in outputs
    )
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        f"name: {name}\n"
        "description: child graph for context_bridge tests\n"
        "io:\n"
        "  inputs:\n"
        f"{inputs_lines}\n"
        "  outputs:\n"
        f"{outputs_lines}\n"
        "phases:\n"
        "  - name: only_phase\n"
        "    mode: logic\n"
        "    execute_steps:\n"
        "      - core.graph_agent.callbacks.events.SubgraphEnterEvent\n"
        "---\n"
    )
    path = tmp_path / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _build_parent(child_path: Path, bridge_inputs: dict[str, str], bridge_outputs: dict[str, str]) -> GraphSkillDef:
    """Construct a valid parent GraphSkillDef in-memory pointing at `child_path`."""
    raw = {
        "schema_version": "2.0",
        "type": "graph",
        "name": "parent",
        "description": "parent graph for context_bridge tests",
        "io": {"inputs": [], "outputs": []},
        "phases": [
            {
                "name": "delegate_phase",
                "mode": "delegate",
                "subgraph": child_path.name,
                "context_bridge": {
                    "inputs": bridge_inputs,
                    "outputs": bridge_outputs,
                },
            }
        ],
    }
    return TypeAdapter(SkillManifest).validate_python(raw)


def test_returns_empty_when_inputs_and_outputs_align(tmp_path: Path) -> None:
    child = _write_child_graph(
        tmp_path,
        name="child",
        inputs=["alpha", "beta"],
        outputs=["gamma"],
    )
    parent = _build_parent(
        child_path=child,
        bridge_inputs={"parent_a": "alpha", "parent_b": "beta"},
        bridge_outputs={"gamma": "parent_g"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert issues == []
```

- [ ] **Step 3: Run test — expect FAIL with NotImplementedError**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_returns_empty_when_inputs_and_outputs_align -xvs`
Expected: FAILED — NotImplementedError from the stub.

- [ ] **Step 4: Implement just enough for the happy path**

Replace `check_context_bridge` body in `src/core/graph_agent/core/validators/context_bridge.py`:

```python
from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from ..compiler import CompileIssue
from ..manifest import GraphSkillDef, SkillManifest
from ..parser import parse_skill_file
from ..exceptions import SkillLoadError


def check_context_bridge(
    parent: GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    issues: list[CompileIssue] = []
    for phase in parent.phases:
        if phase.mode != "delegate":  # type: ignore[attr-defined]
            continue
        # phase is DelegatePhase here; mypy can't narrow on Literal yet, but
        # the runtime field access is safe.
        child_path = (base_dir / phase.subgraph).resolve()  # type: ignore[attr-defined]
        try:
            parsed = parse_skill_file(child_path)
        except SkillLoadError as exc:
            issues.append(CompileIssue(
                rule_id="F-context-bridge-child-invalid",
                severity="FATAL",
                location=f"{child_path}:frontmatter",
                message=str(exc),
            ))
            continue
        # parse_skill_file returns {"frontmatter": dict, "human_body": str};
        # only the frontmatter is what SkillManifest validates.
        child_raw = parsed["frontmatter"]
        try:
            child_manifest = TypeAdapter(SkillManifest).validate_python(child_raw)
        except ValidationError as exc:
            issues.append(CompileIssue(
                rule_id="F-context-bridge-child-invalid",
                severity="FATAL",
                location=f"{child_path}:frontmatter",
                message=str(exc),
            ))
            continue
        if child_manifest.type != "graph":
            # Handled in later tasks (agent → WARNING, persona → FATAL)
            continue
        declared_inputs = {io.name for io in child_manifest.io.inputs}
        declared_outputs = {io.name for io in child_manifest.io.outputs}
        bridge = phase.context_bridge  # type: ignore[attr-defined]
        for parent_key, child_input in bridge.inputs.items():
            if child_input not in declared_inputs:
                issues.append(CompileIssue(
                    rule_id="F-context-bridge-input-undeclared",
                    severity="FATAL",
                    location=f"SKILL.md:phases.{phase.name}.context_bridge.inputs.{parent_key}",
                    message=(
                        f"DelegatePhase '{phase.name}' wires parent context "
                        f"'{parent_key}' to child input '{child_input}', but "
                        f"{child_path.name} declares no io.input named "
                        f"'{child_input}'. Declared: {sorted(declared_inputs) or '[]'}."
                    ),
                ))
        for child_key, parent_key in bridge.outputs.items():
            if child_key not in declared_outputs:
                issues.append(CompileIssue(
                    rule_id="F-context-bridge-output-undeclared",
                    severity="FATAL",
                    location=f"SKILL.md:phases.{phase.name}.context_bridge.outputs.{child_key}",
                    message=(
                        f"DelegatePhase '{phase.name}' reads child output "
                        f"'{child_key}' (mapping to parent '{parent_key}'), but "
                        f"{child_path.name} declares no io.output named "
                        f"'{child_key}'. Declared: {sorted(declared_outputs) or '[]'}."
                    ),
                ))
    return issues
```

- [ ] **Step 5: Run test — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_returns_empty_when_inputs_and_outputs_align -xvs`
Expected: PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/core/graph_agent/core/validators/context_bridge.py tests/graph_agent/core/validators/__init__.py tests/graph_agent/core/validators/test_context_bridge.py
git commit -m "feat(validators): context_bridge happy path with first passing test"
```

---

### Task 3: Test FATAL when a child input name is undeclared

**Files:**
- Modify: `tests/graph_agent/core/validators/test_context_bridge.py`

- [ ] **Step 1: Add `test_fatal_when_child_input_undeclared`**

Append to `tests/graph_agent/core/validators/test_context_bridge.py`:

```python
def test_fatal_when_child_input_undeclared(tmp_path: Path) -> None:
    child = _write_child_graph(
        tmp_path, name="child", inputs=["alpha"], outputs=["gamma"],
    )
    parent = _build_parent(
        child_path=child,
        bridge_inputs={"parent_typo": "alphaa"},  # 'alphaa' not in child.io.inputs
        bridge_outputs={"gamma": "parent_g"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "F-context-bridge-input-undeclared"
    assert issue.severity == "FATAL"
    assert "alphaa" in issue.message
    assert "alpha" in issue.message  # the available declared name appears in the help
    assert issue.location.endswith("inputs.parent_typo")
```

- [ ] **Step 2: Run — expect PASS (already implemented in Task 2)**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_fatal_when_child_input_undeclared -xvs`
Expected: PASSED. (If FAIL, the message format in Task 2's implementation diverged — fix the implementation to match the assertions.)

- [ ] **Step 3: Commit**

```bash
git add tests/graph_agent/core/validators/test_context_bridge.py
git commit -m "test(validators): lock context_bridge undeclared-input FATAL contract"
```

---

### Task 4: Test FATAL when a child output name is undeclared

**Files:**
- Modify: `tests/graph_agent/core/validators/test_context_bridge.py`

- [ ] **Step 1: Add `test_fatal_when_child_output_undeclared`**

```python
def test_fatal_when_child_output_undeclared(tmp_path: Path) -> None:
    child = _write_child_graph(
        tmp_path, name="child", inputs=["alpha"], outputs=["gamma"],
    )
    parent = _build_parent(
        child_path=child,
        bridge_inputs={"parent_a": "alpha"},
        bridge_outputs={"gammma": "parent_g"},  # typo: child has 'gamma'
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "F-context-bridge-output-undeclared"
    assert issue.severity == "FATAL"
    assert "gammma" in issue.message
    assert "gamma" in issue.message
    assert issue.location.endswith("outputs.gammma")
```

- [ ] **Step 2: Run — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_fatal_when_child_output_undeclared -xvs`
Expected: PASSED.

- [ ] **Step 3: Commit**

```bash
git add tests/graph_agent/core/validators/test_context_bridge.py
git commit -m "test(validators): lock context_bridge undeclared-output FATAL contract"
```

---

### Task 5: Test FATAL when child SKILL.md is missing

**Files:**
- Modify: `tests/graph_agent/core/validators/test_context_bridge.py`
- Modify: `src/core/graph_agent/core/validators/context_bridge.py`

- [ ] **Step 1: Add `test_fatal_when_child_path_missing`**

```python
def test_fatal_when_child_path_missing(tmp_path: Path) -> None:
    parent = _build_parent(
        child_path=tmp_path / "nonexistent.md",
        bridge_inputs={"parent_a": "alpha"},
        bridge_outputs={"gamma": "parent_g"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-context-bridge-child-missing"
    assert issues[0].severity == "FATAL"
    assert "nonexistent.md" in issues[0].message
```

- [ ] **Step 2: Run — expect FAIL (validator currently lets `parse_skill_file` raise on missing path; the FAIL surfaces as `F-context-bridge-child-invalid`, not `-missing`)**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_fatal_when_child_path_missing -xvs`
Expected: AssertionError on `rule_id`.

- [ ] **Step 3: Add an explicit `child_path.is_file()` check before `parse_skill_file`**

In `validators/context_bridge.py`, replace the start of the loop body:

```python
        child_path = (base_dir / phase.subgraph).resolve()  # type: ignore[attr-defined]
        if not child_path.is_file():
            issues.append(CompileIssue(
                rule_id="F-context-bridge-child-missing",
                severity="FATAL",
                location=f"SKILL.md:phases.{phase.name}.subgraph",
                message=(
                    f"DelegatePhase '{phase.name}' subgraph not found: "
                    f"{child_path} (resolved from '{phase.subgraph}'). "
                    f"Check the path is relative to the parent SKILL.md."
                ),
            ))
            continue
        try:
            child_raw = parse_skill_file(child_path)
        except SkillLoadError as exc:
            ...
```

- [ ] **Step 4: Run — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_fatal_when_child_path_missing -xvs`
Expected: PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/core/graph_agent/core/validators/context_bridge.py tests/graph_agent/core/validators/test_context_bridge.py
git commit -m "feat(validators): emit F-context-bridge-child-missing for unresolved subgraph paths"
```

---

### Task 6: Test FATAL when child SKILL.md frontmatter is invalid

**Files:**
- Modify: `tests/graph_agent/core/validators/test_context_bridge.py`

- [ ] **Step 1: Add `test_fatal_when_child_frontmatter_invalid`**

```python
def test_fatal_when_child_frontmatter_invalid(tmp_path: Path) -> None:
    bad_child = tmp_path / "bad.md"
    bad_child.write_text(
        textwrap.dedent(
            """\
            ---
            schema_version: "2.0"
            type: graph
            name: bad
            description: missing-required-io
            phases:
              - name: x
                mode: logic
                execute_steps:
                  - some.path
            ---
            """
        ),
        encoding="utf-8",
    )
    parent = _build_parent(
        child_path=bad_child,
        bridge_inputs={"p": "x"},
        bridge_outputs={"y": "p"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert any(i.rule_id == "F-context-bridge-child-invalid" for i in issues)
    invalid = next(i for i in issues if i.rule_id == "F-context-bridge-child-invalid")
    assert invalid.severity == "FATAL"
    assert str(bad_child) in invalid.location
```

- [ ] **Step 2: Run — expect PASS (Task 2 already wired ValidationError → F-context-bridge-child-invalid)**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_fatal_when_child_frontmatter_invalid -xvs`
Expected: PASSED.

- [ ] **Step 3: Commit**

```bash
git add tests/graph_agent/core/validators/test_context_bridge.py
git commit -m "test(validators): lock context_bridge invalid-child-frontmatter FATAL"
```

---

### Task 7: Test WARNING when child is an AgentSkillDef

**Files:**
- Modify: `tests/graph_agent/core/validators/test_context_bridge.py`
- Modify: `src/core/graph_agent/core/validators/context_bridge.py`

- [ ] **Step 1: Helper to write a minimal valid AgentSkillDef child**

Add to `test_context_bridge.py` (above the test functions):

```python
def _write_child_agent(tmp_path: Path, *, name: str) -> Path:
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: agent\n"
        f"name: {name}\n"
        "description: child agent skill\n"
        "agent_profile:\n"
        "  role: tester\n"
        "  goal: be tested\n"
        "---\n"
    )
    path = tmp_path / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path
```

- [ ] **Step 2: Add `test_warning_when_child_is_agent_skill`**

```python
def test_warning_when_child_is_agent_skill(tmp_path: Path) -> None:
    child = _write_child_agent(tmp_path, name="agent_child")
    parent = _build_parent(
        child_path=child,
        bridge_inputs={"parent_x": "anything"},
        bridge_outputs={"anything_back": "parent_y"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "W-context-bridge-agent-child"
    assert issues[0].severity == "WARNING"
    assert "agent" in issues[0].message.lower()
    assert "delegate_phase" in issues[0].location
```

- [ ] **Step 3: Run — expect FAIL (Task 2's implementation silently `continue`s on non-graph children)**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_warning_when_child_is_agent_skill -xvs`
Expected: AssertionError on `len(issues) == 1`.

- [ ] **Step 4: Replace the `continue` block with explicit dispatch**

In `validators/context_bridge.py`, replace:

```python
        if child_manifest.type != "graph":
            # Handled in later tasks (agent → WARNING, persona → FATAL)
            continue
```

with:

```python
        from ..manifest import AgentSkillDef, PersonaSkillDef
        if isinstance(child_manifest, AgentSkillDef):
            issues.append(CompileIssue(
                rule_id="W-context-bridge-agent-child",
                severity="WARNING",
                location=f"SKILL.md:phases.{phase.name}.subgraph",
                message=(
                    f"DelegatePhase '{phase.name}' delegates to agent skill "
                    f"'{child_path.name}', which has no io declaration. "
                    f"context_bridge inputs/outputs cannot be statically "
                    f"verified; runtime mismatches will surface as None values."
                ),
            ))
            continue
        if isinstance(child_manifest, PersonaSkillDef):
            issues.append(CompileIssue(
                rule_id="F-context-bridge-persona-child",
                severity="FATAL",
                location=f"SKILL.md:phases.{phase.name}.subgraph",
                message=(
                    f"DelegatePhase '{phase.name}' delegates to persona "
                    f"'{child_path.name}'. Persona skills carry no execution "
                    f"semantics — delegation will fail at runtime. Use "
                    f"adopted_persona on an llm phase instead."
                ),
            ))
            continue
        # otherwise child is GraphSkillDef — fall through to io check
```

(Hoist the `from ..manifest import AgentSkillDef, PersonaSkillDef` to the top-level imports of the module — keeping the inline import here is illustrative only.)

- [ ] **Step 5: Run — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_warning_when_child_is_agent_skill -xvs`
Expected: PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/core/graph_agent/core/validators/context_bridge.py tests/graph_agent/core/validators/test_context_bridge.py
git commit -m "feat(validators): WARNING when DelegatePhase child is an AgentSkillDef"
```

---

### Task 8: Test FATAL when child is a PersonaSkillDef

**Files:**
- Modify: `tests/graph_agent/core/validators/test_context_bridge.py`

- [ ] **Step 1: Helper for persona child**

Add to `test_context_bridge.py`:

```python
def _write_child_persona(tmp_path: Path, *, name: str) -> Path:
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: persona\n"
        f"name: {name}\n"
        "description: child persona skill\n"
        "role_profile: |\n"
        "  A test persona used as a (forbidden) delegate child.\n"
        "---\n"
    )
    path = tmp_path / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path
```

- [ ] **Step 2: Add `test_fatal_when_child_is_persona_skill`**

```python
def test_fatal_when_child_is_persona_skill(tmp_path: Path) -> None:
    child = _write_child_persona(tmp_path, name="persona_child")
    parent = _build_parent(
        child_path=child,
        bridge_inputs={"parent_x": "anything"},
        bridge_outputs={"anything_back": "parent_y"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-context-bridge-persona-child"
    assert issues[0].severity == "FATAL"
    assert "persona" in issues[0].message.lower()
```

- [ ] **Step 3: Run — expect PASS (Task 7 already wired the persona branch)**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_fatal_when_child_is_persona_skill -xvs`
Expected: PASSED.

- [ ] **Step 4: Commit**

```bash
git add tests/graph_agent/core/validators/test_context_bridge.py
git commit -m "test(validators): lock context_bridge persona-child FATAL contract"
```

---

### Task 9: Test that non-delegate phases are skipped

**Files:**
- Modify: `tests/graph_agent/core/validators/test_context_bridge.py`

- [ ] **Step 1: Add `test_returns_empty_when_parent_has_no_delegate_phases`**

```python
def test_returns_empty_when_parent_has_no_delegate_phases(tmp_path: Path) -> None:
    raw = {
        "schema_version": "2.0",
        "type": "graph",
        "name": "all_logic",
        "description": "no delegate phases at all",
        "io": {"inputs": [], "outputs": []},
        "phases": [
            {
                "name": "logic_only",
                "mode": "logic",
                "execute_steps": ["some.module.fn"],
            },
            {
                "name": "llm_only",
                "mode": "llm",
                "prompt": "do the thing",
            },
        ],
    }
    parent = TypeAdapter(SkillManifest).validate_python(raw)

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert issues == []
```

- [ ] **Step 2: Run — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_returns_empty_when_parent_has_no_delegate_phases -xvs`
Expected: PASSED.

- [ ] **Step 3: Commit**

```bash
git add tests/graph_agent/core/validators/test_context_bridge.py
git commit -m "test(validators): lock context_bridge no-delegate-phase fast path"
```

---

### Task 10: Test multiple-issue accumulation in a single phase

**Files:**
- Modify: `tests/graph_agent/core/validators/test_context_bridge.py`

- [ ] **Step 1: Add `test_accumulates_input_and_output_issues_in_one_phase`**

```python
def test_accumulates_input_and_output_issues_in_one_phase(tmp_path: Path) -> None:
    child = _write_child_graph(
        tmp_path, name="child", inputs=["alpha"], outputs=["gamma"],
    )
    parent = _build_parent(
        child_path=child,
        bridge_inputs={"p_a": "alpha", "p_typo": "alfa"},
        bridge_outputs={"gamma": "p_g", "delta": "p_d"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    rule_ids = sorted(i.rule_id for i in issues)
    assert rule_ids == [
        "F-context-bridge-input-undeclared",
        "F-context-bridge-output-undeclared",
    ]
```

- [ ] **Step 2: Run — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_accumulates_input_and_output_issues_in_one_phase -xvs`
Expected: PASSED.

- [ ] **Step 3: Commit**

```bash
git add tests/graph_agent/core/validators/test_context_bridge.py
git commit -m "test(validators): accumulate input + output issues per delegate phase"
```

---

### Task 11: Test WARNING when two parent_keys map to the same child_input

> Codex plan-review must-fix: in `bridge.inputs`, multiple parent_keys mapping to the same `child_input` value cause silent last-wins overwrite at runtime (`subgraph.py:94`). Surface this at compile time.

**Files:**
- Modify: `tests/graph_agent/core/validators/test_context_bridge.py`
- Modify: `src/core/graph_agent/core/validators/context_bridge.py`

- [ ] **Step 1: Add `test_warning_when_duplicate_child_input`**

```python
def test_warning_when_duplicate_child_input(tmp_path: Path) -> None:
    child = _write_child_graph(
        tmp_path, name="child", inputs=["alpha"], outputs=["gamma"],
    )
    parent = _build_parent(
        child_path=child,
        bridge_inputs={"parent_a": "alpha", "parent_b": "alpha"},  # both → alpha
        bridge_outputs={"gamma": "parent_g"},
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "W-context-bridge-duplicate-child-input"
    assert issue.severity == "WARNING"
    assert "alpha" in issue.message
    assert "parent_a" in issue.message
    assert "parent_b" in issue.message
```

- [ ] **Step 2: Run — expect FAIL (validator does not detect duplicates yet)**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_warning_when_duplicate_child_input -xvs`
Expected: AssertionError on `len(issues) == 1`.

- [ ] **Step 3: Add the duplicate-detection block to the validator**

Insert into `validators/context_bridge.py`, **before** the "iterate bridge.inputs and check membership" loop (so duplicates fire even when every individual entry resolves):

```python
        # Detect parent_keys that map to the same child_input (last-wins
        # silent overwrite at runtime; subgraph.py:94 iteration order).
        seen_inputs: dict[str, list[str]] = {}
        for parent_key, child_input in bridge.inputs.items():
            seen_inputs.setdefault(child_input, []).append(parent_key)
        for child_input, parent_keys in seen_inputs.items():
            if len(parent_keys) > 1:
                issues.append(CompileIssue(
                    rule_id="W-context-bridge-duplicate-child-input",
                    severity="WARNING",
                    location=f"SKILL.md:phases.{phase.name}.context_bridge.inputs",
                    message=(
                        f"DelegatePhase '{phase.name}' maps parent keys "
                        f"{sorted(parent_keys)} to the same child input "
                        f"'{child_input}'. Runtime iterates the dict and "
                        f"last-wins (subgraph.py:94); silent data loss."
                    ),
                ))
```

- [ ] **Step 4: Run — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_warning_when_duplicate_child_input -xvs`
Expected: PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/core/graph_agent/core/validators/context_bridge.py tests/graph_agent/core/validators/test_context_bridge.py
git commit -m "feat(validators): warn when parent_keys collide on the same child input"
```

---

### Task 12: Test WARNING when two child_keys map to the same parent_key

> Symmetric counterpart of Task 11 on the outputs side: `subgraph.py:227` overwrites `parent_ctx[parent_key]` for each child_key, so multiple child_keys mapping to the same parent_key silently drop all but the last.

**Files:**
- Modify: `tests/graph_agent/core/validators/test_context_bridge.py`
- Modify: `src/core/graph_agent/core/validators/context_bridge.py`

- [ ] **Step 1: Add `test_warning_when_duplicate_parent_output`**

```python
def test_warning_when_duplicate_parent_output(tmp_path: Path) -> None:
    child = _write_child_graph(
        tmp_path, name="child", inputs=["alpha"], outputs=["gamma", "delta"],
    )
    parent = _build_parent(
        child_path=child,
        bridge_inputs={"parent_a": "alpha"},
        bridge_outputs={"gamma": "parent_g", "delta": "parent_g"},  # both → parent_g
    )

    issues = check_context_bridge(parent, base_dir=tmp_path)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "W-context-bridge-duplicate-parent-output"
    assert issue.severity == "WARNING"
    assert "parent_g" in issue.message
    assert "gamma" in issue.message
    assert "delta" in issue.message
```

- [ ] **Step 2: Run — expect FAIL**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_warning_when_duplicate_parent_output -xvs`
Expected: AssertionError on `len(issues) == 1`.

- [ ] **Step 3: Add the symmetric output-side duplicate block**

Insert into `validators/context_bridge.py`, **before** the "iterate bridge.outputs and check membership" loop:

```python
        # Detect child_keys that map to the same parent_key (last-wins
        # silent overwrite at runtime; subgraph.py:227).
        seen_outputs: dict[str, list[str]] = {}
        for child_key, parent_key in bridge.outputs.items():
            seen_outputs.setdefault(parent_key, []).append(child_key)
        for parent_key, child_keys in seen_outputs.items():
            if len(child_keys) > 1:
                issues.append(CompileIssue(
                    rule_id="W-context-bridge-duplicate-parent-output",
                    severity="WARNING",
                    location=f"SKILL.md:phases.{phase.name}.context_bridge.outputs",
                    message=(
                        f"DelegatePhase '{phase.name}' maps child outputs "
                        f"{sorted(child_keys)} to the same parent key "
                        f"'{parent_key}'. Runtime iterates the dict and "
                        f"last-wins (subgraph.py:227); silent data loss."
                    ),
                ))
```

- [ ] **Step 4: Run — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_context_bridge.py::test_warning_when_duplicate_parent_output -xvs`
Expected: PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/core/graph_agent/core/validators/context_bridge.py tests/graph_agent/core/validators/test_context_bridge.py
git commit -m "feat(validators): warn when child outputs collide on the same parent key"
```

---

### Task 13: Wire the validator into compile_skill

**Files:**
- Modify: `src/core/graph_agent/core/compiler.py` (lines 148-167 and module docstring 27-44)
- Create: `tests/graph_agent/core/test_compile_skill_context_bridge_integration.py`

- [ ] **Step 1: Decide test file location**

Run: `ls tests/graph_agent/core/test_compile*.py 2>/dev/null` (from repo root, in activated venv)
Expected: empty (no existing compile_skill test file). Create the new integration test file.

- [ ] **Step 2: Write the integration test**

```python
# tests/graph_agent/core/test_compile_skill_context_bridge_integration.py
"""End-to-end: compile_skill on a parent with a typo'd context_bridge surfaces
the validator's F-context-bridge-output-undeclared FATAL."""
from __future__ import annotations

import textwrap
from pathlib import Path

from graph_agent.core.compiler import compile_skill


def test_compile_skill_propagates_context_bridge_fatal(tmp_path: Path) -> None:
    child = tmp_path / "child.md"
    child.write_text(
        textwrap.dedent(
            """\
            ---
            schema_version: "2.0"
            type: graph
            name: child
            description: child for compile_skill integration test
            io:
              inputs:
                - name: alpha
                  source: runtime
              outputs:
                - name: gamma
                  target: artifact
            phases:
              - name: only
                mode: logic
                execute_steps:
                  - some.module.fn
            ---
            """
        ),
        encoding="utf-8",
    )
    parent = tmp_path / "parent.md"
    parent.write_text(
        textwrap.dedent(
            """\
            ---
            schema_version: "2.0"
            type: graph
            name: parent
            description: parent for compile_skill integration test
            io:
              inputs: []
              outputs: []
            phases:
              - name: delegate_phase
                mode: delegate
                subgraph: child.md
                context_bridge:
                  inputs:
                    parent_a: alpha
                  outputs:
                    gammma: parent_g
            ---
            """
        ),
        encoding="utf-8",
    )

    result = compile_skill(parent)

    rule_ids = sorted(i.rule_id for i in result.fatals)
    assert "F-context-bridge-output-undeclared" in rule_ids
    assert result.passed is False
```

- [ ] **Step 3: Run — expect FAIL (validator not yet wired)**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/test_compile_skill_context_bridge_integration.py -xvs`
Expected: AssertionError — `F-context-bridge-output-undeclared` not in fatals.

- [ ] **Step 4: Wire `check_context_bridge` into `compile_skill`**

In `src/core/graph_agent/core/compiler.py`, replace the post-Pydantic block (lines 148-167):

```python
    # Pydantic does the structural validation when the manifest is
    # constructed in load_workflow_from_md. Surface validation errors
    # as fatals here too so static compile catches them before runtime.
    try:
        from pydantic import TypeAdapter, ValidationError
        from .manifest import SkillManifest

        TypeAdapter(SkillManifest).validate_python(frontmatter)
    except ValidationError as ve:
        for err in ve.errors():
            loc = ".".join(str(p) for p in err.get("loc", ()))
            result.issues.append(CompileIssue(
                rule_id="F-pydantic",
                severity="FATAL",
                location=f"SKILL.md:{loc or 'frontmatter'}",
                message=err.get("msg", "Pydantic validation failed"),
            ))
        if not result.passed:
            return result
```

with:

```python
    # Pydantic does the structural validation when the manifest is
    # constructed in load_workflow_from_md. Surface validation errors
    # as fatals here too so static compile catches them before runtime.
    from pydantic import TypeAdapter, ValidationError
    from .manifest import GraphSkillDef, SkillManifest

    try:
        manifest = TypeAdapter(SkillManifest).validate_python(frontmatter)
    except ValidationError as ve:
        for err in ve.errors():
            loc = ".".join(str(p) for p in err.get("loc", ()))
            result.issues.append(CompileIssue(
                rule_id="F-pydantic",
                severity="FATAL",
                location=f"SKILL.md:{loc or 'frontmatter'}",
                message=err.get("msg", "Pydantic validation failed"),
            ))
        return result

    # PR #7 semantic checks (run only when Pydantic validation succeeds)
    if isinstance(manifest, GraphSkillDef):
        from .validators.context_bridge import check_context_bridge
        result.issues.extend(
            check_context_bridge(manifest, base_dir=skill_path.parent)
        )
```

- [ ] **Step 5: Run integration test — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/test_compile_skill_context_bridge_integration.py -xvs`
Expected: PASSED.

- [ ] **Step 6: Update compiler.py docstring TODO list**

In `src/core/graph_agent/core/compiler.py`, replace the `context_bridge` bullet in the `TODO(PR#7)` block (around line 36) with a note that it now ships:

```python
- **context_bridge static type check** ✅ shipped in PR #7 step 1.
  See ``validators/context_bridge.py``. The remaining four checks below
  still have only load-time fallbacks.
```

(Leave the other four bullets untouched.)

- [ ] **Step 7: Commit**

```bash
git add src/core/graph_agent/core/compiler.py tests/graph_agent/core/test_compile_skill_context_bridge_integration.py
git commit -m "feat(compiler): run context_bridge validator after Pydantic for graph skills"
```

---

### Task 14: Run the full test suite to catch regressions

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite (excluding the network-dependent llm_client_manager)**

Run: `source .venv/bin/activate && pytest tests/ --ignore=tests/llm_client_manager -q`
Expected: all tests pass (the previous baseline was **362 passed**; this PR adds **11 unit tests** in `test_context_bridge.py` (Tasks 2-12) + **1 integration test** in `test_compile_skill_context_bridge_integration.py` (Task 13), so the new total should be **374 passed**). Any pre-existing failure must be unrelated to this work — investigate before committing.

- [ ] **Step 2: Re-run only the new test files in verbose mode for a sanity check**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/ tests/graph_agent/core/test_compile_skill_context_bridge_integration.py -v`
Expected: 12 PASSED.

- [ ] **Step 3: Run the existing compile_skill / load_workflow_from_md tests, if any, to verify the new wiring did not break them**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/ -k "compile or manifest or loader" -v`
Expected: all PASS. (The validator is additive on top of Pydantic — no existing test should observe new issues unless its fixture genuinely has a context_bridge mismatch.)

- [ ] **Step 4: No commit (this task is verification only)**

---

### Task 15: Send git diff to Codex for code review

**Files:** none (review handoff)

- [ ] **Step 1: Stage the full PR's worth of commits and capture the diff range**

Run: `git log --oneline origin/feat/studio-phase0-manifest..HEAD` and verify the new commits from Tasks 1-13 are listed (Task 14 has no commit).

- [ ] **Step 2: Generate the diff in a file Codex can read**

Run: `git diff origin/feat/studio-phase0-manifest..HEAD -- src/core/graph_agent/core/validators src/core/graph_agent/core/compiler.py tests/graph_agent/core/validators tests/graph_agent/core/test_compile_skill_context_bridge_integration.py > /tmp/pr7-step1-diff.txt`

- [ ] **Step 3: Send a narrow-focus review prompt to Codex**

Use the heredoc + `--wait --timeout 600` form per CLAUDE.md. **Keep the prompt narrow** (CLAUDE.md memory: large prompts hang Codex). Ask three yes/no questions, no rubric scoring:

```bash
command ccb ask --wait --timeout 600 a1 <<'EOF'
请用中文回答。这是 PR #7 step 1 (context_bridge static validator) 的代码审查请求,只要回答 3 个 yes/no:

1) `validators/context_bridge.py` 的 6 个 rule_id (F-child-missing / F-child-invalid / F-input-undeclared / F-output-undeclared / W-agent-child / F-persona-child) 在所有应该触发的路径上都触发了吗?有没有漏分支?
2) `compile_skill` 在 Pydantic ValidationError 后立刻 return,在 isinstance(manifest, GraphSkillDef) 才跑 check_context_bridge——这个顺序保证 manifest 总是结构良好,无需额外 try/except 包裹 validator 调用,对吗?
3) `phase.context_bridge.inputs` 是 dict[parent_key, child_input],validator 检查的是 .values()(child_input 一侧)对应到 child 的 io.inputs[*].name——这个语义和 subgraph.py:94 的运行时一致吗?

不打分,不写 rubric,直接给三个 YES/NO + 简短理由(每问 ≤ 2 行)。

git diff (限定到本 PR 4 个 path):
--- CHANGES START ---
[paste contents of /tmp/pr7-step1-diff.txt here]
--- CHANGES END ---
EOF
```

- [ ] **Step 4: Address must-fix from Codex**

If Codex flags a true issue, write a follow-up commit. If Codex's concern is non-issue (false positive), document why in the eventual PR description. **Do not** automatically apply Codex's style suggestions — confirm they're not "nice-to-have" first per CLAUDE.md.

- [ ] **Step 5: No commit (review-only task; commits happen if must-fix surfaces)**

---

## Self-Review (run after writing the plan, before sending to Gemini)

**1. Spec coverage** — every PR #7 step-1 deliverable from `core/compiler.py`'s docstring is covered:
   - context_bridge static type check ✅ (Tasks 1-13)
   - Tool-path resolvability ❌ (separate PR #7 step — not this plan)
   - Subgraph cycle detection ❌ (separate)
   - Persona resolution ❌ (separate)
   - Custom rules.yaml decision ❌ (separate)

**2. Placeholder scan** — re-read each Task. No "TBD", no "implement appropriately", every code block is the literal source.

**3. Type consistency** — `check_context_bridge(parent: GraphSkillDef, *, base_dir: Path) -> list[CompileIssue]` is the only public signature; it appears identically in Task 1 (stub), Task 2 (real implementation), and Task 13 (caller in compile_skill). The 8 rule_ids in the catalogue table appear with the same spelling in every test assertion and every implementation branch. The location string format `"SKILL.md:phases.<phase_name>.context_bridge.inputs.<parent_key>"` is consistent across Task 2's implementation and Task 3's `endswith` assertion. The location format for the duplicate rules omits the trailing `.<key>` since the issue is collection-level (`SKILL.md:phases.<phase_name>.context_bridge.inputs` / `...outputs`).

**4. PR #7 docstring update** — Task 13 Step 6 strikes through the context_bridge bullet only and leaves the other four PR #7 TODOs intact. After this PR ships, the next "PR #7 step" (likely subgraph cycle detection) can land as a sibling validator with the same package layout.

**5. Test count math** — baseline 362 passed; Tasks 2-12 each add 1 unit test = 11 unit tests in `test_context_bridge.py`; Task 13 adds 1 integration test = total +12 → 374 passed expected.

---

## Plan revision history

- **v1 (initial draft)** — 13 tasks, 6 rule_ids, expected 371 passed.
- **v2 (post-Codex plan-review must-fix + sanity-check fixes)**:
  - Added `W-context-bridge-duplicate-child-input` (Codex must-fix #1) — Task 11 (new).
  - Added `W-context-bridge-duplicate-parent-output` (symmetric counterpart) — Task 12 (new).
  - Old Tasks 11/12/13 renumbered to 13/14/15.
  - Replaced `textwrap.dedent` in `_write_child_graph` / `_write_child_agent` / `_write_child_persona` with column-0 string literals (sanity check uncovered: textwrap dedent against an f-string with variable-indent interpolation produces a left-shifted `---` that breaks frontmatter parsing).
  - Validator implementation in Task 2 now extracts `parsed["frontmatter"]` from `parse_skill_file`'s return (the function returns `{"frontmatter": dict, "human_body": str}`, not a flat dict).
  - Documented decision NOT to add `F-context-bridge-child-escapes-base` (Codex must-fix #2) — see "Rules deliberately NOT in this validator" subsection. Rationale: legitimate cross-skill `..` paths exist; staging-dir confinement belongs at the upload boundary, not in this validator.
  - Test count corrected: 362 → 374 (was 371; off-by-one in v1 + 2 new tests in v2).

---

## Pre-Execution Checkpoints

Before Task 1, complete these out-of-plan steps:

1. **Plan review by Gemini (designer-side)** — send this entire plan file to `a2` via `command ccb ask` (async + Monitor due to current Gemini latency). Wait for `[PLAN REVIEW REQUEST]` reply. Address must-fix items inline by editing this file before any Task 1 commit.

2. **Plan-only review by Codex (executor-side)** — narrow prompt: "is the rule catalogue complete given subgraph.py runtime semantics? any missing edge case?" Async OK. This is *separate* from Task 13's code review.

3. **Confirm `.venv/` is active** — `which pytest` should print `/home/sevenx/coding/agent-harness/.venv/bin/pytest`. If not: `source .venv/bin/activate`.

After both reviews land and any must-fix is patched into the plan, proceed to Task 1.
