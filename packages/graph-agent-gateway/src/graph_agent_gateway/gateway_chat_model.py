"""LangChain-compatible gateway chat model."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any, NoReturn, cast

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, message_chunk_to_message
from langchain_core.messages.ai import AIMessage as LangChainAIMessage
from langchain_core.messages.human import HumanMessage
from langchain_core.messages.system import SystemMessage
from langchain_core.messages.tool import ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ConfigDict, Field

from graph_agent_gateway.call_settings import (
    ActualRuntimeSettings,
    CallSettings,
    ModelDefaults,
    budget_cap,
    compose_call_settings,
    effective_runtime_settings,
    initial_budget,
    token_budget,
)
from graph_agent_gateway.events import RouteDecision
from graph_agent_gateway.exceptions import AllProvidersFailedError
from graph_agent_gateway.registry import ResolvedRole, ResolvedRoute
from graph_agent_gateway.resolve import classify_exception
from graph_agent_gateway.route_chat_model_factory import (
    RouteChatModelFactory,
    provider_request_keys,
)
from graph_agent_gateway.settings_outcome import judge_settings
from graph_agent_gateway.settings_probe import probe_call_settings
from graph_agent_gateway.tracing import emit_call_settings_event, emit_route_decision_event

logger = logging.getLogger(__name__)


def _raise_all_providers_failed(
    role_name: str,
    failures: list[dict[str, Any]],
    *,
    phase_name: str,
    cause: BaseException | None = None,
) -> NoReturn:
    """Log every per-candidate failure, then raise.

    Upstream wrappers flatten the exception to its message, so without these
    log lines a crashed run leaves no trace of WHY each provider failed."""
    for failure in failures:
        logger.warning(
            "phase=gateway_chat_model action=provider_failure role=%s phase_name=%s "
            "route=%s error=%s status=%s decision=%s shape=%s message=%s",
            role_name,
            phase_name,
            failure.get("route_id"),
            failure.get("error_type"),
            failure.get("provider_status_code"),
            failure.get("fallback_decision"),
            failure.get("history_shape"),
            str(failure.get("message"))[:500],
        )
    raise AllProvidersFailedError(role_name, failures, phase_name=phase_name) from cause


def _history_shape(messages: Sequence[Any]) -> str:
    """Compact per-message trace of the outgoing history: role + tool_call ids
    an AI message carries, and which id a ToolMessage answers — enough to spot
    an orphaned tool_call in a provider-rejected request without dumping
    content."""
    parts: list[str] = []
    for message in messages:
        kind = type(message).__name__.removesuffix("Message") or "?"
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            ids = ",".join(str(tc.get("id")) for tc in tool_calls)
            parts.append(f"{kind}[{ids}]")
        elif isinstance(message, ToolMessage):
            parts.append(f"Tool->{message.tool_call_id}")
        else:
            parts.append(kind)
    return " ".join(parts)

ToolSpec = dict[str, Any] | type | Callable[..., object] | BaseTool
_MAX_TOKENS_UNSET = object()
ANSWER_RESTARTED = "gateway_answer_restarted"
"""Key a chunk carries to say the answer begins again from here.

