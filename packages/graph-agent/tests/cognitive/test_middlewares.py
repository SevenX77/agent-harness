"""Tests for GraphAgent custom middleware assembly."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from graph_agent.cognitive.middlewares import (
    UnattendedClarificationMiddleware,
    create_custom_middlewares,
)


class _FakeSummaryModel:
    _llm_type = "fake-chat"

    def __init__(self, *, profile: dict[str, Any] | None = None) -> None:
        if profile is not None:
            self.profile = profile

    def _get_ls_params(self) -> dict[str, str]:
        return {"ls_provider": "fake"}

    def invoke(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("summary model should not be invoked during assembly")

    async def ainvoke(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("summary model should not be invoked during assembly")


def _names(middlewares: list[Any]) -> list[str]:
    return [type(m).__name__ for m in middlewares]


class TestCreateCustomMiddlewaresPR3:
    def test_loop_detection_not_mounted_in_mvp0(self) -> None:
        middlewares = create_custom_middlewares(phase_name="test")

        assert "LoopDetectionMiddleware" not in _names(middlewares)

    def test_loop_detection_can_be_disabled(self) -> None:
        middlewares = create_custom_middlewares(
            phase_name="test",
            loop_detection=False,
        )

        assert "LoopDetectionMiddleware" not in _names(middlewares)

    def test_summarization_disabled_by_default(self) -> None:
        middlewares = create_custom_middlewares(phase_name="test")

        assert "SummarizationMiddleware" not in _names(middlewares)

    def test_summarization_requested_but_not_mounted_in_mvp0(self) -> None:
        mock_model = _FakeSummaryModel(profile={"max_input_tokens": 100_000})

        middlewares = create_custom_middlewares(
            phase_name="test",
            summarization=True,
            summarization_model=mock_model,
        )
        assert "SummarizationMiddleware" not in _names(middlewares)

    def test_summarization_no_warning_when_model_has_profile_max_input_tokens(
        self,
        caplog: Any,
    ) -> None:
        mock_model = _FakeSummaryModel(profile={"max_input_tokens": 128_000})

        with caplog.at_level("WARNING", logger="graph_agent.cognitive.middlewares"):
            middlewares = create_custom_middlewares(
                phase_name="test",
                summarization=True,
                summarization_model=mock_model,
            )

        assert "SummarizationMiddleware" not in _names(middlewares)
        assert "using fallback max_input_tokens" not in caplog.text

    def test_summarization_uses_32k_fallback_when_model_has_no_profile(
        self,
        caplog: Any,
    ) -> None:
        with caplog.at_level("WARNING", logger="graph_agent.cognitive.middlewares"):
            middlewares = create_custom_middlewares(
                phase_name="test",
                summarization=True,
                summarization_model=_FakeSummaryModel(),
            )

        assert "SummarizationMiddleware" not in _names(middlewares)
        assert "using fallback max_input_tokens=32000" not in caplog.text

    def test_summarization_skipped_without_model(self) -> None:
        middlewares = create_custom_middlewares(
            phase_name="test",
            summarization=True,
            summarization_model=None,
        )

        assert "SummarizationMiddleware" not in _names(middlewares)

    def test_summarization_model_without_profile_not_mounted(self) -> None:
        middlewares = create_custom_middlewares(
            phase_name="test",
            summarization=True,
            summarization_model=_FakeSummaryModel(),
        )

        assert "SummarizationMiddleware" not in _names(middlewares)

    def test_loop_detection_warn_and_hard_limit_ignored(self) -> None:
        middlewares = create_custom_middlewares(
            phase_name="test",
            loop_detection_warn_threshold=2,
            loop_detection_hard_limit=4,
        )

        assert "LoopDetectionMiddleware" not in _names(middlewares)

    def test_existing_middleware_order_is_preserved(self) -> None:
        middlewares = create_custom_middlewares(
            phase_name="test",
            summarization=True,
            summarization_model=_FakeSummaryModel(profile={"max_input_tokens": 100_000}),
        )

        assert _names(middlewares) == [
            "AgentLoopIterationMiddleware",
            "WorkingMemoryMiddleware",
            "DeadEndPruningMiddleware",
            "ClarificationMiddleware",
        ]


class TestCreateCustomMiddlewaresPR5:
    def test_clarification_enabled_by_default(self) -> None:
        middlewares = create_custom_middlewares(phase_name="test")

        assert "ClarificationMiddleware" in _names(middlewares)

    def test_clarification_can_be_disabled(self) -> None:
        middlewares = create_custom_middlewares(
            phase_name="test",
            clarification=False,
        )

        assert "ClarificationMiddleware" not in _names(middlewares)


class TestUnattendedClarificationMiddleware:
    def test_unattended_context_replaces_hitl_clarification(self) -> None:
        middlewares = create_custom_middlewares(
            phase_name="test",
            context_ref={"_unattended": True},
        )

        names = _names(middlewares)
        assert "UnattendedClarificationMiddleware" in names
        assert "ClarificationMiddleware" not in names

    def test_attended_mode_keeps_hitl_clarification(self) -> None:
        middlewares = create_custom_middlewares(
            phase_name="test",
            context_ref={"_unattended": False},
        )

        names = _names(middlewares)
        assert "ClarificationMiddleware" in names
        assert "UnattendedClarificationMiddleware" not in names

    def test_intercepts_ask_clarification_in_unattended_mode(self) -> None:
        middleware = UnattendedClarificationMiddleware(unattended=True)
        request = _clarification_request(
            args={"question": "Which segmentation policy should I use?"}
        )
        called = False

        def handler(_request: ToolCallRequest) -> ToolMessage:
            nonlocal called
            called = True
            return ToolMessage(
                content="should not run",
                name="ask_clarification",
                tool_call_id="call_1",
            )

        result = middleware.wrap_tool_call(request, handler)

        assert called is False
        assert isinstance(result, Command)
        assert result.goto == "model"
        message = result.update["messages"][0]
        assert isinstance(message, ToolMessage)
        assert message.tool_call_id == "call_1"
        assert message.name == "ask_clarification"
        assert "unattended=True" in str(message.content)
        assert "Which segmentation policy" in str(message.content)

    def test_invalid_json_args_returns_llm_feedback(self) -> None:
        middleware = UnattendedClarificationMiddleware(
            unattended=True,
            phase_name="clarify_phase",
        )
        request = _clarification_request(args="{bad json")

        def handler(_request: ToolCallRequest) -> ToolMessage:
            raise AssertionError("ask_clarification handler should not run")

        result = middleware.wrap_tool_call(request, handler)

        assert isinstance(result, Command)
        assert result.goto == "model"
        message = result.update["messages"][0]
        assert isinstance(message, ToolMessage)
        assert message.status == "error"
        assert message.name == "ask_clarification"
        assert message.tool_call_id == "call_1"
        assert "JSON parse failed" in str(message.content)
        assert "Please retry with valid JSON" in str(message.content)

    def test_attended_mode_passes_through(self) -> None:
        middleware = UnattendedClarificationMiddleware(unattended=False)
        request = _clarification_request()
        expected = ToolMessage(
            content="handled",
            name="ask_clarification",
            tool_call_id="call_1",
        )

        def handler(_request: ToolCallRequest) -> ToolMessage:
            return expected

        assert middleware.wrap_tool_call(request, handler) is expected

    def test_other_tools_pass_through_in_unattended_mode(self) -> None:
        middleware = UnattendedClarificationMiddleware(unattended=True)
        request = _clarification_request(name="finish_task")
        expected = ToolMessage(
            content="handled",
            name="finish_task",
            tool_call_id="call_1",
        )

        def handler(_request: ToolCallRequest) -> ToolMessage:
            return expected

        assert middleware.wrap_tool_call(request, handler) is expected


def _clarification_request(
    *,
    name: str = "ask_clarification",
    args: dict[str, Any] | str | None = None,
) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={
            "name": name,
            "args": args or {"question": "Need input?"},
            "id": "call_1",
        },
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )
