"""Precise Studio events for runtime_config dataset writes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.services.event_bus import STUDIO_EVENTS_TOPIC, event_bus

logger = logging.getLogger(__name__)


async def publish_runtime_config_changed(
    *,
    skill_id: str,
    dataset: str,
    node_id: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "type": "runtime_config_changed",
        "timestamp": datetime.now(UTC).isoformat(),
        "source": "http_api",
        "skill_id": skill_id,
        "dataset": dataset,
    }
    if node_id is not None:
        payload["node_id"] = node_id
    try:
        await event_bus.publish(STUDIO_EVENTS_TOPIC, payload)
    except Exception:
        logger.exception(
            "phase=publish_runtime_config_changed action=publish status=failed event_type=runtime_config_changed",
        )
