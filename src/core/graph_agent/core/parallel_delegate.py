"""Parallel delegate execution node builder for fan-out subgraphs.

Per PR-7 design (Gemini-reviewed 2026-04-27):
- ThreadPoolExecutor runs N child harnesses concurrently (Q4a: each child
  gets a deep-copied parent ctx -> write isolation, read shared baseline)
- context_bridge is broadcast to all children (Q5.1)
- Each child collects either a child_state or an exception
- Reducer + tolerance (Q2c, Q3d) is wired in Commit 3; this commit raises
  NotImplementedError after the parallel collection completes, so the
  parallel mechanism is independently testable.
"""
from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from .state import WorkflowState
from .types import ContextBridge, Phase


def _derive_child_thread_id(parent_thread_id: Any, phase_name: str, idx: int) -> str:
    """Derive a stable nested thread_id per parallel child."""
    base = str(parent_thread_id or "").strip()
    suffix = f"{phase_name}#{idx}"
    return f"{base}:{suffix}" if base else suffix


def _merge_child_io_errors(parent_ctx: dict[str, Any], child_ctx: dict[str, Any]) -> None:
    """Append child ``_io_errors`` into the parent context."""
    child_errors = child_ctx.get("_io_errors", [])
    if not isinstance(child_errors, list) or not child_errors:
        return
    existing = parent_ctx.get("_io_errors")
    normalized = [str(item) for item in child_errors]
    if isinstance(existing, list):
        existing.extend(normalized)
        return
    if existing is None:
        parent_ctx["_io_errors"] = normalized
        return
    parent_ctx["_io_errors"] = [str(existing), *normalized]


def build_parallel_delegate_node(
    harness: Any,
    phase: Phase,
    logger: logging.Logger,
) -> Callable[..., WorkflowState]:
    """Build a node that fan-outs into N parallel child GraphAgentHarness runs.

    Returns a graph_node closure that:
    1. Deep-copies parent ctx (write isolation per Q4a)
    2. Applies context_bridge.inputs to derive each child's runtime inputs
       (broadcast per Q5.1: same bridge to all children)
    3. Submits each child harness to ThreadPoolExecutor.run()
    4. Waits for all to complete; collects (child_state, exception) per slot
    5. **(Commit 2 stops here, raises NotImplementedError)**
       Commit 3 will:
       - Resolve phase.reducer_path -> callable reducer
       - Apply tolerance check on collected errors
       - If too many failures -> raise CompositeFailure
       - Else -> call reducer(parent_ctx, child_outputs, errors) -> merge
    """
    if not phase.parallel_subgraphs:
        raise ValueError(
            f"Phase '{phase.name}' has no parallel_subgraphs configured"
        )
    if phase.reducer_path is None:
        raise ValueError(
            f"Phase '{phase.name}' parallel_subgraphs requires reducer_path"
        )

    bridge = phase.context_bridge or ContextBridge()
    children = phase.parallel_subgraphs

    def execute(state: WorkflowState, config: RunnableConfig) -> WorkflowState:
        parent_ctx = copy.deepcopy(state["context"])
        active_callbacks = harness.callbacks
        retry_feedback: list[str] | None = None
        if "_retry_feedback" in parent_ctx:
            retry_feedback = parent_ctx.pop("_retry_feedback")

        for cb in active_callbacks:
            cb.on_phase_start(phase.name, dict(parent_ctx))

        configurable = (config or {}).get("configurable") or {}
        parent_run_context = configurable.get("_run_context")
        if parent_run_context is None:
            raise RuntimeError(
                f"ParallelDelegate phase '{phase.name}' invoked without "
                "RunContext in RunnableConfig['configurable']['_run_context']. "
                "All parallel-delegate invocations must originate from "
                "GraphAgentHarness.run() or .resume()."
            )
        run_options = harness._get_active_run_options(parent_run_context)

        # Build a broadcast child context once, then deepcopy per child.
        child_context: dict[str, Any] = copy.deepcopy(parent_ctx)
        for parent_key, child_input in bridge.inputs.items():
            if parent_key not in parent_ctx:
                logger.warning(
                    "[ParallelDelegate] Parent context key '%s' missing for phase '%s', "
                    "passing None to child input '%s'",
                    parent_key, phase.name, child_input,
                )
            child_context[child_input] = parent_ctx.get(parent_key)
        if retry_feedback is not None:
            child_context["_retry_feedback"] = retry_feedback

        child_trace_dir = run_options.get("trace_dir")
        if child_trace_dir is not None and not isinstance(child_trace_dir, Path):
            child_trace_dir = Path(child_trace_dir)

        parent_thread_id = run_options.get("thread_id") or parent_ctx.get("_thread_id")

        # Concurrent execution via ThreadPoolExecutor.
        # Each child gets its own thread_id slot to keep checkpointer state separated.
        outcomes: list[tuple[dict[str, Any] | None, Exception | None]] = [
            (None, None)
        ] * len(children)

        def _run_child(idx: int, child: Any) -> tuple[dict[str, Any] | None, Exception | None]:
            try:
                child_state = child.run(
                    initial_context=copy.deepcopy(child_context),
                    trace_dir=child_trace_dir if isinstance(child_trace_dir, Path) else None,
                    thread_id=_derive_child_thread_id(parent_thread_id, phase.name, idx),
                    artifact_saver=run_options.get("artifact_saver"),
                    runtime_inputs_map=(
                        dict(run_options.get("runtime_inputs"))
                        if isinstance(run_options.get("runtime_inputs"), dict)
                        else {}
                    ),
                    extra_callbacks=list(active_callbacks),
                )
                return (child_state, None)
            except Exception as exc:  # noqa: BLE001 - surfaced for tolerance check
                logger.warning(
                    "[ParallelDelegate] child %d (phase=%s) raised: %s",
                    idx, phase.name, exc,
                )
                return (None, exc)

        with ThreadPoolExecutor(max_workers=max(1, len(children))) as pool:
            futures: list[Future[tuple[dict[str, Any] | None, Exception | None]]] = [
                pool.submit(_run_child, idx, child)
                for idx, child in enumerate(children)
            ]
            for idx, fut in enumerate(futures):
                outcomes[idx] = fut.result()

        logger.info(
            "[ParallelDelegate] phase=%s collected %d outcomes (errors=%d)",
            phase.name,
            len(outcomes),
            sum(1 for _, exc in outcomes if exc is not None),
        )

        # Commit 3 will replace this raise with: resolve reducer, apply
        # tolerance, raise CompositeFailure or call reducer.
        raise NotImplementedError(
            f"Phase '{phase.name}': parallel_delegate reducer/tolerance "
            "is pending PR-7 Commit 3. Children completed in parallel "
            f"({len(outcomes)} outcomes), but aggregation is not yet wired."
        )

    return execute


__all__ = ["build_parallel_delegate_node"]
