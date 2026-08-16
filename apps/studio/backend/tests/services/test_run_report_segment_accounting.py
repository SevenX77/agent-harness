"""A transition is accounted as its own segment, not charged to the next node.

Decision 2026-08-15 (docs/design/2026-08-15-edge-as-first-class-run-segment-decision.md,
D8). Before this, every edge operation fell through to the `to_phase` fallback
in `_event_node`, so work and failures that happened BEFORE a node started were
folded into that node's row — the node looked responsible for them.
"""

from __future__ import annotations

from typing import Any

from app.services.run_report import _account_nodes


def _accounts(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {account.node_id: account for account in _account_nodes(events)}


class TestTransitionIsItsOwnRow:
    def test_an_edge_operation_is_not_charged_to_the_node_it_leads_into(self) -> None:
        accounts = _accounts(
            [
                {
                    "event_type": "input_dispatch",
                    "edge_transition_id": "t1",
                    "from_phases": ["outline"],
                    "to_phase": "draft",
                },
                {"event_type": "phase_start", "phase_name": "draft", "timestamp": "T1"},
                {"event_type": "llm_call", "phase_name": "draft", "input_tokens": 10},
            ]
        )

        assert "outline -> draft" in accounts, (
            "the transition should have a row of its own; instead its operation was "
            f"folded into a node row. Got: {sorted(accounts)}"
        )
        assert accounts["draft"].llm_calls == 1

    def test_a_transition_row_carries_its_own_wall_time(self) -> None:
        accounts = _accounts(
            [
                {
                    "event_type": "edge_start",
                    "edge_transition_id": "t1",
                    "from_phases": ["outline"],
                    "to_phase": "draft",
                    "timestamp": "2026-08-15T00:00:00+00:00",
                },
                {
                    "event_type": "edge_end",
                    "edge_transition_id": "t1",
                    "from_phases": ["outline"],
                    "to_phase": "draft",
                    "timestamp": "2026-08-15T00:00:02+00:00",
                },
            ]
        )

        assert accounts["outline -> draft"].wall_time_sec == 2.0

    def test_a_transition_leaving_the_input_boundary_says_so(self) -> None:
        accounts = _accounts(
            [
                {
                    "event_type": "edge_start",
                    "edge_transition_id": "t1",
                    "from_phases": [],
                    "to_phase": "first",
                }
            ]
        )

        assert "input -> first" in accounts

    def test_a_fan_in_transition_names_every_upstream(self) -> None:
        accounts = _accounts(
            [
                {
                    "event_type": "edge_start",
                    "edge_transition_id": "t1",
                    "from_phases": ["left", "right"],
                    "to_phase": "merge",
                }
            ]
        )

        assert "left + right -> merge" in accounts

    def test_a_failure_inside_a_transition_stays_on_the_transition(self) -> None:
        accounts = _accounts(
            [
                {
                    "event_type": "protocol_violation",
                    "edge_transition_id": "t1",
                    "from_phases": ["outline"],
                    "to_phase": "draft",
                    "violations": ["blackboard key missing"],
                },
                {"event_type": "phase_start", "phase_name": "draft"},
            ]
        )

        assert accounts["outline -> draft"].errors == [
            "protocol_violation: blackboard key missing"
        ]
        assert accounts["draft"].errors == []
