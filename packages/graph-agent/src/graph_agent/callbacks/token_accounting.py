"""One definition of what an LLM call cost, and of how it adds to a run.

Both phase runtimes fold their calls into the same running totals — the legacy
LLM phase node through ``_HarnessCallbackBridge``, the V4 agent node from the
assembler — and keeping the reading and the fold in one place is what stops the
two paths from disagreeing about what a run cost.

Providers do not agree on where usage lives or what to call it, so reading it
is a small search rather than one lookup. That search belongs here, next to the
fold, for the same reason: a second copy of it is a second answer.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

__all__ = ["account_llm_call", "token_usage_of"]


def account_llm_call(
    metrics: MutableMapping[str, Any],
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Add one LLM round-trip's usage to a run's running metrics."""
    metrics["total_input_tokens"] = int(metrics.get("total_input_tokens", 0)) + input_tokens
    metrics["total_output_tokens"] = int(metrics.get("total_output_tokens", 0)) + output_tokens


def token_usage_of(answer: Any) -> tuple[int, int]:
    """Read ``(input_tokens, output_tokens)`` off one answer message."""
    metadata = getattr(answer, "response_metadata", None)
    usage = metadata.get("token_usage") if isinstance(metadata, dict) else None
    if not isinstance(usage, dict):
        usage = metadata.get("usage") if isinstance(metadata, dict) else None
    if not isinstance(usage, dict):
        usage = getattr(answer, "usage_metadata", None)
    if not isinstance(usage, dict):
        return 0, 0
    input_tokens = _coerce_token_count(
        usage.get("input_tokens", usage.get("prompt_tokens", usage.get("total_input_tokens")))
    )
    output_tokens = _coerce_token_count(
        usage.get(
            "output_tokens",
            usage.get("completion_tokens", usage.get("total_output_tokens")),
        )
    )
    return input_tokens, output_tokens


def _coerce_token_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0
