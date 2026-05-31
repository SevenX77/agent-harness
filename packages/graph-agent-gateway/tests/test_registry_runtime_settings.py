"""Runtime setting schema, defaulting, and validation tests."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError


def test_role_route_entry_uses_nested_runtime_settings_and_rejects_legacy_scalars() -> None:
    from graph_agent_gateway.registry.schema import RoleRouteEntry, RuntimeSettings

    entry = RoleRouteEntry(
        route_id="anthropic-official:claude",
        runtime_settings={
            "temperature": 0.2,
            "max_output_tokens": 8192,
            "reasoning": {"enabled": True, "budget_tokens": 4096},
        },
    )

    assert isinstance(entry.runtime_settings, RuntimeSettings)
    assert entry.runtime_settings.temperature == 0.2
    assert entry.runtime_settings.max_output_tokens == 8192
    assert entry.runtime_settings.reasoning.enabled is True
    assert entry.runtime_settings.reasoning.budget_tokens == 4096

    with pytest.raises(ValidationError):
        RoleRouteEntry(route_id="anthropic-official:claude", temperature=0.2)

    with pytest.raises(ValidationError):
        RoleRouteEntry(
            route_id="anthropic-official:claude",
            runtime_settings={"provider_specific_knob": True},
        )

    with pytest.raises(ValidationError):
        RoleRouteEntry(
            route_id="anthropic-official:claude",
            runtime_settings={
                "structured_output": {
                    "mode": "json_schema",
                    "provider_specific_knob": True,
                }
            },
        )


def test_runtime_settings_defaults_are_fixed_normalized_objects() -> None:
    from graph_agent_gateway.registry.schema import RuntimeSettings, StructuredOutputSettings

    settings = RuntimeSettings()
    structured = StructuredOutputSettings()

    assert settings.temperature is None
    assert settings.max_output_tokens is None
    assert settings.reasoning.enabled is None
    assert settings.reasoning.effort is None
    assert settings.reasoning.budget_tokens is None
    assert structured.mode == "none"
    assert structured.json_schema is None
    assert structured.strict is None


def test_resolver_produces_effective_runtime_settings_with_sources() -> None:
    from graph_agent_gateway.registry.resolver import resolve_role
    from graph_agent_gateway.registry.schema import (
        CapabilityValue,
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        RoleEntry,
        RoleRouteEntry,
    )

    snapshot = RegistrySnapshot(
        provider_endpoints={
            "anthropic-official": ProviderEndpoint(
                endpoint_id="anthropic-official",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.com",
                api_key=SecretStr("secret"),
            )
        },
        provider_routes={
            "anthropic-official:claude": ProviderRoute(
                route_id="anthropic-official:claude",
                endpoint_id="anthropic-official",
                route_slug="claude",
                provider_model_id="claude",
                canonical_id="claude",
                status="verified",
                capabilities={
                    "max_output_tokens": CapabilityValue(
                        value={"max": 8192, "default": 2048},
                        source="provider_doc",
                    ),
                    "thinking_protocol": CapabilityValue(value=True, source="manual"),
                    "reasoning_budget_tokens": CapabilityValue(
                        value={"min": 1024, "default": 4096},
                        source="provider_doc",
                    ),
                },
            )
        },
        roles={
            "graph_agent": RoleEntry(
                fallback_chain=[
                    RoleRouteEntry(
                        route_id="anthropic-official:claude",
                        runtime_settings={
                            "temperature": 0.3,
                            "reasoning": {"enabled": True},
                        },
                    )
                ]
            )
        },
    )

    resolved = resolve_role(snapshot, "graph_agent")
    route = resolved.routes[0]

    assert route.runtime_settings.temperature == 0.3
    assert route.effective_runtime_settings["temperature"].value == 0.3
    assert route.effective_runtime_settings["temperature"].source == "route_setting"
    assert route.effective_runtime_settings["max_output_tokens"].value == 2048
    assert route.effective_runtime_settings["max_output_tokens"].source == (
        "route_capability_default"
    )
    assert route.effective_runtime_settings["reasoning.enabled"].value is True
    assert route.effective_runtime_settings["reasoning.enabled"].source == "route_setting"
    assert route.effective_runtime_settings["reasoning.budget_tokens"].value == 4096
    assert route.effective_runtime_settings["reasoning.budget_tokens"].source == (
        "route_capability_default"
    )


def test_profile_applied_runtime_defaults_keep_profile_source_without_runtime_dependency() -> None:
    from graph_agent_gateway.registry.resolver import resolve_role
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
        model_profiles={},
        roles={
            "graph_agent": RoleEntry(
                source_profile_id="GPT5",
                source_profile_snapshot={
                    "model_profile_id": "GPT5",
                    "route_ids": ["openai:gpt-5"],
                },
                fallback_chain=[
                    RoleRouteEntry(
                        route_id="openai:gpt-5",
                        runtime_settings_source="profile_default",
                        runtime_settings={
                            "temperature": 0.2,
                            "max_output_tokens": 8192,
                        },
                    )
                ],
            )
        },
    )

    resolved = resolve_role(snapshot, "graph_agent")

    assert resolved.routes[0].effective_runtime_settings["temperature"].source == "profile_default"
    assert resolved.routes[0].effective_runtime_settings["max_output_tokens"].source == "profile_default"


def test_runtime_settings_are_linted_against_capability_bounds() -> None:
    from graph_agent_gateway.registry.lint import lint_role_routes
    from graph_agent_gateway.registry.schema import (
        CapabilityValue,
        ProviderRoute,
        RoleEntry,
        RoleRouteEntry,
    )

    role = RoleEntry(
        fallback_chain=[
            RoleRouteEntry(
                route_id="anthropic-official:claude",
                runtime_settings={
                    "max_output_tokens": 10_000,
                    "seed": 1234,
                    "reasoning": {"enabled": True, "budget_tokens": 512},
                },
            )
        ]
    )
    route = ProviderRoute(
        route_id="anthropic-official:claude",
        endpoint_id="anthropic-official",
        route_slug="claude",
        provider_model_id="claude",
        canonical_id="claude",
        status="verified",
        capabilities={
            "max_output_tokens": CapabilityValue(
                value={"max": 8192, "default": 4096},
                source="provider_doc",
            ),
            "seed": CapabilityValue(value={"supported": False}, source="provider_doc"),
            "thinking_protocol": CapabilityValue(value=True, source="manual"),
            "reasoning_budget_tokens": CapabilityValue(
                value={"min": 1024, "default": 4096},
                source="provider_doc",
            ),
        },
    )

    results = lint_role_routes("graph_agent", role, [route])

    assert any(
        item.capability == "max_output_tokens" and item.code == "runtime_setting_invalid"
        for item in results
    )
    assert any(
        item.capability == "seed" and item.code == "runtime_setting_unsupported"
        for item in results
    )
    assert any(
        item.capability == "reasoning.budget_tokens"
        and item.code == "runtime_setting_invalid"
        for item in results
    )


def test_runtime_setting_capabilities_are_normalized_from_provider_metadata() -> None:
    from graph_agent_gateway.registry.capabilities import normalize_route_capabilities

    capabilities = normalize_route_capabilities(
        protocol="openai_compatible",
        provider_model_id="gpt-5",
        raw_capabilities={
            "temperature": {"supported": True, "min": 0, "max": 2, "default": 1},
            "top_p": {"supported": True, "min": 0, "max": 1},
            "seed": {"supported": False},
            "tool_choice": {"supported": True},
            "parallel_tool_calls": {"supported": True},
            "stop_sequences": {"supported": True},
            "structured_outputs": {"supported": True},
        },
        source="api_list",
    )

    assert capabilities["temperature"].value == {
        "supported": True,
        "min": 0,
        "max": 2,
        "default": 1,
    }
    assert capabilities["top_p"].value == {"supported": True, "min": 0, "max": 1}
    assert capabilities["seed"].value == {"supported": False}
    assert capabilities["tool_choice"].value == {"supported": True}
    assert capabilities["parallel_tool_calls"].value == {"supported": True}
    assert capabilities["stop_sequences"].value == {"supported": True}
    assert capabilities["structured_output_protocol"].value is True


def test_runtime_settings_lint_covers_non_reasoning_controls() -> None:
    from graph_agent_gateway.registry.lint import lint_role_routes
    from graph_agent_gateway.registry.schema import (
        CapabilityValue,
        ProviderRoute,
        RoleEntry,
        RoleRouteEntry,
    )

    role = RoleEntry(
        fallback_chain=[
            RoleRouteEntry(
                route_id="openai:gpt-5",
                runtime_settings={
                    "temperature": 3,
                    "top_p": 1.5,
                    "tool_choice": "required",
                    "parallel_tool_calls": True,
                    "structured_output": {"mode": "json_object"},
                    "reasoning": {"effort": "xhigh"},
                },
            )
        ]
    )
    route = ProviderRoute(
        route_id="openai:gpt-5",
        endpoint_id="openai",
        route_slug="gpt-5",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
        status="verified",
        capabilities={
            "temperature": CapabilityValue(
                value={"supported": True, "min": 0, "max": 2},
                source="provider_doc",
            ),
            "top_p": CapabilityValue(
                value={"supported": True, "min": 0, "max": 1},
                source="provider_doc",
            ),
            "tool_choice": CapabilityValue(value={"supported": False}, source="provider_doc"),
            "parallel_tool_calls": CapabilityValue(
                value={"supported": False},
                source="provider_doc",
            ),
            "reasoning_effort": CapabilityValue(
                value={"supported": True, "values": ["low", "medium", "high"]},
                source="provider_doc",
            ),
            "structured_output_protocol": CapabilityValue(value=False, source="provider_doc"),
        },
    )

    results = lint_role_routes("graph_agent", role, [route])

    assert any(item.capability == "temperature" and item.code == "runtime_setting_invalid" for item in results)
    assert any(item.capability == "top_p" and item.code == "runtime_setting_invalid" for item in results)
    assert any(item.capability == "tool_choice" and item.code == "runtime_setting_unsupported" for item in results)
    assert any(
        item.capability == "parallel_tool_calls" and item.code == "runtime_setting_unsupported"
        for item in results
    )
    assert any(
        item.capability == "structured_output" and item.code == "runtime_setting_unsupported"
        for item in results
    )
    assert any(
        item.capability == "reasoning.effort" and item.code == "runtime_setting_invalid"
        for item in results
    )
