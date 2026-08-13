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

from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr, ValidationError

if TYPE_CHECKING:
    from graph_agent_gateway.registry import RegistrySnapshot, RoleEntry


def _empty_registry() -> RegistrySnapshot:
    """A registry that does not know the role's referenced route."""
    from graph_agent_gateway.registry import RegistrySnapshot

    return RegistrySnapshot()


def _role(canonical_id: str = "gpt-5", route_id: str = "openai:gpt-5") -> RoleEntry:
    from graph_agent_gateway.registry import RoleEntry, RoleModelGroup, RoleProviderModel

    return RoleEntry(
        model_groups=[
            RoleModelGroup(
                canonical_id=canonical_id,
                display_name=canonical_id,
                provider_models=[RoleProviderModel(route_id=route_id)],
            )
        ],
    )


def _credentials(*, route_status: str) -> RegistrySnapshot:
    from graph_agent_gateway.registry import ProviderEndpoint, ProviderRoute, RegistrySnapshot

    return RegistrySnapshot(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key=SecretStr("secret"),
                status="verified",
            )
        },
        provider_routes={
            "openai:gpt-5": ProviderRoute(
                route_id="openai:gpt-5",
                endpoint_id="openai",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                status=route_status,
            )
        },
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
            role=_role(),
            credentials=_empty_registry(),
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
            role=_role(),
            credentials=_credentials(route_status="failed"),
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
            role=_role(),
            credentials=_credentials(route_status="verified"),
        )
    )

    assert [entry.route_id for entry in materialized.fallback_chain] == ["openai:gpt-5"]
    assert materialized.error_code is None
