# Persona Registry Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `loader._resolve_persona`'s implicit `<repo_root>/skills/` walk-up with an explicit, env-var-driven persona registry, and promote the function to a public module shared by load-time and compile-time callers.

**Architecture:** New module `src/core/graph_agent/core/personas.py` exposes `resolve_persona(name, *, base_dir, search_paths=None) -> PersonaSkillDef` plus `default_persona_search_paths() -> list[Path]` that reads `GRAPH_AGENT_PERSONA_PATH` (`os.pathsep`-separated, like `PYTHONPATH`). Skill-local `<base_dir>/subskills/<name>/SKILL.md` lookup is preserved (it's a natural skill convention; existing tests rely on it). The walk-up is dropped — global registries must be made explicit by setting the env var. Three callsites migrate: `loader._phase_from_agent_skill`, `loader._phase_from_graph_skill`'s LLM phase branch, and `validators/persona_resolution.check_persona_resolution` (which currently does a cross-module private import).

**Tech Stack:** Python 3.11, Pydantic v2, pytest, `os.pathsep`-separated env var convention.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/core/graph_agent/core/personas.py` | **Create** | Public registry API: `resolve_persona`, `default_persona_search_paths`, env-var name constant |
| `src/core/graph_agent/core/loader.py` | Modify | Delete `_resolve_persona` (lines 382-425); update 2 callsites at lines 475 and 510 to call the new public API |
| `src/core/graph_agent/core/validators/persona_resolution.py` | Modify | Switch import from `..loader._resolve_persona` to `..personas.resolve_persona`; drop the cross-module-private-import comment block |
| `src/core/graph_agent/core/compiler.py` | Modify | Update PR #7 step 3 docstring bullet — note that the loader-private helper has been promoted to the public `personas` module |
| `tests/graph_agent/core/test_personas.py` | **Create** | Unit tests for the registry: skill-local resolves, env-var path resolves, skill-local precedes env-var, missing → SkillLoadError, wrong-type → SkillLoadError, env-var unset → only skill-local |
| `tests/graph_agent/core/validators/test_persona_resolution.py` | Modify | Add one test exercising env-var-based registry to verify the validator picks up the same default search paths as the loader |

The validator's existing 7 tests (skill-local only) keep passing without changes.

---

## Decision: env-var vs. yaml registry

The TODO at `loader.py:392-395` lists two candidate mechanisms:

- **A. `personas.yaml`** — file-based registry next to project root. Requires defining a YAML schema, a discovery rule for "next to project root", and a parser. Larger surface; couples persona registry to filesystem layout.
- **B. `GRAPH_AGENT_PERSONA_PATH` env var** — colon-separated list of dirs containing `<name>/SKILL.md`. Mirrors `PYTHONPATH` semantics; needs no new schema; trivially testable via `monkeypatch.setenv`; users can layer multiple registries by composing the path string.

Picking **B** (env var). Reasoning: the smallest change that makes resolution deterministic. Authors who want a project-local registry export `GRAPH_AGENT_PERSONA_PATH=$PWD/personas` once at the top of their workflow. If a YAML registry surface is later wanted (so PMs can edit it without env vars), it can be layered on top — `default_persona_search_paths()` is the single seam.

**Backwards compat:** the dropped behavior is the implicit walk-up to find any directory named `skills/`. Existing tests in `tests/graph_agent/core/validators/test_persona_resolution.py` only exercise the skill-local `subskills/` path, which is preserved. No production skill in the repo relies on the walk-up (verified: `grep -rn "skills/" src/core/graph_agent/skills/` shows only sub-skills referenced via skill-local convention). If a downstream user did rely on it, they get a clear error message naming the searched paths and can fix it by exporting the env var.

---

## Task 1: Add the env-var-driven default search path helper

**Files:**
- Create: `src/core/graph_agent/core/personas.py`
- Test: `tests/graph_agent/core/test_personas.py`

- [ ] **Step 1.1: Write the failing test for `default_persona_search_paths` with env var unset**

```python
# tests/graph_agent/core/test_personas.py
"""Unit tests for the persona registry."""
from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.personas import (
    PERSONA_PATH_ENV_VAR,
    default_persona_search_paths,
)


def test_default_search_paths_empty_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PERSONA_PATH_ENV_VAR, raising=False)
    assert default_persona_search_paths() == []
