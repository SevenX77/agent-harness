from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from graph_agent.core import graph_assembler, loader
from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.loader import CompiledSkill, PhaseDocument, SkillLoader
from graph_agent.core.manifest import GraphManifest, SubagentSpec, SubgraphNodeAST
from graph_agent.core.runner import run_skill
from graph_agent.core.skill_resolver_protocol import SkillResolverProtocol


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
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: child
io:
  inputs:
    type: object
    properties:
      text:
        type: string
  outputs:
    type: object
    properties: {}
phases:
  - done
---
<phase depends_on="input" output>done</phase>
""",
    )
    _write(
        root / "phases" / "done" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    properties:
      text:
        type: string
  outputs:
    type: object
    properties: {}
---
<action>identity</action>
""",
    )
    _write(
        root / "phases" / "done" / "actions" / "identity.py",
        "def identity(inputs):\n    return {}\n",
    )


def _subgraph_parent(root: Path, child: Path) -> None:
    _graph(root, name="parent", phase="child")
    _write(
        root / "phases" / "child" / "SUBGRAPH.md",
        f"""---
path: {child}
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
---
""",
    )


def _subagent_parent(root: Path, target_skill: str) -> None:
    _graph(root, name="parent", phase="main")
    _write(
        root / "phases" / "main" / "SKILL.md",
        f"""---
subagents:
  - name: child_expert
    target_skill: {target_skill}
    description: Resolve child by skill id.
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
---
<role>Parent</role>
<goal>Parent work.</goal>
""",
    )


def test_delta3_compile_and_runtime_entrypoints_default_local_skill_resolver(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    child = tmp_path / "demo" / "child"
    _subagent_parent(parent, "demo.child")
    _logic_skill(child)

    compiled = compile_skill(parent, cache=False)

    assembled = assemble_graph(compiled)
    assert assembled.graph is not None
    assert compiled.subagents_by_phase["main"][0].root == child


def test_delta3_run_skill_defaults_local_skill_resolver(tmp_path: Path) -> None:
    skill_root = tmp_path / "standalone"
    _logic_skill(skill_root)

    result = run_skill(
        skill_root,
        workspace_dir=(tmp_path / "workspace").resolve(),
    )

    assert result.success is True


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


def test_delta5_subgraph_ast_requires_path() -> None:
    with pytest.raises(ValidationError, match="path"):
        SubgraphNodeAST.model_validate({"mode": "subgraph", "name": "child"})


def test_delta5_graph_assembler_no_longer_exposes_sub_skill_path_resolver() -> None:
    assert not hasattr(graph_assembler, "_resolve_sub_skill" + "_path")


def test_delta5_subgraph_path_compile_smoke(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = parent / "subgraphs" / "child"
    _subgraph_parent(parent, child)
    _logic_skill(child)
    resolver: SkillResolverProtocol = DictSkillResolver({"demo.child": child})

    compiled = SkillLoader().compile_skill(parent, skill_resolver=resolver)
    graph = assemble_graph(compiled, skill_resolver=resolver)

    assert graph.phase_ids == ["child"]


def test_delta1_assemble_graph_defaults_local_resolver(tmp_path: Path) -> None:
    child = tmp_path / "parent" / "subgraphs" / "child"
    _logic_skill(child)
    phase_ast = SubgraphNodeAST.model_validate(
        {
            "mode": "subgraph",
            "name": "child",
            "path": str(child),
            "io": {"inputs": {"type": "object"}, "outputs": {"type": "object"}},
        }
    )
    compiled = CompiledSkill(
        raw={
            "graph_topology": {"phases": [{"name": "child", "depends_on": ["input"], "output": True}]}
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

    assembled = assemble_graph(compiled)

    assert assembled.graph is not None
