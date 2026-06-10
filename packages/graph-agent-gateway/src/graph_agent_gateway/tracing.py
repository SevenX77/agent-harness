"""Gateway tracing adapter helpers."""

from __future__ import annotations

import logging
from typing import Any

from graph_agent_gateway.events import LLMFallbackEvent

logger = logging.getLogger(__name__)


def build_llm_fallback_event(
    *,
    phase_name: str,
    from_provider: str,
    to_provider: str,
    reason: str,
    context: dict[str, Any] | None = None,
) -> LLMFallbackEvent:
    """Build one fallback event using the shared graph-agent callback schema."""
    return LLMFallbackEvent(
        phase_name=phase_name,
        from_provider=from_provider,
        to_provider=to_provider,
        reason=reason,
        context=dict(context or {}),
    )


def emit_llm_fallback_event(
    *,
    callbacks: tuple[Any, ...],
    phase_name: str,
    from_provider: str,
    to_provider: str,
    reason: str,
    context: dict[str, Any] | None = None,
) -> None:
    """Emit a gateway fallback event without letting callback failures mask runtime errors."""
    event = build_llm_fallback_event(
        phase_name=phase_name,
        from_provider=from_provider,
        to_provider=to_provider,
        reason=reason,
        context=context,
    )
    for callback in callbacks:
        try:
            callback.on_event(event)
        except Exception:
            logger.exception(
                "phase=gateway_tracing action=callback_failed callback=%s",
                type(callback).__name__,
            )
