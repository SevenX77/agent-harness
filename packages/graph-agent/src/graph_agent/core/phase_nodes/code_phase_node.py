"""``CodePhaseNode`` — synchronous code-only phase execution.

PHASE3_DESIGN.md §2.2 specialises the legacy
``PhaseExecutor.execute_code_only_phase`` into a focused class. The
behaviour is identical to the pre-M6 method — including the Phase 2
A3 reserved-key + Pydantic-validate dict-merge contract on tool
returns — only the surrounding plumbing now lives on a polymorphic
``PhaseNode`` subclass.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from ..state import StateManager, WorkflowState
from ..types import Phase
from .base import PhaseNode

logger = logging.getLogger(__name__)


class CodePhaseNode(PhaseNode):
    """Run a code-only phase (``requires_llm=False``).

    Tools are invoked sequentially as plain callables receiving
    ``BusinessData``. A tool that returns a string updates framework
    ``last_output``; one returning a dict has it merged into
    ``BusinessData`` (Phase 2 A3, see
    :meth:`_merge_code_phase_tool_result`); retry feedback is cleared
    through ``FrameworkState``.
    """

    def execute(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        from ..harness import _clone_state  # lazy: avoid import cycle at module load

        next_state = _clone_state(state)
        for cb in self.container.callbacks:
            cb.on_phase_start(phase.name, next_state["data"].model_dump())

        if phase.tools:
            logger.info(
                "[CodeOnly] Executing %d tool(s) for phase=%s",
                len(phase.tools),
                phase.name,
            )
            for fn in phase.tools:
                result = fn(next_state["data"])
                next_state = self._merge_code_phase_tool_result(
                    phase, next_state, result, fn=fn,
                )

        next_state = StateManager.update_framework(
            next_state,
            current_phase=phase.name,
            retry_feedback=None,
            validation_warnings=[],
        )

        # MVP-2 T7-bis: apply declarative io.outputs hoist for code-only
        # phases. Source is the live BusinessData dump because tools mutate
        # ``state['data']`` directly during the loop above and there is
        # no finish_task_result on this code path.
        next_state = self._apply_io_hoist(
            next_state,
            phase,
            source_data=next_state["data"].model_dump(),
        )

        for cb in self.container.callbacks:
            cb.on_phase_end(
                phase.name,
                next_state["data"].model_dump(),
                next_state["flow"].metrics,
            )
        return next_state

    def _merge_code_phase_tool_result(
        self,
        phase: Phase,
        state: WorkflowState,
        result: object,
        *,
        fn: Callable[..., object],
    ) -> WorkflowState:
        """Phase 2 A3: explicit handling of a code-only tool's return value.

        Earlier revisions silently dropped any tool return that was not a
        ``str`` — including ``dict`` payloads carrying business fields the
        tool meant to merge into the next state. That violates the
        framework's "fail-loud" rule because the dropped fields would be
        invisible to the rest of the pipeline. PHASE2_DESIGN.md §4.2 / §4.4
        specify the new contract:

        * ``str`` result → set ``flow.last_output`` (legacy behaviour).
        * ``dict`` result → merge into ``BusinessData`` via
          ``StateManager.update_business``. **Reserved-key check (any
          ``_``-prefixed key) must run on the raw returned dict BEFORE
          Pydantic validation** — Pydantic's default ``extra='ignore'``
          would otherwise silently drop ``_metrics`` / ``_phase_internal``
          and the reserved-key check would never see them. After the
          reserved-key gate passes, ``phase.output_schema`` (if set) runs
          a Pydantic validate to normalise the dict into the declared
          shape.
        * Other values (``None`` / ``list`` / ``int`` / ...) → no state
          change. Code-only tools that need side effects on
          ``BusinessData`` should mutate the passed-in instance directly
          (covered by the existing IO-hoist path).

        Args:
            phase: The currently executing code-only phase.
            state: The workflow state cloned by the caller.
            result: The tool's return value, typed ``object`` per
                PHASE2_DESIGN.md §4.4. Real shape is
                inspected via ``isinstance`` checks below.
            fn: The tool callable; used to surface ``__name__`` in
                log records and error messages so operators can identify
                the offending tool. Typed ``Callable[..., object]`` per
                §4.4.

        Returns:
            The next ``WorkflowState`` after applying the result. ``str``
            updates ``flow.last_output``; ``dict`` updates ``data``
            fields via ``update_business``; other types pass through.

        Raises:
            RuntimeError: When ``result`` is a dict whose keys include
                any framework-reserved (``_``-prefixed) entry.
            pydantic.ValidationError: When ``phase.output_schema`` is
                set and the dict fails Pydantic validation. Propagated
                so callers see the precise field-level diagnostic.
        """
        if isinstance(result, str):
            return StateManager.update_framework(state, last_output=result)
        if not isinstance(result, dict):
            return state

        fn_name = getattr(fn, "__name__", repr(fn))
        # Treat the returned dict as ``dict[str, object]`` — keys are the
        # business field names the tool wants merged, values are arbitrary
        # business payloads we forward verbatim through ``update_business``.
        raw: dict[str, object] = result

        # ---- Step 1: reserved-key check on the RAW dict ------------------
        # PHASE2_DESIGN.md §4.4: this MUST run before Pydantic validation.
        # ``extra='ignore'`` (Pydantic's default) would silently drop any
        # ``_metrics`` / ``_phase_internal`` injection before we ever see
        # them, so a post-validate scan misses the attack entirely (a1 v1
        # NO_RAISE probe). Inspecting the raw dict closes that hole.
        invalid_keys = sorted(
            k for k in raw if isinstance(k, str) and k.startswith("_")
        )
        if invalid_keys:
            logger.error(
                "phase=%s action=code_only_dict_merge decision=reject "
                "tool=%s reason=reserved_keys keys=%s",
                phase.name,
                fn_name,
                invalid_keys,
            )
            raise RuntimeError(
                f"Code-only phase {phase.name!r} tool {fn_name!r} returned a "
                f"dict containing framework-reserved keys (any key starting "
                f"with '_' is owned by FrameworkState and must be written via "
                f"StateManager.update_framework, never returned from a tool): "
                f"{invalid_keys}. Phase 2 A3 contract: code-only phases that "
                f"need to set framework metadata must do so explicitly through "
                f"update_framework instead of returning '_'-prefixed keys."
            )

        # ---- Step 2: Pydantic validation (only after reserved-key gate) --
        merged: dict[str, object] = raw
        if phase.output_schema is not None:
            schema_cls = phase.output_schema
            try:
                validated = schema_cls.model_validate(merged)
            except Exception as exc:
                logger.error(
                    "phase=%s action=code_only_dict_validate decision=fail "
                    "tool=%s schema=%s reason=%s",
                    phase.name,
                    fn_name,
                    schema_cls.__name__,
                    type(exc).__name__,
                )
                raise
            merged = validated.model_dump()
            logger.info(
                "phase=%s action=code_only_dict_validate decision=pass "
                "tool=%s schema=%s fields=%d",
                phase.name,
                fn_name,
                schema_cls.__name__,
                len(merged),
            )

        # ---- Step 3: merge into BusinessData ----------------------------
        logger.info(
            "phase=%s action=code_only_dict_merge decision=apply "
            "tool=%s fields=%d",
            phase.name,
            fn_name,
            len(merged),
        )
        return StateManager.update_business(state, **merged)


__all__ = ["CodePhaseNode"]
