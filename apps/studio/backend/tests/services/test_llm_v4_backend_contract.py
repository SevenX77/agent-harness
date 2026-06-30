from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from app.models.llm_config import (
    CapabilityValue,
    LLMCredentialsFile,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleRouteEntry,
    RolesData,
)
from app.services.llm_credentials import (
    load_credentials,
    migrate_v3_credentials_to_v4,
    save_credentials,
    serialize_for_response,
    upsert_endpoints,
)
from app.services.llm_roles import InvalidRoleReference, load_roles_file, save_roles_file
from graph_agent_gateway.registry.route_identity import stable_endpoint_id
from graph_agent_gateway.registry.storage import compute_credential_fingerprint
from pydantic import SecretStr, ValidationError


def _endpoint(
    endpoint_id: str = "openai-direct",
    *,
    api_key: str | None = "secret",
) -> ProviderEndpoint:
    return ProviderEndpoint(
        endpoint_id=endpoint_id,
        display_name="OpenAI Direct",
        protocol="openai_compatible",
        base_url="https://api.openai.example/v1",
        api_key=SecretStr(api_key) if api_key is not None else None,
    )


def _route(route_id: str = "openai-direct:gpt-5") -> ProviderRoute:
    return ProviderRoute(
        route_id=route_id,
        endpoint_id=route_id.split(":", 1)[0],
        route_slug=route_id.split(":", 1)[1],
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
        display_name="GPT-5",
        status="verified",
        capabilities={
            "tool_protocol": CapabilityValue(value="openai_tools", source="manual"),
        },
    )


def _url_endpoint_id(
    base_url: str = "https://api.openai.example/v1",
    protocol: str = "openai_compatible",
) -> str:
    return stable_endpoint_id(protocol=protocol, base_url=base_url)


def test_credentials_v4_schema_redacts_secret_and_rejects_legacy_v3() -> None:
    data = LLMCredentialsFile(
        provider_endpoints={"openai-direct": _endpoint()},
        provider_routes={"openai-direct:gpt-5": _route()},
    )

    dumped = data.model_dump(mode="json")

    assert dumped["schema_version"] == 5  # v5: credentials now carries route.evidence (SSOT)
    assert dumped["provider_endpoints"]["openai-direct"]["api_key"] == "**********"
    with pytest.raises(ValidationError):
        LLMCredentialsFile.model_validate(
            {
                "schema_version": 3,
                "providers": [{"id": "old", "name": "Old", "api_key": "secret"}],
            }
        )


