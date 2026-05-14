from __future__ import annotations

import pytest
from app.models.copilot import (
    CopilotCredentials,
    ModelInfo,
    ProviderConfig,
    TestProviderRequest as ProviderTestRequest,
    TestProviderResponse as ProviderTestResponse,
)
from pydantic import ValidationError


def test_provider_config_accepts_v2_provider_kinds() -> None:
    for kind in ("anthropic", "openai-compat", "google"):
        provider = ProviderConfig(id=f"default-{kind}", name=kind, kind=kind, api_key="secret")
        assert provider.kind == kind
        assert provider.api_key == "secret"


def test_provider_config_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(id="bad", name="Bad", kind="bad-kind")


def test_copilot_credentials_keeps_plaintext_keys_and_no_sanitized_fields() -> None:
    credentials = CopilotCredentials(
        active_provider_id="default-claude",
        providers=[
            ProviderConfig(
                id="default-claude",
                name="Claude",
                kind="anthropic",
                api_key="sk-secret",
                active_model_id="claude-sonnet-4-5",
            )
        ],
    )

    dumped = credentials.model_dump()
    assert dumped["active_provider_id"] == "default-claude"
    assert dumped["providers"][0]["api_key"] == "sk-secret"
    assert dumped["providers"][0]["active_model_id"] == "claude-sonnet-4-5"
    assert "has_key" not in str(dumped)
    assert "last4" not in str(dumped)
    assert "backends" not in str(dumped)


def test_copilot_credentials_requires_active_provider_id() -> None:
    with pytest.raises(ValidationError):
        CopilotCredentials.model_validate({"providers": []})


def test_models_ignore_extra_fields() -> None:
    provider = ProviderConfig.model_validate(
        {"id": "default-claude", "name": "Claude", "kind": "anthropic", "extra": "ignored"}
    )
    request = ProviderTestRequest.model_validate(
        {
            "id": "default-claude",
            "name": "Claude",
            "kind": "anthropic",
            "api_key": "secret",
            "extra": "ignored",
        }
    )

    assert not hasattr(provider, "extra")
    assert not hasattr(request, "extra")


def test_test_provider_response_carries_models() -> None:
    response = ProviderTestResponse(
        status="ok",
        latency_ms=42,
        models=[ModelInfo(id="claude-opus-4-7", supports_thinking=True, supports_vision=True)],
    )

    assert response.models[0].id == "claude-opus-4-7"
    assert response.models[0].supports_thinking is True
