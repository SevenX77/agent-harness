"""PhaseExecutor — executes a single phase once (LLM / code-only / validation / subgraph).

Extracted progressively from ``GraphAgentHarness._build_*_node`` factories
as D-7.2 of the harness-split. Migration order per context.md §6.1 step 4:

  * step 4.1: ``execute_code_only_phase`` — smallest, no
    heartbeat / run_context dependency.
  * step 4.2: ``execute_validation_phase``.
  * step 4.3 (this commit): ``execute_llm_phase`` — the DeerFlow agent
    loop. Holds a ``harness`` reference during Phase A so it can read
    ``_active_heartbeat`` / ``_active_run_context`` / ``_resolver`` /
    ``_save_compaction_sidecar`` from the still-stateful harness
    instance. The reference is explicitly marked as temporary here —
    step 4.4 (Phase B) will switch to per-run PhaseExecutor passed via
    LangGraph ``RunnableConfig["configurable"]``, delete ``self._harness``
    and the mutable instance attrs on GraphAgentHarness.
  * step 4.4 (Phase B): RunnableConfig-based per-run wiring, resolves
    the concurrent-``child.run()`` race noted in subgraph.py's FIXME.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from ..callbacks.base import Callback
from ..cognitive.ambiguity import log_ambiguity
from ..cognitive.finish import finish_task
from ..cognitive.memory import update_working_memory
from ..cognitive.middlewares import create_custom_middlewares
from ..cognitive.prompt import apply_cognitive_template
from ..config.llm_config import get_role_config
from .callback_bridge import _HarnessCallbackBridge, _extract_text_content
from .nudge_injector import NudgeInjector
from .state import WorkflowState
from .template import _render_user_prompt, _safe_render_template
from .tool_wrapper import _wrap_tool_for_langchain
from .tracing_proxy import TracingClientProxy
from .types import Phase

if TYPE_CHECKING:
    from .harness import GraphAgentHarness

logger = logging.getLogger(__name__)


class PhaseExecutor:
    """Execute a single phase invocation; retry / routing is the graph's job."""

    def __init__(
        self,
        callbacks: list[Callback],
        *,
        harness: "GraphAgentHarness | None" = None,
    ) -> None:
        self._callbacks = callbacks
        # Phase-A scaffolding — ``harness`` is only needed by
        # ``execute_llm_phase`` for reading ``_active_heartbeat`` /
        # ``_active_run_context`` / ``_resolver`` /
        # ``_save_compaction_sidecar``. Step 4.4 (Phase B) removes this
        # reference once those attributes move off the harness instance.
        self._harness = harness

    def execute_code_only_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Run a code-only phase (``requires_llm=False``).

        Tools are invoked sequentially as plain callables receiving the
        phase's mutable context dict. A tool that returns a string sets
        ``context["_last_output"]`` (the last wins, matching pre-refactor
        semantics). ``_retry_feedback`` is popped after tools run so the
        feedback is visible to tools but does not leak to the next phase.
        """
        from .harness import _clone_state  # lazy: avoid import cycle at module load

        next_state = _clone_state(state)
        for cb in self._callbacks:
            cb.on_phase_start(phase.name, dict(next_state["context"]))

        if phase.tools:
            logger.info(
                "[CodeOnly] Executing %d tool(s) for phase=%s",
                len(phase.tools),
                phase.name,
            )
            for fn in phase.tools:
                result = fn(next_state["context"])
                if isinstance(result, str):
                    next_state["context"]["_last_output"] = result

        next_state["context"].pop("_retry_feedback", None)
        next_state["current_phase"] = phase.name

        for cb in self._callbacks:
            cb.on_phase_end(
                phase.name,
                dict(next_state["context"]),
                dict(next_state["metrics"]),
            )
        return next_state

    def execute_validation_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Run the phase's validator and emit retry / pass state updates.

        Control-flow shape (preserved verbatim from ``_build_validation_node``):

          * no ``phase.validator`` → clone and return unchanged
          * validator returns ``(True, ...)`` → pop the phase's retry
            bucket, pop ``_validation_warnings``, emit
            ``ValidationPassEvent`` with the pre-pop retry count
          * validator returns ``(False, errors)`` →
            - fire ``on_validation_fail(phase, errors, current_retries)``
            - if ``current_retries >= max_retries``: emit
              ``RetryExhaustedEvent``, set ``_validation_warnings=errors``
            - else: set ``_retry_feedback=errors``, increment the retry
              bucket, fire ``on_retry(phase, target, errors)``

        Retry bucket key is ``phase.retry_target or phase.name`` on both
        the pass and fail paths — the same rule as the pre-refactor code.
        """
        from .harness import _clone_state, _safe_emit_event  # lazy: avoid import cycle
        from ..callbacks.events import RetryExhaustedEvent, ValidationPassEvent

        if phase.validator is None:
            return _clone_state(state)

        next_state = _clone_state(state)
        passed, errors = phase.validator(next_state["context"])
        retry_key = phase.retry_target or phase.name

        if passed:
            retries_used = next_state["retry_counts"].get(retry_key, 0)
            next_state["retry_counts"].pop(retry_key, None)
            next_state["context"].pop("_validation_warnings", None)
            _safe_emit_event(
                self._callbacks,
                ValidationPassEvent(
                    phase_name=phase.name,
                    retry_count=retries_used,
                ),
            )
            return next_state

        current_retries = next_state["retry_counts"].get(retry_key, 0)
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
            next_state["context"]["_validation_warnings"] = errors
            return next_state

        next_state["context"]["_retry_feedback"] = errors
        next_state["retry_counts"][retry_key] = current_retries + 1

        for cb in self._callbacks:
            cb.on_retry(phase.name, retry_key, errors)

        return next_state

    def execute_llm_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Run an LLM-driven phase (DeerFlow create_agent + nudge-loop).

        Migrated verbatim (behaviour-preserving) from the ``execute`` closure
        that used to live inside ``GraphAgentHarness._build_phase_node``.
        The outer while-loop orchestrates DeerFlow ``agent.invoke`` calls
        with three nudge gates (selfcheck / planning / standard) via
        ``NudgeInjector``, a compaction checkpoint when working memory
        updates, and a degrade-to-warning exit when max iterations or
        nudge budget are exhausted.
        """
        from .harness import (  # lazy imports: harness module depends on us
            _append_validation_warning,
            _clone_state,
            _ctx_reports,
            _ctx_text,
            _safe_emit_event,
        )
        from ..callbacks.events import (
            CompactionEvent,
            ModelResolvedEvent,
            WorkingMemoryUpdateEvent,
        )

        assert self._harness is not None, (
            "execute_llm_phase requires a harness reference during Phase A. "
            "Step 4.4 (Phase B) will remove this requirement."
        )
        harness = self._harness
        resolver = harness._resolver
        active_callbacks = self._callbacks

        state = _clone_state(state)
        ctx = state["context"]
        ctx["_current_phase"] = phase.name

        # Inject md_to_json schema info if available.
        # Store the dotted path (string) instead of the Pydantic class itself —
        # LangGraph's msgpack-based checkpointer cannot serialize ModelMetaclass.
        # md_to_json resolves the path → class via sys.modules on demand.
        if phase.output_schema_path is not None:
            ctx["_md_schema_path"] = phase.output_schema_path
        if phase.md_type_dict is not None:
            ctx["_md_type_dict"] = phase.md_type_dict

        working_memory_before = _ctx_text(ctx, "_working_memory")

        # Step 1: Consume _retry_feedback
        retry_feedback: list[str] | None = None
        if "_retry_feedback" in ctx:
            retry_feedback = ctx.pop("_retry_feedback")

        # Step 2: Determine if new phase or retry
        is_retry = state["current_phase"] == phase.name

        # Tier 1 Commit D — update heartbeat's current_phase so
        # subsequent HeartbeatEvents carry the correct phase name.
        if harness._active_heartbeat is not None:
            harness._active_heartbeat.current_phase = phase.name

        # Callbacks
        for cb in active_callbacks:
            cb.on_phase_start(phase.name, dict(ctx))

        # Step 3: Render user_prompt_template
        user_message = _render_user_prompt(phase, ctx)
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
        model = resolver.resolve(phase.tier, model_override=phase.model_override)
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
                resolved_model=(
                    str(resolved_model_name) if resolved_model_name else None
                ),
                thinking_enabled=getattr(model, "thinking_enabled", None),
                model_override=phase.model_override,
                call_chain=[],
            ),
        )

        model = TracingClientProxy(
            wrapped_client=model,
            callbacks=active_callbacks,
            phase_name=phase.name,
            llm_role=phase.tier,
            resolved_model=str(resolved_model_name) if resolved_model_name else None,
            sub_run_id=ctx.get("_sub_run_id") if isinstance(ctx, dict) else None,
            group_key=ctx.get("_group_key") if isinstance(ctx, dict) else None,
        )
        role_prefix = ""
        try:
            role_prefix = get_role_config().resolve_role(phase.tier).system_prompt_prefix
        except Exception as exc:
            logger.warning('[Harness] role config resolution failed for tier=%s: %s', phase.tier, exc)
            role_prefix = ""

        # Step 5: Create callback bridge and wrap tools with limiter.
        bridge = _HarnessCallbackBridge(
            phase.name,
            active_callbacks,
            state["metrics"],
            max_tool_calls=phase.max_tool_calls,
        )
        lc_tools = [_wrap_tool_for_langchain(fn, ctx, bridge) for fn in phase.tools]
        lc_tools.append(_wrap_tool_for_langchain(finish_task, ctx, bridge, return_direct=True))
        lc_tools.append(_wrap_tool_for_langchain(update_working_memory, ctx, bridge))
        lc_tools.append(_wrap_tool_for_langchain(log_ambiguity, ctx, bridge))
        if phase.subagent_enabled:
            try:
                from deerflow.tools.builtins import task_tool as deerflow_task_tool

                lc_tools.append(deerflow_task_tool)
            except Exception as exc:
                logger.warning("[Harness] Failed to enable task tool for phase '%s': %s", phase.name, exc)

        phase_middlewares = create_custom_middlewares(
            working_memory=True,
            dead_end_pruning=True,
            dead_end_threshold=phase.dead_end_threshold,
            context_ref=ctx,
            callbacks=active_callbacks,
            phase_name=phase.name,
        )

        # Step 6: Create DeerFlow Agent — render system_prompt with context
        raw_skill_prompt = phase.system_prompt or "完成当前阶段的任务。"
        rendered_skill_prompt = _safe_render_template(raw_skill_prompt, ctx)
        rendered_data_architecture = (
            _safe_render_template(phase.data_architecture, ctx)
            if phase.data_architecture
            else None
        )
        system_prompt = apply_cognitive_template(
            phase_name=phase.name,
            skill_system_prompt=rendered_skill_prompt,
            data_architecture=rendered_data_architecture,
            subagent_enabled=phase.subagent_enabled,
            context=ctx,
            role_prefix=role_prefix,
        )
        agent = create_agent(
            model=model,
            tools=lc_tools,
            system_prompt=system_prompt,
            middleware=phase_middlewares,
        )

        # Step 7: Build messages
        messages = list(state["messages"]) if is_retry else []
        messages.append(HumanMessage(content=user_message))

        # Step 8: Run agent with Callback Bridge + Phase metadata
        outer_tid = _ctx_text(ctx, "_thread_id") or ""
        model_name = (
            getattr(model, "model_name", None)
            or getattr(model, "model", None)
            or phase.tier
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
        result_messages: list[BaseMessage] = []

        def _latest_ai_content(msgs: list[BaseMessage]) -> str:
            for _msg in reversed(msgs):
                if isinstance(_msg, AIMessage) and _msg.content:
                    return _extract_text_content(_msg.content)
            return ""

        def _compact_messages(
            original_user_msg: HumanMessage,
            working_memory: str,
        ) -> list[BaseMessage]:
            """Checkpoint: compress accumulated messages into a compact context."""
            checkpoint_text = (
                f"## 执行进度（Checkpoint）\n\n{working_memory}\n\n"
                "前序步骤的中间消息已被压缩。请根据上述进度继续执行计划中的下一步。"
                "如果需要数据，请使用工具获取。"
            )
            return [original_user_msg, HumanMessage(content=checkpoint_text)]

        ctx.pop("_finish_task_result", None)
        # D-7.4: nudge policy + counter state moved to NudgeInjector.
        # Pass active_callbacks (= harness.callbacks, not RunContext.callbacks)
        # to preserve the legacy narrower callback scope for nudge events.
        nudge_injector = NudgeInjector(phase, active_callbacks)
        plan_verified = False
        wm_snapshot = _ctx_text(ctx, "_working_memory")
        checkpoint_count = 0
        current_messages = list(messages)
        original_user_msg = messages[0] if messages else HumanMessage(content="")
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
                _append_validation_warning(ctx, warning)
                break

            try:
                result = agent.invoke({"messages": current_messages}, config=agent_config)
            except Exception as agent_err:
                logger.error(
                    "[Harness] agent.invoke failed in phase '%s': %s",
                    phase.name,
                    agent_err,
                )
                # Ensure on_phase_end fires even when agent.invoke raises
                for cb in active_callbacks:
                    try:
                        cb.on_phase_end(phase.name, dict(ctx), dict(state["metrics"]))
                    except Exception as cb_exc:
                        logger.warning("[Harness] on_phase_end callback error during cleanup: %s", cb_exc)
                raise
            result_messages = list(result.get("messages", []))

            # --- Finish gate: self-check enforcement ---
            finish_result = ctx.get("_finish_task_result")
            if finish_result:
                outcome = nudge_injector.try_selfcheck(finish_result)
                if outcome.message is not None:
                    ctx.pop("_finish_task_result", None)
                    current_messages = list(result_messages) + [outcome.message]
                    continue
                break

            # --- Planning enforcement: first invoke must produce a plan ---
            wm_current = _ctx_text(ctx, "_working_memory")
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
                        current_messages = list(result_messages) + [outcome.message]
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
                # Sidecar write for compaction: see _save_compaction_sidecar.
                # Read run_id / storage_manager from the active RunContext —
                # they're NOT in this closure's scope (the closure is built
                # at __init__ time, before any run_id exists). Gemini audit
                # 2026-04-24 caught this as a latent NameError that only
                # fired when compaction actually triggered at runtime.
                removed_messages = (
                    current_messages[:-2]
                    if len(current_messages) > 2
                    else []
                )
                active_ctx = harness._active_run_context
                sidecar_ref = harness._save_compaction_sidecar(
                    run_id=(active_ctx.run_id if active_ctx else ""),
                    idx=checkpoint_count,
                    removed_messages=removed_messages,
                    storage_manager=(
                        active_ctx.storage_manager if active_ctx else None
                    ),
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
                isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
                for m in result_messages
            )
            outcome = nudge_injector.try_standard(
                latest_content, has_tool_calls=has_tool_calls
            )
            if outcome.message is not None:
                current_messages = list(result_messages) + [outcome.message]
                continue
            if outcome.budget_exhausted:
                warning = (
                    f"[CognitiveLoop] Phase '{phase.name}' exceeded max_nudges="
                    f"{phase.max_nudges}; forced degrade without finish_task."
                )
                logger.warning(warning)
                _append_validation_warning(ctx, warning)
            # No text, no finish_task, no working memory update — exit with warning
            if not latest_content:
                exit_warning = (
                    f"[CognitiveLoop] Phase '{phase.name}' exited with no AI text content "
                    "and no finish_task. Output may be incomplete."
                )
                logger.warning(exit_warning)
                _append_validation_warning(ctx, exit_warning)
            break

        # Step 9: Extract results
        final_output = ""
        for msg in reversed(result_messages):
            if isinstance(msg, AIMessage) and msg.content:
                final_output = _extract_text_content(msg.content)
                break

        ctx["_last_output"] = final_output

        finish_result = ctx.get("_finish_task_result")
        if isinstance(finish_result, dict):
            reasoning = str(
                finish_result.get("execution_summary")
                or finish_result.get("reasoning", "")
            )
            evidence_raw = finish_result.get("evidence", [])
            evidence = evidence_raw if isinstance(evidence_raw, list) else [str(evidence_raw)]
            checklist = finish_result.get("plan_checklist", [])
            if isinstance(checklist, list):
                for item in checklist:
                    if isinstance(item, dict):
                        evidence.append(
                            "checklist:"
                            f"{item.get('step', '')}|"
                            f"completed={item.get('completed', False)}|"
                            f"quality={item.get('quality_check', '')}"
                        )
            for cb in active_callbacks:
                try:
                    cb.on_finish_task(phase.name, reasoning, [str(item) for item in evidence])
                except Exception as exc:
                    logger.warning('[Harness] callback error: %s', exc)

        all_reports = _ctx_reports(ctx)
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
                        logger.warning('[Harness] callback error: %s', exc)

        working_memory_after = _ctx_text(ctx, "_working_memory")
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

        # Step 10: Clean up phase-local keys before returning state
        ctx.pop("_finish_task_result", None)

        # Step 11: Update state
        new_state: WorkflowState = {
            "context": ctx,
            "messages": result_messages,
            "current_phase": phase.name,
            "retry_counts": dict(state["retry_counts"]),
            "metrics": dict(state["metrics"]),
        }

        # Callbacks
        for cb in active_callbacks:
            cb.on_phase_end(phase.name, dict(ctx), dict(new_state["metrics"]))

        return new_state

    def execute_subgraph_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Invoke a child harness for a subgraph phase."""
        raise NotImplementedError("D-7.2: migrate from _build_subgraph_node body")
