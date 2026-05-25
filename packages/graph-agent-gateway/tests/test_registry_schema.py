"""Registry schema tests for LLM Provider Intelligence V2."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError


def test_route_identity_and_secret_serialization() -> None:
    from graph_agent_gateway.registry.schema import ProviderRoute, ResolvedRoute

    route = ProviderRoute(
        route_id="anthropic-official:claude-sonnet-4.6",
        endpoint_id="anthropic-official",
        route_slug="claude-sonnet-4.6",
        provider_model_id="claude-sonnet-4-6",
        canonical_id="claude-sonnet-4.6",
        display_name="Claude Sonnet 4.6",
        status="verified",
    )

    assert route.route_id == "anthropic-official:claude-sonnet-4.6"

    resolved = ResolvedRoute(
        role_name="graph_agent",
        route_id=route.route_id,
        endpoint_id=route.endpoint_id,
        protocol="anthropic_compatible",
        base_url="https://api.anthropic.com",
        api_key=SecretStr("secret-value"),
        credential_fingerprint="fp",
        provider_model_id=route.provider_model_id,
        canonical_id=route.canonical_id,
        display_name=route.display_name,
    )

    assert resolved.api_key.get_secret_value() == "secret-value"
    assert "secret-value" not in resolved.model_dump_json()


def test_invalid_route_id_or_mismatched_parts_fail_validation() -> None:
    from graph_agent_gateway.registry.schema import ProviderRoute

    with pytest.raises(ValidationError):
        ProviderRoute(
            route_id="BAD:bad",
            endpoint_id="bad",
            route_slug="bad",
            provider_model_id="bad",
            canonical_id="bad",
            display_name="bad",
        )

    with pytest.raises(ValidationError):
        ProviderRoute(
            route_id="one:route",
            endpoint_id="two",
            route_slug="route",
            provider_model_id="model",
            canonical_id="model",
            display_name="Model",
        )


def test_runtime_policy_defaults_and_ranges() -> None:
    from graph_agent_gateway.registry.schema import RuntimePolicy

    policy = RuntimePolicy()

    assert policy.provider_down_ttl_seconds == 60
    assert policy.probe_timeout_seconds == 5
    assert policy.token_escalation_rounds == 2

    with pytest.raises(ValidationError):
        RuntimePolicy(provider_down_ttl_seconds=-1)
    with pytest.raises(ValidationError):
        RuntimePolicy(probe_timeout_seconds=0)
    with pytest.raises(ValidationError):
        RuntimePolicy(token_escalation_rounds=11)


def test_role_prefix_and_multi_endpoint_import_draft_validation() -> None:
    from graph_agent_gateway.registry.schema import (
        EndpointCandidate,
        ProviderImportDraft,
        RoleEntry,
        RouteCandidate,
    )

    with pytest.raises(ValidationError):
        RoleEntry(system_prompt_prefix=None, fallback_chain=[])  # type: ignore[arg-type]

    draft = ProviderImportDraft(
        draft_id="draft_test",
        source={"kind": "url", "url": "https://provider.example/docs"},
        status="needs_probe",
        endpoint_candidates={
            "provider-openai": EndpointCandidate(
                endpoint_id="provider-openai",
                display_name="Provider OpenAI",
                protocol="openai_compatible",
                base_url="https://provider.example/openai",
            ),
            "provider-anthropic": EndpointCandidate(
                endpoint_id="provider-anthropic",
                display_name="Provider Anthropic",
                protocol="anthropic_compatible",
                base_url="https://provider.example/anthropic",
            ),
        },
        route_candidates={
            "provider-openai:anthropic.claude": RouteCandidate(
                endpoint_id="provider-openai",
                route_slug="anthropic.claude",
                provider_model_id="anthropic/claude",
                canonical_id="claude",
                display_name="Claude",
            )
        },
        probe_results={
            "provider-openai": {"target_type": "endpoint", "status": "not_run"},
        },
    )

    assert len(draft.endpoint_candidates) == 2
    assert draft.route_candidates["provider-openai:anthropic.claude"].endpoint_id == (
        "provider-openai"
    )

    with pytest.raises(ValidationError):
        ProviderImportDraft(draft_id="d", source={}, status="unknown")
