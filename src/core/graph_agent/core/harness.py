"""GraphAgentHarness — multi-phase Agent orchestration engine based on LangGraph.

Builds a LangGraph StateGraph from a list of Phase definitions. Each phase
creates a DeerFlow Agent (via create_agent) that runs its own agent loop
with the phase-specific model, tools, system prompt, and middleware.

Key design: messages reset on new phase entry but are preserved during retries,
so the LLM can see its previous errors and fix them.

MODIFIED: Refactored to use DeerFlow create_agent + Model Resolver instead
of the old ToolExecutor + LLMGateway.
"""

from __future__ import annotations

import copy
import json
import logging
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from .callback_bridge import (
    _HarnessCallbackBridge,
    _extract_text_content,
    _extract_thinking_content,
)
from .subgraph import build_subgraph_node
from .template import _render_user_prompt, _safe_render_template
from .types import ContextBridge, Phase
from ..callbacks.base import Callback
from ..config.llm_config import get_role_config
from .exceptions import SkillLoadError
from ..cognitive.middlewares import create_custom_middlewares
from ..models.resolver import get_model_resolver
from ..cognitive.prompt import apply_cognitive_template
from .state import WorkflowState
from ..cognitive.ambiguity import log_ambiguity
from ..cognitive.finish import (
    MIN_FINISH_REASONING_LEN as _MIN_FINISH_REASONING_LEN,
    PLANNING_NUDGE as _PLANNING_NUDGE,
    SELFCHECK_NUDGE as _SELFCHECK_NUDGE,
    build_standard_nudge_text as _build_standard_nudge_text,
    finish_task,
)
from ..cognitive.memory import update_working_memory
from .tool_wrapper import _wrap_tool_for_langchain

logger = logging.getLogger(__name__)

__all__ = [
    "ContextBridge",
    "GraphAgentHarness",
    "Phase",
    "finish_task",
    "update_working_memory",
]


def _resolve_studio_checkpointer_spec(spec: str) -> Any:
    """Parse a ``STUDIO_CHECKPOINTER`` env-var value into a checkpointer.

    Supported forms (Task 7.7):

    * ``memory`` — LangGraph ``InMemorySaver``
    * ``sqlite:<path>`` — ``SqliteSaver`` opened at ``<path>`` (the
      ``:memory:`` sentinel and ``file:...`` URIs are passed through
      untouched; bare paths are resolved via DeerFlow's
      ``_resolve_sqlite_conn_str``)
    * ``postgres://...`` or ``postgresql://...`` — ``PostgresSaver``
      opened from the DSN
    """
    spec = spec.strip()
    if not spec:
        raise ValueError("empty spec")

    if spec == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        logger.info("[Harness] STUDIO_CHECKPOINTER=memory → InMemorySaver")
        return InMemorySaver()

    if spec.startswith("sqlite:"):
        raw = spec[len("sqlite:"):]
        from deerflow.agents.checkpointer.provider import _resolve_sqlite_conn_str
        from langgraph.checkpoint.sqlite import SqliteSaver

        conn_str = _resolve_sqlite_conn_str(raw or "store.db")
        saver_cm = SqliteSaver.from_conn_string(conn_str)
        saver = saver_cm.__enter__()
        saver.setup()
        logger.info("[Harness] STUDIO_CHECKPOINTER=sqlite:%s → SqliteSaver", conn_str)
        return saver

    if spec.startswith(("postgres://", "postgresql://")):
        from langgraph.checkpoint.postgres import PostgresSaver

        saver_cm = PostgresSaver.from_conn_string(spec)
        saver = saver_cm.__enter__()
        saver.setup()
        logger.info("[Harness] STUDIO_CHECKPOINTER=%s → PostgresSaver", _redact_dsn(spec))
        return saver

    raise ValueError(
        f"unrecognised STUDIO_CHECKPOINTER value: {spec!r} "
        "(expected 'memory', 'sqlite:<path>' or 'postgres://...')"
    )


def _redact_dsn(dsn: str) -> str:
    """Strip the password from a DSN before logging it."""
    import re

    return re.sub(r"(://[^:]+):[^@]+@", r"\1:***@", dsn)


