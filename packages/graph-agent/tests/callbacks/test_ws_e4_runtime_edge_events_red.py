"""RED tests for WS-E4 runtime edge event emission."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any

from graph_agent.callbacks.emit import _CompositeEventSink, _SubscriberSink, _TraceJsonlSink
from graph_agent.callbacks.events import (
    BlackboardReduceEvent,
    InputDispatchEvent,
    InputFileInjectedEvent,
)
from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.runner import run_skill


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
    return data.model_dump() if hasattr(data, "model_dump") else dict(data)


def _event_sink(trace_dir: Path, events: list[object]) -> _CompositeEventSink:
    return _CompositeEventSink(
        [
            _TraceJsonlSink(trace_dir),
            _SubscriberSink(events.append),
        ]
    )


def _invoke(
    root: Path,
    mock_skill_resolver: object,
    inputs: dict[str, Any],
    *,
    callbacks: object | None = None,
) -> dict[str, Any]:
    compiled = compile_skill(root, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(
        compiled,
        callbacks=callbacks,
        skill_resolver=mock_skill_resolver,
    ).graph
    return graph.invoke(
        {
            "data": {"inputs": inputs},
            "flow": {"run_id": "run-ws-e4", "thread_id": "thread-ws-e4"},
            "messages": [],
        }
    )


def _serial_two_phase_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e4-runtime-serial
io:
  inputs:
    {_schema_yaml({"source": {"type": "string"}}, required=["source"])}
  outputs:
    {_schema_yaml({"answer": {"type": "string"}})}
phases:
  - prepare
  - finish
---
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare" output>finish</phase>
""",
    )
    _write_logic_phase(
        root,
        "prepare",
        inputs={"source": {"type": "string"}},
        outputs={"prepared": {"type": "string"}},
        required=["source"],
        action_body="""
            def prepare(context):
                return {"prepared": f"{context['source']}:prepared"}
        """,
    )
    _write_logic_phase(
        root,
        "finish",
        inputs={"prepared": {"type": "string"}},
        outputs={"answer": {"type": "string"}},
        required=["prepared"],
        action_body="""
            def finish(context):
                return {"answer": f"{context['prepared']}:done"}
        """,
    )


def _loop_accumulate_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e4-runtime-loop-reduce
io:
  inputs:
    {_schema_yaml({"items": {"type": "array"}})}
  outputs:
    {_schema_yaml({"collected": {"type": "array"}})}
phases:
  - collect
---
<phase depends_on="input" output>collect</phase>
""",
    )
    _write_logic_phase(
        root,
        "collect",
        inputs={"item": {}, "collected": {}},
        outputs={"piece": {}},
        required=["item", "collected"],
        iterate="""
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
            def collect(context):
                return {"piece": context["item"]}
        """,
    )


def _batch_iterate_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e4-runtime-batch-dispatch
io:
  inputs:
    {_schema_yaml({"items": {"type": "array"}})}
  outputs:
    {_schema_yaml({"seen": {"type": "array"}})}
phases:
  - worker
---
<phase depends_on="input" output>worker</phase>
""",
    )
    _write_logic_phase(
        root,
        "worker",
        inputs={"item": {}},
        outputs={"seen": {}},
        required=["item"],
        iterate="""
iterate:
  mode: batch
  over: data.inputs.items
  item_var: item
  concurrency: 2
""",
        action_body="""
            def worker(context):
                return {"seen": context["item"]}
        """,
    )


def _file_input_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e4-runtime-file-input
io:
  inputs:
    {_schema_yaml({"title": {"type": "string"}}, required=["title"])}
  outputs:
    {_schema_yaml({"answer": {"type": "string"}})}
phases:
  - reader
---
<phase depends_on="input" output>reader</phase>
""",
    )
    _write_logic_phase(
        root,
        "reader",
        inputs={
            "title": {"type": "string"},
            "body": {
                "type": "string",
                "source": "file",
                "path": "inputs/body.md",
            },
        },
        outputs={"answer": {"type": "string"}},
        required=["title", "body"],
        action_body="""
            def reader(context):
                return {"answer": f"{context['title']}::{context['body']}"}
        """,
    )


def _write_logic_phase(
    root: Path,
    phase_id: str,
    *,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    action_body: str,
    required: list[str] | None = None,
    iterate: str | None = None,
) -> None:
    iterate_block = f"{iterate.rstrip()}\n" if iterate else ""
    _write(
        root / "phases" / phase_id / "LOGIC.md",
        f"""---
io:
  inputs:
    {_schema_yaml(inputs, required=required)}
  outputs:
    {_schema_yaml(outputs)}
