"""Unit tests for the persona registry."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.manifest import PersonaSkillDef
from graph_agent.core.personas import (
    PERSONA_PATH_ENV_VAR,
    default_persona_search_paths,
    resolve_persona,
)


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


def test_default_search_paths_empty_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PERSONA_PATH_ENV_VAR, raising=False)
    assert default_persona_search_paths() == []


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


def test_resolve_persona_finds_skill_local(tmp_path: Path) -> None:
    base_dir = tmp_path
    _stage_persona(base_dir / "subskills", name="reviewer")

    persona = resolve_persona("reviewer", base_dir=base_dir)

    assert isinstance(persona, PersonaSkillDef)
    assert persona.name == "reviewer"


def test_resolve_persona_finds_via_env_var(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "skill_a"
    base_dir.mkdir()
    registry = tmp_path / "global_personas"
    _stage_persona(registry, name="reviewer")
    monkeypatch.setenv(PERSONA_PATH_ENV_VAR, str(registry))

    persona = resolve_persona("reviewer", base_dir=base_dir)

    assert persona.name == "reviewer"


def test_resolve_persona_skips_directory_candidate_and_uses_next_registry(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "skill_a"
    base_dir.mkdir()
    broken_registry = tmp_path / "broken_registry"
    (broken_registry / "reviewer" / "SKILL.md").mkdir(parents=True)
    valid_registry = tmp_path / "valid_registry"
    _stage_persona(valid_registry, name="reviewer")

    persona = resolve_persona(
        "reviewer",
        base_dir=base_dir,
        search_paths=[broken_registry, valid_registry],
    )

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

    # Confirm skill-local wins by passing search_paths=[] and getting same persona
    persona_no_env = resolve_persona("reviewer", base_dir=base_dir, search_paths=[])
    assert persona_no_env.name == persona.name == "reviewer"


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

    # Explicit empty search_paths disables the env var entirely
    with pytest.raises(SkillLoadError):
        resolve_persona(
            "reviewer",
            base_dir=base_dir,
            search_paths=[explicit_registry / "wrong"],
        )

    # Explicit registry resolves even when env var points elsewhere
    persona = resolve_persona(
        "reviewer",
        base_dir=base_dir,
        search_paths=[explicit_registry],
    )
    assert persona.name == "reviewer"
