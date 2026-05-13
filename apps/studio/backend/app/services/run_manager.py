"""Run process management and WebSocket event streaming."""

from __future__ import annotations

import asyncio
import contextlib
import json
import multiprocessing
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty
from typing import Any, Literal

from graph_agent import run_skill
from graph_agent.callbacks import Callback
from graph_agent.callbacks.events import (
    AmbiguityReportEvent,
    CallbackEvent,
    CompactionEvent,
    DeadEndPrunedEvent,
    FinishTaskEvent,
    LLMCallEvent,
    NudgeEvent,
    PhaseEndEvent,
    PhaseStartEvent,
    RetryEvent,
    ToolCallEvent,
    ValidationFailEvent,
    WorkingMemoryUpdateEvent,
)
from graph_agent.callbacks.serialize import to_jsonable_dict
from graph_agent.callbacks.tracing import TracingCallback
from pydantic import TypeAdapter

from app.core import config
from app.core.backends import get_metadata, get_storage
from app.core.exceptions import error_response, raise_error_response, standard_http_exception
from app.core.ports.metadata import MetadataStore
from app.core.ports.storage import StorageBackend
from app.models.runs import (
    BatchRunItem,
    BatchRunResponse,
    BatchRunStatus,
    RunDetail,
    RunListResponse,
    RunMetadata,
    RunRequest,
    TokensMetrics,
)
from app.services.git_local import GitLocalService
from app.services.skills import resolve_skill_dir, run_dir_for, test_inputs_dir_for_skill

_EVENT_ADAPTER: TypeAdapter[Any] = TypeAdapter(CallbackEvent)


@dataclass
class RunRecord:
    """In-memory handle for a spawned run."""

    metadata: RunMetadata
    skill_id: str
    run_dir: Path
    process: Any
    process_queue: Any
    ws_queue: asyncio.Queue[dict[str, Any] | None] = field(default_factory=asyncio.Queue)
    events: list[dict[str, Any]] = field(default_factory=list)
    drain_task: asyncio.Task[None] | None = None


@dataclass
class BatchRecord:
    """In-memory metadata for one batch run request."""

    batch_id: str
    skill_id: str
    items: list[tuple[str, str]]


class StudioQueueCallback(Callback):
    """Callback that forwards graph_agent events to a multiprocessing queue."""

    def __init__(self, process_queue: Any) -> None:
        self._queue = process_queue

    def on_event(self, event: CallbackEvent) -> None:
        self._put_event(event)

    def on_phase_start(self, phase_name: str, context: dict[str, Any]) -> None:
        self._put_event(PhaseStartEvent(phase_name=phase_name, context=to_jsonable_dict(context)))

    def on_phase_end(
        self,
        phase_name: str,
        context: dict[str, Any],
        metrics: dict[str, Any],
    ) -> None:
        self._put_event(
            PhaseEndEvent(
                phase_name=phase_name,
                context=to_jsonable_dict(context),
                metrics=to_jsonable_dict(metrics),
            ),
        )

    def on_llm_call(
        self,
        phase_name: str,
        input_tokens: int,
        output_tokens: int,
        *,
        messages: list[dict[str, Any]] | None = None,
        response_data: dict[str, Any] | None = None,
    ) -> None:
        self._put_event(
            LLMCallEvent(
                phase_name=phase_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                messages=to_jsonable_dict(messages),
                response_data=to_jsonable_dict(response_data),
            ),
        )

    def on_tool_call(
        self,
        phase_name: str,
        tool_name: str,
        args: dict[str, Any],
        result: str,
        *,
        duration_ms: float | None = None,
    ) -> None:
        self._put_event(
            ToolCallEvent(
                phase_name=phase_name,
                tool_name=tool_name,
                args=to_jsonable_dict(args),
                result=result,
                duration_ms=duration_ms,
            ),
        )

    def on_validation_fail(
        self,
        phase_name: str,
        errors: list[str],
        retry_count: int,
    ) -> None:
        self._put_event(
            ValidationFailEvent(
                phase_name=phase_name,
                errors=errors,
                retry_count=retry_count,
            ),
        )

    def on_retry(self, phase_name: str, target_phase: str, feedback: list[str]) -> None:
        self._put_event(
            RetryEvent(phase_name=phase_name, target_phase=target_phase, feedback=feedback),
        )

    def on_finish_task(self, phase_name: str, reasoning: str, evidence: list[str]) -> None:
        self._put_event(
            FinishTaskEvent(phase_name=phase_name, reasoning=reasoning, evidence=evidence),
        )

    def on_nudge(
        self,
        phase_name: str,
        nudge_count: int,
        nudge_type: str = "standard",
    ) -> None:
        self._put_event(
            NudgeEvent(phase_name=phase_name, nudge_count=nudge_count, nudge_type=nudge_type),
        )

    def on_working_memory_update(self, phase_name: str, content_length: int) -> None:
        self._put_event(
            WorkingMemoryUpdateEvent(phase_name=phase_name, content_length=content_length),
        )

    def on_dead_end_pruned(self, phase_name: str, summary: str) -> None:
        self._put_event(DeadEndPrunedEvent(phase_name=phase_name, summary=summary))

    def on_compaction(self, phase_name: str, removed_pairs: int) -> None:
        self._put_event(CompactionEvent(phase_name=phase_name, removed_pairs=removed_pairs))

    def on_ambiguity_report(
        self,
        phase_name: str,
        ambiguity_type: str,
        question: str,
        decision: str,
    ) -> None:
        self._put_event(
            AmbiguityReportEvent(
                phase_name=phase_name,
                ambiguity_type=ambiguity_type,
                question=question,
                decision=decision,
            ),
        )

    def _put_event(self, event: CallbackEvent) -> None:
        self._queue.put({"type": "event", "event": event.model_dump(mode="json")})


