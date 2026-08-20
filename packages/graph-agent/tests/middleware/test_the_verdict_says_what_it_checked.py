"""The finish_task verdict names the checks that ran, and only those.

Field evidence (2026-08-20, run ``2026-08-20T15-44-03_98726d7c``): the verdict
read "1 item(s) passed schema and **business validation**", and the very next
thing that happened was the phase's own ``validator.py`` rejecting that same
submission and killing the run with ``[F-v3-agent-validator-failed]``. Both
sentences cannot be true about one payload (ledger E16).

They were never both true. The gate's ``business_validator`` hook has no
supplier on the live path — the one caller that ever passed one
(``business_validator=phase.validator``) was deleted with the legacy execution
family in #810 — so on every run the message named a check that structurally
could not have happened. The phase's real validator is the sibling
``validator.py``, whose contract lives in ``core/validator_contract.py``
(``def validate(output: dict, state_slice: dict, **kwargs)``, fatal
``[F-v3-*-validator-failed]``) and which ``PhaseWrapper`` runs after the phase
body, outside this gate entirely.

So the fix is not to run something here — it is to stop claiming it. What the
finish gate checks is the schema, per item, and that is what it now says.
"""

from __future__ import annotations

from typing import Any

from graph_agent.core.io_manager import IODef, IOManager
from graph_agent.core.schema_engine import SchemaEngine
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware

from .test_cognitive_flow import VALID_BUSINESS_MD, _handler, _request


class _Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


def _accepted_verdict() -> Any:
    recorder = _Recorder()
    engine = SchemaEngine()
    middleware = CognitiveFlowMiddleware(
        IOManager([IODef(source_field="business_data_parsed", target_field="items")]),
        schema_engine=engine,
        current_phase_schema=engine.parse_from_md("title: str\nscore: int"),
        phase_name="segment",
        callbacks=(recorder,),
    )

    middleware.wrap_tool_call(
        _request(
            name="finish_task",
            args={
                "reasoning": "done",
                "diagnostics_md": "ok",
                "business_data_md": VALID_BUSINESS_MD,
            },
        ),
        _handler,
    )

    verdicts = [e for e in recorder.events if getattr(e, "event_type", "") == "finish_task_verdict"]
    assert len(verdicts) == 1, f"expected exactly one verdict, got {len(verdicts)}"
    assert verdicts[0].verdict == "accepted"
    return verdicts[0]


def test_an_accepted_verdict_does_not_claim_a_check_that_never_ran() -> None:
    message = _accepted_verdict().message.lower()

    assert "business validation" not in message, (
        "the finish gate runs no business validation, so saying it passed one "
        f"is a sentence about nothing; got: {message}"
    )
    assert "schema" in message, f"say what it DID check, not merely that it passed: {message}"


def test_the_story_lists_the_stages_that_ran_and_no_others() -> None:
    """The step-by-step narration answers the same question as the message.

    Two answers to one question is the defect this whole row is about, so the
    story cannot keep a business-validator step after the message drops it —
    a reader who opened the details would come away believing the summary was
    the abbreviated one, rather than the corrected one.
    """
    joined = " ".join(_accepted_verdict().details).lower()

    assert "md2json" in joined, "step one: md2json parsed the markdown"
    assert "schema" in joined, "step two: each block checked against the schema"
    assert "business validator" not in joined, (
        f"nothing here consults a business validator any more; got: {joined}"
    )
