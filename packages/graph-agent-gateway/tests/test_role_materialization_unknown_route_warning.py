"""Materialization must SURFACE an unknown route, not silently drop it.

Data-loss fix: when a role's model_group references a ``route_id`` that is not in
the current credentials registry (route deleted / credential expired / model
retired), materialization still skips it for the runnable ``fallback_chain`` — a
non-existent route cannot be called — but it must leave a diagnostic warning in
the ``materialization_report`` instead of an untraceable ``continue``. That
warning is what lets the Studio UI show the role as partially broken instead of
the group vanishing without explanation.
"""

from __future__ import annotations

from graph_agent_gateway.registry import (
    RegistrySnapshot,
    RoleEntry,
    RoleModelGroup,
    RoleProviderModel,
)


def test_unknown_route_is_skipped_but_reported_as_warning() -> None:
    from graph_agent_gateway.role import (
        MaterializeRoleRequest,
        materialize_role,
    )

    role = RoleEntry(
        model_groups=[
            RoleModelGroup(
                canonical_id="anthropic.claude-opus-4.8",
                display_name="Claude Opus 4.8",
                provider_models=[
                    RoleProviderModel(route_id="anthropic-official:claude-opus-4-8")
                ],
            )
        ],
    )

    materialized = materialize_role(
        MaterializeRoleRequest(
            role=role,
            # A registry that does not know the role's referenced route.
            credentials=RegistrySnapshot(),
        )
    )

    # Unknown route cannot run: it stays out of the executable chain.
    assert materialized.fallback_chain == []

    # But it is no longer a silent drop — a diagnostic warning names the route.
    warnings = materialized.materialization_report["warnings"]
    unknown = [w for w in warnings if w.get("code") == "route_not_in_registry"]
    assert len(unknown) == 1
    assert unknown[0]["route_id"] == "anthropic-official:claude-opus-4-8"
    assert unknown[0]["canonical_id"] == "anthropic.claude-opus-4.8"
