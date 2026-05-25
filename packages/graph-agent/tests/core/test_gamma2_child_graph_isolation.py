from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.graph_assembler import _invoke_subagent_once_t23, assemble_graph
from graph_agent.runtime.state_mapper import PhaseWrapper, StateMapper


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _base(root: Path, phases: str, outputs: dict[str, object] | None = None) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "2.1"
name: gamma2-child
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
"""
        + phases,
    )
    _write(root / "io" / "inputs.json", "{}\n")
    _write(root / "io" / "outputs.json", json.dumps(outputs or {}, ensure_ascii=False))


def _logic_action(root: Path, phase: str, action: str, body: str) -> None:
    _write(
        root / "phases" / phase / "LOGIC.md",
        f"""---
mode: logic
---
<python_callable>
{action}
</python_callable>
""",
    )
    _write(root / "phases" / phase / "actions" / f"{action}.py", body)


def _subgraph(root: Path, phase: str, ref: str = "child") -> None:
    _write(
        root / "phases" / phase / "SUBGRAPH.md",
        f"""---
mode: subgraph
target_skill: {ref}
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


def test_subgraph_child_starts_from_explicit_inputs_only(tmp_path: Path) -> None:
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

    result = assemble_graph(compile_skill(tmp_path, cache=False)).graph.invoke(
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


def test_subgraph_child_outputs_are_deterministic_across_child_phases(tmp_path: Path) -> None:
    _base(tmp_path, '<phase id="sub" src="phases/sub" depends_on="" />\n')
    _subgraph(tmp_path, "sub")
    child = tmp_path / "phases" / "sub" / "child"
    _base(
        child,
        '<phase id="first" src="phases/first" depends_on="" />\n'
        '<phase id="second" src="phases/second" depends_on="first" />\n',
    )
    _logic_action(child, "first", "first", "def first(context):\n    return {'seen_public': 'a'}\n")
    _logic_action(
        child,
        "second",
        "second",
        "def second(context):\n"
        "    return {'saw_parent_secret': False, 'saw_parent_message': False}\n",
    )

    result = assemble_graph(compile_skill(tmp_path, cache=False)).graph.invoke(
        {"data": {"inputs": {"public": "ok"}}, "flow": {}, "messages": [], "run_id": "r1"}
    )

    assert result["data"]["phase_outputs"]["sub"] == {
        "seen_public": "a",
        "saw_parent_secret": False,
        "saw_parent_message": False,
    }


def test_subagent_child_without_phase_outputs_does_not_flat_diff_parent_data() -> None:
    class FlatOnlyGraph:
        def invoke(self, state, config=None):
            del config
            return {
                "data": {
                    "inputs": {**state["data"]["inputs"], "legacy": "must-not-leak"},
                    "phase_outputs": {},
                    "scratch": {},
                },
                "flow": state["flow"],
                "messages": [],
            }

    result = _invoke_subagent_once_t23(
        SimpleNamespace(graph=FlatOnlyGraph()),
        {"data": {"inputs": {"item": "a"}}, "flow": {}, "messages": [], "run_id": "parent"},
        {"item": "a"},
    )

    assert result["data"] == {}


def test_phase_wrapper_rejects_double_wrap() -> None:
    mapper = StateMapper(phase_id="logic")

    def node(state):
        return {"data": {"answer": "ok"}}

    wrapped = PhaseWrapper(mapper, node_kind="logic").wrap(node)

    with pytest.raises(GraphAgentFatalError, match="double-wrap"):
        PhaseWrapper(mapper, node_kind="logic").wrap(wrapped)
