"""NudgeInjector — per-phase cognitive-nudge state machine + policy.

Extracted from the while-loop of ``GraphAgentHarness._build_phase_node``
(L1146-L1378 before the extract) as D-7.4 of the harness-split.

Runtime collaborator — a fresh instance is created each time the phase's
execute closure is entered, so the counters are scoped to a single phase
execution (matching the lifetime of the pre-refactor local counters).

Design notes (Gemini-reviewed 2026-04-24):
  - Option β (behaviour wrapper): each ``try_*`` returns a ``NudgeOutcome``
    that tells the caller whether to inject a nudge message and whether the
    condition was hit but budget was exhausted. The caller keeps outer
    control flow (continue / break / plan_verified flag) since those depend
    on state not owned by NudgeInjector.
  - ``_has_structured_selfcheck`` is private here: it serves only the
    selfcheck branch and is not reused elsewhere.
  - Accepts an explicit ``callbacks`` list rather than RunContext: the
    pre-refactor code fired nudge callbacks onto ``harness.callbacks``
    only (a subtly smaller scope than ``RunContext.callbacks``, which also
    includes subgraph-forwarded ``extra_callbacks``). Preserving the
    narrower scope is strictly behaviour-preserving; widening it can be
    revisited once an E2E baseline catches regressions.
  - Planning and standard gates preserve the legacy increment-before-check
    quirk — see the FIXME on ``_consume_after_increment``. This costs one
    bookkeeping wart but guarantees byte-for-byte behaviour equivalence
    with the pre-refactor loop (validated by a counterexample in the D-7.4
    Gemini debate, 2026-04-24).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.messages import HumanMessage

from ..callbacks.base import Callback
from ..cognitive.finish import (
    MIN_FINISH_REASONING_LEN,
    PLANNING_NUDGE,
    SELFCHECK_NUDGE,
    build_standard_nudge_text,
)
from .types import Phase

logger = logging.getLogger(__name__)

NudgeKind = Literal["planning", "selfcheck", "standard"]


@dataclass(frozen=True)
class NudgeOutcome:
    """Result of a single ``try_*`` call.

    Attributes
    ----------
    message:
        HumanMessage to append to the LLM conversation, or ``None`` when
        the caller should not inject anything.
    budget_exhausted:
        ``True`` only when the triggering condition was met but a budget
        gate blocked the injection. ``False`` in every other "no message"
        case (condition unmet, or payload already satisfies selfcheck).
        Only the standard-nudge caller currently branches on this flag —
        it logs an "exceeded max_nudges" warning specifically when the
        condition was hit but budget ran out.
    """

    message: HumanMessage | None
    budget_exhausted: bool


class NudgeInjector:
    """Encapsulate nudge policy + counter state for one phase execution."""

    def __init__(self, phase: Phase, callbacks: list[Callback]) -> None:
        self._phase = phase
        self._callbacks = callbacks
        self._planning = 0
        self._selfcheck = 0
        self._standard = 0
        self._total = 0

    # ----- public gates ------------------------------------------------

    def try_selfcheck(self, finish_payload: dict[str, Any]) -> NudgeOutcome:
        """Decide whether to nudge because the finish_task payload is thin.

        Check-before-increment: if either budget gate fails, no counters
        advance. This matches the legacy behaviour for the selfcheck
        branch (``selfcheck_nudge_count < max_nudges`` in the pre-refactor
        loop) and contrasts with ``try_planning`` / ``try_standard`` below.
        """
        if finish_payload.get("schema_validation") == "failed":
            error_text = finish_payload.get(
                "validation_error_text",
                "Schema validation failed.",
            )
            return NudgeOutcome(
                message=HumanMessage(content=str(error_text)),
                budget_exhausted=False,
            )

        if self._has_structured_selfcheck(finish_payload):
            return NudgeOutcome(message=None, budget_exhausted=False)
        if (
            self._selfcheck < self._phase.max_nudges
            and self._total < self._phase.max_nudges * 2
        ):
            self._selfcheck += 1
            self._total += 1
            self._emit("selfcheck", self._selfcheck)
            return NudgeOutcome(
                message=HumanMessage(content=SELFCHECK_NUDGE),
                budget_exhausted=False,
            )
        return NudgeOutcome(message=None, budget_exhausted=True)

    def try_planning(self, latest_content: str, *, has_tool_calls: bool) -> NudgeOutcome:
        """Decide whether to nudge the LLM to produce a plan first.

        Triggering condition: text output present without any tool calls
        (and working-memory hasn't been updated yet — the caller is
        expected to guard on ``plan_verified`` / ``wm_updated`` before
        calling this method, matching the pre-refactor branch structure).
        """
        if not latest_content or has_tool_calls:
            return NudgeOutcome(message=None, budget_exhausted=False)
        if self._consume_after_increment("planning"):
            self._emit("planning", self._planning)
            return NudgeOutcome(
                message=HumanMessage(content=PLANNING_NUDGE),
                budget_exhausted=False,
            )
        return NudgeOutcome(message=None, budget_exhausted=True)

    def try_standard(self, latest_content: str, *, has_tool_calls: bool) -> NudgeOutcome:
        """Generic "don't just talk — use tools or finish" nudge.

        Escalating text via ``build_standard_nudge_text(count, latest)``
        so each retry nudges progressively more firmly.
        """
        if not latest_content or has_tool_calls:
            return NudgeOutcome(message=None, budget_exhausted=False)
        if self._consume_after_increment("standard"):
            self._emit("standard", self._standard)
            text = build_standard_nudge_text(self._standard, latest_content)
            return NudgeOutcome(
                message=HumanMessage(content=text),
                budget_exhausted=False,
            )
        return NudgeOutcome(message=None, budget_exhausted=True)

    # ----- observation -------------------------------------------------

    def counts(self) -> dict[str, int]:
        """Return counter snapshot for tests / diagnostics."""
        return {
            "planning": self._planning,
            "selfcheck": self._selfcheck,
            "standard": self._standard,
            "total": self._total,
        }

    # ----- private helpers ---------------------------------------------

    def _consume_after_increment(self, kind: Literal["planning", "standard"]) -> bool:
        """Increment the per-kind + total counter, then test budget.

        FIXME(Legacy Quirk): this preserves the pre-refactor behaviour where
        a failed-budget call still bumps both ``{kind}_nudge_count`` and
        ``total_nudge_count``. Consequence: a condition hit + budget miss
        on planning/standard still consumes one unit of the global
        ``total_nudge_count < max_nudges * 2`` cap, which can block later
        cross-type injections (observed: max_nudges=1 with selfcheck +
        planning sequence — the planning's quirky total bump prevents the
        follow-up standard from firing). Do NOT "simplify" this to
        check-before-increment without an E2E golden baseline pass —
        verified divergent in the D-7.4 Gemini debate on 2026-04-24.
        """
        if kind == "planning":
            self._planning += 1
            counter_ok = self._planning <= self._phase.max_nudges
        else:
            self._standard += 1
            counter_ok = self._standard <= self._phase.max_nudges
        self._total += 1
        return counter_ok and self._total < self._phase.max_nudges * 2

    def _emit(self, kind: NudgeKind, count_after: int) -> None:
        """Fire ``on_nudge`` across all callbacks, with the legacy TypeError fallback.

        Legacy callbacks (pre-``nudge_type`` kwarg) raise ``TypeError`` when
        called with the kwarg; we retry positional-only. Any other callback
        exception is absorbed with a warning log so a misbehaving observer
        cannot derail the cognitive loop.
        """
        for cb in self._callbacks:
            try:
                cb.on_nudge(self._phase.name, count_after, nudge_type=kind)
            except TypeError:
                try:
                    cb.on_nudge(self._phase.name, count_after)
                except Exception as exc:
                    logger.warning('[NudgeInjector] callback error: %s', exc)
            except Exception as exc:
                logger.warning('[NudgeInjector] callback error: %s', exc)

    def _has_structured_selfcheck(self, payload: dict[str, Any]) -> bool:
        """True iff finish_task payload meets the structured-selfcheck bar.

        Accepted when either structured business output has passed schema
        validation, diagnostics are substantive, or the minimal no-schema
        completion text is substantive. Validation failures are intercepted
        earlier in ``try_selfcheck``.
        """
        schema_status = payload.get("schema_validation")
        business_data_md = str(payload.get("business_data_md", "")).strip()
        if business_data_md and schema_status == "passed":
            return True

        diagnostics_md = str(payload.get("diagnostics_md", "")).strip()
        if len(diagnostics_md) >= MIN_FINISH_REASONING_LEN:
            return True

        reasoning_text = str(payload.get("reasoning", "")).strip()
        return len(reasoning_text) >= MIN_FINISH_REASONING_LEN
