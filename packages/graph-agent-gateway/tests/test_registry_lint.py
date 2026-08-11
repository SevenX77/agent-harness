"""Registry lint tests."""

from __future__ import annotations


def test_lint_key_mapping_and_error_missing_blocks() -> None:
    from graph_agent_gateway.registry import ProviderRoute, RoleEntry, RoleRouteEntry
    from graph_agent_gateway.registry.lint import capability_key_for_lint, lint_role_routes

    assert capability_key_for_lint("thinking") == "thinking_protocol"
    assert capability_key_for_lint("tool_calling") == "tool_protocol"

    role = RoleEntry(
        fallback_chain=[RoleRouteEntry(route_id="anthropic-official:claude")],
        lint_requirements={"thinking": "error", "tool_calling": "warn"},
    )
    route = ProviderRoute(
        route_id="anthropic-official:claude",
        endpoint_id="anthropic-official",
        route_slug="claude",
        provider_model_id="claude",
        canonical_id="claude",
        status="verified",
    )

    results = lint_role_routes("graph_agent", role, [route])

    assert any(item.capability == "thinking" and item.blocking for item in results)
    assert any(item.capability == "tool_calling" and not item.blocking for item in results)


def test_verified_capability_satisfies_error_lint() -> None:
    from graph_agent_gateway.registry import CapabilityValue, ProviderRoute, RoleEntry
    from graph_agent_gateway.registry.lint import lint_role_routes

    role = RoleEntry(lint_requirements={"thinking": "error"}, fallback_chain=[])
    route = ProviderRoute(
        route_id="anthropic-official:claude",
        endpoint_id="anthropic-official",
        route_slug="claude",
        provider_model_id="claude",
        canonical_id="claude",
        status="verified",
        capabilities={
            "thinking_protocol": CapabilityValue(
                value="anthropic_v1",
                source="probed_verified",
            )
        },
    )

    assert lint_role_routes("graph_agent", role, [route]) == []


def test_runtime_thinking_settings_are_blocked_when_route_cannot_support_them() -> None:
    from graph_agent_gateway.registry import ProviderRoute, RoleEntry, RoleRouteEntry
    from graph_agent_gateway.registry.lint import lint_role_routes

    role = RoleEntry(
        fallback_chain=[
            RoleRouteEntry(
                route_id="anthropic-official:claude",
                runtime_settings={
                    "reasoning": {"enabled": True},
                    "max_output_tokens": 8192,
                },
            )
        ],
    )
    route = ProviderRoute(
        route_id="anthropic-official:claude",
        endpoint_id="anthropic-official",
        route_slug="claude",
        provider_model_id="claude",
        canonical_id="claude",
        status="verified",
    )

    results = lint_role_routes("graph_agent", role, [route])

    assert any(
        item.capability == "thinking" and item.code == "runtime_setting_unsupported" and item.blocking
        for item in results
    )


def test_runtime_token_floor_blocks_invalid_thinking_budget() -> None:
    from graph_agent_gateway.registry import (
        CapabilityValue,
        ProviderRoute,
        RoleEntry,
        RoleRouteEntry,
    )
    from graph_agent_gateway.registry.lint import lint_role_routes

    role = RoleEntry(
        fallback_chain=[
            RoleRouteEntry(
                route_id="anthropic-official:claude",
                runtime_settings={
                    "reasoning": {"enabled": True, "budget_tokens": 512},
                    "max_output_tokens": 1024,
                },
            )
        ],
    )
    route = ProviderRoute(
        route_id="anthropic-official:claude",
        endpoint_id="anthropic-official",
        route_slug="claude",
        provider_model_id="claude",
        canonical_id="claude",
        status="verified",
        capabilities={
            "thinking_protocol": CapabilityValue(value=True, source="manual"),
            "min_thinking_budget_tokens": CapabilityValue(value=1024, source="provider_doc"),
            "requires_thinking_budget_lt_max_output": CapabilityValue(value=True, source="provider_doc"),
        },
    )

    results = lint_role_routes("graph_agent", role, [route])

    assert any(item.capability == "reasoning.budget_tokens" and item.code == "runtime_setting_invalid" for item in results)
    assert any(item.capability == "max_output_tokens" and item.code == "runtime_setting_invalid" for item in results)


