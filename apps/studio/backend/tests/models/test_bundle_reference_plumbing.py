"""#51 束=引用 materialize — Studio shell plumbs bundle_id + model_bundles
through to the gateway materializer; the by-reference + delta overlay is owned by
the gateway (materialize_role_entry), the shell only carries the fields through.

These tests pin the LEAK fixes:
  * _gateway_role keeps bundle_id (was dropped by the hardcoded include set).
  * to_registry_snapshot passes model_bundles (was none -> gateway raised
    "model bundle is not configured").
  * validate_references validates role.bundle_id against known bundles.
"""

from __future__ import annotations

import pytest
from app.models.llm_config import (
    LLMCredentialsFile,
    ModelBundle,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleRouteEntry,
    RolesData,
    _gateway_role,
)
from app.services.llm_roles import InvalidRoleReference, validate_references
from graph_agent_gateway.registry.resolver import materialize_role_entry
from graph_agent_gateway.registry.schema import RegistrySnapshot


def _credentials() -> LLMCredentialsFile:
    return LLMCredentialsFile(
        provider_endpoints={
            "openai-direct": ProviderEndpoint(
                endpoint_id="openai-direct",
                display_name="OpenAI",
                protocol="openai_compatible",
                base_url="https://api.openai.example/v1",
                api_key="secret",
            )
        },
        provider_routes={
            "openai-direct:gpt-5": ProviderRoute(
                route_id="openai-direct:gpt-5",
                endpoint_id="openai-direct",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
                canonical_id="gpt-5",
                display_name="GPT-5",
            )
        },
    )


def _bundle(*, with_chain: bool = True) -> ModelBundle:
    return ModelBundle(
        model_profile_id="primary",
        display_name="Primary",
        canonical_id="bundle:primary",
        fallback_chain=(
            [RoleRouteEntry(route_id="openai-direct:gpt-5")] if with_chain else []
        ),
    )


def test_gateway_role_keeps_bundle_id() -> None:
    """LEAK 1: _gateway_role must carry bundle_id so the gateway can resolve the
    reference; the hardcoded include set previously dropped it."""
    role = RoleEntry(bundle_id="primary")

    gateway_role = _gateway_role(role)

    assert gateway_role.bundle_id == "primary"


def test_registry_snapshot_carries_model_bundles_and_reference_materializes() -> None:
    """LEAK 2: to_registry_snapshot must pass model_bundles, and the gateway's
    materialize_role_entry overlay then produces a non-empty chain for a pure
    bundle-reference role (bundle_id set, no own fallback_chain delta)."""
    credentials = _credentials()
    roles = RolesData(
        model_bundles={"primary": _bundle()},
        roles={"graph_agent": RoleEntry(bundle_id="primary")},
    )

    snapshot = roles.to_registry_snapshot(credentials)

    assert "primary" in snapshot.model_bundles
    materialized = materialize_role_entry(snapshot, "graph_agent")
    assert [entry.route_id for entry in materialized.fallback_chain] == [
        "openai-direct:gpt-5"
    ]


def test_registry_snapshot_round_trips_through_gateway_validation() -> None:
    credentials = _credentials()
    roles = RolesData(
        model_bundles={"primary": _bundle()},
        roles={"graph_agent": RoleEntry(bundle_id="primary")},
    )

    snapshot = roles.to_registry_snapshot(credentials)

    RegistrySnapshot.model_validate(snapshot.model_dump(mode="json"))


def test_validate_references_rejects_dangling_bundle_id() -> None:
    """Cascade guard: a role whose bundle_id has no backing bundle is an
    InvalidRoleReference."""
    data = RolesData(roles={"graph_agent": RoleEntry(bundle_id="ghost")})

    with pytest.raises(InvalidRoleReference):
        validate_references(data, known_route_ids=set(), known_bundle_ids=set())


def test_validate_references_accepts_known_bundle_id() -> None:
    data = RolesData(
        model_bundles={"primary": _bundle()},
        roles={"graph_agent": RoleEntry(bundle_id="primary")},
    )

    validate_references(
        data,
        known_route_ids={"openai-direct:gpt-5"},
        known_bundle_ids={"primary"},
    )
