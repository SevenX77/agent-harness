"""Template rendering helpers for GraphAgent phase prompts."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{(\w+)\}(?!\})")


class MissingContextError(RuntimeError):
    """Raised when a runtime template variable cannot be resolved."""


def _safe_render_template(
    template: str,
    context: dict[str, Any],
    *,
    phase_name: str | None = None,
    strict: bool = False,
) -> str:
    """Render ``{key}`` placeholders without conflicting with JSON braces."""
    if strict:
        referenced = sorted(set(_PLACEHOLDER_RE.findall(template)))
        missing = [key for key in referenced if context.get(key) is None]
        if missing:
            available = sorted(
                str(key)
                for key, value in context.items()
                if value is not None and not str(key).startswith("_")
            )
            phase_label = phase_name or "unknown"
            raise MissingContextError(
                f"[ContextError] 在渲染 Phase '{phase_label}' 的 User Prompt 时，"
                f"变量 {missing} 未找到（值为 None 或缺失）。\n"
                "请检查前序 Phase 是否已通过 hoist_to 注册为 output，"
                "或检查全局 io.inputs 声明。\n"
                f"当前可用变量: {available}"
            )

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


__all__ = ["MissingContextError", "_safe_render_template"]
