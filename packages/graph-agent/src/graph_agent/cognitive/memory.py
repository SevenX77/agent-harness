"""Working memory utilities for cognitive control."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def update_working_memory(ctx: dict[str, Any], plan: str) -> str:
    """Persist intermediate plan/status so the agent can externalize cognition."""
    content = plan or ""
    ctx["_working_memory"] = content
    logger.info("update_working_memory: len=%d", len(content))
    return "WORKING_MEMORY_UPDATED"


__all__ = ["update_working_memory"]
