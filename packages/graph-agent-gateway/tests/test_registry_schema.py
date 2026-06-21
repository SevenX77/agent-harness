"""Registry schema tests for LLM Provider Intelligence V2."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError


def test_route_identity_and_resolved_route_has_no_inline_secret() -> None:
    from graph_agent_gateway.registry.schema import ProviderRoute, ResolvedRoute

    route = ProviderRoute(
        route_id="anthropic-official:claude-sonnet-4.6",
        endpoint_id="anthropic-official",
        route_slug="claude-sonnet-4.6",
        provider_model_id="claude-sonnet-4-6",
        canonical_id="claude-sonnet-4.6",
        status="verified",
    )

    assert route.route_id == "anthropic-official:claude-sonnet-4.6"

    resolved = ResolvedRoute(
        role_name="graph_agent",
        route_id=route.route_id,
        endpoint_id=route.endpoint_id,
        protocol="anthropic_compatible",
        base_url="https://api.anthropic.com",
        credential_ref="cred:anthropic-prod",
        credential_fingerprint="fp",
        provider_model_id=route.provider_model_id,
        canonical_id=route.canonical_id,
    )

    assert resolved.credential_ref == "cred:anthropic-prod"
    assert "api_key" not in resolved.model_dump(mode="json")
    assert "cred:anthropic-prod" in resolved.model_dump_json()

    with pytest.raises(ValidationError, match="api_key"):
        ResolvedRoute(
            role_name="graph_agent",
            route_id=route.route_id,
            endpoint_id=route.endpoint_id,
            protocol="anthropic_compatible",
            base_url="https://api.anthropic.com",
            credential_ref="cred:anthropic-prod",
            api_key=SecretStr("secret-value"),
            credential_fingerprint="fp",
            provider_model_id=route.provider_model_id,
            canonical_id=route.canonical_id,
        )


def test_runtime_schema_rejects_display_name_fields() -> None:
    from graph_agent_gateway.registry.schema import (
        ModelProfile,
        ProviderEndpoint,
        ProviderRoute,
        RegistrySnapshot,
        ResolvedRoute,
    )

    with pytest.raises(ValidationError, match="display_name"):
        ProviderEndpoint.model_validate(
            {
                "endpoint_id": "anthropic-official",
                "display_name": "Anthropic",
                "protocol": "anthropic_compatible",
                "base_url": "https://api.anthropic.com",
            }
        )

    with pytest.raises(ValidationError, match="display_name"):
        ProviderRoute.model_validate(
            {
                "route_id": "anthropic-official:claude-sonnet-4.6",
                "endpoint_id": "anthropic-official",
                "route_slug": "claude-sonnet-4.6",
                "provider_model_id": "claude-sonnet-4-6",
                "canonical_id": "claude-sonnet-4.6",
                "display_name": "Claude Sonnet 4.6",
            }
        )

    with pytest.raises(ValidationError, match="display_name"):
        RegistrySnapshot.model_validate(
            {
                "provider_endpoints": {
                    "anthropic-official": {
                        "endpoint_id": "anthropic-official",
                        "display_name": "Anthropic",
                        "protocol": "anthropic_compatible",
                        "base_url": "https://api.anthropic.com",
                    }
                }
            }
        )

    with pytest.raises(ValidationError, match="display_name"):
        ModelProfile.model_validate(
            {
                "model_profile_id": "analysis-default",
                "display_name": "Analysis Default",
                "fallback_chain": [],
            }
        )

    with pytest.raises(ValidationError, match="display_name"):
        ResolvedRoute.model_validate(
            {
                "role_name": "graph_agent",
                "route_id": "anthropic-official:claude-sonnet-4.6",
                "endpoint_id": "anthropic-official",
                "protocol": "anthropic_compatible",
                "base_url": "https://api.anthropic.com",
                "credential_ref": "cred:anthropic-prod",
                "credential_fingerprint": "fp",
                "provider_model_id": "claude-sonnet-4-6",
                "canonical_id": "claude-sonnet-4.6",
                "display_name": "Claude Sonnet 4.6",
            }
        )


def test_gateway_role_schema_rejects_deprecated_authoring_intent_fields() -> None:
    from graph_agent_gateway.registry.schema import ModelBundle, RoleEntry, RuntimeSettings

    with pytest.raises(ValidationError, match="cost_priority"):
        RoleEntry.model_validate(
            {
                "bundle_id": "analysis",
                "cost_priority": "cheap_first",
                "fallback_chain": [],
            }
        )

    with pytest.raises(ValidationError, match="ModelGroupIntent"):
        RoleEntry.model_validate(
            {
                "bundle_id": "analysis",
                "ModelGroupIntent": {"thinking": "inherit"},
                "fallback_chain": [],
            }
        )

    with pytest.raises(ValidationError, match="inherit"):
        RuntimeSettings.model_validate(
            {
                "reasoning": {"enabled": True},
                "inherit": {"target_output_tokens": True},
            }
        )

    with pytest.raises(ValidationError, match="target_output_tokens"):
        RuntimeSettings.model_validate(
            {
                "target_output_tokens": {"mode": "inherit"},
            }
        )

    with pytest.raises(ValidationError, match="intent"):
        ModelBundle.model_validate(
            {
                "bundle_id": "analysis",
                "intent": {"cost_priority": "cheap_first"},
                "fallback_chain": [],
            }
        )


def test_invalid_route_id_or_mismatched_parts_fail_validation() -> None:
    from graph_agent_gateway.registry.schema import ProviderRoute

    with pytest.raises(ValidationError):
        ProviderRoute(
            route_id="BAD:bad",
            endpoint_id="bad",
            route_slug="bad",
            provider_model_id="bad",
            canonical_id="bad",
        )

    with pytest.raises(ValidationError):
        ProviderRoute(
            route_id="one:route",
            endpoint_id="two",
            route_slug="route",
            provider_model_id="model",
            canonical_id="model",
        )


def test_runtime_policy_defaults_and_ranges() -> None:
    from graph_agent_gateway.registry.schema import RuntimePolicy

    policy = RuntimePolicy()

    assert policy.provider_down_ttl_seconds == 60
    assert policy.probe_timeout_seconds == 5
    assert policy.token_escalation_rounds == 2
    assert policy.terminal_retry_enabled is False
    assert policy.terminal_retry_policy.standard_runtime.max_attempts == 2
    assert policy.terminal_retry_policy.standard_runtime.backoff_ms == [250]
    assert 529 in policy.terminal_retry_policy.standard_runtime.retryable_status_codes
    assert policy.terminal_retry_policy.standard_probe.max_attempts == 1
    assert policy.terminal_retry_policy.sdk_runtime.claude_code_max_retries == 2
    assert policy.secret_lifetime_policy.invalidate_on_rotation is True

    with pytest.raises(ValidationError):
        RuntimePolicy(provider_down_ttl_seconds=-1)
    with pytest.raises(ValidationError):
        RuntimePolicy(probe_timeout_seconds=0)
    with pytest.raises(ValidationError):
        RuntimePolicy(token_escalation_rounds=11)


def test_control_plane_runtime_contract_models_validate_without_secrets() -> None:
    from graph_agent_gateway.registry.contracts import (
        CredentialDescriptor,
        SecretLifetimePolicy,
        SnapshotVersion,
        StandardTerminalRetrySettings,
        TerminalRetryPolicy,
    )

    descriptor = CredentialDescriptor(
        ref="cred:anthropic-prod",
        exists=True,
        status="available",
        fingerprint="fp",
        scope="workspace",
    )
    version = SnapshotVersion(
        registry_version="registry-1",
        catalog_version="catalog-1",
        client_id="graph_agent",
        client_version="1",
        terminal_version="standard-1",
        probe_contract_version="probe-1",
        client_route_profile_version="profile-1",
        generated_at="2026-05-30T00:00:00Z",
    )
    policy = TerminalRetryPolicy()
    lifetime = SecretLifetimePolicy(standard_client_cache_ttl_seconds=300)

    assert descriptor.model_dump()["ref"] == "cred:anthropic-prod"
    assert version.client_id == "graph_agent"
    assert policy.standard_runtime.retryable_status_codes == [429, 500, 502, 503, 504, 529]
    assert lifetime.standard_client_cache_ttl_seconds == 300

    with pytest.raises(ValidationError):
        CredentialDescriptor(ref="cred:missing", exists=False, status="available")
    with pytest.raises(ValidationError):
        StandardTerminalRetrySettings(max_attempts=3, backoff_ms=[100])


def test_registry_snapshot_and_route_accept_snapshot_version_with_legacy_default() -> None:
    from graph_agent_gateway.registry.contracts import SnapshotVersion
    from graph_agent_gateway.registry.schema import ProviderRoute, RegistrySnapshot

    legacy_snapshot = RegistrySnapshot.model_validate({})

    assert legacy_snapshot.snapshot_version is None

    snapshot_version = SnapshotVersion(
        registry_version="registry-2",
        client_id="graph_agent",
        client_route_profile_version="profile-2",
    )
    snapshot = RegistrySnapshot(snapshot_version=snapshot_version)
    route = ProviderRoute(
        route_id="provider:model",
        endpoint_id="provider",
        route_slug="model",
        provider_model_id="model",
        canonical_id="model",
        status="verified",
        snapshot_version=snapshot_version,
    )

    assert snapshot.snapshot_version == snapshot_version
    assert route.snapshot_version == snapshot_version


def test_ark_runtime_protocol_is_first_class() -> None:
    from graph_agent_gateway.registry.schema import ProviderEndpoint, ResolvedRoute

    endpoint = ProviderEndpoint(
        endpoint_id="ark-cn",
        protocol="ark_runtime",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        credential_ref="cred:ark-cn",
    )
    route = ResolvedRoute(
        role_name="graph_agent",
        route_id="ark-cn:deepseek-v3",
        endpoint_id="ark-cn",
        protocol=endpoint.protocol,
        base_url=endpoint.base_url,
        credential_ref="cred:ark-cn",
        credential_fingerprint="fp",
        provider_model_id="deepseek-v3",
        canonical_id="deepseek-v3",
    )

    assert endpoint.protocol == "ark_runtime"
    assert route.protocol == "ark_runtime"


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
