"""Which questions a route is worth asking, and what a set of answers settles.

Two things are provider knowledge and belong here rather than in whatever app
happens to press the button: which candidate values are worth a request at all,
and what a batch of answers means once they are in. The app still owns whether
it is allowed to ask right now and how it tells its user — it passes in the
function that does the asking.

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md
D5 §"P4 开工补记" (fact 1: the question list and the answer vocabulary already
lived here; only "how to ask, and what counts as answered" was left behind).
"""

from __future__ import annotations

import asyncio

from graph_agent_gateway.probing import (
    EFFORT_CONTROL_LEVEL,
    Question,
    RouteProbeResult,
    accepted_effort_levels,
    ask_each,
    effort_questions,
)


def _result(status: str) -> RouteProbeResult:
    return RouteProbeResult(
        endpoint_id="vendor",
        route_id="vendor:thinker",
        provider_kind="third_party",
        backend="openai",
        base_url="https://vendor.example/v1",
        model_id="thinker",
        status=status,  # type: ignore[arg-type]
        message=None if status == "ok" else status,
    )


def test_a_protocol_that_pins_its_vocabulary_is_only_asked_about_that() -> None:
    """Naming a level Gemini's body cannot spell spends a request to be told so."""
    asked = [question.value for question in effort_questions("google_genai")]

    assert asked == ["minimal", "low", "medium", "high", EFFORT_CONTROL_LEVEL]


def test_a_protocol_that_pins_nothing_is_asked_the_whole_ladder() -> None:
    """OpenAI's set moves between model versions, so no document settles it."""
    asked = [question.value for question in effort_questions("openai_compatible")]

    assert asked == [
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
        EFFORT_CONTROL_LEVEL,
    ]


def test_every_batch_carries_a_level_no_route_could_sell() -> None:
    """Without it, acceptance and indifference produce the same answer.

    A provider that validates nothing takes every level it is handed, so a list
    of accepted levels alone cannot say which of the two happened.
    """
    for protocol in ("google_genai", "openai_compatible", "anthropic_compatible"):
        asked = [question.value for question in effort_questions(protocol)]  # type: ignore[arg-type]
        assert asked[-1] == EFFORT_CONTROL_LEVEL
        assert asked.count(EFFORT_CONTROL_LEVEL) == 1


def test_a_question_carries_the_settings_that_ask_it() -> None:
    question = effort_questions("openai_compatible")[2]

    assert question.runtime_settings == {"reasoning": {"enabled": True, "effort": "low"}}


def test_the_levels_a_route_accepted_are_the_ones_that_answered_ok() -> None:
    questions = effort_questions("google_genai")
    answers = [
        _result("ok"),
        _result("invalid_model"),
        _result("ok"),
        _result("invalid_model"),
        _result("invalid_model"),  # the control, refused — this route checks the value
    ]

    assert accepted_effort_levels(zip(questions, answers, strict=True)) == ("minimal", "medium")


def test_a_route_that_takes_a_level_that_does_not_exist_settles_nothing() -> None:
    """Taking every level including the invented one is indifference, not support.

    Live 2026-08-11: deepseek-v4-pro accepted all seven levels, `none` and `max`
    among them. A provider that never validates the field answers exactly that
    way, so the list said nothing about what the model actually sells.
    """
    questions = effort_questions("openai_compatible")
    answers = [_result("ok")] * len(questions)

    assert accepted_effort_levels(zip(questions, answers, strict=True)) is None


def test_the_control_is_never_recorded_as_a_level_the_route_sells() -> None:
    questions = effort_questions("google_genai")
    answers = [_result("ok"), _result("ok"), _result("ok"), _result("ok"), _result("invalid_model")]

    levels = accepted_effort_levels(zip(questions, answers, strict=True))

    assert levels == ("minimal", "low", "medium", "high")
    assert EFFORT_CONTROL_LEVEL not in (levels or ())


def test_one_inconclusive_answer_voids_the_whole_batch() -> None:
    """A rate limit says nothing about which levels the route sells.

    Recording it as a refusal would delete levels the route does support, so the
    batch produces no measurement at all rather than a partial one.
    """
    questions = effort_questions("google_genai")
    answers = [
        _result("ok"),
        _result("rate_limited"),
        _result("ok"),
        _result("ok"),
        _result("invalid_model"),  # the control
    ]

    assert accepted_effort_levels(zip(questions, answers, strict=True)) is None


def test_ask_each_pairs_every_answer_with_the_question_it_answered() -> None:
    """The pairing is the invariant: an answer read against the wrong question is worse than none."""
    questions = effort_questions("google_genai")
    seen: list[Question] = []

    async def ask(question: Question) -> RouteProbeResult:
        seen.append(question)
        # Answer out of order so a wrong implementation cannot pass by luck.
        await asyncio.sleep(0.01 if question.value == "minimal" else 0)
        return _result("ok" if question.value in {"low", "high"} else "invalid_model")

    answered = asyncio.run(ask_each(questions, ask))

    assert [question.value for question, _ in answered] == [
        "minimal",
        "low",
        "medium",
        "high",
        EFFORT_CONTROL_LEVEL,
    ]
    assert accepted_effort_levels(answered) == ("low", "high")
    assert len(seen) == len(questions)
