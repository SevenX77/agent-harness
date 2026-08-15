"""Predict-mode chat model interception owned by the engine package."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from inspect import Parameter, Signature
from typing import Any, Literal, cast

from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from pydantic import ConfigDict, Field

from graph_agent.callbacks.base import Callback
from graph_agent.core._predict_internal.strategy import BaseMockStrategy, MockedSource
from graph_agent.core._predict_internal.stub import generate_heuristic_stub
from graph_agent.core._predict_internal.tracing import record_mock_source
from graph_agent.tracing.steps import StepReporter


class _PredictGatewayChatModelMixin:
    mock_strategy: BaseMockStrategy
    name: str | None
    role_name: str
    phase_name: str | None
    phase_output_schema: dict[str, Any] | None
    resolved_role: Any
    max_tokens: int
    temperature: float
    event_callbacks: Sequence[Callback]
    bound_tools: tuple[Any, ...]
    tool_choice: str | None
    tool_kwargs: dict[str, object]
    call_counter: list[int]
    prompt_template_source: str | None
    prompt_variables: dict[str, Any]
    probe_before_call: bool
    thinking_enabled: bool | None
    cache: Any
    verbose: bool
    tags: list[str] | None
    metadata: dict[str, Any] | None
    custom_get_token_ids: Any
    rate_limiter: Any
    disable_streaming: bool | Literal["tool_calling"]
    output_version: str | None
    profile: Any

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Short-circuit provider calls and return P0/P1/P2 mock output."""
        del stop, run_manager, kwargs
        # A mocked round-trip is still a round-trip as far as anyone reading the
        # run is concerned, and it reports itself for the same reason a real one
        # does: the unit that performs a step is the only one that knows when it
        # started and when it ended.
        self.call_counter[0] += 1
        with StepReporter(
            callbacks=self.event_callbacks,
            phase_name=self._predict_phase_name,
        ).llm_call(
            messages,
            llm_role=self.role_name,
            loop_index=self.call_counter[0],
            parent_node_id=self.phase_name,
            node_type="agent",
            template_source=self.prompt_template_source,
            variables=self.prompt_variables,
        ) as step:
            payload, source = self._select_mock_payload()
            result = self._build_predict_chat_result(payload, source)
            step.finished(cast(AIMessage, result.generations[0].message))
        return result

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

    def _select_mock_payload(self) -> tuple[dict[str, Any], MockedSource]:
        phase_name = self._predict_phase_name
        if self.mock_strategy.has_golden_case(phase_name):
            return self.mock_strategy.get_golden_output(phase_name), "golden_case"

        if self.mock_strategy.has_manual_override(phase_name):
            source = self.mock_strategy.get_manual_source(phase_name)
            if source not in {"manual", "copilot"}:
                source = "manual"
            return self.mock_strategy.get_manual_override(phase_name), source

        schema = self.phase_output_schema or self.mock_strategy.get_phase_schema(phase_name)
        return generate_heuristic_stub(schema), "heuristic_stub"

    def _build_predict_chat_result(
        self,
        payload: dict[str, Any],
        source: MockedSource,
    ) -> ChatResult:
        content = _payload_to_content(payload)
        metadata = self._mock_metadata(source)
        message = AIMessage(
            content=content,
            tool_calls=_predict_tool_calls(self.bound_tools, payload, metadata),
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


class PredictGatewayChatModel(_PredictGatewayChatModelMixin, BaseChatModel):
    """LangChain-compatible Predict mock model without Gateway concrete dependencies."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    role_name: str
    resolved_role: Any
    mock_strategy: BaseMockStrategy
    max_tokens: int = 4096
    temperature: float = 0.7
    event_callbacks: tuple[Any, ...] = Field(default_factory=tuple)
    phase_name: str | None = None
    probe_before_call: bool = True
    thinking_enabled: bool | None = None
    bound_tools: tuple[Any, ...] = Field(default_factory=tuple)
    tool_choice: str | None = None
    tool_kwargs: dict[str, object] = Field(default_factory=dict)
    # Shared with the copy ``bind_tools`` makes, so the loop count a phase
    # reports keeps rising instead of restarting at 1 on every turn.
    call_counter: list[int] = Field(default_factory=lambda: [0])
    # A mocked round-trip reports its prompt's provenance for the same reason a
    # real one does: the panel showing it makes no distinction, so a gap here
    # would read as "this prompt came from nowhere".
    prompt_template_source: str | None = None
    prompt_variables: dict[str, Any] = Field(default_factory=dict)
    profile: Any = None
    #: This phase's declared io.outputs, handed over by the assembler that owns
    #: it. Held on the model rather than looked up in a shared per-phase-name map
    #: because phase names are only unique WITHIN a skill — two subgraphs may both
    #: have a phase called "review", and a shared map serves one of them the
    #: other's schema (decision doc 2026-08-15 predict-nested-phase-schema).
    phase_output_schema: dict[str, Any] | None = None

    def __init__(
        self,
        role_name: str,
        resolved_role: Any,
        *,
        mock_strategy: BaseMockStrategy,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        callbacks: Sequence[Callback] = (),
        phase_name: str | None = None,
        probe_before_call: bool = True,
        thinking_enabled: bool | None = None,
        bound_tools: Sequence[Any] = (),
        tool_choice: str | None = None,
        tool_kwargs: dict[str, object] | None = None,
        phase_output_schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(  # type: ignore[call-arg]
            role_name=role_name,
            resolved_role=resolved_role,
            mock_strategy=mock_strategy,
            max_tokens=max_tokens,
            temperature=temperature,
            event_callbacks=tuple(callbacks),
            phase_name=phase_name,
            probe_before_call=probe_before_call,
            thinking_enabled=thinking_enabled,
            bound_tools=tuple(bound_tools),
            tool_choice=tool_choice,
            tool_kwargs=dict(tool_kwargs or {}),
            phase_output_schema=phase_output_schema,
            **kwargs,
        )

    @property
    def _llm_type(self) -> str:
        return "predict_mock"

    @property
    def _identifying_params(self) -> dict[str, object]:
        return {"role_name": self.role_name, "phase_name": self.phase_name or ""}

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        """Keep Predict interception active after LangChain binds phase tools."""
        bound = type(self)(
            self.role_name,
            self.resolved_role,
            mock_strategy=self.mock_strategy,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            callbacks=self.event_callbacks,
            phase_name=self.phase_name,
            probe_before_call=self.probe_before_call,
            thinking_enabled=self.thinking_enabled,
            bound_tools=tuple(_normalise_predict_tool(tool) for tool in tools),
            tool_choice=tool_choice,
            phase_output_schema=self.phase_output_schema,
            tool_kwargs={key: cast(object, value) for key, value in kwargs.items()},
            call_counter=self.call_counter,
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


PredictGatewayChatModel.__signature__ = Signature(
    parameters=[
        Parameter("role_name", Parameter.POSITIONAL_OR_KEYWORD, annotation="str"),
        Parameter("resolved_role", Parameter.POSITIONAL_OR_KEYWORD, annotation="Any"),
        Parameter(
            "mock_strategy",
            Parameter.KEYWORD_ONLY,
            annotation="BaseMockStrategy",
        ),
        Parameter("max_tokens", Parameter.KEYWORD_ONLY, default=4096, annotation="int"),
        Parameter("temperature", Parameter.KEYWORD_ONLY, default=0.7, annotation="float"),
        Parameter("callbacks", Parameter.KEYWORD_ONLY, default=(), annotation="Sequence[Callback]"),
        Parameter("phase_name", Parameter.KEYWORD_ONLY, default=None, annotation="str | None"),
        Parameter("probe_before_call", Parameter.KEYWORD_ONLY, default=True, annotation="bool"),
        Parameter("thinking_enabled", Parameter.KEYWORD_ONLY, default=None, annotation="bool | None"),
        Parameter("kwargs", Parameter.VAR_KEYWORD, annotation="Any"),
    ],
    return_annotation="None",
)


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
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def _normalise_predict_tool(tool: Any) -> Any:
    if isinstance(tool, dict):
        return dict(tool)
    name = getattr(tool, "name", None)
    description = getattr(tool, "description", None)
    if name is not None:
        payload: dict[str, object] = {"name": str(name)}
        if description is not None:
            payload["description"] = str(description)
        return payload
    return tool


def _predict_tool_calls(
    bound_tools: Sequence[Any],
    payload: dict[str, Any],
    metadata: dict[str, object],
) -> list[dict[str, Any]]:
    if not any(_predict_tool_name(tool) == "finish_task" for tool in bound_tools):
        return []
    return [
        {
            "name": "finish_task",
            "args": {
                "reasoning": "Predict mock completed the phase.",
                "business_data_md": _payload_to_business_data_md(payload),
            },
            "id": f"{metadata['id']}_finish_task",
        }
    ]


def _predict_tool_name(tool: Any) -> str | None:
    if isinstance(tool, dict):
        name = tool.get("name")
        return str(name) if name is not None else None
    name = getattr(tool, "name", None)
    return str(name) if name is not None else None


def _payload_to_business_data_md(payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return f"## item-1\n```json\n{rendered}\n```\n"


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)


__all__ = ["PredictGatewayChatModel"]
