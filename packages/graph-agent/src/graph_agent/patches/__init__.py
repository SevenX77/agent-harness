"""Central startup monkey-patch entry points."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_applied = False


def apply_all() -> None:
    """Apply all framework compatibility patches once."""

    global _applied
    if _applied:
        return

    from graph_agent.models.reasoning_patch import _apply_reasoning_content_patch

    _apply_reasoning_content_patch()
    _applied = True
    logger.debug("graph_agent patches applied")


def reset_for_tests() -> None:
    """Reset this module's idempotence guard for isolated unit tests."""

    global _applied
    _applied = False


__all__ = ["apply_all"]
