"""RED tests for WS-E1 Step4 declarative iterate runtime contracts."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentError
from graph_agent.core.graph_assembler import assemble_graph


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _schema_yaml(properties: dict[str, Any], *, required: list[str] | None = None) -> str:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required is not None:
        schema["required"] = required
    return json.dumps(schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _business_data(result: dict[str, Any]) -> dict[str, Any]:
    data = result["data"]
    if hasattr(data, "model_dump"):
        return data.model_dump()
    return dict(data)


def _invoke(root: Path, mock_skill_resolver: object, inputs: dict[str, Any]) -> dict[str, Any]:
    compiled = compile_skill(root, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(compiled, skill_resolver=mock_skill_resolver).graph
    return graph.invoke({"data": {"inputs": inputs}, "flow": {}, "messages": [], "run_id": "r1"})


def _logic_skill(
    root: Path,
    *,
    graph_inputs: dict[str, Any],
    graph_outputs: dict[str, Any],
    phase_inputs: dict[str, Any],
    phase_outputs: dict[str, Any],
    action_body: str,
    phase_iterate: str | None = None,
    graph_iterate: str | None = None,
    graph_required: list[str] | None = None,
    phase_required: list[str] | None = None,
) -> None:
    graph_input_yaml = _schema_yaml(graph_inputs, required=graph_required)
    graph_output_yaml = _schema_yaml(graph_outputs)
    phase_input_yaml = _schema_yaml(phase_inputs, required=phase_required)
    phase_output_yaml = _schema_yaml(phase_outputs)
    graph_iterate_block = f"{graph_iterate.rstrip()}\n" if graph_iterate else ""
    phase_iterate_block = f"{phase_iterate.rstrip()}\n" if phase_iterate else ""

    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e1-step4-iterate-red
io:
  inputs:
    {graph_input_yaml}
  outputs:
    {graph_output_yaml}
phases:
  - worker
{graph_iterate_block}---
<phase depends_on="input" output>worker</phase>
""",
    )
    _write(
        root / "phases" / "worker" / "LOGIC.md",
        f"""---
io:
  inputs:
    {phase_input_yaml}
  outputs:
    {phase_output_yaml}
actions: [worker]
validator: false
{phase_iterate_block}---
<action>worker</action>
""",
    )
    _write(
        root / "phases" / "worker" / "actions" / "worker.py",
        dedent(action_body).lstrip(),
    )


