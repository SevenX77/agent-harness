# PR #7 Step 2 — Subgraph Cycle Detection Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a static semantic validator that, at compile time, detects cycles in `DelegatePhase.subgraph` references and surfaces each cycle as a `CompileIssue` FATAL from `compile_skill()`. This is the second of the four PR #7 semantic checks listed in `core/compiler.py`'s module docstring (the first, `context_bridge`, shipped in step 1 — commits `7ec354f` … `bf5f2ba`).

**Architecture:** A new sibling module `core/validators/subgraph_cycle.py` exports `check_subgraph_cycles(parent: GraphSkillDef, *, skill_path: Path) -> list[CompileIssue]`. The validator does a depth-first walk over `DelegatePhase.subgraph` references, carrying a path stack of resolved SKILL.md paths it is currently walking. A revisit of any path in the stack is a cycle: emit `F-subgraph-cycle` with the chain in the message. `compile_skill()` invokes it after `check_context_bridge` for `GraphSkillDef` manifests; the two validators are independent and emit their own issues without sharing state. If a child SKILL.md is missing, unparseable, or not a `GraphSkillDef`, this validator **silently skips** (the missing/invalid case is already reported by `check_context_bridge`; agent/persona children carry no `phases` so cannot participate in a cycle).

**Tech Stack:** Python 3.11+, Pydantic v2 `TypeAdapter`, existing `core/parser.py::parse_skill_file`, existing `CompileIssue` dataclass.

---

## Why this validator exists (read first)

`loader.py:278-283` already has a runtime cycle guard via the `_loading_stack` set:

```python
loading_stack = _loading_stack or set()
if md_resolved in loading_stack:
    chain = " -> ".join([*sorted(loading_stack), md_resolved])
    raise SkillLoadError(f"Cyclic skill reference detected: {chain}")
```

The runtime guard catches cycles only at actual load time and surfaces them as a generic `SkillLoadError`. Lifting the check to compile time means:

1. Studio "save validate" runs without paying for full skill loading.
2. CI catches cyclic graph designs without instantiating any harness.
3. The error becomes a structured `CompileIssue` (rule_id `F-subgraph-cycle`) instead of a generic exception.

---

## Scope decisions made up front (so reviewers can challenge them in plan review)

