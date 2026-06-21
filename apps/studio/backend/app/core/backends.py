"""Dependency factories for Studio backend ports."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from secrets import token_urlsafe

from fastapi import Depends, Request
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core import config
from app.core.adapters.auth_local import NoAuthProvider
from app.core.adapters.eventbus_memory import InMemoryEventBus
from app.core.adapters.metadata_local import LocalJsonMetadataStore
from app.core.adapters.storage_local import LocalFilesystemBackend
from app.core.ports.auth import AuthProvider
from app.core.ports.eventbus import EventBus
from app.core.ports.metadata import MetadataStore
from app.core.ports.storage import StorageBackend
from app.services.artifact_registry import ArtifactRegistryClient
from app.services.git_collab import GitCollaborateService, GiteaClient
from app.services.git_local import GitLocalService

_DEFAULT_LOOPBACK_TOKEN = token_urlsafe(32)


class BackendConfig(BaseSettings):
    """Environment-driven backend selection for local-first Studio ports."""

    model_config = SettingsConfigDict(env_prefix="STUDIO_", extra="ignore")

    storage_type: str = "local"
    metadata_type: str = "local"
    eventbus_type: str = "memory"
    auth_type: str = "none"
    global_config_dir: Path = Field(default_factory=lambda: config.APP_SETTINGS_DIR)
    workspaces_root: Path = Field(default_factory=lambda: config.WORKSPACES_DIR)
    default_user_id: str = Field(default_factory=lambda: config.DEFAULT_USER_ID)
    gitea_host: str = ""
    gitea_token: str = ""
    registry_host: str = ""
    registry_token: str = ""
    github_token: str = ""
    github_owner: str = ""
    llm_catalog_repo: str = "studio-llm-model-catalog"
    llm_catalog_branch: str = "main"
    llm_catalog_path: str = "llm_import_drafts.json"
    engine_transport: str = "in_process"
    engine_loopback_base_url: str = "http://127.0.0.1:8787"
    gateway_transport: str = "in_process"
    gateway_loopback_base_url: str = "http://127.0.0.1:8787"
    loopback_token: str = Field(default_factory=lambda: _DEFAULT_LOOPBACK_TOKEN)


@lru_cache
def get_backend_config() -> BackendConfig:
    """Return cached backend configuration."""
    return BackendConfig()


@lru_cache
def get_storage() -> StorageBackend:
    """Return the configured StorageBackend."""
    cfg = get_backend_config()
    if cfg.storage_type != "local":
        raise ValueError(f"Unsupported storage backend: {cfg.storage_type}")
    return LocalFilesystemBackend(cfg.workspaces_root)


@lru_cache
def get_metadata() -> MetadataStore:
    """Return the configured MetadataStore."""
    cfg = get_backend_config()
    if cfg.metadata_type != "local":
        raise ValueError(f"Unsupported metadata backend: {cfg.metadata_type}")
    return LocalJsonMetadataStore(
        global_config_dir=cfg.global_config_dir,
        workspaces_root=cfg.workspaces_root,
    )


@lru_cache
def get_eventbus() -> EventBus:
    """Return the configured EventBus."""
    cfg = get_backend_config()
    if cfg.eventbus_type != "memory":
        raise ValueError(f"Unsupported eventbus backend: {cfg.eventbus_type}")
    return InMemoryEventBus()


@lru_cache
def get_auth() -> AuthProvider:
    """Return the configured AuthProvider."""
    cfg = get_backend_config()
    if cfg.auth_type != "none":
        raise ValueError(f"Unsupported auth backend: {cfg.auth_type}")
    return NoAuthProvider(cfg.default_user_id)


@lru_cache
def get_gitea_client() -> GiteaClient:
    """Return a cached Gitea API client."""
    cfg = get_backend_config()
    return GiteaClient(host=cfg.gitea_host, token=cfg.gitea_token)


@lru_cache
def get_registry_client() -> ArtifactRegistryClient:
    """Return a cached Artifact Registry API client."""
    cfg = get_backend_config()
    return ArtifactRegistryClient(host=cfg.registry_host, token=cfg.registry_token)


@lru_cache
def get_git_collab() -> GitCollaborateService:
    """Return the configured L2 Git collaboration service."""
    cfg = get_backend_config()
    return GitCollaborateService(
        local_git=GitLocalService(),
        gitea=get_gitea_client(),
        gitea_host=cfg.gitea_host,
    )


async def get_auth_user_id(
    request: Request,
    auth: AuthProvider = Depends(get_auth),
) -> str:
    """Resolve the current user id through the configured AuthProvider."""
    return await auth.get_current_user_id(request)


def clear_backend_caches() -> None:
    """Clear cached backend instances after config changes."""
    get_backend_config.cache_clear()
    get_storage.cache_clear()
    get_metadata.cache_clear()
    get_auth.cache_clear()
    get_gitea_client.cache_clear()
    get_registry_client.cache_clear()
    get_git_collab.cache_clear()
