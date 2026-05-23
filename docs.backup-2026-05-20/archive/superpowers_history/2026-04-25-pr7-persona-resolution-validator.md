# PR #7 Step 3 — Persona Resolution Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a static semantic validator that, at compile time, confirms every `adopted_persona` field on `AgentSkillDef` (top-level) and `LLMPhase` (inside `GraphSkillDef.phases`) resolves to an existing `PersonaSkillDef` via the loader's walk-up registry. Emit `F-persona-not-resolved` from `compile_skill()` when it doesn't. Third of the four PR #7 semantic checks; load-time fallback exists in `loader._resolve_persona`.

**Architecture:** A new sibling module `core/validators/persona_resolution.py` exports `check_persona_resolution(manifest, *, base_dir) -> list[CompileIssue]`. The validator iterates `adopted_persona` fields, calls the existing `loader._resolve_persona(name, base_dir)` (yes, an underscore-prefixed cross-module call — see "Scope decisions" below), and converts any raised `SkillLoadError` into a structured `CompileIssue`. `compile_skill()` invokes it after `check_subgraph_cycles` for both `AgentSkillDef` and `GraphSkillDef` manifests (`PersonaSkillDef` skips because personas are leaves and can't adopt other personas).

**Tech Stack:** Python 3.11+, existing `loader._resolve_persona`, existing `CompileIssue` dataclass.

---

## Scope decisions made up front

- **Reuse `loader._resolve_persona` directly, despite the underscore prefix** — duplicating the walk-up registry logic in the validator would create a two-source-of-truth bug risk (the user's handoff doc already flags `_resolve_persona`'s walk-up as a future TODO; we want the future fix to land in *one* place). Cross-module private call is ugly but correct. Comment explains.
- **One rule_id `F-persona-not-resolved` for both failure modes** — the loader's `SkillLoadError` covers (a) name not found in any candidate path and (b) name resolves to a non-persona artifact (e.g. graph skill named the same). The PM-facing message includes the verbatim loader error string, so the PM sees what went wrong; granular rule_ids would need refactoring `_resolve_persona` to raise distinct exception types, which is out of scope for this PR.
- **Validator runs for both `AgentSkillDef` and `GraphSkillDef`** — `adopted_persona` lives on both (top-level on agent, on each `LLMPhase` inside graph). One validator, two iteration shapes inside.
- **No deprecation of load-time `_resolve_persona`** — load-time still raises on resolution failure (different code path: full skill load via `load_workflow_from_md`). Compile-time validator is additive: it gives Studio a structured-issue path to surface the same failure earlier without needing to instantiate the harness.

---

## File Structure

| Path | Responsibility | New / Modified |
|---|---|---|
| `src/core/graph_agent/core/validators/persona_resolution.py` | Public `check_persona_resolution(manifest, *, base_dir) -> list[CompileIssue]`. Internal helper iterates `adopted_persona` fields and calls `_resolve_persona` per name. | Create |
| `src/core/graph_agent/core/compiler.py` | Add the validator call after `check_subgraph_cycles` inside the existing `isinstance(manifest, GraphSkillDef)` block, plus a parallel call for `AgentSkillDef` manifests (which the prior two validators don't touch). Update the TODO(PR#7) docstring to mark persona resolution as shipped. | Modify |
| `tests/graph_agent/core/validators/test_persona_resolution.py` | Unit tests for every emitted-issue and skipped path. Uses `tmp_path` fixtures. | Create |
| `tests/graph_agent/core/test_compile_skill_persona_resolution_integration.py` | One integration test asserting `compile_skill().fatals` contains `F-persona-not-resolved` when an `adopted_persona` is wrong. | Create |

---

## Issue catalogue

| rule_id | severity | trigger | location format |
|---|---|---|---|
| `F-persona-not-resolved` | FATAL | `loader._resolve_persona(name, base_dir)` raises `SkillLoadError` (covers both "name not found" and "resolved-but-wrong-type"). The loader's verbatim message is forwarded as the issue message. | For `AgentSkillDef`: `SKILL.md:adopted_persona`. For `LLMPhase` inside `GraphSkillDef`: `SKILL.md:phases.<phase_name>.adopted_persona`. |

---

## Public API contract

```python
# src/core/graph_agent/core/validators/persona_resolution.py

from pathlib import Path
from ..compiler import CompileIssue
from ..manifest import AgentSkillDef, GraphSkillDef

def check_persona_resolution(
    manifest: AgentSkillDef | GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    """For each `adopted_persona`, confirm it resolves to a PersonaSkillDef."""
```

`base_dir` is the parent SKILL.md's directory (same convention as `check_context_bridge`).

---

## Tasks

### Task 1: Create the validator stub

**Files:**
- Create: `src/core/graph_agent/core/validators/persona_resolution.py`

- [ ] **Step 1: Write the stub**

```python
"""Static semantic validator: adopted_persona name resolution.

See docs/superpowers/plans/2026-04-25-pr7-persona-resolution-validator.md.
"""
from __future__ import annotations

from pathlib import Path

from ..compiler import CompileIssue
from ..manifest import AgentSkillDef, GraphSkillDef


def check_persona_resolution(
    manifest: AgentSkillDef | GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    """For each adopted_persona, confirm it resolves to a PersonaSkillDef."""
    raise NotImplementedError("filled in by Task 2 onward")
```

- [ ] **Step 2: Confirm test collection works**

Run: `source .venv/bin/activate && pytest --collect-only tests/graph_agent/core/ 2>&1 | tail -3`
Expected: collection completes.

- [ ] **Step 3: Commit**

```bash
git add src/core/graph_agent/core/validators/persona_resolution.py
git commit -m "feat(validators): scaffold persona_resolution stub"
```

---

### Task 2: Test happy path on AgentSkillDef + implement core resolver

**Files:**
- Create: `tests/graph_agent/core/validators/test_persona_resolution.py`
- Modify: `src/core/graph_agent/core/validators/persona_resolution.py`

- [ ] **Step 1: Write helpers + happy-path test**

```python
"""Unit tests for the persona_resolution validator."""
from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

from graph_agent.core.manifest import (
    AgentSkillDef,
    GraphSkillDef,
    SkillManifest,
)
from graph_agent.core.parser import parse_skill_file
from graph_agent.core.validators.persona_resolution import (
    check_persona_resolution,
)


def _write_persona_skill(parent_dir: Path, *, name: str) -> Path:
    """Stage a minimal valid PersonaSkillDef under parent_dir/subskills/<name>/SKILL.md."""
    persona_dir = parent_dir / "subskills" / name
    persona_dir.mkdir(parents=True, exist_ok=True)
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: persona\n"
        f"name: {name}\n"
        f"description: persona {name} for resolution tests\n"
        "role_profile: |\n"
        "  Test persona for resolution.\n"
        "---\n"
    )
    path = persona_dir / "SKILL.md"
    path.write_text(body, encoding="utf-8")
    return path


def _write_agent_skill(
    parent_dir: Path, *, name: str, adopted_persona: str | None = None,
) -> Path:
    persona_line = (
        f"adopted_persona: {adopted_persona}\n"
        if adopted_persona is not None else ""
    )
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: agent\n"
        f"name: {name}\n"
        f"description: agent {name}\n"
        "agent_profile:\n"
        "  role: tester\n"
        "  goal: be tested\n"
        f"{persona_line}"
        "---\n"
    )
    path = parent_dir / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _load(parent_path: Path):
    raw = parse_skill_file(parent_path)["frontmatter"]
    return TypeAdapter(SkillManifest).validate_python(raw)


def test_returns_empty_when_agent_persona_resolves(tmp_path: Path) -> None:
    _write_persona_skill(tmp_path, name="reviewer")
    agent_path = _write_agent_skill(
        tmp_path, name="my_agent", adopted_persona="reviewer",
    )

    manifest = _load(agent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert issues == []
```

- [ ] **Step 2: Run — expect FAIL with NotImplementedError**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_persona_resolution.py::test_returns_empty_when_agent_persona_resolves -xvs`
Expected: FAILED.

- [ ] **Step 3: Implement the validator**

Replace `check_persona_resolution` body:

```python
from __future__ import annotations

from pathlib import Path

from ..compiler import CompileIssue
from ..exceptions import SkillLoadError
from ..manifest import AgentSkillDef, GraphSkillDef, LLMPhase
# Cross-module private import is intentional: keeping the walk-up
# resolver as a single source of truth between load-time and
# compile-time. See the PR #7 step-3 plan, "Scope decisions".
from ..loader import _resolve_persona


def check_persona_resolution(
    manifest: AgentSkillDef | GraphSkillDef,
    *,
    base_dir: Path,
) -> list[CompileIssue]:
    issues: list[CompileIssue] = []

    if isinstance(manifest, AgentSkillDef):
        if manifest.adopted_persona is not None:
            _check_one(
                manifest.adopted_persona,
                base_dir=base_dir,
                location="SKILL.md:adopted_persona",
                issues=issues,
            )
        return issues

    if isinstance(manifest, GraphSkillDef):
        for phase in manifest.phases:
            if not isinstance(phase, LLMPhase):
                continue
            if phase.adopted_persona is None:
                continue
            _check_one(
                phase.adopted_persona,
                base_dir=base_dir,
                location=f"SKILL.md:phases.{phase.name}.adopted_persona",
                issues=issues,
            )
    return issues


def _check_one(
    persona_name: str,
    *,
    base_dir: Path,
    location: str,
    issues: list[CompileIssue],
) -> None:
    try:
        _resolve_persona(persona_name, base_dir)
    except SkillLoadError as exc:
        issues.append(CompileIssue(
            rule_id="F-persona-not-resolved",
            severity="FATAL",
            location=location,
            message=str(exc),
        ))
```

- [ ] **Step 4: Run — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_persona_resolution.py::test_returns_empty_when_agent_persona_resolves -xvs`
Expected: PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/core/graph_agent/core/validators/persona_resolution.py tests/graph_agent/core/validators/test_persona_resolution.py
git commit -m "feat(validators): persona_resolution agent happy path with first passing test"
```

---

### Task 3: Test agent with persona name not found

**Files:**
- Modify: `tests/graph_agent/core/validators/test_persona_resolution.py`

- [ ] **Step 1: Add `test_fatal_when_agent_persona_not_found`**

```python
def test_fatal_when_agent_persona_not_found(tmp_path: Path) -> None:
    # No persona staged at tmp_path/subskills/missing/SKILL.md
    agent_path = _write_agent_skill(
        tmp_path, name="my_agent", adopted_persona="missing",
    )

    manifest = _load(agent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "F-persona-not-resolved"
    assert issue.severity == "FATAL"
    assert "missing" in issue.message
    assert issue.location == "SKILL.md:adopted_persona"
```

- [ ] **Step 2: Run — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_persona_resolution.py::test_fatal_when_agent_persona_not_found -xvs`
Expected: PASSED.

- [ ] **Step 3: Commit**

```bash
git add tests/graph_agent/core/validators/test_persona_resolution.py
git commit -m "test(validators): lock persona_resolution agent-not-found FATAL"
```

---

### Task 4: Test agent with persona name resolving to wrong type

**Files:**
- Modify: `tests/graph_agent/core/validators/test_persona_resolution.py`

- [ ] **Step 1: Add helper to write a graph skill in subskills/ + test**

```python
def _write_graph_subskill(parent_dir: Path, *, name: str) -> Path:
    """Stage a graph skill where a persona is expected — for the wrong-type FATAL test."""
    sub_dir = parent_dir / "subskills" / name
    sub_dir.mkdir(parents=True, exist_ok=True)
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        f"name: {name}\n"
        f"description: graph (not persona) named {name}\n"
        "io:\n  inputs: []\n  outputs: []\n"
        "phases:\n"
        "  - name: only\n"
        "    mode: logic\n"
        "    execute_steps:\n"
        "      - graph_agent.callbacks.events.SubgraphEnterEvent\n"
        "---\n"
    )
    path = sub_dir / "SKILL.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_fatal_when_agent_persona_resolves_to_wrong_type(tmp_path: Path) -> None:
    _write_graph_subskill(tmp_path, name="not_a_persona")
    agent_path = _write_agent_skill(
        tmp_path, name="my_agent", adopted_persona="not_a_persona",
    )

    manifest = _load(agent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-persona-not-resolved"
    assert "not_a_persona" in issues[0].message
    # Loader's wrong-type message includes 'PersonaSkillDef'.
    assert "PersonaSkillDef" in issues[0].message
```

- [ ] **Step 2: Run — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_persona_resolution.py::test_fatal_when_agent_persona_resolves_to_wrong_type -xvs`
Expected: PASSED.

- [ ] **Step 3: Commit**

```bash
git add tests/graph_agent/core/validators/test_persona_resolution.py
git commit -m "test(validators): lock persona_resolution wrong-type FATAL"
```

---

### Task 5: Test graph LLMPhase persona resolution (happy + sad)

**Files:**
- Modify: `tests/graph_agent/core/validators/test_persona_resolution.py`

- [ ] **Step 1: Add helper for graph parents with LLM phases + tests**

```python
def _write_graph_with_llm_phase(
    parent_dir: Path,
    *,
    name: str,
    phase_name: str,
    adopted_persona: str | None = None,
) -> Path:
    persona_line = (
        f"    adopted_persona: {adopted_persona}\n"
        if adopted_persona is not None else ""
    )
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        f"name: {name}\n"
        f"description: graph {name}\n"
        "io:\n  inputs: []\n  outputs: []\n"
        "phases:\n"
        f"  - name: {phase_name}\n"
        "    mode: llm\n"
        "    prompt: do the thing\n"
        f"{persona_line}"
        "---\n"
    )
    path = parent_dir / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_returns_empty_when_llm_phase_persona_resolves(tmp_path: Path) -> None:
    _write_persona_skill(tmp_path, name="reviewer")
    parent_path = _write_graph_with_llm_phase(
        tmp_path, name="parent", phase_name="review_step",
        adopted_persona="reviewer",
    )

    manifest = _load(parent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert issues == []


def test_fatal_when_llm_phase_persona_not_found(tmp_path: Path) -> None:
    parent_path = _write_graph_with_llm_phase(
        tmp_path, name="parent", phase_name="review_step",
        adopted_persona="missing_persona",
    )

    manifest = _load(parent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "F-persona-not-resolved"
    assert "missing_persona" in issue.message
    assert issue.location == "SKILL.md:phases.review_step.adopted_persona"
```

- [ ] **Step 2: Run both — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_persona_resolution.py -k "llm_phase" -v`
Expected: 2 PASSED.

- [ ] **Step 3: Commit**

```bash
git add tests/graph_agent/core/validators/test_persona_resolution.py
git commit -m "test(validators): persona_resolution covers LLMPhase.adopted_persona"
```

---

### Task 6: Test no-persona fast paths (agent and graph)

**Files:**
- Modify: `tests/graph_agent/core/validators/test_persona_resolution.py`

- [ ] **Step 1: Add tests**

```python
def test_returns_empty_when_agent_has_no_persona(tmp_path: Path) -> None:
    agent_path = _write_agent_skill(tmp_path, name="my_agent", adopted_persona=None)

    manifest = _load(agent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert issues == []


def test_returns_empty_when_graph_has_no_llm_persona(tmp_path: Path) -> None:
    parent_path = _write_graph_with_llm_phase(
        tmp_path, name="parent", phase_name="step", adopted_persona=None,
    )

    manifest = _load(parent_path)
    issues = check_persona_resolution(manifest, base_dir=tmp_path)

    assert issues == []
```

- [ ] **Step 2: Run — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_persona_resolution.py -k "no_persona or no_llm_persona" -v`
Expected: 2 PASSED.

- [ ] **Step 3: Commit**

```bash
git add tests/graph_agent/core/validators/test_persona_resolution.py
git commit -m "test(validators): persona_resolution fast paths when no adopted_persona"
```

---

### Task 7: Wire validator into compile_skill + integration test

**Files:**
- Create: `tests/graph_agent/core/test_compile_skill_persona_resolution_integration.py`
- Modify: `src/core/graph_agent/core/compiler.py`

- [ ] **Step 1: Write integration test**

```python
"""End-to-end: compile_skill on an agent with a missing adopted_persona surfaces F-persona-not-resolved."""
from __future__ import annotations

from pathlib import Path

from graph_agent.core.compiler import compile_skill


def test_compile_skill_propagates_persona_not_resolved(tmp_path: Path) -> None:
    agent_path = tmp_path / "my_agent.md"
    agent_path.write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "type: agent\n"
        "name: my_agent\n"
        "description: agent for persona resolution integration\n"
        "agent_profile:\n"
        "  role: tester\n"
        "  goal: be tested\n"
        "adopted_persona: nonexistent_persona\n"
        "---\n",
        encoding="utf-8",
    )

    result = compile_skill(agent_path)

    rule_ids = sorted(i.rule_id for i in result.fatals)
    assert "F-persona-not-resolved" in rule_ids
    assert result.passed is False
```

- [ ] **Step 2: Run — expect FAIL**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/test_compile_skill_persona_resolution_integration.py -xvs`
Expected: FAIL — F-persona-not-resolved not in fatals.

- [ ] **Step 3: Wire validator into compile_skill**

In `src/core/graph_agent/core/compiler.py`, replace the existing PR #7 block:

```python
    if isinstance(manifest, GraphSkillDef):
        from .validators.context_bridge import check_context_bridge
        from .validators.subgraph_cycle import check_subgraph_cycles

        result.issues.extend(
            check_context_bridge(manifest, base_dir=skill_path.parent)
        )
        result.issues.extend(
            check_subgraph_cycles(manifest, skill_path=skill_path)
        )
```

with:

```python
    # PR #7 semantic checks (run only when Pydantic validation succeeds).
    from .manifest import AgentSkillDef
    from .validators.persona_resolution import check_persona_resolution

    if isinstance(manifest, GraphSkillDef):
        from .validators.context_bridge import check_context_bridge
        from .validators.subgraph_cycle import check_subgraph_cycles

        result.issues.extend(
            check_context_bridge(manifest, base_dir=skill_path.parent)
        )
        result.issues.extend(
            check_subgraph_cycles(manifest, skill_path=skill_path)
        )
        result.issues.extend(
            check_persona_resolution(manifest, base_dir=skill_path.parent)
        )
    elif isinstance(manifest, AgentSkillDef):
        result.issues.extend(
            check_persona_resolution(manifest, base_dir=skill_path.parent)
        )
```

(Persona skills don't carry `adopted_persona` themselves, so `PersonaSkillDef` skips both branches.)

- [ ] **Step 4: Update compiler.py docstring TODO list**

In the module docstring, replace the persona-resolution bullet:

```python
- **Persona resolution** ✅ shipped in PR #7 step 3.
  See ``validators/persona_resolution.py``. Reuses ``loader._resolve_persona``
  so compile-time and load-time agree on the search order.
```

- [ ] **Step 5: Run integration + full validator suite**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/test_compile_skill_persona_resolution_integration.py tests/graph_agent/core/validators/ -v`
Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/core/graph_agent/core/compiler.py tests/graph_agent/core/test_compile_skill_persona_resolution_integration.py
git commit -m "feat(compiler): run persona_resolution validator for agent + graph manifests"
```

---

### Task 8: Full pytest regression

- [ ] **Step 1: Run the full test suite**

Run: `source .venv/bin/activate && pytest tests/ --ignore=tests/llm_client_manager -q`
Expected: 382 baseline + 7 new tests (Tasks 2-7) = **389 passed**. Zero regressions.

- [ ] **Step 2: No commit (verification only).**

---

### Task 9: Send code review to Codex

- [ ] **Step 1: Narrow-focus prompt to Codex listing the new commits + 3 yes/no questions**

```bash
command ccb ask --wait --timeout 600 a1 <<'EOF'
请用中文回答。这是 PR #7 step 3 (persona_resolution validator) 的 [CODE REVIEW]。

新 commit (git log --oneline origin/feat/studio-phase0-manifest..HEAD 可看)。关键文件:
  - src/core/graph_agent/core/validators/persona_resolution.py (新建)
  - src/core/graph_agent/core/compiler.py (新增 8 行 wire + docstring)
  - tests/graph_agent/core/validators/test_persona_resolution.py (新建,7 unit)
  - tests/graph_agent/core/test_compile_skill_persona_resolution_integration.py (新建,1 integration)

请回答 3 题 YES/NO + ≤3 行理由:

1) **跨模块私有 import**: 直接 import loader._resolve_persona (underscore-prefixed) 在 validator 里使用,理由是单一 source of truth 避免 walk-up 逻辑两份。这种依赖可接受吗?还是必须先在 loader 里 promote 成 public?

2) **rule_id 单一性**: 一个 F-persona-not-resolved 同时覆盖 (a) 名字找不到 (b) 解析到错类型(graph/agent),通过把 loader 的 SkillLoadError 消息原样转给 PM。这个粒度合理还是要分 2 个 rule_id?

3) **集成边界**: PersonaSkillDef 的 manifest 既不进 isinstance(manifest, GraphSkillDef) 也不进 isinstance(manifest, AgentSkillDef) 分支,自然跳过 (persona 本身不能 adopted_persona 别人)。这个跳过对吗?

YES/NO + ≤3 行理由,不要 rubric 不要打分。
EOF
```

- [ ] **Step 2: Address must-fix; no commit unless one surfaces.**

---

## Self-Review

- **Spec coverage**: persona resolution ✅ Tasks 1-7. Tool-path / rules.yaml ❌ separate.
- **Placeholder scan**: clean.
- **Type consistency**: `check_persona_resolution(manifest, *, base_dir)` consistent across stub, impl, wiring. Single rule_id `F-persona-not-resolved`.
- **Test count math**: baseline 382 + 7 new (Tasks 2 happy + 3 not-found + 4 wrong-type + 5×2 LLM happy/sad + 6×2 no-persona fastpaths + 7 integration) = **389 expected** at Task 8.

---

## Pre-Execution Checkpoints

1. **Codex plan review** — narrow yes/no questions about the 3 scope decisions above.
2. **Skip Gemini** (per memory `project_gemini_unreliable_2026-04-25.md`).
3. **Confirm `.venv/` is active**.
