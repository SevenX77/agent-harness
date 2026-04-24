"""Subgraph execution node builder for nested GraphAgentHarness phases."""

from __future__ import annotations
import copy

from collections.abc import Callable
import logging
from pathlib import Path
from typing import Any

from .types import ContextBridge, Phase
from .state import WorkflowState


def _derive_child_thread_id(parent_thread_id: Any, phase_name: str) -> str:
    """Derive a stable nested thread_id for a subgraph run."""
    base = str(parent_thread_id or "").strip()
    return f"{base}:{phase_name}" if base else phase_name


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


def build_subgraph_node(
    harness: Any,
    phase: Phase,
    logger: logging.Logger,
) -> Callable[[WorkflowState], WorkflowState]:
    """Build a node that executes a nested GraphAgentHarness."""
    if phase.subgraph is None:
        raise ValueError(f"Phase '{phase.name}' has no subgraph configured")

    bridge = phase.context_bridge or ContextBridge()
    child = phase.subgraph

    def execute(state: WorkflowState) -> WorkflowState:
        parent_ctx = copy.deepcopy(state["context"])
        active_callbacks = harness.callbacks
        retry_feedback: list[str] | None = None
        if "_retry_feedback" in parent_ctx:
            retry_feedback = parent_ctx.pop("_retry_feedback")

        for cb in active_callbacks:
            cb.on_phase_start(phase.name, dict(parent_ctx))

        run_options = {}
        if hasattr(harness, "_get_active_run_options"):
            run_options = harness._get_active_run_options()

        child_inputs: dict[str, Any] = {}
        for parent_key, child_input in bridge.inputs.items():
            if parent_key not in parent_ctx:
                logger.warning(
                    "[Subgraph] Parent context key '%s' missing for phase '%s', passing None to child input '%s'",
                    parent_key,
                    phase.name,
                    child_input,
                )
            child_inputs[child_input] = parent_ctx.get(parent_key)
        if retry_feedback is not None:
            child_inputs["_retry_feedback"] = retry_feedback

        child_trace_dir = run_options.get("trace_dir")
        if child_trace_dir is not None and not isinstance(child_trace_dir, Path):
            child_trace_dir = Path(child_trace_dir)

        # Forward parent callbacks to child harness via the ``extra_callbacks``
        # parameter (added in P1-1 fix). Avoids the previous pattern of
        # mutating ``child.callbacks`` in place, which cross-wired sibling
        # concurrent invocations of the same child harness instance.

        # Tier 1 Commit C (T-B8): emit a subgraph boundary marker so
        # Studio can fold the child's events (which flow into the parent
        # tracing.jsonl per Gemini Q6) into one visual segment.
        import time as _time

        from ..callbacks.events import (
            InternalErrorEvent,
            SubgraphEnterEvent,
            SubgraphExitEvent,
        )

        child_skill_path = str(
            getattr(child, "_skill_dir", None) or phase.name
        )
        child_thread_id_str = _derive_child_thread_id(
            run_options.get("thread_id") or parent_ctx.get("_thread_id"),
            phase.name,
        )
        for cb in active_callbacks:
            try:
                cb.on_event(
                    SubgraphEnterEvent(
                        phase_name=phase.name,
                        child_skill_path=child_skill_path,
                        child_thread_id=child_thread_id_str,
                    )
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "[Subgraph] callback %r failed on SubgraphEnter; continuing",
                    type(cb).__name__,
                )

        subgraph_start = _time.monotonic()
        # FIXME(D-7.2 PhaseExecutor): child harness instance-level state
        # (``_active_heartbeat`` / ``_active_run_context``) is overwritten on
        # every ``child.run`` call. If the same ``child`` instance is invoked
        # concurrently — e.g. a parallel_map fans out two siblings into the
        # same subgraph reference — the second invocation clobbers the first's
        # run state. The P1-1 fix (this file, 2026-04-24) handled the
        # ``callbacks`` list racing via ``extra_callbacks`` but did not touch
        # the instance attributes; Gemini audit 2026-04-24 flagged it as a
        # latent concurrency bug. The clean fix is to move the run-state to a
        # per-invocation ``PhaseExecutor`` object during the harness split
        # (D-7.2). Until then, do NOT share one ``child`` instance across
        # concurrent parallel_map branches.
        try:
            child_state = child.run(
                initial_context=child_inputs,
                trace_dir=child_trace_dir if isinstance(child_trace_dir, Path) else None,
                thread_id=child_thread_id_str,
                artifact_saver=run_options.get("artifact_saver"),
                runtime_inputs_map=(
                    dict(run_options.get("runtime_inputs"))
                    if isinstance(run_options.get("runtime_inputs"), dict)
                    else {}
                ),
                extra_callbacks=list(active_callbacks),
            )
        except Exception as exc:
            # Tier 1 Commit A — T-B14 InternalErrorEvent at subgraph boundary
            # (per Gemini Q2: three independent try/except entry points so a
            # nested crash is attributed to the correct layer and doesn't let
            # the parent die "不明不白").
            import traceback as _tb

            for cb in active_callbacks:
                try:
                    cb.on_event(
                        InternalErrorEvent(
                            entry_point="subgraph",
                            error_type=type(exc).__name__,
                            error_message=str(exc),
                            traceback=_tb.format_exc(),
                        )
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "[Subgraph] callback %r failed on InternalError; continuing",
                        type(cb).__name__,
                    )
            # Still emit SubgraphExit with status="crashed" so the
            # boundary pair is always balanced (Studio needs both sides
            # to close the folded region).
            for cb in active_callbacks:
                try:
                    cb.on_event(
                        SubgraphExitEvent(
                            phase_name=phase.name,
                            child_skill_path=child_skill_path,
                            wall_time_seconds=round(
                                _time.monotonic() - subgraph_start, 3
                            ),
                            status="crashed",
                        )
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "[Subgraph] callback %r failed on SubgraphExit; continuing",
                        type(cb).__name__,
                    )
            raise

        # Success path — emit SubgraphExit with status="completed"
        for cb in active_callbacks:
            try:
                cb.on_event(
                    SubgraphExitEvent(
                        phase_name=phase.name,
                        child_skill_path=child_skill_path,
                        wall_time_seconds=round(
                            _time.monotonic() - subgraph_start, 3
                        ),
                        status="completed",
                    )
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "[Subgraph] callback %r failed on SubgraphExit; continuing",
                    type(cb).__name__,
                )
        child_ctx = child_state["context"]
        child_metrics = child_state.get("metrics", {})

        for child_key, parent_key in bridge.outputs.items():
            if child_key not in child_ctx:
                logger.warning(
                    "[Subgraph] Child context key '%s' missing for phase '%s', parent key '%s' will be set to None",
                    child_key,
                    phase.name,
                    parent_key,
                )
            parent_ctx[parent_key] = child_ctx.get(child_key)

        parent_ctx["_last_output"] = child_ctx.get("_last_output", "")
        _merge_child_io_errors(parent_ctx, child_ctx)

        merged_metrics = dict(state["metrics"])
        merged_metrics["total_input_tokens"] = (
            merged_metrics.get("total_input_tokens", 0)
            + int(child_metrics.get("total_input_tokens", 0))
        )
        merged_metrics["total_output_tokens"] = (
            merged_metrics.get("total_output_tokens", 0)
            + int(child_metrics.get("total_output_tokens", 0))
        )

        new_state: WorkflowState = {
            "context": parent_ctx,
            "messages": list(child_state.get("messages", [])),
            "current_phase": phase.name,
            "retry_counts": dict(state["retry_counts"]),
            "metrics": merged_metrics,
        }

        for cb in active_callbacks:
            cb.on_phase_end(phase.name, dict(parent_ctx), dict(merged_metrics))

        return new_state

    return execute


__all__ = ["build_subgraph_node"]
