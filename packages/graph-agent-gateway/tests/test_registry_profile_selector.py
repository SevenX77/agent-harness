"""Verified route profile selection tests."""

from __future__ import annotations

import pytest
from pydantic import SecretStr


def _endpoint(protocol: str = "anthropic_compatible"):
    from graph_agent_gateway.registry.schema import ProviderEndpoint

    return ProviderEndpoint(
        endpoint_id="provider",
        protocol=protocol,
        base_url="https://provider.example",
        api_key=SecretStr("secret"),
    )


def _route(provider_model_id: str, profiles: list[object], protocol: str = "anthropic_compatible"):
    from graph_agent_gateway.registry.schema import CapabilityValue, ProviderRoute

    return ProviderRoute(
        route_id="provider:model",
        endpoint_id="provider",
        route_slug="model",
        provider_model_id=provider_model_id,
        canonical_id="model",
        status="verified",
        capabilities={
            "thinking_protocol": CapabilityValue(value=True, source="probed_verified"),
        },
        verified_profiles=profiles,
    )


def _profile(
    profile_id: str,
    capability: str,
    method_id: str,
    mapper_id: str,
    *,
    default: bool = False,
    fallback_rank: int = 1,
    runtime_overrides: dict[str, object] | None = None,
    input_modalities: list[str] | None = None,
):
    from graph_agent_gateway.registry.schema import VerifiedProfile

    return VerifiedProfile(
        profile_id=profile_id,
        capability=capability,
        method_id=method_id,
        request_mapper_id=mapper_id,
        status="ready",
        default=default,
        fallback_rank=fallback_rank,
        input_modalities=input_modalities or ["text"],
        output_modalities=["text"],
        runtime_overrides=runtime_overrides or {},
    )


def _snapshot(route: object, *, protocol: str = "anthropic_compatible", runtime_settings=None):
    from graph_agent_gateway.registry.schema import RegistrySnapshot, RoleEntry, RoleRouteEntry

    return RegistrySnapshot(
        provider_endpoints={"provider": _endpoint(protocol)},
        provider_routes={"provider:model": route},
        roles={
            "writer": RoleEntry(
                fallback_chain=[
                    RoleRouteEntry(
                        route_id="provider:model",
                        runtime_settings=runtime_settings or {},
                    )
                ],
            )
        },
    )


def test_resolver_maps_preferred_thinking_to_anthropic_adaptive_profile() -> None:
    from graph_agent_gateway.registry.resolver import resolve_role

    route = _route(
        "claude-opus-4-7",
        [
            _profile(
                "text",
                "text_chat",
                "anthropic_messages",
                "anthropic_text",
                default=True,
                fallback_rank=2,
            ),
            _profile(
                "thinking_adaptive",
                "thinking",
                "anthropic_messages",
                "anthropic_thinking_adaptive",
                default=True,
                fallback_rank=1,
                runtime_overrides={"reasoning": {"enabled": True, "effort": "low"}},
            ),
        ],
    )

    resolved = resolve_role(
        _snapshot(route, runtime_settings={"reasoning": {"enabled": True}}),
        "writer",
    )

    selected = resolved.routes[0]
    assert selected.selected_profile_id == "thinking_adaptive"
    assert selected.call_method_id == "anthropic_messages"
    assert selected.request_mapper_id == "anthropic_thinking_adaptive"
    assert selected.effective_runtime_settings["reasoning.enabled"].value is True
    assert selected.effective_runtime_settings["reasoning.effort"].value == "low"
    assert selected.effective_runtime_settings["reasoning.effort"].source == "profile_default"


def test_resolver_maps_manual_thinking_profile_defaults_to_budget_tokens() -> None:
    from graph_agent_gateway.registry.resolver import resolve_role

    route = _route(
        "claude-opus-4-1-20250805",
        [
            _profile("text", "text_chat", "anthropic_messages", "anthropic_text", default=True),
            _profile(
                "thinking_manual",
                "thinking",
                "anthropic_messages",
                "anthropic_thinking_manual_budget",
                default=True,
                runtime_overrides={"reasoning": {"enabled": True, "budget_tokens": 4096}},
            ),
        ],
    )

    resolved = resolve_role(
        _snapshot(route, runtime_settings={"reasoning": {"enabled": True}}),
        "writer",
    )

    selected = resolved.routes[0]
    assert selected.selected_profile_id == "thinking_manual"
    assert selected.request_mapper_id == "anthropic_thinking_manual_budget"
    assert selected.effective_runtime_settings["reasoning.budget_tokens"].value == 4096
    assert selected.effective_runtime_settings["reasoning.budget_tokens"].source == "profile_default"


