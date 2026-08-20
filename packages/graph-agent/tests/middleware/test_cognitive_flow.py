"""Tests for MVP-3 T8 CognitiveFlowMiddleware."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.graph import END
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from pydantic import BaseModel, Field

from graph_agent.core.io_manager import IODef, IOManager
from graph_agent.core.schema_engine import SchemaEngine, SchemaObject, ValidationResult
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware

VALID_BUSINESS_MD = """## item-1
- title: Scene plan
- score: 3
"""

INVALID_BUSINESS_MD = """## item-1
- title: Scene plan
- score: high
"""


class SpySchemaEngine(SchemaEngine):
    def __init__(self) -> None:
        super().__init__()
        self.validate_calls = 0

    def validate(self, data: Any, schema: SchemaObject) -> ValidationResult:
        self.validate_calls += 1
        return super().validate(data, schema)


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
    args: dict[str, Any] | str | None = None,
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


def _schema() -> SchemaObject:
    return SchemaEngine().parse_from_md("title: str\nscore: int")


class TestInit:
    def test_init_minimal(self) -> None:
        middleware = CognitiveFlowMiddleware(IOManager([]))

        assert middleware.name == "CognitiveFlowMiddleware"


class TestPassThrough:
    def test_other_tool_passes_through(self) -> None:
        middleware = CognitiveFlowMiddleware(IOManager([]))
        request = _request(name="lookup", args={"q": "x"})

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, ToolMessage)
        assert result.content == "handled"

    def test_finish_passes_through_without_workflow_state(self) -> None:
        middleware = CognitiveFlowMiddleware(IOManager([]))
        request = _request(
            name="finish_task",
            args={"business_data_md": VALID_BUSINESS_MD},
            state={"messages": []},
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, ToolMessage)
        assert result.content == "handled"


class TestFinishTask:
    def test_finish_validates_and_hoists_business_data(self) -> None:
        engine = SpySchemaEngine()
        schema = engine.parse_from_md("title: str\nscore: int")
        middleware = CognitiveFlowMiddleware(
            IOManager([IODef(source_field="business_data_parsed", target_field="items")]),
            schema_engine=engine,
            current_phase_schema=schema,
            phase_name="segment",
        )
        state = _state()
        request = _request(
            name="finish_task",
            args={
                "reasoning": "done",
                "diagnostics_md": "ok",
                "business_data_md": VALID_BUSINESS_MD,
            },
            state=state,
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, Command)
        assert result.goto != END
        assert engine.validate_calls == 1
        new_data = result.update["data"]
        assert isinstance(new_data, BusinessData)
        assert new_data["items"] == [{"title": "Scene plan", "score": 3}]
        new_flow = result.update["flow"]
        assert isinstance(new_flow, FrameworkState)
        assert new_flow.finish_task_result == {
            # The marker names its producing phase so the NEXT phase's exit
            # gate cannot mistake it for its own completion.
            "phase_name": "segment",
            "reasoning": "done",
            "diagnostics_md": "ok",
            "business_data_md": VALID_BUSINESS_MD.strip(),
            "schema_validation": "passed",
            "business_data_parsed": [{"title": "Scene plan", "score": 3}],
        }
        assert state["flow"].finish_task_result is None
        message = result.update["messages"][0]
        assert isinstance(message, ToolMessage)
        assert message.name == "finish_task"
        assert message.tool_call_id == "call-1"

    def test_finish_invalid_json_returns_llm_feedback(self) -> None:
        middleware = CognitiveFlowMiddleware(IOManager([]), current_phase_schema=_schema())
        request = _request(name="finish_task", args="{bad json")

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, Command)
        assert result.goto == "model"
        message = result.update["messages"][0]
        assert isinstance(message, ToolMessage)
        assert message.status == "error"
        assert message.name == "finish_task"
        assert "JSON parse failed" in str(message.content)

    def test_finish_rejects_schema_validation_errors(self) -> None:
        middleware = CognitiveFlowMiddleware(
            IOManager([]),
            current_phase_schema=_schema(),
            phase_name="segment",
        )
        request = _request(
            name="finish_task",
            args={"business_data_md": INVALID_BUSINESS_MD},
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, Command)
        assert result.goto == "model"
        message = result.update["messages"][0]
        assert isinstance(message, ToolMessage)
        assert message.status == "error"
        assert "提交已被系统驳回" in str(message.content)
        assert "score" in str(message.content)

    def test_finish_records_io_errors_in_framework_state(self) -> None:
        middleware = CognitiveFlowMiddleware(
            IOManager([IODef(source_field="missing", target_field="target")]),
            current_phase_schema=_schema(),
        )
        state = _state(flow=FrameworkState(io_errors=["prior"]))
        request = _request(
            name="finish_task",
            args={"business_data_md": VALID_BUSINESS_MD},
            state=state,
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, Command)
        new_flow = result.update["flow"]
        assert isinstance(new_flow, FrameworkState)
        assert new_flow.io_errors == [
            "prior",
            "required io.output 'missing' missing in source_data",
        ]

    def test_public_intercept_api_handles_finish_task(self) -> None:
        middleware = CognitiveFlowMiddleware(
            IOManager([]),
            current_phase_schema=_schema(),
        )
        state = _state()

        handled, result = middleware.intercept_tool_call(
            "finish_task",
            {"business_data_md": VALID_BUSINESS_MD},
            state,
        )

        assert handled is True
        assert isinstance(result, Command)
        assert result.goto != END
        new_flow = result.update["flow"]
        assert isinstance(new_flow, FrameworkState)
        assert new_flow.finish_task_result["schema_validation"] == "passed"

    def test_finish_without_schema_raises_phase_2_a1(self) -> None:
        import pytest

        from graph_agent.middleware.cognitive_flow import CognitiveFlowError

        middleware = CognitiveFlowMiddleware(IOManager([]), phase_name="segment")
        state = _state()
        request = _request(
            name="finish_task",
            args={"business_data_md": VALID_BUSINESS_MD},
            state=state,
        )

        with pytest.raises(CognitiveFlowError, match="Phase 2 A1"):
            middleware.wrap_tool_call(request, _handler)


class TestClarification:
    def test_attended_clarification_falls_back_to_end_turn_message(self) -> None:
        middleware = CognitiveFlowMiddleware(IOManager([]), phase_name="clarify")
        request = _request(
            name="ask_clarification",
            args={
                "question": "Which policy?",
                "clarification_type": "approach_choice",
                "context": "Two valid options exist",
                "options": ["A", "B"],
            },
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, Command)
        assert result.goto == END
        message = result.update["messages"][0]
        assert isinstance(message, ToolMessage)
        assert message.id == "clarification:call-1"
        assert message.name == "ask_clarification"
        assert "Approach choice: Two valid options exist" in str(message.content)
        assert "Which policy?" in str(message.content)
        assert "1. A" in str(message.content)

    def test_attended_clarification_uses_interrupt_answer_when_available(self) -> None:
        seen_payloads: list[dict[str, Any]] = []

        def fake_interrupt(payload: dict[str, Any]) -> str:
            seen_payloads.append(payload)
            return "Use the conservative option."

        middleware = CognitiveFlowMiddleware(
            IOManager([]),
            phase_name="clarify",
            interrupt_fn=fake_interrupt,
        )
        request = _request(
            name="ask_clarification",
            args={"question": "Which policy?"},
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, Command)
        assert result.goto == "model"
        assert seen_payloads[0]["phase_name"] == "clarify"
        assert seen_payloads[0]["tool"] == "ask_clarification"
        message = result.update["messages"][0]
        assert isinstance(message, ToolMessage)
        assert message.content == "Use the conservative option."

    def test_unattended_clarification_auto_answers_and_returns_to_model(self) -> None:
        middleware = CognitiveFlowMiddleware(IOManager([]), unattended=True)
        request = _request(
            name="ask_clarification",
            args={"question": "Need a user choice?"},
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, Command)
        assert result.goto == "model"
        message = result.update["messages"][0]
        assert isinstance(message, ToolMessage)
        assert message.name == "ask_clarification"
        assert "unattended=True" in str(message.content)
        assert "Need a user choice?" in str(message.content)


class TestPhase2A2v3PydanticSchemaDispatch:
    """PHASE2_DESIGN.md §3.4 step 1+2: ``current_phase_schema`` accepts
    ``type[BaseModel]`` for dotted-path SKILLs (e.g. text-segmentation
    pointing to ``script.models.Segment``). The middleware dispatches:
    ``SchemaObject`` keeps the schema-engine path; ``type[BaseModel]``
    bypasses the engine and validates each parsed block via
    ``schema_cls.model_validate`` directly.
    """

    def test_pydantic_class_dispatch_validates_via_model_validate(self) -> None:
        class _LiveSchema(BaseModel):
            title: str = Field(min_length=1)
            score: int = Field(ge=0, le=10)

        middleware = CognitiveFlowMiddleware(
            IOManager([IODef(source_field="business_data_parsed", target_field="items")]),
            current_phase_schema=_LiveSchema,
            phase_name="segment",
        )
        state = _state()
        request = _request(
            name="finish_task",
            args={
                "reasoning": "done",
                "diagnostics_md": "ok",
                "business_data_md": VALID_BUSINESS_MD,
            },
            state=state,
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, Command)
        assert result.goto != END
        new_data = result.update["data"]
        assert isinstance(new_data, BusinessData)
        # The Pydantic dispatch path must have produced the same parsed
        # items shape as the SchemaObject path so downstream consumers
        # are agnostic to schema kind.
        assert new_data["items"] == [{"title": "Scene plan", "score": 3}]

    def test_pydantic_class_dispatch_rejects_invalid_block_with_per_field_error(
        self,
    ) -> None:
        class _LiveSchema(BaseModel):
            title: str = Field(min_length=1)
            score: int = Field(ge=0, le=10)

        middleware = CognitiveFlowMiddleware(
            IOManager([]),
            current_phase_schema=_LiveSchema,
            phase_name="segment",
        )
        request = _request(
            name="finish_task",
            args={"business_data_md": INVALID_BUSINESS_MD},  # score: high
        )

        result = middleware.wrap_tool_call(request, _handler)

        assert isinstance(result, Command)
        assert result.goto == "model"
        message = result.update["messages"][0]
        assert isinstance(message, ToolMessage)
        assert message.status == "error"
        text = str(message.content)
        assert "提交已被系统驳回" in text
        # The per-field diagnostic must surface the offending field name
        # so the LLM can correct its markdown on retry.
        assert "score" in text
