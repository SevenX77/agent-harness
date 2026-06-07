"""LangChain-compatible gateway chat model."""

from __future__ import annotations

import inspect
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
from graph_agent_gateway.registry.error_classification import classify_exception
from graph_agent_gateway.registry.schema import ResolvedRole, ResolvedRoute
from graph_agent_gateway.route_chat_model_factory import RouteChatModelFactory
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
    credential_provider: Any = None

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
        credential_provider: Any = None,
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
            credential_provider=credential_provider,
            **kwargs,
        )

    @property
    def _llm_type(self) -> str:
        return "graph_agent_gateway"

    @property
    def _identifying_params(self) -> dict[str, object]:
        return {
            "role_name": self.role_name,
            "candidates": [_candidate_id(candidate) for candidate in self.resolved_role.routes],
        }

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager
        request_messages = _apply_system_prompt_prefix(
            messages,
            self.resolved_role.system_prompt_prefix,
        )
        failures: list[dict[str, Any]] = []
        runtime_policy = self.resolved_role.runtime_policy

        for index, candidate in enumerate(self.resolved_role.routes):
            candidate_id = _candidate_id(candidate)
            if _is_marked_down(self.client_manager, candidate, runtime_policy):
                continue
            if self.probe_before_call:
                try:
                    probe_ok = _probe(
                        self.client_manager,
                        candidate,
                        runtime_policy,
                        credential_provider=self.credential_provider,
                    )
                except Exception as exc:  # noqa: BLE001 - gateway fallback boundary
                    classification = classify_exception(exc, route_id=candidate.route_id)
                    failure = _failure_record(candidate, exc, classification.decision)
                    failure["unclassified_default"] = classification.unclassified_default
                    failure["provider_status_code"] = classification.provider_status_code
                    failures.append(failure)
                    if classification.decision != "fallback_allowed":
                        raise AllProvidersFailedError(
                            self.role_name,
                            failures,
                            phase_name=self.phase_name or "<gateway>",
                        ) from exc
                    _mark_down(self.client_manager, candidate, exc, runtime_policy)
                    emit_llm_fallback_event(
                        callbacks=self.event_callbacks,
                        phase_name=self.phase_name or "<gateway>",
                        from_provider=candidate_id,
                        to_provider=self._next_candidate_id(index + 1),
                        reason=f"{type(exc).__name__}: {exc}",
                        context=self._fallback_event_context(
                            candidate,
                            index + 1,
                            fallback_decision=classification.decision,
                            error_type=type(exc).__name__,
                            provider_status_code=classification.provider_status_code,
                            unclassified_default=classification.unclassified_default,
                        ),
                    )
                    continue
                if not probe_ok:
                    failure = {
                        "provider": candidate_id,
                        "route_id": candidate.route_id,
                        "endpoint_id": candidate.endpoint_id,
                        "provider_model_id": candidate.provider_model_id,
                        "canonical_id": candidate.canonical_id,
                        "protocol": candidate.protocol,
                        "error_type": "RuntimeError",
                        "message": "probe failed",
                        "fallback_decision": "fallback_allowed",
                        "unclassified_default": False,
                        "provider_status_code": None,
                    }
                    failures.append(failure)
                    _mark_down(
                        self.client_manager,
                        candidate,
                        RuntimeError("probe failed"),
                        runtime_policy,
                    )
                    emit_llm_fallback_event(
                        callbacks=self.event_callbacks,
                        phase_name=self.phase_name or "<gateway>",
                        from_provider=candidate_id,
                        to_provider=self._next_candidate_id(index + 1),
                        reason="RuntimeError: probe failed",
                        context=self._fallback_event_context(
                            candidate,
                            index + 1,
                            fallback_decision="fallback_allowed",
                            error_type="RuntimeError",
                            provider_status_code=None,
                        ),
                    )
                    continue
            try:
                before_usage = _usage_total_calls(self.client_manager, candidate)
                response = _dispatch(
                    self.client_manager,
                    candidate,
                    request_messages,
                    credential_provider=self.credential_provider,
                    max_tokens=_int_kwarg(
                        kwargs.get("max_tokens"),
                        _effective_int(candidate, "max_output_tokens", self.max_tokens),
                    ),
                    temperature=_float_kwarg(
                        kwargs.get("temperature"),
                        _effective_float(candidate, "temperature", self.temperature),
                    ),
                    reasoning=_bool_kwarg(
                        kwargs.get("reasoning"),
                        self.thinking_enabled
                        if self.thinking_enabled is not None
                        else _effective_bool(candidate, "reasoning.enabled", False),
                    ),
                    thinking_budget_tokens=_optional_int_kwarg(
                        kwargs.get("thinking_budget_tokens"),
                        _effective_optional_int(candidate, "reasoning.budget_tokens"),
                    ),
                    tools=list(self.bound_tools) or None,
                    tool_choice=self.tool_choice or _effective_text(candidate, "tool_choice"),
                    runtime_policy=runtime_policy,
                    top_p=_effective_optional_float(candidate, "top_p"),
                    stop_sequences=_effective_string_list(candidate, "stop_sequences"),
                    seed=_effective_optional_int(candidate, "seed"),
                    parallel_tool_calls=_effective_optional_bool(candidate, "parallel_tool_calls"),
                    structured_output=_effective_structured_output(candidate),
                    reasoning_effort=_effective_text(candidate, "reasoning.effort"),
                    call_method_id=candidate.call_method_id,
                    request_mapper_id=candidate.request_mapper_id,
                )
                after_usage = _usage_total_calls(self.client_manager, candidate)
                if after_usage == before_usage:
                    usage = _usage_from_response(response)
                    _record_usage(
                        self.client_manager,
                        candidate.endpoint_id,
                        usage["prompt_tokens"],
                        usage["completion_tokens"],
                    )
                return self._build_chat_result(response, candidate)
            except Exception as exc:  # noqa: BLE001 - gateway fallback boundary
                classification = classify_exception(exc, route_id=candidate.route_id)
                failure = _failure_record(candidate, exc, classification.decision)
                failure["unclassified_default"] = classification.unclassified_default
                failure["provider_status_code"] = classification.provider_status_code
                failures.append(failure)
                if classification.decision != "fallback_allowed":
                    raise AllProvidersFailedError(
                        self.role_name,
                        failures,
                        phase_name=self.phase_name or "<gateway>",
                    ) from exc
                _mark_down(self.client_manager, candidate, exc, runtime_policy)
                emit_llm_fallback_event(
                    callbacks=self.event_callbacks,
                    phase_name=self.phase_name or "<gateway>",
                    from_provider=candidate_id,
                    to_provider=self._next_candidate_id(index + 1),
                    reason=f"{type(exc).__name__}: {exc}",
                    context=self._fallback_event_context(
                        candidate,
                        index + 1,
                        fallback_decision=classification.decision,
                        error_type=type(exc).__name__,
                        provider_status_code=classification.provider_status_code,
                        unclassified_default=classification.unclassified_default,
                    ),
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
        cls = self.__class__
        extra_kwargs = {}
        if hasattr(self, "predict_context"):
            extra_kwargs["predict_context"] = self.predict_context

        bound = cls(
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
            credential_provider=self.credential_provider,
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
            **extra_kwargs,
        )
        return cast(Runnable[LanguageModelInput, AIMessage], bound)

    def _build_chat_result(
        self,
        response: Mapping[str, object] | AIMessage,
        candidate: ResolvedRoute,
    ) -> ChatResult:
        if isinstance(response, AIMessage):
            return self._build_chat_result_from_ai_message(response, candidate)

        usage = _usage_from_response(response)
        finish_reason = _optional_text(response.get("finish_reason"))
        message = AIMessage(
            content=_coerce_text(response.get("content")),
            additional_kwargs=_additional_kwargs_from_response(response),
            response_metadata={
                "route_id": candidate.route_id,
                "endpoint_id": candidate.endpoint_id,
                "model": candidate.provider_model_id,
                "canonical_id": candidate.canonical_id,
                "protocol": candidate.protocol,
                "finish_reason": finish_reason,
                "usage": usage,
                "effective_runtime_settings": _runtime_settings_metadata(candidate),
            },
        )
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=message,
                    generation_info={
                        "finish_reason": finish_reason,
                        "route_id": candidate.route_id,
                        "endpoint_id": candidate.endpoint_id,
                        "model": candidate.provider_model_id,
                        "canonical_id": candidate.canonical_id,
                        "protocol": candidate.protocol,
                    },
                )
            ],
            llm_output={
                "token_usage": usage,
                "model_name": candidate.provider_model_id,
                "route_id": candidate.route_id,
                "endpoint_id": candidate.endpoint_id,
                "canonical_id": candidate.canonical_id,
                "protocol": candidate.protocol,
                "effective_runtime_settings": _runtime_settings_metadata(candidate),
            },
        )

    def _build_chat_result_from_ai_message(
        self,
        response: AIMessage,
        candidate: ResolvedRoute,
    ) -> ChatResult:
        usage = _usage_from_ai_message(response)
        provider_metadata = dict(response.response_metadata or {})
        finish_reason = _optional_text(
            provider_metadata.get("finish_reason") or provider_metadata.get("stop_reason")
        )
        response_metadata = {
            **provider_metadata,
            "route_id": candidate.route_id,
            "endpoint_id": candidate.endpoint_id,
            "model": candidate.provider_model_id,
            "canonical_id": candidate.canonical_id,
            "protocol": candidate.protocol,
            "finish_reason": finish_reason,
            "usage": usage,
            "effective_runtime_settings": _runtime_settings_metadata(candidate),
        }
        message = response.model_copy(update={"response_metadata": response_metadata})
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=message,
                    generation_info={
                        "finish_reason": finish_reason,
                        "route_id": candidate.route_id,
                        "endpoint_id": candidate.endpoint_id,
                        "model": candidate.provider_model_id,
                        "canonical_id": candidate.canonical_id,
                        "protocol": candidate.protocol,
                    },
                )
            ],
            llm_output={
                "token_usage": usage,
                "model_name": candidate.provider_model_id,
                "route_id": candidate.route_id,
                "endpoint_id": candidate.endpoint_id,
                "canonical_id": candidate.canonical_id,
                "protocol": candidate.protocol,
                "effective_runtime_settings": _runtime_settings_metadata(candidate),
            },
        )

    def _next_candidate_id(self, start_index: int) -> str:
        candidate = self._next_candidate(start_index)
        return _candidate_id(candidate) if candidate is not None else "<none>"

    def _next_candidate(self, start_index: int) -> ResolvedRoute | None:
        for candidate in self.resolved_role.routes[start_index:]:
            if not _is_marked_down(
                self.client_manager,
                candidate,
                self.resolved_role.runtime_policy,
            ):
                return candidate
        return None

    def _fallback_event_context(
        self,
        candidate: ResolvedRoute,
        next_index: int,
        *,
        fallback_decision: str,
        error_type: str,
        provider_status_code: int | None,
        unclassified_default: bool = False,
    ) -> dict[str, object]:
        return {
            "role_name": self.role_name,
            "fallback_decision": fallback_decision,
            "error_type": error_type,
            "provider_status_code": provider_status_code,
            "unclassified_default": unclassified_default,
            "from_route": _route_diagnostics(candidate),
            "to_route": _route_diagnostics(self._next_candidate(next_index)),
            "effective_runtime_settings": _runtime_settings_metadata(candidate),
        }