def test_load_missing_credentials_returns_empty_v4_and_legacy_file_is_fatal(tmp_path: Path) -> None:
    path = tmp_path / "llm_credentials.json"

    assert load_credentials(path) == LLMCredentialsFile()

    path.write_text(
        json.dumps({"schema_version": 3, "providers": [{"id": "old", "name": "Old"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema_version 4|legacy"):
        load_credentials(path)


def test_migrate_v3_credentials_to_v4_preserves_secret_and_models(tmp_path: Path) -> None:
    path = tmp_path / "llm_credentials.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "providers": [
                    {
                        "id": "anthropic-official",
                        "name": "Anthropic Official",
                        "provider_type": "anthropic_compatible",
                        "base_url": "https://api.anthropic.com",
                        "api_key": "anthropic-secret",
                        "last_test_status": "ok",
                        "available_models": [
                            {
                                "id": "claude-sonnet-4-6",
                                "capabilities": {
                                    "display_name": "Claude Sonnet 4.6",
                                    "max_input_tokens": 1_000_000,
                                    "max_output_tokens": 128_000,
                                    "thinking": {"supported": True},
                                },
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    migrated = migrate_v3_credentials_to_v4(path)

    assert migrated.schema_version == 5  # v3 migration lands on the current schema (v5)
    endpoint = migrated.provider_endpoints["anthropic-official"]
    assert endpoint.api_key is not None
    assert endpoint.api_key.get_secret_value() == "anthropic-secret"
    assert "anthropic-official:claude-sonnet-4.6" in migrated.provider_routes
    route = migrated.provider_routes["anthropic-official:claude-sonnet-4.6"]
    assert route.display_name == "Claude Sonnet 4.6"
    assert route.provider_model_id == "claude-sonnet-4-6"
    assert route.canonical_id == "claude-sonnet-4.6"
    assert route.capabilities["thinking_protocol"].value is True
    assert route.capabilities["thinking_protocol"].source == "probed_verified"
    assert route.capabilities["min_thinking_budget_tokens"].value == 1024
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 5
    assert (tmp_path / "llm_credentials.json.v3.bak").exists()


def test_migrate_v3_credentials_normalizes_known_endpoint_ids(tmp_path: Path) -> None:
    path = tmp_path / "llm_credentials.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "providers": [
                    {
                        "id": "98593eb6-764b-497e-808d-6610935f0e0a",
                        "name": "OpenRouter",
                        "provider_type": "openai_compatible",
                        "base_url": "https://openrouter.ai/api",
                        "api_key": "openrouter-secret",
                        "last_test_status": "ok",
                        "available_models": [
                            {
                                "id": "anthropic/claude-sonnet-4-6",
                                "capabilities": {"display_name": "Claude Sonnet 4.6"},
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    migrated = migrate_v3_credentials_to_v4(path)

    openrouter_endpoint_id = _url_endpoint_id("https://openrouter.ai/api")
    assert openrouter_endpoint_id in migrated.provider_endpoints
    assert "98593eb6-764b-497e-808d-6610935f0e0a" not in migrated.provider_endpoints
    assert f"{openrouter_endpoint_id}:anthropic.claude-sonnet-4-6" in migrated.provider_routes


def test_upsert_endpoint_omitted_api_key_preserves_secret_and_empty_clears_secret(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm_credentials.json"
    save_credentials(
        LLMCredentialsFile(provider_endpoints={"openai-direct": _endpoint()}),
        path,
    )

    upsert_endpoints(
        {
            "openai-direct": {
                "endpoint_id": "openai-direct",
                "display_name": "OpenAI Renamed",
                "protocol": "openai_compatible",
                "base_url": "https://api.openai.example/v1",
            }
        },
        path=path,
    )
    assert (
        load_credentials(path)
        .provider_endpoints[_url_endpoint_id()]
        .api_key.get_secret_value()
        == "secret"
    )

    upsert_endpoints(
        {
            "openai-direct": {
                "endpoint_id": "openai-direct",
                "display_name": "OpenAI Renamed Again",
                "protocol": "openai_compatible",
                "base_url": "https://api.openai.example/v1",
                "api_key": "",
            }
        },
        path=path,
    )

    endpoint = load_credentials(path).provider_endpoints[_url_endpoint_id()]
    assert endpoint.display_name == "OpenAI Renamed Again"
    assert endpoint.api_key is None


def test_upsert_endpoint_omitted_credential_ref_preserves_existing_ref(tmp_path: Path) -> None:
    path = tmp_path / "llm_credentials.json"
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "openai-direct": _endpoint().model_copy(
                    update={"credential_ref": "credential:openai-prod"}
                )
            }
        ),
        path,
    )

    upsert_endpoints(
        {
            "openai-direct": {
                "endpoint_id": "openai-direct",
                "display_name": "OpenAI Renamed",
                "protocol": "openai_compatible",
                "base_url": "https://api.openai.example/v1",
            }
        },
        path=path,
    )

    endpoint = load_credentials(path).provider_endpoints[_url_endpoint_id()]
    assert endpoint.display_name == "OpenAI Renamed"
    assert endpoint.credential_ref == "credential:openai-prod"


def test_upsert_endpoint_redacted_api_key_placeholder_preserves_secret(tmp_path: Path) -> None:
    path = tmp_path / "llm_credentials.json"
    save_credentials(
        LLMCredentialsFile(provider_endpoints={"openai-direct": _endpoint()}),
        path,
    )

    upsert_endpoints(
        {
            "openai-direct": {
                "endpoint_id": "openai-direct",
                "display_name": "OpenAI From Redacted Response",
                "protocol": "openai_compatible",
                "base_url": "https://api.openai.example/v1",
                "api_key": "**********",
            }
        },
        path=path,
    )

    endpoint = load_credentials(path).provider_endpoints[_url_endpoint_id()]
    assert endpoint.display_name == "OpenAI From Redacted Response"
    assert endpoint.api_key.get_secret_value() == "secret"


def test_upsert_endpoint_ordinary_save_does_not_accept_test_status_facts(tmp_path: Path) -> None:
    path = tmp_path / "llm_credentials.json"
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "openai-direct": _endpoint().model_copy(
                    update={
                        "status": "verified",
                        "last_test_at": "2026-06-18T00:00:00Z",
                        "last_test_message": "Backend probe succeeded.",
                    }
                )
            }
        ),
        path,
    )

    upsert_endpoints(
        {
            "openai-direct": {
                "endpoint_id": "openai-direct",
                "display_name": "OpenAI User Edit",
                "protocol": "openai_compatible",
                "base_url": "https://api.openai.example/v1",
                "api_key": "**********",
                "status": "failed",
                "last_test_at": "2026-06-18T01:00:00Z",
                "last_test_message": "Frontend cache should not become fact.",
            }
        },
        path=path,
    )

    endpoint = load_credentials(path).provider_endpoints[_url_endpoint_id()]
    assert endpoint.display_name == "OpenAI User Edit"
    assert endpoint.status == "verified"
    assert endpoint.last_test_at == "2026-06-18T00:00:00Z"
    assert endpoint.last_test_message == "Backend probe succeeded."


def test_upsert_third_party_endpoint_uses_url_stable_id(tmp_path: Path) -> None:
    path = tmp_path / "llm_credentials.json"
    expected_id = stable_endpoint_id(
        protocol="openai_compatible",
        base_url="https://llm.wavespeed.ai/v1",
    )

    upsert_endpoints(
        {
            "custom-00000000-0000-4000-8000-000000000001": {
                "endpoint_id": "custom-00000000-0000-4000-8000-000000000001",
                "display_name": "WaveSpeed Custom",
                "protocol": "openai_compatible",
                "base_url": "https://llm.wavespeed.ai/v1/",
                "api_key": "wavespeed-secret",
                "provider_kind": "custom",
            }
        },
        path=path,
    )

    endpoints = load_credentials(path).provider_endpoints
    assert "custom-00000000-0000-4000-8000-000000000001" not in endpoints
    assert endpoints[expected_id].endpoint_id == expected_id
    assert endpoints[expected_id].base_url == "https://llm.wavespeed.ai/v1"
    assert endpoints[expected_id].provider_kind == "custom"


def test_load_credentials_repairs_legacy_catalog_candidate_failed_status(tmp_path: Path) -> None:
    path = tmp_path / "llm_credentials.json"
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "openai-official": ProviderEndpoint(
                    endpoint_id="openai-official",
                    display_name="OpenAI Official",
                    protocol="openai_compatible",
                    base_url="https://api.openai.com/v1",
                    api_key="secret",
                    provider_kind="official",
                    metadata={
                        "capability_library": [
                            {
                                "model_id": "gpt-image-1",
                                "status": "catalog_candidate",
                                "route_status": "failed",
                                "last_probe_message": "No verified language route profile.",
                            }
                        ]
                    },
                )
            }
        ),
        path,
    )

    endpoint = load_credentials(path).provider_endpoints["openai-official"]

    assert endpoint.metadata["capability_library"] == [
        {
            "model_id": "gpt-image-1",
            "status": "catalog_candidate",
            "route_status": "unverified_manual",
            "last_probe_message": "No verified language route profile.",
        }
    ]


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits do not model Windows ACLs")
def test_save_credentials_chmods_file_0600_and_parent_0700(tmp_path: Path) -> None:
    path = tmp_path / ".studio" / "llm_credentials.json"

    save_credentials(LLMCredentialsFile(provider_endpoints={"openai-direct": _endpoint()}), path)

    assert os.stat(path).st_mode & 0o777 == 0o600
    assert os.stat(path.parent).st_mode & 0o777 == 0o700


def test_save_credentials_atomic_write_preserves_file_on_replace_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "llm_credentials.json"
    save_credentials(LLMCredentialsFile(provider_endpoints={"openai-direct": _endpoint()}), path)
    before = path.read_text(encoding="utf-8")

    def fail_replace(_src: Path, _dst: Path) -> None:
        raise OSError("rename failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError):
        save_credentials(
            LLMCredentialsFile(
                provider_endpoints={
                    "anthropic-official": _endpoint("anthropic-official"),
                }
            ),
            path,
        )

    assert path.read_text(encoding="utf-8") == before


def test_backend_fingerprint_matches_gateway_helper() -> None:
    endpoint = _endpoint()
    data = LLMCredentialsFile(provider_endpoints={"openai-direct": endpoint})

    assert data.endpoint_fingerprint("openai-direct") == compute_credential_fingerprint(endpoint)


def test_provider_endpoint_persists_provider_kind_and_rate_limit_bucket() -> None:
    default_endpoint = _endpoint()

    assert default_endpoint.provider_kind == "third_party"
    assert default_endpoint.rate_limit_bucket is None

    custom_endpoint = ProviderEndpoint(
        endpoint_id="onechats-proxy",
        display_name="OneChats Proxy",
        protocol="openai_compatible",
        base_url="https://onechats.example/v1",
        api_key=SecretStr("secret"),
        provider_kind="custom",
        rate_limit_bucket="onechats-shared-key",
    )

    dumped = custom_endpoint.model_dump(mode="json")

    assert custom_endpoint.provider_kind == "custom"
    assert custom_endpoint.rate_limit_bucket == "onechats-shared-key"
    assert dumped["provider_kind"] == "custom"
    assert dumped["rate_limit_bucket"] == "onechats-shared-key"


def test_upsert_endpoint_preserves_user_provider_kind_and_rate_limit_bucket(tmp_path: Path) -> None:
    path = tmp_path / "llm_credentials.json"
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "onechats-proxy": ProviderEndpoint(
                    endpoint_id="onechats-proxy",
                    display_name="OneChats Proxy",
                    protocol="openai_compatible",
                    base_url="https://onechats.example/v1",
                    api_key=SecretStr("secret"),
                    provider_kind="custom",
                    rate_limit_bucket="onechats-shared-key",
                )
            }
        ),
        path,
    )

    upsert_endpoints(
        {
            "onechats-proxy": {
                "endpoint_id": "onechats-proxy",
                "display_name": "OneChats Proxy Renamed",
                "protocol": "openai_compatible",
                "base_url": "https://onechats.example/v1",
                "provider_kind": "official",
                "rate_limit_bucket": "onechats-official-mirror",
            }
        },
        path=path,
    )

    endpoint = load_credentials(path).provider_endpoints[_url_endpoint_id("https://onechats.example/v1")]
    assert endpoint.display_name == "OneChats Proxy Renamed"
    assert endpoint.provider_kind == "official"
    assert endpoint.rate_limit_bucket == "onechats-official-mirror"
    assert endpoint.api_key is not None
    assert endpoint.api_key.get_secret_value() == "secret"


def test_upsert_new_endpoint_seeds_curated_provider_kind(tmp_path: Path) -> None:
    path = tmp_path / "llm_credentials.json"

    upsert_endpoints(
        {
            "anthropic-official": {
                "endpoint_id": "anthropic-official",
                "display_name": "Anthropic",
                "protocol": "anthropic_compatible",
                "base_url": "https://api.anthropic.com",
                "api_key": "anthropic-secret",
            },
            "my-custom-proxy": {
                "endpoint_id": "my-custom-proxy",
                "display_name": "My Custom Proxy",
                "protocol": "openai_compatible",
                "base_url": "https://proxy.example/v1",
                "api_key": "proxy-secret",
            },
        },
        path=path,
    )

    endpoints = load_credentials(path).provider_endpoints
    proxy_endpoint_id = _url_endpoint_id("https://proxy.example/v1")
    assert endpoints["anthropic-official"].provider_kind == "official"
    assert endpoints[proxy_endpoint_id].provider_kind == "third_party"


def test_upsert_endpoint_omitted_provider_kind_and_bucket_preserve_existing_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm_credentials.json"
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "onechats-proxy": ProviderEndpoint(
                    endpoint_id="onechats-proxy",
                    display_name="OneChats Proxy",
                    protocol="openai_compatible",
                    base_url="https://onechats.example/v1",
                    api_key=SecretStr("secret"),
                    provider_kind="custom",
                    rate_limit_bucket="onechats-shared-key",
                )
            }
        ),
        path,
    )

    upsert_endpoints(
        {
            "onechats-proxy": {
                "endpoint_id": "onechats-proxy",
                "display_name": "OneChats Proxy Renamed",
                "protocol": "openai_compatible",
                "base_url": "https://onechats.example/v1",
            }
        },
        path=path,
    )

    endpoint = load_credentials(path).provider_endpoints[_url_endpoint_id("https://onechats.example/v1")]
    assert endpoint.display_name == "OneChats Proxy Renamed"
    assert endpoint.provider_kind == "custom"
    assert endpoint.rate_limit_bucket == "onechats-shared-key"


