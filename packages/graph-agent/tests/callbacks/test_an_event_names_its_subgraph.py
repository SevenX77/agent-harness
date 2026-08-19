"""Every event emitted inside a subgraph names the subgraph chain it ran in.

A phase name is only unique WITHIN one skill. The composed graph runs several
skills, and two of them may both own a phase called `review` — which is not a
naming accident to fix in the skill: a subgraph is a reusable unit, and units
are allowed to have conventional internal names.

Field evidence (run 2026-08-19T01-56-15_d0733362, story-deconstruction-v3-lab):
the run report accounts nodes by bare ``phase_name``, so the `review` of the
text-segmentation subgraph and the `review` of the event-extraction subgraph
folded into ONE row (13 llm_calls), and event-extraction's `setup` vanished
into segmentation's. The events themselves carried nothing to tell them apart,
so the report could not do better (`run_report._event_node` reads phase keys
only) — the identity has to leave the engine on the event.

``_EventBase.subgraph_path`` is that identity: the dot-joined chain of
enclosing SUBGRAPH phase ids, stamped centrally in ``_safe_emit_event`` from
the scope ``_build_subgraph_node`` maintains around each child-graph invoke.
"""

from __future__ import annotations

from pathlib import Path

from graph_agent.callbacks.events import CallbackEvent, PhaseStartEvent
from graph_agent.core.runner import run_skill

from ..ws_e4_runtime_skills import _write_graph, write_logic_phase


def _child_skill(root: Path, in_field: str, out_field: str) -> None:
    """One-phase child whose only phase is named `review` — in BOTH children."""
    _write_graph(
        root,
        name="child-" + out_field,
        inputs={in_field: {"type": "string"}},
        outputs={out_field: {"type": "string"}},
        phases=["review"],
        phase_edges='<phase depends_on="input" output>review</phase>',
        required_inputs=[in_field],
    )
    write_logic_phase(
        root,
        "review",
        inputs={in_field: {"type": "string"}},
        outputs={out_field: {"type": "string"}},
        required=[in_field],
        action_body=f"""
            def review(inputs):
                return {{"{out_field}": inputs["{in_field}"] + "|review"}}
        """,
    )


def _subgraph_phase(root: Path, phase: str, child_rel: str, in_field: str, out_field: str) -> None:
    phase_dir = root / "phases" / phase
    phase_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"name: {phase}",
        f"path: {child_rel}",
        "io:",
        "  inputs:",
        "    type: object",
        f"    required: [{in_field}]",
        "    properties:",
        f"      {in_field}: {{type: string}}",
        "  outputs:",
        "    type: object",
        f"    required: [{out_field}]",
        "    properties:",
        f"      {out_field}: {{type: string}}",
        "---",
    ]
    (phase_dir / "SUBGRAPH.md").write_text(chr(10).join(lines) + chr(10), encoding="utf-8")


def test_two_subgraphs_same_phase_name_get_distinct_paths(tmp_path: Path) -> None:
    root = tmp_path / "parent"
    _write_graph(
        root,
        name="parent",
        inputs={"text": {"type": "string"}},
        outputs={"final": {"type": "string"}},
        phases=["alpha", "beta"],
        phase_edges=(
            '<phase depends_on="input">alpha</phase>' + chr(10)
            + '<phase depends_on="alpha" output>beta</phase>'
        ),
        required_inputs=["text"],
    )
    _child_skill(root / "subgraph" / "alpha-child", "text", "middle")
    _child_skill(root / "subgraph" / "beta-child", "middle", "final")
    _subgraph_phase(root, "alpha", "subgraph/alpha-child", "text", "middle")
    _subgraph_phase(root, "beta", "subgraph/beta-child", "middle", "final")

    events: list[CallbackEvent] = []
    result = run_skill(
        root,
        workspace_dir=tmp_path / "ws",
        unattended=True,
        event_subscriber=events.append,
        text="T",
    )
    assert result.success, result.error

    review_starts = [
        e for e in events if isinstance(e, PhaseStartEvent) and e.phase_name == "review"
    ]
    assert len(review_starts) == 2, [
        (e.phase_name, e.subgraph_path) for e in events if isinstance(e, PhaseStartEvent)
    ]
    paths = sorted(e.subgraph_path or "" for e in review_starts)
    assert paths == ["alpha", "beta"], (
        "the two `review` executions came from two different subgraphs, and the "
        f"events must say which; got subgraph_path values {paths}"
    )

    root_starts = [
        e
        for e in events
        if isinstance(e, PhaseStartEvent) and e.phase_name in ("alpha", "beta")
    ]
    assert root_starts, "subgraph phases themselves emit phase_start at root"
    assert all(e.subgraph_path is None for e in root_starts), (
        "root-level phases belong to no subgraph; their scope is None, not ''"
    )
