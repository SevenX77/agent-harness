"""Global Studio settings endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.core import config
from app.core.backends import get_metadata
from app.core.exceptions import error_response, raise_error_response
from app.core.ports.metadata import MetadataStore
from app.models.settings import AppSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _with_effective_defaults(settings: AppSettings) -> AppSettings:
    """Return settings with concrete defaults for values the UI edits directly."""
    if settings.default_skills_directory:
        return settings
    return settings.model_copy(update={"default_skills_directory": str(config.DEFAULT_SKILLS_ROOT)})


@router.get("", response_model=AppSettings)
async def get_settings(
    metadata: MetadataStore = Depends(get_metadata),
) -> AppSettings:
    """Return global Studio app settings."""
    return _with_effective_defaults(await metadata.read_app_settings())


@router.put("", response_model=AppSettings)
async def put_settings(
    settings: AppSettings,
    metadata: MetadataStore = Depends(get_metadata),
) -> AppSettings:
    """Persist global Studio app settings."""
    settings = _with_effective_defaults(settings)
    try:
        await metadata.write_app_settings(settings)
    except Exception as exc:
        logger.exception("Failed to write Studio app settings")
        response = error_response(
            error_code="SETTINGS_WRITE_FAILED",
            http_status=500,
            message="Failed to write Studio app settings",
            details={"error": str(exc)},
            retry_strategy="idempotent",
        )
        raise_error_response(response)
    return settings
