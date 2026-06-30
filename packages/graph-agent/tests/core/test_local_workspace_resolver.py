from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.skill_resolver_protocol import SkillResolutionError


def _local_workspace_resolver_class():
    from graph_agent.core.local_workspace_resolver import LocalWorkspaceResolver

    return LocalWorkspaceResolver


def _write_graph(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: resolver-target
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases:
  - main
---
<phase depends_on="input" output>main</phase>
""",
        encoding="utf-8",
    )
    return root


def test_local_workspace_resolver_resolves_direct_directory(tmp_path: Path) -> None:
    LocalWorkspaceResolver = _local_workspace_resolver_class()
    skill_root = _write_graph(tmp_path / "direct-skill")

    resolver = LocalWorkspaceResolver(search_paths=[tmp_path])

    assert resolver.resolve_skill("direct-skill") == skill_root


def test_local_workspace_resolver_resolves_skills_child(tmp_path: Path) -> None:
    LocalWorkspaceResolver = _local_workspace_resolver_class()
    skill_root = _write_graph(tmp_path / "skills" / "child-skill")

    resolver = LocalWorkspaceResolver(search_paths=[tmp_path / "skills"])

    assert resolver.resolve_skill("child-skill") == skill_root


def test_local_workspace_resolver_resolves_dotted_id(tmp_path: Path) -> None:
    LocalWorkspaceResolver = _local_workspace_resolver_class()
    skill_root = _write_graph(tmp_path / "acme" / "echo")

    resolver = LocalWorkspaceResolver(search_paths=[tmp_path])

    assert resolver.resolve_skill("acme.echo") == skill_root


def test_local_workspace_resolver_canonicalizes_search_paths(tmp_path: Path) -> None:
    LocalWorkspaceResolver = _local_workspace_resolver_class()
    workspace = tmp_path / "workspace"
    skills = workspace / "skills"
    skills.mkdir(parents=True)

    resolver = LocalWorkspaceResolver(search_paths=[workspace / "." / "skills" / ".." / "skills"])

    assert resolver.search_paths == (skills.resolve(),)


def test_default_local_resolver_canonicalizes_skill_entrypoint(tmp_path: Path) -> None:
    from graph_agent.core.local_workspace_resolver import default_local_resolver_for_skill

    parent = _write_graph(tmp_path / "workspace" / "parent")

    resolver = default_local_resolver_for_skill(parent / ".." / "parent" / "GRAPH.md")

    assert all(path == path.resolve() for path in resolver.search_paths)
    assert parent.resolve() in resolver.search_paths


def test_local_workspace_resolver_fails_loud_on_ambiguous_skill_id(tmp_path: Path) -> None:
    LocalWorkspaceResolver = _local_workspace_resolver_class()
    literal_root = _write_graph(tmp_path / "acme.echo")
    dotted_root = _write_graph(tmp_path / "acme" / "echo")

    resolver = LocalWorkspaceResolver(search_paths=[tmp_path])

    with pytest.raises(SkillResolutionError) as exc_info:
        resolver.resolve_skill("acme.echo")

    assert exc_info.value.payload.code == "[F-v3-skill-id-ambiguous]"
    message = str(exc_info.value)
    assert str(literal_root.resolve()) in message
    assert str(dotted_root.resolve()) in message


def test_local_workspace_resolver_rejects_invalid_skill_id(tmp_path: Path) -> None:
    LocalWorkspaceResolver = _local_workspace_resolver_class()
    resolver = LocalWorkspaceResolver(search_paths=[tmp_path])

    with pytest.raises(SkillResolutionError) as exc_info:
        resolver.resolve_skill("../escape")

    assert exc_info.value.payload.code == "[F-v3-resolver-skill-id-invalid]"


def test_local_workspace_resolver_reports_unregistered_skill(tmp_path: Path) -> None:
    LocalWorkspaceResolver = _local_workspace_resolver_class()
    resolver = LocalWorkspaceResolver(search_paths=[tmp_path])

    with pytest.raises(SkillResolutionError) as exc_info:
        resolver.resolve_skill("missing.skill")

    assert exc_info.value.payload.code == "[F-v3-skill-not-registered]"
