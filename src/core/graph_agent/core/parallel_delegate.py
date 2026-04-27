"""Parallel delegate execution node builder for fan-out subgraphs.

Per PR-7 design (Gemini-reviewed 2026-04-27):
- ThreadPoolExecutor runs N child harnesses concurrently (Q4a: each child
  gets a deep-copied parent ctx -> write isolation, read shared baseline)
- context_bridge is broadcast to all children (Q5.1)
- Each child collects either a child_state or an exception
- Reducer + tolerance (Q2c, Q3d) aggregate successful child outputs and
  mark retryable failure when the failure ratio exceeds phase tolerance.
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


# Marker key written to ctx by execute closure when CompositeFailure
# is caught. Default validator (`default_parallel_delegate_validator`)
# pops this marker and returns retry feedback so RetryRouter can route
# to retry_target.
_FAILURE_MARKER_KEY = "_parallel_delegate_failed"


def default_parallel_delegate_validator(
    ctx: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Default validator auto-installed on parallel_delegate phases.

    Reads the failure marker written by the execute closure when
    CompositeFailure is caught. Returns (False, summaries) for retry
    routing; (True, []) when no failure flag is present (clean run).

    The marker is popped on access so subsequent retries start from a
    clean slate.
    """
    summaries = ctx.pop(_FAILURE_MARKER_KEY, None)
    if summaries is None:
        return (True, [])
    if isinstance(summaries, list):
        return (False, [str(item) for item in summaries])
    return (False, [str(summaries)])


class CompositeFailure(Exception):
    """Raised when too many parallel children fail relative to tolerance.

    Carries the per-child failure list so RetryRouter / upstream observers
    can inspect what went wrong without re-running.
    """

    def __init__(self, phase_name: str, failures: list[tuple[int, Exception]], total: int) -> None:
        self.phase_name = phase_name
        self.failures = failures
        self.total = total
        message = (
            f"ParallelDelegate phase '{phase_name}' exceeded tolerance: "
            f"{len(failures)}/{total} children failed"
        )
        super().__init__(message)


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


