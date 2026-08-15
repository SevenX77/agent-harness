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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
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
    InterruptedEvent,
    ResumedEvent,
    RunEndedEvent,
    RunStartedEvent,
)
from graph_agent.core.adapter_contracts import (
    PredictArtifactRequest,
    RunArtifactErrorResult,
    RunArtifactRequest,
    RunSession,
)
from graph_agent.core.checkpoint_validity import checkpoint_id_before_phase
from graph_agent.core.checkpointer import resolve_checkpointer
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import (
    GraphAgentError,
    GraphAgentFatalError,
    LoaderError,
    SkillLoadError,
    make_error_payload,
)
from graph_agent.core.graph_assembler import assemble_graph, read_runtime_input_binding_value
from graph_agent.core.llm_provider import LLMProvider, LLMProviderError
from graph_agent.core.loader import DECLARED_OUTPUT_TARGETS
from graph_agent.core.local_workspace_resolver import (
    LocalWorkspaceResolver,
    default_local_resolver_for_skill,
)
from graph_agent.core.result import RunResult, WorkflowMetrics, WorkflowResult
from graph_agent.core.skill_resolver_protocol import SkillResolverProtocol, require_skill_resolver
from graph_agent.core.state import BusinessData
from graph_agent.core.storage_contracts import ObjectRef, RunArtifactStore
from graph_agent.io.artifact_manifest import write_manifest_artifacts
from graph_agent.io.run_layout import predicts_root, runs_root
from graph_agent.runtime.state import normalize_blackboard_data

logger = logging.getLogger(__name__)

_NO_MOCK_LLM = object()
_RUNTIME_PHASE_FAILED_CODE = "[F-v3-runtime-phase-failed]"
_SKILL_ENTRYPOINT_FILENAME = "SKILL.md"
_HITL_TOOL_NAMES = {"ask_clarification"}


def _runtime_input_fields_from_config(
    runtime_config: dict[str, Any] | None,
) -> dict[str, set[str]] | None:
    if not isinstance(runtime_config, dict):
        return None
    inputs = runtime_config.get("inputs")
    if not isinstance(inputs, dict):
        return None
    active = inputs.get("active")
    if not isinstance(active, dict):
        return None
    phases = active.get("phases")
    if not isinstance(phases, dict):
        return None
    result: dict[str, set[str]] = {}
    for phase_id, bindings in phases.items():
        if not isinstance(phase_id, str) or not isinstance(bindings, dict):
            continue
        fields = {
            field for field, value in bindings.items() if isinstance(field, str) and isinstance(value, dict)
        }
        if fields:
            result[phase_id] = fields
    return result or None