def _candidate_id(candidate: ResolvedRoute) -> str:
    return candidate.route_id


def _route_diagnostics(candidate: ResolvedRoute | None) -> dict[str, object] | None:
    if candidate is None:
        return None
    return {
        "route_id": candidate.route_id,
        "endpoint_id": candidate.endpoint_id,
        "provider_model_id": candidate.provider_model_id,
        "canonical_id": candidate.canonical_id,
        "protocol": candidate.protocol,
    }


def _failure_record(
    candidate: ResolvedRoute,
    exc: BaseException,
    fallback_decision: str,
) -> dict[str, object]:
    return {
        "provider": _candidate_id(candidate),
        "route_id": candidate.route_id,
        "endpoint_id": candidate.endpoint_id,
        "provider_model_id": candidate.provider_model_id,
        "canonical_id": candidate.canonical_id,
        "protocol": candidate.protocol,
        "error_type": type(exc).__name__,
        "message": str(exc),
        "fallback_decision": fallback_decision,
    }


def _runtime_settings_metadata(candidate: ResolvedRoute) -> dict[str, dict[str, object]]:
    return {
        key: setting.model_dump(mode="json")
        for key, setting in candidate.effective_runtime_settings.items()
    }


def _default_client_manager() -> Any:
    from graph_agent_gateway.client_manager import LLMClientManager

    return LLMClientManager


