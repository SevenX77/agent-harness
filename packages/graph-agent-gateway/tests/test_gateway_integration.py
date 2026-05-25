"""
Test: test_gateway_integration.py
Covers: tasks.md α6 (integration path) +
design.md §2.2 (RoleModelEntry params feed resolver) +
requirements.md §4.1 (Studio backend -> ModelResolver -> Gateway failure payload).
"""

from __future__ import annotations

from typing import Any

import pytest


class AlwaysFailingClientManager:
    def is_provider_marked_down(self, provider_code: str) -> bool:
        return False

    def probe_provider(self, provider: Any) -> bool:
        return True

    def dispatch_provider_call(self, provider: Any, messages: list[Any], **kwargs: Any) -> Any:
        raise RuntimeError(f"{provider.provider_code} failed")

    def mark_provider_down(self, provider_code: str, exc: BaseException) -> None:
        return None


class RecordingCallback:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


def test_resolver_applies_role_model_parameters_to_gateway_model() -> None:
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    from graph_agent_gateway.llm_config import (
        ModelEntry,
        ProviderEntry,
        RoleEntry,
        RoleModelEntry,
        RolesData,
    )
    from graph_agent_gateway.resolver import ModelResolver

    roles = RolesData(
        models={
            "GPT5": ModelEntry(
                name="GPT-5",
                reasoning=True,
                providers={"openai": "gpt-5"},
            )
        },
        providers={
            "openai": ProviderEntry(
                name="OpenAI",
                type="openai_compatible",
            )
        },
        roles={
            "balanced": RoleEntry(
                model_fallback=False,
                active_model="GPT5",
                models={
                    "GPT5": RoleModelEntry(
                        providers=["openai"],
                        temperature=0.3,
                        max_tokens=1234,
                    )
                },
            )
        },
    )

    resolver = ModelResolver(roles_data=roles, client_manager=AlwaysFailingClientManager())
    model = resolver.resolve("balanced", phase_name="draft")

    assert isinstance(model, GatewayChatModel)
    assert model.role_name == "balanced"
    assert model.phase_name == "draft"
    assert model.temperature == 0.3
    assert model.max_tokens == 1234
    assert model.resolved_role.call_chain[0].provider_code == "openai"
    assert model.resolved_role.call_chain[0].model_name == "gpt-5"


def test_gateway_failure_path_emits_event_and_structured_exception() -> None:
    from graph_agent_gateway.exceptions import AllProvidersFailedError
    from graph_agent_gateway.gateway_chat_model import GatewayChatModel
    from graph_agent_gateway.llm_config import (
        ModelDef,
        ProviderDef,
        ResolvedProvider,
        ResolvedRole,
    )
    from langchain_core.messages import HumanMessage

    callback = RecordingCallback()
    provider_def = ProviderDef(name="OpenAI", type="openai_compatible")
    model_def = ModelDef(name="GPT-5", providers={"openai": "gpt-5"})
    resolved_role = ResolvedRole(
        role_name="balanced",
        temperature=0.7,
        system_prompt_prefix="",
        active_model_code="GPT5",
        model_fallback=False,
        call_chain=[
            ResolvedProvider(
                provider_code="openai",
                provider_def=provider_def,
                model_name="gpt-5",
                model_def=model_def,
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
    assert exc.context["failed_provider_codes"] == ["openai/gpt-5"]
    assert exc.context["last_error_chain"][0]["provider"] == "openai/gpt-5"
    assert len(callback.events) == 1
    assert callback.events[0].from_provider == "openai/gpt-5"
    assert callback.events[0].to_provider == "<none>"


def test_unknown_role_raises_gateway_role_not_configured_error() -> None:
    from graph_agent_gateway.exceptions import GatewayRoleNotConfiguredError
    from graph_agent_gateway.llm_config import (
        ModelEntry,
        ProviderEntry,
        RoleEntry,
        RoleModelEntry,
        RolesData,
    )
    from graph_agent_gateway.resolver import ModelResolver

    roles = RolesData(
        models={"GPT5": ModelEntry(name="GPT-5", providers={"openai": "gpt-5"})},
        providers={"openai": ProviderEntry(name="OpenAI", type="openai_compatible")},
        roles={
            "balanced": RoleEntry(
                active_model="GPT5",
                models={"GPT5": RoleModelEntry(providers=["openai"])},
            )
        },
    )

    resolver = ModelResolver(roles_data=roles, client_manager=AlwaysFailingClientManager())

    with pytest.raises(GatewayRoleNotConfiguredError) as exc_info:
        resolver.resolve("not_exist", phase_name="draft")

    assert exc_info.value.code == "[F-v3-gateway-role-not-configured]"
    assert exc_info.value.context["role_name"] == "not_exist"
