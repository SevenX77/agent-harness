"""Tests for GraphAgent custom middleware assembly."""

from __future__ import annotations

from typing import Any

from graph_agent.cognitive.middlewares import create_custom_middlewares


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
    def test_loop_detection_enabled_by_default(self) -> None:
        middlewares = create_custom_middlewares(phase_name="test")

        assert "LoopDetectionMiddleware" in _names(middlewares)

    def test_loop_detection_can_be_disabled(self) -> None:
        middlewares = create_custom_middlewares(
            phase_name="test",
            loop_detection=False,
        )

        assert "LoopDetectionMiddleware" not in _names(middlewares)

    def test_summarization_disabled_by_default(self) -> None:
        middlewares = create_custom_middlewares(phase_name="test")

        assert "SummarizationMiddleware" not in _names(middlewares)

    def test_summarization_enabled_with_model(self) -> None:
        mock_model = _FakeSummaryModel(profile={"max_input_tokens": 100_000})

        middlewares = create_custom_middlewares(
            phase_name="test",
            summarization=True,
            summarization_model=mock_model,
        )
        summary_mw = next(
            m for m in middlewares if type(m).__name__ == "SummarizationMiddleware"
        )

        assert summary_mw.trigger == ("fraction", 0.8)
        assert summary_mw.keep == ("messages", 20)

    def test_summarization_skipped_without_model(self) -> None:
        middlewares = create_custom_middlewares(
            phase_name="test",
            summarization=True,
            summarization_model=None,
        )

        assert "SummarizationMiddleware" not in _names(middlewares)

    def test_summarization_model_without_profile_gets_fallback_profile(self) -> None:
        middlewares = create_custom_middlewares(
            phase_name="test",
            summarization=True,
            summarization_model=_FakeSummaryModel(),
        )
        summary_mw = next(
            m for m in middlewares if type(m).__name__ == "SummarizationMiddleware"
        )

        assert summary_mw.model.profile["max_input_tokens"] == 32_000

    def test_loop_detection_warn_and_hard_limit_passed(self) -> None:
        middlewares = create_custom_middlewares(
            phase_name="test",
            loop_detection_warn_threshold=2,
            loop_detection_hard_limit=4,
        )
        loop_mw = next(
            m for m in middlewares if type(m).__name__ == "LoopDetectionMiddleware"
        )

        assert loop_mw.warn_threshold == 2
        assert loop_mw.hard_limit == 4

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
            "LoopDetectionMiddleware",
            "SummarizationMiddleware",
        ]
