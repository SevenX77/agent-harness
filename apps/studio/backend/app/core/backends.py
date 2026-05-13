"""Dependency factories for Studio backend ports."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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
