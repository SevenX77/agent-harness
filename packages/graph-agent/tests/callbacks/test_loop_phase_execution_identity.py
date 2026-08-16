"""A loop phase must name its execution to the transitions leaving it.

`from_phase_execution_ids` exists so a downstream transition can say WHICH
upstream execution it carries state out of (decision 2026-08-15
edge-as-first-class-run-segment, D3). A loop phase returns a channel delta
built by `_phase_outputs_delta`, which carries only `data` — so the execution
identity the state mapper records never reached the graph state, and the one
topology the plural field was designed for reported an empty list.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_agent.callbacks.emit import _CompositeEventSink, _SubscriberSink
from graph_agent.callbacks.events import EdgeStartEvent, PhaseStartEvent
from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph

from ..ws_e4_runtime_skills import _write_graph, write_logic_phase


def _write_loop_then_summarize_skill(root: Path) -> None:
    """A loop phase feeding a plain downstream phase — the demo-loop shape."""
    _write_graph(
        root,
        name="loop-execution-identity",
        inputs={"items": {"type": "array"}},
        outputs={"total": {"type": "number"}},
        phases=["collect", "summarize"],
        phase_edges=(
            '<phase depends_on="input">collect</phase>\n'
            '<phase depends_on="collect" output>summarize</phase>'
        ),
        required_inputs=["items"],
    )
    write_logic_phase(
        root,
        "collect",
        inputs={"item": {}, "collected": {}},
        outputs={"piece": {}},
        required=["item", "collected"],
        iterate="""
iterate:
  mode: loop
  over: items
  item_var: item
  accumulate:
    var: collected
    init: []
    from: piece
    merge: append
""",
        action_body="""
            def collect(inputs):
                return {"piece": inputs["item"]}
        """,
    )
    write_logic_phase(
        root,
        "summarize",
        inputs={"collected": {"type": "array"}},
        outputs={"total": {"type": "number"}},
        required=["collected"],
        action_body="""
            def summarize(inputs):
                return {"total": len(inputs["collected"])}
        """,
    )


def _write_batch_then_summarize_skill(root: Path) -> None:
    """The batch twin of the shape above — items run concurrently, not in rounds."""
    _write_graph(
        root,
        name="batch-execution-identity",
        inputs={"items": {"type": "array"}},
        outputs={"total": {"type": "number"}},
        phases=["worker", "summarize"],
        phase_edges=(
            '<phase depends_on="input">worker</phase>\n'
            '<phase depends_on="worker" output>summarize</phase>'
        ),
        required_inputs=["items"],
    )
    write_logic_phase(
        root,
        "worker",
        inputs={"item": {}},
        outputs={"seen": {"type": "array"}},
        required=["item"],
        iterate="""
iterate:
  mode: batch
  over: items
  item_var: item
""",
        action_body="""
            def worker(inputs):
                return {"seen": [inputs["item"]]}
        """,
    )
    write_logic_phase(
        root,
        "summarize",
        inputs={"seen": {"type": "array"}},
        outputs={"total": {"type": "number"}},
        required=["seen"],
        action_body="""
            def summarize(inputs):
                return {"total": len(inputs["seen"])}
        """,
    )


def test_transition_out_of_a_batch_phase_names_every_item_execution(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _write_batch_then_summarize_skill(tmp_path)
    events: list[Any] = []
    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(
        compiled,
        callbacks=_CompositeEventSink([_SubscriberSink(events.append)]),
        skill_resolver=mock_skill_resolver,
    ).graph

    graph.invoke(
        {
            "data": {"inputs": {"items": ["a", "b", "c"]}},
            "flow": {"run_id": "run-batch-identity", "thread_id": "thread-batch-identity"},
            "messages": [],
        }
    )

    worker_executions = {
        event.phase_execution_id
        for event in events
        if isinstance(event, PhaseStartEvent) and event.phase_name == "worker"
    }
    assert len(worker_executions) == 3

    into_summarize = [
        event
        for event in events
        if isinstance(event, EdgeStartEvent) and event.to_phase == "summarize"
    ]
    assert len(into_summarize) == 1
    # A set, not a list: items fan out concurrently, so arrival order is not
    # part of the guarantee — that every item's execution is named is.
    assert set(into_summarize[0].from_phase_execution_ids) == worker_executions


def test_transition_out_of_a_loop_phase_names_the_execution_it_left(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _write_loop_then_summarize_skill(tmp_path)
    events: list[Any] = []
    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(
        compiled,
        callbacks=_CompositeEventSink([_SubscriberSink(events.append)]),
        skill_resolver=mock_skill_resolver,
    ).graph

    graph.invoke(
        {
            "data": {"inputs": {"items": ["a", "b", "c"]}},
            "flow": {"run_id": "run-loop-identity", "thread_id": "thread-loop-identity"},
            "messages": [],
        }
    )

    collect_executions = [
        event.phase_execution_id
        for event in events
        if isinstance(event, PhaseStartEvent) and event.phase_name == "collect"
    ]
    assert len(collect_executions) == 3, "one execution per loop round"

    into_summarize = [
        event
        for event in events
        if isinstance(event, EdgeStartEvent) and event.to_phase == "summarize"
    ]
    assert len(into_summarize) == 1
    transition = into_summarize[0]
    assert transition.from_phases == ["collect"]
    # The accumulated output this transition carries is the join of every round,
    # so it names every round — the same reason the field is plural for fan-in
    # (D3). Naming only the last round would report a real execution while
    # silently dropping its peers; naming none at all was the shipped defect.
    assert transition.from_phase_execution_ids == collect_executions
