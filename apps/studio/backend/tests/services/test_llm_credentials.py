from __future__ import annotations

import os
from pathlib import Path

import pytest
from app.models.llm_config import LLMCredentialsFile, ProviderCredential
from app.services import llm_env
from app.services.llm_credentials import (
    credentials_path,
    load_credentials,
    redacted_for_response,
    save_credentials,
)


def test_read_write_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    data = LLMCredentialsFile(
        providers=[
            ProviderCredential(
                id="provider-1",
                name="Claude",
                api_key="secret",
                base_url="https://api.example.test",
            )
        ]
    )

    save_credentials(data)

    assert load_credentials() == data


def test_save_credentials_chmods_file_0600(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    save_credentials(
        LLMCredentialsFile(providers=[ProviderCredential(id="provider-1", name="Claude", api_key="secret")])
    )

    assert os.stat(credentials_path()).st_mode & 0o777 == 0o600


def test_redacted_for_response_never_returns_api_key() -> None:
    data = LLMCredentialsFile(
        providers=[
            ProviderCredential(id="provider-1", name="Claude", api_key="secret", base_url="https://base")
        ]
    )

    body = redacted_for_response(data)
    assert body["providers"][0]["id"] == "provider-1"
    assert body["providers"][0]["name"] == "Claude"
    assert body["providers"][0]["has_key"] is True
    assert body["providers"][0]["base_url"] == "https://base"
    assert body["providers"][0]["last_test_status"] == "untested"
    assert body["providers"][0]["available_models"] == []
    assert "api_key" not in body["providers"][0]
    assert "secret" not in str(body)


def test_patch_environment_is_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roles_path = _write_roles_yaml(tmp_path)
    monkeypatch.delenv("PRIMARY_KEY", raising=False)
    monkeypatch.setenv("FALLBACK_KEY", "fallback-secret")

    applied = llm_env.patch_environment_from_credentials(
        LLMCredentialsFile(providers=[ProviderCredential(id="provider-1", name="Claude")]),
        roles_path=roles_path,
    )

    assert applied == {}
    assert "PRIMARY_KEY" not in os.environ
    assert os.environ["FALLBACK_KEY"] == "fallback-secret"


def test_patch_environment_does_not_overwrite_existing_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roles_path = _write_roles_yaml(tmp_path)
    monkeypatch.setenv("PRIMARY_KEY", "existing-secret")

    llm_env.patch_environment_from_credentials(
        LLMCredentialsFile(providers=[ProviderCredential(id="provider-1", name="Claude", api_key="")]),
        roles_path=roles_path,
    )

    assert os.environ["PRIMARY_KEY"] == "existing-secret"


def test_patch_environment_does_not_patch_base_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roles_path = _write_roles_yaml(tmp_path)
    monkeypatch.delenv("PRIMARY_KEY", raising=False)
    monkeypatch.delenv("OC_CL_BASE_URL", raising=False)

    llm_env.patch_environment_from_credentials(
        LLMCredentialsFile(
            providers=[
                ProviderCredential(
                    id="provider-1",
                    name="Claude",
                    api_key="saved-secret",
                    base_url="https://override.test",
                )
            ]
        ),
        roles_path=roles_path,
    )

    assert "PRIMARY_KEY" not in os.environ
    assert "OC_CL_BASE_URL" not in os.environ


def test_legacy_copilot_json_is_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    studio_dir = tmp_path / ".studio"
    studio_dir.mkdir()
    (studio_dir / "copilot.json").write_text(
        '{"backends":{"claude":{"api_key":"legacy-secret"}},"active_backend":"claude"}',
        encoding="utf-8",
    )

    assert load_credentials() == LLMCredentialsFile()


def test_stale_v2_credentials_degrade_to_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    studio_dir = tmp_path / ".studio"
    studio_dir.mkdir()
    (studio_dir / "llm_credentials.json").write_text(
        '{"providers":[{"provider_code":"OC_CL","api_key":"legacy-secret"}]}',
        encoding="utf-8",
    )

    assert load_credentials() == LLMCredentialsFile()


def _write_roles_yaml(tmp_path: Path) -> Path:
    roles_path = tmp_path / "llm_roles.yaml"
    roles_path.write_text(
        """
providers:
  OC_CL:
    name: Claude
    type: anthropic_compatible
    api_key_env: PRIMARY_KEY
    api_key_env_fallback: FALLBACK_KEY
    base_url: https://default.test
    base_url_env: OC_CL_BASE_URL
roles: {}
models: {}
""".lstrip(),
        encoding="utf-8",
    )
    return roles_path