def test_upsert_curated_official_endpoint_repairs_legacy_provider_kind(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm_credentials.json"
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "anthropic-official": ProviderEndpoint(
                    endpoint_id="anthropic-official",
                    display_name="Anthropic Official",
                    protocol="anthropic_compatible",
                    base_url="https://api.anthropic.com",
                    api_key=SecretStr("secret"),
                    provider_kind="third_party",
                )
            }
        ),
        path,
    )

    upsert_endpoints(
        {
            "anthropic-official": {
                "endpoint_id": "anthropic-official",
                "display_name": "Anthropic Official",
                "protocol": "anthropic_compatible",
                "base_url": "https://api.anthropic.com",
            }
        },
        path=path,
    )

    endpoint = load_credentials(path).provider_endpoints["anthropic-official"]
    assert endpoint.provider_kind == "official"
    assert endpoint.api_key is not None
    assert endpoint.api_key.get_secret_value() == "secret"


def test_serialize_for_response_does_not_leak_endpoint_secret() -> None:
    body = serialize_for_response(
        LLMCredentialsFile(provider_endpoints={"openai-direct": _endpoint()}),
    )

    assert body["provider_endpoints"]["openai-direct"]["api_key"] == "**********"


def test_roles_v2_schema_rejects_legacy_short_code_shape() -> None:
    with pytest.raises(ValidationError):
        RolesData.model_validate(
            {
                "models": {"GPT5": {"name": "GPT-5", "providers": {"openai": "gpt-5"}}},
                "providers": {"openai": {"name": "OpenAI", "type": "openai_compatible"}},
                "roles": {"graph_agent": {"active_model": "GPT5", "models": {}}},
            }
        )

    with pytest.raises(ValidationError):
        RoleEntry.model_validate({"system_prompt_prefix": None, "fallback_chain": []})


