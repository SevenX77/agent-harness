from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from app.models.copilot import CopilotCredentials, ProviderConfig
from app.services.copilot_credentials import (
    credentials_path,
    default_credentials,
    read_credentials,
    write_credentials,
)
from pydantic import ValidationError


def test_read_credentials_returns_default_when_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    data = read_credentials()

    assert data == default_credentials()
    assert data.active_provider_id == "default-claude"
    assert [provider.id for provider in data.providers] == [
        "default-claude",
        "default-openai",
        "default-deepseek",
        "default-gemini",
    ]
    assert [provider.kind for provider in data.providers] == [
        "anthropic",
        "openai-compat",
        "openai-compat",
        "google",
    ]
    assert all(provider.api_key == "" for provider in data.providers)
    assert all(provider.base_url == "" for provider in data.providers)
    assert all(provider.active_model_id is None for provider in data.providers)


def test_write_credentials_is_atomic_and_chmod_600(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    data = CopilotCredentials(
        active_provider_id="default-openai",
        providers=[
            ProviderConfig(id="default-claude", name="Claude", kind="anthropic", api_key="claude-key"),
            ProviderConfig(id="default-openai", name="OpenAI", kind="openai-compat", api_key="openai-key"),
        ],
    )

    write_credentials(data)

    path = credentials_path()
    assert path.exists()
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert not list(path.parent.glob("*.tmp"))


def test_read_after_write_round_trips(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    data = CopilotCredentials(
        active_provider_id="custom-local",
        providers=[
            ProviderConfig(
                id="default-claude",
                name="Claude",
                kind="anthropic",
                api_key="claude-key",
                active_model_id="claude-sonnet-4-5",
            ),
            ProviderConfig(
                id="custom-local",
                name="Ollama Local",
                kind="openai-compat",
                api_key="ollama-key",
                base_url="http://localhost:11434/v1",
                active_model_id="llama3.2",
            ),
        ],
    )

    write_credentials(data)

    assert read_credentials() == data


def test_concurrent_writes_do_not_corrupt_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    first = CopilotCredentials(
        active_provider_id="default-claude",
        providers=[ProviderConfig(id="default-claude", name="Claude", kind="anthropic", api_key="first")],
    )
    second = CopilotCredentials(
        active_provider_id="default-deepseek",
        providers=[
            ProviderConfig(id="default-claude", name="Claude", kind="anthropic", api_key=""),
            ProviderConfig(
                id="default-deepseek",
                name="DeepSeek",
                kind="openai-compat",
                api_key="deepseek",
                base_url="https://deepseek.local/v1",
            ),
        ],
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(write_credentials, [first, second]))

    stored = read_credentials()
    assert stored in (first, second)
    assert os.stat(credentials_path()).st_mode & 0o777 == 0o600


def test_schema_validation_rejects_invalid_kind() -> None:
    with pytest.raises(ValidationError):
        CopilotCredentials.model_validate(
            {
                "active_provider_id": "default-claude",
                "providers": [
                    {
                        "id": "default-claude",
                        "name": "Claude",
                        "kind": "bad-kind",
                        "api_key": "",
                    }
                ],
            }
        )


def test_schema_validation_rejects_missing_active_provider_id() -> None:
    with pytest.raises(ValidationError):
        CopilotCredentials.model_validate(
            {
                "providers": [
                    {
                        "id": "default-claude",
                        "name": "Claude",
                        "kind": "anthropic",
                        "api_key": "",
                    }
                ],
            }
        )


def test_legacy_backends_file_is_overwritten_with_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    path = credentials_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "backends": {
                    "claude": {"api_key": "legacy-key", "base_url": "https://legacy.example"},
                    "deepseek": {"api_key": ""},
                    "gemini": {"api_key": ""},
                    "openai": {"api_key": ""},
                },
                "active_backend": "claude",
            }
        ),
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        data = read_credentials()

    assert data == default_credentials()
    assert "legacy format detected, overwriting with v2 defaults" in caplog.text
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written == data.model_dump(mode="json")
    assert "backends" not in written
    assert "active_backend" not in written
    assert all("api_key" in provider for provider in written["providers"])


def test_validation_error_file_is_overwritten_with_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    path = credentials_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"active_provider_id": "missing-providers"}),
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        data = read_credentials()

    assert data == default_credentials()
    assert "legacy format detected, overwriting with v2 defaults" in caplog.text
    assert json.loads(path.read_text(encoding="utf-8")) == data.model_dump(mode="json")
