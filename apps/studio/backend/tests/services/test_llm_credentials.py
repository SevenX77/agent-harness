from __future__ import annotations

import os
from pathlib import Path

import pytest
from app.models.llm_config import LLMCredentialsFile, ModelInfo, ProviderCredential
from app.routers.llm import CredentialsWriteRequest, ProviderCredentialWrite, put_llm_credentials
from app.services import llm_env
from app.services.llm_credentials import (
    credentials_path,
    load_credentials,
    save_credentials,
    serialize_for_response,
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


def test_serialize_for_response_returns_api_key_plaintext() -> None:
    data = LLMCredentialsFile(
        providers=[
            ProviderCredential(id="provider-1", name="Claude", api_key="secret", base_url="https://base")
        ]
    )

    body = serialize_for_response(data)
    assert body["providers"][0]["id"] == "provider-1"
    assert body["providers"][0]["name"] == "Claude"
    assert body["providers"][0]["api_key"] == "secret"
    assert body["providers"][0]["base_url"] == "https://base"
    assert body["providers"][0]["last_test_status"] == "untested"
    assert body["providers"][0]["available_sdks"] == []
    assert body["providers"][0]["available_models"] == []
    assert "has_key" not in body["providers"][0]


def test_credential_state_has_available_sdks_and_models() -> None:
    state = ProviderCredential(id="provider-1", name="OpenAI", api_key="sk-secret")

    assert state.available_sdks == []
    assert state.available_models == []


def test_serialize_for_response_includes_new_fields() -> None:
    data = LLMCredentialsFile(
        providers=[
            ProviderCredential(
                id="provider-1",
                name="OpenAI",
                api_key="sk-secret",
                available_sdks=["openai_compatible"],
                available_models=[ModelInfo(id="gpt-5")],
            )
        ]
    )

    body = serialize_for_response(data)

    assert body["providers"][0]["available_sdks"] == ["openai_compatible"]
    assert [model["id"] for model in body["providers"][0]["available_models"]] == ["gpt-5"]


def test_model_info_capabilities_accepts_legacy_and_arbitrary_dicts() -> None:
    legacy = ModelInfo.model_validate(
        {
            "id": "gpt-4o",
            "capabilities": {
                "text": True,
                "function_calling": True,
                "vision": True,
                "reasoning": False,
            },
        }
    )
    expanded = ModelInfo.model_validate(
        {
            "id": "openrouter/auto",
            "capabilities": {
                "max_context_tokens": 131072,
                "max_output_tokens": 8192,
                "modalities": ["text", "image"],
                "pricing": {"prompt": "0.1"},
            },
        }
    )

    assert legacy.capabilities["function_calling"] is True
    assert expanded.capabilities["max_context_tokens"] == 131072
    assert expanded.capabilities["pricing"] == {"prompt": "0.1"}


@pytest.mark.anyio
async def test_put_empty_api_key_preserves_available_sdks_and_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    save_credentials(
        LLMCredentialsFile(
            providers=[
                ProviderCredential(
                    id="provider-1",
                    name="OpenAI",
                    api_key="sk-secret",
                    base_url="https://api.openai.com",
                    provider_type="openai_compatible",
                    available_sdks=["openai_compatible"],
                    available_models=[ModelInfo(id="gpt-5")],
                )
            ]
        )
    )

    body = await put_llm_credentials(
        CredentialsWriteRequest(
            providers=[
                ProviderCredentialWrite(
                    id="provider-1",
                    name="OpenAI renamed",
                    api_key="",
                    base_url="https://api.openai.test",
                    provider_type="openai_compatible",
                )
            ]
        )
    )

    provider = body["providers"][0]
    assert provider["api_key"] == "sk-secret"
    assert provider["available_sdks"] == ["openai_compatible"]
    assert [model["id"] for model in provider["available_models"]] == ["gpt-5"]


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