def _manager(client_manager: Any) -> Any:
    return client_manager if client_manager is not None else _default_client_manager()


def _is_marked_down(
    client_manager: Any,
    candidate: ResolvedRoute,
    runtime_policy: Any,
) -> bool:
    manager = _manager(client_manager)
    return bool(manager.is_provider_marked_down(candidate, runtime_policy))


def _probe(
    client_manager: Any,
    candidate: ResolvedRoute,
    runtime_policy: Any,
    *,
    credential_provider: Any = None,
) -> bool:
    manager = _manager(client_manager)
    if credential_provider is not None and _supports_credential_provider(manager.probe_provider):
        return bool(
            manager.probe_provider(
                candidate,
                runtime_policy,
                credential_provider=credential_provider,
            )
        )
    return bool(manager.probe_provider(candidate, runtime_policy))


def _dispatch(
    client_manager: Any,
    candidate: ResolvedRoute,
    messages: list[BaseMessage],
    **kwargs: Any,
) -> AIMessage:
    del client_manager
    credential_provider = kwargs.pop("credential_provider", None)
    runtime_policy = kwargs.pop("runtime_policy", None)
    tools = kwargs.pop("tools", None)
    tool_choice = kwargs.pop("tool_choice", None)
    factory = RouteChatModelFactory(credential_provider=credential_provider)
    return _invoke_with_token_escalation(
        factory,
        candidate,
        messages,
        runtime_policy=runtime_policy,
        tools=tools,
        tool_choice=tool_choice,
        **kwargs,
    )