def test_required_thinking_rejects_text_only_verified_profiles() -> None:
    from graph_agent_gateway.registry.resolver import RegistryResolutionError, resolve_role

    route = _route(
        "claude-haiku-4-5",
        [
            _profile("text", "text_chat", "anthropic_messages", "anthropic_text", default=True),
        ],
    )

    with pytest.raises(RegistryResolutionError, match="no verified reasoning profile"):
        resolve_role(_snapshot(route, runtime_settings={"reasoning": {"enabled": True}}), "writer")


def test_openai_defaults_to_responses_when_responses_and_chat_profiles_both_work() -> None:
    from graph_agent_gateway.registry.resolver import resolve_role

    route = _route(
        "gpt-5",
        [
            _profile(
                "text_responses",
                "text_chat",
                "openai_responses",
                "openai_responses_text",
                default=True,
                fallback_rank=1,
            ),
            _profile(
                "text_chat",
                "text_chat",
                "openai_chat_completions",
                "openai_chat_completions_text",
                fallback_rank=2,
            ),
        ],
        protocol="openai_compatible",
    )

    resolved = resolve_role(_snapshot(route, protocol="openai_compatible"), "writer")

    assert resolved.routes[0].selected_profile_id == "text_responses"
    assert resolved.routes[0].call_method_id == "openai_responses"
    assert resolved.routes[0].request_mapper_id == "openai_responses_text"


def test_openai_required_reasoning_does_not_downgrade_to_chat_text_profile() -> None:
    from graph_agent_gateway.registry.resolver import RegistryResolutionError, resolve_role

    route = _route(
        "gpt-5.3-chat-latest",
        [
            _profile(
                "text_chat",
                "text_chat",
                "openai_chat_completions",
                "openai_chat_completions_text",
                default=True,
            ),
        ],
        protocol="openai_compatible",
    )

    with pytest.raises(RegistryResolutionError, match="no verified reasoning profile"):
        resolve_role(
            _snapshot(route, protocol="openai_compatible", runtime_settings={"reasoning": {"enabled": True}}),
            "writer",
        )


def test_ark_chat_only_model_selects_ark_chat_profile() -> None:
    from graph_agent_gateway.registry.resolver import resolve_role

    route = _route(
        "doubao-1-5-pro-32k-250115",
        [
            _profile(
                "text_chat",
                "text_chat",
                "ark_chat",
                "ark_chat_text",
                default=True,
            ),
        ],
        protocol="ark_runtime",
    )

    resolved = resolve_role(_snapshot(route, protocol="ark_runtime"), "writer")

    assert resolved.routes[0].call_method_id == "ark_chat"
    assert resolved.routes[0].request_mapper_id == "ark_chat_text"


def test_selector_can_require_image_input_and_thinking_for_deepseek_compatibility() -> None:
    from graph_agent_gateway.registry.profile_selector import select_verified_profile
    from graph_agent_gateway.registry.schema import RuntimeSettings

    route = _route(
        "deepseek-v4-pro",
        [
            _profile(
                "native_text_reasoning",
                "reasoning",
                "deepseek_chat_completions",
                "deepseek_chat_completions_reasoning_effort",
                default=True,
                input_modalities=["text"],
            ),
            _profile(
                "anthropic_image_thinking",
                "image_input+thinking",
                "deepseek_anthropic_messages",
                "deepseek_anthropic_messages_image_thinking",
                default=True,
                input_modalities=["text", "image"],
            ),
        ],
        protocol="openai_compatible",
    )

    selected = select_verified_profile(
        route,
        RuntimeSettings(reasoning={"enabled": True}),
        required_input_modalities={"image"},
    )

    assert selected.profile_id == "anthropic_image_thinking"
    assert selected.method_id == "deepseek_anthropic_messages"
    assert selected.request_mapper_id == "deepseek_anthropic_messages_image_thinking"
