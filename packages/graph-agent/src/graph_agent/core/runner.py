"""Generic Skill Runner — pure document-driven execution of SKILL.md.

Reads SKILL.md's io + context_mapping declarations, loads inputs via IOManager,
transforms via ContextResolver, executes via GraphAgentHarness, saves outputs.

No per-skill __init__.py needed. SKILL.md is the single source of truth.

Usage (Python API)::

    from graph_agent import run_skill

    result = run_skill(
        "path/to/my_skill/SKILL.md",
        scene=scene_dict,
        scene_index=0,
        entity_registry={},
        visual_assets={},
        narrative_context={},
        predecessor_scene=None,
        all_scenes=[scene_dict],
        output_dir="/path/to/output",
    )

Usage (CLI)::

    python -m graph_agent.runner \\
        --skill path/to/my_skill/SKILL.md \\
        --inputs '{"key": "value"}' \\
        --output /path/to/output
"""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from graph_agent.callbacks import LoggingCallback, TracingCallback
from graph_agent.core.exceptions import LoaderError, PersistenceError
from graph_agent.core.loader import load_workflow_from_md
from graph_agent.core.state import WorkflowState

logger = logging.getLogger(__name__)

# Cache loaded harnesses to avoid re-parsing SKILL.md on repeated calls
_harness_cache: dict[str, tuple[Any, dict[str, int]]] = {}
_cache_lock = threading.Lock()


def _collect_skill_dependency_snapshot(
    harness: Any,
    *,
    _seen: set[int] | None = None,
) -> dict[str, int]:
    """Collect mtime_ns for the harness skill tree and local Python modules."""
    if _seen is None:
        _seen = set()

    harness_id = id(harness)
    if harness_id in _seen:
        return {}
    _seen.add(harness_id)

    snapshot: dict[str, int] = {}
    skill_dir = getattr(harness, "_skill_dir", None)
    if isinstance(skill_dir, Path) and skill_dir.exists():
        for pattern in ("*.md", "*.py"):
            for path in skill_dir.rglob(pattern):
                if not path.is_file() or "__pycache__" in path.parts:
                    continue
                try:
                    snapshot[str(path.resolve())] = path.stat().st_mtime_ns
                except OSError:
                    snapshot[str(path.resolve())] = -1

    return snapshot


def _refresh_callbacks_recursive(
    harness: Any,
    callbacks: list[Any],
    *,
    _seen: set[int] | None = None,
) -> None:
    """Replace callback references on the cached harness.

    Pre-V1-reset this also walked ``phase.subgraph`` to refresh nested
    child harnesses; the subgraph runtime is gone, so the walk reduces
    to a flat assignment, but the recursion guard is kept so a future
    runtime that reintroduces nesting can plug in here without changing
    the call sites.
    """
    if _seen is None:
        _seen = set()

    harness_id = id(harness)
    if harness_id in _seen:
        return
    _seen.add(harness_id)

    harness.callbacks = callbacks


