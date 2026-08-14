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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from graph_agent.callbacks.base import Callback
from graph_agent.cognitive.ambiguity import log_ambiguity
from graph_agent.cognitive.finish import finish_task
from graph_agent.cognitive.memory import update_working_memory
from graph_agent.cognitive.middlewares import create_custom_middlewares
from graph_agent.cognitive.prompt import (
    apply_cognitive_template,
    resolve_role_prefix_from_llm_role,
)
from graph_agent.core.callback_bridge import _extract_text_content, _HarnessCallbackBridge
from graph_agent.core.llm_provider import (
    LLMProviderChatModel,
    LLMProviderMissingError,
)
from graph_agent.core.nudge_injector import NudgeInjector
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
from graph_agent.core.state import (
    StateManager,
    StateMessage,
    WorkflowState,
    legacy_context_from_state,
)
from graph_agent.core.template import _render_user_prompt, _safe_render_template
from graph_agent.core.tool_wrapper import _wrap_tool_for_langchain
from graph_agent.core.types import Phase

logger = logging.getLogger(__name__)


class _AgentInvoker(Protocol):
    def invoke(
        self,
        input: object,
        *,
        config: RunnableConfig,
    ) -> Mapping[str, object]:
        """Run the wrapped LangChain agent and return its message payload."""


@dataclass
class _PhaseRuntime:
    state: WorkflowState
    tool_state: dict[str, object]
    active_callbacks: list[Callback]
    save_compaction_sidecar: Any
    is_retry: bool
    retry_feedback: list[str] | None
    working_memory_before: str


@dataclass
class _CognitiveLoopState:
    result_messages: list[StateMessage]
    current_messages: list[StateMessage]
    plan_verified: bool
    wm_snapshot: str
    checkpoint_count: int


@dataclass(frozen=True)
class _LoopDecision:
    should_continue: bool = False
    should_break: bool = False


