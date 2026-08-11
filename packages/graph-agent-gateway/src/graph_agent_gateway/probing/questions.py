"""Which questions a route is worth asking, and what a set of answers settles.

Two halves of asking a route something are provider knowledge and belong to the
gateway: **which candidate values are worth spending a request on**, and **what a
batch of answers means once they are all in**. The half that is not provider
knowledge — whether the app is allowed to ask right now, and how it tells its
user it is asking — stays with the app, which passes in the function that asks.

That seam is why `ask_each` takes an asker instead of calling the probe itself:
Studio wraps every ask with its own disabled-endpoint rule and its own
"probe active" event, and a runner that skipped those would either duplicate
them or quietly drop them.

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md
D1 (T2 is one capability with a depth parameter, not two) and D5's P4 note.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from graph_agent_gateway.registry import Protocol, effort_probe_candidates

from .results import RouteProbeResult

__all__ = [
    "INCONCLUSIVE_PROBE_STATUSES",
    "Answered",
    "Question",
    "accepted_effort_levels",
    "ask_each",
    "effort_questions",
]


@dataclass(frozen=True)
class Question:
    """One request worth spending, and the value it would settle.

    `value` is the candidate being tried — the effort level, and later the tool
    shape. It is carried alongside the settings rather than dug back out of them
    so that reading a batch of answers never has to re-parse what was asked.
    """

    value: str
    runtime_settings: Mapping[str, Any]


Answered = tuple[Question, RouteProbeResult]
"""One question and the answer to that same question.

Kept paired rather than as two parallel lists: an answer read against the wrong
question records a level the route never accepted, which is worse than recording
nothing at all.
"""


INCONCLUSIVE_PROBE_STATUSES: Final[frozenset[str]] = frozenset(
    {"rate_limited", "quota_exceeded", "network_error", "timeout", "invalid_key"}
)
"""Answers that say something about the moment, not about the route.

A rate limit is not a refusal of the value that was asked, so a batch containing
one cannot be read as "these levels are the ones it sells".
"""


def effort_questions(protocol: Protocol) -> tuple[Question, ...]:
    """The effort levels this protocol's route is worth being asked about.

    Bounded by the protocol's documented vocabulary where its API pins one, and
    the whole ladder where it pins nothing — the reasoning for that boundary
    lives with the vocabulary itself, in `registry.effort_probe_candidates`.
    """
    return tuple(
        Question(value=level, runtime_settings={"reasoning": {"enabled": True, "effort": level}})
        for level in effort_probe_candidates(protocol)
    )


async def ask_each(
    questions: Sequence[Question],
    ask: Callable[[Question], Awaitable[RouteProbeResult]],
    /,
) -> tuple[Answered, ...]:
    """Ask every question, and return each answer next to the question it answers.

    Concurrent, because the questions in a set are independent by construction —
    each one names a different candidate value and none depends on the others'
    outcome. The returned order is the order asked, whatever order they finished.
    """
    results = await asyncio.gather(*(ask(question) for question in questions))
    return tuple(zip(questions, results, strict=True))


def accepted_effort_levels(answered: Iterable[Answered]) -> tuple[str, ...] | None:
    """The levels this route accepted, or `None` when the batch settles nothing.

    A single inconclusive answer voids the whole batch rather than being read as
    a refusal: recording it as one would delete levels the route does sell, and a
    capability that quietly shrinks is worse than one that stays unmeasured.
    """
    pairs = tuple(answered)
    if any(result.status in INCONCLUSIVE_PROBE_STATUSES for _, result in pairs):
        return None
    return tuple(question.value for question, result in pairs if result.status == "ok")
