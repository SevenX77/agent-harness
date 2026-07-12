from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import (
    AmbiguityLoggedEvent,
    BuiltinSubagentEnterEvent,
    BuiltinSubagentExitEvent,
    BuiltinSubagentFallbackEvent,
)
from graph_agent.cognitive.ambiguity import log_ambiguity
from graph_agent.core.callback_bridge import _HarnessCallbackBridge
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.loader import load_workflow_from_md
from graph_agent.core.tool_wrapper import _wrap_tool_for_langchain


class CollectorCallback(Callback):
    def __init__(self) -> None:
        self.events: list[Any] = []
        self.tool_calls: list[dict[str, Any]] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)

    def on_tool_call(
        self,
        phase_name: str,
        tool_name: str,
        args: dict[str, Any],
        result: str,
        *,
        duration_ms: float | None = None,
    ) -> None:
        self.tool_calls.append(
            {
                "phase_name": phase_name,
                "tool_name": tool_name,
                "args": args,
                "result": result,
                "duration_ms": duration_ms,
            }
        )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _agent_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: pr-e-reference-reader
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - main
---
<phase depends_on="input" output>main</phase>
""",
    )
    _write(
        root / "phases" / "main" / "SKILL.md",
        """---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
tools:
  - finish_task
references:
  - id: Guide
    path: references/guide.md
    summary: Guide reference
---
<role>
Reader.
</role>
<goal>
Use @reference:Guide.
</goal>
""",
    )
    _write(root / "references" / "guide.md", "SENTINEL_RAW_REFERENCE " * 80)


def _event_types(events: list[Any]) -> list[str]:
    return [str(getattr(event, "event_type", "")) for event in events]


def test_e1_runtime_tool_path_keeps_tool_trace_and_emits_ambiguity_logged() -> None:
    collector = CollectorCallback()
    bridge = _HarnessCallbackBridge("main", [collector], {})
    tool_ctx = {"_current_phase": "main"}
    tool = _wrap_tool_for_langchain(log_ambiguity, tool_ctx)

    result = json.loads(
        tool.invoke(
            {
                "question": "How should @reference:R1 be interpreted?",
                "ambiguity_type": "ambiguous_requirement",
                "decision": "Use conservative reading.",
                "reason": "Protocol @protocol:P1 is closest.",
            },
            config={"callbacks": [bridge]},
        )
    )

    assert result["status"] == "recorded"
    assert any(call["tool_name"] == "log_ambiguity" for call in collector.tool_calls)

    ambiguity_events = [
        event for event in collector.events if isinstance(event, AmbiguityLoggedEvent)
    ]
    assert len(ambiguity_events) == 1
    event = ambiguity_events[0]
    assert event.phase_name == "main"
    assert event.ambiguity_type == "ambiguous_requirement"
    assert event.question == "How should @reference:R1 be interpreted?"
    assert event.decision == "Use conservative reading."
    assert event.reason == "Protocol @protocol:P1 is closest."
    assert event.related_refs == ["R1"]
    assert event.related_protocols == ["P1"]


def test_e2_reference_reader_success_emits_enter_then_exit_from_loader_callbacks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    class SuccessfulReaderRuntime:
        def __init__(self, **kwargs: Any) -> None:
            self.phase_id = kwargs["phase_id"]
            self.references = kwargs["references"]

        def run(self) -> dict[str, str]:
            return {"markdown": "## refined\n\nshort refined knowledge"}

    monkeypatch.setattr(
        "graph_agent.core.graph_assembler.ReferenceReaderRuntime",
        SuccessfulReaderRuntime,
    )
    _agent_skill(tmp_path)
    collector = CollectorCallback()

    load_workflow_from_md(tmp_path, callbacks=[collector], skill_resolver=mock_skill_resolver)

    assert _event_types(collector.events) == [
        "builtin_subagent_enter",
        "builtin_subagent_exit",
    ]
    enter, exit_event = collector.events
    assert isinstance(enter, BuiltinSubagentEnterEvent)
    assert isinstance(exit_event, BuiltinSubagentExitEvent)
    assert enter.run_id is None
    assert exit_event.run_id is None
    assert enter.phase_name == "main"
    assert exit_event.phase_name == "main"
    assert enter.builtin_name == "reference_reader"
    assert exit_event.builtin_name == "reference_reader"
    assert "SENTINEL_RAW_REFERENCE" not in exit_event.model_dump_json()


@pytest.mark.parametrize(
    ("mode", "expected_reason"),
    [
        ("timeout", "remote_timeout"),
        ("remote_error", "remote_error"),
        ("missing_config", "config_missing"),
        ("invalid_output", "invalid_output"),
        ("local_io_error", "local_io_error"),
    ],
)
def test_e2_e3_reference_reader_fallback_emits_slim_payload_for_each_reason(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: object,
    mode: str,
    expected_reason: str,
) -> None:
    class FailingReaderRuntime:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def run(self) -> dict[str, str]:
            if mode == "timeout":
                raise TimeoutError("reader timed out")
            if mode == "remote_error":
                raise RuntimeError("remote model unavailable")
            if mode == "missing_config":
                raise GraphAgentFatalError("[F-v3-reference-reader-failed] missing config")
            if mode == "local_io_error":
                raise OSError("local fallback read failed")
            return {"unexpected": "shape"}  # invalid_output

    monkeypatch.setattr(
        "graph_agent.core.graph_assembler.ReferenceReaderRuntime",
        FailingReaderRuntime,
    )
    _agent_skill(tmp_path)
    collector = CollectorCallback()

    load_workflow_from_md(tmp_path, callbacks=[collector], skill_resolver=mock_skill_resolver)

    assert _event_types(collector.events) == [
        "builtin_subagent_enter",
        "builtin_subagent_fallback",
    ]
    enter, fallback = collector.events
    assert isinstance(enter, BuiltinSubagentEnterEvent)
    assert isinstance(fallback, BuiltinSubagentFallbackEvent)
    assert fallback.run_id is None
    assert fallback.phase_name == "main"
    assert fallback.builtin_name == "reference_reader"
    assert fallback.fallback_reason == expected_reason
    assert fallback.fallback_strategy
    assert fallback.excerpt_token_limit == 3000
    assert fallback.warning
    serialized = fallback.model_dump_json()
    assert "warning_message" not in serialized
    assert "SENTINEL_RAW_REFERENCE" not in serialized
    assert "系统无法完成知识精炼" not in serialized
