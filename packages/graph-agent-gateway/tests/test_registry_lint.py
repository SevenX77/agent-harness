"""Registry lint tests."""

from __future__ import annotations


def test_lint_key_mapping_and_error_missing_blocks() -> None:
    from graph_agent_gateway.registry.lint import capability_key_for_lint, lint_role_routes
    from graph_agent_gateway.registry.schema import ProviderRoute, RoleEntry, RoleRouteEntry

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
        display_name="Claude",
        status="verified",
    )

    results = lint_role_routes("graph_agent", role, [route])

    assert any(item.capability == "thinking" and item.blocking for item in results)
    assert any(item.capability == "tool_calling" and not item.blocking for item in results)


def test_verified_capability_satisfies_error_lint() -> None:
    from graph_agent_gateway.registry.lint import lint_role_routes
    from graph_agent_gateway.registry.schema import CapabilityValue, ProviderRoute, RoleEntry

    role = RoleEntry(lint_requirements={"thinking": "error"}, fallback_chain=[])
    route = ProviderRoute(
        route_id="anthropic-official:claude",
        endpoint_id="anthropic-official",
        route_slug="claude",
        provider_model_id="claude",
        canonical_id="claude",
        display_name="Claude",
        status="verified",
        capabilities={
            "thinking_protocol": CapabilityValue(
                value="anthropic_v1",
                source="probed_verified",
            )
        },
    )

    assert lint_role_routes("graph_agent", role, [route]) == []
