"""Role materialization looks routes up in a registry, and reads them as routes.

``MaterializeRoleRequest.credentials`` was ``Any``, so everything reached
through it was ``Any`` too: the route, its endpoint, the evidence on the route,
the capability values on it. All of them are types THIS package defines —
``ProviderRoute``, ``ProviderEndpoint``, ``EvidenceRecord``, ``CapabilityValue``
— and they were still being read through a helper that means "a dict or an
object, whichever this is, and ``None`` if neither". Under that helper
``mypy --strict`` reports success on a field name that exists nowhere, which is
how ``endpoint.secret_handle`` survived (#778).

What the gateway needs from a host's registry is two lookups by id, so that is
what the contract says. It is a Protocol rather than a base class because the
registry a host keeps is its own file: Studio's is an on-disk credentials file
with a schema version and a sync marker, this package's is ``RegistrySnapshot``,
and neither should have to become the other to have a route looked up in it.

The role is this package's own ``RoleEntry`` — the model sink-down is
decided in docs/design/2026-08-13-gateway-role-model-and-section-truth-decision.md
and asserted in test_role_model_belongs_to_the_gateway.py.
"""

from __future__ import annotations

import inspect

import pytest
from graph_agent_gateway.registry import (
    ProviderEndpoint,
    ProviderRoute,
    RegistrySnapshot,
    RoleEntry,
    RoleModelGroup,
    RoleProviderModel,
    RouteRegistry,
)
from graph_agent_gateway.role import MaterializeRoleRequest, materialization, materialize_role


def _gateway_role() -> RoleEntry:
    return RoleEntry(
        model_groups=[
            RoleModelGroup(
                canonical_id="gpt-5",
                display_name="GPT 5",
                provider_models=[RoleProviderModel(route_id="openai:gpt-5")],
            )
        ],
    )


def _snapshot() -> RegistrySnapshot:
    return RegistrySnapshot(
        provider_endpoints={
            "openai": ProviderEndpoint(
                endpoint_id="openai",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                credential_ref="cred://openai",
                status="verified",
            )
        },
        provider_routes={
            "openai:gpt-5": ProviderRoute(
                route_id="openai:gpt-5",
                endpoint_id="openai",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                status="verified",
            )
        },
    )


def test_this_package_can_satisfy_its_own_contract() -> None:
    """``RegistrySnapshot`` is this package's registry; it must be usable as one."""

    registry: RouteRegistry = _snapshot()

    assert set(registry.provider_routes) == {"openai:gpt-5"}
    assert set(registry.provider_endpoints) == {"openai"}


def test_the_request_names_what_it_needs_instead_of_accepting_anything() -> None:
    annotations = inspect.get_annotations(MaterializeRoleRequest, eval_str=False)

    assert annotations["credentials"] == "RouteRegistry"


@pytest.mark.parametrize("reader", ["route", "endpoint", "evidence", "capability"])
def test_what_this_package_defines_is_read_as_what_it_defined(reader: str) -> None:
    """No ``dict or object, whichever this is`` on a type we own."""

    assert f"_value({reader}" not in inspect.getsource(materialization)


def test_a_role_resolves_over_this_package_s_own_registry() -> None:
    materialized = materialize_role(
        MaterializeRoleRequest(role=_gateway_role(), credentials=_snapshot())
    )

    assert [entry.route_id for entry in materialized.fallback_chain] == ["openai:gpt-5"]
    assert materialized.error_code is None
