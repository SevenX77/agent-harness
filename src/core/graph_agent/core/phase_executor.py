"""PhaseExecutor — executes a single phase once (LLM / code-only / validation / subgraph).

Per-run collaborator: one instance is built inside each call to
``GraphAgentHarness.run()`` / ``.resume()`` and passed into the compiled
LangGraph via ``RunnableConfig["configurable"]["_phase_executor"]``.
The graph-node closures built by ``GraphBuilder`` extract it from the
config on each invocation and delegate to the appropriate ``execute_*``
method.

This wiring replaces the Phase-A ``self._harness`` back-reference + the
pre-D-7.2 ``harness._active_heartbeat`` / ``harness._active_run_context``
instance slots. Because each ``run()`` now owns a fresh PhaseExecutor on
the stack rather than on the harness instance, concurrent ``child.run()``
calls on the same child harness instance no longer share mutable
run-state — the race noted in the former ``subgraph.py`` FIXME is gone.

Design notes:
  - ``callbacks`` is kept explicit (not pulled from ``RunContext.callbacks``)
    to preserve the pre-refactor nudge-callback scope; see
    ``NudgeInjector``'s module docstring for the same reasoning.
  - ``resolver`` and ``save_compaction_sidecar`` are harness-lifetime
    objects that ``execute_llm_phase`` needs; ``run()`` injects them at
    construction so PhaseExecutor no longer needs any harness reference.
  - ``run_context`` and ``heartbeat`` are per-invocation; only
    ``execute_llm_phase`` reads them (code_only / validation phases are
    oblivious).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from ..callbacks.base import Callback
from ..cognitive.ambiguity import log_ambiguity
from ..cognitive.finish import finish_task
from ..cognitive.memory import update_working_memory
from ..cognitive.middlewares import ValidationMiddleware, create_custom_middlewares
from ..cognitive.prompt import (
    apply_cognitive_template,
    resolve_role_prefix_from_llm_role,
)
from .callback_bridge import _extract_text_content, _HarnessCallbackBridge
from .nudge_injector import NudgeInjector
from .run_context import RunContext
from .state import (
    StateManager,
    WorkflowState,
    legacy_context_from_state,
)
from .template import _render_user_prompt, _safe_render_template
from .tool_wrapper import _wrap_tool_for_langchain
from .tracing_proxy import TracingClientProxy
from .types import Phase

logger = logging.getLogger(__name__)

_AMBIGUITY_REPORTS_KEY = "_ambiguity_reports"
_FINISH_TASK_RESULT_KEY = "_finish_task_result"
_RETRY_FEEDBACK_KEY = "_retry_feedback"
_SKILL_BASE_DIR_KEY = "_skill_base_dir"
_VALIDATION_WARNINGS_KEY = "_validation_warnings"
_WORKING_MEMORY_KEY = "_working_memory"


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _tool_text(tool_state: dict[str, Any], key: str) -> str | None:
    return _as_text(tool_state.get(key))


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        return [value] if value else []
    return [str(value)] if value else []


def _tool_reports(tool_state: dict[str, Any]) -> list[dict[str, Any]]:
    raw = tool_state.get(_AMBIGUITY_REPORTS_KEY, [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _append_tool_warning(tool_state: dict[str, Any], warning: str) -> None:
    existing = tool_state.get(_VALIDATION_WARNINGS_KEY)
    if isinstance(existing, list):
        existing.append(warning)
        return
    if existing is None:
        tool_state[_VALIDATION_WARNINGS_KEY] = [warning]
        return
    tool_state[_VALIDATION_WARNINGS_KEY] = [str(existing), warning]


def _finish_result_from_tool_state(tool_state: dict[str, Any]) -> dict[str, Any] | None:
    value = tool_state.get(_FINISH_TASK_RESULT_KEY)
    return value if isinstance(value, dict) else None


def _sync_tool_state(
    state: WorkflowState,
    tool_state: dict[str, Any],
    *,
    messages: list[AnyMessage] | None = None,
) -> WorkflowState:
    business_fields = {k: v for k, v in tool_state.items() if not k.startswith("_")}
    next_state = state
    if business_fields:
        next_state = StateManager.update_business(next_state, **business_fields)

    flow_updates: dict[str, Any] = {}
    if _VALIDATION_WARNINGS_KEY in tool_state:
        flow_updates["validation_warnings"] = _normalize_string_list(
            tool_state.get(_VALIDATION_WARNINGS_KEY)
        )
    if _RETRY_FEEDBACK_KEY in tool_state:
        flow_updates["retry_feedback"] = _normalize_string_list(
            tool_state.get(_RETRY_FEEDBACK_KEY)
        )
    if _WORKING_MEMORY_KEY in tool_state:
        flow_updates["working_memory"] = tool_state.get(_WORKING_MEMORY_KEY)
    if _AMBIGUITY_REPORTS_KEY in tool_state:
        flow_updates["ambiguity_reports"] = _tool_reports(tool_state)

    if flow_updates:
        next_state = StateManager.update_framework(next_state, **flow_updates)

    return WorkflowState(
        data=next_state["data"],
        flow=next_state["flow"],
        messages=messages if messages is not None else next_state["messages"],
    )


class PhaseExecutor:
    """Execute a single phase invocation; retry / routing is the graph's job.

    Build one per ``harness.run()`` invocation. Pass it to
    ``graph.invoke`` via ``config["configurable"]["_phase_executor"]``;
    the graph-node closures extract it from the config on each call.
    """

    def __init__(
        self,
        callbacks: list[Callback],
        *,
        run_context: RunContext | None = None,
        heartbeat: Any = None,
        resolver: Any = None,
        save_compaction_sidecar: Callable[..., Any] | None = None,
    ) -> None:
        self._callbacks = callbacks
        self._run_context = run_context
        self._heartbeat = heartbeat
        self._resolver = resolver
        self._save_compaction_sidecar = save_compaction_sidecar

    def __getstate__(self) -> Any:
        # Fail-fast guard for the LangGraph checkpointer (and any other
        # path that tries to pickle RunnableConfig). ``PhaseExecutor``
        # deliberately holds live per-run references (heartbeat thread,
        # bound method to the harness's sidecar writer, callback list
        # with open trace files); these are not serialisable and even if
        # they were, a resumed run would be wrong to reuse stale
        # instances. We thread the executor through
        # ``config["configurable"]`` for in-memory access only. If the
        # checkpointer tries to persist the config, raising here surfaces
        # the design violation immediately rather than letting a silent
        # data-corruption bug reach production.
        raise TypeError(
            "PhaseExecutor is a per-run runtime object and must not be "
            "pickled. Its presence in RunnableConfig['configurable'] is "
            "for in-memory propagation only — ensure your checkpointer "
            "excludes '_phase_executor' or do not persist the config that "
            "carries it."
        )

    # Read-only accessors for callers that need the fields (e.g. subgraph).
    @property
    def run_context(self) -> RunContext | None:
        return self._run_context

    @property
    def heartbeat(self) -> Any:
        return self._heartbeat

    @property
    def callbacks(self) -> list[Callback]:
        return self._callbacks

    def _apply_io_hoist(
        self,
        state: WorkflowState,
        phase: Phase,
        *,
        source_data: dict[str, Any] | None = None,
    ) -> WorkflowState:
        """MVP-2 T7-bis: route declarative io.outputs into BusinessData.

        Called at phase exit from each of the three executor entry
        points (LLM phase end, code-only phase end, validation phase
        pass). When ``phase.io_specs`` is empty the call is a no-op,
        which keeps phases without declarative io routing on the
        legacy path.

        ``source_data`` defaults to ``state['flow'].finish_task_result``
        (the LLM phase exit case after ``StateManager.route_finish_task``
        has populated it). Code-only phases pass the live BusinessData
        dump so tool-returned dict keys can hoist directly. The IOManager
        is constructed per-call from the phase's specs — re-construction
        is cheap and lets the caller stay stateless.
        """
        if not phase.io_specs:
            return state

        from .io_manager import IOManager

        if source_data is None:
            ftr = state["flow"].finish_task_result
            source_data = dict(ftr) if isinstance(ftr, dict) else {}

        manager = IOManager(list(phase.io_specs))
        result = manager.resolve_hoist(source_data, state["data"])

        next_state = state
        new_dump = result.new_business_data.model_dump()
        # Only push BusinessData updates when the hoist produced new
        # fields. Comparing against the live dump avoids a redundant
        # ``model_copy`` round-trip when every spec was missing.
        if new_dump != next_state["data"].model_dump():
            next_state = StateManager.update_business(next_state, **new_dump)

        if result.io_errors:
            existing = list(next_state["flow"].io_errors)
            next_state = StateManager.update_framework(
                next_state, io_errors=existing + list(result.io_errors)
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
        * Anything else (``None`` / ``list`` / ``int`` / ...) → no state
          change. Code-only tools that need side effects on
          ``BusinessData`` should mutate the passed-in instance directly
          (covered by the existing IO-hoist path).

        Args:
            phase: The currently executing code-only phase.
            state: The workflow state cloned by the caller.
            result: The tool's return value, typed ``object`` per
                PHASE2_DESIGN.md §4.4 (no ``Any``). Real shape is
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
            k for k in raw.keys() if isinstance(k, str) and k.startswith("_")
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

    def execute_code_only_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Run a code-only phase (``requires_llm=False``).

        Tools are invoked sequentially as plain callables receiving
        ``BusinessData``. A tool that returns a string updates framework
        ``last_output``; one returning a dict has it merged into
        ``BusinessData`` (Phase 2 A3, see
        :meth:`_merge_code_phase_tool_result`); retry feedback is cleared
        through ``FrameworkState``.
        """
        from .harness import _clone_state  # lazy: avoid import cycle at module load

        next_state = _clone_state(state)
        for cb in self._callbacks:
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

        for cb in self._callbacks:
            cb.on_phase_end(
                phase.name,
                next_state["data"].model_dump(),
                next_state["flow"].metrics,
            )
        return next_state

    def execute_validation_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Run the phase's validator and emit retry / pass state updates.

        Control-flow shape (preserved verbatim from ``_build_validation_node``):

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
        from ..callbacks.events import RetryExhaustedEvent, ValidationPassEvent
        from .harness import _clone_state, _safe_emit_event  # lazy: avoid import cycle

        next_state = _clone_state(state)
        if next_state["flow"].validation_middleware_phase == phase.name:
            # LLM phase validators have already run inside ValidationMiddleware,
            # keeping rejected finish_task submissions in the same agent loop
            # instead of restarting the whole phase through retry_target routing.
            return StateManager.update_framework(next_state, validation_middleware_phase=None)

        if phase.validator is None:
            return next_state

        passed, errors = phase.validator(next_state["data"])
        if isinstance(errors, str):
            logger.warning(
                "phase=%s validator returned str instead of list[str]; "
                "coercing to single-element list. Update validator to "
                "match Callback.on_retry / RetryEvent.feedback contract.",
                phase.name,
            )
            errors = [errors] if errors else []
        elif not isinstance(errors, list):
            logger.warning(
                "phase=%s validator returned %s instead of list[str]; coercing.",
                phase.name,
                type(errors).__name__,
            )
            errors = [str(errors)] if errors else []
        retry_key = phase.retry_target or phase.name

        retry_counts = dict(next_state["flow"].retry_counts)
        if passed:
            retries_used = retry_counts.get(retry_key, 0)
            retry_counts.pop(retry_key, None)
            _safe_emit_event(
                self._callbacks,
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
        for cb in self._callbacks:
            cb.on_validation_fail(phase.name, errors, current_retries)

        if current_retries >= phase.max_retries:
            logger.warning(
                "Phase '%s' exceeded max retries (%d). Continuing with warnings.",
                phase.name,
                phase.max_retries,
            )
            _safe_emit_event(
                self._callbacks,
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

        for cb in self._callbacks:
            cb.on_retry(phase.name, retry_key, errors)

        return StateManager.update_framework(
            next_state,
            retry_counts=retry_counts,
            retry_feedback=errors,
        )

    def execute_llm_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Run an LLM-driven phase (DeerFlow create_agent + nudge-loop).

        Reads per-run state (``_run_context``, ``_heartbeat``) and
        harness-lifetime deps (``_resolver``, ``_save_compaction_sidecar``)
        from its own fields. No harness back-reference.
        """
        from ..callbacks.events import (
            CompactionEvent,
            ModelResolvedEvent,
            WorkingMemoryUpdateEvent,
        )
        from .harness import (  # lazy imports: harness module depends on us
            _clone_state,
            _safe_emit_event,
        )

        assert self._resolver is not None, "execute_llm_phase requires a resolver"
        assert self._save_compaction_sidecar is not None, (
            "execute_llm_phase requires a save_compaction_sidecar callable"
        )
        resolver = self._resolver
        active_callbacks = self._callbacks

        state = _clone_state(state)
        is_retry = state["flow"].current_phase == phase.name
        framework_updates: dict[str, Any] = {
            "current_phase": phase.name,
            "finish_task_result": None,
            "validation_middleware_phase": phase.name,
        }
        if phase.output_schema_path is not None:
            framework_updates["md_schema_path"] = phase.output_schema_path
        if phase.md_type_dict is not None:
            framework_updates["md_type_dict"] = phase.md_type_dict
        state = StateManager.update_framework(state, **framework_updates)
        tool_state = legacy_context_from_state(state)

        working_memory_before = _tool_text(tool_state, _WORKING_MEMORY_KEY)

        # Step 1: Consume retry feedback for this invoke.
        retry_feedback = state["flow"].retry_feedback
        state = StateManager.update_framework(state, retry_feedback=None)
        tool_state.pop(_RETRY_FEEDBACK_KEY, None)

        # Tier 1 Commit D — update heartbeat's current_phase so
        # subsequent HeartbeatEvents carry the correct phase name.
        if self._heartbeat is not None:
            self._heartbeat.current_phase = phase.name

        # Callbacks
        for cb in active_callbacks:
            cb.on_phase_start(phase.name, state["data"].model_dump())

        # Step 3: Render user_prompt_template
        prompt_view = state["data"].model_dump()
        user_message = _render_user_prompt(phase, prompt_view)
        if retry_feedback:
            feedback_text = "\n".join(f"- {e}" for e in retry_feedback)
            user_message += (
                f"\n\n--- 校验反馈 ---\n"
                f"以下是上一轮输出的校验错误，请仔细阅读后修正你的输出：\n"
                f"{feedback_text}"
            )

        # Step 4: Get model from Model Resolver
        # thinking_enabled=None → auto-detect from model's reasoning flag
        # Task 6.1: phase.model_override pins the phase to a specific
        # model code from llm_roles.yaml's models: section, bypassing
        # the tier → role → model mapping. When it's None the call
        # behaves exactly as before.
        model = resolver.resolve(
            phase.tier,
            model_override=phase.model_override,
            callbacks=tuple(active_callbacks),
            phase_name=phase.name,
        )
        resolved_model_name = (
            getattr(model, "name", None)
            or getattr(model, "model", None)
            or getattr(model, "model_name", None)
        )

        # Tier 1 Commit B (T-B2): record the tier → role → model
        # resolution decision itself so Studio can show *why* this
        # phase runs on this specific provider/model combo.
        _safe_emit_event(
            active_callbacks,
            ModelResolvedEvent(
                phase_name=phase.name,
                tier=phase.tier or "",
                role_name=(
                    f"_model_override::{phase.model_override}"
                    if phase.model_override
                    else (phase.tier or "")
                ),
                resolved_model=(str(resolved_model_name) if resolved_model_name else None),
                thinking_enabled=getattr(model, "thinking_enabled", None),
                model_override=phase.model_override,
                call_chain=[],
            ),
        )

        effective_llm_role = phase.llm_role or phase.tier

        model = TracingClientProxy(
            wrapped_client=model,
            callbacks=active_callbacks,
            phase_name=phase.name,
            llm_role=effective_llm_role,
            resolved_model=str(resolved_model_name) if resolved_model_name else None,
            sub_run_id=state["flow"].sub_run_id,
            group_key=state["flow"].group_key,
        )
        llm_role = effective_llm_role or "balanced"
        role_prefix = resolve_role_prefix_from_llm_role(llm_role)
        logger.info(
            "phase=%s llm_role=%s -> role_prefix injected (len=%d)",
            phase.name,
            llm_role,
            len(role_prefix),
        )

        # Step 5: Create callback bridge and wrap tools with limiter.
        bridge = _HarnessCallbackBridge(
            phase.name,
            active_callbacks,
            state["flow"].metrics,
            max_tool_calls=phase.max_tool_calls,
        )

        def _finish_task_tool(
            ctx: dict[str, Any],
            reasoning: str = "",
            diagnostics_md: str = "",
            business_data_md: str = "",
        ) -> dict[str, Any]:
            prior = _finish_result_from_tool_state(ctx)
            finish_input = {"finish_task_result": prior} if prior is not None else {}
            outcome = finish_task(
                finish_input,
                reasoning=reasoning,
                diagnostics_md=diagnostics_md,
                business_data_md=business_data_md,
            )
            payload = outcome.get("value") if isinstance(outcome, dict) else None
            if isinstance(payload, dict):
                ctx[_FINISH_TASK_RESULT_KEY] = {**prior, **payload} if prior else payload
            return outcome

        _finish_task_tool.__name__ = "finish_task"
        _finish_task_tool.__doc__ = finish_task.__doc__

        lc_tools = [_wrap_tool_for_langchain(fn, tool_state, bridge) for fn in phase.tools]
        lc_tools.append(
            _wrap_tool_for_langchain(_finish_task_tool, tool_state, bridge, return_direct=True)
        )
        lc_tools.append(_wrap_tool_for_langchain(update_working_memory, tool_state, bridge))
        lc_tools.append(_wrap_tool_for_langchain(log_ambiguity, tool_state, bridge))
        from ..tools.builtin.clarification_tool import ask_clarification_tool

        lc_tools.append(ask_clarification_tool)
        logger.info("phase=%s: mounted ask_clarification tool", phase.name)
        references = list(getattr(phase, "references", []) or [])
        if references:
            base_dir = getattr(phase, "skill_base_dir", None) or tool_state.get(
                _SKILL_BASE_DIR_KEY
            )
            if base_dir is None:
                logger.warning(
                    "phase=%s has references=%s but no skill_base_dir; read_file tool not mounted",
                    phase.name,
                    references,
                )
            else:
                from ..tools.builtin.read_file import make_read_file_tool

                read_file_fn = make_read_file_tool(references, Path(base_dir))
                lc_tools.append(_wrap_tool_for_langchain(read_file_fn, tool_state, bridge))
                logger.info(
                    "phase=%s mounted read_file tool with %d references",
                    phase.name,
                    len(references),
                )
        context_access = list(phase.context_access)
        if context_access:
            from ..tools.builtin.context_access import (
                query_working_memory,
                read_artifact,
            )

            if "working_memory" in context_access:
                lc_tools.append(_wrap_tool_for_langchain(query_working_memory, tool_state, bridge))
                logger.info("phase=%s mounted query_working_memory tool", phase.name)
            if "artifact" in context_access:
                lc_tools.append(_wrap_tool_for_langchain(read_artifact, tool_state, bridge))
                logger.info("phase=%s mounted read_artifact tool", phase.name)
        phase_middlewares = create_custom_middlewares(
            working_memory=True,
            dead_end_pruning=True,
            dead_end_threshold=phase.dead_end_threshold,
            context_ref=tool_state,
            callbacks=active_callbacks,
            phase_name=phase.name,
            loop_detection=True,
            summarization=True,
            summarization_model=model,
            summarization_trigger_fraction=0.8,
            summarization_keep_messages=20,
            clarification=True,
        )
        phase_middlewares.append(
            ValidationMiddleware(
                output_schema=phase.output_schema,
                output_schema_path=phase.output_schema_path,
                business_validator=phase.validator,
                ctx=tool_state,
                callbacks=active_callbacks,
                phase_name=phase.name,
            )
        )

        # Step 6: Create LangChain agent — render system_prompt with business data
        raw_skill_prompt = phase.system_prompt or "完成当前阶段的任务。"
        rendered_skill_prompt = _safe_render_template(raw_skill_prompt, prompt_view)
        rendered_data_architecture = (
            _safe_render_template(phase.data_architecture, prompt_view)
            if phase.data_architecture
            else None
        )
        system_prompt = apply_cognitive_template(
            phase_name=phase.name,
            skill_system_prompt=rendered_skill_prompt,
            data_architecture=rendered_data_architecture,
            context=prompt_view,
            role_prefix=role_prefix,
        )
        agent: Any = create_agent(
            model=cast(Any, model),
            tools=lc_tools,
            system_prompt=system_prompt,
            middleware=phase_middlewares,
        )

        # Step 7: Build messages
        messages: list[AnyMessage] = list(state["messages"]) if is_retry else []
        messages.append(HumanMessage(content=user_message))

        # Step 8: Run agent with Callback Bridge + Phase metadata
        outer_tid = state["flow"].thread_id or ""
        model_name = (
            getattr(model, "model_name", None) or getattr(model, "model", None) or phase.tier
        )
        agent_config = RunnableConfig(
            configurable={
                "max_iterations": phase.max_iterations,
                "thread_id": f"{outer_tid}:{phase.name}",
            },
            recursion_limit=phase.max_iterations * 2 + 10,
            callbacks=[bridge],
            run_name=f"Phase_{phase.name}",
            metadata={
                "phase_name": phase.name,
                "tier": phase.tier,
                "model_name": str(model_name),
                "trace_id": f"{outer_tid}:{phase.name}",
            },
            tags=[f"phase:{phase.name}", f"tier:{phase.tier}"],
        )
        result_messages: list[AnyMessage] = []

        def _latest_ai_content(msgs: list[AnyMessage]) -> str:
            for _msg in reversed(msgs):
                if isinstance(_msg, AIMessage) and _msg.content:
                    return _extract_text_content(_msg.content)
            return ""

        def _compact_messages(
            original_user_msg: HumanMessage,
            working_memory: str,
        ) -> list[AnyMessage]:
            """Checkpoint: compress accumulated messages into a compact context."""
            checkpoint_text = (
                f"## 执行进度（Checkpoint）\n\n{working_memory}\n\n"
                "前序步骤的中间消息已被压缩。请根据上述进度继续执行计划中的下一步。"
                "如果需要数据，请使用工具获取。"
            )
            return [original_user_msg, HumanMessage(content=checkpoint_text)]

        tool_state.pop(_FINISH_TASK_RESULT_KEY, None)
        # D-7.4: nudge policy + counter state moved to NudgeInjector.
        # Pass active_callbacks (= harness.callbacks, not RunContext.callbacks)
        # to preserve the legacy narrower callback scope for nudge events.
        nudge_injector = NudgeInjector(phase, active_callbacks)
        plan_verified = False
        wm_snapshot = _tool_text(tool_state, _WORKING_MEMORY_KEY)
        checkpoint_count = 0
        current_messages: list[AnyMessage] = list(messages)
        original_user_msg = (
            messages[0]
            if messages and isinstance(messages[0], HumanMessage)
            else HumanMessage(content="")
        )
        max_outer_iterations = max(20, phase.max_iterations * 2)
        outer_iterations = 0

        while True:
            outer_iterations += 1
            if outer_iterations > max_outer_iterations:
                warning = (
                    f"[CognitiveLoop] Phase '{phase.name}' exceeded max_outer_iterations="
                    f"{max_outer_iterations}; forced degrade to avoid infinite loop."
                )
                logger.warning(warning)
                _append_tool_warning(tool_state, warning)
                break

            try:
                result = agent.invoke(
                    cast(Any, {"messages": current_messages}),
                    config=agent_config,
                )
            except Exception as agent_err:
                logger.error(
                    "[Harness] agent.invoke failed in phase '%s': %s",
                    phase.name,
                    agent_err,
                )
                # Ensure on_phase_end fires even when agent.invoke raises
                for cb in active_callbacks:
                    try:
                        cb.on_phase_end(
                            phase.name,
                            state["data"].model_dump(),
                            state["flow"].metrics,
                        )
                    except Exception as cb_exc:
                        logger.warning(
                            "[Harness] on_phase_end callback error during cleanup: %s", cb_exc
                        )
                raise
            result_messages = list(cast(list[AnyMessage], result.get("messages", [])))

            # --- Finish gate: self-check enforcement ---
            finish_result = _finish_result_from_tool_state(tool_state)
            if finish_result:
                outcome = nudge_injector.try_selfcheck(finish_result)
                if outcome.message is not None:
                    tool_state.pop(_FINISH_TASK_RESULT_KEY, None)
                    current_messages = [
                        *result_messages,
                        cast(AnyMessage, outcome.message),
                    ]
                    continue
                break

            # --- Planning enforcement: first invoke must produce a plan ---
            wm_current = _tool_text(tool_state, _WORKING_MEMORY_KEY)
            wm_updated = wm_current != wm_snapshot

            if not plan_verified:
                if wm_updated:
                    plan_verified = True
                    wm_snapshot = wm_current
                else:
                    latest_content = _latest_ai_content(result_messages)
                    # Check if agent made tool calls (productive behavior)
                    has_tool_calls = any(
                        isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
                        for m in result_messages
                    )
                    outcome = nudge_injector.try_planning(
                        latest_content, has_tool_calls=has_tool_calls
                    )
                    if outcome.message is not None:
                        current_messages = [
                            *result_messages,
                            cast(AnyMessage, outcome.message),
                        ]
                        continue
                    plan_verified = True

            # --- Checkpoint: compact context when working memory updates ---
            if plan_verified and wm_updated and wm_current:
                checkpoint_count += 1
                wm_snapshot = wm_current
                removed_pairs = max((len(current_messages) - 2) // 2, 0)
                wm_text = str(wm_current or "")
                _safe_emit_event(
                    active_callbacks,
                    WorkingMemoryUpdateEvent(
                        phase_name=phase.name,
                        content_length=len(wm_text),
                        content=wm_text,
                    ),
                )
                # Sidecar write for compaction: runs through the
                # harness-provided writer but reads run_id /
                # storage_manager from this executor's own RunContext
                # (not a harness instance attr) — eliminates the
                # concurrent-child.run() race that the pre-Phase-B code
                # carried.
                removed_messages = current_messages[:-2] if len(current_messages) > 2 else []
                active_ctx = self._run_context
                # P1-1.1 post-D: ``active_ctx.run_id`` is an empty string
                # for code paths that never populate the RunContext (older
                # test fixtures, bare PhaseExecutor([]) use cases). Empty
                # string produces a ``_history//<idx>.json`` path — a
                # filesystem-valid but semantically broken dir. Fall back
                # to "unknown" so the sidecar lands somewhere greppable.
                # NOTE: the ``run_id=`` kwarg expression is kept inline as
                # an IfExp/BoolOp (not extracted to a local) so the
                # test_compaction_closure_scope AST regression guard
                # still sees a non-bare-Name RHS.
                sidecar_ref = self._save_compaction_sidecar(
                    run_id=((active_ctx.run_id if active_ctx else "") or "unknown"),
                    idx=checkpoint_count,
                    removed_messages=removed_messages,
                    storage_manager=(active_ctx.storage_manager if active_ctx else None),
                )
                removed_summary = (
                    f"Compacted {removed_pairs} message pair(s) at checkpoint "
                    f"#{checkpoint_count} in phase '{phase.name}'."
                )
                _safe_emit_event(
                    active_callbacks,
                    CompactionEvent(
                        phase_name=phase.name,
                        removed_pairs=removed_pairs,
                        removed_summary=removed_summary,
                        content_ref=sidecar_ref,
                    ),
                )
                current_messages = _compact_messages(original_user_msg, str(wm_current))
                logger.info(
                    "[CognitiveLoop] Phase '%s' checkpoint #%d — context compacted.",
                    phase.name,
                    checkpoint_count,
                )
                continue

            # --- Standard nudge: text output without tool calls ---
            latest_content = _latest_ai_content(result_messages)
            # Only nudge when agent produced text WITHOUT any tool calls
            has_tool_calls = any(
                isinstance(m, AIMessage) and getattr(m, "tool_calls", None) for m in result_messages
            )
            outcome = nudge_injector.try_standard(latest_content, has_tool_calls=has_tool_calls)
            if outcome.message is not None:
                current_messages = [
                    *result_messages,
                    cast(AnyMessage, outcome.message),
                ]
                continue
            if outcome.budget_exhausted:
                warning = (
                    f"[CognitiveLoop] Phase '{phase.name}' exceeded max_nudges="
                    f"{phase.max_nudges}; forced degrade without finish_task."
                )
                logger.warning(warning)
                _append_tool_warning(tool_state, warning)
            # No text, no finish_task, no working memory update — exit with warning
            if not latest_content:
                exit_warning = (
                    f"[CognitiveLoop] Phase '{phase.name}' exited with no AI text content "
                    "and no finish_task. Output may be incomplete."
                )
                logger.warning(exit_warning)
                _append_tool_warning(tool_state, exit_warning)
            break

        # Step 9: Extract results
        final_output = ""
        for msg in reversed(result_messages):
            if isinstance(msg, AIMessage) and msg.content:
                final_output = _extract_text_content(msg.content)
                break

        finish_result = _finish_result_from_tool_state(tool_state)
        if isinstance(finish_result, dict):
            reasoning = str(
                finish_result.get("diagnostics_md", "") or finish_result.get("reasoning", "")
            )
            business_data = str(finish_result.get("business_data_md", "")).strip()
            callback_payload = [business_data] if business_data else []
            for cb in active_callbacks:
                try:
                    cb.on_finish_task(phase.name, reasoning, callback_payload)
                except Exception as exc:
                    logger.warning("[Harness] callback error: %s", exc)

        all_reports = _tool_reports(tool_state)
        if all_reports:
            phase_reports = [r for r in all_reports if r.get("phase") == phase.name]
            for cb in active_callbacks:
                for report in phase_reports:
                    try:
                        cb.on_ambiguity_report(
                            phase.name,
                            str(report.get("type", "")),
                            str(report.get("question", "")),
                            str(report.get("decision", "")),
                        )
                    except Exception as exc:
                        logger.warning("[Harness] callback error: %s", exc)

        working_memory_after = _tool_text(tool_state, _WORKING_MEMORY_KEY)
        if working_memory_after != working_memory_before:
            wm_text = str(working_memory_after or "")
            _safe_emit_event(
                active_callbacks,
                WorkingMemoryUpdateEvent(
                    phase_name=phase.name,
                    content_length=len(wm_text),
                    content=wm_text,
                ),
            )

        # Step 10: Keep successful finish_task data in split state so
        # declarative io.outputs.source can persist parsed business data.

        # Step 11: Update state
        new_state = _sync_tool_state(
            state,
            tool_state,
            messages=result_messages,
        )
        new_state = StateManager.update_framework(
            new_state,
            current_phase=phase.name,
            last_output=final_output,
        )
        if isinstance(finish_result, dict):
            new_state = StateManager.route_finish_task(new_state, finish_result)

        # MVP-2 T7-bis: declarative io.outputs hoist runs at LLM phase
        # exit, after route_finish_task has populated
        # ``flow.finish_task_result``. The default source for hoist is
        # that finish_task_result, so the helper picks it up from state
        # without an explicit pass-through. No-op when phase.io_specs
        # is empty (legacy phase without declarative io).
        new_state = self._apply_io_hoist(new_state, phase)

        # Callbacks
        for cb in active_callbacks:
            cb.on_phase_end(
                phase.name,
                new_state["data"].model_dump(),
                new_state["flow"].metrics,
            )

        return new_state