- **Independent validator, no shared helper with `context_bridge`** — both validators open + parse child SKILL.md files. Tempting to extract a shared loader helper. **Rejected** for this PR: extracting it would require touching the already-reviewed `context_bridge.py` (which user has just merged into PR #5) and bundling a refactor inside step 2's commits muddles review boundaries. If a third validator (step 3 = persona resolution) needs the same loader, *that* PR can extract the helper as its first task and refactor both prior validators. YAGNI for now.
- **Silent skip on unparseable / missing / non-graph children** — missing/invalid children already produce `F-context-bridge-child-missing` / `F-context-bridge-child-invalid` from step 1. Re-emitting them under a different rule_id wastes PM attention. Agent / persona children have no `phases` so cannot participate in a cycle; nothing to report.
- **Path identity = `Path.resolve()` result** — same as `subgraph.py:54`. Symlinks are resolved before comparison so two symlinks to the same file count as the same node.
- **One `F-subgraph-cycle` per detected cycle, not per phase that points into it** — if the same parent has two phases both pointing into the same cyclic loop, we still emit a single issue. Implementation: when a cycle is detected on a child path, mark that child path "cycle-reported" and skip subsequent re-detections from sibling phases. This keeps the diagnostic terse.

---

## File Structure

| Path | Responsibility | New / Modified |
|---|---|---|
| `src/core/graph_agent/core/validators/subgraph_cycle.py` | Public `check_subgraph_cycles(parent, *, skill_path) -> list[CompileIssue]`. Internal `_walk` does DFS with a path stack. | Create |
| `src/core/graph_agent/core/compiler.py` | Wire `check_subgraph_cycles` into `compile_skill` after `check_context_bridge`, both inside the `isinstance(manifest, GraphSkillDef)` block. Update the TODO(PR#7) docstring to mark cycle detection as shipped. | Modify (`compile_skill` body around the existing `check_context_bridge` call site; module docstring's PR#7 TODO list) |
| `tests/graph_agent/core/validators/test_subgraph_cycle.py` | Unit tests for every emitted-issue and skipped path. Uses `tmp_path` fixtures with the same column-0 YAML helpers as `test_context_bridge.py`. | Create |
| `tests/graph_agent/core/test_compile_skill_subgraph_cycle_integration.py` | End-to-end integration: a parent + cyclic chain of children, asserting `compile_skill().fatals` contains `F-subgraph-cycle`. | Create |

The `_write_child_graph` helper from `test_context_bridge.py` is duplicated in `test_subgraph_cycle.py` rather than imported. Reason: tests in this codebase do not depend on each other across files; copy-paste of a tiny fixture-builder is cheaper than introducing a tests-only utility module that future contributors have to discover.

---

## Issue catalogue

| rule_id | severity | trigger | location format |
|---|---|---|---|
| `F-subgraph-cycle` | FATAL | DFS revisits a SKILL.md path that is already in the current walk stack. The cycle chain is included in the message. | `SKILL.md:phases.<phase_name>.subgraph` (the phase whose subgraph closed the loop) |

One rule_id; cycles are the only thing this validator decides on. Path-missing / parse-failure / non-graph-child cases are all silent skips (step 1 owns them).

---

## Public API contract (lock this before coding)

```python
# src/core/graph_agent/core/validators/subgraph_cycle.py

from pathlib import Path
from ..compiler import CompileIssue
from ..manifest import GraphSkillDef

def check_subgraph_cycles(
    parent: GraphSkillDef,
    *,
    skill_path: Path,
) -> list[CompileIssue]:
    """DFS-walk DelegatePhase.subgraph references and emit F-subgraph-cycle.

    `skill_path` is the absolute path of `parent`'s SKILL.md — it seeds the
    walk stack so a self-cycle (`subgraph: ./SKILL.md`) is detected. The
    base directory for resolving `phase.subgraph` strings is derived as
    `skill_path.parent` recursively for each child. Returns an empty list
    on no cycles. Does not raise.
    """
```

Why `skill_path` (not `base_dir`): the validator needs the parent's identity in the stack to detect self-cycles, so it needs the file path, not just the directory.

---

## Tasks

### Task 1: Create the validator stub

**Files:**
- Create: `src/core/graph_agent/core/validators/subgraph_cycle.py`

- [ ] **Step 1: Write the stub with docstring + signature + NotImplementedError**

```python
# src/core/graph_agent/core/validators/subgraph_cycle.py
"""Static semantic validator: DelegatePhase.subgraph cycle detection.

See docs/superpowers/plans/2026-04-25-pr7-subgraph-cycle-validator.md for
the full rule catalogue and rationale.
"""
from __future__ import annotations

from pathlib import Path

from ..compiler import CompileIssue
from ..manifest import GraphSkillDef


def check_subgraph_cycles(
    parent: GraphSkillDef,
    *,
    skill_path: Path,
) -> list[CompileIssue]:
    """DFS-walk subgraph references and emit F-subgraph-cycle on revisits."""
    raise NotImplementedError("filled in by Task 2 onward")
```

- [ ] **Step 2: Confirm test collection still works**

Run: `source .venv/bin/activate && pytest --collect-only tests/graph_agent/core/ 2>&1 | tail -3`
Expected: collection completes without ImportError.

- [ ] **Step 3: Commit**

```bash
git add src/core/graph_agent/core/validators/subgraph_cycle.py
git commit -m "feat(validators): scaffold subgraph_cycle stub"
```

---

### Task 2: Test happy path — single subgraph link, no cycle

**Files:**
- Create: `tests/graph_agent/core/validators/test_subgraph_cycle.py`

- [ ] **Step 1: Write `test_returns_empty_when_no_cycle` + the column-0 child-graph helper (copy from test_context_bridge.py — see "File Structure" rationale)**

```python
"""Unit tests for the subgraph_cycle validator."""
from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

from graph_agent.core.manifest import GraphSkillDef, SkillManifest
from graph_agent.core.validators.subgraph_cycle import (
    check_subgraph_cycles,
)


def _write_graph_skill(
    tmp_path: Path,
    *,
    name: str,
    subgraphs: list[tuple[str, str]] | None = None,
) -> Path:
    """Stage a minimal valid GraphSkillDef SKILL.md.

    `subgraphs` is a list of (phase_name, subgraph_path_string) tuples. Each
    becomes a DelegatePhase wired up with a no-op context_bridge so the parent
    parses cleanly.
    """
    delegate_phases = ""
    for phase_name, subgraph_path in subgraphs or []:
        delegate_phases += (
            f"  - name: {phase_name}\n"
            f"    mode: delegate\n"
            f"    subgraph: {subgraph_path}\n"
            f"    context_bridge:\n"
            f"      inputs: {{}}\n"
            f"      outputs: {{}}\n"
        )
    if not delegate_phases:
        # All-graph-skills must have at least one phase; add a no-op logic phase.
        delegate_phases = (
            "  - name: only_phase\n"
            "    mode: logic\n"
            "    execute_steps:\n"
            "      - graph_agent.callbacks.events.SubgraphEnterEvent\n"
        )
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        f"name: {name}\n"
        f"description: graph skill {name} for subgraph_cycle tests\n"
        "io:\n"
        "  inputs: []\n"
        "  outputs: []\n"
        "phases:\n"
        f"{delegate_phases}"
        "---\n"
    )
    path = tmp_path / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _load_parent(parent_path: Path) -> GraphSkillDef:
    from graph_agent.core.parser import parse_skill_file
    raw = parse_skill_file(parent_path)["frontmatter"]
    return TypeAdapter(SkillManifest).validate_python(raw)


def test_returns_empty_when_no_cycle(tmp_path: Path) -> None:
    leaf = _write_graph_skill(tmp_path, name="leaf")
    middle = _write_graph_skill(
        tmp_path, name="middle", subgraphs=[("p", "leaf.md")],
    )
    parent_path = _write_graph_skill(
        tmp_path, name="parent", subgraphs=[("p", "middle.md")],
    )

    parent = _load_parent(parent_path)
    issues = check_subgraph_cycles(parent, skill_path=parent_path)

    assert issues == []
```

- [ ] **Step 2: Run — expect FAIL with NotImplementedError**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_subgraph_cycle.py::test_returns_empty_when_no_cycle -xvs`
Expected: FAILED with NotImplementedError from the stub.

- [ ] **Step 3: Implement the DFS walk**

Replace `check_subgraph_cycles` body in `src/core/graph_agent/core/validators/subgraph_cycle.py`:

```python
from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from ..compiler import CompileIssue
from ..exceptions import SkillLoadError
from ..manifest import (
    DelegatePhase,
    GraphSkillDef,
    SkillManifest,
)
from ..parser import parse_skill_file


def check_subgraph_cycles(
    parent: GraphSkillDef,
    *,
    skill_path: Path,
) -> list[CompileIssue]:
    issues: list[CompileIssue] = []
    parent_resolved = skill_path.resolve()
    _walk(
        skill_def=parent,
        skill_path=parent_resolved,
        path_stack=[parent_resolved],
        cycle_reported=set(),
        issues=issues,
    )
    return issues


def _walk(
    *,
    skill_def: GraphSkillDef,
    skill_path: Path,
    path_stack: list[Path],
    cycle_reported: set[Path],
    issues: list[CompileIssue],
) -> None:
    base_dir = skill_path.parent
    for phase in skill_def.phases:
        if not isinstance(phase, DelegatePhase):
            continue
        child_resolved = (base_dir / phase.subgraph).resolve()
        if child_resolved in path_stack:
            if child_resolved in cycle_reported:
                continue
            cycle_reported.add(child_resolved)
            cycle_start = path_stack.index(child_resolved)
            chain = [*path_stack[cycle_start:], child_resolved]
            chain_str = " -> ".join(str(p) for p in chain)
            issues.append(CompileIssue(
                rule_id="F-subgraph-cycle",
                severity="FATAL",
                location=f"SKILL.md:phases.{phase.name}.subgraph",
                message=(
                    f"Cyclic subgraph reference detected from phase "
                    f"'{phase.name}': {chain_str}"
                ),
            ))
            continue
        if not child_resolved.is_file():
            continue  # context_bridge validator owns child-missing
        try:
            child_raw = parse_skill_file(child_resolved)["frontmatter"]
            child_manifest = TypeAdapter(SkillManifest).validate_python(child_raw)
        except (SkillLoadError, ValidationError):
            continue  # context_bridge validator owns child-invalid
        if not isinstance(child_manifest, GraphSkillDef):
            continue  # agent / persona have no phases — no cycle possible
        _walk(
            skill_def=child_manifest,
            skill_path=child_resolved,
            path_stack=[*path_stack, child_resolved],
            cycle_reported=cycle_reported,
            issues=issues,
        )
```

- [ ] **Step 4: Run — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_subgraph_cycle.py::test_returns_empty_when_no_cycle -xvs`
Expected: PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/core/graph_agent/core/validators/subgraph_cycle.py tests/graph_agent/core/validators/test_subgraph_cycle.py
git commit -m "feat(validators): subgraph_cycle DFS happy path with first passing test"
```

---

### Task 3: Test direct self-cycle (parent → parent)

**Files:**
- Modify: `tests/graph_agent/core/validators/test_subgraph_cycle.py`

- [ ] **Step 1: Add `test_fatal_when_self_cycle`**

```python
def test_fatal_when_self_cycle(tmp_path: Path) -> None:
    parent_path = _write_graph_skill(
        tmp_path, name="parent", subgraphs=[("self_loop", "parent.md")],
    )

    parent = _load_parent(parent_path)
    issues = check_subgraph_cycles(parent, skill_path=parent_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-subgraph-cycle"
    assert issues[0].severity == "FATAL"
    assert "parent.md" in issues[0].message
    assert issues[0].location.endswith("phases.self_loop.subgraph")
```

- [ ] **Step 2: Run — expect PASS (Task 2's implementation handles self-cycles via parent_resolved seeding)**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_subgraph_cycle.py::test_fatal_when_self_cycle -xvs`
Expected: PASSED.

- [ ] **Step 3: Commit**

```bash
git add tests/graph_agent/core/validators/test_subgraph_cycle.py
git commit -m "test(validators): lock subgraph_cycle self-cycle FATAL"
```

---

### Task 4: Test indirect cycle (A → B → A)

**Files:**
- Modify: `tests/graph_agent/core/validators/test_subgraph_cycle.py`

- [ ] **Step 1: Add `test_fatal_when_indirect_cycle`**

```python
def test_fatal_when_indirect_cycle(tmp_path: Path) -> None:
    # Two skills referencing each other.
    a_path = tmp_path / "a.md"
    b_path = tmp_path / "b.md"
    a_path.write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        "name: a\n"
        "description: a\n"
        "io:\n  inputs: []\n  outputs: []\n"
        "phases:\n"
        "  - name: to_b\n"
        "    mode: delegate\n"
        "    subgraph: b.md\n"
        "    context_bridge:\n"
        "      inputs: {}\n"
        "      outputs: {}\n"
        "---\n",
        encoding="utf-8",
    )
    b_path.write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        "name: b\n"
        "description: b\n"
        "io:\n  inputs: []\n  outputs: []\n"
        "phases:\n"
        "  - name: to_a\n"
        "    mode: delegate\n"
        "    subgraph: a.md\n"
        "    context_bridge:\n"
        "      inputs: {}\n"
        "      outputs: {}\n"
        "---\n",
        encoding="utf-8",
    )

    parent = _load_parent(a_path)
    issues = check_subgraph_cycles(parent, skill_path=a_path)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-subgraph-cycle"
    # Chain should mention both files.
    assert "a.md" in issues[0].message
    assert "b.md" in issues[0].message
    # Issue is attributed to the phase that closed the loop, not the entry phase.
    assert issues[0].location.endswith("phases.to_a.subgraph")
```

- [ ] **Step 2: Run — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_subgraph_cycle.py::test_fatal_when_indirect_cycle -xvs`
Expected: PASSED.

- [ ] **Step 3: Commit**

```bash
git add tests/graph_agent/core/validators/test_subgraph_cycle.py
git commit -m "test(validators): lock subgraph_cycle indirect-cycle FATAL"
```

---

### Task 5: Test that missing / invalid / agent / persona children silently skip

**Files:**
- Modify: `tests/graph_agent/core/validators/test_subgraph_cycle.py`

- [ ] **Step 1: Add `test_silently_skips_missing_child`**

```python
def test_silently_skips_missing_child(tmp_path: Path) -> None:
    parent_path = _write_graph_skill(
        tmp_path,
        name="parent",
        subgraphs=[("dead_link", "nonexistent.md")],
    )

    parent = _load_parent(parent_path)
    issues = check_subgraph_cycles(parent, skill_path=parent_path)

    # Missing child is context_bridge's concern, not cycle validator's.
    assert issues == []
```

- [ ] **Step 2: Add `test_silently_skips_agent_child`**

```python
def test_silently_skips_agent_child(tmp_path: Path) -> None:
    agent_path = tmp_path / "agent.md"
    agent_path.write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "type: agent\n"
        "name: agent_child\n"
        "description: child agent\n"
        "agent_profile:\n"
        "  role: tester\n"
        "  goal: be tested\n"
        "---\n",
        encoding="utf-8",
    )
    parent_path = _write_graph_skill(
        tmp_path, name="parent", subgraphs=[("p", "agent.md")],
    )

    parent = _load_parent(parent_path)
    issues = check_subgraph_cycles(parent, skill_path=parent_path)

    assert issues == []  # agent has no phases, cannot participate in a cycle
```

- [ ] **Step 3: Run both — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_subgraph_cycle.py -k "silently_skips" -xvs`
Expected: 2 PASSED.

- [ ] **Step 4: Commit**

```bash
git add tests/graph_agent/core/validators/test_subgraph_cycle.py
git commit -m "test(validators): subgraph_cycle silently skips non-participating children"
```

---

### Task 6: Test that the same cycle reached via two parent phases is reported once

**Files:**
- Modify: `tests/graph_agent/core/validators/test_subgraph_cycle.py`

- [ ] **Step 1: Add `test_cycle_reported_once_for_two_parent_phases`**

```python
def test_cycle_reported_once_for_two_parent_phases(tmp_path: Path) -> None:
    # Two phases on the parent both delegate to the same self-cycling child.
    parent_path = _write_graph_skill(
        tmp_path,
        name="parent",
        subgraphs=[
            ("p1", "parent.md"),
            ("p2", "parent.md"),
        ],
    )

    parent = _load_parent(parent_path)
    issues = check_subgraph_cycles(parent, skill_path=parent_path)

    # Both phases close the same loop; the cycle_reported set deduplicates.
    assert len(issues) == 1
    # The first phase to close the loop wins attribution.
    assert issues[0].location.endswith("phases.p1.subgraph")
```

- [ ] **Step 2: Run — expect PASS**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/validators/test_subgraph_cycle.py::test_cycle_reported_once_for_two_parent_phases -xvs`
Expected: PASSED.

- [ ] **Step 3: Commit**

```bash
git add tests/graph_agent/core/validators/test_subgraph_cycle.py
git commit -m "test(validators): subgraph_cycle dedupes per resolved child path"
```

---

### Task 7: Wire validator into compile_skill + integration test

**Files:**
- Create: `tests/graph_agent/core/test_compile_skill_subgraph_cycle_integration.py`
- Modify: `src/core/graph_agent/core/compiler.py`

- [ ] **Step 1: Write the integration test**

```python
"""End-to-end: compile_skill on a self-cycling parent surfaces F-subgraph-cycle."""
from __future__ import annotations

from pathlib import Path

from graph_agent.core.compiler import compile_skill


def test_compile_skill_propagates_subgraph_cycle(tmp_path: Path) -> None:
    parent = tmp_path / "parent.md"
    parent.write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        "name: parent\n"
        "description: parent for cycle integration test\n"
        "io:\n  inputs: []\n  outputs: []\n"
        "phases:\n"
        "  - name: self_loop\n"
        "    mode: delegate\n"
        "    subgraph: parent.md\n"
        "    context_bridge:\n"
        "      inputs: {}\n"
        "      outputs: {}\n"
        "---\n",
        encoding="utf-8",
    )

    result = compile_skill(parent)

    rule_ids = sorted(i.rule_id for i in result.fatals)
    assert "F-subgraph-cycle" in rule_ids
    assert result.passed is False
```

- [ ] **Step 2: Run — expect FAIL (validator not yet wired)**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/test_compile_skill_subgraph_cycle_integration.py -xvs`
Expected: AssertionError — `F-subgraph-cycle` not in fatals.

- [ ] **Step 3: Wire `check_subgraph_cycles` into `compile_skill`**

In `src/core/graph_agent/core/compiler.py`, find the existing `check_context_bridge` call site and add the cycle validator beside it:

```python
    # PR #7 semantic checks (run only when Pydantic validation succeeds).
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

- [ ] **Step 4: Update the compiler.py docstring TODO list**

In the module docstring's `TODO(PR#7)` block, replace the subgraph cycle bullet:

```python
- **Subgraph cycle detection** ✅ shipped in PR #7 step 2.
  See ``validators/subgraph_cycle.py``. Independent of step 1 — both
  validators run unconditionally for ``GraphSkillDef`` manifests.
```

- [ ] **Step 5: Run integration + full validator suite**

Run: `source .venv/bin/activate && pytest tests/graph_agent/core/test_compile_skill_subgraph_cycle_integration.py tests/graph_agent/core/validators/ -v`
Expected: all PASSED. The cycle integration plus the 5 cycle unit tests + the 11 context_bridge unit tests + the 1 context_bridge integration = 18 passed.

- [ ] **Step 6: Commit**

```bash
git add src/core/graph_agent/core/compiler.py tests/graph_agent/core/test_compile_skill_subgraph_cycle_integration.py
git commit -m "feat(compiler): run subgraph_cycle validator after context_bridge"
```

---

### Task 8: Full pytest regression

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `source .venv/bin/activate && pytest tests/ --ignore=tests/llm_client_manager -q`
Expected: total = previous baseline (374 after step 1) + 5 new cycle unit tests + 1 new cycle integration = **380 passed**. Zero regressions.

- [ ] **Step 2: No commit (verification only).**

---

### Task 9: Send git diff to Codex for code review

**Files:** none (review handoff)

- [ ] **Step 1: List the new commits**

Run: `git log --oneline origin/feat/studio-phase0-manifest..HEAD`
Expected: 7-ish commits from Tasks 1-7 (one per task that commits).

- [ ] **Step 2: Send a narrow-focus review prompt to Codex**

```bash
command ccb ask --wait --timeout 600 a1 <<'EOF'
请用中文回答。这是 PR #7 step 2 (subgraph cycle detection validator) 的 [CODE REVIEW],3 道窄焦点 YES/NO + ≤3 行理由。

代码 commit:
  - <T1 sha> scaffold
  - <T2 sha> DFS happy path + impl
  - <T3 sha> self-cycle test
  - <T4 sha> indirect cycle test
  - <T5 sha> silent skip tests
  - <T6 sha> dedup test
  - <T7 sha> wire into compile_skill + integration

可 git show 看每个 commit。关键文件:
  - src/core/graph_agent/core/validators/subgraph_cycle.py (新建)
  - src/core/graph_agent/core/compiler.py (新增 3 行)
  - tests/graph_agent/core/validators/test_subgraph_cycle.py (新建,5 unit test)
  - tests/graph_agent/core/test_compile_skill_subgraph_cycle_integration.py (新建,1 integration)

请回答:

1) **DFS 正确性**: path_stack + cycle_reported set 保证 (a) 自循环检测, (b) 间接循环检测, (c) 同 child 多入口去重, (d) 不漏报。这 4 点都成立吗?有没有漏的 case?

2) **silent skip 边界**: 缺失 / 解析失败 / agent / persona child 全部 silent skip,理由是 step 1 已报或不可能成环。这个分工合理吗?有没有用户体验问题(比如 cycle 跨过一个 invalid child 时整条 cycle 被漏报)?

3) **集成顺序**: compile_skill 里 context_bridge 先调,subgraph_cycle 后调,两者无依赖。这个顺序对吗?有没有需要前后顺序的子分支?

YES/NO + ≤3 行理由,不要 rubric 不要打分。
EOF
```

- [ ] **Step 3: Address must-fix from Codex**

Same protocol as step 1 Task 13: only apply Codex's true must-fix; document non-issue rebuttals in the eventual PR description.

- [ ] **Step 4: No commit (review-only task).**

---

## Self-Review

**1. Spec coverage** — every PR #7 step-2 deliverable from `core/compiler.py`'s docstring is covered:
   - Subgraph cycle detection ✅ (Tasks 1-7)
   - Tool-path resolvability ❌ (separate PR #7 step)
   - Persona resolution ❌ (separate)
   - Custom rules.yaml decision ❌ (separate)
   - context_bridge ✅ shipped in step 1

**2. Placeholder scan** — all code blocks are literal source. The Codex prompt template in Task 9 has `<T1 sha>` etc. that get filled in at execution time after the actual commits land.

**3. Type consistency** — `check_subgraph_cycles(parent: GraphSkillDef, *, skill_path: Path) -> list[CompileIssue]` is the only public signature; appears identically in Task 1 stub, Task 2 implementation, and Task 7 wiring. The single rule_id `F-subgraph-cycle` is consistent across implementation and all assertions.

**4. Independence from step 1** — step 2 does not modify `validators/context_bridge.py`. All shared concerns (parsing failures, missing files) are owned by step 1; step 2 silently skips. If a future PR extracts a shared loader helper, both validators can adopt it then.

**5. Test count math** — baseline 374 (after step 1); +5 unit tests (Tasks 2-6) + 1 integration (Task 7) = **380 expected** at Task 8.

---

## Pre-Execution Checkpoints

1. **Plan-only review by Codex** — narrow prompt: "is the rule catalogue + skip-policy complete? Any cycle case I'm missing?" Async OK; this is *separate* from Task 9's code review.
2. **Skip Gemini plan review** — see memory `project_gemini_unreliable_2026-04-25.md`. Gemini is best-effort right now; Codex is the gating reviewer.
3. **Confirm `.venv/` is active** — `which pytest` should print `/home/sevenx/coding/agent-harness/.venv/bin/pytest`.

After Codex approves the plan, proceed to Task 1.