def test_roles_v3_authoring_schema_migrates_legacy_provider_preferences_to_manual_order() -> None:
    data = RolesData.model_validate(
        {
            "schema_version": 3,
            "model_bundles": {},
            "roles": {
                "analyst": {
                    "role_kind": "graph_agent",
                    "system_prompt_prefix": "",
                    "model_fallback_enabled": True,
                    "intent": {
                        "provider_preference": "official_first",
                        "thinking": "preferred",
                        "target_output_tokens": {
                            "mode": "target",
                            "value": 128000,
                            "downgrade": "allow_with_warning",
                        },
                    },
                    "model_groups": [
                        {
                            "canonical_id": "claude-sonnet-4-7",
                            "display_name": "Claude Sonnet 4.7",
                            "intent": {
                                "thinking": "inherit",
                                "target_output_tokens": {"mode": "inherit"},
                            },
                            "provider_models": [
                                {
                                    "route_id": "anthropic-official:claude-sonnet-4-7",
                                },
                                {
                                    "route_id": "openrouter-prod:anthropic.claude-sonnet-4-7",
                                },
                            ],
                        }
                    ],
                },
                "copilot_chat": {
                    "role_kind": "copilot",
                    "system_prompt_prefix": "",
                    "model_fallback_enabled": True,
                    "intent": {"provider_preference": "ready_first"},
                    "model_groups": [],
                },
            },
        }
    )

    assert data.schema_version == 3
    assert data.roles["analyst"].role_kind == "graph_agent"
    assert data.roles["analyst"].model_fallback_enabled is True
    assert data.roles["analyst"].intent.provider_preference == "manual_order"
    assert data.roles["analyst"].model_groups[0].canonical_id == "claude-sonnet-4-7"
    assert data.roles["analyst"].model_groups[0].provider_models[0].route_id == (
        "anthropic-official:claude-sonnet-4-7"
    )
    assert data.roles["copilot_chat"].role_kind == "copilot"
    assert data.roles["copilot_chat"].intent.provider_preference == "manual_order"


