"""Two same-named phases from different subgraphs get different report rows.

Field evidence (run 2026-08-19T01-56-15_d0733362, story-deconstruction-v3-lab):
the text-segmentation subgraph and the event-extraction subgraph both own a
phase named `review`. The report keyed node rows on the bare phase name, so the
two nodes folded into one row (13 llm_calls) and event-extraction's `setup`
row vanished into segmentation's. The engine now stamps `subgraph_path` on
every event (`_EventBase.subgraph_path`); the report keys rows on
`subgraph_path/phase_name` so the folding cannot recur, while iterate
executions of ONE node still aggregate into one row.
"""

from __future__ import annotations

from typing import Any

from app.services.run_report import _account_nodes


def _accounts(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {account.node_id: account for account in _account_nodes(events)}


class TestSubgraphScope:
    def test_same_phase_name_in_two_subgraphs_is_two_rows(self) -> None:
        accounts = _accounts(
            [
                {"event_type": "phase_start", "phase_name": "review",
                 "subgraph_path": "segmentation", "timestamp": "T1"},
                {"event_type": "llm_call", "phase_name": "review",
                 "subgraph_path": "segmentation", "input_tokens": 10},
                {"event_type": "phase_start", "phase_name": "review",
                 "subgraph_path": "event_timeline.extrac", "timestamp": "T2"},
                {"event_type": "llm_call", "phase_name": "review",
                 "subgraph_path": "event_timeline.extrac", "input_tokens": 20},
            ]
        )

        assert "segmentation/review" in accounts and "event_timeline.extrac/review" in accounts, (
            f"two different nodes folded into one row: {sorted(accounts)}"
        )
        assert accounts["segmentation/review"].llm_calls == 1
        assert accounts["event_timeline.extrac/review"].llm_calls == 1

    def test_iterate_executions_of_one_node_still_share_a_row(self) -> None:
        accounts = _accounts(
            [
                {"event_type": "llm_call", "phase_name": "review",
                 "subgraph_path": "segmentation", "input_tokens": 10},
                {"event_type": "llm_call", "phase_name": "review",
                 "subgraph_path": "segmentation", "input_tokens": 15},
            ]
        )

        assert accounts["segmentation/review"].llm_calls == 2

    def test_root_level_events_keep_their_bare_label(self) -> None:
        accounts = _accounts(
            [
                {"event_type": "phase_start", "phase_name": "segmentation", "timestamp": "T1"},
                {"event_type": "input_dispatch", "edge_transition_id": "t1",
                 "from_phases": ["segmentation"], "to_phase": "event_timeline"},
            ]
        )

        assert "segmentation" in accounts
        assert "segmentation -> event_timeline" in accounts

    def test_a_transition_inside_a_subgraph_is_scoped_too(self) -> None:
        accounts = _accounts(
            [
                {"event_type": "input_dispatch", "edge_transition_id": "t1",
                 "subgraph_path": "event_timeline",
                 "from_phases": ["extrac"], "to_phase": "stitch"},
            ]
        )

        assert "event_timeline/extrac -> stitch" in accounts, sorted(accounts)
