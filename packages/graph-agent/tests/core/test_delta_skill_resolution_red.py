from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from graph_agent.core import graph_assembler, loader
from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.loader import CompiledSkill, PhaseDocument, SkillLoader
from graph_agent.core.manifest import GraphManifest, SubagentSpec, SubgraphNodeAST
from graph_agent.core.runner import run_skill
from graph_agent.core.skill_resolver_protocol import SkillResolutionError, SkillResolverProtocol


class DictSkillResolver:
    def __init__(self, roots: dict[str, Path]) -> None:
        self.roots = roots

    def resolve_skill(self, skill_id: str) -> Path:
        return self.roots[skill_id]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _graph(root: Path, *, name: str, phase: str = "main") -> None:
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: {name}
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
phases:
  - {phase}
---
<phase depends_on="input" output>{phase}</phase>
""",
    )


def _logic_skill(root: Path) -> None:
    _graph(root, name="child", phase="done")
    _write(
        root / "phases" / "done" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
<action>identity</action>
""",
    )
    _write(
        root / "phases" / "done" / "actions" / "identity.py",
        "def identity(context):\n    return {}\n",
    )


def _subgraph_parent(root: Path) -> None:
    _graph(root, name="parent", phase="child")
    _write(
        root / "phases" / "child" / "SUBGRAPH.md",
        """---
target_skill: demo.child
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
""",
    )


def _assert_required_keyword(func: Any, name: str) -> None:
    parameter = inspect.signature(func).parameters[name]
    assert parameter.default is inspect.Parameter.empty


def test_delta3_compile_and_runtime_entrypoints_require_skill_resolver() -> None:
    _assert_required_keyword(compile_skill, "skill_resolver")
    _assert_required_keyword(SkillLoader.compile_skill, "skill_resolver")
    _assert_required_keyword(assemble_graph, "skill_resolver")
    _assert_required_keyword(run_skill, "skill_resolver")


def test_delta2_subagent_spec_rejects_legacy_path_field() -> None:
    with pytest.raises(ValidationError):
        SubagentSpec.model_validate(
            {
                "name": "legacy_child",
                "path": "subskills/child",
                "description": "Legacy path must be removed.",
            }
        )


def test_delta2_subagent_spec_has_no_path_model_field() -> None:
    assert "path" not in SubagentSpec.model_fields


def test_delta2_loader_no_longer_exposes_legacy_subagent_path_resolver() -> None:
    assert not hasattr(loader, "_resolve_subagent" + "_root")


def test_delta2_active_fixtures_no_longer_use_legacy_subagent_path() -> None:
    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "subagent_minimal"
        / "phases"
        / "main"
        / "SKILL.md"
    )
    assert "path: " + "subskills/" not in fixture.read_text(encoding="utf-8")


def test_delta5_subgraph_ast_rejects_legacy_child_reference_field() -> None:
    with pytest.raises(ValidationError):
        SubgraphNodeAST.model_validate({"mode": "subgraph", "sub_skill" + "_ref": "child"})


def test_delta5_subgraph_ast_requires_target_skill() -> None:
    with pytest.raises(ValidationError, match="target_skill"):
        SubgraphNodeAST.model_validate({"mode": "subgraph", "name": "child"})


def test_delta5_graph_assembler_no_longer_exposes_sub_skill_path_resolver() -> None:
    assert not hasattr(graph_assembler, "_resolve_sub_skill" + "_path")


def test_delta5_subgraph_target_skill_compile_smoke(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = tmp_path / "child"
    _subgraph_parent(parent)
    _logic_skill(child)
    resolver: SkillResolverProtocol = DictSkillResolver({"demo.child": child})

    compiled = SkillLoader().compile_skill(parent, skill_resolver=resolver)
    graph = assemble_graph(compiled, skill_resolver=resolver)

    assert graph.phase_ids == ["child"]


def test_delta1_assemble_graph_missing_resolver_raises_v3_code(tmp_path: Path) -> None:
    phase_ast = SubgraphNodeAST.model_validate(
        {
            "mode": "subgraph",
            "name": "child",
            "target_skill": "demo.child",
            "io": {"inputs": {"type": "object"}, "outputs": {"type": "object"}},
        }
    )
    compiled = CompiledSkill(
        raw={
            "graph_topology": {"phases": [{"id": "child", "depends_on": ["input"], "output": True}]}
        },
        manifest=GraphManifest(
            schema_version="v0.3.0",
            name="parent",
            io={"inputs": {"type": "object"}, "outputs": {"type": "object"}},
            phases=["child"],
        ),
        nodes=[
            PhaseDocument(
                phase_name="child",
                path=tmp_path / "parent" / "phases" / "child" / "SUBGRAPH.md",
                mode="subgraph",
                frontmatter={},
                raw_blocks={},
                ast=phase_ast,
            )
        ],
    )

    with pytest.raises(SkillResolutionError) as exc_info:
        assemble_graph(compiled, skill_resolver=None)
    assert exc_info.value.payload.code == "[F-v3-resolver-missing]"
