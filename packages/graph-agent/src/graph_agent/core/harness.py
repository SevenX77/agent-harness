"""GraphAgentHarness — multi-phase Agent orchestration engine based on LangGraph.

Builds a LangGraph StateGraph from a list of Phase definitions. Each phase
creates a LangChain agent that runs its own agent loop
with the phase-specific model, tools, system prompt, and middleware.

Key design: messages reset on new phase entry but are preserved during retries,
so the LLM can see its previous errors and fix them.

MODIFIED: Refactored to use LangChain create_agent + Model Resolver instead
of the old ToolExecutor + LLMGateway.
"""

from __future__ import annotations

import copy
import logging
import sys
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from graph_agent.callbacks.base import Callback
from graph_agent.cognitive.finish import finish_task
from graph_agent.cognitive.memory import update_working_memory
from graph_agent.core.exceptions import (
    CheckpointError,
    SkillLoadError,
    StateTransformError,
    TraceWriteError,
)
from graph_agent.core.graph_builder import GraphBuilder
from graph_agent.core.manifest import ContextBridge
from graph_agent.core.phase_executor import PhaseExecutor
from graph_agent.core.retry_router import RetryRouter
from graph_agent.core.run_context import RunContext
from graph_agent.core.state import (
    BusinessData,
    FrameworkState,
    StateManager,
    WorkflowState,
    verify_state_invariants,
)
from graph_agent.core.types import Phase

logger = logging.getLogger(__name__)

__all__ = [
    "ContextBridge",
    "GraphAgentHarness",
    "Harness",
    "Phase",
    "finish_task",
    "update_working_memory",
]


