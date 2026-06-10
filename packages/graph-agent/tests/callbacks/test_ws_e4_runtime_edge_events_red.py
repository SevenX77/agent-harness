"""RED tests for WS-E4 runtime edge event emission."""

from __future__ import annotations

from pathlib import Path
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
from tests.ws_e4_runtime_skills import (
    write_batch_iterate_skill,
    write_file_input_skill,
    write_loop_accumulate_skill,
    write_serial_two_phase_skill,
)


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


def test_serial_graph_emits_input_dispatch_for_each_phase_before_execution(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    write_serial_two_phase_skill(tmp_path)
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
    write_batch_iterate_skill(tmp_path)
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
    write_loop_accumulate_skill(tmp_path)
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
    input_path = workspace_dir / "inputs" / "body.md"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text("Imported body.", encoding="utf-8")
    write_file_input_skill(skill_root)

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
