"""ContextResolver — Expression engine for context_mapping in SKILL.md.

Resolves declarative expressions from SKILL.md frontmatter context_mapping
into concrete context values, eliminating the need for manual context_builder.py.

Supported expression syntax:
- ``{input.scene.scene_id}``        — dot-path value lookup
- plain string                       — passed through as-is
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.exceptions import SkillLoadError

_MAX_CONTEXT_PATH_DEPTH = 32
_SCALAR_TYPES = (str, bytes, int, float, bool)


class ContextResolver:
    """Resolve context_mapping expressions into concrete context values.

    Supported syntax: ``{dot.path}`` deep lookup, quoted literals, plain strings.
    ``$func()`` syntax is deprecated (compiler F006 FATAL) and will raise at resolve time.

    Args:
        mapping: Dict of ``{context_key: expression_string}`` from SKILL.md frontmatter.
        helpers_dir: Ignored (kept for backward compatibility).
    """

    def __init__(
        self,
        mapping: dict[str, str],
        # Kept for backward compatibility; helper-based $func() is deprecated.
        helpers_dir: Path | None = None,
    ) -> None:
        self._mapping = mapping

    def resolve(self, raw_inputs: dict[str, Any]) -> dict[str, Any]:
        """Resolve all mapping expressions against raw_inputs.

        Args:
            raw_inputs: Dict with an ``input`` key containing the raw data.
                Example: ``{"input": {"scene": {...}, "entity_registry": {...}}}``

        Returns:
            Dict of resolved context values keyed by mapping keys.
        """
        result: dict[str, Any] = {}
        for key, expr in self._mapping.items():
            try:
                result[key] = self._resolve_expr(expr, raw_inputs)
            except Exception as exc:
                raise SkillLoadError(
                    f"Failed to resolve context_mapping key '{key}' "
                    f"with expression '{expr}': {exc}"
                ) from exc
        return result

    # ------------------------------------------------------------------
    # Expression resolution
    # ------------------------------------------------------------------

    def _resolve_expr(self, expr: str, inputs: dict[str, Any]) -> Any:
        """Resolve a single expression string.

        Handles three forms:
        - ``{dot.path}`` — deep value lookup
        - ``'literal'`` or ``"literal"`` — quoted string literal
        - plain string — passthrough
        """
        expr = expr.strip()

        if expr.startswith("$"):
            raise SkillLoadError(
                "$func() syntax is deprecated (F006). "
                "Use setup phase (requires_llm: false) + script tools instead."
            )
        if expr.startswith("{") and expr.endswith("}"):
            path = expr[1:-1].strip()
            return _deep_get(inputs, path.split("."))
        if len(expr) >= 2 and expr[0] in ("'", '"') and expr[-1] == expr[0]:
            return expr[1:-1]
        return expr


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _deep_get(obj: Any, keys: list[str]) -> Any:
    """Navigate a nested dict/object by a list of keys.

    Example: ``_deep_get({"a": {"b": 1}}, ["a", "b"])`` → ``1``
    """
    if len(keys) > _MAX_CONTEXT_PATH_DEPTH:
        raise SkillLoadError(
            f"context_mapping path depth {len(keys)} exceeds max {_MAX_CONTEXT_PATH_DEPTH}"
        )

    for key in keys:
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(key)
            continue
        if isinstance(obj, _SCALAR_TYPES):
            return None
        obj = getattr(obj, key, None)
    return obj
