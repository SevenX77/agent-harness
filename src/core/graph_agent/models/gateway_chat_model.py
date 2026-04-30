"""LangChain-compatible gateway adapter backed by ``LLMClientManager``.

Phase 4 M2 added the adapter; M3 wires ``ModelResolver`` to return it for
live graph execution while preserving LangChain's ``BaseChatModel`` surface.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

import httpx
from anthropic import APIConnectionError as AnthropicAPIConnectionError
from anthropic import APITimeoutError as AnthropicAPITimeoutError
from anthropic import InternalServerError as AnthropicInternalServerError
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from openai import APIConnectionError, APITimeoutError, BadRequestError, InternalServerError
from pydantic import ConfigDict, Field

from ..callbacks.base import Callback
from ..callbacks.events import LLMFallbackEvent
from ..config.llm_config import ResolvedProvider, ResolvedRole
from .llm_client_manager import LLMClientManager, MessageDict

logger = logging.getLogger(__name__)

_RUNTIME_FAILOVER_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    ConnectionError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    BadRequestError,
    AnthropicAPIConnectionError,
    AnthropicAPITimeoutError,
    AnthropicInternalServerError,
    RuntimeError,
)

ToolSpec = dict[str, Any] | type | Callable[..., object] | BaseTool


class GatewayChatModel(BaseChatModel):
    """``BaseChatModel`` adapter with explicit provider fallback control."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    role_name: str
    resolved_role: ResolvedRole
    max_tokens: int = 4096
    temperature: float = 0.7
    phase_name: str | None = None
    event_callbacks: tuple[Callback, ...] = Field(default_factory=tuple)
    probe_before_call: bool = True
    thinking_enabled: bool | None = None
    bound_tools: tuple[dict[str, object], ...] = Field(default_factory=tuple)
    tool_choice: str | None = None
    tool_kwargs: dict[str, object] = Field(default_factory=dict)

    def __init__(
        self,
        role_name: str,
        resolved_role: ResolvedRole,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        callbacks: Sequence[Callback] = (),
        phase_name: str | None = None,
        probe_before_call: bool = True,
        thinking_enabled: bool | None = None,
        bound_tools: Sequence[Mapping[str, object]] = (),
        tool_choice: str | None = None,
        tool_kwargs: Mapping[str, object] | None = None,
        **kwargs: Any,
    ) -> None:
        model_kwargs: dict[str, object] = {
            "role_name": role_name,
            "resolved_role": resolved_role,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "phase_name": phase_name,
            "event_callbacks": tuple(callbacks),
            "probe_before_call": probe_before_call,
            "thinking_enabled": thinking_enabled,
            "bound_tools": tuple(bound_tools),
            "tool_choice": tool_choice,
            "tool_kwargs": dict(tool_kwargs or {}),
            **kwargs,
        }
        super().__init__(**cast(Any, model_kwargs))

    @property
    def _llm_type(self) -> str:
        return "graph_agent_gateway"

    @property
    def _identifying_params(self) -> dict[str, object]:
        return {
            "role_name": self.role_name,
            "active_model_code": self.resolved_role.active_model_code,
            "candidates": [_candidate_id(candidate) for candidate in self.resolved_role.call_chain],
        }

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Call providers in priority order with probe, mark-down, and real fallback events."""
        del stop, run_manager
        request_messages = _langchain_messages_to_dict(messages)
        failures: list[str] = []

        for index, candidate in enumerate(self.resolved_role.call_chain):
            candidate_id = _candidate_id(candidate)
            if LLMClientManager._is_provider_marked_down(
                candidate.provider_code,
                candidate.model_name,
            ):
                logger.info(
                    "phase=gateway_chat_model role=%s candidate=%s decision=skip_down",
                    self.role_name,
                    candidate_id,
                )
                continue

            if self.probe_before_call and not LLMClientManager._probe_provider(candidate):
                LLMClientManager._mark_provider_down(candidate.provider_code, candidate.model_name)
                logger.warning(
                    "phase=gateway_chat_model role=%s candidate=%s decision=probe_failed",
                    self.role_name,
                    candidate_id,
                )
                continue

            try:
                before_calls = _usage_total_calls(candidate.provider_code)
                response = LLMClientManager._dispatch_provider_call(
                    candidate,
                    request_messages,
                    _int_kwarg(kwargs.get("max_tokens"), self.max_tokens),
                    _float_kwarg(kwargs.get("temperature"), self.temperature),
                    reasoning=_bool_kwarg(
                        kwargs.get("reasoning"),
                        (
                            self.thinking_enabled
                            if self.thinking_enabled is not None
                            else candidate.model_def.reasoning
                        ),
                    ),
                    tools=list(self.bound_tools) or None,
                    tool_choice=self.tool_choice,
                )
                self._record_usage_if_needed(candidate.provider_code, before_calls, response)
                logger.info(
                    "phase=gateway_chat_model role=%s candidate=%s decision=success",
                    self.role_name,
                    candidate_id,
                )
                return self._build_chat_result(response, candidate)
            except _RUNTIME_FAILOVER_EXCEPTIONS as exc:
                failures.append(f"{candidate_id}: {type(exc).__name__}: {exc}")
                LLMClientManager._mark_provider_down(candidate.provider_code, candidate.model_name)
                self._emit_real_fallback_event(
                    exc,
                    candidate,
                    to_provider=self._next_candidate_id(index + 1),
                )
                logger.warning(
                    "phase=gateway_chat_model role=%s candidate=%s decision=fallback error=%s",
                    self.role_name,
                    candidate_id,
                    exc,
                )

        detail = "; ".join(failures) if failures else "no available candidates"
        raise RuntimeError(f"All LLM fallback candidates failed for role={self.role_name}: {detail}")

    def bind_tools(
        self,
        tools: Sequence[ToolSpec],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        """Return a runnable clone carrying LangChain tool-binding metadata."""
        bound = GatewayChatModel(
            self.role_name,
            self.resolved_role,
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

    def _build_chat_result(
        self,
        response: Mapping[str, object],
        candidate: ResolvedProvider,
    ) -> ChatResult:
        usage = _usage_from_response(response)
        finish_reason = _optional_text(response.get("finish_reason"))
        additional_kwargs = _additional_kwargs_from_response(response)
        metadata: dict[str, object] = {
            "provider": candidate.provider_code,
            "model": candidate.model_name,
            "finish_reason": finish_reason,
            "usage": usage,
        }
        message = AIMessage(
            content=_coerce_text(response.get("content")),
            additional_kwargs=additional_kwargs,
            response_metadata=metadata,
        )
        generation = ChatGeneration(
            message=message,
            generation_info={
                "finish_reason": finish_reason,
                "provider": candidate.provider_code,
                "model": candidate.model_name,
            },
        )
        return ChatResult(
            generations=[generation],
            llm_output={
                "token_usage": usage,
                "model_name": candidate.model_name,
                "provider": candidate.provider_code,
            },
        )

    def _emit_real_fallback_event(
        self,
        exc: BaseException,
        candidate: ResolvedProvider,
        *,
        to_provider: str,
    ) -> None:
        if not self.event_callbacks:
            return

        event = LLMFallbackEvent(
            phase_name=self.phase_name or "<gateway>",
            from_provider=_candidate_id(candidate),
            to_provider=to_provider,
            reason=f"{type(exc).__name__}: {exc}",
        )
        for callback in self.event_callbacks:
            try:
                callback.on_event(event)
            except Exception:
                logger.exception(
                    "phase=gateway_chat_model action=callback_failed callback=%s",
                    type(callback).__name__,
                )

    def _next_candidate_id(self, start_index: int) -> str:
        for candidate in self.resolved_role.call_chain[start_index:]:
            if not LLMClientManager._is_provider_marked_down(
                candidate.provider_code,
                candidate.model_name,
            ):
                return _candidate_id(candidate)
        return "<none>"

    def _record_usage_if_needed(
        self,
        provider_code: str,
        before_calls: int,
        response: Mapping[str, object],
    ) -> None:
        if _usage_total_calls(provider_code) > before_calls:
            return
        usage = _usage_from_response(response)
        LLMClientManager.record_usage(
            provider_code,
            int(usage["prompt_tokens"]),
            int(usage["completion_tokens"]),
        )


def _candidate_id(candidate: ResolvedProvider) -> str:
    return f"{candidate.provider_code}/{candidate.model_name}"


def _usage_total_calls(provider_code: str) -> int:
    stats = LLMClientManager.get_usage_stats().get(provider_code)
    if stats is None:
        return 0
    return int(stats.get("total_calls", 0))


def _usage_from_response(response: Mapping[str, object]) -> dict[str, int]:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    prompt_tokens = _int_value(usage.get("prompt_tokens"))
    completion_tokens = _int_value(usage.get("completion_tokens"))
    total_tokens = _int_value(usage.get("total_tokens"))
    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _additional_kwargs_from_response(response: Mapping[str, object]) -> dict[str, object]:
    additional_kwargs: dict[str, object] = {}
    raw_additional = response.get("additional_kwargs")
    if isinstance(raw_additional, Mapping):
        additional_kwargs.update({str(key): value for key, value in raw_additional.items()})

    for key in ("tool_calls", "reasoning_content"):
        value = response.get(key)
        if value is not None:
            additional_kwargs[key] = value

    return additional_kwargs


def _normalise_tool(tool: ToolSpec) -> dict[str, object]:
    if isinstance(tool, Mapping):
        if tool.get("type") == "function":
            return {str(key): value for key, value in tool.items()}
        if "name" in tool:
            return {
                "type": "function",
                "function": {
                    "name": str(tool["name"]),
                    "description": str(tool.get("description", "")),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                },
            }
    return cast(dict[str, object], convert_to_openai_tool(tool))


def _langchain_messages_to_dict(messages: Sequence[BaseMessage]) -> list[MessageDict]:
    converted: list[MessageDict] = []
    for message in messages:
        item: MessageDict = {
            "role": _message_role(message),
            "content": _message_content(message.content),
        }
        if message.name:
            item["name"] = message.name

        tool_call_id = getattr(message, "tool_call_id", None)
        if isinstance(tool_call_id, str):
            item["tool_call_id"] = tool_call_id

        reasoning_content = message.additional_kwargs.get("reasoning_content")
        if reasoning_content is not None:
            item["reasoning_content"] = reasoning_content

        raw_tool_calls = message.additional_kwargs.get("tool_calls")
        if raw_tool_calls is not None:
            item["tool_calls"] = raw_tool_calls
        else:
            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls:
                item["tool_calls"] = _langchain_tool_calls_to_openai(tool_calls)

        converted.append(item)
    return converted


def _langchain_tool_calls_to_openai(tool_calls: Sequence[object]) -> list[dict[str, object]]:
    converted: list[dict[str, object]] = []
    for call in tool_calls:
        if not isinstance(call, Mapping):
            continue
        name = call.get("name")
        if not isinstance(name, str) or not name:
            continue
        args = call.get("args")
        converted.append(
            {
                "id": str(call.get("id") or ""),
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": args if isinstance(args, str) else json.dumps(args or {}),
                },
            }
        )
    return converted


def _message_role(message: BaseMessage) -> str:
    if message.type == "human":
        return "user"
    if message.type == "ai":
        return "assistant"
    if message.type in {"system", "tool"}:
        return message.type
    return "user"


def _message_content(content: object) -> object:
    if content is None or isinstance(content, str):
        return content or ""
    return content


def _coerce_text(value: object) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _int_kwarg(value: object, default: int) -> int:
    parsed = _int_value(value)
    return parsed if parsed > 0 else default


def _float_kwarg(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _bool_kwarg(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


__all__ = ["GatewayChatModel"]
