"""
Test: test_gateway_integration.py
Covers: tasks.md α6 (integration path) +
design.md §2.2 (RoleModelEntry params feed resolver) +
requirements.md §4.1 (Studio backend -> ModelResolver -> Gateway failure payload).
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import SecretStr


class FakeRouteChatModel:
    def __init__(self, factory: FakeRouteChatModelFactory, route: Any) -> None:
        self.factory = factory
        self.route = route

    def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.factory.invocations.append({"route": self.route, "messages": messages})
        behavior = self.factory.behaviors.get(self.route.route_id, self.factory.default_behavior)
        if isinstance(behavior, BaseException):
            raise behavior
        return AIMessage(
            content=str(behavior),
            usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            response_metadata={"finish_reason": "stop"},
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


def _install_route_factory(monkeypatch: pytest.MonkeyPatch, factory: FakeRouteChatModelFactory) -> None:
    from graph_agent_gateway import gateway_chat_model

    monkeypatch.setattr(
        gateway_chat_model,
        "RouteChatModelFactory",
        lambda **_kwargs: factory,
    )


class AlwaysFailingClientManager:
    def is_provider_marked_down(self, route: Any, runtime_policy: Any) -> bool:
        return False

    def probe_provider(self, route: Any, runtime_policy: Any) -> bool:
        return True

    def mark_provider_down(self, route: Any, exc: BaseException, runtime_policy: Any) -> None:
        return None


class ProbeFallbackClientManager:
    def __init__(self) -> None:
        self.marked_down: list[str] = []

    def is_provider_marked_down(self, route: Any, runtime_policy: Any) -> bool:
        return False

    def probe_provider(self, route: Any, runtime_policy: Any) -> bool:
        return route.route_id != "dead:claude"

    def mark_provider_down(self, route: Any, exc: BaseException, runtime_policy: Any) -> None:
        self.marked_down.append(route.route_id)


class ProbeRouteFallbackClientManager:
    def __init__(self) -> None:
        self.marked_down: list[str] = []

    def is_provider_marked_down(self, route: Any, runtime_policy: Any) -> bool:
        return False

    def probe_provider(self, route: Any, runtime_policy: Any) -> bool:
        if route.route_id == "missing:model":
            class ProviderStatusError(RuntimeError):
                status_code = 404

            raise ProviderStatusError("model not found")
        return True

    def mark_provider_down(self, route: Any, exc: BaseException, runtime_policy: Any) -> None:
        self.marked_down.append(route.route_id)


class RecordingSuccessClientManager:
    def __init__(self) -> None:
        pass

    def is_provider_marked_down(self, route: Any, runtime_policy: Any) -> bool:
        return False

    def probe_provider(self, route: Any, runtime_policy: Any) -> bool:
        return True

    def mark_provider_down(self, route: Any, exc: BaseException, runtime_policy: Any) -> None:
        return None


class RecordingCallback:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


def _resolver_from_snapshot(snapshot: Any, **kwargs: Any) -> Any:
    from graph_agent_gateway.resolver import ModelResolver
    from graph_agent_gateway.storage_contracts import InMemoryConfigTruthStore

    payload = snapshot.model_dump(mode="python")
    store = InMemoryConfigTruthStore()
    user_id = "test-user"
    store.put_config(
        user_id,
        "credentials",
        {
            "schema_version": 4,
            "provider_endpoints": payload["provider_endpoints"],
            "provider_routes": payload["provider_routes"],
            "runtime_policy": payload["runtime_policy"],
        },
    )
    store.put_config(
        user_id,
        "roles",
        {
            "schema_version": 2,
            "model_profiles": payload["model_profiles"],
            "roles": payload["roles"],
        },
    )
    return ModelResolver(config_store=store, user_id=user_id, **kwargs)


def test_resolver_applies_role_model_parameters_to_gateway_model() -> None:
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    from graph_agent_gateway.registry.schema import (
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
    )

    snapshot = RegistrySnapshot(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("secret"),
            )
        },
        provider_routes={
            "openai:gpt-5": ProviderRoute(
                route_id="openai:gpt-5",
                endpoint_id="openai",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                status="verified",
            )
        },
        roles={
            "balanced": RoleEntry(
                fallback_chain=[
                    RoleRouteEntry(
                        route_id="openai:gpt-5",
                        runtime_settings={
                            "temperature": 0.3,
                            "max_output_tokens": 1234,
                        },
                    )
                ],
            )
        },
    )

    resolver = _resolver_from_snapshot(
        snapshot,
        client_manager=AlwaysFailingClientManager(),
    )
    model = resolver.resolve("balanced", phase_name="draft")

    assert isinstance(model, GatewayChatModel)
    assert model.role_name == "balanced"
    assert model.phase_name == "draft"
    assert model.temperature is None
    assert model.max_tokens == 1234
    assert model.resolved_role.routes[0].endpoint_id == "openai"
    assert model.resolved_role.routes[0].provider_model_id == "gpt-5"
    assert model.resolved_role.routes[0].effective_runtime_settings["temperature"].value == 0.3


def test_gateway_failure_path_emits_event_and_structured_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.exceptions import AllProvidersFailedError
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    from graph_agent_gateway.registry.schema import (
        ResolvedRole,
        ResolvedRoute,
        RuntimePolicy,
    )
    from langchain_core.messages import HumanMessage

    callback = RecordingCallback()
    _install_route_factory(monkeypatch, FakeRouteChatModelFactory(RuntimeError("openai:gpt-5 failed")))
    resolved_role = ResolvedRole(
        role_name="balanced",
        system_prompt_prefix="",
        runtime_policy=RuntimePolicy(),
        routes=[
            ResolvedRoute(
                role_name="balanced",
                route_id="openai:gpt-5",
                endpoint_id="openai",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                credential_ref="endpoint:openai",
                credential_fingerprint="fp",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
            )
        ],
    )
    model = GatewayChatModel(
        role_name="balanced",
        resolved_role=resolved_role,
        callbacks=(callback,),
        phase_name="draft",
        client_manager=AlwaysFailingClientManager(),
    )

    with pytest.raises(AllProvidersFailedError) as exc_info:
        model.invoke([HumanMessage(content="hello")])

    exc = exc_info.value
    assert exc.code == "[F-v3-gateway-all-providers-failed]"
    assert exc.context["role_name"] == "balanced"
    assert exc.context["phase_name"] == "draft"
    assert exc.context["failed_provider_codes"] == ["openai:gpt-5"]
    assert exc.context["last_error_chain"][0]["provider"] == "openai:gpt-5"
    assert exc.context["last_error_chain"][0]["route_id"] == "openai:gpt-5"
    assert len(callback.events) == 0


def test_probe_failure_fallback_emits_event_and_returns_second_route_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    from graph_agent_gateway.registry.schema import (
        ResolvedRole,
        ResolvedRoute,
        RuntimePolicy,
    )
    from langchain_core.messages import HumanMessage

    callback = RecordingCallback()
    client_manager = ProbeFallbackClientManager()
    factory = FakeRouteChatModelFactory(
        behaviors={"anthropic-official:claude-sonnet-4.6": "ok from fallback"}
    )
    _install_route_factory(monkeypatch, factory)
    resolved_role = ResolvedRole(
        role_name="graph_agent",
        system_prompt_prefix="",
        runtime_policy=RuntimePolicy(),
        routes=[
            ResolvedRoute(
                role_name="graph_agent",
                route_id="dead:claude",
                endpoint_id="dead",
                protocol="anthropic_compatible",
                base_url="http://127.0.0.1:9",
                credential_ref="endpoint:dead",
                credential_fingerprint="dead-fp",
                provider_model_id="claude-sonnet-4-6",
                canonical_id="claude-sonnet-4.6",
                runtime_settings={
                    "max_output_tokens": 111,
                    "temperature": 0.1,
                },
                effective_runtime_settings={
                    "max_output_tokens": {"value": 111, "source": "route_setting"},
                    "temperature": {"value": 0.1, "source": "route_setting"},
                },
            ),
            ResolvedRoute(
                role_name="graph_agent",
                route_id="anthropic-official:claude-sonnet-4.6",
                endpoint_id="anthropic-official",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.com",
                credential_ref="endpoint:anthropic-official",
                credential_fingerprint="anthropic-fp",
                provider_model_id="claude-sonnet-4-6",
                canonical_id="claude-sonnet-4.6",
                runtime_settings={
                    "max_output_tokens": 222,
                    "temperature": 0.2,
                },
                effective_runtime_settings={
                    "max_output_tokens": {"value": 222, "source": "route_setting"},
                    "temperature": {"value": 0.2, "source": "route_setting"},
                },
            ),
        ],
    )
    model = GatewayChatModel(
        role_name="graph_agent",
        resolved_role=resolved_role,
        callbacks=(callback,),
        phase_name="e2e",
        client_manager=client_manager,
    )

    result = model.invoke([HumanMessage(content="hello")])

    assert result.content == "ok from fallback"
    assert result.response_metadata["route_id"] == "anthropic-official:claude-sonnet-4.6"
    assert result.response_metadata["effective_runtime_settings"] == {
        "max_output_tokens": {"value": 222, "source": "route_setting", "message": None},
        "temperature": {"value": 0.2, "source": "route_setting", "message": None},
    }
    assert client_manager.marked_down == ["dead:claude"]
    assert [item["route"].route_id for item in factory.builds] == [
        "anthropic-official:claude-sonnet-4.6"
    ]
    assert factory.builds[0]["kwargs"]["max_tokens"] == 222
    assert factory.builds[0]["kwargs"]["temperature"] == 0.2
    assert len(callback.events) == 1
    assert callback.events[0].from_provider == "dead:claude"
    assert callback.events[0].to_provider == "anthropic-official:claude-sonnet-4.6"
    event_payload = callback.events[0].model_dump(mode="json")
    assert event_payload["event_type"] == "llm_fallback"
    assert event_payload["context"]["role_name"] == "graph_agent"
    assert event_payload["context"]["fallback_decision"] == "fallback_allowed"
    assert event_payload["context"]["from_route"] == {
        "route_id": "dead:claude",
        "endpoint_id": "dead",
        "provider_model_id": "claude-sonnet-4-6",
        "canonical_id": "claude-sonnet-4.6",
        "protocol": "anthropic_compatible",
    }
    assert event_payload["context"]["to_route"]["route_id"] == "anthropic-official:claude-sonnet-4.6"
    assert event_payload["context"]["effective_runtime_settings"] == {
        "max_output_tokens": {"value": 111, "source": "route_setting", "message": None},
        "temperature": {"value": 0.1, "source": "route_setting", "message": None},
    }


def test_probe_missing_model_error_falls_back_to_next_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    from graph_agent_gateway.registry.schema import (
        ResolvedRole,
        ResolvedRoute,
        RuntimePolicy,
    )
    from langchain_core.messages import HumanMessage

    callback = RecordingCallback()
    client_manager = ProbeRouteFallbackClientManager()
    factory = FakeRouteChatModelFactory(
        behaviors={"fallback:model": "ok after missing model fallback"}
    )
    _install_route_factory(monkeypatch, factory)
    resolved_role = ResolvedRole(
        role_name="graph_agent",
        runtime_policy=RuntimePolicy(),
        routes=[
            ResolvedRoute(
                role_name="graph_agent",
                route_id="missing:model",
                endpoint_id="missing",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.com",
                credential_ref="endpoint:missing",
                credential_fingerprint="missing-fp",
                provider_model_id="missing-model",
                canonical_id="missing-model",
            ),
            ResolvedRoute(
                role_name="graph_agent",
                route_id="fallback:model",
                endpoint_id="fallback",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.com",
                credential_ref="endpoint:fallback",
                credential_fingerprint="fallback-fp",
                provider_model_id="fallback-model",
                canonical_id="fallback-model",
            ),
        ],
    )
    model = GatewayChatModel(
        role_name="graph_agent",
        resolved_role=resolved_role,
        callbacks=(callback,),
        phase_name="e2e",
        client_manager=client_manager,
    )

    result = model.invoke([HumanMessage(content="hello")])

    assert result.content == "ok after missing model fallback"
    assert [item["route"].route_id for item in factory.builds] == ["fallback:model"]
    assert client_manager.marked_down == ["missing:model"]
    assert len(callback.events) == 1
    event_payload = callback.events[0].model_dump(mode="json")
    assert event_payload["context"]["fallback_decision"] == "fallback_allowed"
    assert event_payload["context"]["provider_status_code"] == 404


def test_gateway_passes_effective_runtime_settings_to_route_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    from graph_agent_gateway.registry.schema import (
        ResolvedRole,
        ResolvedRoute,
        RuntimePolicy,
    )
    from langchain_core.messages import HumanMessage

    client_manager = RecordingSuccessClientManager()
    factory = FakeRouteChatModelFactory()
    _install_route_factory(monkeypatch, factory)
    route = ResolvedRoute(
        role_name="graph_agent",
        route_id="openai:gpt-5",
        endpoint_id="openai",
        protocol="openai_compatible",
        base_url="https://api.openai.example/v1",
        credential_ref="endpoint:openai",
        credential_fingerprint="fp",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
        selected_profile_id="reasoning_responses",
        call_method_id="openai_responses",
        request_mapper_id="openai_responses_reasoning",
        effective_runtime_settings={
            "max_output_tokens": {"value": 333, "source": "route_setting"},
            "temperature": {"value": 0.4, "source": "route_setting"},
            "top_p": {"value": 0.9, "source": "route_setting"},
            "stop_sequences": {"value": ["END"], "source": "route_setting"},
            "seed": {"value": 42, "source": "route_setting"},
            "tool_choice": {"value": "auto", "source": "route_setting"},
            "parallel_tool_calls": {"value": False, "source": "route_setting"},
            "structured_output.mode": {"value": "json_schema", "source": "route_setting"},
            "structured_output.json_schema": {
                "value": {"name": "Answer", "schema": {"type": "object"}},
                "source": "route_setting",
            },
            "structured_output.strict": {"value": True, "source": "route_setting"},
            "reasoning.enabled": {"value": True, "source": "route_setting"},
            "reasoning.effort": {"value": "medium", "source": "route_setting"},
        },
    )
    model = GatewayChatModel(
        role_name="graph_agent",
        resolved_role=ResolvedRole(
            role_name="graph_agent",
            runtime_policy=RuntimePolicy(),
            routes=[route],
        ),
        client_manager=client_manager,
    )

    model.invoke([HumanMessage(content="hello")])

    assert [item["kwargs"] for item in factory.builds] == [
        {
            "max_tokens": 333,
            "temperature": 0.4,
            "reasoning": True,
            "top_p": 0.9,
            "stop_sequences": ["END"],
            "seed": 42,
            "parallel_tool_calls": False,
            "structured_output": {
                "mode": "json_schema",
                "json_schema": {"name": "Answer", "schema": {"type": "object"}},
                "strict": True,
            },
            "reasoning_effort": "medium",
            "call_method_id": "openai_responses",
            "request_mapper_id": "openai_responses_reasoning",
        }
    ]


def test_gateway_response_metadata_reports_actual_call_runtime_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    from graph_agent_gateway.registry.schema import (
        ResolvedRole,
        ResolvedRoute,
        RuntimePolicy,
    )
    from langchain_core.messages import HumanMessage

    factory = FakeRouteChatModelFactory()
    _install_route_factory(monkeypatch, factory)
    route = ResolvedRoute(
        role_name="graph_agent",
        route_id="anthropic:claude",
        endpoint_id="anthropic",
        protocol="anthropic_compatible",
        base_url="https://api.anthropic.example",
        credential_ref="endpoint:anthropic",
        credential_fingerprint="fp",
        provider_model_id="claude-sonnet-4-6",
        canonical_id="claude-sonnet-4.6",
        effective_runtime_settings={
            "max_output_tokens": {"value": 333, "source": "route_setting"},
            "temperature": {"value": 0.4, "source": "route_setting"},
            "reasoning.enabled": {"value": False, "source": "route_setting"},
        },
    )
    model = GatewayChatModel(
        role_name="graph_agent",
        resolved_role=ResolvedRole(
            role_name="graph_agent",
            runtime_policy=RuntimePolicy(),
            routes=[route],
        ),
        client_manager=RecordingSuccessClientManager(),
        max_tokens=555,
        temperature=1.2,
        thinking_enabled=True,
    )

    result = model.invoke([HumanMessage(content="hello")])

    assert result.response_metadata["effective_runtime_settings"]["temperature"] == {
        "value": 0.4,
        "source": "route_setting",
        "message": None,
    }
    assert result.response_metadata["actual_runtime_settings"] == {
        "max_output_tokens": {"value": 555, "source": "call_override"},
        "temperature": {
            "authored_value": 1.2,
            "provider_value": 0.6,
            "source": "call_override",
            "protocol": "anthropic_compatible",
        },
        "reasoning.enabled": {"value": True, "source": "call_override"},
    }


def test_unknown_role_raises_gateway_role_not_configured_error() -> None:
    from graph_agent_gateway.registry.schema import (
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
    )
    from graph_agent_gateway.resolver import ResourceTerminalError

    snapshot = RegistrySnapshot(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("secret"),
            )
        },
        provider_routes={
            "openai:gpt-5": ProviderRoute(
                route_id="openai:gpt-5",
                endpoint_id="openai",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
            )
        },
        roles={
            "balanced": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id="openai:gpt-5")],
            )
        },
    )

    resolver = _resolver_from_snapshot(
        snapshot,
        client_manager=AlwaysFailingClientManager(),
    )

    with pytest.raises(ResourceTerminalError) as exc_info:
        resolver.resolve("not_exist", phase_name="draft")

    assert exc_info.value.error_code == "resource.no_available_route"
    assert exc_info.value.error_payload == {"role": "not_exist"}