def _resolve_studio_checkpointer_spec(
    spec: str,
    context_managers: list[Any] | None = None,
) -> Any:
    """Parse a ``STUDIO_CHECKPOINTER`` env-var value into a checkpointer.

    Supported forms (Task 7.7):

    * ``memory`` — LangGraph ``InMemorySaver``
    * ``sqlite:<path>`` — ``SqliteSaver`` opened at ``<path>`` (the
      ``:memory:`` sentinel and ``file:...`` URIs are passed through
      untouched; bare paths are resolved by GraphAgent's local helper)
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
        raw = spec[len("sqlite:") :]
        from langgraph.checkpoint.sqlite import SqliteSaver

        from graph_agent.core.checkpointer import _resolve_sqlite_conn_str

        conn_str = _resolve_sqlite_conn_str(raw or "store.db")
        saver_cm = SqliteSaver.from_conn_string(conn_str)
        saver = saver_cm.__enter__()
        if context_managers is not None:
            context_managers.append(saver_cm)
        saver.setup()
        logger.info("[Harness] STUDIO_CHECKPOINTER=sqlite:%s → SqliteSaver", conn_str)
        return saver

    if spec.startswith(("postgres://", "postgresql://")):
        from langgraph.checkpoint.postgres import PostgresSaver

        saver_cm = PostgresSaver.from_conn_string(spec)
        saver = saver_cm.__enter__()
        if context_managers is not None:
            context_managers.append(saver_cm)
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


class _HeartbeatPulser:
    """Background thread that emits periodic HeartbeatEvent during a run.

    Tier 1 Commit D (T-B13). Uses a plain daemon thread rather than
    asyncio because ``GraphAgentHarness.run`` is synchronous — LangGraph
    ``invoke`` blocks the calling thread through every tool call, and an
    asyncio-backed timer would starve in that window. The thread only
    touches an ``Event`` for cancellation + a timestamp, so it never
    races with the main phase loop.
    """

    def __init__(
        self,
        callbacks: list[Callback],
        *,
        interval_seconds: float = 30.0,
    ) -> None:
        self._callbacks = callbacks
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_monotonic = 0.0
        # Mutable handle so external code can update current_phase on
        # the pulser without having to pass the harness instance in.
        self.current_phase: str | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._started_monotonic = time.monotonic()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="graph_agent.heartbeat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                from graph_agent.callbacks.events import HeartbeatEvent

                event = HeartbeatEvent(
                    current_phase=self.current_phase,
                    elapsed_seconds=round(time.monotonic() - self._started_monotonic, 3),
                    memory_usage_mb=_safe_memory_usage_mb(),
                )
                _safe_emit_event(self._callbacks, event)
            except Exception:  # noqa: BLE001
                logger.exception("[Heartbeat] tick failed; continuing")


def _safe_memory_usage_mb() -> float | None:
    """Best-effort resident-set-size in MiB; None when the read fails.

    Tries ``resource.getrusage`` (stdlib, Unix) first because it's the
    lightest read. Falls back to ``psutil`` when the platform makes
    rusage unreliable (Windows, containers with cgroup quirks). Returns
    None silently rather than raising so a bad reading never takes down
    the heartbeat.
    """
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # On Linux ru_maxrss is in kilobytes; on macOS it's bytes.
        if sys.platform == "darwin":
            return round(usage / (1024 * 1024), 2)
        return round(usage / 1024, 2)
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "[Harness] resource.getrusage failed: %s; falling back to psutil",
            exc,
        )
    try:
        import psutil  # type: ignore[import-untyped]  # psutil runtime dependency has no local stubs.

        rss = cast(float, psutil.Process().memory_info().rss)
        return round(rss / (1024 * 1024), 2)
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "[Harness] psutil memory read failed: %s; heartbeat will emit memory=None",
            exc,
        )
        return None


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
        cloned_data = state["data"].model_copy(deep=True)
    except TypeError as exc:
        raise StateTransformError(
            f"deepcopy failed for state field data: {exc}",
            context={"field": "data", "type": type(state["data"]).__name__},
        ) from exc
    try:
        cloned_flow = state["flow"].model_copy(deep=True)
    except TypeError as exc:
        raise StateTransformError(
            f"deepcopy failed for state field flow: {exc}",
            context={"field": "flow", "type": type(state["flow"]).__name__},
        ) from exc
    try:
        cloned_msgs = copy.deepcopy(state["messages"])
    except TypeError as exc:
        raise StateTransformError(
            f"deepcopy failed for state field messages: {exc}",
            context={"field": "messages", "type": type(state["messages"]).__name__},
        ) from exc
    return WorkflowState(data=cloned_data, flow=cloned_flow, messages=cloned_msgs)


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
        *,
        callbacks: list[Callback] | None = None,
        io_config: dict[str, Any] | None = None,
        context_mapping: dict[str, str] | None = None,
        skill_dir: Path | None = None,
        checkpointer: Any = "auto",
        model_resolver: Any | None = None,
    ) -> None:
        """Initialize a harness with fixed phases and shared runtime services."""
        if not phases:
            raise SkillLoadError("GraphAgentHarness requires at least one phase")
        self.phases = phases
        self.callbacks = callbacks or []
        self._io_config = io_config
        self._context_mapping = context_mapping
        self._skill_dir = skill_dir
        if model_resolver is None:
            from graph_agent_gateway.exceptions import GatewayResolverMissingError

            raise GatewayResolverMissingError(phase_name="<harness>")
        self._resolver = model_resolver
        self._checkpointer_cms: list[Any] = []
        self._checkpointer = self._resolve_checkpointer(checkpointer)
        # D-7.3 — compile-time routing collaborator; reused across runs.
        self._retry_router = RetryRouter(phases)
        # D-7.1 — compile-time topology builder, reused across runs.
        # D-7.2 Phase B: GraphBuilder no longer needs PhaseExecutor at
        # construction; the executor is built per-run inside ``run()`` /
        # ``resume()`` and passed through LangGraph
        # ``RunnableConfig["configurable"]``. Graph node closures extract
        # it from the config on each invocation.
        self._graph_builder = GraphBuilder(
            phases,
            retry_router=self._retry_router,
            checkpointer=self._checkpointer,
        )
        self._graph = self._graph_builder.build()

    def _resolve_checkpointer(self, checkpointer: Any) -> Any:
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
                    return _resolve_studio_checkpointer_spec(
                        override,
                        self._checkpointer_cms,
                    )
                except Exception as exc:
                    raise ValueError(
                        f"STUDIO_CHECKPOINTER={override!r} could not be resolved: {exc}"
                    ) from exc
            try:
                from graph_agent.core.checkpointer import get_checkpointer

                db_path = os.environ.get("GRAPH_AGENT_CHECKPOINTER_DB")
                cp = get_checkpointer(db_path=db_path)
                logger.info("[Harness] Checkpointer: %s", type(cp).__name__)
                return cp
            except Exception as exc:
                raise CheckpointError(
                    f"checkpointer init failed: {exc}",
                    context={"checkpoint_dir": None, "checkpointer": "auto"},
                ) from exc
        return checkpointer  # None or explicit instance

    def close(self) -> None:
        """Close any checkpointer context managers opened by this harness."""
        errors: list[BaseException] = []
        while self._checkpointer_cms:
            cm = self._checkpointer_cms.pop()
            try:
                cm.__exit__(None, None, None)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
        if errors:
            raise RuntimeError(
                f"Failed to close {len(errors)} checkpointer context manager(s)"
            ) from errors[0]

    def run(
        self,
        initial_context: dict[str, Any] | None = None,
        trace_dir: Path | None = None,
        thread_id: str | None = None,
        artifact_saver: Callable[..., Any] | None = None,
        storage_manager: Any | None = None,
        runtime_inputs_map: dict[str, Any] | None = None,
        unattended: bool = False,
        extra_callbacks: list[Callback] | None = None,
        persistent_runtime_inputs: dict[str, Any] | None = None,
        persistent_storage_config: dict[str, Any] | None = None,
        **runtime_inputs: Any,
    ) -> WorkflowState:
        """Execute the complete multi-phase workflow.

        ``extra_callbacks`` are appended to ``self.callbacks`` for the
        duration of this run without mutating the attribute. Used by
        ``subgraph.execute`` to forward parent callbacks into a child
        harness concurrency-safely (a child harness instance may be
        invoked from multiple parent runs in parallel; mutating
        ``child.callbacks`` directly would cross-wire them).

        ``persistent_runtime_inputs`` and ``persistent_storage_config``
        are the opt-in knobs that let a HITL ``resume()`` rehydrate
        per-run state from the LangGraph checkpointer. Both are stashed
        into ``initial_state["flow"]`` so they ride along the
        checkpointed workflow state; both are pre-flighted through
        ``json.dumps`` at ``run()`` entry so a non-serialisable payload
        fails loudly here, not later at checkpoint-write time.

        * ``persistent_runtime_inputs`` — the caller-declared safe
          subset of ``runtime_inputs``; a common pattern is to pass
          ``{"pipeline": "p1", "project_id": "x"}`` here and pass
          arbitrary-python objects (database handles, model clients) via
          ``runtime_inputs`` that shouldn't cross a checkpoint boundary.
        * ``persistent_storage_config`` — kwargs for rebuilding a
          ``StorageManager`` on resume. ``run_id`` / ``skill_id`` are
          auto-filled from the current run if the caller omits them, so
          the minimal call is ``{"workspace_root": ...}``. Callers who
          already passed ``storage_manager=`` above get the runtime
          instance for this run; ``persistent_storage_config`` only
          affects what ``resume()`` sees after a checkpoint reload.

        Passing neither preserves the pre-D-7.2 behaviour: ``resume()``
        rebuilds with ``storage_manager=None`` and whatever
        ``runtime_inputs_map`` the caller re-supplies.
        """
        effective_runtime_inputs = dict(runtime_inputs_map or {})
        effective_runtime_inputs.update(runtime_inputs)
        if initial_context is None:
            initial_context = self._build_context_from_io(effective_runtime_inputs)

        effective_trace_dir = trace_dir
        if effective_trace_dir is None and initial_context.get("output_dir"):
            effective_trace_dir = Path(initial_context["output_dir"])

        initial_state = WorkflowState(
            data=BusinessData.model_validate(dict(initial_context)),
            flow=FrameworkState(metrics={"total_input_tokens": 0, "total_output_tokens": 0}),
            messages=[],
        )

        if persistent_runtime_inputs is not None or persistent_storage_config is not None:
            import json

            payload: dict[str, Any] = {}
            if persistent_runtime_inputs is not None:
                payload["runtime_inputs"] = persistent_runtime_inputs
            if persistent_storage_config is not None:
                payload["storage_config"] = persistent_storage_config
            try:
                json.dumps(payload)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "persistent_runtime_inputs / persistent_storage_config "
                    "must be JSON-serialisable so resume() can read them "
                    "back from the LangGraph checkpointer. Pre-flight "
                    f"json.dumps failed: {exc}"
                ) from exc

        tid = thread_id or str(uuid.uuid4())
        # Tier 1 Commit A: run_id identifies a single harness.run invocation.
        # thread_id may be reused across multiple runs (resume scenarios);
        # run_id is always fresh so Studio can distinguish each execution.
        run_id = uuid.uuid4().hex[:12]
        is_resume = thread_id is not None
        run_start_monotonic = time.monotonic()
        initial_state = StateManager.update_framework(
            initial_state,
            thread_id=tid,
            run_id=run_id,
            unattended=bool(unattended),
        )

        # D-post session: stash the opt-in persistent knobs into the
        # workflow state so the LangGraph checkpointer persists them and
        # resume() can rebuild runtime_inputs / storage_manager from them.
        if persistent_runtime_inputs is not None:
            initial_state = StateManager.update_framework(
                initial_state,
                persistent_runtime_inputs=dict(persistent_runtime_inputs),
            )
        if persistent_storage_config is not None:
            effective_storage_config = dict(persistent_storage_config)
            # Auto-fill run_id so the caller doesn't have to know the
            # freshly-minted UUID up front. ``skill_id`` is filled from
            # the harness's loaded skill if the caller omitted it.
            effective_storage_config.setdefault("run_id", run_id)
            if "skill_id" not in effective_storage_config:
                derived_skill_id = getattr(self, "_skill_id", "") or "unknown"
                effective_storage_config["skill_id"] = derived_skill_id
            initial_state = StateManager.update_framework(
                initial_state,
                persistent_storage_config=effective_storage_config,
            )

        verify_state_invariants(initial_state)

        config: dict[str, Any] = {
            "recursion_limit": self._graph_builder.recursion_limit(),
            "configurable": {"thread_id": tid},
        }

        # D-7.2 Phase B: build per-run RunContext + PhaseExecutor as
        # locals. No harness-instance state carries run-specific data —
        # concurrent ``run()`` calls on the same harness instance now
        # work because the executor lives on this call's stack and
        # propagates through LangGraph config["configurable"].
        active_callbacks = list(self.callbacks) if hasattr(self, "callbacks") else []
        # Merge extra_callbacks (from subgraph parent forwarding) without
        # mutating self.callbacks — concurrency-safe because the merged
        # list is local to this invocation.
        if extra_callbacks:
            for cb in extra_callbacks:
                if cb not in active_callbacks:
                    active_callbacks.append(cb)
        run_context = RunContext(
            thread_id=tid,
            run_id=run_id,
            trace_dir=effective_trace_dir,
            runtime_inputs=dict(effective_runtime_inputs),
            storage_manager=storage_manager,
            artifact_saver=artifact_saver,
            callbacks=tuple(active_callbacks),
            unattended=bool(unattended),
        )

        # Tier 1 Commit A — T-B1 RunStartedEvent
        from graph_agent.callbacks.events import (
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
                initial_context=_safe_jsonable_dict(initial_state["data"].model_dump()),
            ),
        )

        # Tier 1 Commit D — T-B13 HeartbeatEvent daemon thread
        heartbeat = _HeartbeatPulser(active_callbacks)
        heartbeat.start()

        # D-7.2 Phase B: per-run PhaseExecutor threaded through LangGraph
        # config — graph node closures extract it from
        # ``config["configurable"]["_phase_executor"]`` on each invocation.
        phase_executor = PhaseExecutor(
            active_callbacks,
            run_context=run_context,
            heartbeat=heartbeat,
            resolver=self._resolver,
            save_compaction_sidecar=type(self)._save_compaction_sidecar,
        )
        config["configurable"]["_phase_executor"] = phase_executor
        config["configurable"]["_run_context"] = run_context

        try:
            result = self._graph.invoke(initial_state, config=config)
            result_context = result["data"].model_dump()

            # Tier 2 — T-B11: if the run stopped because a middleware
            # raised an interrupt (request_human_input / clarification),
            # emit InterruptedEvent so tracing.jsonl carries the pause
            # marker. We detect this by inspecting post-invoke state;
            # `get_thread_status` uses the same shape.
            #
            # Cohesion plan 方针 2.1 (2026-04-26): when the run is paused
            # on AWAITING_INPUT we must NOT auto-save outputs (the data
            # the user is being asked for has not been provided yet) and
            # the terminating RunEndedEvent must carry status="interrupted"
            # so Studio's "needs input" queue keeps the run.
            is_awaiting_input = False
            try:
                status = self.get_thread_status(tid)
                if status.get("status") == "AWAITING_INPUT":
                    is_awaiting_input = True
                    from graph_agent.callbacks.events import InterruptedEvent

                    clar = status.get("clarification", {}) or {}
                    _safe_emit_event(
                        active_callbacks,
                        InterruptedEvent(
                            phase_name=str(result["flow"].current_phase or ""),
                            thread_id=tid,
                            question=clar.get("question"),
                            clarification_type=clar.get("clarification_type"),
                            options=list(clar.get("options") or []),
                        ),
                    )
                elif status.get("status") == "CRASHED":
                    raise RuntimeError(
                        "Post-invoke interrupt status check failed: "
                        f"{status.get('reason') or 'unknown error'}"
                    )
            except Exception as exc:  # noqa: BLE001
                logger.exception("[Harness] post-invoke interrupt detection failed")
                raise RuntimeError(
                    "Post-invoke interrupt detection failed; refusing to "
                    "auto-save outputs or mark the run completed."
                ) from exc

            if is_awaiting_input:
                # Skip outputs auto-save: the run is paused waiting for
                # user input, the workflow has not produced final outputs.
                # Trace save is also skipped — the run is still alive,
                # resume() will append further trace records and save
                # once the run actually terminates.
                logger.info(
                    "[Harness] run %s paused on AWAITING_INPUT; skipping "
                    "outputs/trace auto-save until resume completes",
                    run_id,
                )
                _safe_emit_event(
                    active_callbacks,
                    RunEndedEvent(
                        run_id=run_id,
                        thread_id=tid,
                        status="interrupted",
                        final_context=_safe_jsonable_dict(result_context),
                        wall_time_seconds=round(time.monotonic() - run_start_monotonic, 3),
                    ),
                )
                return cast(WorkflowState, result)

            # Auto-save outputs via IOManager if configured
            if self._io_config and self._io_config.get("outputs"):
                self._save_outputs_via_io(
                    result_context,
                    effective_runtime_inputs,
                    artifact_saver=artifact_saver,
                    storage_manager=storage_manager,
                )

            # Auto-save TracingCallback trace to output dir
            from graph_agent.callbacks.tracing import TracingCallback

            trace_output = effective_trace_dir
            if trace_output is None and result_context.get("output_dir"):
                trace_output = Path(result_context["output_dir"])
            if trace_output:
                for cb in active_callbacks:
                    if isinstance(cb, TracingCallback):
                        try:
                            saved = cb.save(trace_output)
                            result = StateManager.update_framework(
                                result,
                                trace_path=saved,
                            )
                        except Exception as exc:
                            raise TraceWriteError(
                                f"trace save failed: {exc}",
                                context={"trace_path": str(trace_output)},
                            ) from exc
                        break

            # Tier 1 Commit A — T-B1 RunEndedEvent on success
            _safe_emit_event(
                active_callbacks,
                RunEndedEvent(
                    run_id=run_id,
                    thread_id=tid,
                    status="completed",
                    final_context=_safe_jsonable_dict(result_context),
                    wall_time_seconds=round(time.monotonic() - run_start_monotonic, 3),
                ),
            )
            return cast(WorkflowState, result)
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
            # Always stop the heartbeat — don't leak daemon threads even
            # after a crash; _HeartbeatPulser.stop is idempotent.
            try:
                heartbeat.stop()
                heartbeat.join(timeout=1.0)
            except Exception:  # noqa: BLE001
                logger.warning("[Harness] heartbeat stop failed", exc_info=True)

    def _get_active_run_options(self, run_context: RunContext | None) -> dict[str, Any]:
        """Return active-run options for nested subgraph / parallel_map.

        Projects the caller-supplied RunContext back into the legacy dict
        shape that ``subgraph.execute`` still consumes. ``run_context``
        is threaded through LangGraph's
        ``config["configurable"]["_run_context"]`` so this method never
        reads mutable harness-instance state. ``None`` returns an empty
        dict (defensive default for tests / callers that forgot to pass).
        """
        if run_context is None:
            return {}
        return {
            "trace_dir": run_context.trace_dir,
            "thread_id": run_context.thread_id,
            "artifact_saver": run_context.artifact_saver,
            "storage_manager": run_context.storage_manager,
            "runtime_inputs": dict(run_context.runtime_inputs),
            "unattended": run_context.unattended,
        }

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
            from graph_agent.callbacks.serialize import to_jsonable_dict

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

        from graph_agent.io.manager import IOManager

        io_mgr = IOManager(self._io_config)
        raw_inputs = io_mgr.load_inputs(**runtime_inputs)

        if self._context_mapping:
            from graph_agent.io.context_resolver import ContextResolver

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
        """Auto-save outputs via IOManager.

        Cohesion plan 方针 2.2 (2026-04-26): write failures (disk full,
        permission denied, schema/target mismatch) used to be swallowed
        by ``except Exception: logger.warning(...)`` here, so the run
        was reported as ``completed`` even though the artifact never
        landed. Failures now propagate — the outer ``run()`` try/except
        converts them into ``RunEndedEvent(status="crashed")`` and
        re-raises so callers know the data did not persist.
        """
        from graph_agent.io.manager import IOManager

        io_mgr = IOManager(self._io_config)  # type: ignore[arg-type]
        logger.info(
            "[Harness] auto-saving %d declared output(s)",
            len(self._io_config.get("outputs", []) if self._io_config else []),
        )
        io_mgr.save_outputs(
            context,
            output_dir=context.get("output_dir"),
            project_id=runtime_inputs.get("project_id"),
            artifact_saver=artifact_saver,
            storage_manager=storage_manager,
        )

    def get_thread_status(self, thread_id: str) -> dict[str, Any]:
        """Introspect a thread's LangGraph-level state without resuming it.

        Task I-1 — the "Human-in-the-loop status sync protocol" Gemini
        flagged as Studio's next missing surface. Lets Studio's UI ask
        "is this thread waiting for my input / still running / done /
        crashed?" without tailing tracing.jsonl.

        Returns a dict with the shape::

            {"status": "AWAITING_INPUT" | "COMPLETED" | "RUNNING" | "NOT_FOUND" | "CRASHED",
             "clarification": {"question", "clarification_type", "options"}}  # AWAITING_INPUT only
             "error": str                                                      # CRASHED only

        Reads the checkpointer state directly so two processes cannot
        disagree about which thread is paused.
        """
        if self._checkpointer is None:
            return {"status": "NOT_FOUND", "reason": "no_checkpointer"}

        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

        try:
            # LangGraph's official API — returns a StateSnapshot. Different
            # versions spelled this differently, cover both.
            if hasattr(self._graph, "get_state"):
                snapshot = self._graph.get_state(config)
            else:
                get_tuple = getattr(self._checkpointer, "get_tuple", None)
                if get_tuple is None:
                    return {"status": "NOT_FOUND", "reason": "no_get_state"}
                snapshot = get_tuple(config)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[Harness] get_thread_status(%s): snapshot read failed — %s",
                thread_id,
                exc,
            )
            return {"status": "CRASHED", "reason": str(exc)}

        if not snapshot:
            return {"status": "NOT_FOUND"}

        next_nodes = getattr(snapshot, "next", None) or ()
        tasks = getattr(snapshot, "tasks", None) or ()

        # Identify an outstanding clarification request. Each PregelTask
        # carries an ``interrupts`` tuple populated by LangGraph when a
        # middleware ``Command(goto=END)`` fires — our clarification +
        # request_human_input middlewares both go through this.
        for task in tasks:
            interrupts = getattr(task, "interrupts", None) or ()
            if not interrupts:
                continue
            last = interrupts[-1]
            payload = getattr(last, "value", None)
            clarification: dict[str, Any] = {}
            if isinstance(payload, dict):
                clarification = {
                    "question": payload.get("question") or payload.get("message"),
                    "clarification_type": payload.get("clarification_type")
                    or payload.get("type")
                    or "missing_info",
                    "options": payload.get("options") or [],
                }
            else:
                clarification = {
                    "question": str(payload) if payload is not None else None,
                    "clarification_type": "missing_info",
                    "options": [],
                }
            return {"status": "AWAITING_INPUT", "clarification": clarification}

        if not next_nodes:
            return {"status": "COMPLETED"}

        # ``next`` present but no interrupt → either still running in
        # another process, or crashed and left the graph partially
        # executed. We can't distinguish the two from a snapshot alone,
        # so we surface RUNNING and leave CRASHED to callers that correlate
        # with the InternalErrorEvent in tracing.jsonl.
        return {"status": "RUNNING", "next": list(next_nodes)}

    def resume(
        self,
        state: WorkflowState,
        human_input: str,
        thread_id: str | None = None,
        trace_dir: Path | None = None,
        artifact_saver: Callable[..., Any] | None = None,
        runtime_inputs_map: dict[str, Any] | None = None,
    ) -> WorkflowState:
        """Resume execution after a request_human_input interrupt.

        ``runtime_inputs_map`` lets the caller restore the per-run inputs
        that the original ``run()`` received. The field is not persisted
        in the LangGraph checkpointer (arbitrary runtime_inputs may carry
        non-picklable values), so the caller that resumes a mid-run
        interrupt must re-supply it if downstream components (e.g.
        ``StorageManager`` resolving ``pipeline_prefix``) read it via
        ``_get_active_run_options``. Passing ``None`` (the default) causes
        ``resume()`` to look for a persisted copy in
        ``state['flow'].persistent_runtime_inputs`` that an
        earlier ``run(persistent_runtime_inputs=...)`` may have stashed;
        if that key is absent too, the behaviour falls back to the
        pre-D-7.2 empty dict.

        The ``StorageManager`` is rebuilt from
        ``state['flow'].persistent_storage_config`` when present
        (stashed by an earlier ``run(persistent_storage_config=...)``) so
        sidecar writes after resume land under the same
        ``_history/{run_id}/`` directory as pre-pause artifacts. When
        the stashed config is absent or rebuild fails, the executor
        runs with ``storage_manager=None`` and sidecar writes degrade
        to a no-op (matching pre-PR-#3 behaviour).
        """
        from langchain_core.messages import ToolMessage

        state = _clone_state(state)

        tool_call_id = ""
        for msg in reversed(state["messages"]):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.get("name") == "request_human_input":
                        tool_call_id = str(tc.get("id") or "")
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

        effective_thread_id = thread_id or state["flow"].thread_id
        config: dict[str, Any] = {
            "recursion_limit": self._graph_builder.recursion_limit(),
            "configurable": {"thread_id": effective_thread_id},
        }

        # D-7.2 Phase B: build per-run RunContext + PhaseExecutor as
        # locals here too, matching run()'s pattern. run_id is inherited
        # from the paused state so compaction sidecars written during the
        # resumed run share the same ``_history/{run_id}/`` directory as
        # sidecars from the original run — Studio folds pre-pause and
        # post-resume sidecars under one thread.
        active_callbacks = list(self.callbacks) if hasattr(self, "callbacks") else []
        inherited_run_id = state["flow"].run_id or ""

        # D-post session P0-2.1: rehydrate runtime_inputs / storage_manager
        # from the state the checkpointer replayed, when an earlier run()
        # opted in via ``persistent_runtime_inputs`` /
        # ``persistent_storage_config``. Explicit caller-supplied
        # ``runtime_inputs_map`` still wins (e.g. test harness overrides).
        restored_runtime_inputs: dict[str, Any] = {}
        if runtime_inputs_map:
            restored_runtime_inputs = dict(runtime_inputs_map)
        else:
            persisted = state["flow"].persistent_runtime_inputs
            if isinstance(persisted, dict):
                restored_runtime_inputs = dict(persisted)

        restored_storage_manager: Any | None = None
        persisted_sc = state["flow"].persistent_storage_config
        if isinstance(persisted_sc, dict) and persisted_sc:
            sc_kwargs = dict(persisted_sc)
            # Prefer the inherited run_id so artifacts land in the
            # original ``_history/{run_id}/`` tree; fall back to whatever
            # the persisted config declared, or "unknown" as last resort
            # (StorageManager's constructor rejects empty run_id, so we
            # must pass a non-empty string).
            sc_kwargs["run_id"] = (
                inherited_run_id or str(sc_kwargs.get("run_id") or "") or "unknown"
            )
            try:
                from graph_agent.io.storage import StorageManager

                restored_storage_manager = StorageManager(**sc_kwargs)
            except Exception as exc:  # noqa: BLE001
                # Fail soft so an otherwise-recoverable resume isn't
                # killed by a malformed persisted config; the run
                # continues with sidecar writes no-op'd.
                logger.warning(
                    "[Harness] resume could not rebuild StorageManager from "
                    "_persistent_storage_config=%r: %s; continuing with "
                    "storage_manager=None (compaction sidecars will no-op)",
                    sc_kwargs,
                    exc,
                )

        run_context = RunContext(
            thread_id=str(effective_thread_id or ""),
            run_id=inherited_run_id,
            trace_dir=trace_dir if isinstance(trace_dir, Path) else None,
            runtime_inputs=restored_runtime_inputs,
            storage_manager=restored_storage_manager,
            artifact_saver=artifact_saver,
            callbacks=tuple(active_callbacks),
            unattended=state["flow"].unattended,
        )

        # Tier 1 Commit D — T-B13 HeartbeatEvent daemon thread.
        heartbeat = _HeartbeatPulser(active_callbacks)
        heartbeat.current_phase = state["flow"].current_phase or None
        heartbeat.start()

        # D-7.2 Phase B: per-run PhaseExecutor threaded through config.
        phase_executor = PhaseExecutor(
            active_callbacks,
            run_context=run_context,
            heartbeat=heartbeat,
            resolver=self._resolver,
            save_compaction_sidecar=type(self)._save_compaction_sidecar,
        )
        config["configurable"]["_phase_executor"] = phase_executor
        config["configurable"]["_run_context"] = run_context

        # Tier 2 — T-B11: announce the resume to the trace.
        from graph_agent.callbacks.events import ResumedEvent

        _safe_emit_event(
            self.callbacks,
            ResumedEvent(
                thread_id=str(effective_thread_id or ""),
                human_input=human_input,
                resumed_from_phase=state["flow"].current_phase or None,
            ),
        )

        try:
            result = self._graph.invoke(state, config=config)
            return cast(WorkflowState, result)
        except Exception as exc:
            # Tier 1 Commit A — T-B14 InternalErrorEvent at harness.resume
            from graph_agent.callbacks.events import InternalErrorEvent

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
            try:
                heartbeat.stop()
                heartbeat.join(timeout=1.0)
            except Exception:  # noqa: BLE001
                logger.warning("[Harness] heartbeat stop failed", exc_info=True)


Harness = GraphAgentHarness