def test_legacy_batch_field_remains_supported_while_iterate_becomes_primary(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _logic_skill(
        tmp_path,
        graph_inputs={"items": {"type": "array", "items": {"type": "string"}}},
        graph_outputs={
            "seen": {"type": "array", "items": {"type": "string"}},
            "batch_outputs": {"type": "array"},
        },
        phase_inputs={
            "items": {"type": "array", "items": {"type": "string"}},
            "item": {"type": "string"},
        },
        phase_outputs={
            "seen": {"type": "array", "items": {"type": "string"}},
            "batch_outputs": {"type": "array"},
        },
        phase_iterate="""
batch:
  iterator: data.items
  item_var: item
  concurrency: 2
""",
        action_body="""
            def worker(context):
                return {"seen": context["item"]}
        """,
    )

    result = _invoke(tmp_path, mock_skill_resolver, {"items": ["a", "b", "c"]})

    assert _business_data(result)["seen"] == ["a", "b", "c"]


def test_node_batch_iterate_one_based_closed_range_runs_selected_items_and_aggregates_outputs(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _logic_skill(
        tmp_path,
        graph_inputs={"items": {"type": "array", "items": {"type": "string"}}},
        graph_outputs={"seen": {"type": "array", "items": {"type": "string"}}},
        phase_inputs={"item": {"type": "string"}},
        phase_outputs={"seen": {"type": "string"}},
        phase_iterate="""
iterate:
  mode: batch
  over: data.inputs.items
  item_var: item
  range: [2, 3]
  concurrency: 2
""",
        action_body="""
            def worker(context):
                return {"seen": context["item"]}
        """,
    )

    result = _invoke(tmp_path, mock_skill_resolver, {"items": ["a", "b", "c", "d"]})

    assert _business_data(result)["seen"] == ["b", "c"]
    assert _business_data(result)["phase_outputs"]["worker"] == {"seen": ["b", "c"]}


@pytest.mark.parametrize(
    ("merge", "items", "init_value", "action_body", "expected"),
    [
        (
            "append",
            ["a", "b", "c"],
            [],
            """
            def worker(context):
                assert isinstance(context, dict)
                return {"piece": context["item"]}
            """,
            ["a", "b", "c"],
        ),
        (
            "extend",
            ["a", "b", "c"],
            [],
            """
            def worker(context):
                assert isinstance(context, dict)
                return {"piece": [context["item"]]}
            """,
            ["a", "b", "c"],
        ),
        (
            "merge",
            [{"key": "a", "value": 1}, {"key": "b", "value": 2}],
            {},
            """
            def worker(context):
                item = context["item"]
                return {"piece": {item["key"]: item["value"]}}
            """,
            {"a": 1, "b": 2},
        ),
        (
            "replace",
            ["draft", "final"],
            "",
            """
            def worker(context):
                return {"piece": context["item"]}
            """,
            "final",
        ),
    ],
)
def test_node_loop_iterate_accumulates_serially_with_declared_merge_mode(
    tmp_path: Path,
    mock_skill_resolver: object,
    merge: str,
    items: list[Any],
    init_value: Any,
    action_body: str,
    expected: Any,
) -> None:
    _logic_skill(
        tmp_path,
        graph_inputs={"items": {"type": "array"}},
        graph_outputs={"collected": {}},
        phase_inputs={"item": {}, "collected": {}},
        phase_outputs={"piece": {}},
        phase_required=["item", "collected"],
        phase_iterate=f"""
iterate:
  mode: loop
  over: data.inputs.items
  item_var: item
  accumulate:
    var: collected
    init: {json.dumps(init_value)}
    from: piece
    merge: {merge}
""",
        action_body=action_body,
    )

    result = _invoke(tmp_path, mock_skill_resolver, {"items": items})

    assert _business_data(result)["collected"] == expected
    assert _business_data(result)["phase_outputs"]["worker"] == {"collected": expected}


def test_node_loop_iterate_next_iteration_reads_previous_accumulator_value(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _logic_skill(
        tmp_path,
        graph_inputs={"items": {"type": "array"}},
        graph_outputs={"collected": {"type": "array"}},
        phase_inputs={"item": {}, "collected": {}},
        phase_outputs={"piece": {}},
        phase_required=["item", "collected"],
        phase_iterate="""
iterate:
  mode: loop
  over: data.inputs.items
  item_var: item
  accumulate:
    var: collected
    init: []
    from: piece
    merge: replace
""",
        action_body="""
            def worker(context):
                assert isinstance(context, dict)
                previous = list(context["collected"])
                return {"piece": previous + [context["item"]]}
        """,
    )

    result = _invoke(tmp_path, mock_skill_resolver, {"items": ["a", "b", "c"]})

    assert _business_data(result)["collected"] == ["a", "b", "c"]
    assert _business_data(result)["phase_outputs"]["worker"] == {"collected": ["a", "b", "c"]}


@pytest.mark.parametrize(
    ("phase_inputs", "phase_required", "missing_name"),
    [
        (
            {"collected": {"type": "array"}},
            ["collected"],
            "item",
        ),
        (
            {"item": {"type": "string"}},
            ["item"],
            "collected",
        ),
    ],
)
def test_loop_iterate_requires_item_and_accumulator_in_phase_inputs(
    tmp_path: Path,
    mock_skill_resolver: object,
    phase_inputs: dict[str, Any],
    phase_required: list[str],
    missing_name: str,
) -> None:
    _logic_skill(
        tmp_path,
        graph_inputs={"items": {"type": "array", "items": {"type": "string"}}},
        graph_outputs={"collected": {"type": "array"}},
        phase_inputs=phase_inputs,
        phase_outputs={"piece": {"type": "string"}},
        phase_required=phase_required,
        phase_iterate="""
iterate:
  mode: loop
  over: data.inputs.items
  item_var: item
  accumulate:
    var: collected
    init: []
    from: piece
    merge: append
""",
        action_body="""
            def worker(context):
                return {"piece": context["item"]}
        """,
    )

    with pytest.raises(GraphAgentError) as exc_info:
        compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    assert exc_info.value.payload.code == "[F-v3-iterate-accumulate-fields-missing]"
    assert missing_name in str(exc_info.value)


def test_iterate_over_must_resolve_to_list_at_runtime(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _logic_skill(
        tmp_path,
        graph_inputs={"title": {"type": "string"}},
        graph_outputs={"seen": {"type": "array"}},
        phase_inputs={"item": {"type": "string"}},
        phase_outputs={"seen": {"type": "string"}},
        phase_iterate="""
iterate:
  mode: batch
  over: data.inputs.title
  item_var: item
""",
        action_body="""
            def worker(context):
                return {"seen": context["item"]}
        """,
    )

    with pytest.raises(GraphAgentError) as exc_info:
        _invoke(tmp_path, mock_skill_resolver, {"title": "not-a-list"})

    assert exc_info.value.payload.code == "[F-v3-iterate-over-not-list]"
    assert "data.inputs.title" in str(exc_info.value)


def test_node_batch_iterate_empty_list_returns_empty_aggregate_without_calling_action(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _logic_skill(
        tmp_path,
        graph_inputs={"items": {"type": "array", "items": {"type": "string"}}},
        graph_outputs={"seen": {"type": "array", "items": {"type": "string"}}},
        phase_inputs={"item": {"type": "string"}},
        phase_outputs={"seen": {"type": "string"}},
        phase_iterate="""
iterate:
  mode: batch
  over: data.inputs.items
  item_var: item
""",
        action_body="""
            def worker(context):
                raise AssertionError("batch body must not run for an empty iterate list")
        """,
    )

    result = _invoke(tmp_path, mock_skill_resolver, {"items": []})

    assert _business_data(result)["seen"] == []
    assert _business_data(result)["phase_outputs"]["worker"] == {"seen": []}


def test_node_loop_iterate_empty_list_returns_accumulate_init_without_calling_action(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _logic_skill(
        tmp_path,
        graph_inputs={"items": {"type": "array", "items": {"type": "string"}}},
        graph_outputs={"collected": {"type": "array", "items": {"type": "string"}}},
        phase_inputs={"item": {"type": "string"}, "collected": {"type": "array"}},
        phase_outputs={"piece": {"type": "array"}},
        phase_required=["item", "collected"],
        phase_iterate="""
iterate:
  mode: loop
  over: data.inputs.items
  item_var: item
  accumulate:
    var: collected
    init: ["seed"]
    from: piece
    merge: replace
""",
        action_body="""
            def worker(context):
                raise AssertionError("loop body must not run for an empty iterate list")
        """,
    )

    result = _invoke(tmp_path, mock_skill_resolver, {"items": []})

    assert _business_data(result)["collected"] == ["seed"]
    assert _business_data(result)["phase_outputs"]["worker"] == {"collected": ["seed"]}


def test_graph_level_batch_iterate_runs_the_whole_dag_inside_one_graph_invoke(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _logic_skill(
        tmp_path,
        graph_inputs={"items": {"type": "array", "items": {"type": "integer"}}},
        graph_outputs={"doubled": {"type": "array", "items": {"type": "integer"}}},
        phase_inputs={"item": {"type": "integer"}},
        phase_outputs={"doubled": {"type": "integer"}},
        graph_iterate="""
iterate:
  mode: batch
  over: data.inputs.items
  item_var: item
  concurrency: 2
""",
        action_body="""
            def worker(context):
                return {"doubled": context["item"] * 2}
        """,
    )

    result = _invoke(tmp_path, mock_skill_resolver, {"items": [1, 2, 3]})

    assert _business_data(result)["doubled"] == [2, 4, 6]
    assert _business_data(result)["phase_outputs"]["worker"] == {"doubled": [2, 4, 6]}


def test_graph_level_loop_iterate_is_one_thread_loop_body_not_test_side_reinvoke(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _logic_skill(
        tmp_path,
        graph_inputs={
            "rounds": {"type": "array", "items": {"type": "integer"}},
        },
        graph_outputs={"count": {"type": "integer"}},
        phase_inputs={
            "count": {"type": "integer"},
            "round": {"type": "integer"},
        },
        phase_outputs={"count": {"type": "integer"}},
        graph_iterate="""
iterate:
  mode: loop
  over: data.inputs.rounds
  item_var: round
  accumulate:
    var: count
    init: 0
    from: count
    merge: replace
""",
        action_body="""
            def worker(context):
                assert isinstance(context, dict)
                return {"count": context["count"] + context["round"]}
        """,
    )

    result = _invoke(tmp_path, mock_skill_resolver, {"rounds": [1, 2, 3]})

    assert _business_data(result)["count"] == 6
    assert _business_data(result)["phase_outputs"]["worker"] == {"count": 6}
