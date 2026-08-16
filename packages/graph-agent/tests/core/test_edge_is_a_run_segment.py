"""An edge is a run segment, peer to a node — not an unowned gap.

Decision 2026-08-15 (docs/design/2026-08-15-edge-as-first-class-run-segment-decision.md).
The user's ruling the design answers, verbatim: 「edge指的是一个node到下一个中间的
过程，是需要的，把engine该补的补齐」「tracing要把edge和node作为平级的运行分段，
流中的一个节点」.

What these tests pin is the SHAPE of the record, not the wording: a transition
opens and closes around every phase execution, every edge operation inside it
carries its id, and both ends of the transition name the executions they join.
"""

from __future__ import annotations

from typing import Any

from graph_agent.callbacks.events import (
    BlackboardReduceEvent,
    EdgeEndEvent,
    EdgeStartEvent,
    InputDispatchEvent,
    PhaseEndEvent,
    PhaseStartEvent,
)
from graph_agent.core.edge_transition import (
    active_edge_transition_var,
    active_phase_execution_id,
    close_edge_transition,
    record_edge_operation,
    transition_identity,
    wrap_edge_transition,
)
from graph_agent.core.state import BusinessData, FrameworkState, merge_flow_channel


class _Recorder:
    """The production consumer shape: one `on_event`, nothing else."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)

    def of(self, event_type: type) -> list[Any]:
        return [e for e in self.events if isinstance(e, event_type)]

    @property
    def order(self) -> list[str]:
        return [e.event_type for e in self.events]


def _state(**flow_kwargs: Any) -> dict[str, Any]:
    return {"data": BusinessData(), "flow": FrameworkState(**flow_kwargs), "messages": []}


class TestTransitionBoundaries:
    def test_an_empty_transition_still_opens_and_closes(self) -> None:
        """A transition with zero operations is an observation, not a gap (D1)."""
        rec = _Recorder()
        node = wrap_edge_transition(
            "draft",
            lambda state: {},
            upstream_phases=[],
            callbacks=[rec],
            branch_index_of=lambda: None,
        )

        node(_state())

        assert rec.order == ["edge_start", "edge_end"]
        start, end = rec.of(EdgeStartEvent)[0], rec.of(EdgeEndEvent)[0]
        assert start.edge_transition_id == end.edge_transition_id
        assert end.operation_count == 0

    def test_the_transition_closes_before_the_phase_it_leads_into_starts(self) -> None:
        """Peer segments must not overlap: edge_end precedes phase_start."""
        rec = _Recorder()

        def _phase(state: dict[str, Any]) -> dict[str, Any]:
            close_edge_transition([rec])
            execution_id = active_phase_execution_id()
            rec.on_event(PhaseStartEvent(phase_name="draft", phase_execution_id=execution_id))
            rec.on_event(PhaseEndEvent(phase_name="draft", phase_execution_id=execution_id))
            return {}

        node = wrap_edge_transition(
            "draft",
            _phase,
            upstream_phases=[],
            callbacks=[rec],
            branch_index_of=lambda: None,
        )
        node(_state())

        assert rec.order == ["edge_start", "edge_end", "phase_start", "phase_end"]

    def test_the_phase_execution_named_on_edge_start_is_the_one_that_runs(self) -> None:
        seen: list[str] = []

        def _phase(state: dict[str, Any]) -> dict[str, Any]:
            seen.append(active_phase_execution_id())
            return {}

        rec = _Recorder()
        node = wrap_edge_transition(
            "draft",
            _phase,
            upstream_phases=[],
            callbacks=[rec],
            branch_index_of=lambda: None,
        )
        node(_state())

        assert seen == [rec.of(EdgeStartEvent)[0].to_phase_execution_id]

    def test_each_pass_is_its_own_transition(self) -> None:
        """A loop walking the same edge N times is N transitions, not one (D4)."""
        rec = _Recorder()
        node = wrap_edge_transition(
            "draft",
            lambda state: {},
            upstream_phases=["outline"],
            callbacks=[rec],
            branch_index_of=lambda: None,
        )

        node(_state())
        node(_state())

        ids = [e.edge_transition_id for e in rec.of(EdgeStartEvent)]
        assert len(ids) == 2
        assert ids[0] != ids[1]

    def test_the_transition_closes_even_when_the_phase_raises(self) -> None:
        rec = _Recorder()

        def _explode(state: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("phase died")

        node = wrap_edge_transition(
            "draft",
            _explode,
            upstream_phases=[],
            callbacks=[rec],
            branch_index_of=lambda: None,
        )

        try:
            node(_state())
        except RuntimeError:
            pass

        assert rec.order == ["edge_start", "edge_end"]

    def test_the_segment_does_not_leak_out_of_the_phase(self) -> None:
        node = wrap_edge_transition(
            "draft",
            lambda state: {},
            upstream_phases=[],
            callbacks=None,
            branch_index_of=lambda: None,
        )

        node(_state())

        assert active_edge_transition_var.get() is None


class TestUpstreamIdentity:
    def test_a_fan_in_names_every_upstream_execution_it_joins(self) -> None:
        """Plural by design (D3): "take the most recent one" is the inference
        this decision exists to delete."""
        rec = _Recorder()
        node = wrap_edge_transition(
            "merge",
            lambda state: {},
            upstream_phases=["left", "right"],
            callbacks=[rec],
            branch_index_of=lambda: None,
        )

        node(
            _state(
                phase_execution_ids={
                    "left": ["exec-l"],
                    "right": ["exec-r"],
                    "other": ["exec-o"],
                }
            )
        )

        start = rec.of(EdgeStartEvent)[0]
        assert start.from_phases == ["left", "right"]
        assert start.from_phase_execution_ids == ["exec-l", "exec-r"]

    def test_a_single_upstream_is_a_list_of_one_not_a_special_case(self) -> None:
        rec = _Recorder()
        node = wrap_edge_transition(
            "draft",
            lambda state: {},
            upstream_phases=["outline"],
            callbacks=[rec],
            branch_index_of=lambda: None,
        )

        node(_state(phase_execution_ids={"outline": ["exec-1"]}))

        assert rec.of(EdgeStartEvent)[0].from_phase_execution_ids == ["exec-1"]

    def test_parallel_siblings_do_not_overwrite_each_others_execution_ids(self) -> None:
        """The flow channel merges this map per key, so a fan-out keeps both."""
        base = FrameworkState(phase_execution_ids={"left": ["exec-l"]})

        merged = merge_flow_channel(base, {"phase_execution_ids": {"right": ["exec-r"]}})

        assert merged.phase_execution_ids == {"left": ["exec-l"], "right": ["exec-r"]}


class TestOperationsBelongToTheSegment:
    def test_every_operation_carries_the_id_of_the_segment_it_ran_in(self) -> None:
        rec = _Recorder()

        def _phase(state: dict[str, Any]) -> dict[str, Any]:
            transition_id, from_phases, to_phase = transition_identity()
            record_edge_operation(["topic"], {"topic": "mars"})
            rec.on_event(
                InputDispatchEvent(
                    edge_transition_id=transition_id,
                    from_phases=from_phases,
                    to_phase=to_phase,
                    changed_keys=["topic"],
                    blackboard_snapshot={"topic": "mars"},
                    dispatched_keys=["topic"],
                    branch_index=None,
                )
            )
            return {}

        node = wrap_edge_transition(
            "draft",
            _phase,
            upstream_phases=["outline"],
            callbacks=[rec],
            branch_index_of=lambda: None,
        )
        node(_state())

        transition_id = rec.of(EdgeStartEvent)[0].edge_transition_id
        dispatch = rec.of(InputDispatchEvent)[0]
        assert dispatch.edge_transition_id == transition_id
        assert dispatch.from_phases == ["outline"]

    def test_the_closing_event_reports_what_the_segment_handed_downstream(self) -> None:
        rec = _Recorder()

        def _phase(state: dict[str, Any]) -> dict[str, Any]:
            record_edge_operation(["a"], {"a": 1})
            record_edge_operation(["b"], {"a": 1, "b": 2})
            record_edge_operation(["a"], {"a": 3, "b": 2})
            return {}

        node = wrap_edge_transition(
            "draft",
            _phase,
            upstream_phases=[],
            callbacks=[rec],
            branch_index_of=lambda: None,
        )
        node(_state())

        end = rec.of(EdgeEndEvent)[0]
        assert end.operation_count == 3
        assert end.changed_keys == ["a", "b"]
        assert end.blackboard_snapshot == {"a": 3, "b": 2}

    def test_an_operation_outside_any_segment_reports_no_owner_rather_than_a_guess(
        self,
    ) -> None:
        """Nothing invents an owner. The empty id is a visible "unattributed",
        which is the state the old `from_phase=None` could not distinguish from
        "no upstream"."""
        assert transition_identity() == ("", [], "")
        record_edge_operation(["a"], {"a": 1})  # must not raise


class TestBlackboardReduceIsAttributed:
    def test_reduce_names_its_segment_instead_of_a_null_upstream(self) -> None:
        from graph_agent.core.graph_assembler import _emit_blackboard_reduce

        rec = _Recorder()

        def _phase(state: dict[str, Any]) -> dict[str, Any]:
            _emit_blackboard_reduce(
                [rec],
                to_phase="draft",
                state=state,  # type: ignore[arg-type]
                changed_key="outline",
                reducer="last",
            )
            return {}

        node = wrap_edge_transition(
            "draft",
            _phase,
            upstream_phases=["outline_phase"],
            callbacks=[rec],
            branch_index_of=lambda: None,
        )
        node(_state())

        reduce_event = rec.of(BlackboardReduceEvent)[0]
        assert reduce_event.edge_transition_id == rec.of(EdgeStartEvent)[0].edge_transition_id
        assert reduce_event.from_phases == ["outline_phase"]
