"""
Test: test_llm_fallback_event.py
Covers: tasks.md α4 (fallback tracing alignment) +
design.md §4 (β/γ3 tracing boundary) +
requirements.md §4.1 (structured fallback diagnostics).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from stream_fakes import as_one_piece

FALLBACK_EVENT_CODE = "[F-v3-gateway-llm-fallback]"


class RecordingCallback:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


class FailingCallback:
    def on_event(self, event: Any) -> None:
        raise RuntimeError("callback failed")


class FallbackStatusError(RuntimeError):
    status_code = 404


class FakeRouteChatModel:
    def __init__(self, factory: FakeRouteChatModelFactory, route: Any) -> None:
        self.factory = factory
        self.route = route

    def stream(self, messages: list[Any], **kwargs: Any) -> Iterator[AIMessageChunk]:
        del kwargs
        self.factory.invocations.append({"route": self.route, "messages": messages})
        behavior = self.factory.behaviors.get(self.route.route_id, self.factory.default_behavior)
        if isinstance(behavior, BaseException):
            raise behavior
        yield from as_one_piece(
            AIMessage(
                content=str(behavior),
                usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                response_metadata={"finish_reason": "stop"},
            )
        )


class FakeRouteChatModelFactory:
    def __init__(
        self,
        default_behavior: str | BaseException = "ok",
        behaviors: dict[str, str | BaseException] | None = None,
    ) -> None:
        self.default_behavior = default_behavior
        self.behaviors = dict(behaviors or {})
        self.builds: list[dict[str, Any]] = []
        self.invocations: list[dict[str, Any]] = []

    def build(self, route: Any, **kwargs: Any) -> FakeRouteChatModel:
        self.builds.append({"route": route, "kwargs": dict(kwargs)})
        return FakeRouteChatModel(self, route)


class FallbackClientManager:
    def __init__(
        self,
        *,
        probe_results: dict[str, bool] | None = None,
        probe_errors: dict[str, BaseException] | None = None,
    ) -> None:
        self.probe_results = dict(probe_results or {})
        self.probe_errors = dict(probe_errors or {})
        self.marked_down: list[str] = []

    def is_provider_marked_down(self, route: Any, runtime_policy: Any) -> bool:
        return False

    def probe_provider(self, route: Any, runtime_policy: Any) -> bool:
        del runtime_policy
        error = self.probe_errors.get(route.route_id)
        if error is not None:
            raise error
        return self.probe_results.get(route.route_id, True)

    def mark_provider_down(self, route: Any, exc: BaseException, runtime_policy: Any) -> None:
        del exc, runtime_policy
        self.marked_down.append(route.route_id)


def _install_route_factory(monkeypatch: pytest.MonkeyPatch, factory: FakeRouteChatModelFactory) -> None:
    from graph_agent_gateway import gateway_chat_model

    monkeypatch.setattr(
        gateway_chat_model,
        "RouteChatModelFactory",
        lambda **_kwargs: factory,
    )


def _two_route_resolved_role() -> Any:
    from graph_agent_gateway.registry.schema import ResolvedRole, ResolvedRoute, RuntimePolicy

    return ResolvedRole(
        role_name="graph_agent",
        runtime_policy=RuntimePolicy(),
        routes=[
            ResolvedRoute(
                role_name="graph_agent",
                route_id="primary:model",
                endpoint_id="primary",
                protocol="openai_compatible",
                base_url="https://api.primary.example/v1",
                credential_ref="endpoint:primary",
                credential_fingerprint="primary-fp",
                provider_model_id="primary-model",
                canonical_id="primary-model",
            ),
            ResolvedRoute(
                role_name="graph_agent",
                route_id="fallback:model",
                endpoint_id="fallback",
                protocol="openai_compatible",
                base_url="https://api.fallback.example/v1",
                credential_ref="endpoint:fallback",
                credential_fingerprint="fallback-fp",
                provider_model_id="fallback-model",
                canonical_id="fallback-model",
            ),
        ],
    )


def test_build_llm_fallback_event_has_gateway_payload_schema() -> None:
    from graph_agent_gateway.tracing import build_llm_fallback_event

    event = build_llm_fallback_event(
        phase_name="draft",
        from_provider="openai/gpt-5",
        to_provider="anthropic/claude-opus",
        reason="RateLimitError: quota exceeded",
        context={"role_name": "balanced"},
    )

    assert event.phase_name == "draft"
    assert event.from_provider == "openai/gpt-5"
    assert event.to_provider == "anthropic/claude-opus"
    assert event.reason == "RateLimitError: quota exceeded"
    assert event.code == FALLBACK_EVENT_CODE
    assert event.context == {"role_name": "balanced"}
    assert event.model_dump(mode="json")["code"] == FALLBACK_EVENT_CODE


def test_emit_llm_fallback_event_uses_unified_callback_surface() -> None:
    from graph_agent_gateway.tracing import emit_llm_fallback_event

    callback = RecordingCallback()

    emit_llm_fallback_event(
        callbacks=(callback,),
        phase_name="draft",
        from_provider="openai/gpt-5",
        to_provider="anthropic/claude-opus",
        reason="RateLimitError: quota exceeded",
        context={"role_name": "balanced"},
    )

    assert len(callback.events) == 1
    assert callback.events[0].phase_name == "draft"
    assert callback.events[0].from_provider == "openai/gpt-5"
    assert callback.events[0].to_provider == "anthropic/claude-opus"
    assert callback.events[0].code == FALLBACK_EVENT_CODE


def test_callback_failure_does_not_mask_fallback_event_delivery() -> None:
    from graph_agent_gateway.tracing import emit_llm_fallback_event

    callback = RecordingCallback()

    emit_llm_fallback_event(
        callbacks=(FailingCallback(), callback),
        phase_name="draft",
        from_provider="openai/gpt-5",
        to_provider="<none>",
        reason="TimeoutError: request timed out",
        context={"role_name": "balanced"},
    )

    assert len(callback.events) == 1
    assert callback.events[0].to_provider == "<none>"
    assert callback.events[0].code == FALLBACK_EVENT_CODE


def test_llm_fallback_event_code_is_not_call_site_configurable() -> None:
    from graph_agent_gateway.events import LLMFallbackEvent

    with pytest.raises(TypeError):
        LLMFallbackEvent(
            phase_name="draft",
            from_provider="openai/gpt-5",
            to_provider="anthropic/claude-opus",
            reason="RateLimitError: quota exceeded",
            context={"role_name": "balanced"},
            **{"code": "[F-v3-gateway-all-providers-failed]"},
        )


def test_tracing_helpers_reject_call_site_code_override() -> None:
    from graph_agent_gateway.tracing import build_llm_fallback_event, emit_llm_fallback_event

    with pytest.raises(TypeError):
        build_llm_fallback_event(
            phase_name="draft",
            from_provider="openai/gpt-5",
            to_provider="anthropic/claude-opus",
            reason="RateLimitError: quota exceeded",
            context={"role_name": "balanced"},
            **{"code": "[F-v3-gateway-all-providers-failed]"},
        )

    with pytest.raises(TypeError):
        emit_llm_fallback_event(
            callbacks=(),
            phase_name="draft",
            from_provider="openai/gpt-5",
            to_provider="anthropic/claude-opus",
            reason="RateLimitError: quota exceeded",
            context={"role_name": "balanced"},
            **{"code": "[F-v3-gateway-all-providers-failed]"},
        )


@pytest.mark.parametrize(
    ("trigger", "client_manager", "factory"),
    [
        (
            "probe_exception",
            FallbackClientManager(
                probe_errors={"primary:model": FallbackStatusError("model not found")}
            ),
            FakeRouteChatModelFactory(behaviors={"fallback:model": "ok after probe exception"}),
        ),
        (
            "probe_false",
            FallbackClientManager(probe_results={"primary:model": False}),
            FakeRouteChatModelFactory(behaviors={"fallback:model": "ok after probe false"}),
        ),
        (
            "dispatch_exception",
            FallbackClientManager(),
            FakeRouteChatModelFactory(
                behaviors={
                    "primary:model": FallbackStatusError("dispatch rejected"),
                    "fallback:model": "ok after dispatch exception",
                }
            ),
        ),
    ],
)
def test_gateway_generate_fallback_paths_emit_dedicated_event_code(
    monkeypatch: pytest.MonkeyPatch,
    trigger: str,
    client_manager: FallbackClientManager,
    factory: FakeRouteChatModelFactory,
) -> None:
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    from langchain_core.messages import HumanMessage

    del trigger
    callback = RecordingCallback()
    _install_route_factory(monkeypatch, factory)
    model = GatewayChatModel(
        role_name="graph_agent",
        resolved_role=_two_route_resolved_role(),
        callbacks=(callback,),
        phase_name="e2e",
        client_manager=client_manager,
    )

    result = model.invoke([HumanMessage(content="hello")])

    assert result.content.startswith("ok after")
    assert client_manager.marked_down == ["primary:model"]
    assert len(callback.events) == 1
    event = callback.events[0]
    assert event.from_provider == "primary:model"
    assert event.to_provider == "fallback:model"
    assert event.code == FALLBACK_EVENT_CODE
    assert event.model_dump(mode="json")["code"] == FALLBACK_EVENT_CODE
