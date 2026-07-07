"""Global Studio settings endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from app.core import config
from app.core.backends import get_metadata
from app.core.exceptions import error_response, raise_error_response
from app.core.ports.metadata import MetadataStore
from app.models.settings import AppSettings
from app.services.event_bus import STUDIO_EVENTS_TOPIC, event_bus
from app.services.runtime_activity import record_runtime_activity

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
    previous = _with_effective_defaults(await metadata.read_app_settings())
    changes = _settings_changes(previous, settings)
    if not changes:
        return previous
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
    await _publish_settings_changed(changes)
    record_runtime_activity(
        source_id="app_settings",
        action="update_app_settings",
        message="Saved Studio general settings.",
        changes=changes,
    )
    return settings


def _settings_changes(previous: AppSettings, current: AppSettings) -> dict[str, dict[str, object]]:
    previous_data = previous.model_dump(mode="json")
    current_data = current.model_dump(mode="json")
    return {
        key: {"from": previous_data.get(key), "to": value}
        for key, value in current_data.items()
        if previous_data.get(key) != value
    }


async def _publish_settings_changed(changes: dict[str, dict[str, object]]) -> None:
    payload: dict[str, Any] = {
        "type": "settings_changed",
        "timestamp": datetime.now(UTC).isoformat(),
        "source": "http_api",
        "source_id": "app_settings",
        "changed_fields": sorted(changes),
        "changes": changes,
    }
    try:
        await event_bus.publish(STUDIO_EVENTS_TOPIC, payload)
    except Exception:
        logger.exception(
            "phase=publish_settings_changed action=publish status=failed payload=%s",
            payload,
        )
