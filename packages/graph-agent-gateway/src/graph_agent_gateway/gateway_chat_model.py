"""LangChain-compatible gateway chat model."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.messages.ai import AIMessage as LangChainAIMessage
from langchain_core.messages.human import HumanMessage
from langchain_core.messages.system import SystemMessage
from langchain_core.messages.tool import ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ConfigDict, Field

from graph_agent_gateway.exceptions import AllProvidersFailedError
from graph_agent_gateway.llm_config import ResolvedProvider, ResolvedRole
from graph_agent_gateway.tracing import emit_llm_fallback_event

ToolSpec = dict[str, Any] | type | Callable[..., object] | BaseTool


class GatewayChatModel(BaseChatModel):
    """BaseChatModel adapter with explicit provider fallback control."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    role_name: str
    resolved_role: ResolvedRole
    max_tokens: int = 4096
    temperature: float = 0.7
    phase_name: str | None = None
    event_callbacks: tuple[Any, ...] = Field(default_factory=tuple)
    probe_before_call: bool = True
    thinking_enabled: bool | None = None
    bound_tools: tuple[dict[str, object], ...] = Field(default_factory=tuple)
    tool_choice: str | None = None
    tool_kwargs: dict[str, object] = Field(default_factory=dict)
    client_manager: Any = None

    def __init__(
        self,
        role_name: str,
        resolved_role: ResolvedRole,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        callbacks: Sequence[Any] = (),
        phase_name: str | None = None,
        probe_before_call: bool = True,
        thinking_enabled: bool | None = None,
        bound_tools: Sequence[Mapping[str, object]] = (),
        tool_choice: str | None = None,
        tool_kwargs: Mapping[str, object] | None = None,
        client_manager: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(  # type: ignore[call-arg]
            role_name=role_name,
            resolved_role=resolved_role,
            max_tokens=max_tokens,
            temperature=temperature,
            phase_name=phase_name,
            event_callbacks=tuple(callbacks),
            probe_before_call=probe_before_call,
            thinking_enabled=thinking_enabled,
            bound_tools=tuple(dict(item) for item in bound_tools),
            tool_choice=tool_choice,
            tool_kwargs=dict(tool_kwargs or {}),
            client_manager=client_manager,
            **kwargs,
        )

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
        del stop, run_manager
        request_messages = _langchain_messages_to_dict(messages)
        failures: list[dict[str, Any]] = []

        for index, candidate in enumerate(self.resolved_role.call_chain):
            candidate_id = _candidate_id(candidate)
            if _is_marked_down(self.client_manager, candidate):
                continue
            if self.probe_before_call and not _probe(self.client_manager, candidate):
                _mark_down(self.client_manager, candidate, RuntimeError("probe failed"))
                continue
            try:
                before_usage = _usage_total_calls(self.client_manager, candidate.provider_code)
                response = _dispatch(
                    self.client_manager,
                    candidate,
                    request_messages,
                    max_tokens=_int_kwarg(kwargs.get("max_tokens"), self.max_tokens),
                    temperature=_float_kwarg(kwargs.get("temperature"), self.temperature),
                    reasoning=_bool_kwarg(
                        kwargs.get("reasoning"),
                        self.thinking_enabled
                        if self.thinking_enabled is not None
                        else candidate.model_def.reasoning,
                    ),
                    tools=list(self.bound_tools) or None,
                    tool_choice=self.tool_choice,
                )
                after_usage = _usage_total_calls(self.client_manager, candidate.provider_code)
                if after_usage == before_usage:
                    usage = _usage_from_response(response)
                    _record_usage(
                        self.client_manager,
                        candidate.provider_code,
                        usage["prompt_tokens"],
                        usage["completion_tokens"],
                    )
                return self._build_chat_result(response, candidate)
            except Exception as exc:  # noqa: BLE001 - gateway fallback boundary
                failure = {
                    "provider": candidate_id,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
                failures.append(failure)
                _mark_down(self.client_manager, candidate, exc)
                emit_llm_fallback_event(
                    callbacks=self.event_callbacks,
                    phase_name=self.phase_name or "<gateway>",
                    from_provider=candidate_id,
                    to_provider=self._next_candidate_id(index + 1),
                    reason=f"{type(exc).__name__}: {exc}",
                    code="[F-v3-gateway-all-providers-failed]",
                    context={"role_name": self.role_name},
                )

        raise AllProvidersFailedError(
            self.role_name,
            failures,
            phase_name=self.phase_name or "<gateway>",
        )

    def bind_tools(
        self,
        tools: Sequence[ToolSpec],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
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
            client_manager=self.client_manager,
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
        message = AIMessage(
            content=_coerce_text(response.get("content")),
            additional_kwargs=_additional_kwargs_from_response(response),
            response_metadata={
                "provider": candidate.provider_code,
                "model": candidate.model_name,
                "finish_reason": finish_reason,
                "usage": usage,
            },
        )
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=message,
                    generation_info={
                        "finish_reason": finish_reason,
                        "provider": candidate.provider_code,
                        "model": candidate.model_name,
                    },
                )
            ],
            llm_output={
                "token_usage": usage,
                "model_name": candidate.model_name,
                "provider": candidate.provider_code,
            },
        )

    def _next_candidate_id(self, start_index: int) -> str:
        for candidate in self.resolved_role.call_chain[start_index:]:
            if not _is_marked_down(self.client_manager, candidate):
                return _candidate_id(candidate)
        return "<none>"


