from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.models.llm_config import (
    LLMCredentialsFile,
    RoleEntry,
    RolesData,
)
from app.services.llm_credentials import (
    load_credentials,
    save_credentials,
    serialize_for_response,
    upsert_endpoints,
)
from app.services.llm_roles import InvalidRoleReference, load_roles_file, save_roles_file
from graph_agent_gateway.registry.schema import (
    CapabilityValue,
    ProviderEndpoint,
    ProviderRoute,
    RoleRouteEntry,
)
from graph_agent_gateway.registry.storage import compute_credential_fingerprint


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


def test_credentials_v4_schema_redacts_secret_and_rejects_legacy_v3() -> None:
    data = LLMCredentialsFile(
        provider_endpoints={"openai-direct": _endpoint()},
        provider_routes={"openai-direct:gpt-5": _route()},
    )

    dumped = data.model_dump(mode="json")

    assert dumped["schema_version"] == 4
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


def test_upsert_endpoint_omitted_or_empty_api_key_preserves_secret(tmp_path: Path) -> None:
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
        .provider_endpoints["openai-direct"]
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

    endpoint = load_credentials(path).provider_endpoints["openai-direct"]
    assert endpoint.display_name == "OpenAI Renamed Again"
    assert endpoint.api_key.get_secret_value() == "secret"


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

    endpoint = load_credentials(path).provider_endpoints["openai-direct"]
    assert endpoint.display_name == "OpenAI From Redacted Response"
    assert endpoint.api_key.get_secret_value() == "secret"


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
