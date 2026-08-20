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

from collections.abc import Mapping, MutableMapping
from typing import Any

__all__ = ["account_llm_call", "fold_spend", "spend_of", "token_usage_of"]


def account_llm_call(
    metrics: MutableMapping[str, Any],
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Add one LLM round-trip's usage to a run's running metrics."""
    metrics["total_input_tokens"] = int(metrics.get("total_input_tokens", 0)) + input_tokens
    metrics["total_output_tokens"] = int(metrics.get("total_output_tokens", 0)) + output_tokens


def fold_spend(into: MutableMapping[str, Any], spend: Mapping[str, Any]) -> None:
    """Add one worker's own counters into a running total.

    These metrics are counters — they only ever go up, and the only correct way
    to combine two workers' counters is to add them. That is why every producer
    reports what IT spent rather than the total it inherited: increments can be
    summed across siblings and across nesting levels, inherited totals cannot
    (adding two of them counts the shared base twice). The discipline is the
    G-Counter's, and the same one LangGraph applies to an
    ``Annotated[int, operator.add]`` channel; what this repo cannot borrow is
    the channel itself, because a batch item is invoked as a plain function
    call and never writes to a channel at all.

    A non-numeric value is not a counter, so it is carried across rather than
    added — an entry that does not belong in a counter map must not be silently
    turned into arithmetic.
    """
    for key, value in spend.items():
        current = into.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            into[key] = value
            continue
        if isinstance(current, bool) or not isinstance(current, int | float):
            into[key] = value
            continue
        into[key] = current + value


def spend_of(state: Any) -> dict[str, Any]:
    """Read ``flow.metrics`` off a graph state or a channel delta.

    The flow channel is a Pydantic model in a live state and a plain dict in a
    delta, and a caller harvesting a discarded child state may be handed either.
    """
    flow = state.get("flow") if hasattr(state, "get") else None
    if flow is None:
        return {}
    metrics = flow.get("metrics") if isinstance(flow, dict) else getattr(flow, "metrics", None)
    return dict(metrics) if isinstance(metrics, dict) else {}


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
