"""E2E RED tests for WS-E4 runtime edge events in trace.jsonl."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any

from graph_agent.callbacks.events import InputDispatchEvent
from graph_agent.core.runner import run_skill


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _schema_yaml(properties: dict[str, Any], *, required: list[str] | None = None) -> str:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required is not None:
        schema["required"] = required
    return json.dumps(schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _serial_two_phase_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e4-runtime-trace-e2e
io:
  inputs:
    {_schema_yaml({"source": {"type": "string"}}, required=["source"])}
  outputs:
    {_schema_yaml({"answer": {"type": "string"}})}
phases:
  - prepare
  - finish
---
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare" output>finish</phase>
""",
    )
    _write_logic_phase(
        root,
        "prepare",
        inputs={"source": {"type": "string"}},
        outputs={"prepared": {"type": "string"}},
        required=["source"],
        action_body="""
            def prepare(context):
                return {"prepared": f"{context['source']}:prepared"}
        """,
    )
    _write_logic_phase(
        root,
        "finish",
        inputs={"prepared": {"type": "string"}},
        outputs={"answer": {"type": "string"}},
        required=["prepared"],
        action_body="""
            def finish(context):
                return {"answer": f"{context['prepared']}:done"}
        """,
    )


def _write_logic_phase(
    root: Path,
    phase_id: str,
    *,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    action_body: str,
    required: list[str] | None = None,
) -> None:
    _write(
        root / "phases" / phase_id / "LOGIC.md",
        f"""---
io:
  inputs:
    {_schema_yaml(inputs, required=required)}
  outputs:
    {_schema_yaml(outputs)}
actions: [{phase_id}]
validator: false
---
<action>{phase_id}</action>
""",
    )
    _write(
        root / "phases" / phase_id / "actions" / f"{phase_id}.py",
        dedent(action_body).lstrip(),
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_runtime_edge_events_reach_event_subscriber_and_trace_jsonl(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace = tmp_path / "workspace"
    _serial_two_phase_skill(skill_root)
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