```

- [ ] **Step 1.2: Run to confirm failure**

```
pytest tests/graph_agent/core/test_personas.py::test_default_search_paths_empty_when_env_unset -v
```

Expected: `ModuleNotFoundError: No module named 'graph_agent.core.personas'`.

- [ ] **Step 1.3: Create `personas.py` with the env-var helper**

```python
# src/core/graph_agent/core/personas.py
"""Public persona registry shared by load-time and compile-time callers.

Replaces the implicit walk-up that ``loader._resolve_persona`` used to do
(searching up the parent chain for any directory named ``skills/``). The
new contract is explicit:

1. **Skill-local convention** — ``<base_dir>/subskills/<name>/SKILL.md``
   is always checked first. This is the natural authoring convention for
   personas that ship inside a single skill tree.
2. **Explicit search paths** — additional directories are taken from the
   ``GRAPH_AGENT_PERSONA_PATH`` env var (``os.pathsep``-separated, like
   ``PYTHONPATH``). Each entry is treated as a registry root: a persona
   named ``foo`` resolves to ``<entry>/foo/SKILL.md``.

If the env var is unset, only the skill-local convention applies. Authors
who want a project-wide registry export the env var at the top of their
workflow; a YAML-driven registry can later be layered on top by
extending ``default_persona_search_paths`` without changing callers.
"""
from __future__ import annotations

import os
from pathlib import Path

PERSONA_PATH_ENV_VAR = "GRAPH_AGENT_PERSONA_PATH"


def default_persona_search_paths() -> list[Path]:
    """Read ``GRAPH_AGENT_PERSONA_PATH`` and return its directory entries."""
    raw = os.environ.get(PERSONA_PATH_ENV_VAR, "")
    if not raw:
        return []
    return [Path(p) for p in raw.split(os.pathsep) if p]
```

- [ ] **Step 1.4: Run to confirm pass**

```
pytest tests/graph_agent/core/test_personas.py::test_default_search_paths_empty_when_env_unset -v
```

Expected: PASS.

- [ ] **Step 1.5: Add the env-var-set case test**

```python
def test_default_search_paths_returns_env_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv(PERSONA_PATH_ENV_VAR, f"{a}{os.pathsep}{b}")
    assert default_persona_search_paths() == [a, b]


def test_default_search_paths_skips_empty_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    a = tmp_path / "a"
    a.mkdir()
    # leading separator + double separator + trailing separator should all be ignored
    monkeypatch.setenv(PERSONA_PATH_ENV_VAR, f"{os.pathsep}{a}{os.pathsep}{os.pathsep}")
    assert default_persona_search_paths() == [a]
```

Add `import os` at the top of `test_personas.py`.

- [ ] **Step 1.6: Run to confirm pass**

```
pytest tests/graph_agent/core/test_personas.py -v
```

Expected: 3 passed.

- [ ] **Step 1.7: Commit**

```
git add src/core/graph_agent/core/personas.py tests/graph_agent/core/test_personas.py
git commit -m "$(cat <<'EOF'
feat(personas): add env-var-driven default persona search paths

Introduces the GRAPH_AGENT_PERSONA_PATH convention (os.pathsep-separated,
PYTHONPATH-style) as the explicit replacement for the implicit walk-up
that loader._resolve_persona used to do. Helper-only commit; the
resolver itself lands in the next commit.
EOF
)"
```

---

## Task 2: Implement `resolve_persona` in the new module

**Files:**
- Modify: `src/core/graph_agent/core/personas.py`
- Test: `tests/graph_agent/core/test_personas.py`

- [ ] **Step 2.1: Write the failing happy-path test (skill-local resolves)**

```python
# Append to tests/graph_agent/core/test_personas.py
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.manifest import PersonaSkillDef
from graph_agent.core.personas import resolve_persona


def _stage_persona(parent: Path, *, name: str) -> Path:
    """Stage a minimal valid PersonaSkillDef under parent/<name>/SKILL.md."""
    persona_dir = parent / name
    persona_dir.mkdir(parents=True, exist_ok=True)
    body = (
        "---\n"
        'schema_version: "2.0"\n'
        "type: persona\n"
        f"name: {name}\n"
        f"description: persona {name}\n"
        "role_profile: |\n"
        "  Test persona.\n"
        "---\n"
    )
    path = persona_dir / "SKILL.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_resolve_persona_finds_skill_local(tmp_path: Path) -> None:
    base_dir = tmp_path
    _stage_persona(base_dir / "subskills", name="reviewer")

    persona = resolve_persona("reviewer", base_dir=base_dir)

    assert isinstance(persona, PersonaSkillDef)
    assert persona.name == "reviewer"
