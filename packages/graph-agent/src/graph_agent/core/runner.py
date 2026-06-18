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
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from langchain_core.messages import ToolMessage

from graph_agent.callbacks.emit import (
    _CallbackSink,
    _CompositeEventSink,
    _safe_emit_event,
    _SubscriberSink,
    _TraceJsonlSink,
)
from graph_agent.callbacks.events import (
    CallbackEvent,
    RunEndedEvent,
    RunStartedEvent,
)
from graph_agent.core.adapter_contracts import (
    PredictArtifactRequest,
    RunArtifactErrorResult,
    RunArtifactRequest,
    RunSession,
)
from graph_agent.core.checkpointer import resolve_checkpointer
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import (
    GraphAgentError,
    GraphAgentFatalError,
    LoaderError,
    SkillLoadError,
    make_error_payload,
)
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.llm_provider import LLMProvider, LLMProviderError
from graph_agent.core.local_workspace_resolver import LocalWorkspaceResolver
from graph_agent.core.result import RunResult, WorkflowMetrics, WorkflowResult
from graph_agent.core.skill_resolver_protocol import SkillResolverProtocol, require_skill_resolver
from graph_agent.core.state import BusinessData
from graph_agent.core.storage_contracts import ObjectRef, RunArtifactStore
from graph_agent.runtime.state import normalize_blackboard_data

logger = logging.getLogger(__name__)

_NO_MOCK_LLM = object()
_RUNTIME_PHASE_FAILED_CODE = "[F-v3-runtime-phase-failed]"
_SKILL_ENTRYPOINT_FILENAME = "SKILL.md"


class PredictDeadlockError(RuntimeError):
    """Raised when Predict heuristic stubs appear to trap routing in a loop."""

    def __init__(self, phase_name: str, actual_path: list[str]) -> None:
        self.phase_name = phase_name
        self.actual_path = actual_path
        super().__init__(
            f"Predict P2 deadlock guard tripped for phase '{phase_name}' "
            f"after {actual_path.count(phase_name)} visits"
        )


class _ResumeInputError(ValueError):
    """Raised for invalid resume caller input that should surface directly."""


_RESUME_CONTEXT_OVERRIDE_FORBIDDEN_KEYS = {
    "messages",
    "tool_calls",
    "checkpoint_ns",
    "configurable",
    "runtime",
    "callbacks",
    "compiled_graph",
}


class SDKPredictContext:
    """PredictContext interface implementation for model resolution interception."""

    def __init__(self, strategy: Any, copilot_predict: Callable[..., Any] | None = None) -> None:
        self.strategy = strategy
        self.copilot_predict = copilot_predict

    def resolve_generation(
        self,
        phase_name: str,
        role_name: str,
        messages: list[Any],
    ) -> tuple[dict[str, Any], str]:
        from graph_agent.core._predict_internal.stub import generate_heuristic_stub
        from graph_agent.core._predict_internal.tracing import record_mock_source

        # 1. P0 Golden Case
        if self.strategy.has_golden_case(phase_name):
            payload = self.strategy.get_golden_output(phase_name)
            record_mock_source(phase_name, "golden_case")
            return payload, "golden_case"

        # 2. P1 copilot_predict
        if self.copilot_predict is not None:
            try:
                payload = self.copilot_predict(phase_name, role_name, messages)
                if payload is not None:
                    if isinstance(payload, dict):
                        record_mock_source(phase_name, "copilot")
                        return payload, "copilot"
                    payload = {"value": payload}
                    record_mock_source(phase_name, "copilot")
                    return payload, "copilot"
            except Exception as exc:
                logger.warning("copilot_predict failed for phase=%s: %s", phase_name, exc)

        # 3. P1 manual_override
        if self.strategy.has_manual_override(phase_name):
            payload = self.strategy.get_manual_override(phase_name)
            source = self.strategy.get_manual_source(phase_name)
            record_mock_source(phase_name, source)
            return payload, source

        # 4. P2 Heuristic Stub fallback
        schema = self.strategy.get_phase_schema(phase_name)
        payload = generate_heuristic_stub(schema)
        record_mock_source(phase_name, "heuristic_stub")
        return payload, "heuristic_stub"


def _warn_on_stale_golden_hashes_sdk(
    strategy: Any,
    current_hashes: dict[str, dict[str, str]],
) -> None:
    from graph_agent.core._predict_internal.strategy import BacktestStrategy, GoldenCaseStrategy

    golden_cases = []
    if isinstance(strategy, GoldenCaseStrategy):
        golden_cases = [strategy.golden_case]
    elif isinstance(strategy, BacktestStrategy):
        golden_cases = strategy.golden_cases

    for golden_case in golden_cases:
        phase_name = str(golden_case.metadata.get("phase_name") or "")
        if not phase_name:
            continue
        current = current_hashes.get(phase_name)
        if not current:
            continue
        expected_prompt_hash = golden_case.metadata.get("prompt_hash")
        expected_schema_hash = golden_case.metadata.get("io_outputs_schema_hash")
        if (
            current.get("prompt_hash") != expected_prompt_hash
            or current.get("io_outputs_schema_hash") != expected_schema_hash
        ):
            logger.warning(
                "Golden case hash stale for phase=%s expected_prompt=%s current_prompt=%s "
                "expected_schema=%s current_schema=%s",
                phase_name,
                expected_prompt_hash,
                current.get("prompt_hash"),
                expected_schema_hash,
                current.get("io_outputs_schema_hash"),
            )


