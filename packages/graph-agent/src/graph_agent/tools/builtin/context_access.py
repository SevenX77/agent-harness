"""Active mining tools for cross-phase context access.

These tools are auto-mounted when a phase opts in through
``context_access``. Phases otherwise keep strong isolation between agent
loops; artifacts and working memory are exposed only by request.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MAX_REPR_LENGTH = 50_000


def _truncate(text: str) -> str:
    if len(text) > _MAX_REPR_LENGTH:
        return text[:_MAX_REPR_LENGTH] + "... [truncated]"
    return text


def query_working_memory(ctx: dict[str, Any]) -> str:
    """Read the current phase's working memory."""
    raw = ctx.get("_working_memory")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return "(empty)"
    return _truncate(str(raw))


def read_artifact(ctx: dict[str, Any], name: str) -> str:
    """Read a named business artifact from the cross-phase context."""
    if not name or not isinstance(name, str):
        return "[read_artifact Error] name must be a non-empty string"
    if name.startswith("_"):
        return (
            f"[read_artifact Error] {name!r} is a framework-internal key "
            "and cannot be read. Only business artifacts (named outputs) "
            "are accessible."
        )
    if name not in ctx:
        visible = [str(key) for key in ctx if not str(key).startswith("_")]
        return (
            f"[read_artifact Error] artifact {name!r} not found in current ctx. "
            f"Available artifacts: {visible}"
        )

    value = ctx[name]
    if value is None:
        return "(none)"

    text = value if isinstance(value, str) else repr(value)
    text = _truncate(str(text))
    logger.info("read_artifact: name=%s len=%d", name, len(text))
    return text


__all__ = ["query_working_memory", "read_artifact"]