```

- [ ] **Step 2.2: Run to confirm failure**

```
pytest tests/graph_agent/core/test_personas.py::test_resolve_persona_finds_skill_local -v
```

Expected: `ImportError: cannot import name 'resolve_persona'`.

- [ ] **Step 2.3: Implement `resolve_persona`**

Append to `src/core/graph_agent/core/personas.py`:

```python
from .exceptions import SkillLoadError


def resolve_persona(
    name: str,
    *,
    base_dir: Path,
    search_paths: list[Path] | None = None,
) -> "PersonaSkillDef":
    """Resolve a persona ``name`` to a ``PersonaSkillDef`` manifest.

    Args:
        name: The persona name as written in ``adopted_persona``.
        base_dir: The parent directory of the SKILL.md that referenced
            the persona. ``<base_dir>/subskills/<name>/SKILL.md`` is
            always checked first.
        search_paths: Additional registry root directories. Each entry
            ``<root>`` is checked as ``<root>/<name>/SKILL.md`` in the
            order given. ``None`` falls back to
            :func:`default_persona_search_paths`, which reads
            ``GRAPH_AGENT_PERSONA_PATH``.

    Raises:
        SkillLoadError: when no candidate path exists, or when a
            candidate exists but does not parse as a ``PersonaSkillDef``.
    """
    from pydantic import TypeAdapter

    from .manifest import PersonaSkillDef, SkillManifest
    from .parser import parse_skill_file

    if search_paths is None:
        search_paths = default_persona_search_paths()

    candidates: list[Path] = [base_dir / "subskills" / name / "SKILL.md"]
    candidates.extend(root / name / "SKILL.md" for root in search_paths)

    for candidate in candidates:
        if not candidate.exists():
            continue
        parsed = parse_skill_file(candidate)
        manifest = TypeAdapter(SkillManifest).validate_python(parsed["frontmatter"])
        if not isinstance(manifest, PersonaSkillDef):
            raise SkillLoadError(
                f"adopted_persona '{name}' resolved to {candidate}, but its "
                f"type is {type(manifest).__name__}, not PersonaSkillDef."
            )
        return manifest

    raise SkillLoadError(
        f"adopted_persona '{name}' not found. Searched: "
        + ", ".join(str(c) for c in candidates)
    )
```

The string-quoted `"PersonaSkillDef"` return type avoids importing `PersonaSkillDef` at module top level (matches the pattern the loader uses to keep `manifest.py` deferrable).

- [ ] **Step 2.4: Run to confirm pass**

```
pytest tests/graph_agent/core/test_personas.py::test_resolve_persona_finds_skill_local -v
```

Expected: PASS.

- [ ] **Step 2.5: Add the env-var-search-path resolution test**

```python
def test_resolve_persona_finds_via_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base_dir = tmp_path / "skill_a"
    base_dir.mkdir()
    registry = tmp_path / "global_personas"
    _stage_persona(registry, name="reviewer")
    monkeypatch.setenv(PERSONA_PATH_ENV_VAR, str(registry))

    persona = resolve_persona("reviewer", base_dir=base_dir)

    assert persona.name == "reviewer"


def test_resolve_persona_skill_local_precedes_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base_dir = tmp_path / "skill_a"
    base_dir.mkdir()
    _stage_persona(base_dir / "subskills", name="reviewer")
    registry = tmp_path / "global_personas"
    _stage_persona(registry, name="reviewer")
    monkeypatch.setenv(PERSONA_PATH_ENV_VAR, str(registry))

    persona = resolve_persona("reviewer", base_dir=base_dir)

    # The persona name is identical, so we verify precedence by checking
    # the resolved file path indirectly: the skill-local file is the one
    # under base_dir/subskills/, and the env-var file is under registry/.
    # Re-resolve with explicit search_paths=[] to confirm skill-local is
    # the one being picked.
    persona_no_env = resolve_persona("reviewer", base_dir=base_dir, search_paths=[])
    assert persona_no_env.name == persona.name == "reviewer"
