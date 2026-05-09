from __future__ import annotations

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
    assert data.backends["gemini"].v1_5_placeholder is True
    assert data.backends["openai"].v1_5_placeholder is True


def test_write_credentials_is_atomic_and_chmod_600(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    data = CredentialsData(
        backends={
            "claude": BackendCredentials(api_key="claude-key"),
            "deepseek": BackendCredentials(api_key="deepseek-key"),
            "gemini": BackendCredentials(api_key="", v1_5_placeholder=True),
            "openai": BackendCredentials(api_key="", v1_5_placeholder=True),
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
            "deepseek": BackendCredentials(api_key="deepseek-key"),
            "gemini": BackendCredentials(api_key="", v1_5_placeholder=True),
            "openai": BackendCredentials(api_key="", v1_5_placeholder=True),
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
            "gemini": BackendCredentials(api_key="", v1_5_placeholder=True),
            "openai": BackendCredentials(api_key="", v1_5_placeholder=True),
        },
        active_backend="claude",
    )
    second = CredentialsData(
        backends={
            "claude": BackendCredentials(api_key="second"),
            "deepseek": BackendCredentials(api_key="deepseek"),
            "gemini": BackendCredentials(api_key="", v1_5_placeholder=True),
            "openai": BackendCredentials(api_key="", v1_5_placeholder=True),
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
                    "gemini": {"api_key": "", "V1_5_PLACEHOLDER": True},
                    "openai": {"api_key": "", "V1_5_PLACEHOLDER": True},
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
                    "gemini": {"api_key": "", "V1_5_PLACEHOLDER": True},
                    "openai": {"api_key": "", "V1_5_PLACEHOLDER": True},
                }
            }
        )