def _run_worker_main(
    skill_id: str,
    skill_path_raw: str,
    run_dir_raw: str,
    inputs: dict[str, Any],
    process_queue: Any,
) -> None:
    """Subprocess entrypoint that executes graph_agent.run_skill."""
    run_dir = Path(run_dir_raw)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(exist_ok=True)
    started = time.monotonic()
    callbacks = [StudioQueueCallback(process_queue), TracingCallback(trace_dir=run_dir)]
    try:
        result = run_skill(
            Path(skill_path_raw),
            trace_dir=run_dir,
            callbacks=callbacks,
            unattended=True,
            cleanup_checkpoints_on_finish=False,
            **inputs,
        )
        metrics = dict(result.get("metrics", {}))
        metrics.setdefault("wall_time_sec", result.get("wall_time_sec", time.monotonic() - started))
        _write_json(run_dir / "final_state.json", result.get("context", {}))
        _write_json(run_dir / "metrics.json", {"status": "success", **metrics})
        _ensure_run_files(run_dir)
        process_queue.put({"type": "status", "status": "success", "metrics": metrics})
    except Exception as exc:  # noqa: BLE001
        metrics = {"wall_time_sec": round(time.monotonic() - started, 3)}
        _write_json(run_dir / "final_state.json", {})
        _write_json(
            run_dir / "metrics.json",
            {"status": "failed", "error": str(exc), **metrics},
        )
        _ensure_run_files(run_dir)
        process_queue.put(
            {
                "type": "status",
                "status": "failed",
                "metrics": metrics,
                "error": str(exc),
            },
        )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def _ensure_run_files(run_dir: Path) -> None:
    (run_dir / "artifacts").mkdir(exist_ok=True)
    (run_dir / "tracing.jsonl").touch(exist_ok=True)
    (run_dir / "checkpoints.db").touch(exist_ok=True)


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

    async def start_run(self, skill_id: str, request: RunRequest) -> RunMetadata:
        skill_dir = resolve_skill_dir(skill_id)
        skill_path = skill_dir / "SKILL.md"
        inputs = _runtime_inputs_from_request(request)
        run_id = _new_run_id()
        run_dir = run_dir_for(skill_id, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "artifacts").mkdir(exist_ok=True)
        _write_json(run_dir / "input_data.json", inputs)
        metadata = RunMetadata(
            run_id=run_id,
            status="running",
            started_at=datetime.now(UTC),
            input_summary=_input_summary(inputs),
        )
        _write_run_metadata(run_dir, metadata)
        await self._save_run_metadata(skill_id, metadata)

        process_queue = self.queue_factory()
        process = self.process_factory(
            target=self.worker,
            args=(skill_id, str(skill_path), str(run_dir), inputs, process_queue),
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
        return RunDetail(
            metadata=metadata,
            input_data=_read_optional_json(run_dir / "input_data.json"),
            events=_read_events(run_dir / "tracing.jsonl"),
            final_context=_read_optional_json(run_dir / "final_state.json"),
            artifacts=[str(path) for path in sorted((run_dir / "artifacts").glob("*"))],
        )

    def delete_run(self, skill_id: str, run_id: str) -> None:
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

    async def stream_run(self, run_id: str) -> asyncio.Queue[dict[str, Any] | None]:
        record = self._runs.get(run_id)
        if record is None:
            raise standard_http_exception(
                "RESUME_CHECKPOINT_NOT_FOUND",
                f"Run not found: {run_id}",
                {"run_id": run_id},
            )
        if record.metadata.status == "running":
            return record.ws_queue
        replay: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        for event in record.events:
            await replay.put(event)
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
        return RunMetadata.model_validate_json(metadata_path.read_text())

    async def _drain_process_queue(self, record: RunRecord) -> None:
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
                event = message["event"]
                record.events.append(event)
                await record.ws_queue.put(event)
            elif message_type == "status":
                status: Literal["success", "failed"] = (
                    "success" if message.get("status") == "success" else "failed"
                )
                metrics = _tokens_metrics(message.get("metrics"))
                metadata = RunMetadata(
                    run_id=record.metadata.run_id,
                    status=status,
                    started_at=record.metadata.started_at,
                    metrics=metrics,
                    input_summary=record.metadata.input_summary,
                )
                _write_run_metadata(record.run_dir, metadata)
                await self._save_run_metadata(record.skill_id, metadata)
                record.metadata = metadata
                break

        if record.metadata.status == "running":
            exitcode = getattr(record.process, "exitcode", None)
            status_from_exit: Literal["success", "failed"] = (
                "success" if exitcode == 0 else "failed"
            )
            record.metadata = RunMetadata(
                run_id=record.metadata.run_id,
                status=status_from_exit,
                started_at=record.metadata.started_at,
                metrics=record.metadata.metrics,
                input_summary=record.metadata.input_summary,
            )
            _write_run_metadata(record.run_dir, record.metadata)
            await self._save_run_metadata(record.skill_id, record.metadata)
        await self._copy_final_state_to_storage(record)
        if record.metadata.status == "success":
            await asyncio.to_thread(_sync_latest_run, record.run_dir)
            await asyncio.to_thread(
                self.git_service.auto_commit_run,
                record.run_dir.parent.parent.parent,
                record.metadata.run_id,
            )
        await record.ws_queue.put(None)
        with contextlib.suppress(Exception):
            record.process.join(timeout=0)

    async def _save_run_metadata(self, skill_id: str, metadata: RunMetadata) -> None:
        metadata_store = self._metadata_store()
        await metadata_store.save_run_metadata(config.DEFAULT_USER_ID, skill_id, metadata)

    async def _copy_final_state_to_storage(self, record: RunRecord) -> None:
        final_state_path = record.run_dir / "final_state.json"
        if not final_state_path.exists():
            return
        content = await asyncio.to_thread(final_state_path.read_text, encoding="utf-8")
        await self._storage_backend().write_text(str(final_state_path), content)

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


def _new_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def _write_run_metadata(run_dir: Path, metadata: RunMetadata) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")


def _tokens_metrics(raw: Any) -> TokensMetrics | None:
    if not isinstance(raw, dict):
        return None
    input_tokens = int(raw.get("total_input_tokens", raw.get("input_tokens", 0)) or 0)
    output_tokens = int(raw.get("total_output_tokens", raw.get("output_tokens", 0)) or 0)
    return TokensMetrics(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=int(raw.get("total_tokens", input_tokens + output_tokens) or 0),
        cost_estimate=raw.get("cost_estimate"),
    )


def _read_events(path: Path) -> list[CallbackEvent]:
    if not path.exists():
        return []
    events: list[CallbackEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(_EVENT_ADAPTER.validate_json(line))
    return events


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def test_inputs_dir_for(skill_id: str) -> Path:
    return test_inputs_dir_for_skill(resolve_skill_dir(skill_id))


def _sync_latest_run(run_dir: Path) -> None:
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
    metadata = RunMetadata.model_validate_json(metadata_path.read_text())
    if metadata.input_summary:
        return metadata
    input_data = _read_optional_json(metadata_path.parent / "input_data.json") or {}
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