actions: [{phase_id}]
validator: false
{iterate_block}---
<action>{phase_id}</action>
""",
    )
    _write(
        root / "phases" / phase_id / "actions" / f"{phase_id}.py",
        dedent(action_body).lstrip(),
    )


def test_serial_graph_emits_input_dispatch_for_each_phase_before_execution(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _serial_two_phase_skill(tmp_path)
    events: list[object] = []
    sink = _event_sink(tmp_path / "trace", events)

    result = _invoke(
        tmp_path,
        mock_skill_resolver,
        {"source": "seed"},
        callbacks=sink,
    )

    assert _business_data(result)["answer"] == "seed:prepared:done"
    dispatches = [event for event in events if isinstance(event, InputDispatchEvent)]
    assert [event.to_phase for event in dispatches] == ["prepare", "finish"]

    first, second = dispatches
    assert first.from_phase is None
    assert first.dispatched_keys == ["source"]
    assert first.changed_keys == ["source"]
    assert first.branch_index is None
    assert first.blackboard_snapshot["source"] == "seed"

    assert second.from_phase == "prepare"
    assert second.dispatched_keys == ["prepared"]
    assert second.changed_keys == ["prepared"]
    assert second.branch_index is None
    assert second.blackboard_snapshot["prepared"] == "seed:prepared"


def test_batch_iterate_emits_input_dispatch_for_each_branch_with_stable_branch_index(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _batch_iterate_skill(tmp_path)
    events: list[object] = []
    sink = _event_sink(tmp_path / "trace", events)

    result = _invoke(
        tmp_path,
        mock_skill_resolver,
        {"items": ["a", "b", "c"]},
        callbacks=sink,
    )

    assert _business_data(result)["seen"] == ["a", "b", "c"]
    dispatches = [
        event
        for event in events
        if isinstance(event, InputDispatchEvent) and event.to_phase == "worker"
    ]
    assert [event.branch_index for event in dispatches] == [1, 2, 3]
    assert [event.dispatched_keys for event in dispatches] == [["item"], ["item"], ["item"]]
    assert [event.changed_keys for event in dispatches] == [["item"], ["item"], ["item"]]
    assert [event.blackboard_snapshot["item"] for event in dispatches] == ["a", "b", "c"]


def test_loop_accumulate_emits_blackboard_reduce_after_each_declared_merge(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _loop_accumulate_skill(tmp_path)
    events: list[object] = []
    sink = _event_sink(tmp_path / "trace", events)

    result = _invoke(
        tmp_path,
        mock_skill_resolver,
        {"items": ["a", "b", "c"]},
        callbacks=sink,
    )

    assert _business_data(result)["collected"] == ["a", "b", "c"]
    reductions = [event for event in events if isinstance(event, BlackboardReduceEvent)]
    assert [event.to_phase for event in reductions] == ["collect", "collect", "collect"]
    assert [event.reducer for event in reductions] == ["append", "append", "append"]
    assert [event.changed_keys for event in reductions] == [
        ["collected"],
        ["collected"],
        ["collected"],
    ]
    assert [event.blackboard_snapshot["collected"] for event in reductions] == [
        ["a"],
        ["a", "b"],
        ["a", "b", "c"],
    ]


def test_input_file_injected_event_emits_before_dispatch_for_runtime_file_input(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    events: list[object] = []
    _write(workspace_dir / "inputs" / "body.md", "Imported body.")
    _file_input_skill(skill_root)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id="ws-e4-runtime-file-input",
        event_subscriber=events.append,
        skill_resolver=mock_skill_resolver,
        title="Runtime IO",
    )

    assert result.success is True
    assert result.context["answer"] == "Runtime IO::Imported body."
    injected = [event for event in events if isinstance(event, InputFileInjectedEvent)]
    dispatches = [
        event
        for event in events
        if isinstance(event, InputDispatchEvent) and event.to_phase == "reader"
    ]
    assert len(injected) == 1
    assert len(dispatches) == 1

    file_event = injected[0]
    dispatch_event = dispatches[0]
    assert events.index(file_event) < events.index(dispatch_event)
    assert file_event.to_phase == "reader"
    assert file_event.changed_keys == ["body"]
    assert file_event.file_ref == "inputs/body.md"
    assert file_event.target_field == "body"
    assert file_event.blackboard_snapshot["body"] == "Imported body."
    assert set(dispatch_event.dispatched_keys) == {"title", "body"}
    assert dispatch_event.blackboard_snapshot["body"] == "Imported body."