def _runtime_artifacts_from_config(runtime_config: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(runtime_config, dict):
        return []
    raw = runtime_config.get("artifacts")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _runtime_root_inputs_from_config(
    runtime_config: dict[str, Any] | None,
    workspace_dir: Path,
) -> dict[str, Any]:
    if not isinstance(runtime_config, dict):
        return {}
    inputs = runtime_config.get("inputs")
    if not isinstance(inputs, dict):
        return {}
    active = inputs.get("active")
    if not isinstance(active, dict):
        return {}
    root = active.get("root")
    if not isinstance(root, dict):
        return {}
    materialized: dict[str, Any] = {}
    for field_name, binding in root.items():
        if not isinstance(field_name, str) or not isinstance(binding, dict):
            continue
        materialized[field_name] = read_runtime_input_binding_value(field_name, binding, workspace_dir)
    return materialized


@dataclass(frozen=True)
class _HitLInterruptCheckpoint:
    checkpoint_id: str
    checkpoint_ns: str
    phase_name: str
    question: str | None = None
    clarification_type: str | None = None
    options: list[str] | None = None


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
    skill_resolver: SkillResolverProtocol | None = None,
    model_resolver: Any | None = None,
    llm_provider: LLMProvider | None = None,
    copilot_predict: Callable[..., Any] | None = None,
    runtime_config: dict[str, Any] | None = None,
    **inputs: Any,
) -> RunResult:
    """Run skill compilation and execution in Predict mode with caching and mock generation."""
    from collections import Counter

    from graph_agent import PathDiff
    from graph_agent.core._predict_internal.exporter import assemble_phase_record
    from graph_agent.core._predict_internal.path_diff import compute_diff
    from graph_agent.core._predict_internal.strategy import MockStrategy
    from graph_agent.core._predict_internal.tracing import (
        PredictTracingCallback,
        clear_mock_source_cache,
        clear_validator_downgrades,
        get_validator_downgrade,
    )
    from graph_agent.core.compiler import compile_skill

    resolver = skill_resolver or default_local_resolver_for_skill(skill_path)
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

    # The compile gate for predict: this call is here to REJECT a defective
    # skill before any of it executes, so it is used for the exception it
    # raises, not for a value — the execution path below compiles its own graph
    # from the same path. (Phase output schemas used to be harvested from this
    # result, which silently covered only root phases; the assembler now hands
    # each phase its own schema — decision doc 2026-08-15
    # predict-nested-phase-schema.)
    compile_skill(
        skill_path_obj,
        skill_resolver=resolver,
        runtime_input_fields=_runtime_input_fields_from_config(runtime_config),
    )

    # 1. Strategy setup
    strategy = MockStrategy.from_param(mock_llm)
    _warn_on_stale_golden_hashes_sdk(strategy, current_hashes)

    # 3. Setup Predict interception context & tracing
    # Both records are process-local and keyed by phase name, so a previous
    # predict in the same process would otherwise bleed into this one.
    clear_mock_source_cache()
    clear_validator_downgrades()
    predict_context = SDKPredictContext(strategy, copilot_predict)
    tracing_callback = PredictTracingCallback()
    tracing_callback.on_chain_start(metadata={})

    run_id = thread_id or str(uuid.uuid4())
    run_root = predicts_root(workspace_root)
    trace_output = run_root / run_id

    raw = _run_v030_skill_dict(
        skill_path_obj,
        workspace_dir=workspace_root,
        run_root=run_root,
        thread_id=run_id,
        event_subscriber=event_subscriber,
        callbacks=[tracing_callback],
        skill_resolver=resolver,
        model_resolver=model_resolver,
        llm_provider=llm_provider,
        checkpointer_spec=None,
        runtime_config=runtime_config,
        predict_context=predict_context,
        unattended=unattended,
        persist_declared_outputs=False,
        **inputs,
    )

    finished_at = datetime.now(UTC)
    wall_time = float(raw.get("wall_time_sec", round(time.monotonic() - started_monotonic, 3)))

    # 5. Extract results, path & deadlocks
    final_context = dict(raw.get("context", {}))
    raw_phases = tracing_callback.phases or []
    # Validator downgrades land after the trace stamper has already finalized the
    # phase (the validator runs downstream of phase end), so they are folded in
    # here rather than at stamping time.
    for item in raw_phases:
        downgrade = get_validator_downgrade(str(item.get("phase_name") or item.get("name") or ""))
        if downgrade is not None:
            item["validator_downgraded"] = downgrade
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
        metrics=WorkflowMetrics.from_mapping(dict(raw.get("metrics", {})), wall_time_sec=wall_time),
        trace_path=Path(raw["trace_path"]) if raw.get("trace_path") else trace_output / "trace.jsonl",
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
    skill_resolver: SkillResolverProtocol | None = None,
    model_resolver: Any | None = None,
    llm_provider: LLMProvider | None = None,
    runtime_config: dict[str, Any] | None = None,
    **inputs: Any,
) -> RunResult:
    """Execute a SKILL.md and return a typed workflow result."""
    mock_llm = inputs.pop("mock_llm", _NO_MOCK_LLM)
    resolver = skill_resolver or default_local_resolver_for_skill(skill_path)
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
            runtime_config=runtime_config,
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
            runs_root(workspace_root) / failed_result.run_id,
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
    run_dir = Path(raw.get("run_dir") or runs_root(workspace_root) / workflow_result.run_id)
    _write_workflow_result_artifacts(run_dir, workflow_result)
    return workflow_result