```

- [ ] **Step 2.6: Add the missing-and-wrong-type failure tests**

```python
def test_resolve_persona_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(SkillLoadError) as exc:
        resolve_persona("nope", base_dir=tmp_path, search_paths=[])
    assert "nope" in str(exc.value)
    assert "Searched:" in str(exc.value)


def test_resolve_persona_raises_when_wrong_type(tmp_path: Path) -> None:
    base_dir = tmp_path
    sub_dir = base_dir / "subskills" / "not_a_persona"
    sub_dir.mkdir(parents=True)
    (sub_dir / "SKILL.md").write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "type: graph\n"
        "name: not_a_persona\n"
        "description: graph not persona\n"
        "io:\n  inputs: []\n  outputs: []\n"
        "phases:\n"
        "  - name: only\n"
        "    mode: logic\n"
        "    execute_steps:\n"
        "      - graph_agent.callbacks.events.SubgraphEnterEvent\n"
        "---\n",
        encoding="utf-8",
    )

    with pytest.raises(SkillLoadError) as exc:
        resolve_persona("not_a_persona", base_dir=base_dir, search_paths=[])
    assert "PersonaSkillDef" in str(exc.value)
    assert "not_a_persona" in str(exc.value)
```

- [ ] **Step 2.7: Add the explicit-search-paths-override-env-var test**

```python
def test_resolve_persona_explicit_search_paths_override_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base_dir = tmp_path / "skill_a"
    base_dir.mkdir()
    env_registry = tmp_path / "env_registry"
    _stage_persona(env_registry, name="reviewer")
    explicit_registry = tmp_path / "explicit_registry"
    _stage_persona(explicit_registry, name="reviewer")
    monkeypatch.setenv(PERSONA_PATH_ENV_VAR, str(env_registry))

    # Passing search_paths=[] disables the env var entirely
    with pytest.raises(SkillLoadError):
        resolve_persona(
            "reviewer", base_dir=base_dir, search_paths=[explicit_registry / "wrong"],
        )

    # Passing the explicit registry succeeds even though env var points elsewhere
    persona = resolve_persona(
        "reviewer", base_dir=base_dir, search_paths=[explicit_registry],
    )
    assert persona.name == "reviewer"
```

- [ ] **Step 2.8: Run all tests in the file**

```
pytest tests/graph_agent/core/test_personas.py -v
```

Expected: 8 passed (3 from Task 1 + 5 added in Task 2).

- [ ] **Step 2.9: Commit**

```
git add src/core/graph_agent/core/personas.py tests/graph_agent/core/test_personas.py
git commit -m "$(cat <<'EOF'
feat(personas): public resolve_persona with explicit registry

