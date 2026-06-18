from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import graph_agent.core.graph_assembler as graph_assembler_module
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.graph_assembler import (
    _build_subgraph_node,
    _invoke_subagent_once_t23,
    assemble_graph,
)
from graph_agent.core.loader import PhaseDocument
from graph_agent.core.manifest import PhaseIOSchema, SubgraphNodeAST
from graph_agent.runtime.state_mapper import PhaseWrapper, StateMapper


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _base(root: Path, phases: str, outputs: dict[str, object] | None = None) -> None:
    phase_entries = []
    for match in re.finditer(r'<phase id="([^"]+)" src="([^"]+)" depends_on="([^"]*)"', phases):
        deps = [dep for dep in re.split(r"[\s,]+", match.group(3).strip()) if dep]
        phase_entries.append((match.group(1), deps))
    phase_yaml = "\n".join(f"  - {phase_id}" for phase_id, _ in phase_entries)
    depended_on = {dep for _, deps in phase_entries for dep in deps}
    phase_body = "\n".join(
        '<phase depends_on="{deps}"{output}>{phase_id}</phase>'.format(
            deps=", ".join(deps) if deps else "input",
            output=" output" if phase_id not in depended_on else "",
            phase_id=phase_id,
        )
        for phase_id, deps in phase_entries
    )
    output_schema = outputs or {
        "type": "object",
        "properties": {
            "seen_public": {"type": "string"},
            "saw_parent_secret": {"type": "boolean"},
            "saw_parent_message": {"type": "boolean"},
        },
    }
    output_yaml = json.dumps(output_schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: gamma2-child
io:
  inputs:
    type: object
    properties:
      public:
        type: string
  outputs:
    {output_yaml}
phases:
{phase_yaml}
---
{phase_body}
""",
    )


def _logic_action(root: Path, phase: str, action: str, body: str, outputs: list[str] | None = None) -> None:
    output_properties = {}
    if outputs is not None:
        for out in outputs:
            if out == "seen_public":
                output_properties["seen_public"] = {"type": "string"}
            else:
                output_properties[out] = {"type": "boolean"}
    else:
        output_properties = {
            "seen_public": {"type": "string"},
            "saw_parent_secret": {"type": "boolean"},
            "saw_parent_message": {"type": "boolean"},
        }
    output_yaml = json.dumps({"type": "object", "properties": output_properties}, ensure_ascii=False, indent=4).replace("\n", "\n    ")
    _write(
        root / "phases" / phase / "LOGIC.md",
        f"""---
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    {output_yaml}
---
<action>{action}</action>
""",
    )
    _write(root / "phases" / phase / "actions" / f"{action}.py", body)


def _subgraph(root: Path, phase: str, ref: str = "child") -> None:
    child_path = Path(ref) if Path(ref).is_absolute() else root / "phases" / phase / ref
    _write(
        root / "phases" / phase / "SUBGRAPH.md",
        f"""---
path: {child_path}
io:
  inputs:
    type: object
    properties:
      public:
        type: string
  outputs:
    type: object
    properties:
      seen_public:
        type: string
      saw_parent_secret:
        type: boolean
      saw_parent_message:
        type: boolean
---
""",
    )


def test_subgraph_child_starts_from_explicit_inputs_only(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _base(tmp_path, '<phase id="sub" src="phases/sub" depends_on="" />\n')
    _subgraph(tmp_path, "sub")
    child = tmp_path / "phases" / "sub" / "child"
    _base(child, '<phase id="inspect" src="phases/inspect" depends_on="" />\n')
    _logic_action(
        child,
        "inspect",
        "inspect",
        "def inspect(context):\n"
        "    return {\n"
        "        'seen_public': context.get('public'),\n"
        "        'saw_parent_secret': context.get('parent_secret') is not None,\n"
        "        'saw_parent_message': context.get('parent_message') is not None,\n"
        "    }\n",
    )

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    result = assemble_graph(compiled, skill_resolver=mock_skill_resolver).graph.invoke(
        {
            "data": {
                "inputs": {"public": "ok", "parent_secret": "do-not-leak"},
                "phase_outputs": {"upstream": {"parent_message": "do-not-leak"}},
                "scratch": {"parent_secret": "do-not-leak"},
            },
            "flow": {"trace": "parent"},
            "messages": ["parent-message"],
            "run_id": "parent-run",
        }
    )

    assert result["data"]["phase_outputs"]["sub"] == {
        "seen_public": "ok",
        "saw_parent_secret": False,
        "saw_parent_message": False,
    }


def test_subgraph_child_outputs_are_deterministic_across_child_phases(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _base(tmp_path, '<phase id="sub" src="phases/sub" depends_on="" />\n')
    _subgraph(tmp_path, "sub")
    child = tmp_path / "phases" / "sub" / "child"
    _base(
        child,
        '<phase id="first" src="phases/first" depends_on="" />\n'
        '<phase id="second" src="phases/second" depends_on="first" />\n',
    )
    _logic_action(child, "first", "first", "def first(context):\n    return {'seen_public': 'a'}\n", outputs=["seen_public"])
    _logic_action(
        child,
        "second",
        "second",
        "def second(context):\n"
        "    return {'saw_parent_secret': False, 'saw_parent_message': False}\n",
        outputs=["saw_parent_secret", "saw_parent_message"],
    )

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    result = assemble_graph(compiled, skill_resolver=mock_skill_resolver).graph.invoke(
        {"data": {"inputs": {"public": "ok"}}, "flow": {}, "messages": [], "run_id": "r1"}
    )

    assert result["data"]["phase_outputs"]["sub"] == {
        "seen_public": "a",
        "saw_parent_secret": False,
        "saw_parent_message": False,
    }


def test_subagent_child_without_phase_outputs_does_not_flat_diff_parent_data() -> None:
    from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
    class FlatOnlyGraph:
        def invoke(self, state, config=None):
            del config
            return WorkflowState(
                data=state["data"].model_copy(),
                flow=state["flow"],
                messages=[],
            )

    parent_state = WorkflowState(
        data=BusinessData.model_validate({"item": "a"}),
        flow=FrameworkState(),
        messages=[],
    )
    result = _invoke_subagent_once_t23(
        SimpleNamespace(graph=FlatOnlyGraph()),
        parent_state,
        {"item": "a"},
    )

    assert result["data"] == {}


def test_subagent_child_flow_is_deep_copied_and_depth_increments() -> None:
    from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
    captured_child_flow: FrameworkState | None = None

    class MutatingChildGraph:
        def invoke(self, state, config=None):
            del config
            nonlocal captured_child_flow
            captured_child_flow = state["flow"].model_copy()
            state["flow"].working_memory["child_only"] = True
            state["flow"].subagent_depth = 2
            return WorkflowState(
                data=BusinessData(),
                flow=state["flow"],
                messages=[],
            )

    parent_flow = FrameworkState(
        subagent_depth=1,
        working_memory={"parent_only": True},
    )
    parent_state = WorkflowState(
        data=BusinessData.model_validate({"item": "a"}),
        flow=parent_flow,
        messages=[],
    )
    result = _invoke_subagent_once_t23(
        SimpleNamespace(graph=MutatingChildGraph()),
        parent_state,
        {"item": "a"},
    )

    assert captured_child_flow is not None
    assert captured_child_flow.subagent_depth == 2
    assert parent_flow.subagent_depth == 1
    assert parent_flow.working_memory == {"parent_only": True}
    assert result["flow"].working_memory["child_only"] is True


def test_subgraph_child_flow_is_deep_copied_and_depth_increments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
    class MutatingSubgraph:
        def invoke(self, state):
            assert state["flow"].subagent_depth == 2
            state["flow"].working_memory["child_only"] = True
            return WorkflowState(
                data=BusinessData(),
                flow=state["flow"],
                messages=[],
            )

    class FakeSkillLoader:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        def compile_skill(self, *args, **kwargs):
            del args, kwargs
            return SimpleNamespace(manifest=SimpleNamespace(phases=[]))

    monkeypatch.setattr(
        graph_assembler_module,
        "_resolve_subgraph_path_root_for_assembly",
        lambda source, value: tmp_path,
    )
    monkeypatch.setattr(graph_assembler_module, "SkillLoader", FakeSkillLoader)
    monkeypatch.setattr(
        graph_assembler_module,
        "assemble_graph",
        lambda *args, **kwargs: SimpleNamespace(graph=MutatingSubgraph()),
    )
    phase_ast = SubgraphNodeAST(
        mode="subgraph",
        path=str(tmp_path),
        io=PhaseIOSchema(
            inputs={"type": "object", "properties": {"public": {"type": "string"}}},
            outputs={"type": "object", "properties": {}},
        ),
    )
    phase_doc = PhaseDocument(
        phase_name="sub",
        path=tmp_path / "phases" / "sub" / "SUBGRAPH.md",
        mode="subgraph",
        frontmatter={},
        raw_blocks={},
        ast=phase_ast,
    )
    parent_flow = FrameworkState(
        subagent_depth=1,
        working_memory={"parent_only": True},
    )

    node = _build_subgraph_node(
        phase_doc,
        phase_ast,
        chat_model=None,
        max_patch_attempts=1,
        skill_resolver=SimpleNamespace(resolve_skill=lambda skill_id: tmp_path),
    )
    result = node(
        WorkflowState(
            data=BusinessData.model_validate({"public": "visible"}),
            flow=parent_flow,
            messages=[],
        )
    )

    assert parent_flow.subagent_depth == 1
    assert parent_flow.working_memory == {"parent_only": True}
    assert result["flow"].working_memory["child_only"] is True


def test_phase_wrapper_rejects_double_wrap() -> None:
    mapper = StateMapper(phase_id="logic")

    def node(state):
        return {"data": {"answer": "ok"}}

    wrapped = PhaseWrapper(mapper, node_kind="logic").wrap(node)

    with pytest.raises(GraphAgentFatalError, match="double-wrap"):
        PhaseWrapper(mapper, node_kind="logic").wrap(wrapped)
