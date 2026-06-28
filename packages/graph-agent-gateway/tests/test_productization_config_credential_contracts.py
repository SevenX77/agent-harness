"""MVP1 productization contracts for Gateway config truth and credentials."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError


def test_config_truth_store_requires_user_scoped_etag_contract() -> None:
    from graph_agent_gateway.storage_contracts import ConfigTruthStore

    get_signature = inspect.signature(ConfigTruthStore.get_config)
    put_signature = inspect.signature(ConfigTruthStore.put_config)

    assert list(get_signature.parameters) == ["self", "user_id", "key"]
    assert get_signature.parameters["user_id"].default is inspect.Parameter.empty
    assert get_signature.parameters["key"].default is inspect.Parameter.empty

    assert list(put_signature.parameters) == [
        "self",
        "user_id",
        "key",
        "value",
        "if_match",
        "if_none_match",
    ]
    assert put_signature.parameters["user_id"].default is inspect.Parameter.empty
    assert put_signature.parameters["key"].default is inspect.Parameter.empty
    assert put_signature.parameters["value"].default is inspect.Parameter.empty
    assert put_signature.parameters["if_match"].kind is inspect.Parameter.KEYWORD_ONLY
    assert put_signature.parameters["if_match"].default is None
    assert put_signature.parameters["if_none_match"].kind is inspect.Parameter.KEYWORD_ONLY
    assert put_signature.parameters["if_none_match"].default is None


def test_config_truth_store_returns_etag_and_rejects_stale_writes() -> None:
    from graph_agent_gateway.storage_contracts import (
        ConfigConflictError,
        ConfigRecord,
        InMemoryConfigTruthStore,
    )

    store = InMemoryConfigTruthStore()

    first_etag = store.put_config(
        user_id="user-a",
        key="roles",
        value={"roles": {"graph_agent": {"fallback_chain": []}}},
        if_none_match="*",
    )
    record = store.get_config(user_id="user-a", key="roles")

    assert isinstance(record, ConfigRecord)
    assert record.etag == first_etag
    assert record.value == {"roles": {"graph_agent": {"fallback_chain": []}}}

    with pytest.raises(ConfigConflictError) as create_conflict:
        store.put_config(
            user_id="user-a",
            key="roles",
            value={"roles": {}},
            if_none_match="*",
        )

    assert create_conflict.value.error_code == "config.etag_conflict"
    assert create_conflict.value.error_payload["user_id"] == "user-a"
    assert create_conflict.value.error_payload["key"] == "roles"

    with pytest.raises(ConfigConflictError) as stale_conflict:
        store.put_config(
            user_id="user-a",
            key="roles",
            value={"roles": {"graph_agent": {"fallback_chain": ["new"]}}},
            if_match="stale-etag",
        )

    assert stale_conflict.value.error_code == "config.etag_conflict"
    assert stale_conflict.value.error_payload["expected_etag"] == first_etag
    assert stale_conflict.value.error_payload["actual_if_match"] == "stale-etag"

    second_etag = store.put_config(
        user_id="user-a",
        key="roles",
        value={"roles": {"graph_agent": {"fallback_chain": ["new"]}}},
        if_match=first_etag,
    )

    assert second_etag != first_etag
    assert store.get_config(user_id="user-a", key="roles").etag == second_etag


@pytest.mark.parametrize("source", ["local_input", "remote_vault"])
def test_credential_resolve_request_supports_declared_sources(source: str) -> None:
    from graph_agent_gateway.credential_resolver import CredentialResolveRequest

    request = CredentialResolveRequest(
        user_id="user-a",
        role="graph_agent",
        credential_ref="credential:openai-prod",
        source=source,
    )

    assert request.user_id == "user-a"
    assert request.role == "graph_agent"
    assert request.credential_ref == "credential:openai-prod"
    assert request.source == source


def test_credential_resolve_request_rejects_undeclared_source() -> None:
    from graph_agent_gateway.credential_resolver import CredentialResolveRequest

    with pytest.raises(ValidationError):
        CredentialResolveRequest(
            user_id="user-a",
            role="graph_agent",
            credential_ref="credential:openai-prod",
            source="env_var",
        )


def test_credential_resolve_response_returns_handle_and_never_raw_secret() -> None:
    from graph_agent_gateway.credential_resolver import CredentialResolveResponse

    expires_at = datetime.now(UTC) + timedelta(minutes=15)
    response = CredentialResolveResponse(
        secret_handle="secret-handle://user-a/openai-prod/session-1",
        expires_at=expires_at,
        redacted_label="sk-...prod",
    )

    dumped = response.model_dump()
    schema_fields = CredentialResolveResponse.model_json_schema()["properties"]

    assert dumped["secret_handle"] == "secret-handle://user-a/openai-prod/session-1"
    assert dumped["expires_at"] == expires_at
    assert "secret_handle" in schema_fields
    assert "expires_at" in schema_fields
    assert "raw_secret" not in schema_fields
    assert "api_key" not in schema_fields
    assert "secret" not in schema_fields

    with pytest.raises(ValidationError):
        CredentialResolveResponse(
            secret_handle="secret-handle://user-a/openai-prod/session-1",
            expires_at=expires_at,
            redacted_label="sk-...prod",
            raw_secret="sk-live-secret",
        )


def test_credential_resolver_owns_provider_lookup_handle_and_expiry() -> None:
    from graph_agent_gateway.credential_resolver import (
        CredentialResolveRequest,
        resolve_credential,
    )
    from graph_agent_gateway.registry.contracts import CredentialDescriptor

    now = datetime.now(UTC)
    raw_secret = "sk-owner-secret"

    class FakeProvider:
        def __init__(self) -> None:
            self.described_refs: list[str] = []

        def describe(self, ref: str) -> CredentialDescriptor:
            self.described_refs.append(ref)
            return CredentialDescriptor(
                ref=ref,
                exists=True,
                status="available",
                fingerprint="fingerprint-owner",
                scope="endpoint-openai",
                metadata={"raw_secret": raw_secret},
            )

        def get(self, ref: str) -> str:
            raise AssertionError(f"resolve_credential must not fetch raw secret for {ref}")

    provider = FakeProvider()
    response = resolve_credential(
        CredentialResolveRequest(
            user_id="user-a",
            role="graph_agent",
            credential_ref="endpoint:openai",
            source="local_input",
            ttl_seconds=60,
            now=now,
        ),
        credential_provider=provider,
    )

    assert provider.described_refs == ["endpoint:openai"]
    assert response.credential_ref == "endpoint:openai"
    assert response.secret_handle.startswith("secret-handle://studio-local/")
    assert raw_secret not in response.secret_handle
    assert response.expires_at == now + timedelta(seconds=60)
    assert response.fingerprint == "fingerprint-owner"
    assert response.scope == "endpoint-openai"
