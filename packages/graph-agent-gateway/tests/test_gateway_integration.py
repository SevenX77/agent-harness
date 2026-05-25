"""
Test: test_gateway_integration.py
Covers: tasks.md α6 (integration path) +
design.md §2.2 (RoleModelEntry params feed resolver) +
requirements.md §4.1 (Studio backend -> ModelResolver -> Gateway failure payload).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr


class AlwaysFailingClientManager:
    def is_provider_marked_down(self, route: Any, runtime_policy: Any) -> bool:
        return False

    def probe_provider(self, route: Any, runtime_policy: Any) -> bool:
        return True

    def dispatch_provider_call(self, route: Any, messages: list[Any], **kwargs: Any) -> Any:
        raise RuntimeError(f"{route.route_id} failed")

    def mark_provider_down(self, route: Any, exc: BaseException, runtime_policy: Any) -> None:
        return None


class RecordingCallback:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


def test_resolver_applies_role_model_parameters_to_gateway_model() -> None:
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    from graph_agent_gateway.registry.schema import (
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
    )
    from graph_agent_gateway.resolver import ModelResolver

    snapshot = RegistrySnapshot(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
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
                display_name="GPT-5",
                status="verified",
            )
        },
        roles={
            "balanced": RoleEntry(
                fallback_chain=[
                    RoleRouteEntry(
                        route_id="openai:gpt-5",
                        temperature=0.3,
                        max_output_tokens=1234,
                    )
                ],
            )
        },
    )

    resolver = ModelResolver(
        registry_snapshot=snapshot,
        client_manager=AlwaysFailingClientManager(),
    )
    model = resolver.resolve("balanced", phase_name="draft")

    assert isinstance(model, GatewayChatModel)
    assert model.role_name == "balanced"
    assert model.phase_name == "draft"
    assert model.temperature == 0.3
    assert model.max_tokens == 1234
    assert model.resolved_role.routes[0].endpoint_id == "openai"
    assert model.resolved_role.routes[0].provider_model_id == "gpt-5"


def test_gateway_failure_path_emits_event_and_structured_exception() -> None:
    from graph_agent_gateway.exceptions import AllProvidersFailedError
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    from graph_agent_gateway.registry.schema import (
        ResolvedRoute,
        ResolvedRole,
        RuntimePolicy,
    )
    from langchain_core.messages import HumanMessage

    callback = RecordingCallback()
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
                api_key=SecretStr("secret"),
                credential_fingerprint="fp",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                display_name="GPT-5",
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


def test_unknown_role_raises_gateway_role_not_configured_error() -> None:
    from graph_agent_gateway.exceptions import GatewayRoleNotConfiguredError
    from graph_agent_gateway.registry.schema import (
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
    )
    from graph_agent_gateway.resolver import ModelResolver

    snapshot = RegistrySnapshot(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                display_name="OpenAI",
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
                display_name="GPT-5",
            )
        },
        roles={
            "balanced": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id="openai:gpt-5")],
            )
        },
    )

    resolver = ModelResolver(
        registry_snapshot=snapshot,
        client_manager=AlwaysFailingClientManager(),
    )

    with pytest.raises(GatewayRoleNotConfiguredError) as exc_info:
        resolver.resolve("not_exist", phase_name="draft")

    assert exc_info.value.code == "[F-v3-gateway-role-not-configured]"
    assert exc_info.value.context["role_name"] == "not_exist"