def _safe_emit_event(callbacks: list[Callback], event: Any) -> None:
    """Dispatch a typed CallbackEvent to every callback, swallowing errors.

    Mirrors TracingClientProxy._emit_prompt_captured's isolation pattern:
    a broken callback must never take down the harness run. Each callback
    is tried independently and any exception is logged + skipped.
    """
    for cb in callbacks or []:
        try:
            cb.on_event(event)
        except Exception:  # noqa: BLE001
            logger.exception(
                "[Harness] callback %r raised on %s; continuing with other callbacks",
                type(cb).__name__,
                type(event).__name__,
            )


def _safe_jsonable_dict(data: Any) -> dict[str, Any]:
    """Minimal best-effort conversion of a context dict to JSON-safe values.

    Proper structural conversion (T-A3 in deferred-items.md) lands with
    Commit B and a dedicated ``callbacks/serialize.to_jsonable_dict()``
    helper. Until then, lifecycle events use this shallow pass: drop
    callables, convert Path/datetime to str, keep everything else.
    """
    if not isinstance(data, dict):
        return {"_value": repr(data)}

    out: dict[str, Any] = {}
    for key, value in data.items():
        try:
            if callable(value):
                out[str(key)] = f"<callable {getattr(value, '__name__', 'fn')}>"
            elif isinstance(value, Path):
                out[str(key)] = str(value)
            elif isinstance(value, (str, int, float, bool)) or value is None:
                out[str(key)] = value
            elif isinstance(value, (list, tuple)):
                out[str(key)] = [
                    v if isinstance(v, (str, int, float, bool)) or v is None else repr(v)
                    for v in value
                ]
            elif isinstance(value, dict):
                # One level of recursion is enough for the payload shape we ship.
                out[str(key)] = _safe_jsonable_dict(value)
            else:
                out[str(key)] = repr(value)
        except Exception:  # noqa: BLE001
            out[str(key)] = "<unserialisable>"
    return out


