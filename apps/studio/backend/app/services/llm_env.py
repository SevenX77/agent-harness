"""Patch process environment from Studio LLM credentials and role metadata."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.core import config
from app.models.llm_config import LLMCredentialsFile, ProviderCredential


@dataclass(frozen=True)
class ProviderEnvMetadata:
    """Environment variable metadata declared by one provider."""

    provider_code: str
    api_key_env: str = ""
    api_key_env_fallback: str = ""
    base_url: str = ""
    base_url_env: str = ""


@dataclass(frozen=True)
class AppliedProviderEnv:
    """Effective values observed or patched for one provider."""

    api_key: str = ""
    base_url: str = ""


def default_roles_path() -> Path:
    """Return the repo-local role configuration path."""

    return config.REPO_ROOT / "config" / "llm_roles.yaml"


def load_provider_env_metadata(roles_path: Path | None = None) -> dict[str, ProviderEnvMetadata]:
    """Load provider env metadata from ``llm_roles.yaml``."""

    path = roles_path or default_roles_path()
    with path.open("r", encoding="utf-8") as stream:
        raw = yaml.safe_load(stream) or {}
    providers = raw.get("providers") or {}
    if not isinstance(providers, dict):
        return {}

    result: dict[str, ProviderEnvMetadata] = {}
    for provider_code, provider_data in providers.items():
        if not isinstance(provider_data, dict):
            continue
        result[str(provider_code)] = ProviderEnvMetadata(
            provider_code=str(provider_code),
            api_key_env=str(provider_data.get("api_key_env") or ""),
            api_key_env_fallback=str(provider_data.get("api_key_env_fallback") or ""),
            base_url=str(provider_data.get("base_url") or ""),
            base_url_env=str(provider_data.get("base_url_env") or ""),
        )
    return result


def patch_environment_from_credentials(
    credentials: LLMCredentialsFile,
    *,
    roles_path: Path | None = None,
) -> dict[str, AppliedProviderEnv]:
    """Patch missing process env values from saved credentials and fallback env."""

    metadata = load_provider_env_metadata(roles_path)
    credentials_by_code = {provider.provider_code: provider for provider in credentials.providers}
    applied: dict[str, AppliedProviderEnv] = {}

    for provider_code, provider in credentials_by_code.items():
        provider_metadata = metadata.get(provider_code)
        if provider_metadata is None:
            continue
        api_key = _patch_api_key_env(provider, provider_metadata)
        base_url = _patch_base_url_env(provider, provider_metadata)
        applied[provider_code] = AppliedProviderEnv(api_key=api_key, base_url=base_url)

    return applied


def _patch_api_key_env(
    provider: ProviderCredential,
    metadata: ProviderEnvMetadata,
) -> str:
    primary_env = metadata.api_key_env
    fallback_env = metadata.api_key_env_fallback
    existing_primary = os.environ.get(primary_env, "") if primary_env else ""
    existing_fallback = os.environ.get(fallback_env, "") if fallback_env else ""
    saved_key = provider.api_key.strip()
    effective_key = existing_primary or existing_fallback or saved_key

    if primary_env and not existing_primary and effective_key:
        os.environ[primary_env] = effective_key
    return effective_key


def _patch_base_url_env(
    provider: ProviderCredential,
    metadata: ProviderEnvMetadata,
) -> str:
    base_url_env = metadata.base_url_env
    existing_base_url = os.environ.get(base_url_env, "") if base_url_env else ""
    saved_base_url = provider.base_url.strip()
    effective_base_url = existing_base_url or saved_base_url or metadata.base_url

    if base_url_env and not existing_base_url and saved_base_url:
        os.environ[base_url_env] = saved_base_url
    return effective_base_url


__all__ = [
    "AppliedProviderEnv",
    "ProviderEnvMetadata",
    "default_roles_path",
    "load_provider_env_metadata",
    "patch_environment_from_credentials",
]