def _resolve_reducer_callable(reducer_path: str | None) -> Any:
    """Import and return the reducer callable at execute time.

    Loader-time validation (loader._validate_reducer_path) ensures the
    path resolves and points at a callable, but we re-resolve here in
    case the host process was restarted from a checkpoint and the import
    cache is cold.
    """
    if not reducer_path:
        raise RuntimeError(
            "parallel_delegate phase has no reducer_path "
            "(loader should have caught this - internal error)"
        )
    import importlib

    module_path, _, attr = reducer_path.rpartition(".")
    module = importlib.import_module(module_path)
    fn = getattr(module, attr)
    return fn


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
    5. Applies tolerance, calls reducer, and merges reducer output
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

        # Build child_outputs (successful) and errors (failed) lists per Gemini Q2c/Q3d.
        # "Failure" definition (Q3d): any of -
        #   1. child raised exception (collected in outcomes[idx][1])
        #   2. child finished but schema_validation == "failed" in finish_result
        #   3. child finished but no _finish_task_result at all (LLM didn't call finish_task)
        child_outputs: list[dict[str, Any]] = []
        failures: list[tuple[int, Exception]] = []  # (idx, exc) per failed child
        successful_states: list[dict[str, Any]] = []  # full child_state for metrics + ctx merge
        for idx, (child_state, exc) in enumerate(outcomes):
            if exc is not None:
                failures.append((idx, exc))
                continue
            if child_state is None:
                failures.append(
                    (idx, RuntimeError(f"child {idx} returned no state (no exception)"))
                )
                continue
            child_ctx = child_state.get("context", {}) if isinstance(child_state, dict) else {}
            finish_result = child_ctx.get("_finish_task_result") if isinstance(child_ctx, dict) else None
            if not isinstance(finish_result, dict):
                failures.append(
                    (
                        idx,
                        RuntimeError(
                            f"child {idx} (phase {phase.name}) did not call finish_task; "
                            "no _finish_task_result in ctx"
                        ),
                    )
                )
                continue
            if finish_result.get("schema_validation") == "failed":
                failures.append(
                    (
                        idx,
                        RuntimeError(
                            f"child {idx} (phase {phase.name}) finish_task schema validation failed: "
                            f"{finish_result.get('validation_error_text', '(no detail)')}"
                        ),
                    )
                )
                continue
            child_outputs.append(dict(child_ctx))
            successful_states.append(child_state)

        total_children = len(outcomes)
        fail_ratio = len(failures) / total_children if total_children else 0.0

        logger.info(
            "[ParallelDelegate] phase=%s success=%d failures=%d ratio=%.2f tolerance=%.2f",
            phase.name, len(child_outputs), len(failures), fail_ratio, phase.tolerance,
        )

        # Aggregate metrics from ALL children that produced a state (successful
        # AND semantically-failed-but-completed). Only true exception cases
        # (child_state is None) are skipped because there's no metrics to read.
        merged_metrics = dict(state["metrics"])
        for child_state, _exc in outcomes:
            if not isinstance(child_state, dict):
                continue  # exception case - no metrics available
            child_metrics = child_state.get("metrics", {})
            merged_metrics["total_input_tokens"] = (
                merged_metrics.get("total_input_tokens", 0)
                + int(child_metrics.get("total_input_tokens", 0))
            )
            merged_metrics["total_output_tokens"] = (
                merged_metrics.get("total_output_tokens", 0)
                + int(child_metrics.get("total_output_tokens", 0))
            )

        try:
            # Apply tolerance check (Q3d): if fail_ratio > tolerance, abort the phase.
            # Note: == is allowed (e.g., tolerance=0.0 + 0 failures works).
            if fail_ratio > phase.tolerance:
                raise CompositeFailure(phase.name, failures, total_children)

            # Resolve reducer dotted path to callable (per Gemini Q1c: stored as path,
            # imported at execute time to avoid checkpointer serialization issues).
            reducer_callable = _resolve_reducer_callable(phase.reducer_path)

            # Build errors-as-list for reducer signature (Q2c).
            errors_for_reducer: list[Exception] = [exc for _, exc in failures]

            # Call reducer(parent_ctx, child_outputs, errors) -> merge dict.
            # Reducer is responsible for combining N child outputs into a single
            # business-data dict that the parent phase can merge into ctx.
            try:
                reduced = reducer_callable(parent_ctx, child_outputs, errors_for_reducer)
            except Exception as exc:
                raise CompositeFailure(
                    phase.name,
                    [(-1, exc)],
                    total_children,
                ) from exc

            if not isinstance(reduced, dict):
                raise CompositeFailure(
                    phase.name,
                    [(-1, TypeError(f"reducer must return dict, got {type(reduced).__name__}"))],
                    total_children,
                )

            # Merge reducer output into parent ctx.
            # Note: reducer is responsible for namespacing - it returns dict keys
            # that will be set on parent_ctx directly. Framework keys ('_'-prefixed)
            # are not filtered (reducer trust contract).
            parent_ctx.update(reduced)

            # _io_errors merge restricted to successful children: failed ones already
            # surfaced via failures/errors_for_reducer.
            for child_state in successful_states:
                child_ctx = child_state.get("context", {}) if isinstance(child_state, dict) else {}
                if isinstance(child_ctx, dict):
                    _merge_child_io_errors(parent_ctx, child_ctx)

        except CompositeFailure as composite_exc:
            # Convert to ctx state for default validator (PR-7.2): write failure
            # summaries to _parallel_delegate_failed marker, _io_errors for ctx
            # observability. Do NOT raise - let validate_node + RetryRouter route
            # the retry through the standard pipeline.
            failure_summaries = [
                f"child {idx}: {type(child_exc).__name__}: {child_exc}"
                for idx, child_exc in composite_exc.failures
            ]
            parent_ctx[_FAILURE_MARKER_KEY] = failure_summaries
            existing_io_errors = parent_ctx.get("_io_errors", []) or []
            parent_ctx["_io_errors"] = list(existing_io_errors) + failure_summaries
            logger.warning(
                "[ParallelDelegate] phase=%s caught CompositeFailure (%d failures); "
                "marking ctx for RetryRouter (will retry if max_retries not exhausted)",
                phase.name, len(composite_exc.failures),
            )

        new_state: WorkflowState = {
            "context": parent_ctx,
            "messages": [],
            "current_phase": phase.name,
            "retry_counts": dict(state["retry_counts"]),
            "metrics": merged_metrics,
        }

        for cb in active_callbacks:
            cb.on_phase_end(phase.name, dict(parent_ctx), dict(merged_metrics))

        return new_state

    return execute


__all__ = [
    "CompositeFailure",
    "_FAILURE_MARKER_KEY",
    "build_parallel_delegate_node",
    "default_parallel_delegate_validator",
]