def _ctx_text(ctx: dict[str, Any], key: str) -> str | None:
    """Read a context value as text, preserving None."""
    value = ctx.get(key)
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _ctx_reports(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Read ambiguity reports defensively from arbitrary context payloads."""
    raw = ctx.get("_ambiguity_reports", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _append_validation_warning(ctx: dict[str, Any], warning: str) -> None:
    """Normalize the validation warning bucket to ``list[str]``."""
    existing = ctx.get("_validation_warnings")
    if isinstance(existing, list):
        existing.append(warning)
        return
    if existing is None:
        ctx["_validation_warnings"] = [warning]
        return
    ctx["_validation_warnings"] = [str(existing), warning]


def _clone_state(state: WorkflowState) -> WorkflowState:
    """Return a deep-cloned workflow state to prevent cross-phase mutation."""
    try:
        cloned_ctx = copy.deepcopy(state["context"])
    except TypeError:
        logger.error(
            "[Harness] deepcopy failed on context — shallow copy fallback weakens "
            "state isolation. Non-serializable objects in context should be avoided."
        )
        cloned_ctx = dict(state["context"])
    try:
        cloned_msgs = copy.deepcopy(state["messages"])
    except TypeError:
        logger.error(
            "[Harness] deepcopy failed on messages — shallow copy fallback weakens "
            "state isolation."
        )
        cloned_msgs = list(state["messages"])
    return {
        "context": cloned_ctx,
        "messages": cloned_msgs,
        "current_phase": state["current_phase"],
        "retry_counts": dict(state["retry_counts"]),
        "metrics": dict(state["metrics"]),
    }


# ---------------------------------------------------------------------------
# GraphAgentHarness
# ---------------------------------------------------------------------------


class GraphAgentHarness:
    """Multi-phase Agent orchestration engine based on LangGraph StateGraph.

    Each LLM phase reuses DeerFlow's ``create_agent()`` loop, while the harness
    adds graph-level control around it:

    - cognitive template injection
    - phase routing and validation retries
    - working-memory checkpoint compaction
    - finish_task enforcement and observability callbacks

    The runtime model is a dual-control architecture:

    - inner DeerFlow middleware handles a single ``agent.invoke()`` lifecycle
    - outer harness while-loop handles invoke-to-invoke nudges and exit gates

    State updates follow a reducer-friendly rule: graph nodes clone and return a
    new ``WorkflowState`` instead of mutating the inbound state object in place.

    Usage::

        harness = GraphAgentHarness(phases=[phase_a, phase_b])
        result = harness.run(initial_context={"input": data})
    """

    def __init__(
        self,
        phases: list[Phase],
        callbacks: list[Callback] | None = None,
        io_config: dict[str, Any] | None = None,
        context_mapping: dict[str, str] | None = None,
        skill_dir: Path | None = None,
        checkpointer: Any = "auto",
    ) -> None:
        """Initialize a harness with fixed phases and shared runtime services."""
        if not phases:
            raise SkillLoadError("GraphAgentHarness requires at least one phase")
        self.phases = phases
        self.callbacks = callbacks or []
        self._io_config = io_config
        self._context_mapping = context_mapping
        self._skill_dir = skill_dir
        self._resolver = get_model_resolver()
        self._checkpointer = self._resolve_checkpointer(checkpointer)
        self._runtime_local = threading.local()
        self._graph = self._build_graph()

    @staticmethod
    def _resolve_checkpointer(checkpointer: Any) -> Any:
        """Resolve checkpointer parameter to a concrete instance.

        Task 7.7: when the ``STUDIO_CHECKPOINTER`` env var is set it
        overrides the ``"auto"`` default so Studio runs can pick a
        backend without editing the host config. Accepted values:

        * ``memory`` — LangGraph's in-process ``InMemorySaver``
        * ``sqlite:<path>`` — SQLite backend at the given path
          (``sqlite:.studio/checkpoints.db`` is the Studio convention)
        * ``postgres://...`` — full Postgres DSN

        Any other ``checkpointer`` argument value (``None``, an explicit
        saver instance, etc.) passes through unchanged — the env var only
        applies when the caller has asked for auto resolution.
        """
        import os

        if checkpointer == "auto":
            override = os.environ.get("STUDIO_CHECKPOINTER")
            if override:
                try:
                    return _resolve_studio_checkpointer_spec(override)
                except Exception as exc:
                    logger.warning(
                        "[Harness] STUDIO_CHECKPOINTER=%r could not be resolved (%s); "
                        "falling back to default auto path",
                        override,
                        exc,
                    )
            try:
                from deerflow.agents.checkpointer.provider import get_checkpointer
                cp = get_checkpointer()
                logger.info("[Harness] Checkpointer: %s", type(cp).__name__)
                return cp
            except Exception as exc:
                logger.warning("[Harness] Auto-checkpointer failed, running without: %s", exc)
                return None
        return checkpointer  # None or explicit instance

    def run(
        self,
        initial_context: dict[str, Any] | None = None,
        trace_dir: Path | None = None,
        thread_id: str | None = None,
        artifact_saver: Callable[..., Any] | None = None,
        storage_manager: Any | None = None,
        runtime_inputs_map: dict[str, Any] | None = None,
        **runtime_inputs: Any,
    ) -> WorkflowState:
        """Execute the complete multi-phase workflow."""
        effective_runtime_inputs = dict(runtime_inputs_map or {})
        effective_runtime_inputs.update(runtime_inputs)
        if initial_context is None:
            initial_context = self._build_context_from_io(effective_runtime_inputs)

        effective_trace_dir = trace_dir
        if effective_trace_dir is None and initial_context.get("output_dir"):
            effective_trace_dir = Path(initial_context["output_dir"])

        initial_state: WorkflowState = {
            "context": dict(initial_context),
            "messages": [],
            "current_phase": "",
            "retry_counts": {},
            "metrics": {"total_input_tokens": 0, "total_output_tokens": 0},
        }

        tid = thread_id or str(uuid.uuid4())
        # Tier 1 Commit A: run_id identifies a single harness.run invocation.
        # thread_id may be reused across multiple runs (resume scenarios);
        # run_id is always fresh so Studio can distinguish each execution.
        run_id = uuid.uuid4().hex[:12]
        is_resume = thread_id is not None
        run_start_monotonic = time.monotonic()
        initial_state["context"]["_thread_id"] = tid
        initial_state["context"]["_run_id"] = run_id
        config: dict[str, Any] = {
            "recursion_limit": self._calc_recursion_limit(),
            "configurable": {"thread_id": tid},
        }

        previous_options = getattr(self._runtime_local, "options", None)
        self._runtime_local.options = {
            "trace_dir": effective_trace_dir,
            "thread_id": tid,
            "artifact_saver": artifact_saver,
            "storage_manager": storage_manager,
            "runtime_inputs": dict(effective_runtime_inputs),
        }

        # Task 7.0: Create explicit RunContext for new emit sites
        # (coexists with threading.local for backward compatibility)
        from .run_context import RunContext

        active_callbacks = list(self.callbacks) if hasattr(self, 'callbacks') else []
        self._active_run_context = RunContext(
            thread_id=tid,
            trace_dir=effective_trace_dir,
            runtime_inputs=dict(effective_runtime_inputs),
            storage_manager=storage_manager,
            artifact_saver=artifact_saver,
            callbacks=active_callbacks,
        )

        # Tier 1 Commit A — T-B1 RunStartedEvent
        from ..callbacks.events import (
            InternalErrorEvent,
            RunEndedEvent,
            RunStartedEvent,
        )
        _safe_emit_event(
            active_callbacks,
            RunStartedEvent(
                run_id=run_id,
                thread_id=tid,
                is_resume=is_resume,
                initial_context=_safe_jsonable_dict(initial_state["context"]),
            ),
        )

        try:
            result = self._graph.invoke(initial_state, config=config)

            # Auto-save outputs via IOManager if configured
            if self._io_config and self._io_config.get("outputs"):
                self._save_outputs_via_io(
                    result["context"],
                    effective_runtime_inputs,
                    artifact_saver=artifact_saver,
                    storage_manager=storage_manager,
                )

            # Auto-save TracingCallback trace to output dir
            from ..callbacks.tracing import TracingCallback

            trace_output = effective_trace_dir
            if trace_output is None and result["context"].get("output_dir"):
                trace_output = Path(result["context"]["output_dir"])
            if trace_output:
                for cb in self.callbacks:
                    if isinstance(cb, TracingCallback):
                        try:
                            saved = cb.save(trace_output)
                            result["context"]["_trace_path"] = saved
                        except Exception as exc:
                            logger.warning("[Harness] Trace save failed: %s", exc)
                        break

            # Tier 1 Commit A — T-B1 RunEndedEvent on success
            _safe_emit_event(
                active_callbacks,
                RunEndedEvent(
                    run_id=run_id,
                    thread_id=tid,
                    status="completed",
                    final_context=_safe_jsonable_dict(result["context"]),
                    wall_time_seconds=round(time.monotonic() - run_start_monotonic, 3),
                ),
            )
            return result  # type: ignore[return-value]
        except Exception as exc:
            # Tier 1 Commit A — T-B14 InternalErrorEvent at harness.run entry
            _safe_emit_event(
                active_callbacks,
                InternalErrorEvent(
                    entry_point="run",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    traceback=traceback.format_exc(),
                ),
            )
            _safe_emit_event(
                active_callbacks,
                RunEndedEvent(
                    run_id=run_id,
                    thread_id=tid,
                    status="crashed",
                    final_context={},
                    wall_time_seconds=round(time.monotonic() - run_start_monotonic, 3),
                ),
            )
            raise
        finally:
            if previous_options is None:
                if hasattr(self._runtime_local, "options"):
                    delattr(self._runtime_local, "options")
            else:
                self._runtime_local.options = previous_options

    def _get_active_run_options(self) -> dict[str, Any]:
        """Return thread-local run options for nested subgraph execution."""
        options = getattr(self._runtime_local, "options", None)
        return dict(options) if isinstance(options, dict) else {}

    @staticmethod
    def _save_compaction_sidecar(
        *,
        run_id: str,
        idx: int,
        removed_messages: list[Any],
        storage_manager: Any | None,
    ) -> str | None:
        """Write the compacted-out messages to a sidecar JSON file.

        Tier 1 Commit B (T-A2). The path is returned as ``content_ref`` on
        the CompactionEvent so Studio (or any JSONL reader) can inflate
        the full history on demand. Uses StorageManager when one is
        available (inherits retention); falls back to no-op + None ref
        when the caller did not inject storage.
        """
        if storage_manager is None:
            return None
        try:
            from ..callbacks.serialize import to_jsonable_dict

            name = f"compaction_{idx}.json"
            serialised = to_jsonable_dict(removed_messages)
            path = storage_manager.save_artifact(
                name,
                serialised,
                phase=f"_history/{run_id}",
            )
            return str(path)
        except Exception:  # noqa: BLE001
            logger.exception(
                "[Harness] failed to write compaction sidecar (run=%s idx=%d)",
                run_id,
                idx,
            )
            return None

    def _build_context_from_io(
        self,
        runtime_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Build initial_context using IOManager + ContextResolver."""
        if not self._io_config:
            raise ValueError(
                "initial_context is None but no io_config is set. "
                "Either pass initial_context or configure io in SKILL.md frontmatter."
            )

        from ..io.manager import IOManager

        io_mgr = IOManager(self._io_config)
        raw_inputs = io_mgr.load_inputs(**runtime_inputs)

        if self._context_mapping:
            from ..io.context_resolver import ContextResolver

            resolver = ContextResolver(
                mapping=self._context_mapping,
                helpers_dir=self._skill_dir,
            )
            return resolver.resolve({"input": raw_inputs})

        return raw_inputs

    def _save_outputs_via_io(
        self,
        context: dict[str, Any],
        runtime_inputs: dict[str, Any],
        *,
        artifact_saver: Callable[..., Any] | None = None,
        storage_manager: Any | None = None,
    ) -> None:
        """Auto-save outputs via IOManager."""
        from ..io.manager import IOManager

        io_mgr = IOManager(self._io_config)  # type: ignore[arg-type]
        try:
            io_mgr.save_outputs(
                context,
                output_dir=context.get("output_dir"),
                project_id=runtime_inputs.get("project_id"),
                artifact_saver=artifact_saver,
                storage_manager=storage_manager,
            )
        except Exception as exc:
            logger.warning("[Harness] Auto-save outputs failed: %s", exc)

    def resume(
        self,
        state: WorkflowState,
        human_input: str,
        thread_id: str | None = None,
        trace_dir: Path | None = None,
        artifact_saver: Callable[..., Any] | None = None,
    ) -> WorkflowState:
        """Resume execution after a request_human_input interrupt."""
        from langchain_core.messages import ToolMessage

        state = _clone_state(state)

        tool_call_id = ""
        for msg in reversed(state["messages"]):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.get("name") == "request_human_input":
                        tool_call_id = tc.get("id", "")
                        break
                if tool_call_id:
                    break

        if tool_call_id:
            state["messages"].append(
                ToolMessage(
                    content=human_input,
                    tool_call_id=tool_call_id,
                    name="request_human_input",
                )
            )

        effective_thread_id = thread_id or state["context"].get("_thread_id")
        config: dict[str, Any] = {
            "recursion_limit": self._calc_recursion_limit(),
            "configurable": {"thread_id": effective_thread_id},
        }

        previous_options = getattr(self._runtime_local, "options", None)
        self._runtime_local.options = {
            "trace_dir": trace_dir,
            "thread_id": effective_thread_id,
            "artifact_saver": artifact_saver,
            "runtime_inputs": {},
        }
        try:
            result = self._graph.invoke(state, config=config)
            return result  # type: ignore[return-value]
        except Exception as exc:
            # Tier 1 Commit A — T-B14 InternalErrorEvent at harness.resume
            from ..callbacks.events import InternalErrorEvent
            _safe_emit_event(
                self.callbacks,
                InternalErrorEvent(
                    entry_point="resume",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    traceback=traceback.format_exc(),
                ),
            )
            raise
        finally:
            if previous_options is None:
                if hasattr(self._runtime_local, "options"):
                    delattr(self._runtime_local, "options")
            else:
                self._runtime_local.options = previous_options

    # -----------------------------------------------------------------------
    # Graph construction
    # -----------------------------------------------------------------------

    def _build_graph(self) -> Any:
        """Build the LangGraph StateGraph from Phase definitions."""
        graph = StateGraph(WorkflowState)

        for _i, phase in enumerate(self.phases):
            execute_name = f"{phase.name}_execute"
            validate_name = f"{phase.name}_validate"

            if phase.subgraph is not None:
                graph.add_node(execute_name, self._build_subgraph_node(phase))
                graph.add_node(validate_name, self._build_validation_node(phase))
                graph.add_edge(execute_name, validate_name)

                graph.add_conditional_edges(
                    validate_name,
                    self._should_retry(phase),
                )
            elif phase.requires_llm:
                graph.add_node(execute_name, self._build_phase_node(phase))
                graph.add_node(validate_name, self._build_validation_node(phase))
                graph.add_edge(execute_name, validate_name)

                graph.add_conditional_edges(
                    validate_name,
                    self._should_retry(phase),
                )
            else:
                graph.add_node(execute_name, self._build_code_only_node(phase))
                next_node = self._get_next_phase_node(phase)
                if next_node == END:
                    graph.add_edge(execute_name, END)
                else:
                    graph.add_edge(execute_name, next_node)

        if self.phases:
            graph.set_entry_point(f"{self.phases[0].name}_execute")

        return graph.compile(checkpointer=self._checkpointer)

    def _build_subgraph_node(self, phase: Phase) -> Callable[[WorkflowState], WorkflowState]:
        """Build a node that executes a nested GraphAgentHarness."""
        return build_subgraph_node(self, phase, logger)

    def _build_phase_node(self, phase: Phase) -> Callable[[WorkflowState], WorkflowState]:
        """Build a PhaseNode that creates a DeerFlow Agent for execution.

        MODIFIED: Uses DeerFlow create_agent + Model Resolver instead of ToolExecutor.
        """
        resolver = self._resolver
        harness = self

        def execute(state: WorkflowState) -> WorkflowState:
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

            active_callbacks = harness.callbacks
            working_memory_before = _ctx_text(ctx, "_working_memory")

            # Step 1: Consume _retry_feedback
            retry_feedback: list[str] | None = None
            if "_retry_feedback" in ctx:
                retry_feedback = ctx.pop("_retry_feedback")

            # Step 2: Determine if new phase or retry
            is_retry = state["current_phase"] == phase.name

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
            # Task 4.2: wrap with TracingClientProxy so every LLM round-trip
            # emits a prompt_captured event to the registered callbacks.
            from .tracing_proxy import TracingClientProxy
            resolved_model_name = (
                getattr(model, "name", None)
                or getattr(model, "model", None)
                or getattr(model, "model_name", None)
            )

            # Tier 1 Commit B (T-B2): record the tier → role → model
            # resolution decision itself so Studio can show *why* this
            # phase runs on this specific provider/model combo.
            from ..callbacks.events import ModelResolvedEvent
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

            def _has_structured_selfcheck(payload: dict[str, Any]) -> bool:
                checklist = payload.get("plan_checklist", [])
                if isinstance(checklist, str):
                    try:
                        parsed = json.loads(checklist)
                        checklist = parsed if isinstance(parsed, list) else []
                    except Exception as exc:
                        logger.warning('[Harness] plan_checklist JSON parse failed: %s', exc)
                        checklist = []
                if isinstance(checklist, list) and checklist:
                    complete_items = 0
                    for item in checklist:
                        if not isinstance(item, dict):
                            continue
                        step = str(item.get("step", "")).strip()
                        quality_check = str(item.get("quality_check", "")).strip()
                        if step and quality_check:
                            complete_items += 1
                    if complete_items > 0:
                        return True

                # Backward compatibility fallback.
                reasoning_text = str(payload.get("reasoning", ""))
                evidence_raw = payload.get("evidence", [])
                if isinstance(evidence_raw, str):
                    evidence_raw = [evidence_raw]
                return len(reasoning_text) >= _MIN_FINISH_REASONING_LEN and bool(evidence_raw)

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
            planning_nudge_count = 0
            selfcheck_nudge_count = 0
            standard_nudge_count = 0
            total_nudge_count = 0
            plan_verified = False
            wm_snapshot = _ctx_text(ctx, "_working_memory")
            checkpoint_count = 0
            current_messages = list(messages)
            original_user_msg = messages[0] if messages else HumanMessage(content="")
            max_outer_iterations = max(20, phase.max_iterations * 2)
            outer_iterations = 0

            def _emit_nudge(nudge_type: str, nudge_count: int) -> None:
                for cb in active_callbacks:
                    try:
                        cb.on_nudge(phase.name, nudge_count, nudge_type=nudge_type)
                    except TypeError:
                        try:
                            cb.on_nudge(phase.name, nudge_count)
                        except Exception as exc:
                            logger.warning('[Harness] callback error: %s', exc)
                    except Exception as exc:
                        logger.warning('[Harness] callback error: %s', exc)

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
                    if (
                        not _has_structured_selfcheck(finish_result)
                        and selfcheck_nudge_count < phase.max_nudges
                        and total_nudge_count < phase.max_nudges * 2
                    ):
                        ctx.pop("_finish_task_result", None)
                        selfcheck_nudge_count += 1
                        total_nudge_count += 1
                        _emit_nudge("selfcheck", selfcheck_nudge_count)
                        current_messages = list(result_messages) + [
                            HumanMessage(content=_SELFCHECK_NUDGE)
                        ]
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
                        if latest_content and not has_tool_calls:
                            planning_nudge_count += 1
                            total_nudge_count += 1
                            if planning_nudge_count <= phase.max_nudges and total_nudge_count < phase.max_nudges * 2:
                                _emit_nudge("planning", planning_nudge_count)
                                current_messages = list(result_messages) + [
                                    HumanMessage(content=_PLANNING_NUDGE)
                                ]
                                continue
                        plan_verified = True

                # --- Checkpoint: compact context when working memory updates ---
                if plan_verified and wm_updated and wm_current:
                    checkpoint_count += 1
                    wm_snapshot = wm_current
                    removed_pairs = max((len(current_messages) - 2) // 2, 0)
                    # Tier 1 Commit B (T-A1 + T-A2): emit with full content
                    # and an optional sidecar ref for the compacted history.
                    from ..callbacks.events import (
                        CompactionEvent,
                        WorkingMemoryUpdateEvent,
                    )

                    wm_text = str(wm_current or "")
                    _safe_emit_event(
                        active_callbacks,
                        WorkingMemoryUpdateEvent(
                            phase_name=phase.name,
                            content_length=len(wm_text),
                            content=wm_text,
                        ),
                    )
                    # Sidecar write for compaction: see _save_compaction_sidecar
                    removed_messages = (
                        current_messages[:-2]
                        if len(current_messages) > 2
                        else []
                    )
                    sidecar_ref = self._save_compaction_sidecar(
                        run_id=run_id,
                        idx=checkpoint_count,
                        removed_messages=removed_messages,
                        storage_manager=storage_manager,
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
                if latest_content and not has_tool_calls:
                    standard_nudge_count += 1
                    total_nudge_count += 1
                    if standard_nudge_count <= phase.max_nudges and total_nudge_count < phase.max_nudges * 2:
                        _emit_nudge("standard", standard_nudge_count)
                        nudge_text = _build_standard_nudge_text(
                            standard_nudge_count,
                            latest_content,
                        )
                        current_messages = list(result_messages) + [HumanMessage(content=nudge_text)]
                        continue

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
                # Tier 1 Commit B (T-A1): emit the full wm text, not just length
                from ..callbacks.events import WorkingMemoryUpdateEvent

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

        return execute

    def _build_validation_node(
        self,
        phase: Phase,
    ) -> Callable[[WorkflowState], WorkflowState]:
        """Build a ValidationNode that runs the phase validator and routes."""
        harness = self

        def validate(state: WorkflowState) -> WorkflowState:
            active_callbacks = harness.callbacks
            if phase.validator is None:
                return _clone_state(state)

            next_state = _clone_state(state)
            passed, errors = phase.validator(next_state["context"])

            if passed:
                retry_key = phase.retry_target or phase.name
                # Tier 1 Commit A — T-B5 ValidationPassEvent
                # Capture the retry count BEFORE popping so "how many retries
                # did this phase consume before passing" is observable.
                retries_used = next_state["retry_counts"].get(retry_key, 0)
                next_state["retry_counts"].pop(retry_key, None)
                next_state["context"].pop("_validation_warnings", None)
                from ..callbacks.events import ValidationPassEvent
                _safe_emit_event(
                    active_callbacks,
                    ValidationPassEvent(
                        phase_name=phase.name,
                        retry_count=retries_used,
                    ),
                )
                return next_state

            # Validation failed
            retry_key = phase.retry_target or phase.name
            current_retries = next_state["retry_counts"].get(retry_key, 0)

            for cb in active_callbacks:
                cb.on_validation_fail(phase.name, errors, current_retries)

            if current_retries >= phase.max_retries:
                logger.warning(
                    "Phase '%s' exceeded max retries (%d). Continuing with warnings.",
                    phase.name,
                    phase.max_retries,
                )
                # Tier 1 Commit A — T-B12 RetryExhaustedEvent
                from ..callbacks.events import RetryExhaustedEvent
                _safe_emit_event(
                    active_callbacks,
                    RetryExhaustedEvent(
                        phase_name=phase.name,
                        max_retries=phase.max_retries,
                        final_errors=list(errors),
                    ),
                )
                next_state["context"]["_validation_warnings"] = errors
                return next_state

            # Inject retry feedback
            next_state["context"]["_retry_feedback"] = errors
            next_state["retry_counts"][retry_key] = current_retries + 1

            for cb in active_callbacks:
                target = phase.retry_target or phase.name
                cb.on_retry(phase.name, target, errors)

            return next_state

        return validate

    def _build_code_only_node(self, phase: Phase) -> Callable[[WorkflowState], WorkflowState]:
        """Build a pure code node (requires_llm=False)."""
        harness = self

        def execute(state: WorkflowState) -> WorkflowState:
            next_state = _clone_state(state)
            active_callbacks = harness.callbacks
            for cb in active_callbacks:
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

            # Discard retry feedback AFTER tools execute so tools can inspect it,
            # but before the state is returned to prevent leaking to the next phase.
            next_state["context"].pop("_retry_feedback", None)

            next_state["current_phase"] = phase.name

            for cb in active_callbacks:
                cb.on_phase_end(phase.name, dict(next_state["context"]), dict(next_state["metrics"]))

            return next_state

        return execute

    def _should_retry(self, phase: Phase) -> Callable[[WorkflowState], str]:
        """Build a conditional edge routing function."""
        next_node = self._get_next_phase_node(phase)

        def route(state: WorkflowState) -> str:
            if "_retry_feedback" in state["context"]:
                target = phase.retry_target or phase.name
                return f"{target}_execute"
            return next_node

        return route

    def _get_next_phase_node(self, phase: Phase) -> str:
        """Get the execute node name of the next phase, or END."""
        idx = next(
            (i for i, p in enumerate(self.phases) if p.name == phase.name),
            -1,
        )
        if idx < 0 or idx >= len(self.phases) - 1:
            return END
        return f"{self.phases[idx + 1].name}_execute"

    def _calc_recursion_limit(self) -> int:
        """Calculate LangGraph recursion limit.

        Accounts for cross-phase retries via retry_target: a phase retrying
        to an earlier phase effectively doubles both phases' node visits.
        """
        cross_phase_retries = sum(
            1 for p in self.phases if p.retry_target and p.retry_target != p.name
        )
        base = sum(p.max_retries for p in self.phases) * 2
        linear = len(self.phases) * 2
        return base + linear + cross_phase_retries * 4 + 10



