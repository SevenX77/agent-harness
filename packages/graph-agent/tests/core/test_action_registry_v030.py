from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.actions import ActionRegistry
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.graph_assembler import assemble_graph


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _logic_skill(root: Path, action_name: str, action_body: str) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: action-registry
io:
  inputs:
    type: object
    properties:
      foo:
        type: integer
  outputs:
    type: object
    properties:
      foo:
        type: integer
phases:
  - logic
---
<phase depends_on="input" output>logic</phase>
""",
    )
    _write(
        root / "phases" / "logic" / "LOGIC.md",
        f"""---
io:
  inputs:
    type: object
    properties:
      foo:
        type: integer
  outputs:
    type: object
    properties:
      foo:
        type: integer
---
<action>{action_name}</action>
""",
    )
    _write(root / "phases" / "logic" / "actions" / "write_value.py", action_body)


@pytest.mark.parametrize(
    "name",
    ["../escape", "nested/action", r"nested\\action", ".", "..", "/absolute", "pkg.module"],
)
def test_action_registry_rejects_non_primary_action_names(name: str) -> None:
    registry = ActionRegistry.empty()

    with pytest.raises(GraphAgentFatalError) as exc_info:
        registry.resolve("logic", name)
    assert exc_info.value.payload.code == "[F-v3-logic-action-name-invalid]"


def test_runtime_dynamic_return_key_must_use_v030_output_field_error(tmp_path: Path) -> None:
    _logic_skill(
        tmp_path,
        "write_value",
        "def write_value(context):\n    key = 'missing'\n    return {key: 1}\n",
    )
    graph = assemble_graph(compile_skill(tmp_path, cache=False)).graph

    with pytest.raises(GraphAgentFatalError) as exc_info:
        graph.invoke({"data": {"inputs": {"foo": 1}}, "flow": {}, "messages": [], "run_id": "r1"})
    assert exc_info.value.payload.code == "[F-v3-logic-output-field-undeclared]"
    assert "missing" in str(exc_info.value)


def test_action_returning_non_dict_is_runtime_fatal(tmp_path: Path) -> None:
    _logic_skill(
        tmp_path,
        "write_value",
        "def write_value(context):\n    return ['not', 'a', 'dict']\n",
    )
    graph = assemble_graph(compile_skill(tmp_path, cache=False)).graph

    with pytest.raises(GraphAgentFatalError) as exc_info:
        graph.invoke({"data": {"inputs": {"foo": 1}}, "flow": {}, "messages": [], "run_id": "r1"})
    assert exc_info.value.payload.code == "[F-v3-logic-action-return-invalid]"


def test_ctx_data_mutation_key_must_be_declared_and_not_written(tmp_path: Path) -> None:
    _logic_skill(
        tmp_path,
        "write_value",
        "def write_value(context):\n    context.set('missing', 1)\n    return {'foo': 2}\n",
    )
    graph = assemble_graph(compile_skill(tmp_path, cache=False)).graph

    with pytest.raises(GraphAgentFatalError) as exc_info:
        graph.invoke({"data": {"inputs": {"foo": 1}}, "flow": {}, "messages": [], "run_id": "r1"})
    assert exc_info.value.payload.code == "[F-v3-logic-output-field-undeclared]"
    assert "missing" in str(exc_info.value)
