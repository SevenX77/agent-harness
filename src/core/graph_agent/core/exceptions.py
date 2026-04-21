"""Graph agent exception hierarchy.

All exceptions raised by the graph_agent package inherit from GraphAgentError,
allowing callers to catch the entire family with a single except clause.
"""

from __future__ import annotations


class GraphAgentError(Exception):
    """Base exception for all graph engine errors."""


class SkillLoadError(GraphAgentError):
    """Raised when a SKILL.md file cannot be parsed or validated."""


class SkillCompilationError(GraphAgentError):
    """Raised when a SKILL.md fails static compilation checks (FATAL rules)."""

    def __init__(self, message: str, compile_result: object = None) -> None:
        """Store compiler output alongside the surfaced error message."""
        self.compile_result = compile_result
        super().__init__(message)


# 预留：当前模板渲染错误在 harness 内部 fallback 处理。保留供严格模式使用。
class TemplateRenderError(GraphAgentError):
    """Raised when a user_prompt_template references a missing context key."""

    def __init__(self, missing_key: str, available_keys: list[str]) -> None:
        """Capture the missing placeholder and available context keys."""
        self.missing_key = missing_key
        self.available_keys = available_keys
        super().__init__(
            f"Template references key '{missing_key}' which is not in context. "
            f"Available keys: {available_keys}"
        )


class AllProvidersFailedError(GraphAgentError):
    """Raised when all providers in a tier have failed."""

    def __init__(self, tier: str, errors: list[tuple[str, Exception]]) -> None:
        """Capture the failing tier and per-provider error list."""
        self.tier = tier
        self.errors = errors
        details = "; ".join(f"{name}: {err}" for name, err in errors)
        super().__init__(f"All providers failed for tier '{tier}': {details}")


# 预留：当前 harness 内部处理 retry 超限，未向上抛出。保留供外部集成使用。
class MaxRetriesExceededError(GraphAgentError):
    """Informational: a phase exceeded its max retry count (workflow continues)."""

    def __init__(self, phase_name: str, max_retries: int) -> None:
        """Capture the phase name and configured retry ceiling."""
        self.phase_name = phase_name
        self.max_retries = max_retries
        super().__init__(
            f"Phase '{phase_name}' exceeded max retries ({max_retries}). "
            f"Continuing with validation warnings."
        )
