"""Legacy environment patch API for Studio LLM credentials."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core import config
from app.models.llm_config import LLMCredentialsFile


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
    """Return no provider env metadata; API keys are no longer YAML/env-owned."""

    del roles_path
    return {}


def patch_environment_from_credentials(
    credentials: LLMCredentialsFile,
    *,
    roles_path: Path | None = None,
) -> dict[str, AppliedProviderEnv]:
    """No-op compatibility shim; runtime no longer mutates ``os.environ``."""

    del credentials, roles_path
    return {}


__all__ = [
    "AppliedProviderEnv",
    "ProviderEnvMetadata",
    "default_roles_path",
    "load_provider_env_metadata",
    "patch_environment_from_credentials",
]
