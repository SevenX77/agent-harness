from __future__ import annotations

import pytest
from app.models.copilot import (
    BackendStatus,
    CredentialsReadResponse,
    CredentialsWriteRequest,
)
from pydantic import ValidationError


def test_copilot_backend_accepts_four_values() -> None:
    for backend in ("claude", "deepseek", "gemini", "openai"):
        request = CredentialsWriteRequest(backend=backend, api_key=None)
        assert request.backend == backend


def test_copilot_backend_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        CredentialsWriteRequest(backend="bad", api_key=None)


def test_credentials_read_response_is_sanitized() -> None:
    response = CredentialsReadResponse(
        backends={
            "claude": BackendStatus(has_key=True),
            "deepseek": BackendStatus(has_key=False),
            "gemini": BackendStatus(has_key=False, V1_5_PLACEHOLDER=True),
            "openai": BackendStatus(has_key=False, V1_5_PLACEHOLDER=True),
        },
        active_backend="claude",
    )

    dumped = response.model_dump(by_alias=True)
    assert dumped["backends"]["claude"] == {
        "has_key": True,
        "V1_5_PLACEHOLDER": False,
    }
    assert "api_key" not in str(dumped)


def test_credentials_write_request_accepts_none_and_default_set_active() -> None:
    request = CredentialsWriteRequest(backend="claude", api_key=None)

    assert request.api_key is None
    assert request.set_active is False


@pytest.mark.parametrize(
    ("model_cls", "payload"),
    [
        (BackendStatus, {"has_key": True, "extra": "nope"}),
        (
            CredentialsReadResponse,
            {
                "backends": {
                    "claude": {"has_key": False},
                    "deepseek": {"has_key": False},
                    "gemini": {"has_key": False, "V1_5_PLACEHOLDER": True},
                    "openai": {"has_key": False, "V1_5_PLACEHOLDER": True},
                },
                "active_backend": "claude",
                "extra": "nope",
            },
        ),
        (
            CredentialsWriteRequest,
            {"backend": "claude", "api_key": None, "set_active": False, "extra": "nope"},
        ),
    ],
)
def test_models_forbid_extra_fields(model_cls: type, payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model_cls.model_validate(payload)
