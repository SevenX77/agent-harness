"""RED tests for WS-E2 middleware tail-slot contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

import graph_agent.core.graph_assembler as graph_assembler
from graph_agent.callbacks.base import Callback
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.io_manager import IOManager
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.middleware import MVP0_MIDDLEWARE_ORDER_CONTRACT
from graph_agent.middleware.factory import build_middleware_chain
from graph_agent.middleware.loop_detection import LoopDetectionMiddleware
from graph_agent.middleware.tool_error import ToolErrorHandlingMiddleware
from graph_agent.middleware.tracing import TracingMiddleware


class _RecordingCallback(Callback):
    def __init__(self) -> None:
        self.events: list[Any] = []
        self.tool_calls: list[tuple[str, str, dict[str, Any], str]] = []

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
        del duration_ms
        self.tool_calls.append((phase_name, tool_name, args, result))


def _state(messages: list[Any] | None = None) -> WorkflowState:
    return {
        "data": BusinessData(),
        "flow": FrameworkState(thread_id="run-1"),
        "messages": messages if messages is not None else [],
    }


def _request(
    *,
    name: str = "lookup",
    args: dict[str, Any] | None = None,
    call_id: str = "call-1",
) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "id": call_id, "args": args or {}},
        tool=None,
        state=_state(),
        runtime=None,  # type: ignore[arg-type]
    )


def _tool_message(
    *,
    name: str = "lookup",
    content: str = "same args",
    call_id: str = "call-1",
    status: str | None = None,
) -> ToolMessage:
    msg = ToolMessage(content=content, name=name, tool_call_id=call_id)
    if status is not None:
        msg.status = status  # type: ignore[attr-defined]
    return msg


def test_tool_error_converts_tool_exception_to_error_tool_message() -> None:
    middleware = ToolErrorHandlingMiddleware(phase_name="main")
    request = _request(name="explode", args={"topic": "contracts"}, call_id="tool-1")

    def handler(_request: ToolCallRequest) -> ToolMessage:
        raise RuntimeError("boom")

    try:
        result = middleware.wrap_tool_call(request, handler)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            "ToolError must convert ordinary tool exceptions into "
            f"ToolMessage(status='error'), not raise {type(exc).__name__}: {exc}"
        )

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.name == "explode"
    assert result.tool_call_id == "tool-1"
    assert "main" in str(result.content)
    assert "explode" in str(result.content)
    assert "boom" in str(result.content)


def test_tracing_tail_slot_records_tool_context_from_factory_callbacks() -> None:
    callback = _RecordingCallback()
    chain = build_middleware_chain(
        io_manager=IOManager([]),
        phase_name="main",
        callbacks=[callback],
    )
    tracing = next(m for m in chain if isinstance(m, TracingMiddleware))
    request = _request(name="lookup", args={"topic": "contracts"}, call_id="tool-1")
    expected = _tool_message(name="lookup", content="lookup:contracts", call_id="tool-1")

    def handler(_request: ToolCallRequest) -> ToolMessage:
        return expected

    try:
        result = tracing.wrap_tool_call(request, handler)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            "Tracing must participate in the tool hook and pass through "
            f"the handler result, not raise {type(exc).__name__}: {exc}"
        )

    assert result is expected
    typed_tool_events = [
        event
        for event in callback.events
        if getattr(event, "event_type", None) == "tool_call"
    ]
    assert callback.tool_calls or typed_tool_events

    if callback.tool_calls:
        assert callback.tool_calls == [
            ("main", "lookup", {"topic": "contracts"}, "lookup:contracts")
        ]
    else:
        event = typed_tool_events[0]
        assert event.phase_name == "main"
        assert event.tool_name == "lookup"
        assert event.args == {"topic": "contracts"}
        assert event.result == "lookup:contracts"


def test_loop_detection_reports_repeated_no_progress_tool_loop() -> None:
    middleware = LoopDetectionMiddleware(phase_name="main")
    repeated = [
        _tool_message(name="search", content='{"q": "contracts"}', call_id="call-1"),
        _tool_message(name="search", content='{"q": "contracts"}', call_id="call-2"),
        _tool_message(name="search", content='{"q": "contracts"}', call_id="call-3"),
    ]

    try:
        result = middleware.after_model(_state(messages=repeated), runtime=None)  # type: ignore[arg-type]
    except GraphAgentFatalError as exc:
        diagnostic = str(exc)
        assert "main" in diagnostic
        assert "search" in diagnostic
        return

    assert result is not None, (
        "LoopDetection must not silently return None for a repeated "
        "no-progress tool loop"
    )
    diagnostic_messages = result.get("messages", [])
    assert diagnostic_messages, "LoopDetection diagnostic must be visible to the loop"
    diagnostic_text = "\n".join(str(msg.content) for msg in diagnostic_messages)
    assert "main" in diagnostic_text
    assert "search" in diagnostic_text


def test_factory_keeps_tail_slots_in_mvp1_contract_order() -> None:
    chain = build_middleware_chain(io_manager=IOManager([]), phase_name="main")

    def contract_name(middleware: object) -> str:
        name = type(middleware).__name__.removesuffix("Middleware")
        if name == "ToolErrorHandling":
            return "ToolError"
        return name

    assert tuple(contract_name(middleware) for middleware in chain) == (
        MVP0_MIDDLEWARE_ORDER_CONTRACT
    )


def test_live_agent_assembly_passes_tail_slots_to_create_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _agent_skill(tmp_path)
    captured: dict[str, Any] = {}

    class _Agent:
        def invoke(self, input: Any, config: Any | None = None) -> Any:
            del config
            return input

    def fake_create_agent(**kwargs: Any) -> _Agent:
        captured["middleware"] = kwargs["middleware"]
        return _Agent()

    monkeypatch.setattr(graph_assembler, "create_agent", fake_create_agent, raising=False)

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph_assembler.assemble_graph(
        compiled,
        chat_model=object(),
        skill_resolver=mock_skill_resolver,
    )

    names = [type(middleware).__name__ for middleware in captured["middleware"]]
    tracing_index = names.index("TracingMiddleware")
    assert names[tracing_index : tracing_index + 3] == [
        "TracingMiddleware",
        "ToolErrorHandlingMiddleware",
        "LoopDetectionMiddleware",
    ]
    assert names[tracing_index + 3] == "ExitControlMiddleware"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _agent_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: ws-e2-tail-slots
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
max_iterations: 1
llm_role: graph_agent
tools:
  - lookup
  - finish_task
---
<role>
Middleware verifier.
</role>
<goal>
Call @tool:lookup and then @tool:finish_task.
</goal>
""",
    )
    _write(
        root / "phases" / "main" / "tools" / "lookup.py",
        "def lookup(topic: str) -> str:\n"
        "    return f'lookup:{topic}'\n",
    )
