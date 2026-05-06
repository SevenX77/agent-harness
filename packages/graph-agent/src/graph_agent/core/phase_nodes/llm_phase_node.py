"""``LLMPhaseNode`` — DeerFlow ``create_agent`` + nudge-loop execution.

PHASE3_DESIGN.md §2.2 specialises the legacy
``PhaseExecutor.execute_llm_phase`` (~600 lines, the bulk of the old
god class) into a focused class. The behaviour matches the pre-M6
method verbatim — including the post-M7 single-branch
``ProtocolValidation + CognitiveFlow`` middleware stack — only the
surrounding plumbing now lives on a polymorphic ``PhaseNode``
subclass.

The two nested helpers ``_latest_ai_content`` / ``_compact_messages``
remain inline within :meth:`execute` so the captured locals
(``working_memory``, ``original_user_msg``) keep the same closure
semantics as the pre-refactor implementation. Likewise the
``_finish_task_tool`` closure inside :meth:`execute` keeps the
captured ``tool_state`` reference identical to the legacy code path.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from graph_agent.cognitive.ambiguity import log_ambiguity
from graph_agent.cognitive.finish import finish_task
from graph_agent.cognitive.memory import update_working_memory
from graph_agent.cognitive.middlewares import create_custom_middlewares
from graph_agent.cognitive.prompt import (
    apply_cognitive_template,
    resolve_role_prefix_from_llm_role,
)
from graph_agent.core.callback_bridge import _extract_text_content, _HarnessCallbackBridge
from graph_agent.core.nudge_injector import NudgeInjector
from graph_agent.core.state import (
    StateManager,
    StateMessage,
    WorkflowState,
    legacy_context_from_state,
)
from graph_agent.core.template import _render_user_prompt, _safe_render_template
from graph_agent.core.tool_wrapper import _wrap_tool_for_langchain
from graph_agent.core.tracing_proxy import TracingClientProxy
from graph_agent.core.types import Phase
from graph_agent.core.phase_nodes._helpers import (
    _FINISH_TASK_RESULT_KEY,
    _RETRY_FEEDBACK_KEY,
    _SKILL_BASE_DIR_KEY,
    _WORKING_MEMORY_KEY,
    _append_tool_warning,
    _finish_result_from_tool_state,
    _sync_tool_state,
    _tool_reports,
    _tool_text,
)
from graph_agent.core.phase_nodes.base import PhaseNode

logger = logging.getLogger(__name__)


class _AgentInvoker(Protocol):
    def invoke(
        self,
        input: object,
        *,
        config: RunnableConfig,
    ) -> Mapping[str, object]:
        """Run the wrapped LangChain agent and return its message payload."""


class LLMPhaseNode(PhaseNode):
    """Run an LLM-driven phase (DeerFlow ``create_agent`` + nudge-loop)."""

    def execute(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        from graph_agent.callbacks.events import (
            CompactionEvent,
            ModelResolvedEvent,
            WorkingMemoryUpdateEvent,
        )
        from graph_agent.core.harness import (  # lazy imports: harness module depends on us
            _clone_state,
            _safe_emit_event,
        )

        resolver = self.container.resolver
        assert resolver is not None, "execute_llm_phase requires a resolver"
        save_compaction_sidecar = self.container.save_compaction_sidecar
        assert save_compaction_sidecar is not None, (
            "execute_llm_phase requires a save_compaction_sidecar callable"
        )
        active_callbacks = self.container.callbacks

        state = _clone_state(state)
        is_retry = state["flow"].current_phase == phase.name
        framework_updates: dict[str, object] = {
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

        model = cast(
            BaseChatModel,
            TracingClientProxy(
                wrapped_client=model,
                callbacks=active_callbacks,
                phase_name=phase.name,
                llm_role=effective_llm_role,
                resolved_model=str(resolved_model_name) if resolved_model_name else None,
                sub_run_id=state["flow"].sub_run_id,
                group_key=state["flow"].group_key,
            ),
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
            ctx: dict[str, object],
            reasoning: str = "",
            diagnostics_md: str = "",
            business_data_md: str = "",
        ) -> dict[str, object]:
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
        from graph_agent.tools.builtin.clarification_tool import ask_clarification_tool

        lc_tools.append(ask_clarification_tool)
        logger.info("phase=%s: mounted ask_clarification tool", phase.name)
        references = list(getattr(phase, "references", []) or [])
        if references:
            base_dir = getattr(phase, "skill_base_dir", None) or tool_state.get(_SKILL_BASE_DIR_KEY)
            if base_dir is None:
                logger.warning(
                    "phase=%s has references=%s but no skill_base_dir; read_file tool not mounted",
                    phase.name,
                    references,
                )
            else:
                from graph_agent.tools.builtin.read_file import make_read_file_tool

                read_file_fn = make_read_file_tool(references, Path(base_dir))
                lc_tools.append(_wrap_tool_for_langchain(read_file_fn, tool_state, bridge))
                logger.info(
                    "phase=%s mounted read_file tool with %d references",
                    phase.name,
                    len(references),
                )
        context_access = list(phase.context_access)
        if context_access:
            from graph_agent.tools.builtin.context_access import (
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

        # Phase 3 M7 (PHASE3_DESIGN.md §3.2 / §3.4): single-branch
        # finish_task pipeline. Strategy C terminates the dual-system
        # split by requiring every LLM phase to declare a strongly-typed
        # ``output_schema`` (Pydantic ``type[BaseModel]`` or
        # ``SchemaObject``); the legacy parallel pipeline and its
        # ``DynamicSchemaDef`` / schema-less fallbacks are physically
        # retired together with this routing simplification.
        from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware
        from graph_agent.middleware.protocol_validation import ProtocolValidationMiddleware
        from graph_agent.core.io_manager import IOManager
        from graph_agent.core.schema_engine import SchemaEngine

        schema_engine = SchemaEngine()
        io_manager = IOManager(list(phase.io_specs))
        logger.info(
            "phase=%s action=middleware_pipeline decision=static_schema schema=%s",
            phase.name,
            getattr(
                phase.output_schema,
                "__name__",
                type(phase.output_schema).__name__,
            ),
        )
        phase_middlewares.append(
            ProtocolValidationMiddleware(
                schema_engine=schema_engine,
                current_phase_schema=phase.output_schema,
                phase_name=phase.name,
            )
        )
        phase_middlewares.append(
            CognitiveFlowMiddleware(
                io_manager=io_manager,
                unattended=state["flow"].unattended,
                schema_engine=schema_engine,
                current_phase_schema=phase.output_schema,
                business_validator=phase.validator,
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
        agent = cast(
            _AgentInvoker,
            create_agent(
                model=model,
                tools=lc_tools,
                system_prompt=system_prompt,
                middleware=phase_middlewares,
            ),
        )

        # Step 7: Build messages
        messages: list[StateMessage] = list(state["messages"]) if is_retry else []
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
        result_messages: list[StateMessage] = []

        def _latest_ai_content(msgs: list[StateMessage]) -> str:
            for _msg in reversed(msgs):
                if isinstance(_msg, AIMessage) and _msg.content:
                    return _extract_text_content(_msg.content)
            return ""

        def _compact_messages(
            original_user_msg: HumanMessage,
            working_memory: str,
        ) -> list[StateMessage]:
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
        current_messages: list[StateMessage] = list(messages)
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
                    {"messages": current_messages},
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
            result_messages = list(cast(list[StateMessage], result.get("messages", [])))

            # --- Finish gate: self-check enforcement ---
            finish_result = _finish_result_from_tool_state(tool_state)
            if finish_result:
                outcome = nudge_injector.try_selfcheck(finish_result)
                if outcome.message is not None:
                    tool_state.pop(_FINISH_TASK_RESULT_KEY, None)
                    current_messages = [
                        *result_messages,
                        outcome.message,
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
                            outcome.message,
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
                sidecar_ref = save_compaction_sidecar(
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
                    outcome.message,
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


__all__ = ["LLMPhaseNode"]
