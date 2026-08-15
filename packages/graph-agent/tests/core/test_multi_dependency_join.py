"""A phase with several `depends_on` predecessors must wait for ALL of them.

Decision doc: .kiro/specs/decision-2026-08-15-engine-multi-dep-join-waits-for-all.md

The assembler used to translate `depends_on="a,b"` into two independent edges,
one per predecessor. In LangGraph a plain edge is a trigger, not a barrier: the
target fires as soon as ANY subscribed predecessor commits. That is invisible
while every predecessor happens to finish in the same superstep — the usual
fan-out/fan-in diamond — and wrong the moment the branches have different
depths. Then the join runs early against a blackboard that is missing the deep
branch's output, and runs a SECOND time when that branch finally lands.
"""

from __future__ import annotations

from pathlib import Path

import graph_agent

_AGENT = """---
llm_role: analyst
io:
  inputs:
    type: object
    required: [{required}]
    properties:
{input_props}
  outputs:
    type: object
    required: [{produces}]
    properties:
      {produces}: {{type: string}}
---
<role>Test phase.</role>
<goal>Produce `{produces}`, then finish the task.</goal>
"""


def _agent(required: list[str], produces: str) -> str:
    props = "\n".join(f"      {name}: {{type: string}}" for name in required)
    return _AGENT.format(required=", ".join(required), input_props=props, produces=produces)


# seed@1 → {fast@2, slow_a@2} → slow_b@3.  `join` depends on fast AND slow_b, so
# it may only run at superstep 4, after the deeper branch has landed.
_GRAPH = """---
schema_version: "v0.3.0"
name: staggered-join
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic: {type: string}
  outputs:
    type: object
    required: [verdict]
    properties:
      verdict: {type: string}
phases: [seed, fast, slow_a, slow_b, join]
---
<phase depends_on="input">seed</phase>
<phase depends_on="seed">fast</phase>
<phase depends_on="seed">slow_a</phase>
<phase depends_on="slow_a">slow_b</phase>
<phase depends_on="fast,slow_b" output>join</phase>
"""

_PHASES = {
    "seed": (["topic"], "seeded"),
    "fast": (["seeded"], "fast_result"),
    "slow_a": (["seeded"], "slow_a_result"),
    "slow_b": (["slow_a_result"], "slow_b_result"),
    "join": (["fast_result", "slow_b_result"], "verdict"),
}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _staggered_skill(root: Path) -> Path:
    skill = root / "skill"
    _write(skill / "GRAPH.md", _GRAPH)
    for phase_id, (required, produces) in _PHASES.items():
        _write(skill / "phases" / phase_id / "SKILL.md", _agent(required, produces))
    return skill


def test_join_waits_for_the_deeper_branch(tmp_path: Path) -> None:
    """`join` must not run until `slow_b` — two supersteps deeper than `fast` —
    has written its output to the blackboard."""
    skill = _staggered_skill(tmp_path)

    result = graph_agent.predict_skill(skill, workspace_dir=tmp_path / "ws", topic="mirrors")

    assert result.success, f"predict failed: {result.error}"
    assert "verdict" in result.context, f"join never produced its output; context={result.context}"


def test_join_runs_exactly_once(tmp_path: Path) -> None:
    """Each predecessor edge used to re-trigger the join, so a staggered join
    executed once per predecessor superstep. Re-running a phase burns real
    tokens at run time and silently overwrites the first result."""
    skill = _staggered_skill(tmp_path)

    result = graph_agent.predict_skill(skill, workspace_dir=tmp_path / "ws", topic="mirrors")

    assert result.success, f"predict failed: {result.error}"
    runs = [phase for phase in result.phases if phase.phase_name == "join"]
    assert len(runs) == 1, f"join executed {len(runs)} times: {[p.phase_name for p in result.phases]}"
