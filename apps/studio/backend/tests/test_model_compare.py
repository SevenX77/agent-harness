"""PR2 node-level Compare LLMs — isolated single-node side-run mechanics.

Covers the pure helpers: input-slice extraction from a base run's events, and
single-node skill-variant materialization that actually compiles + runs with the
captured slice. The orchestration/spawn path is covered in the API test.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.services.model_compare import (
    CompareNodeInputMissingError,
    extract_node_input,
    materialize_single_node_skill,
    node_effective_role,
)
from graph_agent.core.compiler import compile_skill
from graph_agent.core.event_contracts import make_event_envelope
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _two_phase_skill(root: Path) -> Path:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: two-phase
io:
  inputs: {type: object, properties: {}}
  outputs:
    type: object
    required: [report]
    properties: {report: {type: string}}
phases: [prepare, score]
---
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare" output>score</phase>
""",
    )
    _write(
        root / "phases" / "prepare" / "LOGIC.md",
        """---
io:
  inputs: {type: object, properties: {}}
  outputs:
    type: object
    required: [seed]
    properties: {seed: {type: integer}}
actions: [prepare]
validator: false
---
<action>prepare</action>
""",
    )
    _write(root / "phases" / "prepare" / "actions" / "prepare.py", "def prepare(inputs):\n    return {'seed': 3}\n")
    _write(
        root / "phases" / "score" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    required: [seed]
    properties: {seed: {type: integer}}
  outputs:
    type: object
    required: [report]
    properties: {report: {type: string}}
actions: [score]
validator: false
---
<action>score</action>
""",
    )
    _write(
        root / "phases" / "score" / "actions" / "score.py",
        "def score(inputs):\n    return {'report': f\"scored {inputs['seed']}\"}\n",
    )
    return root


# ---------------------------------------------------------------------------
# extract_node_input
# ---------------------------------------------------------------------------


def _dispatch_event(run_id: str, seq: int, to_phase: str, snapshot: dict) -> object:
    return make_event_envelope(
        stream_id=f"run:{run_id}",
        seq=seq,
        run_id=run_id,
        event_type="input_dispatch",
        payload={
            "event_type": "input_dispatch",
            "from_phase": None,
            "to_phase": to_phase,
            "changed_keys": list(snapshot),
            "blackboard_snapshot": snapshot,
            "dispatched_keys": list(snapshot),
            "branch_index": None,
        },
        cursor=f"run:{run_id}:{seq}",
        timestamp=datetime.now(tz=UTC),
    )


def test_extract_node_input_returns_dispatched_slice() -> None:
    events = [
        _dispatch_event("r1", 1, "prepare", {}),
        _dispatch_event("r1", 2, "score", {"seed": 3}),
    ]
    assert extract_node_input(events, "score") == {"seed": 3}


def test_extract_node_input_missing_raises() -> None:
    events = [_dispatch_event("r1", 1, "prepare", {})]
    with pytest.raises(CompareNodeInputMissingError):
        extract_node_input(events, "score")


def test_extract_node_input_uses_last_dispatch() -> None:
    # a re-dispatched node (retry/loop) -> take the latest slice
    events = [
        _dispatch_event("r1", 1, "score", {"seed": 1}),
        _dispatch_event("r1", 2, "score", {"seed": 9}),
    ]
    assert extract_node_input(events, "score") == {"seed": 9}


# ---------------------------------------------------------------------------
# materialize_single_node_skill  (compiles + runs)
# ---------------------------------------------------------------------------


def test_materialize_single_node_compiles_and_runs(tmp_path: Path) -> None:
    skill = _two_phase_skill(tmp_path / "skill")
    variant = materialize_single_node_skill(skill, "score", tmp_path / "variant")

    compiled = compile_skill(variant, cache=False)
    assert [n.phase_name for n in compiled.nodes] == ["score"]
    # only the target phase dir survives
    assert (variant / "phases" / "score").is_dir()
    assert not (variant / "phases" / "prepare").exists()

    assembled = assemble_graph(compiled)
    init = WorkflowState(
        data=BusinessData.model_validate({"seed": 3}),
        flow=FrameworkState(),
        messages=[],
    )
    result = assembled.graph.invoke(init)
    assert result["data"].model_dump()["report"] == "scored 3"


def test_materialize_unknown_node_raises(tmp_path: Path) -> None:
    skill = _two_phase_skill(tmp_path / "skill")
    with pytest.raises(ValueError, match="not found"):
        materialize_single_node_skill(skill, "nope", tmp_path / "variant")


def test_node_effective_role_falls_back_to_graph_agent(tmp_path: Path) -> None:
    skill = _two_phase_skill(tmp_path / "skill")
    # logic node, no graph llm_role -> conventional fallback
    assert node_effective_role(skill, "score") == "graph_agent"