def _invoke_with_token_escalation(
    factory: Any,
    candidate: ResolvedRoute,
    messages: list[BaseMessage],
    *,
    runtime_policy: Any = None,
    tools: list[dict[str, object]] | None = None,
    tool_choice: str | None = None,
    **kwargs: Any,
) -> AIMessage:
    rounds = int(getattr(runtime_policy, "token_escalation_rounds", 0) or 0)
    token_budget = _int_kwarg(kwargs.get("max_tokens"), 1)
    cap = _max_output_token_cap(candidate)

    for attempt in range(rounds + 1):
        build_kwargs = {
            key: value
            for key, value in kwargs.items()
            if value is not None
        }
        build_kwargs["max_tokens"] = token_budget
        chat_model = factory.build(candidate, **build_kwargs)
        if tools and hasattr(chat_model, "bind_tools"):
            if tool_choice is not None:
                chat_model = chat_model.bind_tools(tools, tool_choice=tool_choice)
            else:
                chat_model = chat_model.bind_tools(tools)
        raw_response = chat_model.invoke(messages)
        response: AIMessage = (
            raw_response
            if isinstance(raw_response, AIMessage)
            else AIMessage(content=str(raw_response))
        )
        if not _is_truncated_response(response) or attempt >= rounds:
            return response
        next_budget = token_budget * 2
        if cap is not None:
            next_budget = min(next_budget, cap)
        if next_budget <= token_budget:
            return response
        token_budget = next_budget

    return response


def _supports_credential_provider(method: Any) -> bool:
    try:
        return "credential_provider" in inspect.signature(method).parameters
    except (TypeError, ValueError):
        return False


def _mark_down(
    client_manager: Any,
    candidate: ResolvedRoute,
    exc: BaseException,
    runtime_policy: Any,
) -> None:
    manager = _manager(client_manager)
    manager.mark_provider_down(candidate, exc, runtime_policy)


def _usage_from_response(response: Mapping[str, object] | AIMessage) -> dict[str, int]:
    if isinstance(response, AIMessage):
        return _usage_from_ai_message(response)
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


