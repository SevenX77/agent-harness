from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

import graph_agent.core.graph_assembler as graph_assembler_module
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.graph_assembler import _build_subgraph_node, assemble_graph
from graph_agent.core.loader import CompiledSubagent, SkillLoader
from graph_agent.core.manifest import PhaseIOSchema, SubgraphNodeAST
from graph_agent.core.skill_resolver_protocol import SkillResolutionError


class DictSkillResolver:
    def __init__(self, roots: dict[str, Path]) -> None:
        self.roots = roots

    def resolve_skill(self, skill_id: str) -> Path:
        try:
            return self.roots[skill_id]
        except KeyError as exc:
            raise SkillResolutionError(skill_id, "not registered") from exc


class SubagentInput(BaseModel):
    text: str


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _schema_yaml(field_name: str = "text") -> str:
    return f"""type: object
    properties:
      {field_name}:
        type: string"""


def _write_graph(root: Path, *, name: str, phases: list[str]) -> None:
    phase_yaml = "\n".join(f"  - {phase}" for phase in phases)
    body = "\n".join(
        f'<phase depends_on="{"input" if index == 0 else phases[index - 1]}"'
        f'{" output" if index == len(phases) - 1 else ""}>{phase}</phase>'
        for index, phase in enumerate(phases)
    )
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: {name}
io:
  inputs:
    {_schema_yaml()}
  outputs:
    type: object
    properties: {{}}
phases:
{phase_yaml}
---
{body}
""",
    )


def _write_agent_phase(root: Path, phase: str, *, target_skill: str | None = None) -> None:
    subagents = ""
    if target_skill is not None:
        subagents = f"""phase_config:
  subagents:
    - name: child_{phase}
      target_skill: {target_skill}
      description: Shared child.
"""
    _write(
        root / "phases" / phase / "SKILL.md",
        f"""---
{subagents}io:
  inputs:
    {_schema_yaml()}
  outputs:
    type: object
    properties: {{}}
---
<role>{phase}</role>
<goal>Do {phase} work.</goal>
""",
    )


def _write_subgraph_phase(root: Path, phase: str, *, target_skill: str) -> None:
    _write(
        root / "phases" / phase / "SUBGRAPH.md",
        f"""---
target_skill: {target_skill}
io:
  inputs:
    {_schema_yaml()}
  outputs:
    type: object
    properties: {{}}
