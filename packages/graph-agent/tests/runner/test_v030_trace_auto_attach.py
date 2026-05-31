from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from graph_agent.core.runner import _run_v030_skill_dict


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_logic_skill(root: Path, phases: list[tuple[str, list[str]]]) -> None:
    phase_yaml = "\n".join(f"  - {phase_id}" for phase_id, _ in phases)
    depended_on = {dep for _, deps in phases for dep in deps}
    phase_body = "\n".join(
        '<phase depends_on="{deps}"{output}>{phase_id}</phase>'.format(
            deps=", ".join(deps) if deps else "input",
            output=" output" if phase_id not in depended_on else "",
            phase_id=phase_id,
        )
        for phase_id, deps in phases
    )
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: trace-auto-attach
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
      request_id:
        type: string
    required: [topic, request_id]
  outputs:
    type: object
    properties:
      answer:
        type: string
      review:
        type: string
phases:
{phase_yaml}
---
{phase_body}
""",
    )
    for phase_id, _ in phases:
        outputs_props = "      answer:\n        type: string" if phase_id == "draft" else "      review:\n        type: string"
        _write(
            root / "phases" / phase_id / "LOGIC.md",
            f"""---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
      request_id:
        type: string
  outputs:
    type: object
    properties:
{outputs_props}
---
<action>{phase_id}</action>
""",
        )
        if phase_id == "draft":
            body = (
                "def draft(context):\n"
                "    topic = context.get('topic', 'missing')\n"
                "    return {'answer': f'draft:{topic}'}\n"
            )
        else:
            body = (
                f"def {phase_id}(context):\n"
                "    answer = context.get('answer', 'missing')\n"
                f"    return {{'review': '{phase_id}:' + answer}}\n"
            )
        _write(root / "phases" / phase_id / "actions" / f"{phase_id}.py", body)


def _run_without_subscriber(
    skill_root: Path,
    trace_dir: Path,
    mock_skill_resolver: object,
    *,
    run_id: str,
) -> Path:
    result = _run_v030_skill_dict(
        skill_root,
        thread_id=run_id,
        skill_resolver=mock_skill_resolver,
        workspace_dir=trace_dir,
        topic="observability",
        request_id=run_id,
    )
    assert result["run_id"] == run_id
    return trace_dir / "runs" / run_id / "trace.jsonl"


def _read_trace_events(trace_path: Path) -> list[dict[str, Any]]:
    assert trace_path.is_file(), f"trace.jsonl not found: {trace_path}"
    lines = [line for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, f"trace.jsonl is empty: {trace_path}"
    return [json.loads(line) for line in lines]


def _make_draft_phase_crash(skill_root: Path) -> None:
    _write(
        skill_root / "phases" / "draft" / "actions" / "draft.py",
        "def draft(context):\n"
        "    del context\n"
        "    raise RuntimeError('intentional trace crash')\n",
    )


def test_v030_skill_dict_writes_trace_jsonl_when_no_subscriber(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    """V0.3 _run_v030_skill_dict() should auto-write trace.jsonl without subscribers."""
    skill_root = tmp_path / "skill"
    trace_dir = tmp_path / "trace-output"
    run_id = "trace-auto-no-subscriber"
    _write_logic_skill(skill_root, [("draft", [])])

    trace_path = _run_without_subscriber(skill_root, trace_dir, mock_skill_resolver, run_id=run_id)
    events = _read_trace_events(trace_path)

    assert events[0]["event_type"] == "run_started"
    assert events[0]["run_id"] == run_id
    assert events[-1]["event_type"] == "run_ended"
    assert events[-1]["run_id"] == run_id
    assert events[-1]["status"] == "completed"


def test_v030_skill_dict_trace_records_phase_events(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    """trace.jsonl should record real phase_start and phase_end for every V0.3 phase."""
    skill_root = tmp_path / "skill"
    trace_dir = tmp_path / "trace-output"
    _write_logic_skill(skill_root, [("draft", []), ("review", ["draft"])])

    trace_path = _run_without_subscriber(
        skill_root,
        trace_dir,
        mock_skill_resolver,
        run_id="trace-auto-phase-events",
    )
    events = _read_trace_events(trace_path)

    phase_starts = [event for event in events if event["event_type"] == "phase_start"]
    phase_ends = [event for event in events if event["event_type"] == "phase_end"]
    assert [event["phase_name"] for event in phase_starts] == ["draft", "review"]
    assert [event["phase_name"] for event in phase_ends] == ["draft", "review"]
    assert [
        (event["event_type"], event.get("phase_name"))
        for event in events
        if event["event_type"] in {"phase_start", "phase_end"}
    ] == [
        ("phase_start", "draft"),
        ("phase_end", "draft"),
        ("phase_start", "review"),
        ("phase_end", "review"),
    ]


def test_v030_skill_dict_trace_includes_phase_io(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    """phase trace events should carry declared runtime inputs and phase outputs."""
    skill_root = tmp_path / "skill"
    trace_dir = tmp_path / "trace-output"
    _write_logic_skill(skill_root, [("draft", [])])

    trace_path = _run_without_subscriber(
        skill_root,
        trace_dir,
        mock_skill_resolver,
        run_id="trace-auto-phase-io",
    )
    events = _read_trace_events(trace_path)

    phase_start = next(event for event in events if event["event_type"] == "phase_start")
    phase_end = next(event for event in events if event["event_type"] == "phase_end")
    assert phase_start["context"]["inputs"] == {
        "topic": "observability",
        "request_id": "trace-auto-phase-io",
    }
    assert phase_end["context"]["phase_outputs"]["draft"] == {"answer": "draft:observability"}


def test_v030_skill_dict_writes_trace_when_phase_crashes(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    """A crashed V0.3 run should still leave a replayable trace.jsonl."""
    skill_root = tmp_path / "skill"
    trace_dir = tmp_path / "trace-output"
    run_id = "trace-auto-crashed"
    _write_logic_skill(skill_root, [("draft", [])])
    _make_draft_phase_crash(skill_root)

    with pytest.raises(Exception, match="intentional trace crash"):
        _run_v030_skill_dict(
            skill_root,
            thread_id=run_id,
            skill_resolver=mock_skill_resolver,
            workspace_dir=trace_dir,
            topic="observability",
            request_id=run_id,
        )

    trace_path = trace_dir / "runs" / run_id / "trace.jsonl"
    events = _read_trace_events(trace_path)

    assert events[-1]["event_type"] == "run_ended"
    assert events[-1]["run_id"] == run_id
    assert events[-1]["status"] == "crashed"
    assert any(
        event["event_type"] == "phase_start" and event["phase_name"] == "draft"
        for event in events
    )