def resume_skill(
    skill_path: str | Path,
    *,
    workspace_dir: Path,
    run_id: str,
    from_phase: str | None = None,
    checkpoint_id: str | None = None,
    checkpoint_ns: str | None = None,
    resume_from_node_id: str | None = None,
    resume_to_node_id: str | None = None,
    checkpointer: Any | None = None,
    context_overrides: dict[str, Any] | None = None,
    human_response: dict[str, Any] | None = None,
    skill_resolver: SkillResolverProtocol | None = None,
    model_resolver: Any | None = None,
    llm_provider: LLMProvider | None = None,
    event_subscriber: Callable[[CallbackEvent], None] | None = None,
    runtime_config: dict[str, Any] | None = None,
) -> RunResult:
    """Resume a previously interrupted skill run from a checkpoint."""
    workspace_root = _validate_workspace_dir(workspace_dir)
    _validate_resume_human_response(human_response)
    _validate_resume_context_overrides(context_overrides)
    _validate_resume_node_selector(from_phase, "from_phase")
    _validate_resume_node_selector(resume_from_node_id, "resume_from_node_id")
    _validate_resume_node_selector(resume_to_node_id, "resume_to_node_id")

    resolver = skill_resolver or default_local_resolver_for_skill(skill_path)
    started_at = datetime.now(UTC)
    started_monotonic = time.monotonic()
    skill_path_obj = Path(skill_path)
    skill_id = (
        skill_path_obj.parent.name
        if skill_path_obj.name == _SKILL_ENTRYPOINT_FILENAME
        else skill_path_obj.stem
    )

    trace_output = runs_root(workspace_root) / run_id
    event_sink = _prepare_v030_event_sink(
        trace_output=trace_output,
        event_subscriber=event_subscriber,
    )

    logger.info(
        "[Resume] Resuming run_id=%s from_phase=%s checkpoint_ns=%s checkpoint_id=%s",
        run_id,
        from_phase,
        checkpoint_ns,
        checkpoint_id,
    )

    active_checkpointer = checkpointer if checkpointer is not None else _resolve_resume_checkpointer()

    try:
        compiled = compile_skill(
            skill_path,
            skill_resolver=resolver,
            runtime_input_fields=_runtime_input_fields_from_config(runtime_config),
        )
        invoke_config = _resolve_resume_config(
            active_checkpointer,
            compiled=compiled,
            run_id=run_id,
            from_phase=from_phase,
            checkpoint_ns=checkpoint_ns,
            checkpoint_id=checkpoint_id,
        )
        selected_checkpoint_id = _checkpoint_id_from_config(invoke_config)
        selected_checkpoint_ns = _checkpoint_ns_from_config(invoke_config)
        _emit_v030_event(
            event_sink,
            RunStartedEvent(
                run_id=run_id,
                thread_id=run_id,
                is_resume=True,
                checkpoint_id=selected_checkpoint_id,
                checkpoint_ns=selected_checkpoint_ns,
                initial_context={
                    "checkpoint_id": selected_checkpoint_id,
                    "checkpoint_ns": selected_checkpoint_ns,
                    "from_phase": from_phase,
                },
            ),
        )
        assembled = assemble_graph(
            compiled,
            model_resolver=model_resolver,
            llm_provider=llm_provider,
            callbacks=cast(Any, event_sink),
            skill_resolver=resolver,
            checkpointer=active_checkpointer,
            runtime_config=runtime_config,
        )
        graph = assembled.graph
        _validate_resume_node_ids(compiled, from_phase, resume_from_node_id, resume_to_node_id)
        _validate_resume_context_override_scope(
            compiled,
            resume_from_node_id or from_phase,
            context_overrides,
        )
        _validate_resume_checkpoint_targets(graph, invoke_config, resume_to_node_id)

        invoke_config = _apply_resume_context_overrides(
            graph,
            compiled,
            invoke_config,
            context_overrides,
            resume_from_node_id=resume_from_node_id or from_phase,
        )
        invoke_config = _apply_resume_human_response(graph, invoke_config, human_response)
        resumed_from_phase = (
            from_phase
            or resume_from_node_id
            or _phase_name_from_checkpoint_ns(selected_checkpoint_ns)
        )
        _emit_v030_event(
            event_sink,
            ResumedEvent(
                thread_id=run_id,
                human_input=str((human_response or {}).get("content") or ""),
                resumed_from_phase=resumed_from_phase,
                checkpoint_id=selected_checkpoint_id,
                checkpoint_ns=selected_checkpoint_ns,
                namespace=selected_checkpoint_ns,
                ns=selected_checkpoint_ns,
            ),
        )
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
        runtime_config=runtime_config,
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
    skill_resolver: SkillResolverProtocol | None = None,
    model_resolver: Any | None = None,
) -> dict[str, Any]:
    """Evaluate skill outputs against golden baseline test cases."""
    _validate_workspace_dir(workspace_dir)
    from graph_agent.core._predict_internal.golden_eval import evaluate_golden_baseline_impl
    return evaluate_golden_baseline_impl(
        skill_path,
        workspace_dir=workspace_dir,
        baseline_id=baseline_id,
        skill_resolver=skill_resolver or default_local_resolver_for_skill(skill_path),
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
    runtime_config: dict[str, Any] | None = None,
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
            run_root=runs_root(workspace_dir),
            mock_llm=mock_llm,
            thread_id=thread_id,
            event_subscriber=event_subscriber,
            callbacks=callbacks,
            skill_resolver=resolver,
            model_resolver=model_resolver,
            llm_provider=llm_provider,
            runtime_config=runtime_config,
            unattended=unattended,
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
    runtime_config = request.execution_context.get("runtime_config")
    if not isinstance(runtime_config, dict):
        runtime_config = None
    checkpointer_spec = request.execution_context.get("checkpointer_spec")
    if checkpointer_spec is None:
        checkpointer_spec = request.execution_context.get("checkpointer")
    started_at = datetime.now(UTC)
    raw = _run_v030_skill_dict(
        artifact_root,
        workspace_dir=workspace_dir,
        run_root=runs_root(workspace_dir),
        mock_llm=_NO_MOCK_LLM,
        thread_id=run_id,
        event_subscriber=event_subscriber if callable(event_subscriber) else None,
        skill_resolver=_artifact_skill_resolver(artifact_root, skill_resolver),
        llm_provider=llm_provider,
        model_resolver=model_resolver,
        checkpointer_spec=checkpointer_spec or "auto",
        runtime_config=runtime_config,
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
    run_dir = Path(raw.get("run_dir") or runs_root(workspace_dir) / workflow_result.run_id)
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

    runtime_config = request.execution_context.get("runtime_config")
    if not isinstance(runtime_config, dict):
        runtime_config = None
    event_subscriber = request.execution_context.get("event_subscriber")
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
        runtime_config=runtime_config,
        event_subscriber=event_subscriber if callable(event_subscriber) else None,
        **request.inputs,
    )


def _workflow_result_ref(result: WorkflowResult | RunResult, run_root: Path | None) -> str | None:
    if run_root is None:
        return None
    result_path = run_root / result.run_id / "result.json"
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


def _engine_error_payload(exc: Exception) -> dict[str, Any] | None:
    """Return the structured payload an engine error raised itself with, if any."""
    payload = getattr(exc, "error_payload", None)
    if isinstance(payload, dict) and payload.get("code"):
        return payload
    return None


def _artifact_error_result(exc: Exception, *, run_id: str) -> RunArtifactErrorResult:
    """Report a run that died of an exception, without inventing a cause for it.

    Every provider failure names itself: `LLMProviderError` takes `error_code` as a
    required constructor argument and `LLMProviderMissingError` carries one at class
    level. So an exception arriving here WITHOUT an `error_code` is, by construction,
    not a provider failure — defaulting to an `llm.*` code told whoever read the
    payload to go look at the gateway for a fault that lives in the engine.
    `_safe_provider_error_message` already draws exactly this line one line below.

    The engine's own fail-fast path DOES classify itself, just through a different
    attribute: `GraphAgentError.__init__` builds an `ErrorPayload` (an `[F-v3-*]`
    code plus the phase and field it happened in) and exposes it as `.payload` /
    `.error_payload`, never as `.error_code` / `.details`. Reading only the
    provider-shaped attributes flattened every such fatal to "unexpected" and
    dropped the location with it, so a phase-contract failure arrived with no
    phase name attached. Prefer the classification the raiser already made; the
    fallback stays for exceptions that never named themselves.
    """
    payload = _engine_error_payload(exc)
    if payload is not None:
        error_code = str(payload["code"])
        details = _safe_provider_error_details(payload.get("details") or {})
        for key in ("phase_id", "field_path", "skill_id", "source_path"):
            value = payload.get(key)
            if value:
                details.setdefault(key, value)
    else:
        error_code = str(getattr(exc, "error_code", "") or "engine.unexpected_error")
        details = _safe_provider_error_details(getattr(exc, "details", {}))
    details.setdefault("exception_type", type(exc).__name__)
    retryable = bool(getattr(exc, "retryable", False))
    return RunArtifactErrorResult(
        error_code=error_code,
        error_payload={
            "error_code": error_code,
            "message": _safe_provider_error_message(exc),
            "details": details,
            "retryable": retryable,
        },
        run_id=run_id,
        retryable=retryable,
    )


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
    metadata: dict[str, Any] = {"artifact_id": request.artifact_ref.artifact_id}
    dev_rebuild = request.execution_context.get("artifact_dev_rebuild")
    if isinstance(dev_rebuild, dict):
        metadata["artifact_dev_rebuild"] = dev_rebuild
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
        return _artifact_error_result(exc, run_id=run_id)

    result_ref = (
        _workflow_result_ref(outputs, runs_root(workspace_dir) if workspace_dir else None)
        if isinstance(outputs, RunResult)
        else None
    )
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
            return _artifact_error_result(exc, run_id=run_id)
        workspace_dir = _resolve_artifact_workspace_dir(request)
        result_ref = _workflow_result_ref(result, predicts_root(workspace_dir) if workspace_dir else None)
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


def _validate_resume_node_selector(value: str | None, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _compiled_phase_names(compiled: Any) -> set[str]:
    names: set[str] = set()
    for node in getattr(compiled, "nodes", []) or []:
        phase_name = getattr(node, "phase_name", None)
        if isinstance(phase_name, str):
            names.add(phase_name)
    return names


def _validate_resume_node_ids(
    compiled: Any,
    from_phase: str | None,
    resume_from_node_id: str | None,
    resume_to_node_id: str | None,
) -> None:
    requested = {
        field_name: value
        for field_name, value in (
            ("from_phase", from_phase),
            ("resume_from_node_id", resume_from_node_id),
            ("resume_to_node_id", resume_to_node_id),
        )
        if value is not None
    }
    if not requested:
        return
    phase_names = _compiled_phase_names(compiled)
    missing = {field_name: value for field_name, value in requested.items() if value not in phase_names}
    if missing:
        rendered = ", ".join(f"{field}={value!r}" for field, value in sorted(missing.items()))
        raise _ResumeInputError(f"Resume node selector does not match compiled graph: {rendered}")


def _validate_resume_checkpoint_targets(
    graph: Any,
    invoke_config: dict[str, Any],
    resume_to_node_id: str | None,
) -> None:
    if resume_to_node_id is None:
        return
    current_state = graph.get_state(invoke_config)
    next_nodes = tuple(str(node) for node in (current_state.next or ()))
    if next_nodes and resume_to_node_id not in next_nodes:
        raise _ResumeInputError(
            f"resume_to_node_id {resume_to_node_id!r} does not match checkpoint next node(s): {next_nodes}"
        )


def _node_output_fields(node: Any) -> set[str]:
    io = getattr(node, "frontmatter", {}).get("io") or {}
    outputs = io.get("outputs") or {}
    properties = outputs.get("properties") or {}
    return {str(field) for field in properties}


def _validate_resume_context_override_scope(
    compiled: Any,
    resume_from_node_id: str | None,
    context_overrides: dict[str, Any] | None,
) -> None:
    if resume_from_node_id is None or not context_overrides:
        return
    phase_order = [name for name in _compiled_phase_names_in_order(compiled)]
    try:
        resume_index = phase_order.index(resume_from_node_id)
    except ValueError:
        return
    producer_by_field: dict[str, str] = {}
    for node in getattr(compiled, "nodes", []) or []:
        phase_name = getattr(node, "phase_name", None)
        if not isinstance(phase_name, str):
            continue
        for field in _node_output_fields(node):
            producer_by_field[field] = phase_name

    dirty_fields: list[str] = []
    for field in context_overrides:
        producer = producer_by_field.get(field)
        if producer is None or producer == resume_from_node_id:
            continue
        if producer in phase_order and phase_order.index(producer) < resume_index:
            dirty_fields.append(field)
    if dirty_fields:
        joined = ", ".join(sorted(dirty_fields))
        raise _ResumeInputError(
            f"context_overrides would dirty upstream checkpoint data before {resume_from_node_id!r}: {joined}"
        )


def _compiled_phase_names_in_order(compiled: Any) -> list[str]:
    names: list[str] = []
    for node in getattr(compiled, "nodes", []) or []:
        phase_name = getattr(node, "phase_name", None)
        if isinstance(phase_name, str):
            names.append(phase_name)
    return names


def _resolve_resume_checkpointer() -> Any:
    active_checkpointer = resolve_checkpointer("auto")
    if active_checkpointer is None or active_checkpointer is True:
        raise RuntimeError("No active checkpointer configured for resume_skill")
    return cast(Any, active_checkpointer)


def _resolve_resume_config(
    active_checkpointer: Any,
    *,
    compiled: Any,
    run_id: str,
    from_phase: str | None,
    checkpoint_ns: str | None,
    checkpoint_id: str | None,
) -> dict[str, Any]:
    ns = checkpoint_ns or ""
    if from_phase and checkpoint_id:
        raise ValueError("from_phase and checkpoint_id are mutually exclusive resume selectors")
    resolved_checkpoint_id = checkpoint_id
    if from_phase:
        resolved_checkpoint_id = checkpoint_id_before_phase(
            active_checkpointer,
            compiled,
            run_id=run_id,
            checkpoint_ns=ns,
            phase_id=from_phase,
        )
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


def _checkpoint_id_from_config(config: dict[str, Any]) -> str:
    return str(config.get("configurable", {}).get("checkpoint_id") or "")


def _checkpoint_ns_from_config(config: dict[str, Any]) -> str:
    return str(config.get("configurable", {}).get("checkpoint_ns") or "")


def _phase_name_from_checkpoint_ns(checkpoint_ns: str) -> str | None:
    for part in reversed([part for part in checkpoint_ns.split(".") if part]):
        if part.startswith("agent:"):
            return part.split(":", 1)[1] or None
    return checkpoint_ns or None


def _checkpoint_config(checkpoint_tuple: Any) -> dict[str, Any]:
    config = getattr(checkpoint_tuple, "config", {}) or {}
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    return configurable if isinstance(configurable, dict) else {}


def _checkpoint_tuple_id(checkpoint_tuple: Any) -> str:
    configurable = _checkpoint_config(checkpoint_tuple)
    checkpoint_id = configurable.get("checkpoint_id")
    if checkpoint_id:
        return str(checkpoint_id)
    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    if isinstance(checkpoint, dict):
        return str(checkpoint.get("id") or "")
    return ""


def _checkpoint_tuple_ns(checkpoint_tuple: Any) -> str:
    return str(_checkpoint_config(checkpoint_tuple).get("checkpoint_ns") or "")


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
    *,
    resume_from_node_id: str | None = None,
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
        as_node = resume_from_node_id or _override_source_node(compiled, set(context_overrides.keys()))

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


def _hitl_tool_call_from_messages(messages: list[Any]) -> dict[str, Any] | None:
    for tool_call in _pending_tool_calls(messages):
        if str(tool_call.get("name") or "") in _HITL_TOOL_NAMES:
            return tool_call
    return None


def _hitl_tool_call_from_pregel_tasks(tasks: Any) -> dict[str, Any] | None:
    if not isinstance(tasks, (list, tuple)):
        return None
    for task in tasks:
        arg = getattr(task, "arg", None)
        # langgraph <=1.2.2 wrapped a single tool call in a dict under
        # "tool_call"; >=1.2.6 carries a list of tool-call dicts directly
        # (Send(node="tools", arg=[{...tool_call...}])).
        if isinstance(arg, dict):
            candidates: list[Any] = [arg.get("tool_call")]
        elif isinstance(arg, (list, tuple)):
            candidates = list(arg)
        else:
            continue
        for tool_call in candidates:
            if isinstance(tool_call, dict) and str(tool_call.get("name") or "") in _HITL_TOOL_NAMES:
                return tool_call
    return None


def _normalise_options(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return []


def _hitl_checkpoint_from_tool_call(
    checkpoint_tuple: Any,
    tool_call: dict[str, Any],
) -> _HitLInterruptCheckpoint | None:
    checkpoint_id = _checkpoint_tuple_id(checkpoint_tuple)
    if not checkpoint_id:
        return None
    checkpoint_ns = _checkpoint_tuple_ns(checkpoint_tuple)
    args = tool_call.get("args")
    args = args if isinstance(args, dict) else {}
    question = args.get("question")
    clarification_type = args.get("clarification_type")
    return _HitLInterruptCheckpoint(
        checkpoint_id=checkpoint_id,
        checkpoint_ns=checkpoint_ns,
        phase_name=_phase_name_from_checkpoint_ns(checkpoint_ns) or "",
        question=str(question) if question is not None else None,
        clarification_type=str(clarification_type) if clarification_type is not None else None,
        options=_normalise_options(args.get("options")),
    )


def _interrupt_payload(value: Any) -> dict[str, Any] | None:
    if not value:
        return None
    candidates = value if isinstance(value, (list, tuple)) else [value]
    if not candidates:
        return None
    raw = getattr(candidates[0], "value", candidates[0])
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return None
    return {"question": str(raw), "clarification_type": "missing_info", "options": []}


def _hitl_checkpoint_from_interrupt_payload(
    checkpoint_tuple: Any,
    payload: dict[str, Any],
) -> _HitLInterruptCheckpoint | None:
    checkpoint_id = _checkpoint_tuple_id(checkpoint_tuple)
    if not checkpoint_id:
        return None
    checkpoint_ns = _checkpoint_tuple_ns(checkpoint_tuple)
    question = payload.get("question")
    clarification_type = payload.get("clarification_type")
    return _HitLInterruptCheckpoint(
        checkpoint_id=checkpoint_id,
        checkpoint_ns=checkpoint_ns,
        phase_name=str(payload.get("phase_name") or _phase_name_from_checkpoint_ns(checkpoint_ns) or ""),
        question=str(question) if question is not None else None,
        clarification_type=str(clarification_type) if clarification_type is not None else None,
        options=_normalise_options(payload.get("options")),
    )


def _checkpoint_values(checkpoint_tuple: Any) -> dict[str, Any]:
    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    if not isinstance(checkpoint, dict):
        return {}
    values = checkpoint.get("channel_values") or {}
    return values if isinstance(values, dict) else {}


def _iter_checkpoints_for_run(active_checkpointer: Any, run_id: str) -> list[Any]:
    list_checkpoints = getattr(active_checkpointer, "list", None)
    if not callable(list_checkpoints):
        return []
    try:
        checkpoints = list(list_checkpoints({"configurable": {"thread_id": run_id}}))
    except Exception:  # noqa: BLE001 - event detection must not crash a run
        logger.warning("[HitL] failed to inspect checkpoints for run_id=%s", run_id, exc_info=True)
        return []
    latest_by_namespace: list[Any] = []
    seen_namespaces: set[str] = set()
    for checkpoint_tuple in checkpoints:
        checkpoint_ns = _checkpoint_tuple_ns(checkpoint_tuple)
        if checkpoint_ns in seen_namespaces:
            continue
        seen_namespaces.add(checkpoint_ns)
        latest_by_namespace.append(checkpoint_tuple)
    return latest_by_namespace


def _find_hitl_interrupt_checkpoint(
    active_checkpointer: Any,
    run_id: str,
    result: Any,
) -> _HitLInterruptCheckpoint | None:
    checkpoints = _iter_checkpoints_for_run(active_checkpointer, run_id)
    result_payload = _interrupt_payload(result.get("__interrupt__") if isinstance(result, dict) else None)
    for checkpoint_tuple in checkpoints:
        values = _checkpoint_values(checkpoint_tuple)
        payload = _interrupt_payload(values.get("__interrupt__")) or result_payload
        if payload is not None:
            hitl = _hitl_checkpoint_from_interrupt_payload(checkpoint_tuple, payload)
            if hitl is not None:
                return hitl

        tool_call = _hitl_tool_call_from_pregel_tasks(values.get("__pregel_tasks"))
        if tool_call is not None:
            hitl = _hitl_checkpoint_from_tool_call(checkpoint_tuple, tool_call)
            if hitl is not None:
                return hitl

        messages = values.get("messages") or []
        if isinstance(messages, list):
            tool_call = _hitl_tool_call_from_messages(messages)
            if tool_call is not None:
                hitl = _hitl_checkpoint_from_tool_call(checkpoint_tuple, tool_call)
                if hitl is not None:
                    return hitl
    return None


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


def _business_context_from_graph_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    data = result.get("data")
    if data is not None and hasattr(data, "model_dump"):
        return cast(dict[str, Any], data.model_dump())
    if isinstance(data, dict):
        return dict(data)
    return {}


def _run_metrics_from_graph_result(result: Any, *, wall_time: float) -> dict[str, Any]:
    """Project the finished graph's own accounting into the run's metrics.

    Both phase runtimes accumulate token spend into ``flow.metrics`` — the
    legacy LLM phase node through ``_HarnessCallbackBridge``, the V4 agent node
    inline. Wall time is the runner's own measurement, so it is layered on top.
    """
    metrics: dict[str, Any] = {}
    flow = result.get("flow") if isinstance(result, dict) else None
    raw = flow.get("metrics") if isinstance(flow, dict) else getattr(flow, "metrics", None)
    if isinstance(raw, dict):
        metrics.update(raw)
    metrics["wall_time_sec"] = wall_time
    return metrics


def _emit_v030_interrupted_run(
    event_sink: Any,
    *,
    run_id: str,
    hitl: _HitLInterruptCheckpoint,
    final_context: dict[str, Any],
    wall_time: float,
) -> None:
    _emit_v030_event(
        event_sink,
        InterruptedEvent(
            phase_name=hitl.phase_name,
            thread_id=run_id,
            checkpoint_id=hitl.checkpoint_id,
            checkpoint_ns=hitl.checkpoint_ns,
            namespace=hitl.checkpoint_ns,
            ns=hitl.checkpoint_ns,
            question=hitl.question,
            clarification_type=hitl.clarification_type,
            options=list(hitl.options or []),
        ),
    )
    _emit_v030_event(
        event_sink,
        RunEndedEvent(
            run_id=run_id,
            thread_id=run_id,
            status="interrupted",
            final_context=_v030_phase_context(final_context),
            wall_time_seconds=wall_time,
        ),
    )


def _finalize_successful_v030_run(
    result: Any,
    *,
    compiled: Any,
    event_sink: Any,
    run_id: str,
    trace_output: Path,
    wall_time: float,
    runtime_config: dict[str, Any] | None,
    persist_declared_outputs: bool = True,
) -> dict[str, Any]:
    final_context = result["data"].model_dump()
    output_context = _context_with_framework_output_sources(final_context, result)
    compiled_raw = getattr(compiled, "raw", {})
    output_schema = (
        compiled_raw.get("io", {}).get("outputs") if isinstance(compiled_raw, dict) else None
    )
    _validate_v030_root_outputs(output_schema, final_context)
    if persist_declared_outputs:
        _save_v030_declared_file_outputs(
            output_schema,
            output_context,
            default_output_dir=trace_output / "artifacts",
        )
        manifest_artifacts = _runtime_artifacts_from_config(runtime_config)
        if manifest_artifacts:
            write_manifest_artifacts(
                manifest_artifacts,
                output_context,
                trace_output / "artifacts",
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


def _validate_v030_root_outputs(output_schema: Any, final_context: dict[str, Any]) -> None:
    if not isinstance(output_schema, dict) or not output_schema:
        return
    try:
        Draft202012Validator.check_schema(output_schema)
    except SchemaError as exc:
        detail = f"root io.outputs schema invalid: {exc.message}"
        raise GraphAgentFatalError(
            detail,
            payload=make_error_payload("[F-v3-runtime-state-mapping-failed]", detail),
        ) from exc
    errors = sorted(Draft202012Validator(output_schema).iter_errors(final_context), key=str)
    if not errors:
        return
    first = errors[0]
    field_path = ".".join(str(part) for part in first.path) or None
    detail = f"root io.outputs validation failed: {first.message}"
    raise GraphAgentFatalError(
        detail,
        payload=make_error_payload(
            "[F-v3-runtime-state-mapping-failed]",
            detail,
            field_path=field_path,
        ),
    )


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
        and schema.get("target") in DECLARED_OUTPUT_TARGETS
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
    run_root: Path,
    thread_id: str | None = None,
    event_subscriber: Callable[[CallbackEvent], None] | None = None,
    callbacks: list[Any] | None = None,
    skill_resolver: SkillResolverProtocol,
    model_resolver: Any | None = None,
    llm_provider: LLMProvider | None = None,
    checkpointer_spec: Any = "auto",
    runtime_config: dict[str, Any] | None = None,
    predict_context: SDKPredictContext | None = None,
    unattended: bool = False,
    persist_declared_outputs: bool = True,
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
    trace_output = run_root / run_id
    root_runtime_inputs = _runtime_root_inputs_from_config(runtime_config, workspace_dir)
    if root_runtime_inputs:
        inputs = {**inputs, **root_runtime_inputs}
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
        compiled = compile_skill(
            skill_root,
            skill_resolver=resolver,
            runtime_input_fields=_runtime_input_fields_from_config(runtime_config),
        )
        assembled = assemble_graph(
            compiled,
            chat_model=chat_model,
            model_resolver=active_model_resolver,
            llm_provider=active_llm_provider,
            callbacks=cast(Any, event_sink),
            skill_resolver=resolver,
            checkpointer=active_checkpointer,
            runtime_config=runtime_config,
            predict_context=predict_context,
        )
        graph = assembled.graph

        # Step 4.2: Build the type-safe initial state using WorkflowState Pydantic models
        initial_state = WorkflowState(
            data=BusinessData.model_validate(dict(inputs)),
            flow=FrameworkState.model_validate({
                "run_id": run_id,
                "thread_id": run_id,
                "unattended": unattended,
                # ``run_dir`` is the storage face for run-scoped observability
                # files (compaction sidecars): the runner is the one caller
                # that knows whether this execution files under ``runs/`` or
                # ``predicts/`` (io/run_layout.py), so the resolved directory
                # travels in state instead of being re-derived downstream.
                "persistent_storage_config": {
                    "workspace_dir": str(workspace_dir),
                    "run_dir": str(trace_output),
                },
            }),
            messages=[],
        )

        # Step 4.3: Invoke the LangGraph compiled StateGraph natively passing the thread_id
        result = graph.invoke(
            initial_state,
            config={"configurable": {"thread_id": run_id}},
        )
        hitl_interrupt = _find_hitl_interrupt_checkpoint(active_checkpointer, run_id, result)
        if hitl_interrupt is not None:
            wall_time = round(time.time() - t0, 3)
            final_context = _business_context_from_graph_result(result)
            _emit_v030_interrupted_run(
                event_sink,
                run_id=run_id,
                hitl=hitl_interrupt,
                final_context=final_context,
                wall_time=wall_time,
            )
            saved_trace_path = str(event_sink.trace_path) if event_sink.trace_path is not None else None
            return {
                "run_id": run_id,
                "context": final_context,
                "metrics": _run_metrics_from_graph_result(result, wall_time=wall_time),
                "trace_path": saved_trace_path,
                "run_dir": str(trace_output),
                "wall_time_sec": wall_time,
            }
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
        runtime_config=runtime_config,
        persist_declared_outputs=persist_declared_outputs,
    )
    saved_trace_path = str(event_sink.trace_path) if event_sink.trace_path is not None else None
    return {
        "run_id": run_id,
        "context": final_context,
        "metrics": _run_metrics_from_graph_result(result, wall_time=wall_time),
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
