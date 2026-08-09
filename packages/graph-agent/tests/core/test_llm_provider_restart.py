"""A retried answer replaces the one before it; folding must agree.

A provider is not the only thing that can decide to answer again. The host
behind the Port retries too — a bigger budget after an answer was cut off, a
different route after one failed — and each retry produces a *different*
answer rather than more of the same one. The slices of the abandoned attempt
are therefore not part of the answer, and whoever folds slices back together
has to be told so explicitly.

Without that, the fold silently concatenates two attempts and hands the agent
loop a message no model ever wrote.
"""

from __future__ import annotations

from collections.abc import Iterator

from graph_agent.core.llm_provider import (
    LLMProviderChatModel,
    LLMProviderChunk,
    LLMProviderRequest,
)


class _RestartingProvider:
    """Answers once badly, voids it, then answers properly."""

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        del request
        yield LLMProviderChunk(
            content="cut off ha",
            metadata={"finish_reason": "length", "route_id": "the-route-that-was-abandoned"},
        )
        yield LLMProviderChunk(restarts_answer=True)
        yield LLMProviderChunk(content="the whole ")
        yield LLMProviderChunk(content="answer")
        yield LLMProviderChunk(metadata={"finish_reason": "stop"})


def _model(provider: object) -> LLMProviderChatModel:
    return LLMProviderChatModel(provider=provider, role="graph_agent", phase_name="draft")


def test_a_restart_leaves_no_trace_of_the_attempt_it_replaced() -> None:
    answer = _model(_RestartingProvider()).invoke([])

    assert answer.content == "the whole answer", "two attempts must never be spliced together"


def test_a_restart_also_voids_what_the_abandoned_attempt_claimed_about_itself() -> None:
    """Metadata is part of the answer: the abandoned attempt's is abandoned too."""
    answer = _model(_RestartingProvider()).invoke([])

    assert answer.response_metadata["finish_reason"] == "stop", (
        "reporting the voided attempt's finish_reason would describe an answer "
        "the caller never received"
    )
    assert "route_id" not in answer.response_metadata, (
        "the abandoned attempt's own claims must go with it, not just the ones "
        "the replacement happens to overwrite"
    )