def run_skill(
    skill_path: str | Path,
    *,
    trace_dir: str | Path | None = None,
    thread_id: str | None = None,
    unattended: bool = False,
    callbacks: list[Any] | None = None,
    artifact_saver: Any | None = None,
    initial_context: dict[str, Any] | None = None,
    cleanup_checkpoints_on_finish: bool = True,
    **inputs: Any,
) -> dict[str, Any]:
    """Execute a SKILL.md with the given inputs. Pure document-driven.

    Args:
        skill_path: Path to SKILL.md.
        trace_dir: Directory for trace output. If None, uses inputs["output_dir"] if available.
        thread_id: Optional thread_id for checkpoint resume.
        callbacks: Optional list of Callback instances. Defaults to [LoggingCallback, TracingCallback].
        artifact_saver: Optional callback for ``artifact_manager`` outputs.
        cleanup_checkpoints_on_finish: When True (default) call
            ``checkpointer.delete_thread(thread_id)`` after a successful
            run so accumulated checkpoints do not pile up. Set to False
            when you still want to resume from a specific earlier
            checkpoint after the pipeline has technically finished
            (e.g. human review loops, golden regression data gathering).
            Task 2.8 (simplified) — see deferred-items.md D-2.8.
        **inputs: Runtime inputs matching SKILL.md io.inputs declarations.
            Each kwarg name must match an input's ``name`` field.

    Returns:
        Dict with keys:
        - ``context``: Final workflow context (contains all outputs)
        - ``metrics``: Token usage and timing stats
        - ``trace_path``: Path to trace.json (if TracingCallback active)
        - ``wall_time_sec``: Total wall time
    """
    skill_path = Path(skill_path)
    if not skill_path.exists():
        raise FileNotFoundError(f"SKILL.md not found: {skill_path}")

    # Resolve trace_dir first so callback can be initialized with it.
    effective_trace_dir = trace_dir
    if effective_trace_dir is None and inputs.get("output_dir"):
        effective_trace_dir = Path(inputs["output_dir"]) / "traces"

    # Setup callbacks
    if callbacks is None:
        callbacks = [LoggingCallback(), TracingCallback(trace_dir=effective_trace_dir)]

    # Load or get cached harness
    # NOTE: The cached harness is shared across calls. Callbacks are refreshed
    # per call while holding _cache_lock.  Concurrent run_skill() calls to the
    # same SKILL.md are NOT supported — callers must serialise or use separate
    # harness instances via load_workflow_from_md().
    cache_key = str(skill_path.resolve())
    with _cache_lock:
        cached = _harness_cache.get(cache_key)
        if cached is None or _collect_skill_dependency_snapshot(cached[0]) != cached[1]:
            harness = load_workflow_from_md(str(skill_path), callbacks=callbacks)
            _harness_cache[cache_key] = (harness, _collect_skill_dependency_snapshot(harness))
            logger.info(
                "[Runner] Loaded SKILL: %s (%d phases)", skill_path.name, len(harness.phases)
            )
        else:
            harness = cached[0]
            # Refresh callbacks while still holding _cache_lock to prevent
            # concurrent run_skill calls from overwriting each other's callbacks.
            _refresh_callbacks_recursive(harness, callbacks)

    # Resume logic: check for .run_id file (previous interrupted run)
    effective_thread_id = thread_id
    run_id_file: Path | None = None
    if inputs.get("output_dir"):
        state_dir = Path(inputs["output_dir"]) / "graph_agent_state"
        run_id_file = state_dir / ".run_id"
        # Migrate from legacy directory name
        legacy_run_id = Path(inputs["output_dir"]) / "pipeline_state" / ".run_id"
        if legacy_run_id.exists() and not run_id_file.exists():
            state_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(legacy_run_id), str(run_id_file))
            if not run_id_file.exists():
                logger.error(
                    "[Runner] Checkpoint migration failed — copy did not produce %s", run_id_file
                )
            else:
                logger.info(
                    "[Runner] Migrated checkpoint from pipeline_state/ to graph_agent_state/"
                )
        elif legacy_run_id.exists() and run_id_file.exists():
            logger.info("[Runner] Both legacy and new checkpoint exist; using graph_agent_state/")
        if effective_thread_id is None and run_id_file.exists():
            saved_tid = run_id_file.read_text(encoding="utf-8").strip()
            if saved_tid:
                effective_thread_id = saved_tid
                logger.info("[Runner] Resuming from checkpoint: thread_id=%s", saved_tid)

    # Run — IOManager + ContextResolver handle input loading + context building
    t0 = time.time()

    # Write .run_id for potential resume
    if run_id_file is not None:
        run_id_file.parent.mkdir(parents=True, exist_ok=True)
        actual_tid = effective_thread_id or str(uuid.uuid4())
        run_id_file.write_text(actual_tid, encoding="utf-8")
        if effective_thread_id is None:
            effective_thread_id = actual_tid

    try:
        final_state: WorkflowState = harness.run(
            trace_dir=Path(effective_trace_dir) if effective_trace_dir else None,
            thread_id=effective_thread_id,
            unattended=unattended,
            artifact_saver=artifact_saver,
            initial_context=initial_context,
            runtime_inputs_map=inputs,
        )
    except Exception:
        # Clean up .run_id on unexpected failure to avoid corrupted resume
        if run_id_file is not None and run_id_file.exists():
            try:
                run_id_file.unlink()
                logger.info("[Runner] Cleaned up .run_id after failure")
            except OSError as exc:
                raise PersistenceError(
                    f"run_id cleanup failed: {exc}",
                    context={
                        "thread_id": effective_thread_id,
                        "run_id_file": str(run_id_file),
                    },
                ) from exc
        raise
    wall_time = time.time() - t0

    # Success — remove .run_id
    if run_id_file is not None and run_id_file.exists():
        run_id_file.unlink()

    # Task 2.8 (simplified) — post-completion checkpoint cleanup.
    # Gemini's "纸杯论": once finish_task has fired, no exception was
    # raised, and no HITL interrupt is pending, checkpoints have no more
    # resume value — the artifact layer already persists the valuable
    # state. Default True; callers that want to keep checkpoints for
    # human-review / golden-regression purposes pass False.
    if cleanup_checkpoints_on_finish and effective_thread_id:
        try:
            checkpointer = getattr(harness, "_checkpointer", None)
            if checkpointer is not None and hasattr(checkpointer, "delete_thread"):
                checkpointer.delete_thread(effective_thread_id)
                logger.info(
                    "[Runner] Checkpoints cleaned up for thread_id=%s",
                    effective_thread_id,
                )
                # Tier 1 T-B7: emit a visible marker so the trace records
                # that resume is no longer possible from this thread.
                with contextlib.suppress(Exception):
                    from graph_agent.callbacks.events import _EventBase  # noqa: F401

                    # We purposefully don't depend on a dedicated event
                    # class here — Gemini flagged ThreadCleanedUpEvent as
                    # optional (降级到 P2). A log INFO is enough for ops;
                    # Studio's "thread archived" UI state can derive from
                    # RunEnded(status=completed) + absence of checkpoint.
        except Exception as exc:  # noqa: BLE001
            raise PersistenceError(
                f"checkpoint cleanup failed: {exc}",
                context={
                    "thread_id": effective_thread_id,
                    "cleanup_checkpoints_on_finish": cleanup_checkpoints_on_finish,
                },
            ) from exc

    ctx = final_state["data"].model_dump()
    metrics = final_state["flow"].metrics

    # Extract trace path
    trace_path = final_state["flow"].trace_path

    logger.info(
        "[Runner] Completed: wall=%.1fs, in_tokens=%d, out_tokens=%d",
        wall_time,
        metrics.get("total_input_tokens", 0),
        metrics.get("total_output_tokens", 0),
    )

    return {
        "context": ctx,
        "metrics": metrics,
        "trace_path": trace_path,
        "wall_time_sec": round(wall_time, 1),
    }


