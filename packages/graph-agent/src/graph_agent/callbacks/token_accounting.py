"""One definition of how an LLM call adds to a run's token totals.

Both phase runtimes emit their own ``LLMCallEvent`` — the legacy LLM phase node
through ``_HarnessCallbackBridge``, the V4 agent node from the assembler — and a
run's totals are the fold of those calls. Keeping the fold in one place is what
stops the two paths from disagreeing about what a run cost.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

__all__ = ["account_llm_call"]


def account_llm_call(
    metrics: MutableMapping[str, Any],
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Add one LLM round-trip's usage to a run's running metrics."""
    metrics["total_input_tokens"] = int(metrics.get("total_input_tokens", 0)) + input_tokens
    metrics["total_output_tokens"] = int(metrics.get("total_output_tokens", 0)) + output_tokens
