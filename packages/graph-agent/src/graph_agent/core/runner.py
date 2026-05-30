"""Generic Skill Runner — pure document-driven execution of SKILL.md.

Reads SKILL.md's io declarations, loads inputs via IOManager, executes via
GraphAgentHarness, and saves outputs.

No per-skill __init__.py needed. SKILL.md is the single source of truth.

Usage (Python API)::

    from graph_agent import run_skill

    result = run_skill(
        "path/to/my_skill/SKILL.md",
        workspace_dir=Path("/path/to/workspace"),
        input_text="...",
    )

Usage (CLI)::

    python -m graph_agent.runner \\
        --skill path/to/my_skill/SKILL.md \\
        --inputs '{"key": "value"}' \\
        --output /path/to/workspace
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from graph_agent.callbacks import LoggingCallback, TracingCallback
from graph_agent.callbacks.events import (
    CallbackEvent,
    PhaseEndEvent,
    PhaseStartEvent,
    RunEndedEvent,
    RunStartedEvent,
)
from graph_agent.core.exceptions import (
    GraphAgentError,
    LoaderError,
    SkillLoadError,
    TraceWriteError,
    make_error_payload,
)
from graph_agent.core.local_workspace_resolver import LocalWorkspaceResolver
from graph_agent.core.result import WorkflowMetrics, WorkflowResult
from graph_agent.core.skill_resolver_protocol import SkillResolverProtocol, require_skill_resolver
from graph_agent.runtime.state import normalize_blackboard_data

logger = logging.getLogger(__name__)

_NO_MOCK_LLM = object()


def run_skill(
    skill_path: str | Path,
    *,
    mock_llm: Any = _NO_MOCK_LLM,
    workspace_dir: Path,
    thread_id: str | None = None,
    unattended: bool = False,
    callbacks: list[Any] | None = None,
    artifact_saver: Any | None = None,
    initial_context: dict[str, Any] | None = None,
    cleanup_checkpoints_on_finish: bool = True,
    skill_resolver: SkillResolverProtocol,
    model_resolver: Any | None = None,
    **inputs: Any,
) -> WorkflowResult:
    """Execute a SKILL.md and return a typed workflow result."""
    resolver = require_skill_resolver(skill_resolver, caller="run_skill")
    workspace_root = _validate_workspace_dir(workspace_dir)
    started_at = datetime.now(UTC)
    started_monotonic = time.monotonic()
    skill_path_obj = Path(skill_path)
    skill_id = (
        skill_path_obj.parent.name if skill_path_obj.name == "SKILL.md" else skill_path_obj.stem
    )

    try:
        raw = _run_skill_dict(
            skill_path,
            workspace_dir=workspace_root,
            mock_llm=mock_llm,
            thread_id=thread_id,
            unattended=unattended,
            callbacks=callbacks,
            artifact_saver=artifact_saver,
            initial_context=initial_context,
            cleanup_checkpoints_on_finish=cleanup_checkpoints_on_finish,
            skill_resolver=resolver,
            model_resolver=model_resolver,
            **inputs,
        )
    except GraphAgentError as exc:
        finished_at = datetime.now(UTC)
        wall_time = round(time.monotonic() - started_monotonic, 3)
        failed_result = WorkflowResult(
            success=False,
            run_id=thread_id or str(uuid.uuid4()),
            skill_id=skill_id,
            context={},
            metrics=WorkflowMetrics(wall_time_sec=wall_time),
            trace_path=None,
            error=exc.payload or make_error_payload("[F-v3-runtime-phase-failed]", str(exc)),
            started_at=started_at,
            finished_at=finished_at,
            wall_time_sec=wall_time,
        )
        _write_workflow_result_artifacts(
            workspace_root / "runs" / failed_result.run_id,
            failed_result,
        )
        return failed_result

    finished_at = datetime.now(UTC)
    wall_time = float(raw.get("wall_time_sec", round(time.monotonic() - started_monotonic, 3)))
    workflow_result = WorkflowResult(
        success=True,
        run_id=str(raw.get("run_id") or thread_id or str(uuid.uuid4())),
        skill_id=skill_id,
        context=dict(raw.get("context", {})),
        metrics=WorkflowMetrics.from_mapping(dict(raw.get("metrics", {})), wall_time_sec=wall_time),
        trace_path=raw.get("trace_path"),
        error=None,
        started_at=started_at,
        finished_at=finished_at,
        wall_time_sec=wall_time,
    )
    run_dir = Path(raw.get("run_dir") or workspace_root / "runs" / workflow_result.run_id)
    _write_workflow_result_artifacts(run_dir, workflow_result)
    return workflow_result


def _run_skill_dict(
    skill_path: str | Path,
    *,
    mock_llm: Any = _NO_MOCK_LLM,
    workspace_dir: Path,
    thread_id: str | None = None,
    unattended: bool = False,
    callbacks: list[Any] | None = None,
    artifact_saver: Any | None = None,
    initial_context: dict[str, Any] | None = None,
    cleanup_checkpoints_on_finish: bool = True,
    skill_resolver: SkillResolverProtocol,
    model_resolver: Any | None = None,
    **inputs: Any,
) -> dict[str, Any]:
    """Execute a SKILL.md with the given inputs. Pure document-driven.

    Args:
        skill_path: Path to SKILL.md.
        workspace_dir: Absolute workspace root for run-scoped artifacts.
        thread_id: Optional thread_id for checkpoint resume.
        callbacks: Optional list of Callback instances. Defaults to
            ``[LoggingCallback, TracingCallback]``.
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
        - ``trace_path``: Path to saved trace summary JSON (if TracingCallback active)
        - ``wall_time_sec``: Total wall time
    """
    resolver = require_skill_resolver(skill_resolver, caller="_run_skill_dict")
    skill_path = Path(skill_path)
    if skill_path.is_dir() and (skill_path / "GRAPH.md").is_file():
        return _run_v030_skill_dict(
            skill_path,
            workspace_dir=workspace_dir,
            mock_llm=mock_llm,
            thread_id=thread_id,
            callbacks=callbacks,
            skill_resolver=resolver,
            model_resolver=model_resolver,
            **inputs,
        )

    detail = (
        "[F-v3-graph-root-missing] run_skill expects a V0.3.0 skill root "
        f"directory containing GRAPH.md; got {skill_path}"
    )
    raise SkillLoadError(
        detail,
        payload=make_error_payload(
            "[F-v3-graph-root-missing]",
            detail,
            source_path=skill_path,
        ),
    )


def _validate_workspace_dir(workspace_dir: Path) -> Path:
    workspace_path = Path(workspace_dir)
    if not workspace_path.is_absolute():
        raise ValueError("workspace_dir must be an absolute path")
    return workspace_path


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _write_workflow_result_artifacts(run_dir: Path, result: WorkflowResult) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "result.json", result.model_dump(mode="json"))
    _write_json(run_dir / "final_state.json", result.context)
    _write_json(run_dir / "metrics.json", result.metrics.model_dump(mode="json"))


def _prepare_v030_callbacks(
    callbacks: list[Any] | None,
    trace_output: Path | None,
) -> list[Any]:
    active_callbacks = list(callbacks) if callbacks is not None else [LoggingCallback()]
    tracing_callbacks = [cb for cb in active_callbacks if isinstance(cb, TracingCallback)]
    if trace_output is not None:
        if not tracing_callbacks:
            tracer = TracingCallback(trace_dir=trace_output)
            active_callbacks.append(tracer)
            tracing_callbacks.append(tracer)
        for tracer in tracing_callbacks:
            if getattr(tracer, "_typed_jsonl_path", None) is None:
                tracer.set_trace_dir(trace_output)
    elif callbacks is None:
        active_callbacks.append(TracingCallback())
    return active_callbacks


def _emit_v030_event(callbacks: list[Any], event: CallbackEvent) -> None:
    for callback in callbacks:
        on_event = getattr(callback, "on_event", None)
        if callable(on_event):
            on_event(event)


def _save_v030_trace(callbacks: list[Any], trace_output: Path | None) -> str | None:
    if trace_output is None:
        return None
    saved_trace_path: str | None = None
    for callback in callbacks:
        if isinstance(callback, TracingCallback):
            try:
                saved_trace_path = callback.save(trace_output)
            except Exception as exc:
                raise TraceWriteError(
                    f"trace save failed: {exc}",
                    context={"trace_path": str(trace_output)},
                ) from exc
    return saved_trace_path


def _v030_phase_context(data: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_blackboard_data(data)
    return {
        "inputs": dict(normalized["inputs"]),
        "phase_outputs": dict(normalized["phase_outputs"]),
        "scratch": dict(normalized["scratch"]),
    }


def _save_v030_declared_file_outputs(
    output_schema: Any,
    context: dict[str, Any],
    *,
    default_output_dir: Path,
) -> None:
    properties = output_schema.get("properties") if isinstance(output_schema, dict) else None
    if not isinstance(properties, dict):
        return
    file_outputs = [
        {"name": name, **schema}
        for name, schema in properties.items()
        if isinstance(name, str)
        and isinstance(schema, dict)
        and schema.get("target") == "file"
    ]
    if not file_outputs:
        return

    from graph_agent.io.manager import IOManager

    output_context = dict(context)
    normalized = normalize_blackboard_data(context)
    for phase_outputs in normalized["phase_outputs"].values():
        if isinstance(phase_outputs, dict):
            output_context.update(phase_outputs)

    io_mgr = IOManager({"outputs": file_outputs})
    io_mgr.save_outputs(
        output_context,
        output_dir=output_context.get("output_dir") or default_output_dir,
    )


def _run_v030_skill_dict(
    skill_root: Path,
    *,
    mock_llm: Any = _NO_MOCK_LLM,
    workspace_dir: Path,
    thread_id: str | None = None,
    callbacks: list[Any] | None = None,
    skill_resolver: SkillResolverProtocol,
    model_resolver: Any | None = None,
    **inputs: Any,
) -> dict[str, Any]:
    """Execute a V0.3.0 skill root through compile_skill + assemble_graph."""

    from graph_agent.core.compiler import compile_skill
    from graph_agent.core.graph_assembler import assemble_graph

    resolver = require_skill_resolver(skill_resolver, caller="_run_v030_skill_dict")
    t0 = time.time()
    run_id = thread_id or str(uuid.uuid4())
    trace_output = workspace_dir / "runs" / run_id
    active_callbacks = _prepare_v030_callbacks(callbacks, trace_output)
    emit_auto_trace_events = callbacks is None
    if mock_llm is not _NO_MOCK_LLM:
        chat_model = mock_llm
    elif model_resolver is not None:
        chat_model = model_resolver.resolve(
            callbacks=tuple(active_callbacks),
            phase_name="<workflow>",
        )
    else:
        chat_model = None
    compiled = compile_skill(skill_root, skill_resolver=resolver)
    assembled = assemble_graph(
        compiled,
        chat_model=chat_model,
        callbacks=active_callbacks,
        skill_resolver=resolver,
    )
    graph = assembled.graph
    if emit_auto_trace_events:
        _emit_v030_event(
            active_callbacks,
            RunStartedEvent(
                run_id=run_id,
                thread_id=run_id,
                initial_context={"inputs": dict(inputs)},
            ),
        )
        for phase_id in assembled.phase_ids:
            _emit_v030_event(
                active_callbacks,
                PhaseStartEvent(phase_name=phase_id, context=_v030_phase_context(dict(inputs))),
            )
    try:
        result = graph.invoke(
            {
                "data": dict(inputs),
                "flow": {},
                "messages": [],
                "run_id": run_id,
            }
        )
    except Exception:
        wall_time = round(time.time() - t0, 3)
        if emit_auto_trace_events:
            _emit_v030_event(
                active_callbacks,
                RunEndedEvent(
                    run_id=run_id,
                    thread_id=run_id,
                    status="crashed",
                    final_context={},
                    wall_time_seconds=wall_time,
                ),
            )
        _save_v030_trace(active_callbacks, trace_output)
        raise
    wall_time = round(time.time() - t0, 3)
    final_context = dict(result.get("data", {}))
    compiled_raw = getattr(compiled, "raw", {})
    output_schema = (
        compiled_raw.get("io", {}).get("outputs") if isinstance(compiled_raw, dict) else None
    )
    _save_v030_declared_file_outputs(
        output_schema,
        final_context,
        default_output_dir=trace_output / "artifacts",
    )
    if emit_auto_trace_events:
        final_trace_context = _v030_phase_context(final_context)
        for phase_id in assembled.phase_ids:
            _emit_v030_event(
                active_callbacks,
                PhaseEndEvent(phase_name=phase_id, context=final_trace_context),
            )
        _emit_v030_event(
            active_callbacks,
            RunEndedEvent(
                run_id=run_id,
                thread_id=run_id,
                status="completed",
                final_context=final_trace_context,
                wall_time_seconds=wall_time,
            ),
        )
    saved_trace_path = _save_v030_trace(active_callbacks, trace_output)
    return {
        "run_id": run_id,
        "context": final_context,
        "metrics": {"wall_time_sec": wall_time},
        "trace_path": saved_trace_path,
        "run_dir": str(trace_output),
        "wall_time_sec": wall_time,
    }


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

    workspace_dir = Path(args.output).resolve() if args.output else (Path.cwd() / ".workspace")

    skill_path = Path(args.skill)
    resolver_roots = [Path.cwd(), Path.cwd() / "skills"]
    if skill_path.is_dir():
        resolver_roots.extend([skill_path, skill_path / "registry", skill_path.parent])
    else:
        resolver_roots.extend([skill_path.parent, skill_path.parent / "registry"])

    result = run_skill(
        args.skill,
        workspace_dir=workspace_dir,
        skill_resolver=LocalWorkspaceResolver(search_paths=resolver_roots),
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
