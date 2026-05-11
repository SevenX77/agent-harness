"""Predict-mode GatewayChatModel subclass skeleton."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any, cast

from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable

from graph_agent.callbacks.base import Callback
from graph_agent.config.llm_config import ResolvedRole
from graph_agent.core._predict_internal.strategy import BaseMockStrategy, MockedSource
from graph_agent.core._predict_internal.stub import generate_heuristic_stub
from graph_agent.core._predict_internal.tracing import record_mock_source
from graph_agent.models.gateway_chat_model import GatewayChatModel, ToolSpec, _normalise_tool


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
        """Short-circuit provider calls and return P0/P1/P2 mock output."""
        del messages, stop, run_manager, kwargs
        payload, source = self._select_mock_payload()
        return self._build_predict_chat_result(payload, source)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async equivalent of ``_generate`` for Predict mode."""
        del run_manager
        return self._generate(messages, stop=stop, **kwargs)

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Yield one complete fake chunk for streaming Predict consumers."""
        del messages, stop, run_manager, kwargs
        payload, source = self._select_mock_payload()
        content = _payload_to_content(payload)
        metadata = self._mock_metadata(source)
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content=content,
                id=str(metadata["id"]),
                response_metadata=metadata,
                usage_metadata=_message_usage_metadata(),
                chunk_position="last",
            ),
            generation_info=metadata,
        )

    def bind_tools(
        self,
        tools: Sequence[ToolSpec],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        """Keep Predict interception active after LangChain binds phase tools."""

        bound = PredictGatewayChatModel(
            self.role_name,
            self.resolved_role,
            mock_strategy=self.mock_strategy,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            callbacks=self.event_callbacks,
            phase_name=self.phase_name,
            probe_before_call=self.probe_before_call,
            thinking_enabled=self.thinking_enabled,
            bound_tools=tuple(_normalise_tool(tool) for tool in tools),
            tool_choice=tool_choice,
            tool_kwargs={key: cast(object, value) for key, value in kwargs.items()},
            name=self.name,
            cache=self.cache,
            verbose=self.verbose,
            tags=self.tags,
            metadata=self.metadata,
            custom_get_token_ids=self.custom_get_token_ids,
            rate_limiter=self.rate_limiter,
            disable_streaming=self.disable_streaming,
            output_version=self.output_version,
            profile=self.profile,
        )
        return cast(Runnable[LanguageModelInput, AIMessage], bound)

    def _select_mock_payload(self) -> tuple[dict[str, Any], MockedSource]:
        phase_name = self._predict_phase_name
        if self.mock_strategy.has_golden_case(phase_name):
            return self.mock_strategy.get_golden_output(phase_name), "golden_case"

        if self.mock_strategy.has_manual_override(phase_name):
            source = self.mock_strategy.get_manual_source(phase_name)
            if source not in {"manual", "copilot"}:
                source = "manual"
            return self.mock_strategy.get_manual_override(phase_name), source

        return generate_heuristic_stub(self.mock_strategy.get_phase_schema(phase_name)), (
            "heuristic_stub"
        )

    def _build_predict_chat_result(
        self,
        payload: dict[str, Any],
        source: MockedSource,
    ) -> ChatResult:
        content = _payload_to_content(payload)
        metadata = self._mock_metadata(source)
        message = AIMessage(
            content=content,
            id=str(metadata["id"]),
            additional_kwargs={"mock_payload": payload, "mocked_source": source},
            response_metadata=metadata,
            usage_metadata=_message_usage_metadata(),
        )
        generation = ChatGeneration(message=message, generation_info=metadata)
        return ChatResult(
            generations=[generation],
            llm_output={
                **metadata,
                "token_usage": _token_usage(),
                "usage": _zero_usage(),
                "model_name": self.name or self.role_name,
                "provider": "predict_mock",
            },
        )

    @property
    def _predict_phase_name(self) -> str:
        return self.phase_name or "<gateway>"

    def _mock_metadata(self, source: MockedSource) -> dict[str, object]:
        now = datetime.now(UTC)
        record_mock_source(self._predict_phase_name, source)
        return {
            "id": f"mock_id_{source}_{_safe_identifier(self._predict_phase_name)}_{time.time_ns()}",
            "created": int(now.timestamp()),
            "mocked_source": source,
            "phase_name": self._predict_phase_name,
            "finish_reason": "stop",
            "usage": _zero_usage(),
        }


def _payload_to_content(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _zero_usage() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "total_cost": 0,
    }


def _token_usage() -> dict[str, int]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _message_usage_metadata() -> UsageMetadata:
    return UsageMetadata(input_tokens=0, output_tokens=0, total_tokens=0)


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)


__all__ = ["PredictGatewayChatModel"]