Published rather than private: the host folding the gateway's chunks back
into one answer is the party that has to honour it, and a contract only one
side can name is one the other side has to guess at."""


def answer_restarts_here(message: Any) -> bool:
    """True for the piece that voids every piece before it in this answer.

    The gateway retries: a bigger token budget after an answer was cut off, the
    next route after one fails. A retry produces a *different* answer, not more
    of the same one, so anyone folding the pieces back together has to drop what
    it holds when it sees this — otherwise it ends up with two attempts spliced
    into one, which is a wrong answer and not merely a wrong picture.
    """
    metadata = getattr(message, "response_metadata", None)
    return bool(isinstance(metadata, dict) and metadata.get(ANSWER_RESTARTED))


class _Conclusion:
    """Where the candidate loop leaves the finished answer for whoever wanted it whole."""

    def __init__(self) -> None:
        self.result: ChatResult | None = None


class _Attempt:
    """One try at one route, and what is left to try with it."""

    def __init__(self, *, budget: int, cap: int | None, escalations_left: int) -> None:
        self.budget = budget
        self.cap = cap
        self.escalations_left = escalations_left
        self.streamed = False

    def can_escalate(self) -> bool:
        return self.escalations_left > 0 and self._next_budget() > self.budget

    def escalate(self) -> None:
        self.budget = self._next_budget()
        self.escalations_left -= 1

    def void(self) -> Iterator[AIMessageChunk]:
        """Announce that this attempt's pieces are to be discarded.

        Silent when nothing was emitted: a marker for pieces that never existed
        would ask the caller to discard someone else's answer.
        """
        if not self.streamed:
            return
        self.streamed = False
        yield AIMessageChunk(content="", response_metadata={ANSWER_RESTARTED: True})

    def _next_budget(self) -> int:
        doubled = self.budget * 2
        return min(doubled, self.cap) if self.cap is not None else doubled


class GatewayChatModel(BaseChatModel):
    """BaseChatModel adapter with explicit provider fallback control."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    role_name: str
    resolved_role: ResolvedRole
    max_tokens: int = 4096
    temperature: float | None = None
    phase_name: str | None = None
    event_callbacks: tuple[Any, ...] = Field(default_factory=tuple)
    probe_before_call: bool = True
    thinking_enabled: bool | None = None
    runtime_setting_sources: dict[str, str] = Field(default_factory=dict)
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
        max_tokens: int | object = _MAX_TOKENS_UNSET,
        temperature: float | None = None,
        callbacks: Sequence[Any] = (),
        phase_name: str | None = None,
        probe_before_call: bool = True,
        thinking_enabled: bool | None = None,
        runtime_setting_sources: Mapping[str, str] | None = None,
        bound_tools: Sequence[Mapping[str, object]] = (),
        tool_choice: str | None = None,
        tool_kwargs: Mapping[str, object] | None = None,
        client_manager: Any = None,
        credential_provider: Any = None,
        **kwargs: Any,
    ) -> None:
        sources = dict(runtime_setting_sources or {})
        resolved_max_tokens = (
            4096 if max_tokens is _MAX_TOKENS_UNSET else token_budget(max_tokens, 4096)
        )
        if max_tokens is not _MAX_TOKENS_UNSET:
            sources.setdefault("max_output_tokens", "call_override")
        if temperature is not None:
            sources.setdefault("temperature", "call_override")
        if thinking_enabled is not None:
            sources.setdefault("reasoning.enabled", "call_override")
        super().__init__(  # type: ignore[call-arg]
            role_name=role_name,
            resolved_role=resolved_role,
            max_tokens=resolved_max_tokens,
            temperature=temperature,
            phase_name=phase_name,
            event_callbacks=tuple(callbacks),
            probe_before_call=probe_before_call,
            thinking_enabled=thinking_enabled,
            runtime_setting_sources=sources,
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

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        del stop, run_manager
        for chunk in self._answer(messages, kwargs, _Conclusion()):
            yield ChatGenerationChunk(message=chunk)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager
        conclusion = _Conclusion()
        for _ in self._answer(messages, kwargs, conclusion):
            pass
        # `_answer` either concludes or raises, so a drained stream without a
        # conclusion would mean the candidate loop found a third way out.
        assert conclusion.result is not None
        return conclusion.result

    def _answer(
        self,
        messages: list[BaseMessage],
        kwargs: dict[str, Any],
        conclusion: _Conclusion,
    ) -> Iterator[AIMessageChunk]:
        """Get one answer, in the pieces it arrives in.

        This is the only place the gateway asks a provider anything: which
        candidate route is tried, when one is skipped or marked down, when the
        same route is retried — with the same request, or without the
        preferences the provider refused — when the budget is escalated, and
        when the next route takes over. Streaming and blocking are two ways of
        reading the same walk through that policy, never two implementations
        of it.

        What each attempt asks for is settled elsewhere
        (:mod:`graph_agent_gateway.call_settings`); this walk only decides
        which route is asked and how many times.

        Every retry here replaces the answer rather than extending it, so
        before retrying, whatever was already yielded is voided (see
        `answer_restarts_here`). Without that, a caller folding the pieces back
        together would end up holding two attempts spliced into one.
        """
        request_messages = _apply_system_prompt_prefix(
            messages,
            self.resolved_role.system_prompt_prefix,
        )
        failures: list[dict[str, Any]] = []
        runtime_policy = self.resolved_role.runtime_policy
        defaults = ModelDefaults(
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            thinking_enabled=self.thinking_enabled,
            runtime_setting_sources=self.runtime_setting_sources,
        )

        for index, candidate in enumerate(self.resolved_role.routes):
            if _is_marked_down(self.client_manager, candidate, runtime_policy):
                self._decided("skipped_circuit_open", route=candidate)
                continue
            retry_same_used = False
            refused_settings: tuple[str, ...] | None = None
            attempt = _Attempt(
                budget=initial_budget(candidate, defaults, kwargs),
                cap=budget_cap(candidate),
                escalations_left=int(getattr(runtime_policy, "token_escalation_rounds", 0) or 0),
            )
            if self.probe_before_call:
                # Asked with this call's own settings, for one token. A route
                # that will not take a setting says so here, before the long
                # call starts — the same finding the failure path below can
                # only make after the request has already been paid for.
                verdict = probe_call_settings(
                    candidate,
                    self._settings_for(candidate, defaults, kwargs, budget=attempt.budget),
                    factory=self._route_factory(),
                    timeout_seconds=getattr(runtime_policy, "probe_timeout_seconds", None),
                )
                if not verdict.answers_without_them:
                    exc = verdict.refusal or RuntimeError("probe failed")
                    classification = classify_exception(exc, route_id=candidate.route_id)
                    failure = _failure_record(candidate, exc, classification.decision)
                    failure["unclassified_default"] = classification.unclassified_default
                    failure["provider_status_code"] = classification.provider_status_code
                    failures.append(failure)
                    if classification.decision != "fallback_allowed":
                        self._decided(
                            "failed_terminal",
                            route=candidate,
                            reason=f"{type(exc).__name__}: {exc}",
                            provider_status_code=classification.provider_status_code,
                        )
                        _raise_all_providers_failed(
                            self.role_name,
                            failures,
                            phase_name=self.phase_name or "<gateway>",
                            cause=exc,
                        )
                    _mark_down(self.client_manager, candidate, exc, runtime_policy)
                    self._decided(
                        "probe_failed",
                        route=candidate,
                        reason=f"{type(exc).__name__}: {exc}",
                        provider_status_code=classification.provider_status_code,
                        next_route_id=self._next_candidate_id(index + 1),
                    )
                    continue
                if verdict.refused:
                    refused_settings = verdict.refused
                    refusal = verdict.refusal
                    self._decided(
                        "dropped_rejected_settings",
                        route=candidate,
                        reason=(
                            f"probe: {type(refusal).__name__}: {refusal}"
                            f" | running without {', '.join(verdict.refused)}"
                        ),
                        provider_status_code=classify_exception(
                            refusal,
                            route_id=candidate.route_id,
                        ).provider_status_code
                        if refusal is not None
                        else None,
                    )
            # Bracketing the whole escalation sequence, not each attempt: an
            # answer that took three tries is still one answer to bill for.
            before_usage = _usage_total_calls(self.client_manager, candidate)
            while True:
                # Settled before the call rather than inside it: the failure
                # handler below has to be able to say what was asked for, and
                # composing is arithmetic on settled values — the only thing
                # that can fail here is the provider.
                settings = self._settings_for(
                    candidate,
                    defaults,
                    kwargs,
                    budget=attempt.budget,
                )
                if refused_settings is not None:
                    # Named by the probe: drop those and keep the rest. Unnamed
                    # (the failure path below): nothing is known about which
                    # one, so none of them survives.
                    settings = (
                        settings.without(refused_settings)
                        if refused_settings
                        else settings.without_preferences()
                    )
                try:
                    accumulated: AIMessageChunk | None = None
                    for piece in _dispatch(
                        candidate,
                        request_messages,
                        settings,
                        factory=self._route_factory(),
                    ):
                        accumulated = piece if accumulated is None else accumulated + piece
                        attempt.streamed = True
                        yield piece
                    response = _as_answer(accumulated)
                    if _is_truncated_response(response) and attempt.can_escalate():
                        # Read before voiding: void() is what clears the flag.
                        voided = attempt.streamed
                        attempt.escalate()
                        self._decided(
                            "escalated_budget",
                            route=candidate,
                            reason=f"answer was cut off; budget raised to {attempt.budget}",
                            voided_streamed_answer=voided,
                        )
                        yield from attempt.void()
                        continue
                    after_usage = _usage_total_calls(self.client_manager, candidate)
                    if after_usage == before_usage:
                        usage = _usage_from_response(response)
                        _record_usage(
                            self.client_manager,
                            candidate.endpoint_id,
                            usage["prompt_tokens"],
                            usage["completion_tokens"],
                        )
                    conclusion.result = self._build_chat_result(
                        response,
                        candidate,
                        settings.reported,
                    )
                    self._said_what_happened(
                        candidate,
                        settings.reported,
                        refused=refused_settings or (),
                        reasoned=_answer_reasoned(response),
                    )
                    self._decided("answered", route=candidate)
                    return
                except Exception as exc:  # noqa: BLE001 - gateway fallback boundary
                    classification = classify_exception(exc, route_id=candidate.route_id)
                    failure = _failure_record(candidate, exc, classification.decision)
                    failure["unclassified_default"] = classification.unclassified_default
                    failure["provider_status_code"] = classification.provider_status_code
                    failure["history_shape"] = _history_shape(request_messages)
                    failures.append(failure)
                    if classification.action == "retry_same_route" and not retry_same_used:
                        retry_same_used = True
                        self._decided(
                            "retried_same_route",
                            route=candidate,
                            reason=f"{type(exc).__name__}: {exc}",
                            provider_status_code=classification.provider_status_code,
                            voided_streamed_answer=attempt.streamed,
                        )
                        yield from attempt.void()
                        continue
                    if (
                        classification.scope == "request"
                        and refused_settings is None
                        and settings.preference_names
                    ):
                        # The provider read this request and refused it — the one
                        # failure a parameter can cause. Runtime settings are
                        # preferences, and a provider that will not take one has
                        # not stopped working, so ask the same route again
                        # without them: the cheapest way to tell "this parameter
                        # is wrong" from "this route is down". No table of
                        # provider wordings can do it, and the wordings are what
                        # providers keep changing. Capacity, credential and route
                        # failures never reach here: nothing about them is the
                        # settings, so nothing is gained by asking twice.
                        refused_settings = ()
                        self._decided(
                            "dropped_rejected_settings",
                            route=candidate,
                            reason=(
                                f"{type(exc).__name__}: {exc}"
                                f" | retrying without {', '.join(settings.preference_names)}"
                            ),
                            provider_status_code=classification.provider_status_code,
                            voided_streamed_answer=attempt.streamed,
                        )
                        yield from attempt.void()
                        continue
                    if classification.decision != "fallback_allowed":
                        self._decided(
                            "failed_terminal",
                            route=candidate,
                            reason=f"{type(exc).__name__}: {exc}",
                            provider_status_code=classification.provider_status_code,
                            voided_streamed_answer=attempt.streamed,
                        )
                        _raise_all_providers_failed(
                            self.role_name,
                            failures,
                            phase_name=self.phase_name or "<gateway>",
                            cause=exc,
                        )
                    _mark_down(self.client_manager, candidate, exc, runtime_policy)
                    self._decided(
                        "fell_back",
                        route=candidate,
                        reason=f"{type(exc).__name__}: {exc}",
                        provider_status_code=classification.provider_status_code,
                        next_route_id=self._next_candidate_id(index + 1),
                        voided_streamed_answer=attempt.streamed,
                    )
                    yield from attempt.void()
                    break

        self._decided("exhausted", reason=f"{len(failures)} candidate(s) failed")
        _raise_all_providers_failed(
            self.role_name,
            failures,
            phase_name=self.phase_name or "<gateway>",
        )

    def _settings_for(
        self,
        route: ResolvedRoute,
        defaults: ModelDefaults,
        call_kwargs: dict[str, Any],
        *,
        budget: int,
    ) -> CallSettings:
        """What this model asks this route for, at this budget."""
        return compose_call_settings(
            route,
            defaults=defaults,
            call_kwargs=call_kwargs,
            budget=budget,
            tools=list(self.bound_tools) or None,
            tool_choice=self.tool_choice,
        )

    def _route_factory(self) -> RouteChatModelFactory:
        """The one builder the probe and the call it precedes both come off."""
        return RouteChatModelFactory(credential_provider=self.credential_provider)

    def _said_what_happened(
        self,
        route: ResolvedRoute,
        reported: ActualRuntimeSettings,
        *,
        refused: tuple[str, ...],
        reasoned: bool | None,
    ) -> None:
        """Report what became of this call's settings, now the answer can be read."""
        emit_call_settings_event(
            callbacks=self.event_callbacks,
            phase_name=self.phase_name or "<gateway>",
            route=route,
            outcomes=judge_settings(
                reported=reported,
                carried=provider_request_keys(str(route.protocol)),
                refused=refused,
                reasoned=reasoned,
            ),
        )

    def _decided(
        self,
        decision: RouteDecision,
        *,
        route: ResolvedRoute | None = None,
        reason: str | None = None,
        provider_status_code: int | None = None,
        next_route_id: str | None = None,
        voided_streamed_answer: bool = False,
    ) -> None:
        """Say what was just decided, bound to this model's phase and listeners."""
        emit_route_decision_event(
            callbacks=self.event_callbacks,
            phase_name=self.phase_name or "<gateway>",
            decision=decision,
            route=route,
            reason=reason,
            provider_status_code=provider_status_code,
            next_route_id=next_route_id,
            voided_streamed_answer=voided_streamed_answer,
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
            runtime_setting_sources=self.runtime_setting_sources,
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
        actual_runtime_settings: ActualRuntimeSettings | None = None,
    ) -> ChatResult:
        actual_runtime_settings = actual_runtime_settings or {}
        if isinstance(response, AIMessage):
            return self._build_chat_result_from_ai_message(
                response,
                candidate,
                actual_runtime_settings,
            )

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
                "effective_runtime_settings": effective_runtime_settings(candidate),
                "actual_runtime_settings": actual_runtime_settings,
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
                "effective_runtime_settings": effective_runtime_settings(candidate),
                "actual_runtime_settings": actual_runtime_settings,
            },
        )

    def _build_chat_result_from_ai_message(
        self,
        response: AIMessage,
        candidate: ResolvedRoute,
        actual_runtime_settings: ActualRuntimeSettings | None = None,
    ) -> ChatResult:
        actual_runtime_settings = actual_runtime_settings or {}
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
            "effective_runtime_settings": effective_runtime_settings(candidate),
            "actual_runtime_settings": actual_runtime_settings,
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
                "effective_runtime_settings": effective_runtime_settings(candidate),
                "actual_runtime_settings": actual_runtime_settings,
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