def test_runtime_thinking_budget_is_blocked_when_manual_budget_is_unsupported() -> None:
    from graph_agent_gateway.registry import (
        CapabilityValue,
        ProviderRoute,
        RoleEntry,
        RoleRouteEntry,
    )
    from graph_agent_gateway.registry.lint import lint_role_routes

    role = RoleEntry(
        fallback_chain=[
            RoleRouteEntry(
                route_id="anthropic-official:claude-opus-4.7",
                runtime_settings={
                    "reasoning": {"enabled": True, "budget_tokens": 4096},
                    "max_output_tokens": 8192,
                },
            )
        ],
    )
    route = ProviderRoute(
        route_id="anthropic-official:claude-opus-4.7",
        endpoint_id="anthropic-official",
        route_slug="claude-opus-4.7",
        provider_model_id="claude-opus-4-7",
        canonical_id="claude-opus-4.7",
        status="verified",
        capabilities={
            "thinking_protocol": CapabilityValue(value=True, source="probed_verified"),
            "adaptive_thinking": CapabilityValue(value=True, source="provider_doc"),
            "manual_thinking_budget_supported": CapabilityValue(value=False, source="provider_doc"),
        },
    )

    results = lint_role_routes("premium", role, [route])

    assert any(
        item.capability == "reasoning.budget_tokens"
        and item.code == "runtime_setting_unsupported"
        and item.blocking
        for item in results
    )


def test_adaptive_thinking_without_manual_budget_does_not_require_default_budget_floor() -> None:
    from graph_agent_gateway.registry import (
        CapabilityValue,
        ProviderRoute,
        RoleEntry,
        RoleRouteEntry,
    )
    from graph_agent_gateway.registry.lint import lint_role_routes

    role = RoleEntry(
        fallback_chain=[
            RoleRouteEntry(
                route_id="anthropic-official:claude-haiku",
                runtime_settings={
                    "reasoning": {"enabled": True},
                    "max_output_tokens": 1024,
                },
            )
        ],
    )
    route = ProviderRoute(
        route_id="anthropic-official:claude-haiku",
        endpoint_id="anthropic-official",
        route_slug="claude-haiku",
        provider_model_id="claude-haiku",
        canonical_id="claude-haiku",
        status="verified",
        capabilities={
            "thinking_protocol": CapabilityValue(value=True, source="probed_verified"),
            "adaptive_thinking": CapabilityValue(value=True, source="provider_doc"),
            "manual_thinking_budget_supported": CapabilityValue(value=True, source="provider_doc"),
            "min_thinking_budget_tokens": CapabilityValue(value=1024, source="provider_doc"),
            "default_thinking_budget_tokens": CapabilityValue(value=4096, source="provider_doc"),
            "requires_thinking_budget_lt_max_output": CapabilityValue(value=True, source="provider_doc"),
        },
    )

    results = lint_role_routes("graph_agent", role, [route])

    assert not any(item.code == "runtime_setting_invalid" for item in results)


def test_manual_thinking_without_explicit_budget_requires_default_budget_room() -> None:
    from graph_agent_gateway.registry import (
        CapabilityValue,
        ProviderRoute,
        RoleEntry,
        RoleRouteEntry,
    )
    from graph_agent_gateway.registry.lint import lint_role_routes

    role = RoleEntry(
        fallback_chain=[
            RoleRouteEntry(
                route_id="anthropic-official:claude-haiku",
                runtime_settings={
                    "reasoning": {"enabled": True},
                    "max_output_tokens": 1024,
                },
            )
        ],
    )
    route = ProviderRoute(
        route_id="anthropic-official:claude-haiku",
        endpoint_id="anthropic-official",
        route_slug="claude-haiku",
        provider_model_id="claude-haiku",
        canonical_id="claude-haiku",
        status="verified",
        capabilities={
            "thinking_protocol": CapabilityValue(value=True, source="probed_verified"),
            "adaptive_thinking": CapabilityValue(value=False, source="provider_doc"),
            "manual_thinking_budget_supported": CapabilityValue(value=True, source="provider_doc"),
            "min_thinking_budget_tokens": CapabilityValue(value=1024, source="provider_doc"),
            "default_thinking_budget_tokens": CapabilityValue(value=4096, source="provider_doc"),
            "requires_thinking_budget_lt_max_output": CapabilityValue(value=True, source="provider_doc"),
        },
    )

    results = lint_role_routes("graph_agent", role, [route])

    assert any(item.capability == "max_output_tokens" and item.code == "runtime_setting_invalid" for item in results)
