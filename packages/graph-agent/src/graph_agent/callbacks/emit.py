"""Shared callback event emission helpers."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _safe_emit_event(callbacks: list[Any] | None, event: Any) -> None:
    """Dispatch a typed callback event without letting callback failures abort a run."""
    for callback in callbacks or []:
        try:
            callback.on_event(event)
        except Exception:  # noqa: BLE001
            logger.exception(
                "[Callbacks] callback %r raised on %s; continuing with other callbacks",
                type(callback).__name__,
                type(event).__name__,
            )


__all__ = ["_safe_emit_event"]