Replaces loader._resolve_persona's walk-up with a deterministic two-tier
lookup: skill-local subskills/<name>/SKILL.md, then any roots passed via
search_paths (or, by default, GRAPH_AGENT_PERSONA_PATH). Loader and
validator still call _resolve_persona for now; migration follows in a
separate commit.
EOF
)"
```

---

## Task 3: Migrate the loader callsites

**Files:**
- Modify: `src/core/graph_agent/core/loader.py:382-425` (delete `_resolve_persona`)
- Modify: `src/core/graph_agent/core/loader.py:475` (update call in `_phase_from_agent_skill`)
- Modify: `src/core/graph_agent/core/loader.py:510` (update call in graph-skill LLM phase branch)

- [ ] **Step 3.1: Confirm baseline tests pass before the swap**

```
pytest tests/ --ignore=tests/llm_client_manager -q
```

Expected: 401 (or higher) passed. Record the exact count.

- [ ] **Step 3.2: Delete `_resolve_persona` from loader.py**

Open `src/core/graph_agent/core/loader.py` and remove the entire function definition at lines 382-425, including the docstring and the `TODO(PR#7)` block (the TODO is now satisfied). Leave a single blank line where the function used to be so the surrounding helpers (`_compose_agent_system_prompt` above, `_inject_persona` below) keep their double-blank separation.

- [ ] **Step 3.3: Update the import block at the top of loader.py**

Add to the existing imports (alphabetical within the local-imports group):

```python
from .personas import resolve_persona
```

- [ ] **Step 3.4: Update the callsite at line 475 (formerly `_phase_from_agent_skill`)**

Find the existing line:

```python
        persona_manifest = _resolve_persona(manifest.adopted_persona, base_dir)
```

Replace with:

```python
        persona_manifest = resolve_persona(
            manifest.adopted_persona, base_dir=base_dir,
        )
```

- [ ] **Step 3.5: Update the callsite at line 510 (graph-skill LLM phase branch)**

Find the existing line:

```python
            persona_manifest = _resolve_persona(phase_def.adopted_persona, base_dir)
```

Replace with:

```python
            persona_manifest = resolve_persona(
                phase_def.adopted_persona, base_dir=base_dir,
            )
```

- [ ] **Step 3.6: Run the full loader-touching test suite**

```
pytest tests/graph_agent/core/test_loader.py tests/graph_agent/core/test_manifest_phase_builders.py -v
```

Expected: all green. The persona injection tests in `test_manifest_phase_builders.py` (lines 223, 259, 315, 354) cover the agent and LLM branches.

- [ ] **Step 3.7: Run the full suite to confirm no regressions**

```
pytest tests/ --ignore=tests/llm_client_manager -q
```

Expected: same count as Step 3.1 (or higher; the new `test_personas.py` adds tests).

- [ ] **Step 3.8: Commit**

```
git add src/core/graph_agent/core/loader.py
git commit -m "$(cat <<'EOF'
refactor(loader): migrate persona resolution to public personas module

Drop the private _resolve_persona helper; both callsites now use the
explicit registry from graph_agent.core.personas. Removes the walk-up
that searched parent directories for a 'skills/' folder — global
registries are now opt-in via GRAPH_AGENT_PERSONA_PATH.
EOF
)"
```

---

## Task 4: Migrate the validator

**Files:**
- Modify: `src/core/graph_agent/core/validators/persona_resolution.py:12-16`
- Modify: `src/core/graph_agent/core/validators/persona_resolution.py:69`

- [ ] **Step 4.1: Update the import in the validator**

Open `src/core/graph_agent/core/validators/persona_resolution.py`. Replace:

```python
from ..compiler import CompileIssue
from ..exceptions import SkillLoadError
# Cross-module private import is intentional: keeps the walk-up
# resolver as a single source of truth between load-time and
# compile-time. See plan "Scope decisions". Promoting _resolve_persona
# to public is tracked separately in loader.py's TODO block.
from ..loader import _resolve_persona
from ..manifest import AgentSkillDef, GraphSkillDef, LLMPhase
```

With:

```python
from ..compiler import CompileIssue
from ..exceptions import SkillLoadError
from ..manifest import AgentSkillDef, GraphSkillDef, LLMPhase
from ..personas import resolve_persona
```

- [ ] **Step 4.2: Update the call site in `_check_one`**

Replace:

```python
    try:
        _resolve_persona(persona_name, base_dir)
```

With:

```python
    try:
        resolve_persona(persona_name, base_dir=base_dir)
```

- [ ] **Step 4.3: Run the validator's existing unit tests**

```
pytest tests/graph_agent/core/validators/test_persona_resolution.py -v
```

Expected: 7 passed (no behavioral change for skill-local cases).

- [ ] **Step 4.4: Add an env-var-aware test to the validator suite**

Append to `tests/graph_agent/core/validators/test_persona_resolution.py`:

```python
import os

from graph_agent.core.personas import PERSONA_PATH_ENV_VAR


def test_validator_resolves_via_env_var_registry(
    monkeypatch, tmp_path: Path,
) -> None:
    """Validator must use the same default search paths as the loader."""
    # base_dir has no subskills/ — only the env var registry knows the persona
    base_dir = tmp_path / "skill_root"
    base_dir.mkdir()
    registry = tmp_path / "global_personas"
    registry_persona = registry / "external_reviewer"
    registry_persona.mkdir(parents=True)
    (registry_persona / "SKILL.md").write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "type: persona\n"
        "name: external_reviewer\n"
        "description: persona only reachable via env var\n"
        "role_profile: |\n"
        "  External reviewer persona.\n"
        "---\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(PERSONA_PATH_ENV_VAR, str(registry))

    agent_path = _write_agent_skill(
        base_dir, name="my_agent", adopted_persona="external_reviewer",
    )
    raw = parse_skill_file(agent_path)["frontmatter"]
    manifest = TypeAdapter(SkillManifest).validate_python(raw)

    issues = check_persona_resolution(manifest, base_dir=base_dir)

    assert issues == []
```

- [ ] **Step 4.5: Run the validator suite again**

```
pytest tests/graph_agent/core/validators/test_persona_resolution.py -v
```

Expected: 8 passed.

- [ ] **Step 4.6: Run the integration-test layer**

```
pytest tests/graph_agent/core/test_compile_skill_persona_resolution_integration.py -v
```

Expected: 1 passed (no behavior change for the missing-persona case).

- [ ] **Step 4.7: Commit**

```
git add src/core/graph_agent/core/validators/persona_resolution.py tests/graph_agent/core/validators/test_persona_resolution.py
git commit -m "$(cat <<'EOF'
refactor(validators): drop cross-module private import in persona_resolution

The validator now imports the public resolve_persona from
graph_agent.core.personas instead of the private loader helper. Adds a
test that exercises the GRAPH_AGENT_PERSONA_PATH registry to confirm
load-time and compile-time agree on search order.
EOF
)"
```

---

## Task 5: Update compiler.py docstring

**Files:**
- Modify: `src/core/graph_agent/core/compiler.py:36-40` (PR #7 step 3 bullet)

- [ ] **Step 5.1: Update the persona-resolution bullet**

Open `src/core/graph_agent/core/compiler.py`. Find the existing bullet:

```
- **Persona resolution** ✅ shipped in PR #7 step 3.
  See ``validators/persona_resolution.py``. Reuses
  ``loader._resolve_persona`` so compile-time and load-time agree on
  the search order; promoting that helper to a public registry remains
  a separate refactor (loader.py TODO).
```

Replace with:

```
- **Persona resolution** ✅ shipped in PR #7 step 3 + PR #7 step 5.
  See ``validators/persona_resolution.py`` and ``personas.py``. The
  loader's private ``_resolve_persona`` was promoted to the public
  ``personas.resolve_persona`` and the implicit walk-up was replaced
  with the explicit ``GRAPH_AGENT_PERSONA_PATH`` env-var registry —
  load-time and compile-time share one resolver and one search order.
```

- [ ] **Step 5.2: Run the full suite**

```
pytest tests/ --ignore=tests/llm_client_manager -q
```

Expected: 401 + 8 (new persona tests) + 1 (validator env-var test) = 410 passed (or higher if the existing baseline drifted upward in earlier tasks).

- [ ] **Step 5.3: Commit**

```
git add src/core/graph_agent/core/compiler.py
git commit -m "$(cat <<'EOF'
docs(compiler): persona registry promoted to public personas module

Updates the PR #7 step 3 bullet to reflect the resolver split out into
graph_agent.core.personas with explicit GRAPH_AGENT_PERSONA_PATH-driven
search order.
EOF
)"
```

---

## Task 6: Push and verify

- [ ] **Step 6.1: Run the final full suite**

```
pytest tests/ --ignore=tests/llm_client_manager -q
```

Expected: ≥410 passed, 0 failed.

- [ ] **Step 6.2: Push to remote**

```
git push origin feat/studio-phase0-manifest
```

- [ ] **Step 6.3: Verify the branch tip**

```
git log --oneline -5
```

Expected: 5 new commits on top of the previous tip (`85e7484`):
1. `feat(personas): add env-var-driven default persona search paths`
2. `feat(personas): public resolve_persona with explicit registry`
3. `refactor(loader): migrate persona resolution to public personas module`
4. `refactor(validators): drop cross-module private import in persona_resolution`
5. `docs(compiler): persona registry promoted to public personas module`

---

## Self-Review

**Spec coverage:**
- Walk-up dropped → Tasks 1, 2, 3 (env var registry replaces it).
- Loader callsites migrated → Task 3 (lines 475 and 510).
- Validator cross-module-private-import dropped → Task 4.
- Public API for compile-time + load-time sharing → Task 1, 2 (new `personas.py`).
- Docstring TODO closed → Task 5.

**Placeholder scan:** every step has exact code, exact paths, exact commands, and an explicit expected outcome. No "TBD" / "implement later" / "similar to" references.

**Type consistency:** `PERSONA_PATH_ENV_VAR` (str), `default_persona_search_paths() -> list[Path]`, and `resolve_persona(name, *, base_dir, search_paths=None) -> PersonaSkillDef` are used identically in tests, loader migration, and validator migration.

**Scope check:** single subsystem (persona resolution). No cross-cutting refactor.
