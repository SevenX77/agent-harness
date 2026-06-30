"""RED tests for WS-E7 Engine resume contracts."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

import graph_agent
from graph_agent.core.checkpointer import get_checkpointer, reset_checkpointer
from graph_agent.core.result import RunResult
from graph_agent.core.runner import run_skill


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _public_callable(name: str) -> Callable[..., Any]:
    value = getattr(graph_agent, name, None)
    assert callable(value), f"graph_agent.{name} must be a public callable"
    return value


def _business_context(result: RunResult) -> dict[str, Any]:
    return result.context


def _schema(properties: dict[str, Any], *, required: list[str] | None = None) -> str:
    payload: dict[str, Any] = {"type": "object", "properties": properties}
    if required is not None:
        payload["required"] = required
    return json.dumps(payload, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _resume_logic_skill(root: Path) -> None:
    graph_input = _schema({"topic": {"type": "string"}}, required=["topic"])
    graph_output = _schema(
        {
            "draft": {"type": "string"},
            "final": {"type": "string"},
        },
        required=["draft", "final"],
    )
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e7-resume-red
io:
  inputs:
    {graph_input}
  outputs:
    {graph_output}
phases:
  - prepare
  - finish
---
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare" output>finish</phase>
""",
    )
    _write(
        root / "phases" / "prepare" / "LOGIC.md",
        f"""---
io:
  inputs:
    {graph_input}
  outputs:
    {_schema({"draft": {"type": "string"}}, required=["draft"])}
actions: [prepare]
validator: false
---
<action>prepare</action>
""",
    )
    _write(
        root / "phases" / "prepare" / "actions" / "prepare.py",
        dedent(
            """
            def prepare(inputs):
                return {"draft": f"draft:{inputs['topic']}"}
            """
        ).lstrip(),
    )
    _write(
        root / "phases" / "finish" / "LOGIC.md",
        f"""---
io:
  inputs:
    {_schema({"draft": {"type": "string"}}, required=["draft"])}
  outputs:
    {_schema({"final": {"type": "string"}}, required=["final"])}
actions: [finish]
validator: false
---
<action>finish</action>
""",
    )
    _write(
        root / "phases" / "finish" / "actions" / "finish.py",
        dedent(
            """
            def finish(inputs):
                return {"final": f"final:{inputs['draft']}"}
            """
        ).lstrip(),
    )


def _abc_resume_logic_skill(root: Path) -> None:
    graph_input = _schema({"topic": {"type": "string"}}, required=["topic"])
    graph_output = _schema(
        {
            "a": {"type": "string"},
            "b": {"type": "string"},
            "c": {"type": "string"},
        },
        required=["a", "b", "c"],
    )
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e7-abc-resume-red
io:
  inputs:
    {graph_input}
  outputs:
    {graph_output}
phases:
  - alpha
  - beta
  - gamma
---
<phase depends_on="input">alpha</phase>
<phase depends_on="alpha">beta</phase>
<phase depends_on="beta" output>gamma</phase>
""",
    )

    phase_specs = {
        "alpha": (
            _schema({"topic": {"type": "string"}}, required=["topic"]),
            _schema({"a": {"type": "string"}}, required=["a"]),
            'return {"a": f"a:{inputs[\'topic\']}"}',
        ),
        "beta": (
            _schema({"a": {"type": "string"}}, required=["a"]),
            _schema({"b": {"type": "string"}}, required=["b"]),
            'return {"b": f"b:{inputs[\'a\']}"}',
        ),
        "gamma": (
            _schema({"b": {"type": "string"}}, required=["b"]),
            _schema({"c": {"type": "string"}}, required=["c"]),
            'return {"c": f"c:{inputs[\'b\']}"}',
        ),
    }
    for phase_name, (inputs_schema, outputs_schema, return_line) in phase_specs.items():
        _write(
            root / "phases" / phase_name / "LOGIC.md",
            f"""---
io:
  inputs:
    {inputs_schema}
  outputs:
    {outputs_schema}