---
""",
    )


def _write_recursive_agent_skill(root: Path, *, name: str, target_skill: str) -> None:
    _write_graph(root, name=name, phases=["main"])
    _write_agent_phase(root, "main", target_skill=target_skill)


def _write_leaf_agent_skill(root: Path, *, name: str = "leaf") -> None:
    _write_graph(root, name=name, phases=["main"])
    _write_agent_phase(root, "main")


def _write_subgraph_skill(root: Path, *, name: str, target_skill: str) -> None:
    _write_graph(root, name=name, phases=["sub"])
    _write_subgraph_phase(root, "sub", target_skill=target_skill)


def _expect_payload_code(exc_info: pytest.ExceptionInfo[SkillLoadError], code: str) -> None:
    assert exc_info.value.payload is not None
    assert exc_info.value.payload.code == code


def test_pr4_loader_rejects_recursive_subagent_cycle_with_v3_payload(tmp_path: Path) -> None:
    skill_a = tmp_path / "skill-a"
    skill_b = tmp_path / "skill-b"
    _write_recursive_agent_skill(skill_a, name="skill-a", target_skill="demo.b")
    _write_recursive_agent_skill(skill_b, name="skill-b", target_skill="demo.a")
    resolver = DictSkillResolver({"demo.a": skill_a, "demo.b": skill_b})

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(skill_a, skill_resolver=resolver)

    _expect_payload_code(exc_info, "[F-v3-compile-recursion-cycle]")


def test_pr4_loader_rejects_compile_depth_over_twenty_with_v3_payload(tmp_path: Path) -> None:
    roots = [tmp_path / f"skill-{index}" for index in range(22)]
    registry: dict[str, Path] = {}
    for index, root in enumerate(roots):
        skill_id = f"demo.skill_{index}"
        registry[skill_id] = root
        if index == len(roots) - 1:
            _write_leaf_agent_skill(root, name=f"skill-{index}")
        else:
            _write_recursive_agent_skill(
                root,
                name=f"skill-{index}",
                target_skill=f"demo.skill_{index + 1}",
            )
    resolver = DictSkillResolver(registry)

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(roots[0], skill_resolver=resolver)

    _expect_payload_code(exc_info, "[F-v3-compile-depth-exceeded]")


def test_pr4_assemble_subgraph_cycle_uses_v3_payload_not_recursionerror(tmp_path: Path) -> None:
    skill_a = tmp_path / "skill-a"
    skill_b = tmp_path / "skill-b"
    _write_subgraph_skill(skill_a, name="skill-a", target_skill="demo.b")
    _write_subgraph_skill(skill_b, name="skill-b", target_skill="demo.a")
    resolver = DictSkillResolver({"demo.a": skill_a, "demo.b": skill_b})
    subgraph_ast = SubgraphNodeAST(
        mode="subgraph",
        target_skill="demo.b",
        io=PhaseIOSchema(
            inputs={"type": "object", "properties": {"text": {"type": "string"}}},
            outputs={"type": "object", "properties": {}},
        ),
    )

    with pytest.raises(SkillLoadError) as exc_info:
        _build_subgraph_node(
            object(),  # phase_doc is not read before the recursive compile path.
            subgraph_ast,
            None,
            1,
            resolver,
        )

    _expect_payload_code(exc_info, "[F-v3-compile-recursion-cycle]")


def test_pr4_assemble_subagent_runtime_cycle_uses_v3_payload_not_recursionerror(
    tmp_path: Path,
) -> None:
    skill_a = tmp_path / "skill-a"
    skill_b = tmp_path / "skill-b"
    _write_recursive_agent_skill(skill_a, name="skill-a", target_skill="demo.b")
    _write_recursive_agent_skill(skill_b, name="skill-b", target_skill="demo.a")
    resolver = DictSkillResolver({"demo.a": skill_a, "demo.b": skill_b})
    subagent = CompiledSubagent(
        parent_phase_id="main",
        name="child",
        target_skill="demo.b",
        description="Recursive child.",
        root=skill_b,
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        input_model=SubagentInput,
        expected_schema=SubagentInput.model_json_schema(),
    )

    with pytest.raises(SkillLoadError) as exc_info:
        graph_assembler_module._subagent_runtime_map(
            {"call_subagent_child": subagent},
            chat_model=None,
            model_resolver=None,
            callbacks=None,
            max_patch_attempts=1,
            skill_resolver=resolver,
        )

    _expect_payload_code(exc_info, "[F-v3-compile-recursion-cycle]")


def test_pr4_assemble_reuses_same_child_root_once_per_lifecycle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    parent = tmp_path / "parent"
    child = tmp_path / "child"
    _write_graph(parent, name="parent", phases=["main_a", "main_b", "main_c"])
    for phase in ("main_a", "main_b", "main_c"):
        _write_agent_phase(parent, phase, target_skill="demo.child")
    _write_leaf_agent_skill(child, name="child")
    resolver = DictSkillResolver({"demo.child": child})
    compiled = compile_skill(parent, cache=False, skill_resolver=resolver)

    original_compile_skill = SkillLoader.compile_skill
    child_compile_count = 0

    def counted_compile_skill(self, skill_root, *args, **kwargs):
        nonlocal child_compile_count
        if Path(skill_root).resolve() == child.resolve():
            child_compile_count += 1
        return original_compile_skill(self, skill_root, *args, **kwargs)

    monkeypatch.setattr(SkillLoader, "compile_skill", counted_compile_skill)

    assemble_graph(compiled, skill_resolver=resolver)

    assert child_compile_count == 1
