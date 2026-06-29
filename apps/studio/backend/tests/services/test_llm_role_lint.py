"""Studio-layer lint check: an llm_role that is not a configured role.

The engine compiler treats llm_role as an opaque string (it does not know about
gateway roles), so "this role isn't configured" is a Studio config-consistency
diagnostic layered on top of a successful compile — surfaced as a WARNING on the
`llm_role` field so the Properties panel / node badge / editor underline light up
without failing the compile.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.services import skills as skill_service

_GRAPH = """---
schema_version: "v0.3.0"
name: role-demo
description: Role demo
io:
  inputs:
    type: object
    properties:
      input_text:
        type: string
    required: [input_text]
    additionalProperties: false
  outputs:
    type: object
    properties:
      review:
        type: string
    required: [review]
    additionalProperties: true
phases:
  - review
---
<phase depends_on="input" output>review</phase>
"""


def _skill_md(llm_role: str | None) -> str:
    role_line = f"llm_role: {llm_role}\n" if llm_role is not None else ""
    return (
        "---\n"
        "name: review\n"
        f"{role_line}"
        "io:\n"
        "  inputs:\n"
        "    type: object\n"
        "    properties:\n"
        "      input_text:\n"
        "        type: string\n"
        "    required: [input_text]\n"
        "  outputs:\n"
        "    type: object\n"
        "    properties:\n"
        "      review:\n"
        "        type: string\n"
        "    required: [review]\n"
        "---\n"
        "<role>You review text.</role>\n"
        "<goal>Produce a review.</goal>\n"
    )


def _write_agent_skill(skill_dir: Path, *, llm_role: str | None) -> None:
    (skill_dir / "phases" / "review").mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text(_GRAPH, encoding="utf-8")
    (skill_dir / "phases" / "review" / "SKILL.md").write_text(_skill_md(llm_role), encoding="utf-8")


def test_unconfigured_llm_role_warns_but_compile_passes(
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir, _workspaces = studio_roots
    _write_agent_skill(skills_dir / "role-demo", llm_role="ghost_role")
    monkeypatch.setattr(skill_service, "_configured_role_names", lambda: {"analyst"})

    result = skill_service.lint_skill_path(skills_dir / "role-demo")

    # Engine compile is fine — the unconfigured role does not break compilation.
    assert result.status == "passed"
    role_errs = [e for e in result.errors if e.field_path == "llm_role"]
    assert len(role_errs) == 1
    err = role_errs[0]
    assert err.severity == "warning"
    assert err.file == "phases/review/SKILL.md"
    assert err.phase_name == "review"
    assert "ghost_role" in err.message


def test_configured_llm_role_has_no_warning(
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir, _workspaces = studio_roots
    _write_agent_skill(skills_dir / "role-demo", llm_role="analyst")
    monkeypatch.setattr(skill_service, "_configured_role_names", lambda: {"analyst"})

    result = skill_service.lint_skill_path(skills_dir / "role-demo")

    assert result.status == "passed"
    assert [e for e in result.errors if e.field_path == "llm_role"] == []


def test_absent_llm_role_is_not_flagged(
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No llm_role on the agent → inherits the graph default; nothing to validate.
    skills_dir, _workspaces = studio_roots
    _write_agent_skill(skills_dir / "role-demo", llm_role=None)
    monkeypatch.setattr(skill_service, "_configured_role_names", lambda: set())

    result = skill_service.lint_skill_path(skills_dir / "role-demo")

    assert result.status == "passed"
    assert [e for e in result.errors if e.field_path == "llm_role"] == []


def test_llm_role_lint_uses_compiled_metadata_without_rereading_phase_file(
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces = studio_roots
    skill_dir = skills_dir / "role-demo"
    _write_agent_skill(skill_dir, llm_role="ghost_role")
    compiled = skill_service._load_compiled(skill_dir)

    (skill_dir / "phases" / "review" / "SKILL.md").write_text(_skill_md("analyst"), encoding="utf-8")

    errors = skill_service._llm_role_lint_errors(compiled, role_names={"analyst"})

    role_errs = [e for e in errors if e.field_path == "llm_role"]
    assert len(role_errs) == 1
    assert role_errs[0].file == "phases/review/SKILL.md"
    assert "ghost_role" in role_errs[0].message
