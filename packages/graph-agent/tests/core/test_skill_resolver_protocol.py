from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core import (
    SkillResolutionError,
    SkillResolverProtocol,
    resolve_skill_root,
    validate_skill_id,
)
from tests.conftest import InMemorySkillResolver


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
