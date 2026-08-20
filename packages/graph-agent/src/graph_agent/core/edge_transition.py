"""The transition segment between one phase execution and the next.

A langgraph edge is routing, not an executable unit, so the engine has no
object standing for "what happens between two nodes". Everything that does
happen there — blackboard reduction, input dispatch, input-file injection —
used to be emitted from the head of the downstream node's wrapper and was
therefore parented to whichever phase happened to be current, which is why
``BlackboardReduceEvent.from_phase`` could only ever be ``None``.

This module owns that stretch as a first-class run segment, peer to a phase
segment: it opens, it closes, it has an identity, and it names both ends.
Authoritative design: docs/design/2026-08-15-edge-as-first-class-run-segment-decision.md

It sits below both the assembler (which opens transitions) and the state
mapper (which records a phase execution's identity for the transitions
leaving it), so neither has to import the other.
"""

from __future__ import annotations

import contextvars
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from graph_agent.callbacks.emit import _safe_emit_event, active_phase_execution
from graph_agent.callbacks.events import EdgeEndEvent, EdgeStartEvent


@dataclass
class EdgeTransition:
    """One transition: the run segment between upstream end and downstream start.

    The engine has no executable object for a langgraph edge — an edge is
    routing, not a node — so the only place where "after the upstream, before
    the downstream" is observable is the head of the downstream phase's
    wrapper. This gives that stretch a name and a pair of boundaries instead
    of leaving its operations parented to whichever phase happened to be
    current (decision 2026-08-15 edge-as-run-segment, §3.1).

    One instance per TRANSITION, not per edge: a loop walking the same edge N
    times produces N of these, and a fan-out to K downstreams produces K (D4).
    """

    transition_id: str
    from_phases: list[str]
    from_phase_execution_ids: list[str]
    to_phase: str
    to_phase_execution_id: str
    branch_index: int | None
    changed_keys: list[str] = field(default_factory=list)
    blackboard_snapshot: dict[str, Any] = field(default_factory=dict)
    operation_count: int = 0
    closed: bool = False

    def record_operation(self, changed_keys: list[str], snapshot: dict[str, Any]) -> None:
        """Fold one edge operation into what this transition will report."""
        self.operation_count += 1
        for key in changed_keys:
            if key not in self.changed_keys:
                self.changed_keys.append(key)
        self.blackboard_snapshot = snapshot


#: The transition the current phase execution arrived through. A ContextVar
#: because every consumer sits in the same call stack below the opener — and
#: because batch/iterate items run on their own threads, where a module global
#: would let concurrent items overwrite each other's transition. Same reason
#: ``active_branch_index_var`` above is one.
active_edge_transition_var: contextvars.ContextVar[EdgeTransition | None] = (
    contextvars.ContextVar("active_edge_transition", default=None)
)


def transition_identity() -> tuple[str, list[str], str]:
    """Return ``(transition_id, from_phases, to_phase)`` of the active transition.

    Every edge operation is stamped with this so a consumer groups by segment
    identity rather than by guessing an owner from the phase that happened to
    be current.
    """
    transition = active_edge_transition_var.get()
    if transition is None:
        return "", [], ""
    return transition.transition_id, list(transition.from_phases), transition.to_phase


def record_edge_operation(changed_keys: list[str], snapshot: dict[str, Any]) -> None:
    transition = active_edge_transition_var.get()
    if transition is not None:
        transition.record_operation(changed_keys, snapshot)

def phase_execution_ids_of(state: Any) -> dict[str, list[str]]:
    """Read ``flow.phase_execution_ids`` off a graph state, tolerating both shapes.

    The flow channel is a Pydantic model in a live run and a plain dict in a
    delta, and this reader is on the path of every transition.
    """
    flow_obj = state.get("flow") if hasattr(state, "get") else None
    if flow_obj is None:
        return {}
    if hasattr(flow_obj, "phase_execution_ids"):
        recorded = flow_obj.phase_execution_ids
    elif isinstance(flow_obj, dict):
        recorded = flow_obj.get("phase_execution_ids")
    else:
        recorded = None
    if not isinstance(recorded, dict):
        return {}
    return {
        str(phase): [str(execution_id) for execution_id in ids]
        for phase, ids in recorded.items()
        if isinstance(ids, list)
    }


def wrap_edge_transition(
    phase_id: str,
    node: Any,
    *,
    upstream_phases: list[str],
    callbacks: Any | None,
    branch_index_of: Callable[[], int | None],
) -> Any:
    """Open a transition segment before the downstream phase, close it before its start.

    The segment closes from inside ``_node_with_lifecycle`` (just before
    ``phase_start``) so the two segments never overlap; closing here in the
    ``finally`` is the backstop for a phase that dies before it starts.
    """

    def _run(state: Any) -> dict[str, Any]:
        recorded = phase_execution_ids_of(state)
        transition = EdgeTransition(
            transition_id=uuid.uuid4().hex[:12],
            from_phases=list(upstream_phases),
            from_phase_execution_ids=[
                execution_id
                for name in upstream_phases
                for execution_id in recorded.get(name, ())
            ],
            to_phase=phase_id,
            to_phase_execution_id=uuid.uuid4().hex[:12],
            branch_index=branch_index_of(),
        )
        token = active_edge_transition_var.set(transition)
        # Everything emitted from here to the end of the phase body belongs to
        # the execution this transition leads into, so it is stamped rather
        # than passed down through every emitter (E15).
        execution_token = active_phase_execution.set(transition.to_phase_execution_id)
        _safe_emit_event(callbacks, edge_start_event(transition))
        try:
            return node(state)  # type: ignore[no-any-return]
        finally:
            close_edge_transition(callbacks)
            active_phase_execution.reset(execution_token)
            active_edge_transition_var.reset(token)

    return _run

def edge_start_event(transition: EdgeTransition) -> EdgeStartEvent:
    return EdgeStartEvent(
        edge_transition_id=transition.transition_id,
        from_phases=transition.from_phases,
        from_phase_execution_ids=transition.from_phase_execution_ids,
        to_phase=transition.to_phase,
        to_phase_execution_id=transition.to_phase_execution_id,
        branch_index=transition.branch_index,
    )

def active_phase_execution_id() -> str:
    """Identity of the phase execution the active transition leads into.

    Minted with the transition rather than here: the transition already had to
    name its destination execution on ``edge_start``, and two mints would be
    two ids for one execution.
    """
    transition = active_edge_transition_var.get()
    return transition.to_phase_execution_id if transition is not None else uuid.uuid4().hex[:12]

def close_edge_transition(callbacks: Any | None) -> None:
    """Emit ``edge_end`` once for the active transition. Idempotent."""
    transition = active_edge_transition_var.get()
    if transition is None or transition.closed:
        return
    transition.closed = True
    _safe_emit_event(
        callbacks,
        EdgeEndEvent(
            edge_transition_id=transition.transition_id,
            from_phases=transition.from_phases,
            from_phase_execution_ids=transition.from_phase_execution_ids,
            to_phase=transition.to_phase,
            to_phase_execution_id=transition.to_phase_execution_id,
            branch_index=transition.branch_index,
            changed_keys=transition.changed_keys,
            blackboard_snapshot=transition.blackboard_snapshot,
            operation_count=transition.operation_count,
        ),
    )


__all__ = [
    "EdgeTransition",
    "active_edge_transition_var",
    "active_phase_execution_id",
    "close_edge_transition",
    "record_edge_operation",
    "transition_identity",
    "phase_execution_ids_of",
    "wrap_edge_transition",
]
