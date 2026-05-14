from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from app.services.copilot_credentials import (
    BackendCredentials,
    CredentialsData,
    credentials_path,
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

    assert data.active_backend == "claude"
    assert set(data.backends) == {"claude", "deepseek", "gemini", "openai"}
    assert all(backend.api_key == "" for backend in data.backends.values())
    assert all(backend.base_url == "" for backend in data.backends.values())
    assert "v1_5_placeholder" not in data.backends["gemini"].model_fields_set


def test_write_credentials_is_atomic_and_chmod_600(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    data = CredentialsData(
        backends={
            "claude": BackendCredentials(api_key="claude-key"),
            "deepseek": BackendCredentials(api_key="deepseek-key"),
            "gemini": BackendCredentials(api_key=""),
            "openai": BackendCredentials(api_key=""),
        },
        active_backend="deepseek",
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
    data = CredentialsData(
        backends={
            "claude": BackendCredentials(api_key="claude-key"),
            "deepseek": BackendCredentials(
                api_key="deepseek-key",
                base_url="https://api.deepseek.example",
            ),
            "gemini": BackendCredentials(api_key=""),
            "openai": BackendCredentials(api_key=""),
        },
        active_backend="claude",
    )

    write_credentials(data)

    assert read_credentials() == data


def test_concurrent_writes_do_not_corrupt_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    first = CredentialsData(
        backends={
            "claude": BackendCredentials(api_key="first"),
            "deepseek": BackendCredentials(api_key=""),
            "gemini": BackendCredentials(api_key=""),
            "openai": BackendCredentials(api_key=""),
        },
        active_backend="claude",
    )
    second = CredentialsData(
        backends={
            "claude": BackendCredentials(api_key="second"),
            "deepseek": BackendCredentials(api_key="deepseek", base_url="https://deepseek.local"),
            "gemini": BackendCredentials(api_key=""),
            "openai": BackendCredentials(api_key=""),
        },
        active_backend="deepseek",
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(write_credentials, [first, second]))

    stored = read_credentials()
    assert stored in (first, second)
    assert os.stat(credentials_path()).st_mode & 0o777 == 0o600


def test_schema_validation_rejects_invalid_backend() -> None:
    with pytest.raises(ValidationError):
        CredentialsData.model_validate(
            {
                "backends": {
                    "claude": {"api_key": ""},
                    "deepseek": {"api_key": ""},
                    "gemini": {"api_key": ""},
                    "openai": {"api_key": ""},
                    "bad": {"api_key": ""},
                },
                "active_backend": "claude",
            }
        )


def test_schema_validation_rejects_missing_active_backend() -> None:
    with pytest.raises(ValidationError):
        CredentialsData.model_validate(
            {
                "backends": {
                    "claude": {"api_key": ""},
                    "deepseek": {"api_key": ""},
                    "gemini": {"api_key": ""},
                    "openai": {"api_key": ""},
                }
            }
        )


def test_old_v1_5_placeholder_field_is_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    path = credentials_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "backends": {
                    "claude": {"api_key": "key", "V1_5_PLACEHOLDER": False},
                    "deepseek": {"api_key": "", "V1_5_PLACEHOLDER": False},
                    "gemini": {"api_key": "", "V1_5_PLACEHOLDER": True},
                    "openai": {"api_key": "", "V1_5_PLACEHOLDER": True},
                },
                "active_backend": "claude",
            }
        ),
        encoding="utf-8",
    )

    data = read_credentials()

    assert data.backends["claude"].api_key == "key"
    assert data.backends["claude"].base_url == ""
    assert not hasattr(data.backends["gemini"], "v1_5_placeholder")


def test_base_url_is_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    data = default_data_with_deepseek_base_url()

    write_credentials(data)

    stored = read_credentials()
    assert stored.backends["deepseek"].base_url == "https://api.deepseek.example"
    assert "V1_5_PLACEHOLDER" not in credentials_path().read_text(encoding="utf-8")


def default_data_with_deepseek_base_url() -> CredentialsData:
    return CredentialsData(
        backends={
            "claude": BackendCredentials(api_key=""),
            "deepseek": BackendCredentials(
                api_key="deepseek-key",
                base_url="https://api.deepseek.example",
            ),
            "gemini": BackendCredentials(api_key=""),
            "openai": BackendCredentials(api_key=""),
        },
        active_backend="deepseek",
    )