actions: [{phase_name}]
validator: false
---
<action>{phase_name}</action>
""",
        )
        _write(
            root / "phases" / phase_name / "actions" / f"{phase_name}.py",
            dedent(
                f"""
                def {phase_name}(inputs):
                    {return_line}
                """
            ).lstrip(),
        )


def _checkpoint_id_with_draft_without_final(run_id: str) -> str:
    saver = get_checkpointer()
    for checkpoint in saver.list({"configurable": {"thread_id": run_id, "checkpoint_ns": ""}}):
        values = checkpoint.checkpoint.get("channel_values", {})
        data = values.get("data")
        if hasattr(data, "model_dump"):
            data = data.model_dump()
        if isinstance(data, dict) and "draft" in data and "final" not in data:
            return str(checkpoint.checkpoint["id"])
    raise AssertionError("expected a checkpoint after prepare and before finish")


def _checkpoint_id_with_b_without_c(run_id: str) -> str:
    saver = get_checkpointer()
    for checkpoint in saver.list({"configurable": {"thread_id": run_id, "checkpoint_ns": ""}}):
        values = checkpoint.checkpoint.get("channel_values", {})
        data = values.get("data")
        if hasattr(data, "model_dump"):
            data = data.model_dump()
        if isinstance(data, dict) and "b" in data and "c" not in data:
            return str(checkpoint.checkpoint["id"])
    raise AssertionError("expected a checkpoint after beta and before gamma")


def test_resume_skill_public_api_signature_is_locked() -> None:
    resume_skill = _public_callable("resume_skill")
    signature = inspect.signature(resume_skill)

    assert signature.return_annotation in (RunResult, "RunResult")
    assert signature.parameters["workspace_dir"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["workspace_dir"].default is inspect.Signature.empty
    assert signature.parameters["run_id"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["run_id"].default is inspect.Signature.empty
    assert "from_phase" in signature.parameters
    assert "checkpoint_id" in signature.parameters
    assert "checkpoint_ns" in signature.parameters
    assert "resume_from_node_id" in signature.parameters
    assert "resume_to_node_id" in signature.parameters
    assert "context_overrides" in signature.parameters
    assert "human_response" in signature.parameters
    assert signature.parameters["skill_resolver"].default is inspect.Signature.empty


def test_resume_rejects_relative_workspace_dir(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _resume_logic_skill(tmp_path / "skill")
    resume_skill = _public_callable("resume_skill")

    with pytest.raises((TypeError, ValueError), match="workspace_dir"):
        resume_skill(
            tmp_path / "skill",
            workspace_dir=Path("relative-workspace"),
            run_id="ws-e7-relative",
            checkpoint_ns="",
            context_overrides={"draft": "manual"},
            skill_resolver=mock_skill_resolver,
        )


def test_resume_from_checkpoint_applies_business_context_overrides_without_rerunning_upstream(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    run_id = "ws-e7-resume-inputs"
    _resume_logic_skill(skill_root)
    reset_checkpointer()
    try:
        resume_skill = _public_callable("resume_skill")
        initial = run_skill(
            skill_root,
            workspace_dir=workspace_dir,
            thread_id=run_id,
            cleanup_checkpoints_on_finish=False,
            skill_resolver=mock_skill_resolver,
            topic="alpha",
        )
        assert initial.success is True
        assert _business_context(initial)["final"] == "final:draft:alpha"
        checkpoint_id = _checkpoint_id_with_draft_without_final(run_id)

        resumed = resume_skill(
            skill_root,
            workspace_dir=workspace_dir,
            run_id=run_id,
            checkpoint_id=checkpoint_id,
            context_overrides={"topic": "manual-topic"},
            skill_resolver=mock_skill_resolver,
        )

        assert isinstance(resumed, RunResult)
        assert resumed.run_id == run_id
        assert resumed.success is True
        assert resumed.context["topic"] == "manual-topic"
        assert resumed.context["draft"] == "draft:alpha"
        assert resumed.context["final"] == "final:draft:alpha"
        run_dir = workspace_dir / "runs" / run_id
        assert (run_dir / "result.json").is_file()
        assert (run_dir / "final_state.json").is_file()
        assert (run_dir / "metrics.json").is_file()
        assert (run_dir / "trace.jsonl").is_file()
    finally:
        reset_checkpointer()


def test_resume_events_include_resolved_checkpoint_id(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    run_id = "ws-e7-resume-events-checkpoint"
    _resume_logic_skill(skill_root)
    reset_checkpointer()
    try:
        resume_skill = _public_callable("resume_skill")
        run_skill(
            skill_root,
            workspace_dir=workspace_dir,
            thread_id=run_id,
            cleanup_checkpoints_on_finish=False,
            skill_resolver=mock_skill_resolver,
            topic="alpha",
        )
        checkpoint_id = _checkpoint_id_with_draft_without_final(run_id)
        events: list[Any] = []

        resumed = resume_skill(
            skill_root,
            workspace_dir=workspace_dir,
            run_id=run_id,
            checkpoint_id=checkpoint_id,
            context_overrides={"draft": "event-draft"},
            event_subscriber=events.append,
            skill_resolver=mock_skill_resolver,
        )

        assert resumed.success is True
        resume_started = [
            event
            for event in events
            if getattr(event, "event_type", None) == "run_started"
            and getattr(event, "is_resume", False)
        ]
        resumed_events = [
            event for event in events if getattr(event, "event_type", None) == "resumed"
        ]
        assert resume_started
        assert resumed_events
        assert resume_started[0].checkpoint_id == checkpoint_id
        assert resumed_events[0].checkpoint_id == checkpoint_id
    finally:
        reset_checkpointer()


def test_node_resume_from_abc_checkpoint_reruns_only_downstream_node(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    run_id = "ws-e7-abc-node-resume"
    _abc_resume_logic_skill(skill_root)
    reset_checkpointer()
    try:
        resume_skill = _public_callable("resume_skill")
        initial = run_skill(
            skill_root,
            workspace_dir=workspace_dir,
            thread_id=run_id,
            cleanup_checkpoints_on_finish=False,
            skill_resolver=mock_skill_resolver,
            topic="alpha",
        )
        assert initial.success is True
        assert _business_context(initial)["c"] == "c:b:a:alpha"
        checkpoint_id = _checkpoint_id_with_b_without_c(run_id)

        resume_events: list[Any] = []
        resumed = resume_skill(
            skill_root,
            workspace_dir=workspace_dir,
            run_id=run_id,
            checkpoint_id=checkpoint_id,
            resume_from_node_id="beta",
            resume_to_node_id="gamma",
            context_overrides={"b": "b:manual"},
            event_subscriber=resume_events.append,
            skill_resolver=mock_skill_resolver,
        )

        assert resumed.success is True
        assert resumed.context["c"] == "c:b:manual"
        resumed_phase_starts = [
            getattr(event, "phase_name", None)
            for event in resume_events
            if getattr(event, "event_type", None) == "phase_start"
        ]
        assert resumed_phase_starts == ["gamma"]
    finally:
        reset_checkpointer()


def test_resume_from_phase_does_not_rerun_successful_upstream_phases(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    run_id = "ws-e7-resume-from-phase"
    _resume_logic_skill(skill_root)
    reset_checkpointer()
    try:
        resume_skill = _public_callable("resume_skill")
        initial = run_skill(
            skill_root,
            workspace_dir=workspace_dir,
            thread_id=run_id,
            cleanup_checkpoints_on_finish=False,
            skill_resolver=mock_skill_resolver,
            topic="alpha",
        )
        assert initial.success is True
        events: list[Any] = []

        resumed = resume_skill(
            skill_root,
            workspace_dir=workspace_dir,
            run_id=run_id,
            from_phase="finish",
            context_overrides={"draft": "draft:manual"},
            event_subscriber=events.append,
            skill_resolver=mock_skill_resolver,
        )

        assert resumed.success is True
        assert resumed.context["final"] == "final:draft:manual"
        resumed_phase_starts = [
            event.phase_name
            for event in events
            if getattr(event, "event_type", None) == "phase_start"
        ]
        assert "finish" in resumed_phase_starts
        assert "prepare" not in resumed_phase_starts
    finally:
        reset_checkpointer()


def test_node_resume_rejects_context_override_from_dirty_upstream_node(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    run_id = "ws-e7-abc-dirty-upstream"
    _abc_resume_logic_skill(skill_root)
    reset_checkpointer()
    try:
        resume_skill = _public_callable("resume_skill")
        initial = run_skill(
            skill_root,
            workspace_dir=workspace_dir,
            thread_id=run_id,
            cleanup_checkpoints_on_finish=False,
            skill_resolver=mock_skill_resolver,
            topic="alpha",
        )
        assert initial.success is True
        checkpoint_id = _checkpoint_id_with_b_without_c(run_id)

        with pytest.raises(ValueError, match="dirty upstream|context_overrides"):
            resume_skill(
                skill_root,
                workspace_dir=workspace_dir,
                run_id=run_id,
                checkpoint_id=checkpoint_id,
                resume_from_node_id="beta",
                resume_to_node_id="gamma",
                context_overrides={"a": "a:dirty"},
                skill_resolver=mock_skill_resolver,
            )
    finally:
        reset_checkpointer()


@pytest.mark.parametrize(
    "forbidden_override",
    [
        {"_checkpoint_ns": "agent:prepare"},
        {"runtime": "not-persistent"},
        {"callbacks": ["not-persistent"]},
        {"compiled_graph": "not-persistent"},
        {"messages": ["not-business"]},
        {"tool_calls": [{"id": "tool-1"}]},
        {"configurable": {"thread_id": "other"}},
    ],
)
def test_resume_context_overrides_reject_non_business_state_fields(
    tmp_path: Path,
    mock_skill_resolver: object,
    forbidden_override: dict[str, Any],
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    run_id = "ws-e7-resume-forbidden-overrides"
    _resume_logic_skill(skill_root)
    reset_checkpointer()
    try:
        resume_skill = _public_callable("resume_skill")
        run_skill(
            skill_root,
            workspace_dir=workspace_dir,
            thread_id=run_id,
            cleanup_checkpoints_on_finish=False,
            skill_resolver=mock_skill_resolver,
            topic="alpha",
        )
        checkpoint_id = _checkpoint_id_with_draft_without_final(run_id)

        with pytest.raises((TypeError, ValueError), match="context_overrides|business"):
            resume_skill(
                skill_root,
                workspace_dir=workspace_dir,
                run_id=run_id,
                checkpoint_id=checkpoint_id,
                context_overrides=forbidden_override,
                skill_resolver=mock_skill_resolver,
            )
    finally:
        reset_checkpointer()


def test_resume_selector_preserves_checkpoint_namespace_boundaries(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    run_id = "ws-e7-resume-ns"
    _resume_logic_skill(skill_root)
    reset_checkpointer()
    try:
        resume_skill = _public_callable("resume_skill")
        run_skill(
            skill_root,
            workspace_dir=workspace_dir,
            thread_id=run_id,
            cleanup_checkpoints_on_finish=False,
            skill_resolver=mock_skill_resolver,
            topic="beta",
        )
        saver = get_checkpointer()
        outer = list(saver.list({"configurable": {"thread_id": run_id, "checkpoint_ns": ""}}))
        assert outer, "fixture must create outer checkpoints before resume"

        resumed = resume_skill(
            skill_root,
            workspace_dir=workspace_dir,
            run_id=run_id,
            checkpoint_ns="",
            context_overrides={"draft": "latest-outer"},
            skill_resolver=mock_skill_resolver,
        )

        assert resumed.success is True
        assert resumed.context["final"] == "final:latest-outer"
    finally:
        reset_checkpointer()


def test_resume_human_response_is_structured_and_plain_string_is_rejected(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _resume_logic_skill(tmp_path / "skill")
    resume_skill = _public_callable("resume_skill")

    with pytest.raises((TypeError, ValueError), match="human_response|content"):
        resume_skill(
            tmp_path / "skill",
            workspace_dir=tmp_path / "workspace",
            run_id="ws-e7-human-string",
            checkpoint_ns="",
            human_response="plain text is not the Engine contract",
            skill_resolver=mock_skill_resolver,
        )

    with pytest.raises((TypeError, ValueError), match="content"):
        resume_skill(
            tmp_path / "skill",
            workspace_dir=tmp_path / "workspace",
            run_id="ws-e7-human-missing-content",
            checkpoint_ns="",
            human_response={"tool_call_id": "tool-1"},
            skill_resolver=mock_skill_resolver,
        )


def test_resume_human_response_without_pending_tool_call_is_rejected(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    run_id = "ws-e7-human-no-pending"
    _resume_logic_skill(skill_root)
    reset_checkpointer()
    try:
        resume_skill = _public_callable("resume_skill")
        run_skill(
            skill_root,
            workspace_dir=workspace_dir,
            thread_id=run_id,
            cleanup_checkpoints_on_finish=False,
            skill_resolver=mock_skill_resolver,
            topic="alpha",
        )

        with pytest.raises((TypeError, ValueError), match="pending|tool call"):
            resume_skill(
                skill_root,
                workspace_dir=workspace_dir,
                run_id=run_id,
                checkpoint_ns="",
                human_response={"content": "there is no pending tool call"},
                skill_resolver=mock_skill_resolver,
            )
    finally:
        reset_checkpointer()
