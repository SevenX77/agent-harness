"""One definition of how to read what an LLM call cost.

Providers do not agree on where usage lives or what to call it, so reading it
is a small search rather than one lookup. That search lives here, in one place,
because a second copy of it is a second answer to what a call cost.

Adding those costs up is NOT here, and no longer happens in graph state at all
(OB10): a run's total is accumulated on its event sink as each call reports
itself (``callbacks/emit._RunSpendLedger``). Counting from a finished graph
state could only ever describe the branch that survived the channel.
"""

from __future__ import annotations

from typing import Any

__all__ = ["token_usage_of"]


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
