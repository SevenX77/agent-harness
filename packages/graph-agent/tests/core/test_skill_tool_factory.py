from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from graph_agent.core import runner
from graph_agent.core.skill_tool_factory import (
    SubSkillSpec,
    _build_input_model,
    _resolve_skill_path,
    build_skill_tool,
)


def test_build_input_model_supports_declared_field_types() -> None:
    model = _build_input_model(
        "demo_tool",
        {
            "title": "string, item title",
            "count": "int, number of items",
            "score": "float, confidence",
            "enabled": "bool, feature flag",
        },
    )

    payload = model.model_validate(
        {"title": "alpha", "count": "3", "score": "0.5", "enabled": "true"}
    )

    assert payload.title == "alpha"
    assert payload.count == 3
    assert payload.score == 0.5
    assert payload.enabled is True
    assert model.model_fields["title"].description == "item title"


def test_build_input_model_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="Unsupported input_schema type 'json'"):
        _build_input_model("bad_tool", {"payload": "json, raw payload"})


def test_resolve_skill_path_uses_parent_dir_for_relative_paths(tmp_path: Path) -> None:
    spec = SubSkillSpec(
        name="child",
        description="child tool",
        skill_path="skills/child/SKILL.md",
        input_schema={},
        _parent_skill_dir=tmp_path,
    )

    assert _resolve_skill_path(spec) == (tmp_path / "skills/child/SKILL.md").resolve()


def test_build_skill_tool_invokes_runner_and_returns_final_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_skill_resolver: object,
) -> None:
    skill_path = tmp_path / "child" / "SKILL.md"
    skill_path.parent.mkdir()
    skill_path.write_text("name: child\n", encoding="utf-8")
    calls: list[dict[str, Any]] = []

    def fake_run_skill(
        path: Path,
        *,
        thread_id: str,
        workspace_dir: Path,
        initial_context: dict[str, Any],
        skill_resolver: object,
    ) -> dict[str, dict[str, str]]:
        calls.append(
            {
                "path": path,
                "thread_id": thread_id,
                "workspace_dir": workspace_dir,
                "initial_context": initial_context,
                "skill_resolver": skill_resolver,
            }
        )
        return {"context": {"final_output": "done"}}

    monkeypatch.setattr(runner, "run_skill", fake_run_skill)
    tool = build_skill_tool(
        SubSkillSpec(
            name="child_tool",
            description="Run child",
            skill_path=str(skill_path),
            input_schema={"topic": "string, topic to process"},
        ),
        parent_thread_id="parent",
        parent_trace_dir=tmp_path / "traces",
        skill_resolver=mock_skill_resolver,
    )

    assert tool.invoke({"topic": "contracts"}) == "done"
    assert calls == [
        {
            "path": skill_path,
            "thread_id": calls[0]["thread_id"],
            "workspace_dir": tmp_path / "traces",
            "initial_context": {"topic": "contracts"},
            "skill_resolver": calls[0]["skill_resolver"],
        }
    ]
    assert str(calls[0]["thread_id"]).startswith("sub_parent_child_tool_")


def test_build_skill_tool_returns_error_when_final_output_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_skill_resolver: object,
) -> None:
    skill_path = tmp_path / "child" / "SKILL.md"
    skill_path.parent.mkdir()
    skill_path.write_text("name: child\n", encoding="utf-8")

    def fake_run_skill(
        path: Path,
        *,
        thread_id: str,
        workspace_dir: Path,
        initial_context: dict[str, Any],
        skill_resolver: object,
    ) -> dict[str, dict[str, str]]:
        del workspace_dir
        return {"context": {}}

    monkeypatch.setattr(runner, "run_skill", fake_run_skill)
    tool = build_skill_tool(
        SubSkillSpec(
            name="child_tool",
            description="Run child",
            skill_path=str(skill_path),
            input_schema={"topic": "string, topic to process"},
        ),
        skill_resolver=mock_skill_resolver,
    )

    assert tool.invoke({"topic": "contracts"}) == "ERROR: Sub-skill produced no final_output"


def test_build_skill_tool_rejects_missing_skill_path(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    spec = SubSkillSpec(
        name="missing",
        description="missing tool",
        skill_path=str(tmp_path / "missing" / "SKILL.md"),
        input_schema={},
    )

    with pytest.raises(ValueError, match="skill_path not found"):
        build_skill_tool(spec, skill_resolver=mock_skill_resolver)
