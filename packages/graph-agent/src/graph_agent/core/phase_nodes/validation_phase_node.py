"""``ValidationPhaseNode`` — standalone validator routing.

PHASE3_DESIGN.md §2.2 isolates the legacy
``PhaseExecutor.execute_validation_phase`` flow into a focused class.
Behaviour and retry semantics match the pre-M6 implementation
verbatim; only the surrounding plumbing now lives on a polymorphic
``PhaseNode`` subclass.
"""

from __future__ import annotations

import logging

from ..state import StateManager, WorkflowState
from ..types import Phase
from .base import PhaseNode

logger = logging.getLogger(__name__)


class ValidationPhaseNode(PhaseNode):
    """Run the phase's validator and emit retry / pass state updates.

    Control-flow shape (preserved verbatim from
    ``PhaseExecutor.execute_validation_phase``):

      * no ``phase.validator`` → clone and return unchanged
      * validator returns ``(True, ...)`` → pop the phase's retry
        bucket, clear validation warnings, emit
        ``ValidationPassEvent`` with the pre-pop retry count
      * validator returns ``(False, errors)`` →
        - fire ``on_validation_fail(phase, errors, current_retries)``
        - if ``current_retries >= max_retries``: emit
          ``RetryExhaustedEvent``, set framework validation warnings
        - else: set framework retry feedback, increment the retry
          bucket, fire ``on_retry(phase, target, errors)``

    Retry bucket key is ``phase.retry_target or phase.name`` on both
    the pass and fail paths — the same rule as the pre-refactor code.
    """

    def execute(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        from ...callbacks.events import RetryExhaustedEvent, ValidationPassEvent
        from ..harness import _clone_state, _safe_emit_event  # lazy: avoid import cycle

        next_state = _clone_state(state)
        if next_state["flow"].validation_middleware_phase == phase.name:
            # LLM phase validators have already run inside CognitiveFlowMiddleware
            # (Phase 3 M7 retired the legacy parallel pipeline), keeping rejected
            # finish_task submissions in the same agent loop instead of
            # restarting the whole phase through retry_target routing.
            return StateManager.update_framework(next_state, validation_middleware_phase=None)

        if phase.validator is None:
            return next_state

        passed, errors_raw = phase.validator(next_state["data"])
        raw_errors: object = errors_raw
        if isinstance(raw_errors, str):
            logger.warning(
                "phase=%s validator returned str instead of list[str]; "
                "coercing to single-element list. Update validator to "
                "match Callback.on_retry / RetryEvent.feedback contract.",
                phase.name,
            )
            errors = [raw_errors] if raw_errors else []
        elif isinstance(raw_errors, list):
            errors = [str(error) for error in raw_errors]
        else:
            logger.warning(
                "phase=%s validator returned %s instead of list[str]; coercing.",
                phase.name,
                type(raw_errors).__name__,
            )
            errors = [str(raw_errors)] if raw_errors else []
        retry_key = phase.retry_target or phase.name

        retry_counts = dict(next_state["flow"].retry_counts)
        if passed:
            retries_used = retry_counts.get(retry_key, 0)
            retry_counts.pop(retry_key, None)
            _safe_emit_event(
                self.container.callbacks,
                ValidationPassEvent(
                    phase_name=phase.name,
                    retry_count=retries_used,
                ),
            )
            next_state = StateManager.update_framework(
                next_state,
                retry_counts=retry_counts,
                retry_feedback=None,
                validation_warnings=[],
            )
            # MVP-2 T7-bis: validator-pass is a phase-exit signal too —
            # apply declarative io.outputs hoist here so a phase that
            # only declares ``io.outputs`` on the validation node still
            # routes BusinessData.
            return self._apply_io_hoist(next_state, phase)

        current_retries = retry_counts.get(retry_key, 0)
        for cb in self.container.callbacks:
            cb.on_validation_fail(phase.name, errors, current_retries)

        if current_retries >= phase.max_retries:
            logger.warning(
                "Phase '%s' exceeded max retries (%d). Continuing with warnings.",
                phase.name,
                phase.max_retries,
            )
            _safe_emit_event(
                self.container.callbacks,
                RetryExhaustedEvent(
                    phase_name=phase.name,
                    max_retries=phase.max_retries,
                    final_errors=list(errors),
                ),
            )
            return StateManager.update_framework(
                next_state,
                retry_counts=retry_counts,
                retry_feedback=None,
                validation_warnings=errors,
            )

        retry_counts[retry_key] = current_retries + 1

        for cb in self.container.callbacks:
            cb.on_retry(phase.name, retry_key, errors)

        return StateManager.update_framework(
            next_state,
            retry_counts=retry_counts,
            retry_feedback=errors,
        )


__all__ = ["ValidationPhaseNode"]