def _usage_from_ai_message(response: AIMessage) -> dict[str, int]:
    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, Mapping):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    prompt_tokens = _int_value(usage.get("input_tokens") or usage.get("prompt_tokens"))
    completion_tokens = _int_value(
        usage.get("output_tokens") or usage.get("completion_tokens")
    )
    total_tokens = _int_value(usage.get("total_tokens"))
    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _is_truncated_response(response: AIMessage) -> bool:
    metadata = response.response_metadata or {}
    finish_reason = str(
        metadata.get("finish_reason") or metadata.get("stop_reason") or ""
    ).lower()
    return finish_reason in {"length", "max_tokens", "max_output_tokens"}


def _max_output_token_cap(candidate: ResolvedRoute) -> int | None:
    capability = candidate.capabilities.get("max_output_tokens")
    value = getattr(capability, "value", None)
    if isinstance(value, int | float) and value > 0:
        return int(value)
    return None


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


def _optional_int_kwarg(value: object, default: int | None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float) and value > 0:
        return int(value)
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return default


def _effective_bool(candidate: ResolvedRoute, key: str, default: bool) -> bool:
    setting = candidate.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    return value if isinstance(value, bool) else default


def _effective_int(candidate: ResolvedRoute, key: str, default: int) -> int:
    setting = candidate.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    return int(value) if isinstance(value, int | float) and value > 0 else default


def _effective_float(candidate: ResolvedRoute, key: str, default: float) -> float:
    setting = candidate.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    return float(value) if isinstance(value, int | float) else default


def _effective_optional_int(candidate: ResolvedRoute, key: str) -> int | None:
    setting = candidate.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    return int(value) if isinstance(value, int | float) and value > 0 else None


def _effective_optional_float(candidate: ResolvedRoute, key: str) -> float | None:
    setting = candidate.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, int | float) else None


def _effective_optional_bool(candidate: ResolvedRoute, key: str) -> bool | None:
    setting = candidate.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    return value if isinstance(value, bool) else None


def _effective_text(candidate: ResolvedRoute, key: str) -> str | None:
    setting = candidate.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    return value if isinstance(value, str) and value else None


def _effective_string_list(candidate: ResolvedRoute, key: str) -> list[str] | None:
    setting = candidate.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    if not isinstance(value, list):
        return None
    result = [item for item in value if isinstance(item, str)]
    return result or None


def _effective_structured_output(candidate: ResolvedRoute) -> dict[str, object] | None:
    mode = _effective_text(candidate, "structured_output.mode")
    if mode is None or mode == "none":
        return None
    result: dict[str, object] = {"mode": mode}
    schema_setting = candidate.effective_runtime_settings.get("structured_output.json_schema")
    if schema_setting is not None and isinstance(schema_setting.value, dict):
        result["json_schema"] = schema_setting.value
    strict_setting = candidate.effective_runtime_settings.get("structured_output.strict")
    if strict_setting is not None and isinstance(strict_setting.value, bool):
        result["strict"] = strict_setting.value
    return result


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


def _apply_system_prompt_prefix(
    messages: list[BaseMessage],
    system_prompt_prefix: str,
) -> list[BaseMessage]:
    prefix = system_prompt_prefix.strip()
    if not prefix:
        return list(messages)
    if messages and isinstance(messages[0], SystemMessage):
        content = _coerce_text(messages[0].content)
        merged_content = f"{prefix}\n\n{content}".strip() if content else prefix
        merged = messages[0].model_copy(update={"content": merged_content})
        return [merged, *messages[1:]]
    return [SystemMessage(content=prefix), *messages]


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


def _usage_total_calls(client_manager: Any, candidate: ResolvedRoute) -> int:
    manager = _manager(client_manager)
    usage_total_calls = getattr(manager, "usage_total_calls", None)
    if usage_total_calls is not None:
        value = usage_total_calls(candidate)
        return value if isinstance(value, int) else 0
    get_usage_stats = getattr(manager, "get_usage_stats", None)
    if get_usage_stats is None:
        return 0
    stats = get_usage_stats()
    if not isinstance(stats, Mapping):
        return 0
    provider_stats = stats.get(candidate.endpoint_id)
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