def _candidate_id(candidate: ResolvedProvider) -> str:
    return f"{candidate.provider_code}/{candidate.model_name}"


def _default_client_manager() -> Any:
    from graph_agent.models.llm_client_manager import LLMClientManager

    return LLMClientManager


def _manager(client_manager: Any) -> Any:
    return client_manager if client_manager is not None else _default_client_manager()


def _is_marked_down(client_manager: Any, candidate: ResolvedProvider) -> bool:
    manager = _manager(client_manager)
    if hasattr(manager, "is_provider_marked_down"):
        return bool(manager.is_provider_marked_down(candidate.provider_code))
    return bool(manager._is_provider_marked_down(candidate.provider_code, candidate.model_name))


def _probe(client_manager: Any, candidate: ResolvedProvider) -> bool:
    manager = _manager(client_manager)
    if hasattr(manager, "probe_provider"):
        return bool(manager.probe_provider(candidate))
    return bool(manager._probe_provider(candidate))


def _dispatch(
    client_manager: Any,
    candidate: ResolvedProvider,
    messages: list[dict[str, Any]],
    **kwargs: Any,
) -> Mapping[str, object]:
    manager = _manager(client_manager)
    if hasattr(manager, "dispatch_provider_call"):
        response = manager.dispatch_provider_call(candidate, messages, **kwargs)
    else:
        response = manager._dispatch_provider_call(
            candidate,
            messages,
            kwargs["max_tokens"],
            kwargs["temperature"],
            reasoning=kwargs.get("reasoning"),
            tools=kwargs.get("tools"),
            tool_choice=kwargs.get("tool_choice"),
        )
    if not isinstance(response, Mapping):
        return {"content": str(response), "usage": {}}
    return response


def _mark_down(client_manager: Any, candidate: ResolvedProvider, exc: BaseException) -> None:
    manager = _manager(client_manager)
    if hasattr(manager, "mark_provider_down"):
        manager.mark_provider_down(candidate.provider_code, exc)
    else:
        manager._mark_provider_down(candidate.provider_code, candidate.model_name)


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


def _int_value(value: object) -> int:
    if isinstance(value, int | float) and value >= 0:
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _int_kwarg(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float) and value > 0:
        return int(value)
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return default


def _float_kwarg(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(value) if isinstance(value, int | float | str) else default
    except ValueError:
        return default


def _bool_kwarg(value: object, default: bool) -> bool:
    return bool(value) if isinstance(value, bool) else default


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _coerce_text(value: object) -> str:
    return value if isinstance(value, str) else str(value) if value is not None else ""


def _additional_kwargs_from_response(response: Mapping[str, object]) -> dict[str, object]:
    extra = response.get("additional_kwargs")
    result = dict(extra) if isinstance(extra, Mapping) else {}
    tool_calls = response.get("tool_calls")
    if isinstance(tool_calls, list):
        result["tool_calls"] = tool_calls
    reasoning = response.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning:
        result["reasoning_content"] = reasoning
    return result


def _langchain_messages_to_dict(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message in messages:
        payload: dict[str, Any] = {
            "role": _message_role(message),
            "content": message.content,
        }
        name = getattr(message, "name", None)
        if name:
            payload["name"] = name
        if isinstance(message, ToolMessage):
            payload["tool_call_id"] = message.tool_call_id
        raw_tool_calls = message.additional_kwargs.get("tool_calls")
        if raw_tool_calls:
            payload["tool_calls"] = raw_tool_calls
        elif isinstance(message, LangChainAIMessage) and message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call.get("id"),
                    "type": "function",
                    "function": {
                        "name": call.get("name"),
                        "arguments": "{}",
                    },
                }
                for call in message.tool_calls
            ]
        reasoning = message.additional_kwargs.get("reasoning_content")
        if reasoning:
            payload["reasoning_content"] = reasoning
        result.append(payload)
    return result


def _normalise_tool(tool: ToolSpec) -> dict[str, object]:
    if isinstance(tool, dict) and tool.get("type") == "function":
        return {str(key): value for key, value in tool.items()}
    normalized = cast(dict[str, object], convert_to_openai_tool(tool))
    function = normalized.get("function")
    if isinstance(function, dict):
        function.setdefault("description", "")
        function.setdefault("parameters", {"type": "object", "properties": {}})
    return normalized


def _message_role(message: BaseMessage) -> str:
    if isinstance(message, SystemMessage):
        return "system"
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, LangChainAIMessage):
        return "assistant"
    if isinstance(message, ToolMessage):
        return "tool"
    return "user"


def _usage_total_calls(client_manager: Any, provider_code: str) -> int:
    manager = _manager(client_manager)
    get_usage_stats = getattr(manager, "get_usage_stats", None)
    if get_usage_stats is None:
        return 0
    stats = get_usage_stats()
    if not isinstance(stats, Mapping):
        return 0
    provider_stats = stats.get(provider_code)
    if not isinstance(provider_stats, Mapping):
        return 0
    total_calls = provider_stats.get("total_calls")
    return total_calls if isinstance(total_calls, int) else 0


def _record_usage(
    client_manager: Any,
    provider_code: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    manager = _manager(client_manager)
    record_usage = getattr(manager, "record_usage", None)
    if record_usage is not None:
        record_usage(provider_code, prompt_tokens, completion_tokens)
