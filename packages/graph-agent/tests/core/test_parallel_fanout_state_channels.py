"""Parallel fan-out must execute: delta updates + reducer channels.

Decision doc: .kiro/specs/decision-2026-08-15-engine-parallel-fanout-state-channels.md

The compiler accepts diamond topology (input -> seed -> left/right -> join),
so the runtime must execute it. Before the fix, WorkflowState.data/flow were
reducer-less LastValue channels and every phase node returned the full merged
state, so the two parallel branches collided with InvalidUpdateError in one
superstep even though their business fields are disjoint.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.loader import SkillLoadError
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _logic_phase(root: Path, name: str, *, inputs: str, outputs: str, action: str, body: str) -> None:
    _write(
        root / "phases" / name / "LOGIC.md",
        f"""---
actions: [{action}]
validator: false
io:
  inputs:
    type: object
{inputs}
  outputs:
    type: object
{outputs}
---
<action>{action}</action>
""",
    )
    _write(root / "phases" / name / "actions" / f"{action}.py", body)


def _diamond_skill(root: Path) -> None:
    """input -> seed -> (left | right) -> join; pure LOGIC nodes, no LLM."""

    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: par-diamond
description: Minimal parallel fan-out probe with pure logic nodes.
io:
  inputs:
    type: object
    required: [seed_value]
    properties:
      seed_value: {type: integer}
  outputs:
    type: object
    required: [combined]
    properties:
      combined: {type: object}
phases: [seed, left, right, join]
---
<phase depends_on="input">seed</phase>
<phase depends_on="seed">left</phase>
<phase depends_on="seed">right</phase>
<phase depends_on="left,right" output>join</phase>
""",
    )
    _logic_phase(
        root,
        "seed",
        inputs="""    required: [seed_value]
    properties:
      seed_value: {type: integer}""",
        outputs="""    required: [base]
    properties:
      base: {type: integer}""",
        action="seed_out",
        body="def seed_out(inputs):\n    return {\"base\": inputs[\"seed_value\"]}\n",
    )
    _logic_phase(
        root,
        "left",
        inputs="""    required: [base]
    properties:
      base: {type: integer}""",
        outputs="""    required: [left_result]
    properties:
      left_result: {type: integer}""",
        action="left_out",
        body="def left_out(inputs):\n    return {\"left_result\": inputs[\"base\"] + 1}\n",
    )
    _logic_phase(
        root,
        "right",
        inputs="""    required: [base]
    properties:
      base: {type: integer}""",
        outputs="""    required: [right_result]
    properties:
      right_result: {type: integer}""",
        action="right_out",
        body="def right_out(inputs):\n    return {\"right_result\": inputs[\"base\"] + 2}\n",
    )
    _logic_phase(
        root,
        "join",
        inputs="""    required: [left_result, right_result]
    properties:
      left_result: {type: integer}
      right_result: {type: integer}""",
        outputs="""    required: [combined]
    properties:
      combined: {type: object}""",
        action="join_out",
        body=(
            "def join_out(inputs):\n"
            "    return {\"combined\": {\"left\": inputs[\"left_result\"], \"right\": inputs[\"right_result\"]}}\n"
        ),
    )


def _initial_state(**fields: object) -> WorkflowState:
    return WorkflowState(
        data=BusinessData(**fields),
        flow=FrameworkState(),
        messages=[],
    )


def test_diamond_fanout_executes_and_join_sees_both_branches(tmp_path: Path) -> None:
    _diamond_skill(tmp_path)
    compiled = compile_skill(tmp_path, cache=False)
    graph = assemble_graph(compiled)

    result = graph.graph.invoke(_initial_state(seed_value=7))

    data = result["data"].model_dump()
    assert data["combined"] == {"left": 8, "right": 9}
    # Both branch outputs must also be recorded per-phase (D7 per-node golden).
    phase_outputs = data.get("phase_outputs") or {}
    assert phase_outputs.get("left") == {"left_result": 8}
    assert phase_outputs.get("right") == {"right_result": 9}


def test_parallel_writers_of_same_field_are_rejected(tmp_path: Path) -> None:
    """Two dependency-independent phases declaring the same output field must be
    rejected at compile time (illegal state made unrepresentable) — or, if the
    compile rule is deferred, at runtime with a fatal naming the field."""

    _diamond_skill(tmp_path)
    # Rewrite right to clash with left on 'left_result'.
    _logic_phase(
        tmp_path,
        "right",
        inputs="""    required: [base]
    properties:
      base: {type: integer}""",
        outputs="""    required: [left_result]
    properties:
      left_result: {type: integer}""",
        action="right_out",
        body="def right_out(inputs):\n    return {\"left_result\": inputs[\"base\"] + 2}\n",
    )
    _write(
        tmp_path / "phases" / "join" / "LOGIC.md",
        """---
actions: [join_out]
validator: false
io:
  inputs:
    type: object
    required: [left_result]
    properties:
      left_result: {type: integer}
  outputs:
    type: object
    required: [combined]
    properties:
      combined: {type: object}
---
<action>join_out</action>
""",
    )
    _write(
        tmp_path / "phases" / "join" / "actions" / "join_out.py",
        "def join_out(inputs):\n    return {\"combined\": {\"got\": inputs[\"left_result\"]}}\n",
    )

    with pytest.raises(SkillLoadError):
        compile_skill(tmp_path, cache=False)
