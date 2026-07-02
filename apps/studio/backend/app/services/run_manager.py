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
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty
from typing import Any, Literal

from pydantic import TypeAdapter

from app.core import config
from app.core.adapters.engine import (
    CallbackEvent,
    EventEnvelope,
    NodeRunResult,
    RunResultSnapshot,
    RunResultsRef,
    StreamCursorExpiredError,
    StreamCursorGapError,
    TransportErrorPayload,
    make_event_envelope,
)
from app.core.adapters.transport_factory import build_engine_adapter
from app.core.backends import get_metadata, get_storage
from app.core.exceptions import error_response, raise_error_response, standard_http_exception
from app.core.ports.metadata import MetadataStore
from app.core.ports.storage import StorageBackend
from app.models.runs import (
    BatchRunItem,
    BatchRunResponse,
    BatchRunStatus,
    CompareCandidateRun,
    CompareRunGroupResponse,
    CompareRunResponse,
    ResumeReq,
    RunDetail,
    RunListResponse,
    RunMetadata,
    RunRequest,
    TokensMetrics,
)
from app.services.git_local import GitCommandError, GitFileLockedError, GitLocalService
from app.services.predict_gate import require_passing_predict
from app.services.skill_resolver import build_studio_skill_resolver as build_studio_skill_resolver
from app.services.skills import resolve_skill_dir, run_dir_for, test_inputs_dir_for_skill

_EVENT_ADAPTER: TypeAdapter[Any] = TypeAdapter(CallbackEvent)
logger = logging.getLogger(__name__)
_LATEST_SYNC_LOCK = threading.Lock()
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
    subscribers: list[asyncio.Queue[dict[str, Any] | None]] = field(default_factory=list)
    drain_task: asyncio.Task[None] | None = None
    auto_commit: bool = True


@dataclass
class BatchRecord:
    """In-memory metadata for one batch run request."""

    batch_id: str
    skill_id: str
    items: list[tuple[str, str]]


def _queue_event_subscriber(process_queue: Any) -> Any:
    def _emit(event: CallbackEvent) -> None:
        process_queue.put({"type": "event", "event": event.model_dump(mode="json")})

    return _emit


