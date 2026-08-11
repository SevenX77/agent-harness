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


class NoCircuits:
    def get_active_circuits(self, **kwargs: object) -> list[object]:
        return []


class _RoleIntent:
    def __init__(self) -> None:
        self.provider_preference = "manual_order"
        self.thinking = False
        self.max_output_tokens = None
        self.temperature = None


class _ProviderModel:
    def __init__(self, route_id: str) -> None:
        self.route_id = route_id


class _Group:
    def __init__(self, canonical_id: str, route_id: str) -> None:
        self.canonical_id = canonical_id
        self.provider_models = [_ProviderModel(route_id)]


class _Role:
    def __init__(self, group: _Group) -> None:
        self.model_fallback_enabled = True
        self.intent = _RoleIntent()
        self.model_groups = [group]


class _EmptyCredentials:
    """A registry that does not know the role's referenced route."""

    def __init__(self) -> None:
        self.provider_routes: dict[str, object] = {}
        self.provider_endpoints: dict[str, object] = {}


def test_unknown_route_is_skipped_but_reported_as_warning() -> None:
    from graph_agent_gateway.role import (
        MaterializeRoleRequest,
        materialize_role,
    )

    role = _Role(_Group("anthropic.claude-opus-4.8", "anthropic-official:claude-opus-4-8"))

    materialized = materialize_role(
        MaterializeRoleRequest(
            role=role,
            credentials=_EmptyCredentials(),
            health_store=NoCircuits(),
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
