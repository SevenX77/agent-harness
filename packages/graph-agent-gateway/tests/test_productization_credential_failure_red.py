"""MVP1 productization RED tests for credential failure and expiry handling."""

from __future__ import annotations

from typing import Any

import pytest


def _resolved_route(credential_ref: str):
    from graph_agent_gateway.registry import ResolvedRoute

    return ResolvedRoute(
        role_name="graph_agent",
        route_id="vault:gpt-5",
        endpoint_id="vault",
        protocol="openai_compatible",
        base_url="https://vault.example/v1",
        credential_ref=credential_ref,
        credential_fingerprint="vault-fingerprint",
        provider_model_id="gpt-5",
        canonical_id="gpt-5",
    )


def _error_code(exc: BaseException) -> str | None:
    return getattr(exc, "error_code", getattr(exc, "code", None))


def test_fake_vault_5xx_is_reported_as_vault_unreachable() -> None:
    from graph_agent_gateway.call import RouteChatModelFactory

    class FakeVault5xxProvider:
        def get(self, ref: str) -> str:
            raise RuntimeError(f"vault 500 while resolving {ref}")

    with pytest.raises(Exception) as exc_info:
        RouteChatModelFactory(credential_provider=FakeVault5xxProvider()).build(
            _resolved_route("credential:remote-vault-openai")
        )

    assert _error_code(exc_info.value) == "credential.vault_unreachable"
    assert getattr(exc_info.value, "error_payload", {})["credential_ref"] == (
        "credential:remote-vault-openai"
    )


def test_expired_secret_handle_is_rejected_before_provider_build(monkeypatch: pytest.MonkeyPatch) -> None:
    from graph_agent_gateway.call import RouteChatModelFactory
    from graph_agent_gateway.call import factory as route_chat_model_factory

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    class ExpiredHandleProvider:
        def get(self, ref: str) -> str:
            assert ref == "secret-handle://expired/openai"
            return "sk-expired-secret"

    monkeypatch.setattr(route_chat_model_factory, "ChatOpenAI", FakeChatOpenAI)

    with pytest.raises(Exception) as exc_info:
        RouteChatModelFactory(credential_provider=ExpiredHandleProvider()).build(
            _resolved_route("secret-handle://expired/openai")
        )

    assert _error_code(exc_info.value) == "credential.secret_expired"
    assert getattr(exc_info.value, "error_payload", {})["credential_ref"] == (
        "secret-handle://expired/openai"
    )
