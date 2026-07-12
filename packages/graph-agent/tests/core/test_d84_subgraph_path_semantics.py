from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.manifest import AgentNodeAST, SubgraphNodeAST
from graph_agent.core.topology_projection import read_subgraph_path


class ExplodingResolver:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def resolve_skill(self, skill_id: str) -> Path:
        self.calls.append(skill_id)
        raise AssertionError(f"SUBGRAPH path semantics must not resolve registry skill {skill_id!r}")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _graph(root: Path, *, name: str, phase: str) -> None:
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


def _logic_child(root: Path) -> None:
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
    _write(root / "phases" / "done" / "actions" / "identity.py", "def identity(inputs):\n    return {}\n")


def _subgraph_parent(root: Path, child_path: str) -> None:
    _graph(root, name="parent", phase="delegate")
    _write(
        root / "phases" / "delegate" / "SUBGRAPH.md",
        f"""---
path: {child_path}
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


def _target_skill_parent(root: Path) -> None:
    _graph(root, name="parent", phase="delegate")
    _write(
        root / "phases" / "delegate" / "SUBGRAPH.md",
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


def _agent_ast_payload(subgraph_path: Path) -> dict[str, Any]:
    return {
        "mode": "agent",
        "role": "Planner",
        "goal": "Plan the work.",
        "io": {
            "inputs": {"type": "object", "properties": {}},
            "outputs": {"type": "object", "properties": {}},
        },
        "subagents": [
            {
                "name": "worker",
                "target_skill": "demo.worker",
                "description": "Callable subagent still uses registry target_skill.",
            }
        ],
        "subgraphs": [
            {
                "name": "child_graph",
                "path": str(subgraph_path),
                "description": "Inspectable child graph uses absolute path.",
            }
        ],
    }


def test_subgraph_ast_accepts_absolute_path() -> None:
    ast = SubgraphNodeAST.model_validate(
        {
            "mode": "subgraph",
            "path": "/workspace/child",
            "io": {"inputs": {"type": "object"}, "outputs": {"type": "object"}},
        }
    )

    assert ast.path == "/workspace/child"
    assert ast.target_skill == "/workspace/child"
    assert "target_skill" in ast.model_fields_set
    assert ast.model_dump(mode="json")["path"] == "/workspace/child"


def test_subgraph_ast_accepts_relative_path() -> None:
    # In-skill subgraphs may declare a path relative to the skill root; the AST
    # accepts it and the loader resolves it against the root (and enforces it
    # stays within the root). Only blank paths are rejected at the AST layer.
    ast = SubgraphNodeAST.model_validate(
        {
            "mode": "subgraph",
            "path": "children/demo",
            "io": {"inputs": {"type": "object"}, "outputs": {"type": "object"}},
        }
    )
    assert ast.path == "children/demo"

    with pytest.raises(ValidationError):
        SubgraphNodeAST.model_validate(
            {
                "mode": "subgraph",
                "path": "   ",
                "io": {"inputs": {"type": "object"}, "outputs": {"type": "object"}},
            }
        )


def test_subgraph_target_skill_is_rejected_with_migration_diagnostic(tmp_path: Path) -> None:
    _target_skill_parent(tmp_path)

    with pytest.raises(SkillLoadError) as exc_info:
        compile_skill(tmp_path, cache=False, skill_resolver=ExplodingResolver())

    assert exc_info.value.payload is not None
    assert exc_info.value.payload.code == "[F-v3-subgraph-target-skill-invalid]"
    message = str(exc_info.value).lower()
    assert "target_skill" in message
    assert "path" in message
    assert "migrat" in message or "deprecated" in message


def test_subgraph_absolute_path_compiles_and_assembles_without_registry_resolver(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = parent / "subgraphs" / "child"
    _logic_child(child)
    _subgraph_parent(parent, str(child))
    resolver = ExplodingResolver()

    compiled = compile_skill(parent, cache=False, skill_resolver=resolver)
    assembled = assemble_graph(compiled, skill_resolver=resolver)

    assert resolver.calls == []
    assert assembled.phase_ids == ["delegate"]


def test_subgraph_relative_path_compiles_and_assembles_within_root(tmp_path: Path) -> None:
    # A SUBGRAPH.md `path` declared relative to the skill root must resolve at
    # ASSEMBLY time exactly as it does at compile time (against the skill root
    # derived from the SUBGRAPH.md location), not be rejected for "must be
    # absolute". This is what lets a skill survive being relocated (e.g. Studio
    # copying it into an ephemeral run dir): the relative path re-resolves against
    # wherever the skill root currently is.
    parent = tmp_path / "parent"
    child = parent / "subgraphs" / "child"
    _logic_child(child)
    _subgraph_parent(parent, "subgraphs/child")
    resolver = ExplodingResolver()

    compiled = compile_skill(parent, cache=False, skill_resolver=resolver)
    assembled = assemble_graph(compiled, skill_resolver=resolver)

    assert resolver.calls == []
    assert assembled.phase_ids == ["delegate"]


def test_subgraph_relative_path_assembles_after_skill_root_relocation(tmp_path: Path) -> None:
    # Faithful reproduction of the Studio predict/run failure: compile the skill
    # in place, then copy the whole tree to a different absolute location (as the
    # ephemeral run sandbox does) and assemble from the copy. A relative subgraph
    # path must re-resolve against the relocated root; an absolute path baked at
    # authoring time would "escape" the new root and fail.
    import shutil

    origin = tmp_path / "origin" / "parent"
    child = origin / "subgraphs" / "child"
    _logic_child(child)
    _subgraph_parent(origin, "subgraphs/child")
    resolver = ExplodingResolver()
    compile_skill(origin, cache=False, skill_resolver=resolver)

    relocated = tmp_path / "ephemeral_run_skills" / "deadbeef" / "parent"
    shutil.copytree(origin, relocated)

    compiled = compile_skill(relocated, cache=False, skill_resolver=resolver)
    assembled = assemble_graph(compiled, skill_resolver=resolver)

    assert resolver.calls == []
    assert assembled.phase_ids == ["delegate"]


@pytest.mark.parametrize(
    ("case_name", "make_child_path", "expected"),
    [
        ("outside_root", lambda parent: parent.parent / "outside-child", "escapes"),
        ("missing_directory", lambda parent: parent / "subgraphs" / "missing-child", "not a directory"),
        ("not_directory", lambda parent: parent / "subgraphs" / "child-file", "not a directory"),
        ("missing_graph", lambda parent: parent / "subgraphs" / "child-without-graph", "GRAPH.md"),
    ],
)
def test_subgraph_path_compile_reports_structured_path_failures(
    tmp_path: Path,
    case_name: str,
    make_child_path: Any,
    expected: str,
) -> None:
    parent = tmp_path / "parent"
    child_path = make_child_path(parent)
    if case_name == "outside_root":
        _logic_child(child_path)
    elif case_name == "not_directory":
        child_path.parent.mkdir(parents=True, exist_ok=True)
        child_path.write_text("not a directory", encoding="utf-8")
    elif case_name == "missing_graph":
        (child_path / "phases").mkdir(parents=True, exist_ok=True)
    _subgraph_parent(parent, str(child_path))

    with pytest.raises(SkillLoadError) as exc_info:
        compile_skill(parent, cache=False, skill_resolver=ExplodingResolver())

    assert exc_info.value.payload is not None
    assert exc_info.value.payload.code == "[F-v3-subgraph-target-skill-invalid]"
    assert expected in str(exc_info.value)


def test_agent_subgraphs_use_path_while_subagents_keep_target_skill(tmp_path: Path) -> None:
    ast = AgentNodeAST.model_validate(_agent_ast_payload(tmp_path / "child"))

    assert ast.subgraphs[0].path == str(tmp_path / "child")
    assert "target_skill" not in ast.subgraphs[0].model_fields_set
    assert ast.subagents[0].target_skill == "demo.worker"


def test_agent_subgraphs_reject_target_skill_registry_id(tmp_path: Path) -> None:
    payload = _agent_ast_payload(tmp_path / "child")
    payload["subgraphs"][0] = {
        "name": "child_graph",
        "target_skill": "demo.child",
        "description": "Registry ids are for subagents, not subgraphs.",
    }

    # engine-compile-diagnostics-v2 §5.1: the revived agent-subgraph-invalid validator
    # rejects the registry-id field target_skill (subgraphs are addressed by path).
    with pytest.raises(ValidationError, match="target_skill"):
        AgentNodeAST.model_validate(payload)


def test_read_subgraph_path_resolves_relative_to_absolute(tmp_path: Path) -> None:
    # The topology projection (consumed by Studio's Subgraph Library + inline
    # drill-down) must surface a RESOLVED ABSOLUTE child path even when the
    # author declared the recommended relative-to-skill-root form. Returning the
    # raw "subgraph/child" string makes the frontend's absolute-path check fall
    # through to "missing", so a perfectly valid in-skill subgraph renders red.
    skill_root = tmp_path / "parent"
    _logic_child(skill_root / "subgraph" / "child")
    _subgraph_parent(skill_root, "subgraph/child")

    resolved = read_subgraph_path(skill_root, "delegate")

    assert resolved == str((skill_root / "subgraph" / "child").resolve())
    assert Path(resolved).is_absolute()


def test_read_subgraph_path_passes_absolute_through(tmp_path: Path) -> None:
    skill_root = tmp_path / "parent"
    child = skill_root / "subgraph" / "child"
    _logic_child(child)
    _subgraph_parent(skill_root, str(child))

    assert read_subgraph_path(skill_root, "delegate") == str(child)


def test_read_subgraph_path_returns_none_without_path(tmp_path: Path) -> None:
    skill_root = tmp_path / "parent"
    _target_skill_parent(skill_root)

    assert read_subgraph_path(skill_root, "delegate") is None
