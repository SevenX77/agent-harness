"""Predict-mode GatewayChatModel subclass skeleton."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, cast

from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult

from graph_agent.callbacks.base import Callback
from graph_agent.config.llm_config import ResolvedRole
from graph_agent.core._predict_internal.strategy import BaseMockStrategy
from graph_agent.models.gateway_chat_model import GatewayChatModel


class PredictGatewayChatModel(GatewayChatModel):
    """Gateway subclass used only for Predict-bound model resolver instances."""

    mock_strategy: BaseMockStrategy

    def __init__(
        self,
        role_name: str,
        resolved_role: ResolvedRole,
        *,
        mock_strategy: BaseMockStrategy,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        callbacks: Sequence[Callback] = (),
        phase_name: str | None = None,
        probe_before_call: bool = True,
        thinking_enabled: bool | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs["mock_strategy"] = mock_strategy
        super().__init__(
            role_name,
            resolved_role,
            max_tokens=max_tokens,
            temperature=temperature,
            callbacks=callbacks,
            phase_name=phase_name,
            probe_before_call=probe_before_call,
            thinking_enabled=thinking_enabled,
            **kwargs,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Predict short-circuit hook; concrete P0/P1/P2 behavior lands in P-T5."""
        raise NotImplementedError("PredictGatewayChatModel._generate is implemented in P-T5")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async Predict short-circuit hook; concrete behavior lands in P-T5."""
        raise NotImplementedError("PredictGatewayChatModel._agenerate is implemented in P-T5")

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Streaming Predict hook; fake chunk iterator behavior lands in P-T5."""
        raise NotImplementedError("PredictGatewayChatModel._astream is implemented in P-T5")
        yield cast(ChatGenerationChunk, None)


__all__ = ["PredictGatewayChatModel"]
