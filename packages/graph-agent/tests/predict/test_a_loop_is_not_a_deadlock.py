"""A phase that loops because the plan says to is not a phase that is stuck.

Predict guards against its own stand-in data trapping routing: feed every agent
node the same output every time and a route that branches on that output keeps
choosing the same edge, so predict would spin where a real run would move on.
The guard counted how often each phase NAME appeared and called anything over
ten a deadlock.

But a phase repeats for two unrelated reasons. `iterate` repeats it on purpose,
once per item, and the item list is resolved before the loop starts
(`graph_assembler._run_graph_loop_iterate`) — finite, planned, and about to end.
Routing coming back to a phase is the other one, and only that one is a trap.
Counting names alone cannot tell them apart, and it did not: a plain loop over
eleven items — a LOGIC phase running a two-line Python action, no model and no
stub anywhere near it — died with `PredictDeadlockError` (ledger K5).

The archived predict-v2 design saw this coming and wrote the mitigation down:
"合法循环 vs 死锁误判:合理的多次循环被强杀。缓解:…该防护仅在 P2 模式生效"
(.kiro/specs/_archive/predict-v2/design.md:234). Scoping the guard to the stub
strategy is in the code — but a strategy belongs to the whole RUN, so it never
separated a looping phase from a stuck one. What separates them is the
iteration each execution belongs to, which is now on the phase record, so the
count is per iteration: a loop over a thousand items is a thousand groups of
one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import graph_agent
from graph_agent.core.runner import MAX_PHASE_REVISITS

_ITEM_COUNT = MAX_PHASE_REVISITS + 1


def _schema(properties: dict[str, Any], *, required: list[str] | None = None) -> str:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required is not None:
        schema["required"] = required
    return json.dumps(schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _looping_skill(root: Path) -> Path:
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: loop-not-deadlock
io:
  inputs:
    {_schema({"items": {"type": "array"}}, required=["items"])}
  outputs:
    {_schema({"collected": {"type": "array"}})}
phases:
  - collect
  - summarize
---
<phase depends_on="input">collect</phase>
<phase depends_on="collect" output>summarize</phase>
""",
    )
    _write(
        root / "phases" / "collect" / "LOGIC.md",
        f"""---
io:
  inputs:
    {_schema({"item": {}, "collected": {}}, required=["item", "collected"])}
  outputs:
    {_schema({"piece": {}})}
actions: [collect]
validator: false
iterate:
  mode: loop
  over: items
  item_var: item
  accumulate:
    var: collected
    init: []
    from: piece
    merge: append
---
<action>collect</action>
""",
    )
    _write(
        root / "phases" / "collect" / "actions" / "collect.py",
        "def collect(inputs):\n    return {\"piece\": inputs[\"item\"]}\n",
    )
    _write(
        root / "phases" / "summarize" / "LOGIC.md",
        f"""---
io:
  inputs:
    {_schema({"collected": {}}, required=["collected"])}
  outputs:
    {_schema({"collected": {}})}
actions: [summarize]
validator: false
---
<action>summarize</action>
""",
    )
    _write(
        root / "phases" / "summarize" / "actions" / "summarize.py",
        "def summarize(inputs):\n    return {\"collected\": inputs[\"collected\"]}\n",
    )
    return root


def test_a_loop_longer_than_the_revisit_limit_still_predicts(tmp_path: Path) -> None:
    """One more item than the limit — the shortest loop the old guard killed."""
    skill = _looping_skill(tmp_path / "skill")
    items = [f"item-{index}" for index in range(_ITEM_COUNT)]

    result = graph_agent.predict_skill(skill, workspace_dir=tmp_path / "ws", items=items)

    assert result.success, f"predict failed on a legal loop: {result.error}"
    visits = [phase.phase_name for phase in result.phases].count("collect")
    assert visits == _ITEM_COUNT, (
        "the looping phase must run once per item, and every one of those runs is "
        f"the plan being followed; phases={[p.phase_name for p in result.phases]}"
    )


def test_a_much_longer_loop_is_still_not_a_deadlock(tmp_path: Path) -> None:
    """Raising the number would pass the test above and still be wrong.

    The limit is not what changed — what a visit is counted AGAINST changed. A
    loop has no length at which it becomes a deadlock, so the test that proves
    the difference is one no threshold could survive.
    """
    skill = _looping_skill(tmp_path / "skill")
    items = [f"item-{index}" for index in range(MAX_PHASE_REVISITS * 5)]

    result = graph_agent.predict_skill(skill, workspace_dir=tmp_path / "ws", items=items)

    assert result.success, f"predict failed on a long legal loop: {result.error}"