def _dispatch(
    candidate: ResolvedRoute,
    messages: list[BaseMessage],
    settings: CallSettings,
    *,
    factory: RouteChatModelFactory,
) -> Iterator[AIMessageChunk]:
    """Ask one route for one answer, and hand back the pieces as they land.

    Always `stream()`, never `invoke()`, and without asking first whether this
    provider can stream: a client that has nothing to reveal gradually answers
    a stream with a single piece, which is the same answer. Asking would mean
    two call paths to keep honest for no gain.
    """
    # Typed by the one capability this needs: binding tools hands back a
    # Runnable rather than the chat model itself, and both know how to stream.
    chat_model: Runnable[LanguageModelInput, AIMessage] = factory.build(
        candidate,
        **settings.build_kwargs(),
    )
    if settings.tools and hasattr(chat_model, "bind_tools"):
        if settings.tool_choice is not None:
            chat_model = chat_model.bind_tools(settings.tools, tool_choice=settings.tool_choice)
        else:
            chat_model = chat_model.bind_tools(settings.tools)
    for piece in chat_model.stream(messages):
        yield piece if isinstance(piece, AIMessageChunk) else AIMessageChunk(content=str(piece))


def _as_answer(accumulated: AIMessageChunk | None) -> AIMessage:
    """The pieces, read as the one message the rest of the gateway works with.

    A provider that yielded nothing still answered — with nothing — and the
    candidate loop has to be able to say so rather than crash on the absence.
    """
    if accumulated is None:
        return AIMessage(content="")
    return cast(AIMessage, message_chunk_to_message(accumulated))


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


def _int_value(value: object) -> int:
    if isinstance(value, int | float) and value >= 0:
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


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


def _answer_reasoned(answer: AIMessage) -> bool:
    """Whether the finished answer shows any reasoning at all.

    Read off the answer the caller receives, not off a parallel record of it:
    "did it reason" and "what was handed over" cannot then disagree.
    """
    reasoning = answer.additional_kwargs.get("reasoning_content")
    return bool(isinstance(reasoning, str) and reasoning.strip())


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
