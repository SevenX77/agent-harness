"""There is one finish_task path, and these symbols are not on it.

``CognitiveFlowMiddleware`` carried a second, complete finish_task pipeline —
``handle_finish_task_tool_result`` plus the static gate
(``validate_finish_task_with_schema_gate``) and validator adapter
(``invoke_validator_with_contract``) it called. Nothing in ``src/`` called it.
Its one call site lived in the hand-rolled tool-execution loop in
``graph_assembler.py`` and went away with that loop in ``3edd12d0``
(WS-E1 step 1, the move to ``create_agent``, 2026-06-07); the handler itself was
left behind. Only tests reached it after that (ledger E19).

Two reasons this was worse than ordinary dead code:

1. It read as a live retry mechanism. ``invoke_validator_with_contract`` takes
   the *real* phase-validator signature and, on rejection, builds a ToolMessage
   telling the model to redo the work — so a reader reasonably concludes that a
   rejected phase validator sends the model back for another try. It does not,
   and it never did from here: the sole caller passed ``validator=None``
   literally, which returns accepted before the validator is ever consulted.
   Building the ledger's E16 row started from exactly this misreading.
2. Design has since ruled the other way. CG4 (cognitive alignment) puts the
   phase's business rules in its sibling ``validator.py``, run by
   ``PhaseWrapper`` after the phase body and **fatally, with no bounce back to
   the model** — and gives the reason for refusing the retry shape: one declared
   validator would otherwise have two call sites with two meanings.

Nothing was lost by deleting it. The live path — ``wrap_tool_call`` →
``_handle_finish_task`` → ``_validate_finish_args`` — checks the same schema and
does strictly more (duplicate-submission detection, verdict narration, io hoist),
and both rules the deleted gate's tests pinned are pinned there too:
``test_cognitive_flow.py::TestFinishTask::test_finish_rejects_schema_validation_errors``
and ``::test_finish_without_schema_raises_phase_2_a1``.
"""

from __future__ import annotations

import graph_agent.middleware.cognitive_flow as cognitive_flow
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware

#: Methods of the second pipeline, and the module-level helpers only it reached.
RETIRED = (
    "handle_finish_task_tool_result",
    "validate_finish_task_with_schema_gate",
    "invoke_validator_with_contract",
    "FinishTaskSchemaGateResult",
    "ValidatorRuntimeResult",
    "_schema_gate_reject",
    "_validator_runtime_reject",
    "_finish_task_accept_response",
    "_has_strict_output_schema",
    "_coerce_output_schema",
    "_parse_finish_task_output_payload",
)


def test_the_second_finish_task_pipeline_is_gone() -> None:
    surviving = [
        name
        for name in RETIRED
        if hasattr(CognitiveFlowMiddleware, name) or hasattr(cognitive_flow, name)
    ]
    assert not surviving, (
        f"{surviving} came back. A finish_task path that only tests call is not "
        "'available for later' — it is a second answer to how a submission is "
        "judged, and readers believe it (E19). If one of these is needed again, "
        "it needs a live call site in src/, not a test-only resurrection."
    )


def test_the_live_finish_path_is_still_wired() -> None:
    """The other half of the claim: deleting the dead one left the real one."""
    for name in ("wrap_tool_call", "_handle_finish_task", "_validate_finish_args"):
        assert hasattr(CognitiveFlowMiddleware, name), (
            f"{name} is how finish_task is actually judged; if it is gone, this "
            "test file is asserting the absence of everything"
        )
