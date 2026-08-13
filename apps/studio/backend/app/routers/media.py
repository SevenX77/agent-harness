"""Media generation settings API (design:
docs/studio/mvp1/02_capabilities/media-generation/design-decision.md §D5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app.core.adapters.media_gateway import (
    MediaModelSettings,
    catalog_by_id,
    validate_model_settings,
)
from app.services import media_generation

router = APIRouter(prefix="/api/media", tags=["media"])


class CredentialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str | None = None
    base_url: str | None = None


class ModelSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    defaults: dict[str, str | int] | None = None


def _require_known_provider(provider_id: str) -> None:
    if provider_id != media_generation.MEDIA_PROVIDER_ID:
        raise HTTPException(status_code=404, detail=f"unknown media provider: {provider_id}")


@router.get("/registry")
async def get_media_registry() -> dict[str, Any]:
    return media_generation.registry_view(media_generation.load_state())


@router.put("/providers/{provider_id}/credential")
async def put_media_credential(provider_id: str, request: CredentialUpdate) -> dict[str, Any]:
    _require_known_provider(provider_id)
    state = media_generation.load_state()
    provider = state.providers[media_generation.MEDIA_PROVIDER_ID]
    if request.api_key is not None:
        provider.api_key = request.api_key.strip()
    if request.base_url is not None:
        base_url = request.base_url.strip()
        if not base_url:
            raise HTTPException(status_code=400, detail="base_url cannot be empty")
        provider.base_url = base_url
    media_generation.save_state(state)
    return media_generation.registry_view(state)


@router.get("/providers/{provider_id}/credential/secret")
async def get_media_credential_secret(provider_id: str) -> dict[str, str]:
    _require_known_provider(provider_id)
    state = media_generation.load_state()
    return {"api_key": state.providers[media_generation.MEDIA_PROVIDER_ID].api_key}


@router.post("/providers/{provider_id}/probe")
async def probe_media_provider(provider_id: str) -> dict[str, Any]:
    _require_known_provider(provider_id)
    state = media_generation.load_state()
    provider = state.providers[media_generation.MEDIA_PROVIDER_ID]
    if not provider.api_key:
        raise HTTPException(status_code=400, detail="api key not set")
    provider.last_probe = await media_generation.run_account_probe(provider)
    media_generation.save_state(state)
    return media_generation.registry_view(state)


@router.patch("/models/{model_id}/settings")
async def patch_media_model_settings(
    model_id: str, request: ModelSettingsUpdate
) -> dict[str, Any]:
    if model_id not in catalog_by_id():
        raise HTTPException(status_code=404, detail=f"unknown media model: {model_id}")

    state = media_generation.load_state()
    provider = state.providers[media_generation.MEDIA_PROVIDER_ID]
    current = provider.model_settings.get(model_id, MediaModelSettings())
    updated = MediaModelSettings(
        enabled=current.enabled if request.enabled is None else request.enabled,
        defaults=current.defaults if request.defaults is None else request.defaults,
    )
    try:
        validate_model_settings(model_id, updated)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    provider.model_settings[model_id] = updated
    media_generation.save_state(state)
    return media_generation.registry_view(state)