class LLMPhaseNode(PhaseNode):
    """Run an LLM-driven phase (DeerFlow ``create_agent`` + nudge-loop)."""

    def execute(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        runtime = self._prepare_phase_runtime(phase, state)
        prompt_view = runtime.state["data"].model_dump()
        user_message = _phase_user_message(phase, prompt_view, runtime.retry_feedback)
        model = self._resolved_tracing_model(phase, runtime)
        role_prefix = _role_prefix_for_phase(phase)
        bridge = _HarnessCallbackBridge(
            phase.name,
            runtime.active_callbacks,
            runtime.state["flow"].metrics,
            max_tool_calls=phase.max_tool_calls,
        )
        tools = self._langchain_tools(phase, runtime.tool_state, bridge)
        middlewares = self._phase_middlewares(phase, runtime, model)
        agent = _create_phase_agent(phase, model, tools, middlewares, prompt_view, role_prefix)
        messages = _phase_messages(runtime.state, runtime.is_retry, user_message)
        agent_config = _agent_config(phase, runtime.state, model, bridge)
        result_messages = self._run_cognitive_loop(
            phase, runtime, agent, agent_config, messages
        )
        return self._finalize_phase(phase, runtime, result_messages)

    def _prepare_phase_runtime(self, phase: Phase, state: WorkflowState) -> _PhaseRuntime:
        from graph_agent.core.state import _clone_state

        if self.container.llm_provider is None and self.container.legacy_model_resolver is None:
            raise LLMProviderMissingError(phase.name)
        save_compaction_sidecar = self.container.save_compaction_sidecar
        assert save_compaction_sidecar is not None, (
            "execute_llm_phase requires a save_compaction_sidecar callable"
        )
        active_callbacks = self.container.callbacks
        state = _clone_state(state)
        is_retry = state["flow"].current_phase == phase.name
        state = _prepare_framework_state(phase, state)
        tool_state = legacy_context_from_state(state)
        working_memory_before = _tool_text(tool_state, _WORKING_MEMORY_KEY) or ""
        retry_feedback = state["flow"].retry_feedback
        state = StateManager.update_framework(state, retry_feedback=None)
        tool_state.pop(_RETRY_FEEDBACK_KEY, None)
        self._set_heartbeat_phase(phase)
        _emit_phase_start(phase, state, active_callbacks)
        return _PhaseRuntime(
            state=state,
            tool_state=tool_state,
            active_callbacks=active_callbacks,
            save_compaction_sidecar=save_compaction_sidecar,
            is_retry=is_retry,
            retry_feedback=retry_feedback,
            working_memory_before=working_memory_before,
        )

    def _set_heartbeat_phase(self, phase: Phase) -> None:
        if self._heartbeat is not None:
            self._heartbeat.current_phase = phase.name

    def _resolved_tracing_model(self, phase: Phase, runtime: _PhaseRuntime) -> BaseChatModel:
        from graph_agent.callbacks.emit import _safe_emit_event
        from graph_agent.callbacks.events import ModelResolvedEvent

        provider = self.container.llm_provider
        if provider is not None:
            model = LLMProviderChatModel(
                provider=provider,
                role=phase.tier,
                phase_name=phase.name,
                model_override=phase.model_override,
                event_callbacks=tuple(runtime.active_callbacks),
                # A parallel sub-run stamps its identity on what it emits, and
                # the model is now what emits the start of a call.
                sub_run_id=runtime.state["flow"].sub_run_id,
                group_key=runtime.state["flow"].group_key,
            )
        else:
            resolver = self.container.legacy_model_resolver
            assert resolver is not None
            model = resolver.resolve(
                phase.tier,
                model_override=phase.model_override,
                callbacks=tuple(runtime.active_callbacks),
                phase_name=phase.name,
            )
        resolved_model_name = _resolved_model_name(model)
        _safe_emit_event(
            runtime.active_callbacks,
            ModelResolvedEvent(
                phase_name=phase.name,
                tier=phase.tier or "",
                role_name=_resolved_role_name(phase),
                resolved_model=(str(resolved_model_name) if resolved_model_name else None),
                thinking_enabled=getattr(model, "thinking_enabled", None),
                model_override=phase.model_override,
                call_chain=[],
            ),
        )
        return cast(BaseChatModel, model)

    def _langchain_tools(
        self,
        phase: Phase,
        tool_state: dict[str, object],
        bridge: _HarnessCallbackBridge,
    ) -> list[Any]:
        lc_tools = [_wrap_tool_for_langchain(fn, tool_state, bridge) for fn in phase.tools]
        lc_tools.extend(_core_cognitive_tools(tool_state, bridge))
        self._append_reference_tool(phase, tool_state, bridge, lc_tools)
        self._append_context_access_tools(phase, tool_state, bridge, lc_tools)
        return lc_tools

    def _append_reference_tool(
        self,
        phase: Phase,
        tool_state: dict[str, object],
        bridge: _HarnessCallbackBridge,
        lc_tools: list[Any],
    ) -> None:
        references = list(getattr(phase, "references", []) or [])
        if not references:
            return
        base_dir = getattr(phase, "skill_base_dir", None) or tool_state.get(_SKILL_BASE_DIR_KEY)
        if base_dir is None:
            logger.warning(
                "phase=%s has references=%s but no skill_base_dir; read_file tool not mounted",
                phase.name,
                references,
            )
            return
        from graph_agent.tools.builtin.read_file import make_read_file_tool

        read_file_fn = make_read_file_tool(references, Path(str(base_dir)))
        lc_tools.append(_wrap_tool_for_langchain(read_file_fn, tool_state, bridge))
        logger.info("phase=%s mounted read_file tool with %d references", phase.name, len(references))

    def _append_context_access_tools(
        self,
        phase: Phase,
        tool_state: dict[str, object],
        bridge: _HarnessCallbackBridge,
        lc_tools: list[Any],
    ) -> None:
        context_access = list(phase.context_access)
        if not context_access:
            return
        from graph_agent.tools.builtin.context_access import query_working_memory, read_artifact

        if "working_memory" in context_access:
            lc_tools.append(_wrap_tool_for_langchain(query_working_memory, tool_state, bridge))
            logger.info("phase=%s mounted query_working_memory tool", phase.name)
        if "artifact" in context_access:
            lc_tools.append(_wrap_tool_for_langchain(read_artifact, tool_state, bridge))
            logger.info("phase=%s mounted read_artifact tool", phase.name)

    def _phase_middlewares(
        self,
        phase: Phase,
        runtime: _PhaseRuntime,
        model: BaseChatModel,
    ) -> list[Any]:
        middlewares = create_custom_middlewares(
            working_memory=True,
            dead_end_pruning=True,
            dead_end_threshold=phase.dead_end_threshold,
            context_ref=runtime.tool_state,
            callbacks=runtime.active_callbacks,
            phase_name=phase.name,
            loop_detection=True,
            summarization=True,
            summarization_model=model,
            summarization_trigger_fraction=0.8,
            summarization_keep_messages=20,
            clarification=True,
        )
        _append_protocol_middlewares(phase, runtime, middlewares)
        return middlewares

    def _run_cognitive_loop(
        self,
        phase: Phase,
        runtime: _PhaseRuntime,
        agent: _AgentInvoker,
        agent_config: RunnableConfig,
        messages: list[StateMessage],
    ) -> list[StateMessage]:
        runtime.tool_state.pop(_FINISH_TASK_RESULT_KEY, None)
        nudge_injector = NudgeInjector(phase, runtime.active_callbacks)
        loop_state = _initial_loop_state(messages, runtime.tool_state)
        max_outer_iterations = max(20, phase.max_iterations * 2)
        for outer_iteration in range(1, max_outer_iterations + 2):
            if _loop_limit_exceeded(phase, runtime.tool_state, outer_iteration, max_outer_iterations):
                break
            decision = self._run_cognitive_iteration(
                phase, runtime, agent, agent_config, nudge_injector, loop_state
            )
            if decision.should_continue:
                continue
            if decision.should_break:
                break
        return loop_state.result_messages

    def _run_cognitive_iteration(
        self,
        phase: Phase,
        runtime: _PhaseRuntime,
        agent: _AgentInvoker,
        agent_config: RunnableConfig,
        nudge_injector: NudgeInjector,
        loop_state: _CognitiveLoopState,
    ) -> _LoopDecision:
        loop_state.result_messages = self._invoke_agent_once(
            phase, runtime, agent, agent_config, loop_state.current_messages
        )
        finish_decision = _handle_finish_gate(runtime.tool_state, nudge_injector, loop_state)
        if finish_decision.should_continue or finish_decision.should_break:
            return finish_decision
        wm_current = _tool_text(runtime.tool_state, _WORKING_MEMORY_KEY) or ""
        wm_updated = wm_current != loop_state.wm_snapshot
        planning_decision = _handle_planning_gate(nudge_injector, loop_state, wm_current, wm_updated)
        if planning_decision.should_continue:
            return planning_decision
        checkpoint_decision = self._handle_checkpoint(
            phase, runtime, loop_state, wm_current, wm_updated
        )
        if checkpoint_decision.should_continue:
            return checkpoint_decision
        return _handle_standard_nudge(phase, runtime.tool_state, nudge_injector, loop_state)

    def _invoke_agent_once(
        self,
        phase: Phase,
        runtime: _PhaseRuntime,
        agent: _AgentInvoker,
        agent_config: RunnableConfig,
        current_messages: list[StateMessage],
    ) -> list[StateMessage]:
        try:
            result = agent.invoke({"messages": current_messages}, config=agent_config)
            return list(cast(list[StateMessage], result.get("messages", [])))
        except Exception as agent_err:
            logger.error("[Harness] agent.invoke failed in phase '%s': %s", phase.name, agent_err)
            _emit_phase_end_cleanup(phase, runtime.state, runtime.active_callbacks)
            raise

    def _handle_checkpoint(
        self,
        phase: Phase,
        runtime: _PhaseRuntime,
        loop_state: _CognitiveLoopState,
        wm_current: str,
        wm_updated: bool,
    ) -> _LoopDecision:
        if not (loop_state.plan_verified and wm_updated and wm_current):
            return _LoopDecision()
        loop_state.checkpoint_count += 1
        loop_state.wm_snapshot = wm_current
        removed_pairs = max((len(loop_state.current_messages) - 2) // 2, 0)
        _emit_working_memory_update(phase, runtime.active_callbacks, wm_current)
        sidecar_ref = self._write_compaction_sidecar(runtime, loop_state)
        _emit_compaction_event(
            phase,
            runtime.active_callbacks,
            removed_pairs,
            loop_state.checkpoint_count,
            sidecar_ref,
        )
        loop_state.current_messages = _compact_messages(_original_user_msg(loop_state), str(wm_current))
        logger.info(
            "[CognitiveLoop] Phase '%s' checkpoint #%d — context compacted.",
            phase.name,
            loop_state.checkpoint_count,
        )
        return _LoopDecision(should_continue=True)

    def _write_compaction_sidecar(
        self,
        runtime: _PhaseRuntime,
        loop_state: _CognitiveLoopState,
    ) -> str | None:
        removed_messages = (
            loop_state.current_messages[:-2] if len(loop_state.current_messages) > 2 else []
        )
        active_ctx = self._run_context
        return cast(
            str | None,
            runtime.save_compaction_sidecar(
                run_id=((active_ctx.run_id if active_ctx else "") or "unknown"),
                idx=loop_state.checkpoint_count,
                removed_messages=removed_messages,
                storage_manager=(active_ctx.storage_manager if active_ctx else None),
            ),
        )

    def _finalize_phase(
        self,
        phase: Phase,
        runtime: _PhaseRuntime,
        result_messages: list[StateMessage],
    ) -> WorkflowState:
        final_output = _latest_ai_content(result_messages)
        finish_result = _finish_result_from_tool_state(runtime.tool_state)
        _emit_finish_callbacks(phase, runtime.active_callbacks, finish_result)
        _emit_ambiguity_callbacks(phase, runtime.active_callbacks, runtime.tool_state)
        self._emit_final_working_memory_update(phase, runtime)
        new_state = _sync_tool_state(runtime.state, runtime.tool_state, messages=result_messages)
        new_state = StateManager.update_framework(
            new_state,
            current_phase=phase.name,
            last_output=final_output,
        )
        if isinstance(finish_result, dict):
            new_state = StateManager.route_finish_task(new_state, finish_result)
        new_state = self._apply_io_hoist(new_state, phase)
        _emit_phase_end(phase, new_state, runtime.active_callbacks)
        return new_state

    def _emit_final_working_memory_update(self, phase: Phase, runtime: _PhaseRuntime) -> None:
        working_memory_after = _tool_text(runtime.tool_state, _WORKING_MEMORY_KEY)
        if working_memory_after != runtime.working_memory_before:
            _emit_working_memory_update(phase, runtime.active_callbacks, str(working_memory_after or ""))


def _prepare_framework_state(phase: Phase, state: WorkflowState) -> WorkflowState:
    framework_updates: dict[str, object] = {
        "current_phase": phase.name,
        "finish_task_result": None,
        "validation_middleware_phase": phase.name,
    }
    if phase.output_schema_path is not None:
        framework_updates["md_schema_path"] = phase.output_schema_path
    if phase.md_type_dict is not None:
        framework_updates["md_type_dict"] = phase.md_type_dict
    return StateManager.update_framework(state, **framework_updates)


def _emit_phase_start(phase: Phase, state: WorkflowState, callbacks: list[Callback]) -> None:
    for cb in callbacks:
        cb.on_phase_start(phase.name, state["data"].model_dump())


def _phase_user_message(
    phase: Phase,
    prompt_view: dict[str, object],
    retry_feedback: list[str] | None,
) -> str:
    user_message = _render_user_prompt(phase, prompt_view)
    if not retry_feedback:
        return user_message
    feedback_text = "\n".join(f"- {e}" for e in retry_feedback)
    return (
        f"{user_message}\n\n--- 校验反馈 ---\n"
        f"以下是上一轮输出的校验错误，请仔细阅读后修正你的输出：\n"
        f"{feedback_text}"
    )


def _resolved_model_name(model: Any) -> Any:
    return getattr(model, "name", None) or getattr(model, "model", None) or getattr(
        model, "model_name", None
    )


def _resolved_role_name(phase: Phase) -> str:
    return f"_model_override::{phase.model_override}" if phase.model_override else (phase.tier or "")


def _role_prefix_for_phase(phase: Phase) -> str:
    llm_role = (phase.llm_role or phase.tier) or "balanced"
    role_prefix = resolve_role_prefix_from_llm_role(llm_role)
    logger.info(
        "phase=%s llm_role=%s -> role_prefix injected (len=%d)",
        phase.name,
        llm_role,
        len(role_prefix),
    )
    return role_prefix


def _core_cognitive_tools(tool_state: dict[str, object], bridge: _HarnessCallbackBridge) -> list[Any]:
    finish_tool = _make_finish_task_tool()
    tools = [
        _wrap_tool_for_langchain(finish_tool, tool_state, bridge, return_direct=True),
        _wrap_tool_for_langchain(update_working_memory, tool_state, bridge),
        _wrap_tool_for_langchain(log_ambiguity, tool_state, bridge),
    ]
    from graph_agent.tools.builtin.clarification_tool import ask_clarification_tool

    tools.append(ask_clarification_tool)
    logger.info("mounted ask_clarification tool")
    return tools


def _make_finish_task_tool() -> Any:
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
    return _finish_task_tool


def _append_protocol_middlewares(
    phase: Phase,
    runtime: _PhaseRuntime,
    middlewares: list[Any],
) -> None:
    from graph_agent.core.io_manager import IOManager
    from graph_agent.core.schema_engine import SchemaEngine
    from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware
    from graph_agent.middleware.protocol_validation import ProtocolValidationMiddleware

    schema_engine = SchemaEngine()
    logger.info(
        "phase=%s action=middleware_pipeline decision=static_schema schema=%s",
        phase.name,
        getattr(phase.output_schema, "__name__", type(phase.output_schema).__name__),
    )
    middlewares.append(
        ProtocolValidationMiddleware(
            schema_engine=schema_engine,
            current_phase_schema=phase.output_schema,
            phase_name=phase.name,
            callbacks=tuple(runtime.active_callbacks),
        )
    )
    middlewares.append(
        CognitiveFlowMiddleware(
            io_manager=IOManager(list(phase.io_specs)),
            unattended=runtime.state["flow"].unattended,
            schema_engine=schema_engine,
            current_phase_schema=phase.output_schema,
            business_validator=phase.validator,
            phase_name=phase.name,
            callbacks=tuple(runtime.active_callbacks),
        )
    )


def _create_phase_agent(
    phase: Phase,
    model: BaseChatModel,
    tools: list[Any],
    middlewares: list[Any],
    prompt_view: dict[str, object],
    role_prefix: str,
) -> _AgentInvoker:
    system_prompt = _phase_system_prompt(phase, prompt_view, role_prefix)
    return cast(
        _AgentInvoker,
        create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            middleware=middlewares,
        ),
    )


def _phase_system_prompt(
    phase: Phase,
    prompt_view: dict[str, object],
    role_prefix: str,
) -> str:
    raw_skill_prompt = phase.system_prompt or "完成当前阶段的任务。"
    rendered_skill_prompt = _safe_render_template(raw_skill_prompt, prompt_view)
    rendered_data_architecture = (
        _safe_render_template(phase.data_architecture, prompt_view)
        if phase.data_architecture
        else None
    )
    return apply_cognitive_template(
        phase_name=phase.name,
        skill_system_prompt=rendered_skill_prompt,
        data_architecture=rendered_data_architecture,
        context=prompt_view,
        role_prefix=role_prefix,
    )


def _phase_messages(
    state: WorkflowState,
    is_retry: bool,
    user_message: str,
) -> list[StateMessage]:
    messages: list[StateMessage] = list(state["messages"]) if is_retry else []
    messages.append(HumanMessage(content=user_message))
    return messages


def _agent_config(
    phase: Phase,
    state: WorkflowState,
    model: BaseChatModel,
    bridge: _HarnessCallbackBridge,
) -> RunnableConfig:
    outer_tid = state["flow"].thread_id or ""
    model_name = getattr(model, "model_name", None) or getattr(model, "model", None) or phase.tier
    return RunnableConfig(
        configurable={"max_iterations": phase.max_iterations, "thread_id": f"{outer_tid}:{phase.name}"},
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


def _initial_loop_state(
    messages: list[StateMessage],
    tool_state: dict[str, object],
) -> _CognitiveLoopState:
    return _CognitiveLoopState(
        result_messages=[],
        current_messages=list(messages),
        plan_verified=False,
        wm_snapshot=_tool_text(tool_state, _WORKING_MEMORY_KEY) or "",
        checkpoint_count=0,
    )


def _loop_limit_exceeded(
    phase: Phase,
    tool_state: dict[str, object],
    outer_iteration: int,
    max_outer_iterations: int,
) -> bool:
    if outer_iteration <= max_outer_iterations:
        return False
    warning = (
        f"[CognitiveLoop] Phase '{phase.name}' exceeded max_outer_iterations="
        f"{max_outer_iterations}; forced degrade to avoid infinite loop."
    )
    logger.warning(warning)
    _append_tool_warning(tool_state, warning)
    return True


def _handle_finish_gate(
    tool_state: dict[str, object],
    nudge_injector: NudgeInjector,
    loop_state: _CognitiveLoopState,
) -> _LoopDecision:
    finish_result = _finish_result_from_tool_state(tool_state)
    if not finish_result:
        return _LoopDecision()
    outcome = nudge_injector.try_selfcheck(finish_result)
    if outcome.message is None:
        return _LoopDecision(should_break=True)
    tool_state.pop(_FINISH_TASK_RESULT_KEY, None)
    loop_state.current_messages = [*loop_state.result_messages, outcome.message]
    return _LoopDecision(should_continue=True)


def _handle_planning_gate(
    nudge_injector: NudgeInjector,
    loop_state: _CognitiveLoopState,
    wm_current: str,
    wm_updated: bool,
) -> _LoopDecision:
    if loop_state.plan_verified:
        return _LoopDecision()
    if wm_updated:
        loop_state.plan_verified = True
        loop_state.wm_snapshot = wm_current
        return _LoopDecision()
    outcome = nudge_injector.try_planning(
        _latest_ai_content(loop_state.result_messages),
        has_tool_calls=_has_tool_calls(loop_state.result_messages),
    )
    if outcome.message is not None:
        loop_state.current_messages = [*loop_state.result_messages, outcome.message]
        return _LoopDecision(should_continue=True)
    loop_state.plan_verified = True
    return _LoopDecision()


def _handle_standard_nudge(
    phase: Phase,
    tool_state: dict[str, object],
    nudge_injector: NudgeInjector,
    loop_state: _CognitiveLoopState,
) -> _LoopDecision:
    latest_content = _latest_ai_content(loop_state.result_messages)
    outcome = nudge_injector.try_standard(
        latest_content,
        has_tool_calls=_has_tool_calls(loop_state.result_messages),
    )
    if outcome.message is not None:
        loop_state.current_messages = [*loop_state.result_messages, outcome.message]
        return _LoopDecision(should_continue=True)
    _record_standard_exit_warnings(phase, tool_state, latest_content, outcome.budget_exhausted)
    return _LoopDecision(should_break=True)


def _record_standard_exit_warnings(
    phase: Phase,
    tool_state: dict[str, object],
    latest_content: str,
    budget_exhausted: bool,
) -> None:
    if budget_exhausted:
        warning = (
            f"[CognitiveLoop] Phase '{phase.name}' exceeded max_nudges="
            f"{phase.max_nudges}; forced degrade without finish_task."
        )
        logger.warning(warning)
        _append_tool_warning(tool_state, warning)
    if not latest_content:
        exit_warning = (
            f"[CognitiveLoop] Phase '{phase.name}' exited with no AI text content "
            "and no finish_task. Output may be incomplete."
        )
        logger.warning(exit_warning)
        _append_tool_warning(tool_state, exit_warning)


def _emit_phase_end_cleanup(
    phase: Phase,
    state: WorkflowState,
    callbacks: list[Callback],
) -> None:
    for cb in callbacks:
        try:
            cb.on_phase_end(phase.name, state["data"].model_dump(), state["flow"].metrics)
        except Exception as cb_exc:
            logger.warning("[Harness] on_phase_end callback error during cleanup: %s", cb_exc)


def _latest_ai_content(msgs: list[StateMessage]) -> str:
    for msg in reversed(msgs):
        if isinstance(msg, AIMessage) and msg.content:
            return _extract_text_content(msg.content)
    return ""


def _has_tool_calls(messages: list[StateMessage]) -> bool:
    return any(isinstance(m, AIMessage) and getattr(m, "tool_calls", None) for m in messages)


def _original_user_msg(loop_state: _CognitiveLoopState) -> HumanMessage:
    message = loop_state.current_messages[0] if loop_state.current_messages else None
    return message if isinstance(message, HumanMessage) else HumanMessage(content="")


def _compact_messages(original_user_msg: HumanMessage, working_memory: str) -> list[StateMessage]:
    checkpoint_text = (
        f"## 执行进度（Checkpoint）\n\n{working_memory}\n\n"
        "前序步骤的中间消息已被压缩。请根据上述进度继续执行计划中的下一步。"
        "如果需要数据，请使用工具获取。"
    )
    return [original_user_msg, HumanMessage(content=checkpoint_text)]


def _emit_working_memory_update(phase: Phase, callbacks: list[Callback], wm_text: str) -> None:
    from graph_agent.callbacks.emit import _safe_emit_event
    from graph_agent.callbacks.events import WorkingMemoryUpdateEvent

    _safe_emit_event(
        callbacks,
        WorkingMemoryUpdateEvent(
            phase_name=phase.name,
            content_length=len(wm_text),
            content=wm_text,
        ),
    )


def _emit_compaction_event(
    phase: Phase,
    callbacks: list[Callback],
    removed_pairs: int,
    checkpoint_count: int,
    sidecar_ref: str | None,
) -> None:
    from graph_agent.callbacks.emit import _safe_emit_event
    from graph_agent.callbacks.events import CompactionEvent

    removed_summary = (
        f"Compacted {removed_pairs} message pair(s) at checkpoint "
        f"#{checkpoint_count} in phase '{phase.name}'."
    )
    _safe_emit_event(
        callbacks,
        CompactionEvent(
            phase_name=phase.name,
            removed_pairs=removed_pairs,
            removed_summary=removed_summary,
            content_ref=sidecar_ref,
        ),
    )


def _emit_finish_callbacks(
    phase: Phase,
    callbacks: list[Callback],
    finish_result: Any,
) -> None:
    if not isinstance(finish_result, dict):
        return
    reasoning = str(finish_result.get("diagnostics_md", "") or finish_result.get("reasoning", ""))
    business_data = str(finish_result.get("business_data_md", "")).strip()
    callback_payload = [business_data] if business_data else []
    for cb in callbacks:
        try:
            cb.on_finish_task(phase.name, reasoning, callback_payload)
        except Exception as exc:
            logger.warning("[Harness] callback error: %s", exc)


def _emit_ambiguity_callbacks(
    phase: Phase,
    callbacks: list[Callback],
    tool_state: dict[str, object],
) -> None:
    for report in _phase_reports(phase, tool_state):
        for cb in callbacks:
            _emit_one_ambiguity_callback(phase, cb, report)


def _phase_reports(phase: Phase, tool_state: dict[str, object]) -> list[dict[str, Any]]:
    all_reports = _tool_reports(tool_state)
    return [r for r in all_reports if r.get("phase") == phase.name] if all_reports else []


def _emit_one_ambiguity_callback(phase: Phase, callback: Any, report: dict[str, Any]) -> None:
    try:
        callback.on_ambiguity_report(
            phase.name,
            str(report.get("type", "")),
            str(report.get("question", "")),
            str(report.get("decision", "")),
        )
    except Exception as exc:
        logger.warning("[Harness] callback error: %s", exc)


def _emit_phase_end(phase: Phase, state: WorkflowState, callbacks: list[Callback]) -> None:
    for cb in callbacks:
        cb.on_phase_end(phase.name, state["data"].model_dump(), state["flow"].metrics)


__all__ = ["LLMPhaseNode"]
