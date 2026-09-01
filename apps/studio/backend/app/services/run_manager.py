"""Run process management and WebSocket event streaming."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import multiprocessing
import os
import re
import shutil
import tempfile
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty
from typing import Any, ClassVar, Literal

from pydantic import TypeAdapter

from app.core import config
from app.core.adapters.atomic_file import read_published_text, write_text_atomically
from app.core.adapters.engine import (
    CallbackEvent,
    DeltaEnvelope,
    EventEnvelope,
    NodeRunResult,
    RunResultSnapshot,
    RunResultsRef,
    StreamCursorExpiredError,
    StreamCursorGapError,
    TransportErrorPayload,
    make_event_envelope,
)
from app.core.adapters.run_layout import predicts_root, runs_root
from app.core.adapters.transport_factory import build_engine_adapter
from app.core.authored_text import read_authored_text
from app.core.backends import get_metadata, get_storage
from app.core.exceptions import error_response, raise_error_response, standard_http_exception
from app.core.path_containment import (
    PathEscapesDirectory,
    WorkspaceEntryName,
    resolve_inside,
)
from app.core.ports.metadata import MetadataStore
from app.core.ports.storage import StorageBackend
from app.models.runs import (
    CONCLUDED_RUN_STATUSES,
    BatchRunItem,
    BatchRunResponse,
    BatchRunStatus,
    CompareCandidateRun,
    CompareRunGroupResponse,
    CompareRunResponse,
    ResumeReport,
    ResumeReq,
    RunDetail,
    RunError,
    RunListResponse,
    RunMetadata,
    RunPausePoint,
    RunRequest,
    TokensMetrics,
)
from app.services.breakpoints import breakpoints_from_runtime_config
from app.services.gate_events import GateOutcome, publish_skill_gate
from app.services.git_local import GitCommandError, GitFileLockedError, GitLocalService
from app.services.predict_gate import require_passing_predict
from app.services.run_ids import is_predict_run_id, new_run_id
from app.services.run_liveness import hold_run_liveness, run_worker_is_alive
from app.services.run_report import write_run_report
from app.services.runtime_config import refresh_runtime_config, write_runtime_snapshot
from app.services.skill_resolver import build_studio_skill_resolver as build_studio_skill_resolver
from app.services.skills import (
    opened_skill_dir,
    predicts_dir_for,
    resolve_skill_dir,
    run_dir_for,
    run_root_for,
    runs_dir_for,
    test_inputs_dir_for_skill,
)

_EVENT_ADAPTER: TypeAdapter[Any] = TypeAdapter(CallbackEvent)
logger = logging.getLogger(__name__)
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SAFE_SKILL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass
class RunRecord:
    """In-memory handle for a spawned run."""

    metadata: RunMetadata
    skill_id: str
    run_dir: Path
    process: Any
    process_queue: Any
    ws_queue: asyncio.Queue[dict[str, Any] | None] = field(default_factory=asyncio.Queue)
    events: list[EventEnvelope] = field(default_factory=list)
    delta_watchers: list[_DeltaStream] = field(default_factory=list)
    subscribers: list[asyncio.Queue[dict[str, Any] | None]] = field(default_factory=list)
    drain_task: asyncio.Task[None] | None = None


@dataclass
class BatchRecord:
    """In-memory metadata for one batch run request."""

    batch_id: str
    skill_id: str
    items: list[tuple[str, str]]


class _DeltaStream:
    """One watcher's view of a run's delta frames — bounded, and lossy on purpose.

    Deltas are allowed to be merged or dropped, and that permission is the only
    reason this queue can have a ceiling: a watcher that stops reading costs a
    fixed amount of memory instead of growing with the run. What it must never
    do is make the run wait — the engine emits deltas from the phase's own
    thread, and a producer blocked on a slow browser tab is a run blocked on a
    slow browser tab.

    Merging happens against the tail of what is still waiting, so the "time
    window" the decision calls for is the backlog itself rather than a timer
    somebody has to tune: a watcher keeping up sees every piece as it was sent,
    and only a watcher falling behind gets them coalesced.
    """

    MAX_PENDING = 256

    def __init__(self) -> None:
        self._pending: deque[DeltaEnvelope] = deque()
        self._wake = asyncio.Event()
        self._closed = False
        self.dropped = 0

    @property
    def pending(self) -> list[DeltaEnvelope]:
        return list(self._pending)

    def offer(self, frame: DeltaEnvelope) -> None:
        tail = self._pending[-1] if self._pending else None
        if (
            tail is not None
            and not tail.restarts_step
            and not frame.restarts_step
            and tail.step_id == frame.step_id
            and tail.channel == frame.channel
        ):
            self._pending[-1] = tail.model_copy(
                update={"text": tail.text + frame.text, "timestamp": frame.timestamp}
            )
        else:
            self._pending.append(frame)
        while len(self._pending) > self.MAX_PENDING:
            # The oldest go first: a live view is showing text as it arrives, so
            # what a backed-up watcher needs is the newest, not the stalest.
            self._pending.popleft()
            self.dropped += 1
        self._wake.set()

    def close(self) -> None:
        self._closed = True
        self._wake.set()

    async def __aiter__(self) -> AsyncIterator[DeltaEnvelope]:
        while True:
            while self._pending:
                yield self._pending.popleft()
            if self._closed:
                return
            self._wake.clear()
            if self._pending or self._closed:
                continue
            await self._wake.wait()


def _queue_event_subscriber(process_queue: Any) -> Any:
    def _emit(event: CallbackEvent) -> None:
        # Two roads, sorted here because here is where the frame still knows
        # which it belongs on. Numbered frames go in the replay buffer and get a
        # sequence number; deltas may be merged or dropped, and a droppable
        # frame holding a sequence number turns every permitted drop into a hole
        # a reconnecting reader reports as data loss.
        kind = "event" if getattr(type(event), "persisted", True) else "delta"
        process_queue.put({"type": kind, "event": event.model_dump(mode="json")})

    return _emit


def _run_worker_main(
    skill_id: str,
    run_dir_raw: str,
    inputs: dict[str, Any],
    process_queue: Any,
    art_ref: dict[str, Any],
    roles_path_override: str | None = None,
    runtime_config: dict[str, Any] | None = None,
) -> None:
    """Subprocess entrypoint: claim the run, then execute it.

    The claim is an OS lock on the run's own directory, held for exactly as long
    as this process lives. It is what lets a LATER sidecar answer "is this run
    still going?" instead of trusting a record its own writer may not have
    survived to correct (see ``run_liveness``). Wrapping rather than inlining
    keeps the two jobs apart: this function owns the claim, the one below owns
    the run.
    """
    run_dir = Path(run_dir_raw)
    with hold_run_liveness(run_dir):
        _execute_run_in_worker(
            skill_id,
            run_dir_raw,
            inputs,
            process_queue,
            art_ref,
            roles_path_override,
            runtime_config,
        )


def _execute_run_in_worker(
    skill_id: str,
    run_dir_raw: str,
    inputs: dict[str, Any],
    process_queue: Any,
    art_ref: dict[str, Any],
    roles_path_override: str | None = None,
    runtime_config: dict[str, Any] | None = None,
) -> None:
    """Executes EngineAdapter.run_artifact.

    ``roles_path_override`` (n4-trace#23): a model-compare candidate worker is
    handed its own materialized ``llm_roles.yaml`` here; setting the env var in
    THIS child process makes the in-process engine resolver load the candidate's
    roles without touching the parent's active roles or the engine.
    """
    run_dir = Path(run_dir_raw)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(exist_ok=True)
    started = time.monotonic()
    emit_to_queue = _queue_event_subscriber(process_queue)
    if roles_path_override:
        os.environ["STUDIO_LLM_ROLES_PATH"] = roles_path_override
    os.environ["STUDIO_RUNTIME_CONFIG_PATH"] = str(run_dir / "runtime_config.snapshot.json")
    try:
        adapter = build_engine_adapter()
        run_payload = {
            "artifact_ref": art_ref,
            # P0#2 (handshake audit §5.2): pass the .workspace ROOT, not run_dir.parent
            # (=.workspace/runs). Engine writes <workspace_dir>/runs/<thread_id>; passing the
            # runs dir made it land in .workspace/runs/runs/<id> while Studio read .workspace/runs/<id>.
            "workspace_dir": str(run_dir.parent.parent),
            "thread_id": run_dir.name,
            "idempotency_key": run_dir.name,
            "inputs": inputs,
        }
        if runtime_config is not None:
            run_payload["execution_context"] = {
                "runtime_config": runtime_config,
                # The engine is told "stop before these phases" in its own
                # words; it never reads the workspace file (RUN_EXECUTION-16).
                "pause_before": breakpoints_from_runtime_config(runtime_config),
            }
        if adapter.transport == "in_process":
            run_payload["event_subscriber"] = emit_to_queue
        result = adapter.run_artifact(run_payload)
        metrics = _result_metrics(result)
        metrics.setdefault("wall_time_sec", _result_wall_time(result, started))
        final_context = _result_context(result)
        pause_point = _result_pause_point(result)
        # P0#3 (handshake audit §5.3): never report fake success — honor RunResult.success.
        if pause_point is not None:
            # A run that stopped produced neither an outcome nor a failure, so it
            # is persisted as itself: what it got so far, and where it stopped.
            metrics_payload = {"status": "paused", **metrics}
            _persist_run_artifacts(
                skill_id,
                run_dir,
                input_data=inputs,
                final_context=final_context,
                metrics=metrics_payload,
                status="paused",
                artifact_ref=art_ref,
                result=result,
            )
            process_queue.put(
                {
                    "type": "status",
                    "status": "paused",
                    "metrics": metrics,
                    "paused_at": pause_point.model_dump(mode="json"),
                },
            )
        elif _result_success(result):
            metrics_payload = {"status": "success", **metrics}
            _persist_run_artifacts(
                skill_id,
                run_dir,
                input_data=inputs,
                final_context=final_context,
                metrics=metrics_payload,
                status="success",
                result=result,
                artifact_ref=art_ref,
            )
            process_queue.put({"type": "status", "status": "success", "metrics": metrics})
        else:
            run_error = _run_error(_result_error(result))
            metrics_payload = {"status": "failed", "error": run_error, **metrics}
            _persist_run_artifacts(
                skill_id,
                run_dir,
                input_data=inputs,
                final_context=final_context,
                metrics=metrics_payload,
                status="failed",
                result=result,
                artifact_ref=art_ref,
            )
            process_queue.put(
                {
                    "type": "status",
                    "status": "failed",
                    "metrics": metrics,
                    "error": run_error,
                },
            )
    except Exception as exc:  # noqa: BLE001
        metrics = {"wall_time_sec": round(time.monotonic() - started, 3)}
        run_error = _run_error(str(exc))
        metrics_payload = {"status": "failed", "error": run_error, **metrics}
        _persist_run_artifacts(
            skill_id,
            run_dir,
            input_data=inputs,
            final_context={},
            metrics=metrics_payload,
            status="failed",
            result={
                "success": False,
                "context": {},
                "error": str(exc),
            },
            artifact_ref=art_ref,
        )
        process_queue.put(
            {
                "type": "status",
                "status": "failed",
                "metrics": metrics,
                "error": run_error,
            },
        )


def _write_json(path: Path, payload: Any) -> None:
    # codeql[py/path-injection] callers pass run_dir_for-derived paths or worker run dirs created from those paths.
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _result_context(result: Any) -> dict[str, Any]:
    error_result = _artifact_error_result_payload(result)
    if error_result is not None:
        return error_result
    if isinstance(result, dict):
        context = result.get("context", {})
    else:
        context = getattr(result, "context", {})
    return context if isinstance(context, dict) else {}


def _result_metrics(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        metrics = result.get("metrics", {})
    else:
        metrics = getattr(result, "metrics", {})
    if hasattr(metrics, "model_dump"):
        return dict(metrics.model_dump(mode="json"))
    return dict(metrics) if isinstance(metrics, dict) else {}


def _result_wall_time(result: Any, started: float) -> float:
    if isinstance(result, dict):
        value = result.get("wall_time_sec")
    else:
        value = getattr(result, "wall_time_sec", None)
    if isinstance(value, int | float):
        return float(value)
    return round(time.monotonic() - started, 3)


def _result_pause_point(result: Any) -> RunPausePoint | None:
    """Where the engine stopped, when it stopped instead of finishing.

    Asked BEFORE ``_result_success``, and that order is the whole point: the
    engine's interrupted path returns a plain dict with no ``success`` key, and
    an absent answer counts as yes down there. Every run that stopped to ask a
    human was therefore filed as a finished one — the breakpoint work only made
    a second way to reach a bug that was already there.
    """
    if _artifact_error_result_payload(result) is not None:
        return None
    if isinstance(result, dict):
        paused_at = result.get("paused_at")
    else:
        paused_at = getattr(result, "paused_at", None)
    if paused_at is None:
        return None
    if hasattr(paused_at, "model_dump"):
        paused_at = paused_at.model_dump(mode="json")
    if not isinstance(paused_at, dict):
        return None
    # The engine says "phase"; the canvas says "node"; they are the same name.
    return RunPausePoint(node_id=str(paused_at["phase_name"]), reason=paused_at["reason"])


def _result_success(result: Any) -> bool:
    """Whether the engine RunResult reports success. Absent → treat as success."""
    if _artifact_error_result_payload(result) is not None:
        return False
    if isinstance(result, dict):
        value = result.get("success")
    else:
        value = getattr(result, "success", None)
    return True if value is None else bool(value)


def _result_error(result: Any) -> Any:
    """Extract the engine RunResult error payload (ErrorPayload model → json) for the failed-status report."""
    error_result = _artifact_error_result_payload(result)
    if error_result is not None:
        return error_result
    if isinstance(result, dict):
        error = result.get("error")
    else:
        error = getattr(result, "error", None)
    if error is None:
        return None
    if hasattr(error, "model_dump"):
        return error.model_dump(mode="json")
    return error


def _run_error(raw: Any) -> dict[str, Any] | None:
    """Normalize whatever the failure came wrapped in into one RunError shape.

    Three producers reach here: the engine's ``ErrorPayload`` (``code``/``message``),
    the artifact-run error envelope (``error_code`` + nested ``error_payload``), and
    a bare exception string from the worker's own guard. Readers must not have to
    tell them apart.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        return {"code": "run.failed", "message": raw, "details": {}}
    if not isinstance(raw, dict):
        return {"code": "run.failed", "message": str(raw), "details": {}}

    payload = raw.get("error_payload")
    if isinstance(payload, dict):
        details = payload.get("details")
        return {
            "code": str(raw.get("error_code") or payload.get("error_code") or "run.failed"),
            "message": str(payload.get("message") or raw.get("error_code") or "run failed"),
            "details": dict(details) if isinstance(details, dict) else {},
        }

    details = raw.get("details")
    code = raw.get("code") or raw.get("error_code")
    message = raw.get("message")
    return {
        "code": str(code or "run.failed"),
        "message": str(message or code or "run failed"),
        "details": dict(details) if isinstance(details, dict) else {},
    }


def _artifact_error_result_payload(result: Any) -> dict[str, Any] | None:
    if isinstance(result, dict):
        error_code = result.get("error_code")
        error_payload = result.get("error_payload")
        run_id = result.get("run_id")
        retryable = result.get("retryable", False)
    else:
        error_code = getattr(result, "error_code", None)
        error_payload = getattr(result, "error_payload", None)
        run_id = getattr(result, "run_id", None)
        retryable = getattr(result, "retryable", False)
    if not isinstance(error_code, str) or not isinstance(error_payload, dict):
        return None
    payload: dict[str, Any] = {
        "error_code": error_code,
        "error_payload": error_payload,
        "run_id": run_id if isinstance(run_id, str) else None,
        "retryable": bool(retryable),
    }
    return payload


def _ensure_run_files(run_dir: Path) -> None:
    (run_dir / "artifacts").mkdir(exist_ok=True)
    (run_dir / "trace.jsonl").touch(exist_ok=True)
    (run_dir / "checkpoints.db").touch(exist_ok=True)


_ARTIFACT_IDENTITY_KEYS = (
    "artifact_id",
    "content_hash",
    "store",
    "version",
    "manifest_ref",
    "source_map_ref",
    "execution_fingerprint",
)


def _public_artifact_ref(artifact_ref: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(artifact_ref, dict):
        return None
    public = {key: artifact_ref[key] for key in _ARTIFACT_IDENTITY_KEYS if key in artifact_ref}
    return public or None


def _metadata_artifact_fields(artifact_ref: dict[str, Any] | None) -> dict[str, Any]:
    public = _public_artifact_ref(artifact_ref)
    if public is None:
        return {}
    fields: dict[str, Any] = {"artifact_ref": public}
    source_map_ref = public.get("source_map_ref")
    if isinstance(source_map_ref, str):
        fields["source_map_ref"] = source_map_ref
    execution_fingerprint = public.get("execution_fingerprint")
    if isinstance(execution_fingerprint, str):
        fields["execution_fingerprint"] = execution_fingerprint
    return fields


def _artifact_store_metadata(source: str, artifact_ref: dict[str, Any] | None) -> dict[str, Any]:
    metadata: dict[str, Any] = {"source": source}
    public = _public_artifact_ref(artifact_ref)
    if public is None:
        return metadata
    metadata["artifact_ref"] = public
    for key, value in public.items():
        metadata[key] = value
    return metadata


def _persist_run_artifacts(
    skill_id: str,
    run_dir: Path,
    *,
    input_data: dict[str, Any] | None = None,
    final_context: dict[str, Any],
    metrics: dict[str, Any],
    status: str,
    result: Any,
    artifact_ref: dict[str, Any] | None = None,
) -> None:
    """File what a run produced under the verdict its caller reached.

    The verdict is passed in rather than re-derived: the caller has already
    decided it, and a second derivation here is a second place that has to learn
    about every way a run can end — which is how ``paused`` would have silently
    filed itself as ``success``.
    """
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    store.begin_run(run_dir.name, metadata=_artifact_store_metadata("run_manager", artifact_ref))
    trace_ref = f"{skill_id}/runs/{run_dir.name}/trace.jsonl"
    node_outputs = _result_node_outputs(result, final_context)
    object_payloads: dict[str, bytes] = {
        "final_state.json": json.dumps(final_context, ensure_ascii=False, default=str).encode("utf-8"),
        "metrics.json": json.dumps(metrics, ensure_ascii=False, default=str).encode("utf-8"),
        "trace.jsonl": (run_dir / "trace.jsonl").read_bytes() if (run_dir / "trace.jsonl").exists() else b"",
    }
    if input_data is not None:
        object_payloads["input_data.json"] = json.dumps(input_data, ensure_ascii=False, default=str).encode("utf-8")
    node_results: list[NodeRunResult] = []
    for node_id, output in node_outputs.items():
        output_path = f"nodes/{node_id}/outputs.json"
        output_ref = f"{skill_id}/runs/{run_dir.name}/{output_path}"
        object_payloads[output_path] = json.dumps(output, ensure_ascii=False, default=str).encode("utf-8")
        node_results.append(
            NodeRunResult(
                agent_node_id=node_id,
                status=status,
                outputs_ref=output_ref,
                trace_refs=[trace_ref],
            )
        )
    snapshot = RunResultSnapshot(
        run_results_ref=RunResultsRef(
            run_id=run_dir.name,
            uri=f"{skill_id}/runs/{run_dir.name}/result.json",
            content_hash=_run_result_snapshot_content_hash(
                status=status,
                final_context=final_context,
                node_outputs=node_outputs,
            ),
        ),
        node_results=node_results,
        status=status,
        outputs_ref=f"{skill_id}/runs/{run_dir.name}/final_state.json",
        trace_refs=[trace_ref],
    )
    object_payloads["result.json"] = snapshot.model_dump_json().encode("utf-8")
    store.put_batch(
        run_dir.name,
        object_payloads,
    )


def _seal_run_artifacts(run_dir: Path) -> None:
    """Close this run's artifact record: commit what is on disk, then seal.

    Sealing declares that no further object will be added to the run, and the
    PARENT is the only party that can ever declare it truthfully. The worker can
    only speak for the graceful ending; a worker killed from outside runs no code
    at all, so a seal left to it never happens — and every read of that run then
    answers `artifact.run_not_sealed`, however completely the run is otherwise
    finished (problem ledger P1). Predict already learned the same lesson from
    the other side: anything outside the seal is unreachable however plainly it
    sits in the directory (`predictor.py`).

    `trace.jsonl` is streamed into the run dir as the run goes and only committed
    at the end, so a run that died mid-phase has events on disk that never
    reached the store. They are committed here rather than sealed over, because a
    detail that reports "nothing happened" about a run whose trace file is right
    there is the same defect wearing different clothes.
    """
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    if store.is_sealed(run_dir.name):
        return
    # A run that produced nothing at all still gets a manifest, so "sealed" means
    # readable without exception: readers reach a run THROUGH its manifest, and a
    # sealed run without one answers not-found to every question about itself.
    store.begin_run(run_dir.name)
    trace_file = run_dir / "trace.jsonl"
    if trace_file.exists():
        store.put_batch(run_dir.name, {"trace.jsonl": trace_file.read_bytes()})
    store.seal_run(run_dir.name)


def _result_node_outputs(result: Any, final_context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = _phase_record_outputs(result)
    if nodes:
        return nodes

    phase_outputs = final_context.get("phase_outputs")
    if isinstance(phase_outputs, dict):
        nodes = {
            str(node_id): _node_output_payload(output)
            for node_id, output in phase_outputs.items()
            if str(node_id)
        }
        if nodes:
            return nodes

    return {"final": dict(final_context)}


def _phase_record_outputs(result: Any) -> dict[str, dict[str, Any]]:
    phases = result.get("phases") if isinstance(result, dict) else getattr(result, "phases", None)
    if not isinstance(phases, list):
        return {}
    nodes: dict[str, dict[str, Any]] = {}
    for phase in phases:
        if isinstance(phase, dict):
            phase_name = phase.get("phase_name")
            outputs = phase.get("outputs")
        else:
            phase_name = getattr(phase, "phase_name", None)
            outputs = getattr(phase, "outputs", None)
        if not isinstance(phase_name, str) or not phase_name:
            continue
        nodes[phase_name] = _node_output_payload(outputs)
    return nodes


def _node_output_payload(output: Any) -> dict[str, Any]:
    if hasattr(output, "model_dump"):
        output = output.model_dump(mode="json")
    if isinstance(output, dict):
        return dict(output)
    return {"value": output}


def _run_result_snapshot_content_hash(
    *,
    status: str,
    final_context: dict[str, Any],
    node_outputs: dict[str, dict[str, Any]],
) -> str:
    import hashlib

    payload = json.dumps(
        {
            "status": status,
            "final_context": final_context,
            "node_outputs": node_outputs,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


class RunManager:
    """Owns active run processes and their event queues."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._batches: dict[str, BatchRecord] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self.process_factory: Any = multiprocessing.Process
        self.queue_factory: Any = multiprocessing.Queue
        self.worker: Any = _run_worker_main
        self.git_service: GitLocalService = GitLocalService()

    @staticmethod
    def _release_run_process(process: Any, process_queue: Any) -> None:
        """Stop a run's child process and release its OS resources.

        A real ``multiprocessing.Process`` child and its ``multiprocessing.Queue`` feeder
        thread must be explicitly terminated + closed — merely dropping the references
        orphans them, and the leaked feeder threads / zombie children then SIGSEGV during
        interpreter or coverage teardown (the flaky ``exit 139`` after "N passed"). Every
        step is guarded so mock factories (``InlineProcess`` / ``queue.Queue``) used in
        tests are harmless no-ops.
        """
        with contextlib.suppress(Exception):
            if hasattr(process, "is_alive") and process.is_alive():
                process.terminate()
        with contextlib.suppress(Exception):
            if hasattr(process, "join"):
                process.join(timeout=2)
        with contextlib.suppress(Exception):
            # terminate() is SIGTERM — a busy or blocked child can ignore it.
            # Escalate to kill() (SIGKILL) rather than orphaning the child into
            # interpreter shutdown (the same exit-139 class).
            if (
                hasattr(process, "kill")
                and hasattr(process, "is_alive")
                and process.is_alive()
            ):
                process.kill()
                if hasattr(process, "join"):
                    process.join(timeout=2)
        with contextlib.suppress(Exception):
            if hasattr(process_queue, "close"):
                process_queue.close()
        with contextlib.suppress(Exception):
            if hasattr(process_queue, "join_thread"):
                process_queue.join_thread()

    def reset_for_tests(self) -> None:
        """Synchronously stop every in-memory run and release its OS resources.

        The test fixture used to just clear ``_runs``, which orphaned real child
        processes and their Queue feeder threads (flaky SIGSEGV on teardown). Stop them
        properly instead.
        """
        for record in list(self._runs.values()):
            self._release_run_process(record.process, record.process_queue)
        self._runs.clear()
        self._batches.clear()
        self._tasks.clear()

    async def start_run(self, skill_id: str, request: RunRequest) -> RunMetadata:
        skill_dir = resolve_skill_dir(skill_id)
        runtime_config = refresh_runtime_config(skill_dir)

        adapter = build_engine_adapter()
        art_ref = adapter.compile(
            {
                "skill_dir": str(skill_dir),
                "skill_id": skill_id,
                "artifact_scope": "ephemeral",
                "runtime_config": runtime_config,
            }
        )

        # MVP1 run-and-verify gate: Run requires a passing Predict for *this* graph
        # state (server-side prerequisite, not UI-only). The gate matches the recorded
        # predict-pass content_hash against the freshly-compiled hash, so editing the
        # graph after a pass forces a re-predict. Raises RUN_REQUIRES_PREDICT (409)
        # when no matching passing predict is on record.
        require_passing_predict(skill_id, content_hash=art_ref["content_hash"])

        inputs = dict(request.input_data or {})
        run_id = new_run_id()
        run_dir = run_dir_for(skill_id, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "artifacts").mkdir(exist_ok=True)
        write_runtime_snapshot(run_dir, runtime_config)
        _write_json(run_dir / "input_data.json", inputs)
        _persist_run_input_artifact(run_dir, inputs, artifact_ref=art_ref)
        metadata = RunMetadata(
            run_id=run_id,
            status="running",
            started_at=datetime.now(UTC),
            input_summary=_input_summary(inputs),
            # The ordinary run, and the only kind that archives the skill when
            # it succeeds. Every other spawn leaves this at its default.
            auto_commit=True,
            **_metadata_artifact_fields(art_ref),
        )
        _write_run_metadata(run_dir, metadata)
        await self._save_run_metadata(skill_id, metadata)

        # 状态对等(决议 2026-08-03 D2/D3):run 一起动就广播,前端据此把 runId
        # 指过去并切到 Trace——不再只认自己按下的那个 Run 按钮。
        await publish_skill_gate(
            skill_id=skill_id,
            gate="run",
            outcome="started",
            content_hash=str(art_ref.get("content_hash") or "") or None,
            run_id=run_id,
        )

        process_queue = self.queue_factory()
        process = self.process_factory(
            target=self.worker,
            args=(skill_id, str(run_dir), inputs, process_queue, art_ref, None, runtime_config),
        )
        try:
            process.start()
        except Exception as exc:
            response = error_response(
                error_code="RUN_SPAWN_FAILED",
                http_status=500,
                message=f"Failed to spawn run for skill {skill_id}: {exc}",
                details={"skill_id": skill_id},
                retry_strategy="idempotent",
            )
            raise_error_response(response)

        record = RunRecord(
            metadata=metadata,
            skill_id=skill_id,
            run_dir=run_dir,
            process=process,
            process_queue=process_queue,
        )
        self._runs[run_id] = record
        task = asyncio.create_task(self._drain_process_queue(record))
        record.drain_task = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return metadata

    async def start_node_compare_run(
        self,
        skill_id: str,
        base_run_id: str,
        node_id: str,
    ) -> CompareRunResponse:
        """Launch isolated single-node side-runs for a node's compare candidates (PR2).

        For each persisted candidate of ``node_id``: feed the node the exact input
        the base run gave it (from the base run's ``input_dispatch`` event), run a
        materialized single-node skill variant with the candidate model swapped in,
        and tag the side-run with a shared compare_group_id. The side-run is a
        physically separate run, so it never writes the base run's blackboard and
        gets its own artifacts directory. The engine is untouched.
        """
        from app.services.compare_candidates import read_compare_candidates
        from app.services.model_compare import (
            extract_node_input,
            materialize_single_node_skill,
            new_compare_group_id,
            write_candidate_roles_file,
        )

        skill_dir = resolve_skill_dir(skill_id)
        runtime_config = refresh_runtime_config(skill_dir)
        candidates = read_compare_candidates(skill_dir).get(node_id, [])
        if not candidates:
            response = error_response(
                error_code="COMPARE_REQUIRES_CANDIDATES",
                http_status=422,
                message=f"node {node_id!r} has no compare candidates",
                details={"skill_id": skill_id, "node_id": node_id},
                retry_strategy="not_retryable",
            )
            raise_error_response(response)

        base_run_dir = run_dir_for(skill_id, base_run_id)
        node_input = extract_node_input(_read_run_artifact_events(base_run_dir), node_id)

        compare_group_id = new_compare_group_id()
        # Scratch (single-node variants + candidate roles) lives OUTSIDE the skill
        # tree: the variant is a copy of the skill, so materializing under the
        # skill's own .workspace would recurse. The compiled art_ref is
        # self-contained after compile, so the scratch is disposable post-spawn.
        group_dir = Path(tempfile.mkdtemp(prefix=f"cmp_{compare_group_id}_"))
        logger.info(
            "start_node_compare_run skill=%s base=%s node=%s group=%s candidates=%d",
            skill_id,
            base_run_id,
            node_id,
            compare_group_id,
            len(candidates),
        )

        adapter = build_engine_adapter()
        spawned: list[CompareCandidateRun] = []
        for candidate in candidates:
            variant_dir = group_dir / f"variant_{candidate.candidate_id}"
            materialize_single_node_skill(skill_dir, node_id, variant_dir)
            variant_art_ref = adapter.compile(
                {
                    "skill_dir": str(variant_dir),
                    "skill_id": skill_id,
                    "artifact_scope": "ephemeral",
                }
            )
            roles_file = write_candidate_roles_file(skill_dir, node_id, candidate, group_dir)
            metadata = await self._spawn_side_run(
                skill_id=skill_id,
                inputs=node_input,
                art_ref=variant_art_ref,
                compare_group_id=compare_group_id,
                compare_node_id=node_id,
                candidate_id=candidate.candidate_id,
                candidate_label=candidate.model_group_id,
                base_run_id=base_run_id,
                roles_path_override=str(roles_file),
                runtime_config=runtime_config,
            )
            spawned.append(
                CompareCandidateRun(
                    candidate_id=candidate.candidate_id,
                    label=candidate.model_group_id,
                    metadata=metadata,
                )
            )
        return CompareRunResponse(
            compare_group_id=compare_group_id,
            node_id=node_id,
            base_run_id=base_run_id,
            runs=spawned,
        )

    async def _spawn_side_run(
        self,
        *,
        skill_id: str,
        inputs: dict[str, Any],
        art_ref: dict[str, Any],
        compare_group_id: str,
        compare_node_id: str,
        candidate_id: str,
        candidate_label: str,
        base_run_id: str,
        roles_path_override: str,
        runtime_config: dict[str, Any] | None,
    ) -> RunMetadata:
        """Spawn one isolated single-node candidate side-run tagged with its group."""
        run_id = new_run_id()
        run_dir = run_dir_for(skill_id, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "artifacts").mkdir(exist_ok=True)
        if runtime_config is not None:
            write_runtime_snapshot(run_dir, runtime_config)
        _write_json(run_dir / "input_data.json", inputs)
        _persist_run_input_artifact(run_dir, inputs, artifact_ref=art_ref)
        metadata = RunMetadata(
            run_id=run_id,
            status="running",
            started_at=datetime.now(UTC),
            input_summary=_input_summary(inputs),
            compare_group_id=compare_group_id,
            compare_node_id=compare_node_id,
            candidate_id=candidate_id,
            candidate_label=candidate_label,
            compare_base_run_id=base_run_id,
            **_metadata_artifact_fields(art_ref),
        )
        _write_run_metadata(run_dir, metadata)
        await self._save_run_metadata(skill_id, metadata)

        process_queue = self.queue_factory()
        process = self.process_factory(
            target=self.worker,
            args=(skill_id, str(run_dir), inputs, process_queue, art_ref, roles_path_override, runtime_config),
        )
        try:
            process.start()
        except Exception as exc:
            response = error_response(
                error_code="RUN_SPAWN_FAILED",
                http_status=500,
                message=f"Failed to spawn compare side-run for skill {skill_id}: {exc}",
                details={"skill_id": skill_id, "candidate_id": candidate_id},
                retry_strategy="idempotent",
            )
            raise_error_response(response)

        record = RunRecord(
            metadata=metadata,
            skill_id=skill_id,
            run_dir=run_dir,
            process=process,
            process_queue=process_queue,
        )
        self._runs[run_id] = record
        task = asyncio.create_task(self._drain_process_queue(record))
        record.drain_task = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return metadata

    def list_compare_group(self, skill_id: str, compare_group_id: str) -> CompareRunGroupResponse:
        """Return the per-candidate side-runs of one compare group, for Trace tabs.

        Reads persisted run metadata (same store ``list_runs`` reads) and filters
        to the requested compare group, surfacing each candidate's current status
        (including a failed candidate) so the frontend can render one tab per
        candidate with its result/failure state.
        """
        listing = self.list_runs(skill_id)
        runs: list[CompareCandidateRun] = []
        for metadata in listing.runs:
            if metadata.compare_group_id != compare_group_id:
                continue
            runs.append(
                CompareCandidateRun(
                    candidate_id=metadata.candidate_id or "",
                    label=metadata.candidate_label or "",
                    metadata=metadata,
                )
            )
        runs.sort(key=lambda item: item.candidate_id)
        return CompareRunGroupResponse(compare_group_id=compare_group_id, runs=runs)

    async def start_run_from_artifact(
        self,
        skill_id: str,
        request: RunRequest,
        *,
        artifact_ref: dict[str, Any],
    ) -> RunMetadata:
        inputs = dict(request.input_data or {})
        runtime_config: dict[str, Any] | None = None
        with contextlib.suppress(Exception):
            runtime_config = refresh_runtime_config(resolve_skill_dir(skill_id))
        run_id = new_run_id()
        run_dir = _source_less_run_dir_for(skill_id, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "artifacts").mkdir(exist_ok=True)
        if runtime_config is not None:
            write_runtime_snapshot(run_dir, runtime_config)
        _write_json(run_dir / "input_data.json", inputs)
        _persist_run_input_artifact(run_dir, inputs, artifact_ref=artifact_ref)
        metadata = RunMetadata(
            run_id=run_id,
            status="running",
            started_at=datetime.now(UTC),
            input_summary=_input_summary(inputs),
            **_metadata_artifact_fields(artifact_ref),
        )
        _write_run_metadata(run_dir, metadata)
        await self._save_run_metadata(skill_id, metadata)

        process_queue = self.queue_factory()
        process = self.process_factory(
            target=self.worker,
            args=(skill_id, str(run_dir), inputs, process_queue, artifact_ref, None, runtime_config),
        )
        try:
            process.start()
        except Exception as exc:
            response = error_response(
                error_code="RUN_SPAWN_FAILED",
                http_status=500,
                message=f"Failed to spawn run for skill {skill_id}: {exc}",
                details={"skill_id": skill_id},
                retry_strategy="idempotent",
            )
            raise_error_response(response)

        record = RunRecord(
            metadata=metadata,
            skill_id=skill_id,
            run_dir=run_dir,
            process=process,
            process_queue=process_queue,
        )
        self._runs[run_id] = record
        task = asyncio.create_task(self._drain_process_queue(record))
        record.drain_task = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return metadata

    async def start_batch_run(
        self,
        skill_id: str,
        input_ids: list[WorkspaceEntryName],
    ) -> BatchRunResponse:
        """One run per named test input, in the order the caller named them.

        ``WorkspaceEntryName`` rather than ``str`` so the signature says which
        vocabulary these ids belong to; the request model
        (``BatchRunRequest.input_ids``) is where that is enforced, and
        ``_load_test_input`` proves containment for the path each id resolves to.
        """
        resolve_skill_dir(skill_id)
        batch_id = f"batch-{new_run_id()}"
        items: list[tuple[str, str]] = []
        for input_id in input_ids:
            inputs = _load_test_input(skill_id, input_id)
            metadata = await self.start_run(skill_id, RunRequest(input_data=inputs))
            items.append((input_id, metadata.run_id))

        self._batches[batch_id] = BatchRecord(
            batch_id=batch_id,
            skill_id=skill_id,
            items=items,
        )
        return BatchRunResponse(batch_id=batch_id, sub_run_ids=[run_id for _, run_id in items])

    def get_batch_status(self, batch_id: str) -> BatchRunStatus:
        record = self._batches.get(batch_id)
        if record is None:
            raise standard_http_exception(
                "RESUME_CHECKPOINT_NOT_FOUND",
                f"Batch not found: {batch_id}",
                {"batch_id": batch_id},
            )

        items: list[BatchRunItem] = []
        for input_id, run_id in record.items:
            metadata = self._metadata_for(record.skill_id, run_id)
            items.append(
                BatchRunItem(
                    input_id=input_id,
                    run_id=run_id,
                    status=metadata.status,
                    started_at=metadata.started_at,
                    metrics=metadata.metrics,
                ),
            )
        completed = sum(1 for item in items if item.status != "running")
        status: Literal["running", "success", "failed"]
        if completed < len(items):
            status = "running"
        elif any(item.status == "failed" for item in items):
            status = "failed"
        else:
            status = "success"
        return BatchRunStatus(
            batch_id=record.batch_id,
            skill_id=record.skill_id,
            status=status,
            total=len(items),
            completed=completed,
            items=items,
        )

    def list_runs(self, skill_id: str) -> RunListResponse:
        # Runs and predicts are stored apart and read together: the split is a
        # storage fact, the single history is the product (decision 2026-08-09
        # D13). Which kind a row is stays on RunMetadata.kind, as before.
        skill_dir = resolve_skill_dir(skill_id)
        metadata: list[RunMetadata] = []
        for root in (runs_dir_for(skill_dir), predicts_dir_for(skill_dir)):
            if not root.exists():
                continue
            for metadata_path in root.glob("*/run_metadata.json"):
                # A record that cannot be read is a fault in the store, not a
                # run that does not exist. Skipping it returned a history that
                # was silently one run shorter — which is how a mid-save read
                # spent months looking like "the run was never there".
                try:
                    metadata.append(
                        self._reconciled(skill_id, _metadata_with_input_summary(metadata_path))
                    )
                except Exception as exc:
                    response = error_response(
                        error_code="RUN_METADATA_UNREADABLE",
                        http_status=500,
                        message=f"Cannot read run record {metadata_path.parent.name}: {exc}",
                        details={"skill_id": skill_id, "metadata_path": str(metadata_path)},
                        retry_strategy="idempotent",
                    )
                    raise_error_response(response)
        runs = sorted(metadata, key=lambda item: item.started_at, reverse=True)
        return RunListResponse(runs=runs, total=len(runs))

    def get_run_detail(self, skill_id: str, run_id: str) -> RunDetail:
        run_dir = run_dir_for(skill_id, run_id)
        # The report path rides on the metadata, the same place the run LIST
        # carries it (D8), so a reader never has to know which endpoint it came
        # from. Derived here rather than in ``_metadata_for`` because a still-
        # registered run holds its metadata in memory, from before the report
        # existed.
        metadata = self._metadata_for(skill_id, run_id).model_copy(
            update={"report_path": _run_report_path(run_dir)}
        )
        # What this run COMMITTED, asked once and asked directly. A run that was
        # killed mid-flight reaches a verdict without ever writing a final state
        # or a trace, and "it produced neither" is a fact about that run, not a
        # failure to read it — the detail has a null context and an empty event
        # list to say so. Deciding that by catching `artifact.not_found` instead
        # would fold in a second, opposite case: an object the manifest DECLARES
        # whose blob is gone, which is corruption and must keep surfacing
        # (`test_run_detail_exposes_missing_sealed_artifact_without_legacy_json_fallback`).
        # An unsealed run still raises here, because "still going" is its own
        # answer and the caller turns it into a 409.
        produced = _run_objects(run_dir)
        return RunDetail(
            metadata=metadata,
            input_data=(
                _read_run_artifact_json(run_dir, "input_data.json")
                if "input_data.json" in produced
                else None
            ),
            events=_read_run_artifact_events(run_dir) if "trace.jsonl" in produced else [],
            final_context=(
                _read_run_artifact_json(run_dir, "final_state.json")
                if "final_state.json" in produced
                else None
            ),
            artifacts=_readable_artifact_paths(run_dir, produced),
        )

    def rebuild_run_report(self, skill_id: str, run_id: str) -> RunMetadata:
        """Re-render this run's report from its sealed artifacts.

        The report is a pure projection (RUN_EXECUTION-5), so re-rendering is
        idempotent and this is the one entry point that makes "可随时重新生成"
        true of a run that finished before today's renderer existed. It is done
        on demand rather than on a stored renderer version: a version stamp is
        one more thing that has to be remembered on every change to the
        renderer, and the vendored-sidecar rebuild already showed what a
        forgotten "bump this too" step costs.

        A run that has not reached a verdict is refused. ``report_path`` is
        derived from the file existing, so writing one mid-run would make every
        run row advertise a report for a run that is still going.
        """
        metadata = self._metadata_for(skill_id, run_id)
        if metadata.status not in CONCLUDED_RUN_STATUSES:
            raise standard_http_exception(
                "RUN_NOT_CONCLUDED",
                f"Run {run_id} has not finished, so there is nothing to project yet",
                {"skill_id": skill_id, "run_id": run_id, "status": metadata.status},
            )
        run_dir = run_dir_for(skill_id, run_id)
        write_run_report(run_dir)
        return metadata.model_copy(update={"report_path": _run_report_path(run_dir)})

    #: Every run status maps to exactly one thing the surfaces are told, so a new
    #: status cannot silently fall through to "fail".
    _GATE_OUTCOME_BY_RUN_STATUS: ClassVar[dict[str, GateOutcome]] = {
        "success": "pass",
        "failed": "fail",
        "paused": "paused",
        "cancelled": "stopped",
        "abandoned": "stopped",
        "running": "started",
    }

    def _reconciled(self, skill_id: str, metadata: RunMetadata) -> RunMetadata:
        """The run's status as it actually stands, not merely as it was last written.

        ``running`` is a claim about a worker, and a record cannot keep a claim
        honest by itself: a sidecar holds its live runs in memory only, so a
        restarted one starts empty while the record still reads ``running``.
        Asked whether the run was going, the list answered yes and ``pause_run``
        answered ``RUN_NOT_RUNNING`` — one question, two answers, and the badge
        spun for the rest of the session (ledger C1).

        ``paused`` is checked by nothing here, because it is not a claim about a
        worker: ``pause_run`` ends the worker deliberately and keeps the
        checkpoint, so "nobody holds the lock" is true of every paused run, alive
        sidecar or not. Reconciling it rewrote a pause the user chose as
        ``abandoned`` — "the app closed while it was going" — about a run that had
        already stopped on purpose (ledger C1 ④).

        Checking is possible because a worker holds a lock on its own run
        directory for as long as it lives (``run_liveness``). Nobody holding it
        means nobody is running the run, and a run whose worker vanished ended —
        ``abandoned``, which is neither ``cancelled`` (a person asked) nor
        ``failed`` (the run itself failed).

        A run THIS sidecar started is left alone: its registry entry is the
        memory, and a worker that has not written its lock yet would otherwise be
        declared dead in the moment between spawn and first claim.
        """
        if metadata.status != "running":
            return metadata
        if metadata.run_id in self._runs:
            return metadata
        run_dir = run_dir_for(skill_id, metadata.run_id)
        if run_worker_is_alive(run_dir):
            return metadata
        abandoned = metadata.model_copy(update={"status": "abandoned"})
        _write_run_metadata(run_dir, abandoned)
        return abandoned

    async def pause_run(self, skill_id: str, run_id: str) -> RunMetadata:
        """Stop the worker but leave the run continuable.

        The engine only clears a run's checkpoints when the run finishes on its
        own, so a worker stopped part-way leaves one behind and ``resume_skill``
        can pick the run up from there. Pausing is that: end the process, keep
        everything, and say the run is waiting rather than over.
        """
        if self._metadata_for(skill_id, run_id).status != "running":
            raise standard_http_exception(
                "RUN_NOT_RUNNING",
                f"Run is not running: {run_id}",
                {"skill_id": skill_id, "run_id": run_id},
            )
        # A `running` run always has a record here: one this sidecar does not
        # hold has no worker either, and `_reconciled` has already closed it as
        # `abandoned` — which the status check above rejects.
        record = self._runs[run_id]
        self._terminate_worker(record)
        # No pause point: killing the worker stops it wherever it happens to be,
        # which is not a place the run can name.
        return await self._record_paused_run(record, record.metadata.model_copy(update={"status": "paused"}))

    async def _record_paused_run(self, record: RunRecord, metadata: RunMetadata) -> RunMetadata:
        """Write down that a run is waiting rather than over.

        Deliberately NOT ``_finalize_terminal_run``: that seals the run
        directory, and sealing says "nothing more will be written here" about a
        run that is going to be written to again the moment it continues. The
        auto-commit and the report hang off the seal for the same reason — both
        describe a finished run.

        One place, because both ways a run pauses end identically. The user's
        Pause button ends the worker; a breakpoint lets the engine end it
        itself. What is left behind — a checkpoint, a record saying ``paused``,
        and a gate telling the surfaces so — is the same either way.
        """
        record.metadata = metadata
        _write_run_metadata(record.run_dir, metadata)
        await self._save_run_metadata(record.skill_id, metadata)
        await publish_skill_gate(
            skill_id=record.skill_id,
            gate="run",
            outcome=self._GATE_OUTCOME_BY_RUN_STATUS[metadata.status],
            run_id=metadata.run_id,
        )
        return metadata

    async def stop_run(self, skill_id: str, run_id: str) -> RunMetadata:
        """End a run for good, keeping what it produced.

        Deleting was the only way to end a run early and it removes the run
        directory, so "end this and keep what it got" could not be said. This is
        the ending; pausing is the other choice, and both leave the run readable.

        Whether a run can be ended is read from its record, not from this
        sidecar's memory of it. A paused run has no worker to signal — `pause_run`
        ended it deliberately — so ending it is a write to its own directory,
        which the run id alone reaches. Requiring a registry entry made the list
        say `paused` while this said 409 about every run a previous sidecar had
        paused: one question, two answers (ledger C1 ④).
        """
        metadata = self._metadata_for(skill_id, run_id)
        if metadata.status not in {"running", "paused"}:
            raise standard_http_exception(
                "RUN_NOT_RUNNING",
                f"Run is neither running nor paused: {run_id}",
                {"skill_id": skill_id, "run_id": run_id},
            )
        cancelled = metadata.model_copy(update={"status": "cancelled"})
        record = self._runs.get(run_id)
        if record is None:
            # Only `paused` reaches here: an unheld `running` run reconciles to
            # `abandoned`, which the check above rejects.
            return await self._seal_terminal_run(
                skill_id=skill_id,
                run_dir=run_dir_for(skill_id, run_id),
                metadata=cancelled,
            )
        self._terminate_worker(record)
        await self._finalize_terminal_run(record, cancelled)
        return cancelled

    @staticmethod
    def _terminate_worker(record: RunRecord) -> None:
        process = record.process
        if process is not None and hasattr(process, "terminate"):
            process.terminate()

    def delete_run(self, skill_id: str, run_id: str) -> None:
        _validate_run_id_segment(run_id)
        record = self._runs.pop(run_id, None)
        if record is not None and hasattr(record.process, "is_alive") and record.process.is_alive():
            record.process.terminate()
        run_dir = run_dir_for(skill_id, run_id)
        if not run_dir.exists():
            raise standard_http_exception(
                "RESUME_CHECKPOINT_NOT_FOUND",
                f"Run not found: {run_id}",
                {"skill_id": skill_id, "run_id": run_id},
            )
        shutil.rmtree(run_dir)

    async def stream_run(
        self,
        skill_id: str,
        run_id: str,
        *,
        cursor: str | None = None,
    ) -> asyncio.Queue[dict[str, Any] | None]:
        # A paused run is going to write again the moment someone resumes it, so
        # this sidecar takes it over and the watcher stays attached. Replaying
        # and hanging up left the watcher reconnecting on a timer to find out —
        # and blind to everything a resume produced until it did.
        record = self.take_over_paused_run(skill_id, run_id)
        if record is None:
            return await self._replay_finished_run(skill_id, run_id, cursor=cursor)
        replay: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        try:
            events = _events_after_cursor(record.events, cursor=cursor)
        except (StreamCursorExpiredError, StreamCursorGapError, ValueError) as exc:
            await replay.put(_stream_error_envelope(run_id, exc).model_dump(mode="json"))
            await replay.put(None)
            return replay
        for event in events:
            await replay.put(event.model_dump(mode="json"))
        if record.metadata.status in {"running", "paused"}:
            record.subscribers.append(replay)
        else:
            await replay.put(None)
        return replay

    def stream_run_deltas(self, run_id: str) -> _DeltaStream:
        """Watch a running run's output arrive.

        A finished run has nothing to stream: its deltas were never kept, and
        what they spelled out is on its step frames. So an unknown or finished
        run gets a stream that is already over rather than an error — "there is
        no more text coming" is the true answer to the question asked.
        """
        watcher = _DeltaStream()
        record = self._runs.get(run_id)
        if record is None or record.metadata.status != "running":
            watcher.close()
            return watcher
        record.delta_watchers.append(watcher)
        return watcher

    def stop_streaming_deltas(self, run_id: str, watcher: _DeltaStream) -> None:
        """Let a watcher go when its socket does.

        Without this a run keeps handing pieces to a browser tab that closed
        twenty minutes ago — and keeps paying for its backlog.
        """
        watcher.close()
        record = self._runs.get(run_id)
        if record is not None and watcher in record.delta_watchers:
            record.delta_watchers.remove(watcher)

    async def _replay_finished_run(
        self,
        skill_id: str,
        run_id: str,
        *,
        cursor: str | None,
    ) -> asyncio.Queue[dict[str, Any] | None]:
        """Serve a run that no longer has an in-memory record from its files.

        A record lives only as long as the run and only inside the process that
        ran it — a predict's transient record lasts a few hundred milliseconds,
        and every record dies with a restart. The run's own directory outlives
        both, so it is what a late subscriber reads. Only a run that exists
        nowhere is refused.
        """
        run_dir = run_dir_for(skill_id, run_id)
        if not (run_dir / "run_metadata.json").exists():
            raise standard_http_exception(
                "RESUME_CHECKPOINT_NOT_FOUND",
                f"Run not found: {run_id}",
                {"skill_id": skill_id, "run_id": run_id},
            )
        replay: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        events = _read_events(run_dir / "trace.jsonl", run_id=run_id)
        try:
            events = _events_after_cursor(events, cursor=cursor)
        except (StreamCursorExpiredError, StreamCursorGapError, ValueError) as exc:
            await replay.put(_stream_error_envelope(run_id, exc).model_dump(mode="json"))
            await replay.put(None)
            return replay
        for event in events:
            await replay.put(event.model_dump(mode="json"))
        await replay.put(None)
        return replay

    async def shutdown(self) -> None:
        for record in list(self._runs.values()):
            process = record.process
            if hasattr(process, "is_alive") and process.is_alive():
                process.terminate()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    @staticmethod
    def _run_dir_if_here(skill_id: str, run_id: str) -> Path | None:
        """Where this run's directory would be, or None if nothing here names it.

        `run_dir_for` raises for a skill this Studio does not hold open, which is
        right for a request ABOUT that skill and wrong for one merely asking
        whether there is a run to take over — the resume endpoint has to report
        the runtime-state error it actually got, not a 404 about a skill it
        never needed to open.
        """
        if not _is_safe_run_id_segment(run_id):
            return None
        skill_dir = opened_skill_dir(skill_id)
        if skill_dir is None:
            return None
        return run_root_for(skill_dir, run_id) / run_id

    def _recorded_metadata(self, skill_id: str, run_id: str) -> RunMetadata | None:
        """What this run's record or its directory says about it, if either does.

        `_metadata_for` is the same lookup for callers whose request is ABOUT
        the run and so cannot proceed without it. Callers merely asking whether
        there is a run here — is this one paused, is there anything to take over
        — need the question to have an answer either way.
        """
        record = self._runs.get(run_id)
        if record is not None:
            return record.metadata
        run_dir = self._run_dir_if_here(skill_id, run_id)
        if run_dir is None:
            return None
        metadata_path = run_dir / "run_metadata.json"
        if not metadata_path.exists():
            return None
        return self._reconciled(
            skill_id, RunMetadata.model_validate_json(read_published_text(metadata_path))
        )

    def _metadata_for(self, skill_id: str, run_id: str) -> RunMetadata:
        _validate_run_id_segment(run_id)
        metadata = self._recorded_metadata(skill_id, run_id)
        if metadata is None:
            raise standard_http_exception(
                "RESUME_CHECKPOINT_NOT_FOUND",
                f"Run not found: {run_id}",
                {"skill_id": skill_id, "run_id": run_id},
            )
        return metadata

    def register_transient_predict_run(
        self,
        *,
        skill_id: str,
        run_id: str,
        run_dir: Path,
    ) -> RunRecord:
        metadata = RunMetadata(
            run_id=run_id,
            status="running",
            started_at=datetime.now(UTC),
            kind="predict",
        )
        record = RunRecord(
            metadata=metadata,
            skill_id=skill_id,
            run_dir=run_dir,
            process=None,
            process_queue=None,
        )
        self._runs[run_id] = record
        return record

    def emit_transient_run_event(self, run_id: str, raw_event: dict[str, Any]) -> None:
        record = self._runs.get(run_id)
        if record is None:
            return
        event = _event_envelope_from_callback(
            raw_event,
            run_id=record.metadata.run_id,
            seq=len(record.events) + 1,
        )
        record.events.append(event)
        event_json = event.model_dump(mode="json")
        record.ws_queue.put_nowait(event_json)
        for subscriber in list(record.subscribers):
            subscriber.put_nowait(event_json)

    def record_predict_outcome(
        self,
        *,
        run_id: str,
        run_dir: Path,
        status: Literal["success", "failed"],
        started_at: datetime,
    ) -> None:
        """Leave a finished predict the same on-disk account a run leaves.

        A predict is dropped from the in-memory registry the moment it ends, so
        without this file nothing can answer questions about it afterwards:
        ``_metadata_for`` finds neither a record nor a metadata file and every
        reader — ``get_run_detail``, and through it ``query_run_trace`` — fails
        with RESUME_CHECKPOINT_NOT_FOUND while the trace sits unread in the very
        same directory. The account format belongs here, so predict reports its
        verdict rather than writing the file itself.
        """
        _write_run_metadata(
            run_dir,
            RunMetadata(run_id=run_id, status=status, started_at=started_at, kind="predict"),
        )

    def finish_transient_predict_run(self, run_id: str) -> None:
        record = self._runs.pop(run_id, None)
        if record is None:
            return
        record.ws_queue.put_nowait(None)
        for subscriber in list(record.subscribers):
            subscriber.put_nowait(None)
        record.subscribers.clear()
        for watcher in record.delta_watchers:
            watcher.close()
        record.delta_watchers.clear()

    async def _drain_process_queue(self, record: RunRecord) -> None:
        terminal_metadata: RunMetadata | None = None
        while True:
            try:
                message = await asyncio.to_thread(record.process_queue.get, True, 0.1)
            except Empty:
                if not record.process.is_alive():
                    break
                continue

            if not isinstance(message, dict):
                continue
            message_type = message.get("type")
            if message_type == "event" and isinstance(message.get("event"), dict):
                event = _event_envelope_from_callback(
                    message["event"],
                    run_id=record.metadata.run_id,
                    seq=len(record.events) + 1,
                )
                record.events.append(event)
                event_json = event.model_dump(mode="json")
                await record.ws_queue.put(event_json)
                for subscriber in list(record.subscribers):
                    await subscriber.put(event_json)
            elif message_type == "delta" and isinstance(message.get("event"), dict):
                frame = _delta_envelope_from_callback(
                    message["event"], run_id=record.metadata.run_id
                )
                for watcher in record.delta_watchers:
                    watcher.offer(frame)
            elif message_type == "status":
                reported = message.get("status")
                # Three endings, because a run that stopped part-way is neither
                # of the other two — and reading it as either loses the fact
                # that it can be continued.
                status: Literal["success", "failed", "paused"] = (
                    reported if reported in {"success", "paused"} else "failed"
                )
                metrics = _tokens_metrics(message.get("metrics"))
                raw_error = message.get("error") if status == "failed" else None
                pause_point = message.get("paused_at") if status == "paused" else None
                terminal_metadata = record.metadata.model_copy(
                    update={
                        "status": status,
                        "metrics": metrics,
                        "error": RunError.model_validate(_run_error(raw_error)) if raw_error else None,
                        "paused_at": RunPausePoint.model_validate(pause_point) if pause_point else None,
                    }
                )
                break

        if terminal_metadata is None and record.metadata.status == "running":
            exitcode = getattr(record.process, "exitcode", None)
            status_from_exit: Literal["success", "failed"] = "success" if exitcode == 0 else "failed"
            terminal_metadata = record.metadata.model_copy(update={"status": status_from_exit})
        stopped = terminal_metadata is not None and terminal_metadata.status == "paused"
        if terminal_metadata is not None:
            if stopped:
                await self._record_paused_run(record, terminal_metadata)
            else:
                await self._finalize_terminal_run(record, terminal_metadata)
        if not stopped:
            # A stopped run keeps its stream: continuing it writes more of the
            # SAME run's story, to these same watchers, under this same run id.
            # Closing here left the resume's events pouring into a pipe nobody
            # was reading, so the canvas sat on the moment the run stopped
            # however correctly the run went on (problem ledger C1 ③). The
            # worker being gone is not the run being over.
            await self._close_run_stream(record)
        with contextlib.suppress(Exception):
            record.process.join(timeout=0)

    async def _close_run_stream(self, record: RunRecord) -> None:
        """Tell everyone watching that this run will write nothing more."""
        await record.ws_queue.put(None)
        for subscriber in list(record.subscribers):
            await subscriber.put(None)
        record.subscribers.clear()
        for watcher in record.delta_watchers:
            watcher.close()
        record.delta_watchers.clear()

    async def _finalize_terminal_run(self, record: RunRecord, metadata: RunMetadata) -> None:
        # The record is what every reader asks for the run's status, and it is
        # deliberately the LAST thing to go terminal: whoever sees it flip may
        # immediately read the sealed run dir, so the flip has to trail
        # finalization, not lead it. The assignment sits in `finally` because a
        # storage write that fails must not strand the record — and every future
        # reader of it — on "running" forever.
        try:
            metadata = await self._seal_terminal_run(
                skill_id=record.skill_id,
                run_dir=record.run_dir,
                metadata=metadata,
            )
        finally:
            record.metadata = metadata

    async def _seal_terminal_run(
        self,
        *,
        skill_id: str,
        run_dir: Path,
        metadata: RunMetadata,
    ) -> RunMetadata:
        """Close a run out on disk however it ended, and announce that it ended.

        Everything here is about the run DIRECTORY, so it asks for the directory
        rather than for a record: a paused run that this sidecar never started is
        ended through exactly this path, and a second copy of the sequence for
        that one caller would be two answers to "what does ending a run do".

        Sealing leads, because this is the only place that runs however the run
        ended, and it precedes the auto-commit or the archived snapshot is of a
        run the archive itself says is unfinished. The gate is published in
        `finally` for the same reason the record flip is: a failed write must not
        leave every listener waiting for an ending that already happened.
        """
        try:
            await asyncio.to_thread(_seal_run_artifacts, run_dir)
            await self._copy_final_state_to_storage(run_dir)
            # The report reads the run's FINAL metadata (outcome, failure reason,
            # archive status), so it is written after that lands.
            if metadata.status == "success" and metadata.auto_commit:
                metadata = await self._auto_commit_successful_run(run_dir, metadata)
            _write_run_metadata(run_dir, metadata)
            await asyncio.to_thread(write_run_report, run_dir)
            await self._save_run_metadata(skill_id, metadata)
        finally:
            await publish_skill_gate(
                skill_id=skill_id,
                gate="run",
                outcome=self._GATE_OUTCOME_BY_RUN_STATUS[metadata.status],
                run_id=metadata.run_id,
            )
        return metadata

    async def _save_run_metadata(self, skill_id: str, metadata: RunMetadata) -> None:
        metadata_store = self._metadata_store()
        await metadata_store.save_run_metadata(config.DEFAULT_USER_ID, skill_id, metadata)

    def take_over_paused_run(self, skill_id: str, run_id: str) -> RunRecord | None:
        """Hold a paused run this sidecar did not start, so it can write again.

        A record lives only inside the process that spawned the run, and dies
        with it; the run's own directory outlives both. `stop_run` already ends
        such a run through that directory alone, because ending is a write
        (ledger C1 ④). Resuming is not: a resumed run PRODUCES — events while it
        runs, an ending to announce — and a record is where a run's stream and
        its watchers live. Without one the resumed segment ran correctly and
        invisibly, and the canvas sat on the moment it stopped until the app was
        reopened (ledger C1 ③).

        So whoever resumes or watches a paused run takes it over here, rebuilding
        the record from the durable artifact — the move a supervisor makes when
        it re-adopts a service it did not launch, rather than starting a second
        one. What does NOT carry over is the worker: there is none to re-adopt,
        and a resumed run executes inside the request, so the process slots stay
        empty rather than holding a stand-in that could be signalled.

        Returns None unless the run is paused: a finished run will write nothing
        more, and a `running` one belongs to whoever holds it.
        """
        record = self._runs.get(run_id)
        if record is not None:
            return record
        metadata = self._recorded_metadata(skill_id, run_id)
        if metadata is None or metadata.status != "paused":
            return None
        run_dir = self._run_dir_if_here(skill_id, run_id)
        if run_dir is None:
            return None
        record = RunRecord(
            metadata=metadata,
            skill_id=skill_id,
            run_dir=run_dir,
            process=None,
            process_queue=None,
        )
        self._runs[run_id] = record
        return record

    def observe_resumed_run(
        self, run_id: str, *, skill_id: str
    ) -> Callable[[dict[str, Any]], None] | None:
        """A sink for the events a resumed segment emits, or None if it cannot run.

        A resume executes the engine inside the request rather than in a worker,
        so there is no process queue to carry its events — and without a sink
        they reached the trace file and nothing else. The live view is built
        from events, so a segment that emits none is invisible however
        correctly it ran: press Resume and the canvas keeps showing the moment
        the run stopped (problem ledger C1 ③).

        The events queue as they arrive and are read when the request returns —
        the engine call is synchronous on the event loop, so nothing drains
        until it finishes. Delivering them as they happen would mean moving that
        call off the loop, which is a separate change with its own risks; this
        one is about the canvas converging at all.

        Returns None only when there is no paused run here to speak for — a
        finished run, or one that exists nowhere.
        """
        record = self.take_over_paused_run(skill_id, run_id)
        if record is None:
            return None

        def observe(raw_event: dict[str, Any]) -> None:
            event = _event_envelope_from_callback(
                raw_event,
                run_id=record.metadata.run_id,
                seq=len(record.events) + 1,
            )
            record.events.append(event)
            event_json = event.model_dump(mode="json")
            record.ws_queue.put_nowait(event_json)
            for subscriber in list(record.subscribers):
                subscriber.put_nowait(event_json)

        return observe

    async def record_resume_result(
        self,
        *,
        skill_id: str,
        run_id: str,
        request: ResumeReq,
        report: ResumeReport,
    ) -> RunMetadata:
        """Apply what one resumed segment did to the run it belongs to.

        The report is applied ONTO the run's own record rather than replacing
        it. Rebuilding a whole `RunMetadata` out of the resume's answer reset
        every field that answer did not mention — the run's start time, its
        input summary, its artifact identity, and whether it archives — which
        was noticed once and patched three fields at a time until the next
        field was added and quietly fell off (problem ledger C1 ③).
        """
        record = self._runs.get(run_id)
        if record is not None:
            metadata = _resumed(record.metadata, report)
            record.metadata = metadata
            _write_run_metadata(record.run_dir, metadata)
            await self._save_run_metadata(skill_id, metadata)
            event = _resume_audit_event(
                run_id=run_id,
                seq=len(record.events) + 1,
                request=request,
                metadata=metadata,
            )
            record.events.append(event)
            event_json = event.model_dump(mode="json")
            await record.ws_queue.put(event_json)
            for subscriber in list(record.subscribers):
                await subscriber.put(event_json)
            if metadata.status != "running":
                # However it ended, say so where the surfaces are listening. A
                # resume used to end in silence: the run gate that every other
                # ending publishes was never sent, so the canvas held the
                # picture it had when the run stopped — by then a lie.
                if metadata.status == "paused":
                    # Stopped again, so again not over: a third segment can
                    # follow, and it needs these same watchers.
                    metadata = await self._record_paused_run(record, metadata)
                else:
                    await self._finalize_terminal_run(record, metadata)
                    await self._close_run_stream(record)
                    # Sealing is what decides `git_status`, so the answer to the
                    # caller is the record as it stands AFTER it, not the one
                    # handed in before.
                    metadata = record.metadata
            return metadata

        # Nothing held here, but the run's own directory still holds its record,
        # and that record — not a fresh one built out of the segment's answer —
        # is what the report updates.
        existing = self._recorded_metadata(skill_id, run_id)
        run_dir = self._run_dir_if_here(skill_id, run_id)
        if existing is None or run_dir is None or not run_dir.exists():
            raise standard_http_exception(
                "RESUME_CHECKPOINT_NOT_FOUND",
                f"Run not found: {run_id}",
                {"skill_id": skill_id, "run_id": run_id},
            )
        metadata = _resumed(existing, report)
        _write_run_metadata(run_dir, metadata)
        await self._save_run_metadata(skill_id, metadata)
        return metadata

    async def _copy_final_state_to_storage(self, run_dir: Path) -> None:
        final_state_path = run_dir / "final_state.json"
        if not final_state_path.exists():
            return
        content = await asyncio.to_thread(final_state_path.read_text, encoding="utf-8")
        await self._storage_backend().write_text(str(final_state_path), content)

    async def _auto_commit_successful_run(
        self, run_dir: Path, metadata: RunMetadata
    ) -> RunMetadata:
        skill_dir = run_dir.parent.parent.parent
        git_status: Literal["committed", "unchanged", "locked", "failed", "no_git"]
        try:
            # The archiver reports what it did; "not a git repo" and "the run
            # changed nothing" are both benign and both worth telling apart.
            git_status = await asyncio.to_thread(
                self.git_service.auto_commit_run,
                skill_dir,
                metadata.run_id,
            )
            if git_status != "committed":
                logger.info(
                    "auto commit made no archive (%s) skill_dir=%s", git_status, skill_dir
                )
        except GitFileLockedError as exc:
            logger.warning("auto commit skipped due to git lock: %s", exc)
            git_status = "locked"
        except GitCommandError as exc:
            logger.warning("auto commit failed: %s", exc)
            git_status = "failed"
        return metadata.model_copy(update={"git_status": git_status})

    def _metadata_store(self) -> MetadataStore:
        return get_metadata()

    def _storage_backend(self) -> StorageBackend:
        return get_storage()


def _resumed(metadata: RunMetadata, report: ResumeReport) -> RunMetadata:
    """The run, as it stands after one resumed segment reported in.

    `paused_at` is cleared unless the report names a new stopping point: a run
    that went past where it stopped must not keep saying it is waiting there.
    """
    return metadata.model_copy(
        update={
            "status": report.status,
            "metrics": report.metrics if report.metrics is not None else metadata.metrics,
            "paused_at": report.paused_at,
        }
    )


def _resume_audit_event(
    *,
    run_id: str,
    seq: int,
    request: ResumeReq,
    metadata: RunMetadata,
) -> EventEnvelope:
    payload: dict[str, Any] = {
        "schema_version": "studio.resume.audit.v1",
        "event_type": "resume_applied",
        "run_id": run_id,
        "status": metadata.status,
        "checkpoint_id": request.checkpoint_id,
        "checkpoint_ns": request.checkpoint_ns,
        "resume_from_node_id": request.resume_from_node_id,
        "resume_to_node_id": request.resume_to_node_id,
        "context_override_keys": sorted((request.context_overrides or {}).keys()),
    }
    human_response = request.human_response
    if isinstance(human_response, dict) and isinstance(human_response.get("tool_call_id"), str):
        payload["human_response_tool_call_id"] = human_response["tool_call_id"]
    return make_event_envelope(
        stream_id=f"run:{run_id}",
        seq=seq,
        run_id=run_id,
        event_type="resume_applied",
        payload=payload,
        cursor=f"run:{run_id}:{seq}",
    )


def _is_safe_run_id_segment(run_id: str) -> bool:
    """Whether this id can name a run directory at all, asked without raising."""
    return bool(
        run_id
        and run_id not in {".", ".."}
        and "/" not in run_id
        and "\\" not in run_id
        and _SAFE_RUN_ID_RE.fullmatch(run_id)
    )


def _validate_run_id_segment(run_id: str) -> None:
    if not _is_safe_run_id_segment(run_id):
        response = error_response(
            error_code="INVALID_RUN_ID",
            http_status=400,
            message=f"Invalid run id: {run_id}",
            details={"run_id": run_id},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)


def _source_less_run_dir_for(skill_id: str, run_id: str) -> Path:
    if (
        not skill_id
        or skill_id in {".", ".."}
        or "/" in skill_id
        or "\\" in skill_id
        or not _SAFE_SKILL_ID_RE.fullmatch(skill_id)
    ):
        response = error_response(
            error_code="INVALID_SKILL_ID",
            http_status=400,
            message=f"Invalid skill id: {skill_id}",
            details={"skill_id": skill_id},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)
    _validate_run_id_segment(run_id)
    workspace = config.DEFAULT_SKILLS_ROOT / skill_id / ".workspace"
    root = predicts_root(workspace) if is_predict_run_id(run_id) else runs_root(workspace)
    return root / run_id


def _write_run_metadata(run_dir: Path, metadata: RunMetadata) -> None:
    # Same document as the metadata store writes, so it gets the same guarantee:
    # readers of a run's record never catch it between two versions.
    write_text_atomically(run_dir / "run_metadata.json", metadata.persisted_json())


def _persist_run_input_artifact(
    run_dir: Path,
    input_data: dict[str, Any],
    *,
    artifact_ref: dict[str, Any] | None = None,
) -> None:
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    store.begin_run(run_dir.name, metadata=_artifact_store_metadata("run_manager", artifact_ref))
    store.put_batch(
        run_dir.name,
        {
            "input_data.json": json.dumps(input_data, ensure_ascii=False, default=str).encode("utf-8"),
        },
    )


def _tokens_metrics(raw: Any) -> TokensMetrics | None:
    if not isinstance(raw, dict):
        return None
    input_tokens = int(raw.get("total_input_tokens", raw.get("input_tokens", 0)) or 0)
    output_tokens = int(raw.get("total_output_tokens", raw.get("output_tokens", 0)) or 0)
    raw_wall_time = raw.get("wall_time_sec")
    return TokensMetrics(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=int(raw.get("total_tokens", input_tokens + output_tokens) or 0),
        cost_estimate=raw.get("cost_estimate"),
        # ⑧a: faithfully pass the engine's wall_time_sec through instead of stripping it.
        wall_time_sec=float(raw_wall_time) if raw_wall_time is not None else None,
    )


def _event_envelope_from_callback(raw_event: dict[str, Any], *, run_id: str, seq: int) -> EventEnvelope:
    event_type = str(raw_event.get("event_type") or "unknown")
    stream_id = f"run:{run_id}"
    return make_event_envelope(
        stream_id=stream_id,
        seq=seq,
        run_id=run_id,
        event_type=event_type,
        payload=dict(raw_event),
        cursor=f"{stream_id}:{seq}",
    )


def _delta_envelope_from_callback(raw_event: dict[str, Any], *, run_id: str) -> DeltaEnvelope:
    return DeltaEnvelope(
        stream_id=f"run:{run_id}",
        run_id=run_id,
        step_id=str(raw_event.get("step_id") or ""),
        channel=str(raw_event.get("channel") or "text"),
        text=str(raw_event.get("text") or ""),
        restarts_step=bool(raw_event.get("restarts_step")),
        timestamp=datetime.now(UTC),
    )


def _cursor_seq(cursor: str, *, stream_id: str) -> int:
    prefix = f"{stream_id}:"
    if not cursor.startswith(prefix):
        raise ValueError(f"Invalid cursor for stream {stream_id}: {cursor}")
    try:
        return int(cursor.removeprefix(prefix))
    except ValueError as err:
        raise ValueError(f"Invalid cursor format: {cursor}") from err


def _events_after_cursor(events: list[EventEnvelope], *, cursor: str | None) -> list[EventEnvelope]:
    if cursor is None:
        return list(events)
    if not events:
        return []
    stream_id = events[0].stream_id
    requested_seq = _cursor_seq(cursor, stream_id=stream_id)
    min_seq = events[0].seq
    max_seq = events[-1].seq
    if requested_seq < min_seq - 1:
        raise StreamCursorExpiredError(f"Cursor expired: requested {requested_seq}, min available is {min_seq}")
    if requested_seq > max_seq:
        raise StreamCursorGapError(f"Cursor gap: requested {requested_seq}, max available is {max_seq}")
    return [event for event in events if event.seq > requested_seq]


def _stream_error_envelope(run_id: str, exc: Exception) -> EventEnvelope:
    error_code = getattr(exc, "error_code", "stream.cursor_invalid")
    return make_event_envelope(
        stream_id=f"run:{run_id}",
        seq=0,
        run_id=run_id,
        event_type="stream.error",
        payload={},
        cursor=f"run:{run_id}:0",
        error_code=error_code,
        error_payload=TransportErrorPayload(
            error_code=error_code,
            message=str(exc),
            details={"run_id": run_id},
            retryable=error_code != "stream.cursor_expired",
        ),
    )


def _read_events(path: Path, *, run_id: str) -> list[EventEnvelope]:
    if not path.exists():
        return []
    return _read_events_from_bytes(path.read_bytes(), run_id=run_id)


def _read_events_from_bytes(raw: bytes, *, run_id: str) -> list[EventEnvelope]:
    events: list[EventEnvelope] = []
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        raw_event = json.loads(line)
        try:
            callback = _EVENT_ADAPTER.validate_python(raw_event)
            payload = callback.model_dump(mode="json")
        except Exception:
            payload = raw_event if isinstance(raw_event, dict) else {"value": raw_event}
        events.append(
            _event_envelope_from_callback(
                payload,
                run_id=run_id,
                seq=len(events) + 1,
            )
        )
    return events


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def _read_run_artifact_json(run_dir: Path, path: str) -> dict[str, Any] | None:
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    raw = store.get_run_object(run_dir.name, path)
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StudioAdapterError(
            "artifact.corrupt_json",
            {"run_id": run_dir.name, "path": path, "detail": str(exc)},
        ) from exc
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def _read_run_artifact_json_if_present(run_dir: Path, path: str) -> dict[str, Any] | None:
    """For readers that describe runs which may still be going.

    The run LIST covers live runs, whose artifacts are by definition not sealed
    yet, so both "no such object" and "not sealed" mean the same thing to it:
    there is nothing to summarise yet. A reader of ONE finished run must not
    reuse this — it cannot tell an absent object from an unreadable one.
    """
    from app.core.adapters.http_transport import StudioAdapterError

    try:
        return _read_run_artifact_json(run_dir, path)
    except StudioAdapterError as exc:
        if exc.error_code in {"artifact.not_found", "artifact.run_not_sealed"}:
            return None
        raise


def _read_run_artifact_events(run_dir: Path) -> list[EventEnvelope]:
    from app.core.adapters.http_transport import StudioAdapterError
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    raw = store.get_run_object(run_dir.name, "trace.jsonl")
    try:
        return _read_events_from_bytes(raw, run_id=run_dir.name)
    except UnicodeDecodeError as exc:
        raise StudioAdapterError(
            "artifact.corrupt_trace",
            {"run_id": run_dir.name, "path": "trace.jsonl", "detail": str(exc)},
        ) from exc
    except json.JSONDecodeError as exc:
        raise StudioAdapterError(
            "artifact.corrupt_trace",
            {"run_id": run_dir.name, "path": "trace.jsonl", "detail": str(exc)},
        ) from exc


def _run_report_path(run_dir: Path) -> str | None:
    """Where this run's report lives, named the way the workspace editor reads.

    Workspace-relative and forward-slashed, because the report opens IN the app
    (`onFileOpen` → the read-only editor document), and that opener resolves
    paths against the skill's workspace root. An absolute path is what you hand
    an OS shell — which is exactly the behaviour PM 08-19 Q6 overturned.

    The layout is fixed by `run_dir_for`: `<skill>/.workspace/<runs|predicts>/
    <run_id>`, so the skill directory is three levels up.
    """
    from app.services.run_report import REPORT_FILENAME

    report = run_dir / REPORT_FILENAME
    if not report.is_file():
        return None
    skill_dir = run_dir.parents[2]
    return report.relative_to(skill_dir).as_posix()


def _run_objects(run_dir: Path) -> dict[str, str]:
    """Everything this run committed, path → content hash: its record of itself.

    Readers reach a sealed run THROUGH this record, so it is also the answer to
    "did this run produce X": anything absent from it is unreachable however
    plainly a file of that name sits in the directory. A ref carrying no path is
    left out — there is no name by which anyone could ask for it.
    """
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    return {
        ref.path: ref.content_hash
        for ref in store.list_run_objects(run_dir.name)
        if ref.path is not None
    }


def _readable_artifact_paths(run_dir: Path, objects: dict[str, str]) -> list[str]:
    """The run's user-facing artifacts, each proven readable before it is listed.

    The blob is fetched and thrown away on purpose: a listing is an offer to open
    the file, and one that names a blob nobody can read is a promise the API
    cannot keep.
    """
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    paths: list[str] = []
    for path, content_hash in objects.items():
        if not path.startswith("artifacts/"):
            continue
        store.get_object(hash=content_hash)
        paths.append(path)
    return sorted(paths)


def test_inputs_dir_for(skill_id: str) -> Path:
    return test_inputs_dir_for_skill(resolve_skill_dir(skill_id))


def _load_test_input(skill_id: str, input_id: str) -> dict[str, Any]:
    # The id's SPELLING is already constrained by the request model
    # (`BatchRunRequest.input_ids`), which is what keeps `..` out. What that
    # cannot see is where the name resolves TO: a well-formed name that happens
    # to be a symlink lands wherever the link points, so the second proof is
    # about the resolved path rather than the string.
    inputs_dir = test_inputs_dir_for(skill_id)
    try:
        candidates = [
            resolve_inside(inputs_dir, input_id),
            resolve_inside(inputs_dir, f"{input_id}.json"),
        ]
    except PathEscapesDirectory as exc:
        raise standard_http_exception(
            "TEST_INPUT_VALIDATION_FAILED",
            f"Test input is not inside this skill's import_files: {input_id}",
            {"skill_id": skill_id, "input_id": input_id},
        ) from exc
    input_path = next((path for path in candidates if path.is_file()), None)
    if input_path is None:
        raise standard_http_exception(
            "RESUME_CHECKPOINT_NOT_FOUND",
            f"Test input not found: {input_id}",
            {"skill_id": skill_id, "input_id": input_id},
        )
    loaded = json.loads(read_authored_text(input_path))
    if isinstance(loaded, dict) and isinstance(loaded.get("input_data"), dict):
        return dict(loaded["input_data"])
    if isinstance(loaded, dict):
        return loaded
    # A file's CONTENTS are past every schema: the request model can constrain
    # the id, not what the id points at. So this answers with the code that says
    # which test input is wrong, rather than raising a bare ValueError for a
    # generic handler to relabel `MANIFEST_VALIDATION_FAILED` — naming the
    # skill's manifest for a defect in one of its inputs.
    raise standard_http_exception(
        "TEST_INPUT_VALIDATION_FAILED",
        f"Test input must be a JSON object: {input_id}",
        {"skill_id": skill_id, "input_id": input_id},
    )


def _metadata_with_input_summary(metadata_path: Path) -> RunMetadata:
    """One row of the run list, with the two fields the stored record lacks.

    ``input_summary`` is backfilled from the sealed input artifact; ``report_path``
    is probed off the report file, which is where that truth lives (D8).
    """
    run_dir = metadata_path.parent
    metadata = RunMetadata.model_validate_json(read_published_text(metadata_path))
    updates: dict[str, Any] = {"report_path": _run_report_path(run_dir)}
    if not metadata.input_summary:
        input_data = _read_run_artifact_json_if_present(run_dir, "input_data.json") or {}
        updates["input_summary"] = _input_summary(input_data)
    return metadata.model_copy(update=updates)


def _input_summary(input_data: dict[str, Any]) -> str | None:
    if not input_data:
        return None
    parts: list[str] = []
    for key in sorted(input_data)[:2]:
        parts.append(f"{key}={_summary_value(input_data[key])}")
    remaining = len(input_data) - len(parts)
    suffix = f", +{remaining}" if remaining > 0 else ""
    return ", ".join(parts) + suffix


def _summary_value(value: Any) -> str:
    if isinstance(value, str):
        compact = value.replace("\n", " ")
        return compact[:32] + ("..." if len(compact) > 32 else "")
    if isinstance(value, int | float | bool) or value is None:
        return str(value)
    if isinstance(value, list):
        return f"[{len(value)} items]"
    if isinstance(value, dict):
        return f"{{{len(value)} keys}}"
    return type(value).__name__


run_manager = RunManager()