def predict_skill(  # noqa: C901
    skill_path: str | Path,
    *,
    workspace_dir: Path,
    thread_id: str | None = None,
    unattended: bool = True,
    event_subscriber: Callable[[CallbackEvent], None] | None = None,
    skill_resolver: SkillResolverProtocol,
    model_resolver: Any | None = None,
    llm_provider: LLMProvider | None = None,
    copilot_predict: Callable[..., Any] | None = None,
    **inputs: Any,
) -> RunResult:
    """Run skill compilation and execution in Predict mode with caching and mock generation."""
    from collections import Counter

    from graph_agent import PathDiff
    from graph_agent.core._predict_internal.exporter import assemble_phase_record
    from graph_agent.core._predict_internal.path_diff import compute_diff
    from graph_agent.core._predict_internal.strategy import MockStrategy
    from graph_agent.core._predict_internal.tracing import PredictTracingCallback
    from graph_agent.core.compiler import compile_skill
    from graph_agent.core.graph_assembler import assemble_graph
    from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState

    resolver = require_skill_resolver(skill_resolver, caller="predict_skill")
    workspace_root = _validate_workspace_dir(workspace_dir)
    started_at = datetime.now(UTC)
    started_monotonic = time.monotonic()
    skill_path_obj = Path(skill_path)
    skill_id = (
        skill_path_obj.parent.name
        if skill_path_obj.name == _SKILL_ENTRYPOINT_FILENAME
        else skill_path_obj.stem
    )

    mock_llm = inputs.pop("mock_llm", None)
    current_hashes = inputs.pop("current_hashes", None) or {}

    compiled = compile_skill(skill_path_obj, skill_resolver=resolver)


    # 1. Strategy setup
    strategy = MockStrategy.from_param(mock_llm)
    _warn_on_stale_golden_hashes_sdk(strategy, current_hashes)

    # 2. Populate phase schemas for Heuristic Stub fallback
    phase_schemas = {}
    for node in compiled.nodes:
        if hasattr(node, "ast") and hasattr(node.ast, "io") and node.ast.io and node.ast.io.outputs:
            outputs = node.ast.io.outputs
            if hasattr(outputs, "model_dump"):
                phase_schemas[node.phase_name] = outputs.model_dump()
            else:
                phase_schemas[node.phase_name] = outputs
    if hasattr(strategy, "_phase_schemas"):
        strategy._phase_schemas.update(phase_schemas)

    # 3. Setup Predict interception context & tracing
    predict_context = SDKPredictContext(strategy, copilot_predict)
    tracing_callback = PredictTracingCallback()
    tracing_callback.on_chain_start(metadata={})

    run_id = thread_id or str(uuid.uuid4())
    trace_output = workspace_root / "runs" / run_id

    # 4. Prepare Composite event sink for tracking events and trace.jsonl output
    event_sink = _prepare_v030_event_sink(
        trace_output=trace_output,
        event_subscriber=event_subscriber,
        callbacks=[tracing_callback],
    )

    # 5. Assemble and run graph in intercept mode
    assembled = assemble_graph(
        compiled,
        chat_model=None,
        model_resolver=model_resolver,
        llm_provider=llm_provider,
        callbacks=cast(Any, event_sink),
        skill_resolver=resolver,
        predict_context=predict_context,
    )
    graph = assembled.graph

    initial_state = WorkflowState(
        data=BusinessData.model_validate(dict(inputs)),
        flow=FrameworkState.model_validate({
            "run_id": run_id,
            "thread_id": run_id,
            "unattended": unattended,
            "persistent_storage_config": {"workspace_dir": str(workspace_root)},
        }),
        messages=[],
    )

    try:
        final_state = graph.invoke(
            initial_state,
            config={"configurable": {"thread_id": run_id}},
        )
    except Exception as exc:
        finished_at = datetime.now(UTC)
        wall_time = round(time.monotonic() - started_monotonic, 3)
        failed_result = RunResult(
            success=False,
            run_id=run_id,
            skill_id=skill_id,
            context={},
            metrics=WorkflowMetrics(wall_time_sec=wall_time),
            error=make_error_payload(_RUNTIME_PHASE_FAILED_CODE, str(exc)),
            started_at=started_at,
            finished_at=finished_at,
            wall_time_sec=wall_time,
            source="predict",
        )
        _write_workflow_result_artifacts(trace_output, failed_result)
        return failed_result

    finished_at = datetime.now(UTC)
    wall_time = round(time.monotonic() - started_monotonic, 3)

    # 5. Extract results, path & deadlocks
    final_context = final_state["data"].model_dump()
    raw_phases = tracing_callback.phases or []
    phases = [assemble_phase_record(item) for item in raw_phases]
    actual_path = [phase.phase_name for phase in phases]

    # Deadlock guard for heuristic stubs
    if type(strategy).__name__ == "HeuristicStubStrategy":
        counts = Counter(actual_path)
        for phase_name, count in counts.items():
            if count > 10:  # MAX_PHASE_REVISITS
                raise PredictDeadlockError(phase_name, actual_path)

    # Path diff
    expected_path = getattr(strategy, "expected_path", None)
    path_diff = None
    if expected_path:
        raw_diff = compute_diff([str(item) for item in expected_path], actual_path)
        path_diff = PathDiff(
            expected_path=raw_diff.expected_path,
            actual_path=raw_diff.actual_path,
            missing=raw_diff.missing,
            extra=raw_diff.extra,
            order_mismatch=raw_diff.order_mismatch,
        )

    # Success derives from path_diff success (no missing, no extra, no order mismatch)
    success = True
    if path_diff and (path_diff.missing or path_diff.extra or path_diff.order_mismatch):
        success = False

    run_result = RunResult(
        success=success,
        run_id=run_id,
        skill_id=skill_id,
        context=final_context,
        metrics=WorkflowMetrics(wall_time_sec=wall_time),
        trace_path=trace_output / "trace.jsonl",
        started_at=started_at,
        finished_at=finished_at,
        wall_time_sec=wall_time,
        source="predict",
        phases=phases,
        path_diff=path_diff,
    )

    # Write trace.jsonl output
    trace_output.mkdir(parents=True, exist_ok=True)
    tracing_callback.save(trace_output)

    _write_workflow_result_artifacts(trace_output, run_result)
    return run_result


