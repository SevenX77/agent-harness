"""CognitiveFlowMiddleware interception for the migrated cognitive tools.

Migration decision 2026-08-15 (docs/design/2026-08-15-legacy-cognitive-features-
migration-decision.md) §3.2-§3.4: update_working_memory / log_ambiguity /
query_working_memory / read_artifact leave the dead ctx-injection family and
become CognitiveFlowMiddleware interceptions over ``FrameworkState``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from graph_agent.callbacks.events import AmbiguityLoggedEvent, WorkingMemoryUpdateEvent
from graph_agent.core.io_manager import IOManager
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware


class _EventSpy:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


def _state(
    *,
    data: BusinessData | None = None,
    flow: FrameworkState | None = None,
) -> WorkflowState:
    return {
        "data": data if data is not None else BusinessData(),
        "flow": flow if flow is not None else FrameworkState(),
        "messages": [],
    }


def _request(
    *,
    name: str,
    args: dict[str, Any] | None = None,
    state: WorkflowState | dict[str, Any] | None = None,
) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "id": "call-1", "args": args or {}},
        tool=None,
        state=state if state is not None else _state(),
        runtime=None,  # type: ignore[arg-type]
    )


def _handler(request: ToolCallRequest) -> ToolMessage:
    return ToolMessage(
        content="handled",
        name=str(request.tool_call.get("name") or ""),
        tool_call_id=str(request.tool_call.get("id") or ""),
    )


def _middleware(spy: _EventSpy | None = None) -> CognitiveFlowMiddleware:
    return CognitiveFlowMiddleware(
        IOManager([]),
        phase_name="main",
        callbacks=[spy] if spy is not None else None,
    )


class TestUpdateWorkingMemory:
    def test_writes_plan_key_and_keeps_existing_keys(self) -> None:
        middleware = _middleware()
        flow = FrameworkState(working_memory={"iterate_executions": [{"loop": 1}]})
        request = _request(
            name="update_working_memory",
            args={"plan": "step 1: draft"},
            state=_state(flow=flow),
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, Command)
        assert result.goto == "model"
        next_flow = result.update["flow"]
        assert next_flow.working_memory["plan"] == "step 1: draft"
        assert next_flow.working_memory["iterate_executions"] == [{"loop": 1}]
        messages = result.update["messages"]
        assert len(messages) == 1
        assert messages[0].name == "update_working_memory"
        assert messages[0].tool_call_id == "call-1"
        assert messages[0].content == "WORKING_MEMORY_UPDATED"

    def test_emits_typed_event_on_every_accepted_update(self) -> None:
        spy = _EventSpy()
        middleware = _middleware(spy)

        for plan in ("plan one", "plan two"):
            middleware.wrap_tool_call(
                _request(name="update_working_memory", args={"plan": plan}),
                _handler,
            )

        events = [e for e in spy.events if isinstance(e, WorkingMemoryUpdateEvent)]
        assert [event.content for event in events] == ["plan one", "plan two"]
        assert [event.content_length for event in events] == [8, 8]
        assert all(event.phase_name == "main" for event in events)


class TestLogAmbiguity:
    def test_appends_full_record_and_returns_recorded_json(self) -> None:
        middleware = _middleware()
        request = _request(
            name="log_ambiguity",
            args={
                "question": "Which locale?",
                "ambiguity_type": "missing_info",
                "decision": "assume zh-CN",
                "reason": "input corpus is Chinese",
            },
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, Command)
        assert result.goto == "model"
        reports = result.update["flow"].ambiguity_reports
        assert len(reports) == 1
        record = reports[0]
        assert record["phase"] == "main"
        assert record["type"] == "missing_info"
        assert record["question"] == "Which locale?"
        assert record["decision"] == "assume zh-CN"
        assert record["reason"] == "input corpus is Chinese"
        assert record["timestamp"]

        payload = json.loads(result.update["messages"][0].content)
        assert payload == {"status": "recorded", "index": 0, "type": "missing_info"}

    def test_appends_after_existing_reports(self) -> None:
        middleware = _middleware()
        flow = FrameworkState(ambiguity_reports=[{"question": "old"}])
        request = _request(
            name="log_ambiguity",
            args={
                "question": "New?",
                "ambiguity_type": "approach_choice",
                "decision": "keep it simple",
            },
            state=_state(flow=flow),
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, Command)
        reports = result.update["flow"].ambiguity_reports
        assert len(reports) == 2
        assert reports[0] == {"question": "old"}
        payload = json.loads(result.update["messages"][0].content)
        assert payload["index"] == 1

    def test_emits_event_with_reference_and_protocol_extraction(self) -> None:
        spy = _EventSpy()
        middleware = _middleware(spy)
        request = _request(
            name="log_ambiguity",
            args={
                "question": "Does @reference:Guide cover this?",
                "ambiguity_type": "ambiguous_requirement",
                "decision": "follow the guide",
                "reason": "per @protocol:review-loop",
            },
        )

        middleware.wrap_tool_call(request, _handler)

        events = [e for e in spy.events if isinstance(e, AmbiguityLoggedEvent)]
        assert len(events) == 1
        event = events[0]
        assert event.phase_name == "main"
        assert event.ambiguity_type == "ambiguous_requirement"
        assert event.related_refs == ["Guide"]
        assert event.related_protocols == ["review-loop"]


class TestQueryWorkingMemory:
    def test_returns_plan_text(self) -> None:
        middleware = _middleware()
        flow = FrameworkState(working_memory={"plan": "the plan"})
        request = _request(name="query_working_memory", state=_state(flow=flow))

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, ToolMessage)
        assert result.content == "the plan"
        assert result.name == "query_working_memory"
        assert result.tool_call_id == "call-1"

    def test_empty_plan_returns_placeholder(self) -> None:
        middleware = _middleware()
        request = _request(name="query_working_memory")

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, ToolMessage)
        assert result.content == "(empty)"

    def test_truncates_long_plan(self) -> None:
        middleware = _middleware()
        flow = FrameworkState(working_memory={"plan": "x" * 50_001})
        request = _request(name="query_working_memory", state=_state(flow=flow))

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, ToolMessage)
        assert isinstance(result.content, str)
        assert result.content.endswith("... [truncated]")
        assert len(result.content) == 50_000 + len("... [truncated]")


class TestReadArtifact:
    def test_reads_business_field(self) -> None:
        middleware = _middleware()
        request = _request(
            name="read_artifact",
            args={"name": "answer"},
            state=_state(data=BusinessData(answer="42")),
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, ToolMessage)
        assert result.content == "42"
        assert result.name == "read_artifact"

    def test_rejects_empty_name(self) -> None:
        middleware = _middleware()
        request = _request(name="read_artifact", args={"name": ""})

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, ToolMessage)
        assert "[read_artifact Error]" in str(result.content)
        assert "non-empty" in str(result.content)

    def test_rejects_framework_internal_prefix(self) -> None:
        middleware = _middleware()
        request = _request(name="read_artifact", args={"name": "_secret"})

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, ToolMessage)
        assert "[read_artifact Error]" in str(result.content)
        assert "framework-internal" in str(result.content)

    def test_missing_artifact_lists_visible_names(self) -> None:
        middleware = _middleware()
        request = _request(
            name="read_artifact",
            args={"name": "missing"},
            state=_state(data=BusinessData(answer="42")),
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, ToolMessage)
        content = str(result.content)
        assert "[read_artifact Error]" in content
        assert "not found" in content
        assert "answer" in content

    def test_truncates_long_value(self) -> None:
        middleware = _middleware()
        request = _request(
            name="read_artifact",
            args={"name": "answer"},
            state=_state(data=BusinessData(answer="y" * 50_001)),
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, ToolMessage)
        assert str(result.content).endswith("... [truncated]")


class TestGateAndParity:
    def test_state_tools_pass_through_without_workflow_state(self) -> None:
        middleware = _middleware()
        for tool_name in (
            "update_working_memory",
            "log_ambiguity",
            "query_working_memory",
            "read_artifact",
        ):
            request = _request(name=tool_name, state={"messages": []})

            result = middleware.wrap_tool_call(request, _handler)

            assert isinstance(result, ToolMessage), tool_name
            assert result.content == "handled", tool_name

    def test_dispatch_gate_covers_all_cognitive_tools(self) -> None:
        for tool_name in (
            "finish_task",
            "ask_clarification",
            "update_working_memory",
            "log_ambiguity",
            "query_working_memory",
            "read_artifact",
        ):
            result = CognitiveFlowMiddleware.dispatch_tool_call(
                tool_name=tool_name,
                args={},
                state={"phase_name": "main"},
                handler=lambda name, args: {"passed_through": name},
            )

            assert result == {"handled": False, "tool_name": tool_name, "args": {}}, tool_name

    def test_awrap_tool_call_intercepts_update_working_memory(self) -> None:
        middleware = _middleware()
        request = _request(name="update_working_memory", args={"plan": "async plan"})

        async def handler(req: ToolCallRequest) -> ToolMessage:
            return _handler(req)

        result = asyncio.run(middleware.awrap_tool_call(request, handler))

        assert isinstance(result, Command)
        assert result.update["flow"].working_memory["plan"] == "async plan"

    def test_awrap_tool_call_intercepts_read_artifact(self) -> None:
        middleware = _middleware()
        request = _request(
            name="read_artifact",
            args={"name": "answer"},
            state=_state(data=BusinessData(answer="ok")),
        )

        async def handler(req: ToolCallRequest) -> ToolMessage:
            return _handler(req)

        result = asyncio.run(middleware.awrap_tool_call(request, handler))

        assert isinstance(result, ToolMessage)
        assert result.content == "ok"

    def test_public_intercept_api_handles_state_tools(self) -> None:
        middleware = _middleware()

        handled, result = middleware.intercept_tool_call(
            "update_working_memory",
            {"plan": "via public api"},
            _state(),
        )

        assert handled is True
        assert isinstance(result, Command)
        assert result.update["flow"].working_memory["plan"] == "via public api"