def test_role_level_intent_rejects_inherit_token_mode() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RolesData.model_validate(
            {
                "schema_version": 3,
                "model_bundles": {},
                "roles": {
                    "analyst": {
                        "role_kind": "graph_agent",
                        "system_prompt_prefix": "",
                        "model_fallback_enabled": True,
                        "intent": {
                            "target_output_tokens": {"mode": "inherit"},
                        },
                        "model_groups": [],
                    }
                },
            }
        )

    error_locations = {tuple(error["loc"]) for error in exc_info.value.errors()}
    assert (
        "roles",
        "analyst",
        "intent",
        "target_output_tokens",
        "mode",
    ) in error_locations


def test_roles_v2_round_trip_and_reference_validation(tmp_path: Path) -> None:
    path = tmp_path / "llm_roles.yaml"
    path.write_text(
        """
schema_version: 2
model_profiles: {}
roles:
  graph_agent:
    system_prompt_prefix: ""
    fallback_chain:
      - route_id: openai-direct:gpt-5
        runtime_settings:
          temperature: 0.2
          max_output_tokens: 1024
    lint_requirements:
      thinking: "warn"
""".lstrip(),
        encoding="utf-8",
    )

    data = load_roles_file(path)

    assert data.schema_version == 2
    assert data.roles["graph_agent"].fallback_chain[0].route_id == "openai-direct:gpt-5"
    assert data.roles["graph_agent"].fallback_chain[0].runtime_settings.temperature == 0.2
    save_roles_file(path, data, known_route_ids={"openai-direct:gpt-5"})
    assert 'thinking: "warn"' in path.read_text(encoding="utf-8")

    data.roles["broken"] = RoleEntry(
        fallback_chain=[RoleRouteEntry(route_id="openai-direct:missing")]
    )
    with pytest.raises(InvalidRoleReference, match="openai-direct:missing"):
        save_roles_file(path, data, known_route_ids={"openai-direct:gpt-5"})


def test_checked_in_roles_file_uses_v2_route_chain_schema() -> None:
    path = Path(__file__).resolve().parents[5] / "config" / "llm_roles.yaml"

    data = load_roles_file(path)

    assert data.schema_version == 2
    assert "balanced" in data.roles
    assert data.roles["balanced"].fallback_chain[0].route_id
    assert data.model_profiles["CL46T"].fallback_chain[0].runtime_settings.reasoning.enabled is True
    assert (
        data.model_profiles["CL46T"]
        .fallback_chain[0]
        .runtime_settings.reasoning.budget_tokens
        == 4096
    )
    assert data.model_profiles["CLO47T"].fallback_chain[0].runtime_settings.reasoning.enabled is True
    assert (
        data.model_profiles["CLO47T"]
        .fallback_chain[0]
        .runtime_settings.reasoning.budget_tokens
        is None
    )
    assert data.roles["balanced"].fallback_chain[0].runtime_settings.reasoning.enabled is True