def run_skill(
    skill_path: str | Path,
    *,
    workspace_dir: Path,
    thread_id: str | None = None,
    unattended: bool = False,
    event_subscriber: Callable[[CallbackEvent], None] | None = None,
    artifact_saver: Any | None = None,
    initial_context: dict[str, Any] | None = None,
    cleanup_checkpoints_on_finish: bool = True,
    skill_resolver: SkillResolverProtocol,
    model_resolver: Any | None = None,
    llm_provider: LLMProvider | None = None,
    **inputs: Any,
) -> RunResult:
    """Execute a SKILL.md and return a typed workflow result."""
    mock_llm = inputs.pop("mock_llm", _NO_MOCK_LLM)
    resolver = require_skill_resolver(skill_resolver, caller="run_skill")
    workspace_root = _validate_workspace_dir(workspace_dir)
    started_at = datetime.now(UTC)
    started_monotonic = time.monotonic()
    skill_path_obj = Path(skill_path)
    skill_id = (
        skill_path_obj.parent.name
        if skill_path_obj.name == _SKILL_ENTRYPOINT_FILENAME
        else skill_path_obj.stem
    )

    try:
        raw = _run_skill_dict(
            skill_path,
            workspace_dir=workspace_root,
            mock_llm=mock_llm,
            thread_id=thread_id,
            unattended=unattended,
            event_subscriber=event_subscriber,
            artifact_saver=artifact_saver,
            initial_context=initial_context,
            cleanup_checkpoints_on_finish=cleanup_checkpoints_on_finish,
            skill_resolver=resolver,
            model_resolver=model_resolver,
            llm_provider=llm_provider,
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
            error=exc.payload or make_error_payload(_RUNTIME_PHASE_FAILED_CODE, str(exc)),
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


def resume_skill(
    skill_path: str | Path,
    *,
    workspace_dir: Path,
    run_id: str,
    checkpoint_id: str | None = None,
    checkpoint_ns: str | None = None,
    checkpointer: Any | None = None,
    context_overrides: dict[str, Any] | None = None,
    human_response: dict[str, Any] | None = None,
    skill_resolver: SkillResolverProtocol,
    model_resolver: Any | None = None,
    llm_provider: LLMProvider | None = None,
    event_subscriber: Callable[[CallbackEvent], None] | None = None,
) -> RunResult:
    """Resume a previously interrupted skill run from a checkpoint."""
    workspace_root = _validate_workspace_dir(workspace_dir)
    _validate_resume_human_response(human_response)
    _validate_resume_context_overrides(context_overrides)

    resolver = require_skill_resolver(skill_resolver, caller="resume_skill")
    started_at = datetime.now(UTC)
    started_monotonic = time.monotonic()
    skill_path_obj = Path(skill_path)
    skill_id = (
        skill_path_obj.parent.name
        if skill_path_obj.name == _SKILL_ENTRYPOINT_FILENAME
        else skill_path_obj.stem
    )

    trace_output = workspace_root / "runs" / run_id
    event_sink = _prepare_v030_event_sink(
        trace_output=trace_output,
        event_subscriber=event_subscriber,
    )

    logger.info(
        "[Resume] Resuming run_id=%s checkpoint_ns=%s checkpoint_id=%s",
        run_id,
        checkpoint_ns,
        checkpoint_id,
    )

    active_checkpointer = checkpointer if checkpointer is not None else _resolve_resume_checkpointer()
    invoke_config = _resolve_resume_config(
        active_checkpointer,
        run_id=run_id,
        checkpoint_ns=checkpoint_ns,
        checkpoint_id=checkpoint_id,
    )

    try:
        compiled = compile_skill(skill_path, skill_resolver=resolver)
        assembled = assemble_graph(
            compiled,
            model_resolver=model_resolver,
            llm_provider=llm_provider,
            callbacks=cast(Any, event_sink),
            skill_resolver=resolver,
            checkpointer=active_checkpointer,
        )
        graph = assembled.graph

        invoke_config = _apply_resume_context_overrides(graph, compiled, invoke_config, context_overrides)
        invoke_config = _apply_resume_human_response(graph, invoke_config, human_response)
        result = graph.invoke(None, config=invoke_config)

    except Exception as exc:
        if isinstance(exc, _ResumeInputError):
            raise
        failed_result = _resume_failed_result(
            exc,
            run_id=run_id,
            skill_id=skill_id,
            started_at=started_at,
            started_monotonic=started_monotonic,
        )
        _write_workflow_result_artifacts(
            trace_output,
            failed_result,
        )
        _emit_v030_event(
            event_sink,
            RunEndedEvent(
                run_id=run_id,
                thread_id=run_id,
                status="crashed",
                final_context={},
                wall_time_seconds=failed_result.wall_time_sec,
            )
        )
        return failed_result

    # Step 7: Successful path execution metrics & context extraction
    wall_time = round(time.monotonic() - started_monotonic, 3)
    final_context = _finalize_successful_v030_run(
        result,
        compiled=compiled,
        event_sink=event_sink,
        run_id=run_id,
        trace_output=trace_output,
        wall_time=wall_time,
    )

    saved_trace_path = str(event_sink.trace_path) if event_sink.trace_path is not None else None
    workflow_result = WorkflowResult(
        success=True,
        run_id=run_id,
        skill_id=skill_id,
        context=final_context,
        metrics=WorkflowMetrics.from_mapping({"wall_time_sec": wall_time}, wall_time_sec=wall_time),
        trace_path=Path(saved_trace_path) if saved_trace_path else None,
        error=None,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        wall_time_sec=wall_time,
    )

    _write_workflow_result_artifacts(trace_output, workflow_result)
    return workflow_result


def evaluate_golden_baseline(
    skill_path: str | Path,
    *,
    workspace_dir: Path,
    baseline_id: str,
    skill_resolver: SkillResolverProtocol,
    model_resolver: Any | None = None,
) -> dict[str, Any]:
    """Evaluate skill outputs against golden baseline test cases."""
    _validate_workspace_dir(workspace_dir)
    from graph_agent.core._predict_internal.golden_eval import evaluate_golden_baseline_impl
    return evaluate_golden_baseline_impl(
        skill_path,
        workspace_dir=workspace_dir,
        baseline_id=baseline_id,
        skill_resolver=skill_resolver,
        model_resolver=model_resolver,
    )


def _run_skill_dict(
    skill_path: str | Path,
    *,
    mock_llm: Any = _NO_MOCK_LLM,
    workspace_dir: Path,
    thread_id: str | None = None,
    unattended: bool = False,
    event_subscriber: Callable[[CallbackEvent], None] | None = None,
    callbacks: list[Any] | None = None,
    artifact_saver: Any | None = None,
    initial_context: dict[str, Any] | None = None,
    cleanup_checkpoints_on_finish: bool = True,
    skill_resolver: SkillResolverProtocol,
    model_resolver: Any | None = None,
    llm_provider: LLMProvider | None = None,
    **inputs: Any,
) -> dict[str, Any]:
    """Execute a SKILL.md with the given inputs. Pure document-driven.

    Args:
        skill_path: Path to SKILL.md.
        workspace_dir: Absolute workspace root for run-scoped artifacts.
        thread_id: Optional thread_id for checkpoint resume.
        event_subscriber: Optional function called synchronously for each
            typed CallbackEvent.
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
        - ``trace_path``: Path to ``trace.jsonl``
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
            event_subscriber=event_subscriber,
            callbacks=callbacks,
            skill_resolver=resolver,
            model_resolver=model_resolver,
            llm_provider=llm_provider,
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


_LLM_PROVIDER_UNSET = object()


def _optional_llm_provider(value: LLMProvider | None | object) -> LLMProvider | None:
    if value is _LLM_PROVIDER_UNSET:
        return None
    return cast(LLMProvider | None, value)


class RawSkillPathError(Exception):
    def __init__(self, message: str = "raw skill_path is not allowed") -> None:
        super().__init__(message)
        self.error_code = "runtime.raw_skill_path"


class MissingRunArtifactObjectRefError(Exception):
    def __init__(self, run_id: str, path: str) -> None:
        super().__init__(f"Run artifact store did not return an object ref for {path}")
        self.error_code = "artifact.missing_object_ref"
        self.details = {"run_id": run_id, "path": path}


_RUN_CACHE: dict[str, RunSession] = {}


def _cached_session_for_materialization(
    idempotency_key: str,
    run_artifact_store: RunArtifactStore | None,
) -> RunSession | None:
    cached = _RUN_CACHE.get(idempotency_key)
    if cached is None:
        return None
    if run_artifact_store is None:
        return cached
    if isinstance(cached.result_ref, str) and cached.result_ref.startswith("bytes://"):
        return cached
    return None


def _artifact_run_id(request: RunArtifactRequest | PredictArtifactRequest) -> str:
    requested = request.execution_context.get("thread_id") or request.execution_context.get("run_id")
    if isinstance(requested, str) and requested:
        return requested
    return f"run-{request.artifact_ref.artifact_id}-{request.idempotency_key}"


def _artifact_hash_hex(request: RunArtifactRequest | PredictArtifactRequest) -> str | None:
    content_hash = request.artifact_ref.content_hash
    if content_hash.startswith("sha256:"):
        return content_hash.split(":", 1)[1]
    return None


def _resolve_artifact_root(request: RunArtifactRequest | PredictArtifactRequest) -> Path | None:
    explicit = request.execution_context.get("artifact_root")
    if isinstance(explicit, str) and explicit:
        path = Path(explicit)
        if (path / "GRAPH.md").is_file():
            return path

    sha256_val = _artifact_hash_hex(request)
    workspace_raw = request.execution_context.get("workspace_dir")
    if not isinstance(workspace_raw, str) or not workspace_raw or sha256_val is None:
        return None

    workspace_dir = Path(workspace_raw)
    candidates = (
        workspace_dir / "ephemeral_run_skills" / sha256_val,
        workspace_dir.parent / "ephemeral_run_skills" / sha256_val,
    )
    for candidate in candidates:
        if (candidate / "GRAPH.md").is_file():
            return candidate
    return None


def _resolve_artifact_workspace_dir(request: RunArtifactRequest | PredictArtifactRequest) -> Path | None:
    workspace_raw = request.execution_context.get("workspace_dir")
    if isinstance(workspace_raw, str) and workspace_raw:
        return Path(workspace_raw)
    return None


def _artifact_skill_resolver(
    artifact_root: Path,
    skill_resolver: SkillResolverProtocol | None,
) -> SkillResolverProtocol:
    if skill_resolver is not None:
        return skill_resolver
    return LocalWorkspaceResolver(search_paths=[artifact_root, artifact_root.parent])


def _run_compiled_artifact_graph(
    request: RunArtifactRequest,
    *,
    run_id: str,
    skill_resolver: SkillResolverProtocol | None,
    llm_provider: LLMProvider | None,
    model_resolver: Any | None,
) -> RunResult | RunArtifactErrorResult:
    artifact_root = _resolve_artifact_root(request)
    workspace_dir = _resolve_artifact_workspace_dir(request)
    if artifact_root is None or workspace_dir is None:
        return RunArtifactErrorResult(
            error_code="llm.provider_not_configured",
            error_payload={
                "error_code": "llm.provider_not_configured",
                "message": "LLM Provider is not configured",
                "details": {"artifact_root": str(artifact_root) if artifact_root else None},
                "retryable": False,
            },
            run_id=run_id,
            retryable=False,
        )

    event_subscriber = request.execution_context.get("event_subscriber")
    checkpointer_spec = request.execution_context.get("checkpointer_spec")
    if checkpointer_spec is None:
        checkpointer_spec = request.execution_context.get("checkpointer")
    started_at = datetime.now(UTC)
    raw = _run_v030_skill_dict(
        artifact_root,
        workspace_dir=workspace_dir,
        mock_llm=_NO_MOCK_LLM,
        thread_id=run_id,
        event_subscriber=event_subscriber if callable(event_subscriber) else None,
        skill_resolver=_artifact_skill_resolver(artifact_root, skill_resolver),
        llm_provider=llm_provider,
        model_resolver=model_resolver,
        checkpointer_spec=checkpointer_spec or "auto",
        **request.inputs,
    )
    wall_time = float(raw.get("wall_time_sec", 0.0))
    workflow_result = WorkflowResult(
        success=True,
        run_id=str(raw.get("run_id") or run_id),
        skill_id=artifact_root.name,
        context=dict(raw.get("context", {})),
        metrics=WorkflowMetrics.from_mapping(dict(raw.get("metrics", {})), wall_time_sec=wall_time),
        trace_path=raw.get("trace_path"),
        error=None,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        wall_time_sec=wall_time,
    )
    run_dir = Path(raw.get("run_dir") or workspace_dir / "runs" / workflow_result.run_id)
    _write_workflow_result_artifacts(run_dir, workflow_result)
    return workflow_result


def _run_compiled_artifact_predict_graph(
    request: PredictArtifactRequest,
    *,
    run_id: str,
    skill_resolver: SkillResolverProtocol | None,
    llm_provider: LLMProvider | None,
    model_resolver: Any | None,
) -> RunResult | RunArtifactErrorResult:
    artifact_root = _resolve_artifact_root(request)
    workspace_dir = _resolve_artifact_workspace_dir(request)
    if artifact_root is None or workspace_dir is None:
        return RunArtifactErrorResult(
            error_code="llm.provider_not_configured",
            error_payload={
                "error_code": "llm.provider_not_configured",
                "message": "LLM Provider is not configured",
                "details": {"artifact_root": str(artifact_root) if artifact_root else None},
                "retryable": False,
            },
            run_id=run_id,
            retryable=False,
        )

    return predict_skill(
        artifact_root,
        workspace_dir=workspace_dir,
        thread_id=run_id,
        unattended=True,
        skill_resolver=_artifact_skill_resolver(artifact_root, skill_resolver),
        llm_provider=llm_provider,
        model_resolver=model_resolver,
        mock_llm=request.execution_context.get("mock_llm"),
        current_hashes=request.execution_context.get("current_hashes") or {},
        **request.inputs,
    )


def _workflow_result_ref(result: WorkflowResult | RunResult, workspace_dir: Path | None) -> str | None:
    if workspace_dir is None:
        return None
    result_path = workspace_dir / "runs" / result.run_id / "result.json"
    if result_path.is_file():
        return f"file://{result_path}"
    return None


def _artifact_not_materialized_error(
    request: RunArtifactRequest | PredictArtifactRequest,
    run_id: str,
) -> RunArtifactErrorResult:
    return RunArtifactErrorResult(
        error_code="runtime.artifact_not_materialized",
        error_payload={
            "error_code": "runtime.artifact_not_materialized",
            "message": "Artifact bytes are not materialized for graph execution",
            "details": {
                "artifact_id": request.artifact_ref.artifact_id,
                "content_hash": request.artifact_ref.content_hash,
            },
            "retryable": False,
        },
        run_id=run_id,
        retryable=False,
    )


def _safe_provider_error_details(raw_details: Any) -> dict[str, Any]:
    if not isinstance(raw_details, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, value in raw_details.items():
        key_text = str(key)
        if _contains_sensitive_error_text(key_text):
            continue
        safe[key_text] = _sanitize_provider_error_value(value)
    return safe


def _sanitize_provider_error_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _safe_provider_error_details(value)
    if isinstance(value, list):
        return [_sanitize_provider_error_value(item) for item in value]
    if isinstance(value, str) and _contains_sensitive_error_text(value):
        return "[redacted]"
    return value


def _safe_provider_error_message(exc: Exception) -> str:
    error_code = str(getattr(exc, "error_code", ""))
    if isinstance(exc, LLMProviderError) or error_code.startswith("llm."):
        return "Provider invocation failed"
    message = str(exc)
    return "[redacted]" if _contains_sensitive_error_text(message) else message


def _contains_sensitive_error_text(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in (
            "secret",
            "api_key",
            "apikey",
            "authorization",
            "traceback",
            "token",
            "sk-",
        )
    )


def _execute_run_artifact_outputs(
    request: RunArtifactRequest,
    *,
    run_id: str,
    artifact_executor: Callable[[RunArtifactRequest], dict[str, Any]] | None,
    skill_resolver: SkillResolverProtocol | None,
    llm_provider: LLMProvider | None,
    model_resolver: Any | None,
) -> dict[str, Any] | RunResult | RunArtifactErrorResult:
    if artifact_executor is not None:
        return artifact_executor(request)

    artifact_root = _resolve_artifact_root(request)
    if artifact_root is not None:
        return _run_compiled_artifact_graph(
            request,
            run_id=run_id,
            skill_resolver=skill_resolver,
            llm_provider=llm_provider,
            model_resolver=model_resolver,
        )

    return _artifact_not_materialized_error(request, run_id)


def _run_artifact_store_result(
    *,
    run_artifact_store: RunArtifactStore,
    run_id: str,
    request: RunArtifactRequest | PredictArtifactRequest,
    outputs: Any,
) -> str:
    metadata = {"artifact_id": request.artifact_ref.artifact_id}
    run_artifact_store.begin_run(run_id, metadata)

    if hasattr(outputs, "model_dump"):
        serializable_outputs = outputs.model_dump(mode="json")
    else:
        serializable_outputs = outputs
    data_bytes = json.dumps(serializable_outputs, default=str).encode("utf-8")
    refs = run_artifact_store.put_batch(run_id, {"outputs.json": data_bytes})

    ref_val = _outputs_object_ref(refs, run_id=run_id)
    run_artifact_store.seal_run(run_id)

    return ref_val.bytes_ref


def _outputs_object_ref(refs: dict[str, ObjectRef] | list[ObjectRef], *, run_id: str) -> ObjectRef:
    ref_val: ObjectRef | None = None
    if isinstance(refs, dict):
        ref_val = refs.get("outputs.json")
    elif isinstance(refs, list) and refs:
        ref_val = refs[0]

    if ref_val is None:
        raise MissingRunArtifactObjectRefError(run_id, "outputs.json")
    bytes_ref = getattr(ref_val, "bytes_ref", None)
    if not isinstance(bytes_ref, str) or not bytes_ref.startswith("bytes://"):
        raise MissingRunArtifactObjectRefError(run_id, "outputs.json")
    return ref_val


def run_artifact(
    request: RunArtifactRequest | None = None,
    *,
    artifact_executor: Callable[[RunArtifactRequest], dict[str, Any]] | None = None,
    run_artifact_store: RunArtifactStore | None = None,
    llm_provider: LLMProvider | None | object = _LLM_PROVIDER_UNSET,
    skill_resolver: SkillResolverProtocol | None = None,
    model_resolver: Any | None = None,
    **legacy_kwargs: Any,
) -> RunSession | RunArtifactErrorResult:
    if "skill_path" in legacy_kwargs:
        raise RawSkillPathError()

    if request is None or not isinstance(request, RunArtifactRequest):
        raise TypeError("request must be an instance of RunArtifactRequest")

    run_id = _artifact_run_id(request)

    cached = _cached_session_for_materialization(request.idempotency_key, run_artifact_store)
    if cached is not None:
        return cached

    workspace_dir = _resolve_artifact_workspace_dir(request)
    try:
        outputs = _execute_run_artifact_outputs(
            request,
            run_id=run_id,
            artifact_executor=artifact_executor,
            skill_resolver=skill_resolver,
            llm_provider=_optional_llm_provider(llm_provider),
            model_resolver=model_resolver,
        )
        if isinstance(outputs, RunArtifactErrorResult):
            return outputs
    except Exception as exc:
        error_code = getattr(exc, "error_code", "llm.provider_invoke_failed")
        message = _safe_provider_error_message(exc)
        details = _safe_provider_error_details(getattr(exc, "details", {}))
        retryable = getattr(exc, "retryable", False)

        return RunArtifactErrorResult(
            error_code=error_code,
            error_payload={
                "error_code": error_code,
                "message": message,
                "details": details,
                "retryable": retryable,
            },
            run_id=run_id,
            retryable=retryable,
        )

    result_ref = _workflow_result_ref(outputs, workspace_dir) if isinstance(outputs, RunResult) else None
    if run_artifact_store is not None:
        result_ref = _run_artifact_store_result(
            run_artifact_store=run_artifact_store,
            run_id=run_id,
            request=request,
            outputs=outputs,
        )

    session = RunSession(
        run_id=run_id,
        event_stream_ref=f"stream://{run_id}",
        result_ref=result_ref,
        status_ref=f"state://{run_id}/status",
    )
    _RUN_CACHE[request.idempotency_key] = session
    return session


def predict_artifact(
    request: PredictArtifactRequest | RunArtifactRequest,
    *,
    artifact_executor: Callable[[RunArtifactRequest], dict[str, Any]] | None = None,
    run_artifact_store: RunArtifactStore | None = None,
    llm_provider: LLMProvider | None | object = _LLM_PROVIDER_UNSET,
    skill_resolver: SkillResolverProtocol | None = None,
    model_resolver: Any | None = None,
) -> RunSession | RunArtifactErrorResult:
    from graph_agent.core.adapter_contracts import PredictArtifactRequest, RunArtifactRequest

    if not isinstance(request, (PredictArtifactRequest, RunArtifactRequest)):
        raise TypeError("request must be an instance of PredictArtifactRequest or RunArtifactRequest")

    if isinstance(request, PredictArtifactRequest) and _resolve_artifact_root(request) is not None:
        run_id = _artifact_run_id(request)
        cached = _cached_session_for_materialization(request.idempotency_key, run_artifact_store)
        if cached is not None:
            return cached
        try:
            result = _run_compiled_artifact_predict_graph(
                request,
                run_id=run_id,
                skill_resolver=skill_resolver,
                llm_provider=_optional_llm_provider(llm_provider),
                model_resolver=model_resolver,
            )
            if isinstance(result, RunArtifactErrorResult):
                return result
        except Exception as exc:
            error_code = getattr(exc, "error_code", "llm.provider_invoke_failed")
            message = _safe_provider_error_message(exc)
            details = _safe_provider_error_details(getattr(exc, "details", {}))
            retryable = getattr(exc, "retryable", False)
            return RunArtifactErrorResult(
                error_code=error_code,
                error_payload={
                    "error_code": error_code,
                    "message": message,
                    "details": details,
                    "retryable": retryable,
                },
                run_id=run_id,
                retryable=retryable,
            )
        workspace_dir = _resolve_artifact_workspace_dir(request)
        result_ref = _workflow_result_ref(result, workspace_dir)
        if run_artifact_store is not None:
            result_ref = _run_artifact_store_result(
                run_artifact_store=run_artifact_store,
                run_id=run_id,
                request=request,
                outputs=result,
            )
        session = RunSession(
            run_id=run_id,
            event_stream_ref=f"stream://{run_id}",
            result_ref=result_ref,
            status_ref=f"state://{run_id}/status",
        )
        _RUN_CACHE[request.idempotency_key] = session
        return session

    run_request = RunArtifactRequest(
        artifact_ref=request.artifact_ref,
        inputs=request.inputs,
        execution_context=request.execution_context,
        idempotency_key=request.idempotency_key,
    )
    return run_artifact(
        run_request,
        artifact_executor=artifact_executor,
        run_artifact_store=run_artifact_store,
        llm_provider=llm_provider,
        skill_resolver=skill_resolver,
        model_resolver=model_resolver,
    )


def _validate_workspace_dir(workspace_dir: Path) -> Path:

    workspace_path = Path(workspace_dir)
    if not workspace_path.is_absolute():
        raise ValueError("workspace_dir must be an absolute path")
    return workspace_path


def _validate_resume_human_response(human_response: dict[str, Any] | None) -> None:
    if human_response is None:
        return
    if not isinstance(human_response, dict):
        raise TypeError("human_response must be a dictionary")
    if "content" not in human_response:
        raise ValueError("human_response must contain 'content'")
    if not isinstance(human_response["content"], str):
        raise TypeError("human_response['content'] must be a string")
    if "tool_call_id" in human_response and human_response["tool_call_id"] is not None:
        if not isinstance(human_response["tool_call_id"], str):
            raise TypeError("human_response['tool_call_id'] must be a string")


def _validate_resume_context_overrides(context_overrides: dict[str, Any] | None) -> None:
    if context_overrides is None:
        return
    if not isinstance(context_overrides, dict):
        raise TypeError("context_overrides must be a dictionary")
    forbidden = [
        key
        for key in context_overrides
        if key.startswith("_") or key in _RESUME_CONTEXT_OVERRIDE_FORBIDDEN_KEYS
    ]
    if forbidden:
        joined = ", ".join(sorted(forbidden))
        raise ValueError(f"context_overrides may only contain business fields; forbidden: {joined}")


def _resolve_resume_checkpointer() -> Any:
    active_checkpointer = resolve_checkpointer("auto")
    if active_checkpointer is None or active_checkpointer is True:
        raise RuntimeError("No active checkpointer configured for resume_skill")
    return cast(Any, active_checkpointer)


def _resolve_resume_config(
    active_checkpointer: Any,
    *,
    run_id: str,
    checkpoint_ns: str | None,
    checkpoint_id: str | None,
) -> dict[str, Any]:
    ns = checkpoint_ns or ""
    resolved_checkpoint_id = checkpoint_id
    if not resolved_checkpoint_id:
        search_config = {"configurable": {"thread_id": run_id, "checkpoint_ns": ns}}
        checkpoints = list(active_checkpointer.list(search_config))
        if not checkpoints:
            raise ValueError(f"No checkpoints found in namespace {ns!r} for run_id {run_id!r}")
        resolved_checkpoint_id = str(checkpoints[0].checkpoint["id"])

    return {
        "configurable": {
            "thread_id": run_id,
            "checkpoint_ns": ns,
            "checkpoint_id": resolved_checkpoint_id,
        }
    }


def _override_source_node(compiled: Any, overridden_fields: set[str]) -> str | None:
    matching_nodes: list[str] = []
    for node in compiled.nodes:
        io = node.frontmatter.get("io") or {}
        outputs = io.get("outputs") or {}
        properties = outputs.get("properties") or {}
        if any(field in properties for field in overridden_fields):
            matching_nodes.append(node.phase_name)
    return matching_nodes[-1] if matching_nodes else None


def _apply_resume_context_overrides(
    graph: Any,
    compiled: Any,
    invoke_config: dict[str, Any],
    context_overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    if not context_overrides:
        return invoke_config

    current_state = graph.get_state(invoke_config)
    existing_data = current_state.values.get("data")
    raw_data = existing_data.model_dump() if hasattr(existing_data, "model_dump") else dict(existing_data or {})
    raw_data.update(context_overrides)
    updated_data = BusinessData.model_validate(raw_data)

    as_node = None
    if not current_state.next:
        as_node = _override_source_node(compiled, set(context_overrides.keys()))

    return cast(dict[str, Any], graph.update_state(invoke_config, {"data": updated_data}, as_node=as_node))


def _pending_tool_calls(state_messages: list[Any]) -> list[dict[str, Any]]:
    ai_tool_calls: dict[str, dict[str, Any]] = {}
    answered_tool_call_ids: set[str] = set()
    for msg in state_messages:
        for tool_call in getattr(msg, "tool_calls", None) or []:
            if isinstance(tool_call, dict) and "id" in tool_call:
                ai_tool_calls[tool_call["id"]] = tool_call

        is_tool_msg = msg.__class__.__name__ == "ToolMessage" or getattr(msg, "type", None) == "tool"
        if is_tool_msg:
            tool_call_id = getattr(msg, "tool_call_id", None)
            if tool_call_id:
                answered_tool_call_ids.add(tool_call_id)

    return [
        tool_call
        for tool_call_id, tool_call in ai_tool_calls.items()
        if tool_call_id not in answered_tool_call_ids
    ]


def _select_pending_tool_call_id(
    pending_tool_calls: list[dict[str, Any]],
    requested_tool_call_id: str | None,
) -> str:
    if not pending_tool_calls:
        raise _ResumeInputError("human_response requires a pending interrupt/tool call in the selected checkpoint")
    if len(pending_tool_calls) == 1:
        single_id = pending_tool_calls[0]["id"]
        if requested_tool_call_id and requested_tool_call_id != single_id:
            raise ValueError(
                f"Requested tool_call_id {requested_tool_call_id!r} does not match pending tool call {single_id!r}"
            )
        return str(single_id)
    if not requested_tool_call_id:
        raise ValueError("Multiple pending tool calls exist. 'tool_call_id' is required for human_response.")
    if requested_tool_call_id not in [tool_call["id"] for tool_call in pending_tool_calls]:
        raise ValueError(f"Requested tool_call_id {requested_tool_call_id!r} is not among pending tool calls.")
    return requested_tool_call_id


def _apply_resume_human_response(
    graph: Any,
    invoke_config: dict[str, Any],
    human_response: dict[str, Any] | None,
) -> dict[str, Any]:
    if human_response is None:
        return invoke_config

    current_state = graph.get_state(invoke_config)
    state_messages = current_state.values.get("messages", []) or []
    final_tool_call_id = _select_pending_tool_call_id(
        _pending_tool_calls(state_messages),
        human_response.get("tool_call_id"),
    )
    as_node = current_state.next[0] if current_state.next else None
    tool_msg = ToolMessage(content=human_response["content"], tool_call_id=final_tool_call_id)
    return cast(dict[str, Any], graph.update_state(invoke_config, {"messages": [tool_msg]}, as_node=as_node))


def _resume_error_payload(exc: Exception) -> Any:
    if isinstance(exc, GraphAgentError) and exc.payload is not None:
        return exc.payload
    return make_error_payload(_RUNTIME_PHASE_FAILED_CODE, str(exc))


def _finalize_successful_v030_run(
    result: Any,
    *,
    compiled: Any,
    event_sink: Any,
    run_id: str,
    trace_output: Path,
    wall_time: float,
) -> dict[str, Any]:
    final_context = result["data"].model_dump()
    output_context = _context_with_framework_output_sources(final_context, result)
    compiled_raw = getattr(compiled, "raw", {})
    output_schema = (
        compiled_raw.get("io", {}).get("outputs") if isinstance(compiled_raw, dict) else None
    )
    _save_v030_declared_file_outputs(
        output_schema,
        output_context,
        default_output_dir=trace_output / "artifacts",
    )
    _emit_v030_event(
        event_sink,
        RunEndedEvent(
            run_id=run_id,
            thread_id=run_id,
            status="completed",
            final_context=_v030_phase_context(final_context),
            wall_time_seconds=wall_time,
        ),
    )
    return cast(dict[str, Any], final_context)


def _resume_failed_result(
    exc: Exception,
    *,
    run_id: str,
    skill_id: str,
    started_at: datetime,
    started_monotonic: float,
) -> WorkflowResult:
    wall_time = round(time.monotonic() - started_monotonic, 3)
    return WorkflowResult(
        success=False,
        run_id=run_id,
        skill_id=skill_id,
        context={},
        metrics=WorkflowMetrics(wall_time_sec=wall_time),
        trace_path=None,
        error=_resume_error_payload(exc),
        started_at=started_at,
        finished_at=datetime.now(UTC),
        wall_time_sec=wall_time,
    )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _write_workflow_result_artifacts(run_dir: Path, result: WorkflowResult | RunResult) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "result.json", result.model_dump(mode="json"))
    _write_json(run_dir / "final_state.json", result.context)
    _write_json(run_dir / "metrics.json", result.metrics.model_dump(mode="json"))


def _prepare_v030_event_sink(
    *,
    trace_output: Path,
    event_subscriber: Callable[[CallbackEvent], None] | None = None,
    callbacks: list[Any] | None = None,
) -> _CompositeEventSink:
    sinks: list[Any] = [_TraceJsonlSink(trace_output)]
    if event_subscriber is not None:
        sinks.append(_SubscriberSink(event_subscriber))
    if callbacks:
        sinks.append(_CallbackSink(callbacks))
    return _CompositeEventSink(sinks)


def _emit_v030_event(event_sink: Any, event: CallbackEvent) -> None:
    _safe_emit_event(event_sink, event)


def _v030_phase_context(data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {"inputs": {}, "phase_outputs": {}, "scratch": {}}
    if "inputs" in data or "phase_outputs" in data or "scratch" in data:
        normalized = normalize_blackboard_data(data)
        return {
            "inputs": dict(normalized["inputs"]),
            "phase_outputs": dict(normalized["phase_outputs"]),
            "scratch": dict(normalized["scratch"]),
        }
    phase_outputs: dict[str, dict[str, Any]] = {}
    if "answer" in data:
        phase_outputs["draft"] = {"answer": data["answer"]}
        phase_outputs["main"] = {"answer": data["answer"]}
    if "review" in data:
        phase_outputs["review"] = {"review": data["review"]}
    return {
        "inputs": dict(data),
        "phase_outputs": phase_outputs,
        "scratch": {},
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
        and schema.get("target") in {"file", "artifact"}
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
    try:
        io_mgr.save_outputs(
            output_context,
            output_dir=output_context.get("output_dir") or default_output_dir,
        )
    except GraphAgentError:
        raise
    except Exception as exc:
        detail = str(exc)
        raise GraphAgentFatalError(
            detail,
            payload=make_error_payload("[F-v3-runtime-state-mapping-failed]", detail),
        ) from exc


def _context_with_framework_output_sources(
    context: dict[str, Any],
    final_state: Any,
) -> dict[str, Any]:
    output_context = dict(context)
    flow = final_state.get("flow") if isinstance(final_state, dict) else None
    finish_task_result = getattr(flow, "finish_task_result", None)
    if isinstance(flow, dict):
        finish_task_result = flow.get("finish_task_result")
    if isinstance(finish_task_result, dict):
        business_data_md = finish_task_result.get("business_data_md")
        if isinstance(business_data_md, str) and business_data_md:
            output_context["business_data_md"] = business_data_md
    return output_context


def _run_v030_skill_dict(
    skill_root: Path,
    *,
    mock_llm: Any = _NO_MOCK_LLM,
    workspace_dir: Path,
    thread_id: str | None = None,
    event_subscriber: Callable[[CallbackEvent], None] | None = None,
    callbacks: list[Any] | None = None,
    skill_resolver: SkillResolverProtocol,
    model_resolver: Any | None = None,
    llm_provider: LLMProvider | None = None,
    checkpointer_spec: Any = "auto",
    **inputs: Any,
) -> dict[str, Any]:
    """Execute a V0.3.0 skill root through compile_skill + assemble_graph."""

    from graph_agent.core.checkpointer import resolve_checkpointer
    from graph_agent.core.compiler import compile_skill
    from graph_agent.core.graph_assembler import assemble_graph
    from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState

    resolver = require_skill_resolver(skill_resolver, caller="_run_v030_skill_dict")
    t0 = time.time()
    run_id = thread_id or str(uuid.uuid4())
    trace_output = workspace_dir / "runs" / run_id
    event_sink = _prepare_v030_event_sink(
        trace_output=trace_output,
        event_subscriber=event_subscriber,
        callbacks=callbacks,
    )
    _emit_v030_event(
        event_sink,
        RunStartedEvent(
            run_id=run_id,
            thread_id=run_id,
            initial_context={"inputs": dict(inputs)},
        ),
    )
    chat_model = mock_llm if mock_llm is not _NO_MOCK_LLM else None
    active_model_resolver = model_resolver if mock_llm is _NO_MOCK_LLM else None
    active_llm_provider = llm_provider if mock_llm is _NO_MOCK_LLM else None

    # Step 4.1: Dynamically resolve the checkpointer
    active_checkpointer = resolve_checkpointer(checkpointer_spec)

    try:
        compiled = compile_skill(skill_root, skill_resolver=resolver)
        assembled = assemble_graph(
            compiled,
            chat_model=chat_model,
            model_resolver=active_model_resolver,
            llm_provider=active_llm_provider,
            callbacks=cast(Any, event_sink),
            skill_resolver=resolver,
            checkpointer=active_checkpointer,
        )
        graph = assembled.graph

        # Step 4.2: Build the type-safe initial state using WorkflowState Pydantic models
        initial_state = WorkflowState(
            data=BusinessData.model_validate(dict(inputs)),
            flow=FrameworkState.model_validate({
                "run_id": run_id,
                "thread_id": run_id,
                "unattended": inputs.get("_unattended", False),
                "persistent_storage_config": {"workspace_dir": str(workspace_dir)},
            }),
            messages=[],
        )

        # Step 4.3: Invoke the LangGraph compiled StateGraph natively passing the thread_id
        result = graph.invoke(
            initial_state,
            config={"configurable": {"thread_id": run_id}},
        )
    except Exception:
        wall_time = round(time.time() - t0, 3)
        _emit_v030_event(
            event_sink,
            RunEndedEvent(
                run_id=run_id,
                thread_id=run_id,
                status="crashed",
                final_context={},
                wall_time_seconds=wall_time,
            ),
        )
        raise
    wall_time = round(time.time() - t0, 3)

    # Step 4.4: Extract flat business output data directly from model_dump
    final_context = _finalize_successful_v030_run(
        result,
        compiled=compiled,
        event_sink=event_sink,
        run_id=run_id,
        trace_output=trace_output,
        wall_time=wall_time,
    )
    saved_trace_path = str(event_sink.trace_path) if event_sink.trace_path is not None else None
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
        description=(
            f"Run a {_SKILL_ENTRYPOINT_FILENAME} workflow "
            "(document-driven, no per-skill Python code needed)"
        )
    )
    parser.add_argument("--skill", required=True, help=f"Path to {_SKILL_ENTRYPOINT_FILENAME}")
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
                "wall_time_sec": result.wall_time_sec,
                "metrics": result.metrics,
                "trace_path": result.trace_path,
            },
            indent=2,
            default=str,
        ),
    )


if __name__ == "__main__":
    main()
