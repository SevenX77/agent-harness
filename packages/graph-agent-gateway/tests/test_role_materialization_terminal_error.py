"""A role that cannot run says so, instead of handing back an empty list.

The design names one entry point — ``materialize_role(request) -> MaterializedRole``
(`docs/mvp1-three-module-interface-design-and-changes-2026-06-11/01-design.md:102`)
— and the rule that an empty fallback chain must carry an explicit terminal
error. That rule was carried by a second, test-only ``MaterializedRole`` in the
projection module, while the function Studio actually calls returned an empty
chain and said nothing. Then the caller learned the role was unrunnable only by
running it.

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError


class NoCircuits:
    def get_active_circuits(self, **kwargs: object) -> list[object]:
        return []


class _RoleIntent:
    def __init__(self) -> None:
        self.provider_preference = "manual_order"
        self.thinking = False
        self.max_output_tokens = None
        self.temperature = None
        self.reasoning_effort = None


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


class _Credentials:
    def __init__(self, endpoint: object, route: object) -> None:
        self.provider_endpoints = {"openai": endpoint}
        self.provider_routes = {"openai:gpt-5": route}


def _credentials(*, route_status: str) -> _Credentials:
    from graph_agent_gateway.registry import ProviderEndpoint, ProviderRoute

    return _Credentials(
        ProviderEndpoint(
            endpoint_id="openai",
            protocol="openai_compatible",
            base_url="https://api.openai.example/v1",
            api_key=SecretStr("secret"),
            status="verified",
        ),
        ProviderRoute(
            route_id="openai:gpt-5",
            endpoint_id="openai",
            route_slug="gpt-5",
            provider_model_id="gpt-5",
            canonical_id="gpt-5",
            status=route_status,
        ),
    )


def test_a_materialized_role_with_nothing_to_run_cannot_stay_silent() -> None:
    from graph_agent_gateway.role import MaterializedRole

    with pytest.raises(ValidationError):
        MaterializedRole(fallback_chain=[], materialization_report={})

    said = MaterializedRole(
        fallback_chain=[],
        materialization_report={},
        error_code="resource.no_available_route",
    )

    assert said.error_code == "resource.no_available_route"


def test_a_role_whose_only_route_is_unknown_reports_the_terminal_error() -> None:
    from graph_agent_gateway.role import MaterializeRoleRequest, materialize_role

    materialized = materialize_role(
        MaterializeRoleRequest(
            role=_Role(_Group("gpt-5", "openai:gpt-5")),
            credentials=_EmptyCredentials(),
            health_store=NoCircuits(),
        )
    )

    assert materialized.fallback_chain == []
    assert materialized.error_code == "resource.no_available_route"
    # The reason each route was excluded stays where the details live; the error
    # code is the verdict, not a second copy of the diagnosis.
    warnings = materialized.materialization_report["warnings"]
    assert [warning["code"] for warning in warnings] == ["route_not_in_registry"]


def test_a_role_whose_only_route_failed_reports_the_terminal_error() -> None:
    from graph_agent_gateway.role import MaterializeRoleRequest, materialize_role

    materialized = materialize_role(
        MaterializeRoleRequest(
            role=_Role(_Group("gpt-5", "openai:gpt-5")),
            credentials=_credentials(route_status="failed"),
            health_store=NoCircuits(),
        )
    )

    assert materialized.fallback_chain == []
    assert materialized.error_code == "resource.no_available_route"
    skipped = materialized.materialization_report["skipped_provider_details"]
    assert [detail["route_id"] for detail in skipped] == ["openai:gpt-5"]
    assert skipped[0]["reason_code"] == "model_failed"


def test_a_role_with_a_usable_route_reports_no_error() -> None:
    from graph_agent_gateway.role import MaterializeRoleRequest, materialize_role

    materialized = materialize_role(
        MaterializeRoleRequest(
            role=_Role(_Group("gpt-5", "openai:gpt-5")),
            credentials=_credentials(route_status="verified"),
            health_store=NoCircuits(),
        )
    )

    assert [entry.route_id for entry in materialized.fallback_chain] == ["openai:gpt-5"]
    assert materialized.error_code is None
