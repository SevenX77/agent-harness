"""A graph can be told which phases to stop before, and continue past them.

Design: run-execution/mvp1-alignment.md F10 + RUN_EXECUTION-16. The stop is
LangGraph's compile-time ``interrupt_before`` rather than a check inside each
phase: a breakpoint is an outside observation, and one that each phase had to
consult would change the code path of the thing being observed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph

from ..ws_e4_runtime_skills import _write_graph, write_logic_phase


def _write_two_phase_skill(root: Path) -> None:
    _write_graph(
        root,
        name="stop-before-phase",
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
        inputs={"items": {"type": "array"}},
        outputs={"seen": {"type": "array"}},
        required=["items"],
        action_body="""
            def collect(inputs):
                return {"seen": list(inputs["items"])}
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


def _initial_state(run_id: str) -> dict[str, Any]:
    return {
        "data": {"inputs": {"items": ["a", "b", "c"]}},
        "flow": {"run_id": run_id, "thread_id": run_id},
        "messages": [],
    }


def test_a_named_phase_stops_the_graph_before_it_runs(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _write_two_phase_skill(tmp_path)
    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(
        compiled,
        skill_resolver=mock_skill_resolver,
        checkpointer=InMemorySaver(),
        pause_before=frozenset({"summarize"}),
    ).graph

    config = {"configurable": {"thread_id": "run-stop-1"}}
    graph.invoke(_initial_state("run-stop-1"), config=config)
    state = graph.get_state(config)

    # `next` names what it is ABOUT to run, so the phase has not run yet.
    assert state.next == ("summarize",)
    # A static stop leaves no interrupt payload — which is exactly how it stays
    # distinguishable from a phase that stopped to ask a human something.
    assert state.interrupts == ()


def test_the_run_goes_on_when_it_is_invoked_again(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _write_two_phase_skill(tmp_path)
    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(
        compiled,
        skill_resolver=mock_skill_resolver,
        checkpointer=InMemorySaver(),
        pause_before=frozenset({"summarize"}),
    ).graph

    config = {"configurable": {"thread_id": "run-stop-2"}}
    graph.invoke(_initial_state("run-stop-2"), config=config)
    graph.invoke(None, config=config)

    assert graph.get_state(config).next == ()


def _write_graph_level_iterate_skill(root: Path) -> None:
    """A skill whose WHOLE graph runs once per item (`iterate` on GRAPH.md)."""
    schema = json.dumps(
        {"type": "object", "properties": {"items": {"type": "array"}}},
        ensure_ascii=False,
        indent=4,
    ).replace("\n", "\n    ")
    outputs = json.dumps(
        {"type": "object", "properties": {"doubled": {"type": "array"}}},
        ensure_ascii=False,
        indent=4,
    ).replace("\n", "\n    ")
    (root / "GRAPH.md").write_text(
        f"""---
schema_version: "v0.3.0"
name: stop-before-in-an-iterating-graph
io:
  inputs:
    {schema}
  outputs:
    {outputs}
phases:
  - worker
iterate:
  mode: batch
  over: items
  item_var: item
  concurrency: 2
---
<phase depends_on="input" output>worker</phase>
""",
        encoding="utf-8",
    )
    write_logic_phase(
        root,
        "worker",
        inputs={"item": {"type": "number"}},
        outputs={"doubled": {"type": "number"}},
        required=["item"],
        action_body="""
            def worker(inputs):
                return {"doubled": inputs["item"] * 2}
        """,
    )


def test_a_graph_that_iterates_refuses_a_stopping_point(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    """The whole graph reruns per item, and the iterate wrapper drives those
    rounds itself — so a stop inside one round could neither be reported nor
    resumed from outside. Say no out loud rather than accept a breakpoint that
    would never fire."""
    _write_graph_level_iterate_skill(tmp_path)
    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    with pytest.raises(ValueError, match="iterates over its whole graph"):
        assemble_graph(
            compiled,
            skill_resolver=mock_skill_resolver,
            checkpointer=InMemorySaver(),
            pause_before=frozenset({"worker"}),
        )


def test_an_iterating_graph_is_still_assembled_when_nothing_asked_it_to_stop(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _write_graph_level_iterate_skill(tmp_path)
    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    assert assemble_graph(compiled, skill_resolver=mock_skill_resolver).graph is not None


def test_naming_no_phase_leaves_the_graph_running_straight_through(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _write_two_phase_skill(tmp_path)
    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(
        compiled,
        skill_resolver=mock_skill_resolver,
        checkpointer=InMemorySaver(),
    ).graph

    config = {"configurable": {"thread_id": "run-stop-3"}}
    graph.invoke(_initial_state("run-stop-3"), config=config)

    assert graph.get_state(config).next == ()
