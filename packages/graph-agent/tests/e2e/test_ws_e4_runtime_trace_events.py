"""E2E RED tests for WS-E4 runtime edge events in trace.jsonl."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graph_agent.callbacks.events import InputDispatchEvent
from graph_agent.core.runner import run_skill
from tests.ws_e4_runtime_skills import write_serial_two_phase_skill


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_runtime_edge_events_reach_event_subscriber_and_trace_jsonl(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace = tmp_path / "workspace"
    write_serial_two_phase_skill(skill_root, name="ws-e4-runtime-trace-e2e")
    subscriber_events: list[object] = []

    result = run_skill(
        skill_root,
        workspace_dir=workspace,
        thread_id="ws-e4-runtime-trace",
        event_subscriber=subscriber_events.append,
        skill_resolver=mock_skill_resolver,
        source="seed",
    )

    assert result["context"]["answer"] == "seed:prepared:done"
    subscriber_dispatches = [
        event for event in subscriber_events if isinstance(event, InputDispatchEvent)
    ]
    trace_rows = _read_jsonl(Path(str(result["trace_path"])))
    trace_dispatches = [
        row for row in trace_rows if row.get("event_type") == "input_dispatch"
    ]

    assert (
        [event.to_phase for event in subscriber_dispatches],
        [row["to_phase"] for row in trace_dispatches],
        [row["event_type"] for row in trace_dispatches],
    ) == (
        ["prepare", "finish"],
        ["prepare", "finish"],
        ["input_dispatch", "input_dispatch"],
    )
    assert trace_dispatches[0]["blackboard_snapshot"]["source"] == "seed"
    assert trace_dispatches[1]["blackboard_snapshot"]["prepared"] == "seed:prepared"