def clear_cache() -> None:
    """Clear the harness cache (for testing or after SKILL.md changes)."""
    with _cache_lock:
        _harness_cache.clear()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for running a SKILL.md."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run a SKILL.md workflow (document-driven, no per-skill Python code needed)"
    )
    parser.add_argument("--skill", required=True, help="Path to SKILL.md")
    parser.add_argument("--inputs", type=str, default=None, help="JSON string of runtime inputs")
    parser.add_argument("--inputs-file", type=str, default=None, help="JSON file of runtime inputs")
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    parser.add_argument(
        "--thread-id", type=str, default=None, help="Thread ID for checkpoint resume"
    )
    parser.add_argument(
        "--unattended",
        action="store_true",
        help=(
            "Run without human intervention. ask_clarification tool calls "
            "are auto-answered with a best-effort instruction instead of "
            "interrupting the run."
        ),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # MVP-3 T10: route framework startup through ``Bootstrap`` instead of
    # leaking ``load_dotenv`` and reasoning_patch side effects across
    # ``runner.main``. ``Bootstrap.apply_patches`` is the single
    # documented entry point for monkey-patches; ``load_settings``
    # produces an explicit ``Settings`` snapshot so downstream
    # consumers can migrate off ``os.environ.get`` reads incrementally.
    # ``load_dotenv`` is kept as a transitional sibling step — it lives
    # outside ``Bootstrap`` because the ``.env`` file is a CLI/runtime
    # convention, not a framework patch. Once every consumer reads from
    # ``Settings``, the dotenv call moves into ``Bootstrap`` and exits
    # ``runner.main`` entirely (deferred to MVP-5 工程门禁).
    from graph_agent.bootstrap import Bootstrap

    bootstrap = Bootstrap()
    bootstrap.apply_patches()

    # Load .env (transitional; reads cli-side .env so Settings.from_env
    # sees user-supplied API keys).
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError as exc:
        raise LoaderError(
            f"required import failed: {exc}",
            context={"module": "dotenv"},
        ) from exc

    bootstrap.load_settings()

    # Parse inputs
    inputs: dict[str, Any] = {}
    if args.inputs:
        inputs = json.loads(args.inputs)
    elif args.inputs_file:
        inputs = json.loads(Path(args.inputs_file).read_text(encoding="utf-8"))

    if args.output:
        inputs["output_dir"] = args.output

    result = run_skill(
        args.skill,
        thread_id=args.thread_id,
        unattended=args.unattended,
        **inputs,
    )

    logger.info(
        "[Runner] Result: %s",
        json.dumps(
            {
                "wall_time_sec": result["wall_time_sec"],
                "metrics": result["metrics"],
                "trace_path": result.get("trace_path"),
            },
            indent=2,
            default=str,
        ),
    )


if __name__ == "__main__":
    main()