def _run_worker_main(
    skill_id: str,
    run_dir_raw: str,
    inputs: dict[str, Any],
    process_queue: Any,
    art_ref: dict[str, Any],
    roles_path_override: str | None = None,
) -> None:
    """Subprocess entrypoint that executes EngineAdapter.run_artifact.

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
        if adapter.transport == "in_process":
            run_payload["event_subscriber"] = emit_to_queue
        result = adapter.run_artifact(run_payload)
        metrics = _result_metrics(result)
        metrics.setdefault("wall_time_sec", _result_wall_time(result, started))
        final_context = _result_context(result)
        # P0#3 (handshake audit §5.3): never report fake success — honor RunResult.success.
        if _result_success(result):
            metrics_payload = {"status": "success", **metrics}
            _persist_run_artifacts(
                skill_id,
                run_dir,
                input_data=inputs,
                final_context=final_context,
                metrics=metrics_payload,
                result=result,
                artifact_ref=art_ref,
            )
            process_queue.put({"type": "status", "status": "success", "metrics": metrics})
        else:
            run_error = _result_error(result)
            metrics_payload = {"status": "failed", "error": run_error, **metrics}
            _persist_run_artifacts(
                skill_id,
                run_dir,
                input_data=inputs,
                final_context=final_context,
                metrics=metrics_payload,
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
        metrics_payload = {"status": "failed", "error": str(exc), **metrics}
        _persist_run_artifacts(
            skill_id,
            run_dir,
            input_data=inputs,
            final_context={},
            metrics=metrics_payload,
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
                "error": str(exc),
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
    result: Any,
    artifact_ref: dict[str, Any] | None = None,
) -> None:
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    store.begin_run(run_dir.name, metadata=_artifact_store_metadata("run_manager", artifact_ref))
    status = "success" if _result_success(result) else "failed"
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

        adapter = build_engine_adapter()
        art_ref = adapter.compile(
            {
                "skill_dir": str(skill_dir),
                "skill_id": skill_id,
                "artifact_scope": "ephemeral",
            }
        )

        # MVP1 run-and-verify gate: Run requires a passing Predict for *this* graph
        # state (server-side prerequisite, not UI-only). The gate matches the recorded
        # predict-pass content_hash against the freshly-compiled hash, so editing the
        # graph after a pass forces a re-predict. Raises RUN_REQUIRES_PREDICT (409)
        # when no matching passing predict is on record.
        require_passing_predict(skill_id, content_hash=art_ref["content_hash"])

        inputs = _runtime_inputs_from_request(request)
        run_id = _new_run_id()
        run_dir = run_dir_for(skill_id, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "artifacts").mkdir(exist_ok=True)
        _write_json(run_dir / "input_data.json", inputs)
        _persist_run_input_artifact(run_dir, inputs, artifact_ref=art_ref)
        metadata = RunMetadata(
            run_id=run_id,
            status="running",
            started_at=datetime.now(UTC),
            input_summary=_input_summary(inputs),
            **_metadata_artifact_fields(art_ref),
        )
        _write_run_metadata(run_dir, metadata)
        await self._save_run_metadata(skill_id, metadata)

        process_queue = self.queue_factory()
        process = self.process_factory(
            target=self.worker,
            args=(skill_id, str(run_dir), inputs, process_queue, art_ref),
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

    async def start_compare_run(
        self,
        skill_id: str,
        request: RunRequest,
    ) -> CompareRunResponse:
        """Fan a run out across model-compare candidates (n4-trace#23).

        Compiles once, gates once (require_passing_predict), then spawns one
        worker per candidate against the SAME artifact + inputs, each pointed at
        a materialized per-candidate ``llm_roles.yaml`` via STUDIO_LLM_ROLES_PATH.
        Every spawned run is tagged with a shared compare_group_id + candidate_id
        so the frontend Trace can tab between per-model results. No engine edit.
        """
        from app.services.run_compare import (
            new_compare_group_id,
            write_candidate_roles_file,
        )

        candidates = request.candidates or []
        if not candidates:
            response = error_response(
                error_code="COMPARE_REQUIRES_CANDIDATES",
                http_status=422,
                message="model-compare run requires at least one candidate",
                details={"skill_id": skill_id},
                retry_strategy="not_retryable",
            )
            raise_error_response(response)

        skill_dir = resolve_skill_dir(skill_id)
        adapter = build_engine_adapter()
        art_ref = adapter.compile(
            {
                "skill_dir": str(skill_dir),
                "skill_id": skill_id,
                "artifact_scope": "ephemeral",
            }
        )
        require_passing_predict(skill_id, content_hash=art_ref["content_hash"])

        inputs = _runtime_inputs_from_request(request)
        compare_group_id = new_compare_group_id()
        group_dir = run_dir_for(skill_id, compare_group_id).parent / f"_compare_{compare_group_id}"
        group_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "start_compare_run skill=%s group=%s candidates=%d",
            skill_id,
            compare_group_id,
            len(candidates),
        )

        spawned: list[CompareCandidateRun] = []
        for candidate in candidates:
            roles_file = write_candidate_roles_file(
                candidate=candidate,
                group_dir=group_dir,
            )
            metadata = await self._spawn_candidate_run(
                skill_id=skill_id,
                inputs=inputs,
                art_ref=art_ref,
                compare_group_id=compare_group_id,
                candidate_id=candidate.candidate_id,
                candidate_role_name=candidate.role_name,
                roles_path_override=str(roles_file),
            )
            spawned.append(
                CompareCandidateRun(
                    candidate_id=candidate.candidate_id,
                    role_name=candidate.role_name,
                    metadata=metadata,
                )
            )
        return CompareRunResponse(compare_group_id=compare_group_id, runs=spawned)

    async def _spawn_candidate_run(
        self,
        *,
        skill_id: str,
        inputs: dict[str, Any],
        art_ref: dict[str, Any],
        compare_group_id: str,
        candidate_id: str,
        candidate_role_name: str,
        roles_path_override: str,
    ) -> RunMetadata:
        """Spawn one compare-candidate worker tagged with its compare group."""
        run_id = _new_run_id()
        run_dir = run_dir_for(skill_id, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "artifacts").mkdir(exist_ok=True)
        _write_json(run_dir / "input_data.json", inputs)
        _persist_run_input_artifact(run_dir, inputs, artifact_ref=art_ref)
        metadata = RunMetadata(
            run_id=run_id,
            status="running",
            started_at=datetime.now(UTC),
            input_summary=_input_summary(inputs),
            compare_group_id=compare_group_id,
            candidate_id=candidate_id,
            candidate_role_name=candidate_role_name,
            **_metadata_artifact_fields(art_ref),
        )
        _write_run_metadata(run_dir, metadata)
        await self._save_run_metadata(skill_id, metadata)

        process_queue = self.queue_factory()
        process = self.process_factory(
            target=self.worker,
            args=(skill_id, str(run_dir), inputs, process_queue, art_ref, roles_path_override),
        )
        try:
            process.start()
        except Exception as exc:
            response = error_response(
                error_code="RUN_SPAWN_FAILED",
                http_status=500,
                message=f"Failed to spawn compare run for skill {skill_id}: {exc}",
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
        """Return the per-candidate runs of one compare group, for Trace tabs.

        Reads the persisted run metadata (same store ``list_runs`` reads) and
        filters to the requested compare group, surfacing each candidate's
        current status (including a failed candidate) so the frontend can render
        one tab per candidate with its result/failure state.
        """
        listing = self.list_runs(skill_id)
        runs: list[CompareCandidateRun] = []
        for metadata in listing.runs:
            if metadata.compare_group_id != compare_group_id:
                continue
            runs.append(
                CompareCandidateRun(
                    candidate_id=metadata.candidate_id or "",
                    role_name=metadata.candidate_role_name or "",
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
        inputs = _runtime_inputs_from_request(request)
        run_id = _new_run_id()
        run_dir = _source_less_run_dir_for(skill_id, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "artifacts").mkdir(exist_ok=True)
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
            args=(skill_id, str(run_dir), inputs, process_queue, artifact_ref),
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
            auto_commit=False,
        )
        self._runs[run_id] = record
        task = asyncio.create_task(self._drain_process_queue(record))
        record.drain_task = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return metadata

    async def start_batch_run(self, skill_id: str, input_ids: list[str]) -> BatchRunResponse:
        resolve_skill_dir(skill_id)
        if not input_ids:
            raise ValueError("input_ids must not be empty")

        batch_id = f"batch-{_new_run_id()}"
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
        resolve_skill_dir(skill_id)
        runs_root = run_dir_for(skill_id, "_").parent
        if not runs_root.exists():
            return RunListResponse(runs=[], total=0)
        metadata: list[RunMetadata] = []
        for metadata_path in runs_root.glob("*/run_metadata.json"):
            if metadata_path.parent.name == "latest":
                continue
            try:
                metadata.append(_metadata_with_input_summary(metadata_path))
            except Exception:
                continue
        runs = sorted(metadata, key=lambda item: item.started_at, reverse=True)
        return RunListResponse(runs=runs, total=len(runs))

    def get_run_detail(self, skill_id: str, run_id: str) -> RunDetail:
        metadata = self._metadata_for(skill_id, run_id)
        run_dir = run_dir_for(skill_id, run_id)
        final_context = _read_run_artifact_json(run_dir, "final_state.json")
        return RunDetail(
            metadata=metadata,
            input_data=_read_run_artifact_json_if_present(run_dir, "input_data.json"),
            events=_read_run_artifact_events(run_dir),
            final_context=final_context,
            artifacts=_read_run_artifact_paths(run_dir),
        )

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

    async def stream_run(self, run_id: str, *, cursor: str | None = None) -> asyncio.Queue[dict[str, Any] | None]:
        record = self._runs.get(run_id)
        if record is None:
            raise standard_http_exception(
                "RESUME_CHECKPOINT_NOT_FOUND",
                f"Run not found: {run_id}",
                {"run_id": run_id},
            )
        replay: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        try:
            events = _events_after_cursor(record.events, cursor=cursor)
        except (StreamCursorExpiredError, StreamCursorGapError, ValueError) as exc:
            await replay.put(_stream_error_envelope(run_id, exc).model_dump(mode="json"))
            await replay.put(None)
            return replay
        for event in events:
            await replay.put(event.model_dump(mode="json"))
        if record.metadata.status == "running":
            record.subscribers.append(replay)
        else:
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

    def _metadata_for(self, skill_id: str, run_id: str) -> RunMetadata:
        _validate_run_id_segment(run_id)
        record = self._runs.get(run_id)
        if record is not None:
            return record.metadata
        metadata_path = run_dir_for(skill_id, run_id) / "run_metadata.json"
        if not metadata_path.exists():
            raise standard_http_exception(
                "RESUME_CHECKPOINT_NOT_FOUND",
                f"Run not found: {run_id}",
                {"skill_id": skill_id, "run_id": run_id},
            )
        return RunMetadata.model_validate_json(metadata_path.read_text(encoding="utf-8"))

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
            elif message_type == "status":
                status: Literal["success", "failed"] = "success" if message.get("status") == "success" else "failed"
                metrics = _tokens_metrics(message.get("metrics"))
                terminal_metadata = record.metadata.model_copy(
                    update={
                        "status": status,
                        "metrics": metrics,
                    }
                )
                break

        if terminal_metadata is None and record.metadata.status == "running":
            exitcode = getattr(record.process, "exitcode", None)
            status_from_exit: Literal["success", "failed"] = "success" if exitcode == 0 else "failed"
            terminal_metadata = record.metadata.model_copy(update={"status": status_from_exit})
        if terminal_metadata is not None:
            await self._finalize_terminal_run(record, terminal_metadata)
        await record.ws_queue.put(None)
        for subscriber in list(record.subscribers):
            await subscriber.put(None)
        record.subscribers.clear()
        with contextlib.suppress(Exception):
            record.process.join(timeout=0)

    async def _finalize_terminal_run(self, record: RunRecord, metadata: RunMetadata) -> None:
        await self._copy_final_state_to_storage(record)
        if metadata.status == "success" and record.auto_commit:
            metadata = await self._auto_commit_successful_run(record, metadata)
            _write_run_metadata(record.run_dir, metadata)
            await asyncio.to_thread(_sync_latest_run, record.run_dir)
        else:
            _write_run_metadata(record.run_dir, metadata)
        await self._save_run_metadata(record.skill_id, metadata)
        record.metadata = metadata

    async def _save_run_metadata(self, skill_id: str, metadata: RunMetadata) -> None:
        metadata_store = self._metadata_store()
        await metadata_store.save_run_metadata(config.DEFAULT_USER_ID, skill_id, metadata)

    async def record_resume_result(
        self,
        *,
        skill_id: str,
        run_id: str,
        request: ResumeReq,
        metadata: RunMetadata,
    ) -> RunMetadata:
        record = self._runs.get(run_id)
        if record is not None:
            metadata = _preserve_resume_artifact_identity(record.metadata, metadata)
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
                await record.ws_queue.put(None)
                for subscriber in list(record.subscribers):
                    await subscriber.put(None)
                record.subscribers.clear()
            return metadata

        run_dir = run_dir_for(skill_id, run_id)
        if run_dir.exists():
            _write_run_metadata(run_dir, metadata)
            await self._save_run_metadata(skill_id, metadata)
        return metadata

    async def _copy_final_state_to_storage(self, record: RunRecord) -> None:
        final_state_path = record.run_dir / "final_state.json"
        if not final_state_path.exists():
            return
        content = await asyncio.to_thread(final_state_path.read_text, encoding="utf-8")
        await self._storage_backend().write_text(str(final_state_path), content)

    async def _auto_commit_successful_run(
        self, record: RunRecord, metadata: RunMetadata
    ) -> RunMetadata:
        skill_dir = record.run_dir.parent.parent.parent
        git_status: Literal["committed", "locked", "failed", "no_git"]
        try:
            commit_result = await asyncio.to_thread(
                self.git_service.auto_commit_run,
                skill_dir,
                record.metadata.run_id,
            )
            if commit_result is None:
                # auto_commit_run returns None only when the workspace is not a
                # git repository. F1/native-fs treats this as a benign boundary:
                # no autocommit safety net, but the run still succeeds.
                logger.info(
                    "auto commit skipped: workspace is not a git repository skill_dir=%s",
                    skill_dir,
                )
                git_status = "no_git"
            else:
                git_status = "committed"
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


def _runtime_inputs_from_request(request: RunRequest) -> dict[str, Any]:
    if request.paste_json:
        loaded = json.loads(request.paste_json)
        if not isinstance(loaded, dict):
            raise ValueError("paste_json must decode to a JSON object")
        return loaded
    return dict(request.input_data or {})


def _preserve_resume_artifact_identity(existing: RunMetadata, resumed: RunMetadata) -> RunMetadata:
    updates: dict[str, Any] = {}
    for field_name in ("artifact_ref", "source_map_ref", "execution_fingerprint"):
        if getattr(resumed, field_name) is None and getattr(existing, field_name) is not None:
            updates[field_name] = getattr(existing, field_name)
    return resumed.model_copy(update=updates) if updates else resumed


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


def _new_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def _validate_run_id_segment(run_id: str) -> None:
    if not run_id or run_id in {".", ".."} or "/" in run_id or "\\" in run_id or not _SAFE_RUN_ID_RE.fullmatch(run_id):
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
    return config.default_workspace_skills_dir() / skill_id / ".workspace" / "runs" / run_id


def _write_run_metadata(run_dir: Path, metadata: RunMetadata) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")


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


def _read_run_artifact_paths(run_dir: Path) -> list[str]:
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    refs = store.list_run_objects(run_dir.name)
    paths: list[str] = []
    for ref in refs:
        path = ref.path
        if not isinstance(path, str) or not path.startswith("artifacts/"):
            continue
        store.get_object(hash=ref.content_hash)
        paths.append(path)
    return sorted(paths)


def test_inputs_dir_for(skill_id: str) -> Path:
    return test_inputs_dir_for_skill(resolve_skill_dir(skill_id))


def _sync_latest_run(run_dir: Path) -> None:
    with _LATEST_SYNC_LOCK:
        latest_dir = run_dir.parent / "latest"
        if latest_dir == run_dir:
            return
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(run_dir, latest_dir)


def _load_test_input(skill_id: str, input_id: str) -> dict[str, Any]:
    candidates = [
        test_inputs_dir_for(skill_id) / input_id,
        test_inputs_dir_for(skill_id) / f"{input_id}.json",
    ]
    input_path = next((path for path in candidates if path.is_file()), None)
    if input_path is None:
        raise standard_http_exception(
            "RESUME_CHECKPOINT_NOT_FOUND",
            f"Test input not found: {input_id}",
            {"skill_id": skill_id, "input_id": input_id},
        )
    loaded = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(loaded, dict) and isinstance(loaded.get("input_data"), dict):
        return dict(loaded["input_data"])
    if isinstance(loaded, dict):
        return loaded
    raise ValueError(f"Test input must be a JSON object: {input_id}")


def _metadata_with_input_summary(metadata_path: Path) -> RunMetadata:
    metadata = RunMetadata.model_validate_json(metadata_path.read_text(encoding="utf-8"))
    if metadata.input_summary:
        return metadata
    input_data = _read_run_artifact_json_if_present(metadata_path.parent, "input_data.json") or {}
    return metadata.model_copy(update={"input_summary": _input_summary(input_data)})


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
