from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core import (
    SkillResolutionError,
    SkillResolverProtocol,
    resolve_skill_root,
    validate_skill_id,
)
from graph_agent.core.loader import SkillLoader
from tests.conftest import InMemorySkillResolver

_FIXTURES = Path(__file__).parents[1] / "fixtures"
_REGISTRY_FIXTURE = _FIXTURES / "v030_skill_registry"


def _write_graph_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "GRAPH.md").write_text(
        '---\nschema_version: "0.3.0"\nname: child_skill\nphases: []\n---\n',
        encoding="utf-8",
    )


def test_skill_resolver_protocol_imports() -> None:
    resolver: SkillResolverProtocol = InMemorySkillResolver({})

    assert isinstance(resolver, InMemorySkillResolver)


def test_validate_skill_id_accepts_v030_ids() -> None:
    validate_skill_id("child_skill")
    validate_skill_id("child-skill")
    validate_skill_id("child1")


@pytest.mark.parametrize("skill_id", ["Child", "child.skill", "../child", "_child", "1child", ""])
def test_validate_skill_id_rejects_invalid_ids(skill_id: str) -> None:
    with pytest.raises(SkillResolutionError) as exc_info:
        validate_skill_id(skill_id)

    assert exc_info.value.code == "[F-v3-resolver-skill-id-invalid]"
    assert exc_info.value.skill_id == skill_id


def test_resolve_skill_root_validates_registered_path(tmp_path: Path) -> None:
    child = tmp_path / "child"
    _write_graph_root(child)

    resolved = resolve_skill_root(InMemorySkillResolver({"child": child}), "child")

    assert resolved == child


def test_resolve_skill_root_invalid_path_has_v3_code(tmp_path: Path) -> None:
    missing_graph = tmp_path / "missing_graph"
    missing_graph.mkdir()

    with pytest.raises(SkillResolutionError) as exc_info:
        resolve_skill_root(InMemorySkillResolver({"child": missing_graph}), "child")

    assert exc_info.value.code == "[F-v3-resolver-path-invalid]"
    assert exc_info.value.skill_id == "child"


def test_resolve_skill_root_unregistered_has_v3_code() -> None:
    with pytest.raises(SkillResolutionError) as exc_info:
        resolve_skill_root(InMemorySkillResolver({}), "missing_child")

    assert exc_info.value.code == "[F-v3-skill-not-registered]"
    assert exc_info.value.skill_id == "missing_child"


def test_v030_parent_agent_subagent_target_skill_compiles() -> None:
    compiled = SkillLoader().compile_skill(
        _REGISTRY_FIXTURE / "parent",
        skill_resolver=InMemorySkillResolver(
            {"echo_agent": _REGISTRY_FIXTURE / "registry" / "echo_agent"}
        ),
    )

    subagent = compiled.subagents_by_phase["main"][0]
    tools = {tool.name: tool for tool in compiled.tools.for_phase("main")}

    assert subagent.name == "echo_expert"
    assert subagent.target_skill == "echo_agent"
    assert subagent.root == _REGISTRY_FIXTURE / "registry" / "echo_agent"
    assert "call_subagent_echo_expert" in tools


def test_v030_parent_agent_registry_miss_fails() -> None:
    with pytest.raises(SkillResolutionError) as exc_info:
        SkillLoader().compile_skill(
            _REGISTRY_FIXTURE / "parent",
            skill_resolver=InMemorySkillResolver({}),
        )

    assert exc_info.value.code == "[F-v3-skill-not-registered]"
    assert exc_info.value.skill_id == "echo_agent"


def test_v030_parent_agent_invalid_registry_path_fails(tmp_path: Path) -> None:
    not_a_skill = tmp_path / "not_a_skill"
    not_a_skill.mkdir()

    with pytest.raises(SkillResolutionError) as exc_info:
        SkillLoader().compile_skill(
            _REGISTRY_FIXTURE / "parent",
            skill_resolver=InMemorySkillResolver({"echo_agent": not_a_skill}),
        )

    assert exc_info.value.code == "[F-v3-resolver-path-invalid]"
    assert exc_info.value.skill_id == "echo_agent"
