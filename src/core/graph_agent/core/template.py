"""Template rendering helpers for GraphAgent phase prompts."""

from __future__ import annotations

import logging
import re
from typing import Any

from .types import Phase

logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _safe_render_template(template: str, context: dict[str, Any]) -> str:
    """Render ``{key}`` placeholders without conflicting with JSON braces."""

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in context:
            return str(context[key])
        logger.debug(
            "[Template] Placeholder '{%s}' not resolved (available: %s)",
            key,
            ", ".join(sorted(context.keys())[:10]),
        )
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_replace, template)


def _render_user_prompt(phase: Phase, context: dict[str, Any]) -> str:
    """Render the phase's user_prompt_template with context values."""
    template = phase.user_prompt_template
    if not template:
        return "请根据当前上下文完成本阶段任务。"
    return _safe_render_template(template, context)


__all__ = ["_render_user_prompt", "_safe_render_template"]
