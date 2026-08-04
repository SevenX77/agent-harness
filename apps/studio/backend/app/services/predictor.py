"""Predict V2 in-process orchestration service."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from app.core.adapters.engine import (
    CallbackEvent,
    RunResult,
)
from app.core.adapters.transport_factory import build_engine_adapter
from app.models.runs import PredictDiagnosticExport
from app.services.diagnostic_export import export_predict_diagnostics
from app.services.gate_events import publish_skill_gate_from_thread
from app.services.run_manager import run_manager
from app.services.runtime_config import refresh_runtime_config, write_runtime_snapshot
from app.services.skills import ensure_workspace_skill_dir, workspace_dir_for

logger = logging.getLogger(__name__)

MAX_PHASE_REVISITS = 10


class PredictDeadlockError(RuntimeError):
    """Raised when P2 heuristic stubs appear to trap routing in a loop."""

    def __init__(self, phase_name: str, actual_path: list[str]) -> None:
        self.phase_name = phase_name
        self.actual_path = actual_path
        super().__init__(
            f"Predict P2 deadlock guard tripped for phase '{phase_name}' after {actual_path.count(phase_name)} visits"
        )


class PredictArtifactError(RuntimeError):
    """Raised when Engine artifact predict returns a structured error result."""

    def __init__(
        self,
        error_code: str,
        error_payload: dict[str, Any],
        *,
        run_id: str | None = None,
        retryable: bool = False,
    ) -> None:
        self.error_code = error_code
        self.error_payload = error_payload
        self.run_id = run_id
        self.retryable = retryable
        message = str(error_payload.get("message") or error_payload.get("detail") or error_code)
        super().__init__(message)


class PredictorService:
    """Studio Backend orchestration layer for Predict V2 runs."""

    def __init__(self, **_deprecated_hooks: Any) -> None:
        if _deprecated_hooks:
            logger.debug("Ignoring deprecated PredictorService constructor hooks.")

    def dispatch_predict_job(
        self,
        skill_id: str,
        mock_param: Any = None,
        *,
        input_data: dict[str, Any] | None = None,
        current_hashes: dict[str, dict[str, str]] | None = None,
    ) -> RunResult:
        """Resolve strategy, run graph_agent in Predict mode, and assemble result."""
        skill_dir = ensure_workspace_skill_dir(skill_id)
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

        # Route through EngineAdapter predict_artifact
        from app.core.adapters.http_transport import StudioAdapterError

        predict_run_id = f"predict-{uuid.uuid4().hex}"
        workspace_dir = workspace_dir_for(skill_dir)
        # 状态对等(决议 2026-08-03 D3):predict 也流事件, 所以它开跑同样要广播——
        # 否则 copilot 发起的 predict 不会把人带到 Trace 面板, 而人自己点会。
        publish_skill_gate_from_thread(
            skill_id=skill_id,
            gate="predict",
            outcome="started",
            run_id=predict_run_id,
        )
        event_subscriber: Callable[[CallbackEvent], None] | None = None
        if getattr(adapter, "transport", None) == "in_process":
            run_manager.register_transient_predict_run(
                skill_id=skill_id,
                run_id=predict_run_id,
                run_dir=workspace_dir / "runs" / predict_run_id,
            )
            event_subscriber = _predict_event_subscriber(predict_run_id)

        try:
            payload: dict[str, Any] = {
                "artifact_ref": _public_artifact_ref(art_ref),
                "mock_llm": mock_param,
                "current_hashes": current_hashes,
                "inputs": input_data or {},
                "workspace_dir": str(workspace_dir),
                "thread_id": predict_run_id,
                "execution_context": {"runtime_config": runtime_config},
            }
            if event_subscriber is not None:
                payload["event_subscriber"] = event_subscriber
            result = adapter.predict_artifact(payload)
        except StudioAdapterError as exc:
            if exc.error_code == "engine.predict_deadlock":
                raise PredictDeadlockError(exc.error_payload["phase_name"], exc.error_payload["actual_path"]) from exc
            raise exc
        finally:
            if event_subscriber is not None:
                _finish_predict_event_stream(predict_run_id)

        if isinstance(result, dict) and "error_code" in result and "success" not in result:
            error_payload = result.get("error_payload")
            raise PredictArtifactError(
                str(result["error_code"]),
                error_payload if isinstance(error_payload, dict) else {},
                run_id=result.get("run_id") if isinstance(result.get("run_id"), str) else None,
                retryable=bool(result.get("retryable", False)),
            )
        if isinstance(result, dict):
            result = RunResult.model_validate(result)
        result = result.model_copy(update=_result_artifact_fields(art_ref))
        # 状态对等(决议 2026-08-03 D2):这次 Predict 的结论只判一次。落盘的账、
        # 广播的 gate、前端的判定共用它,不各自再推一遍。
        status = export_predict_diagnostics(result).status
        self._persist_predict_result(
            skill_dir,
            result.run_id,
            result,
            status=status,
            content_hash=art_ref["content_hash"],
            artifact_ref=art_ref,
            runtime_config=runtime_config,
        )
        publish_skill_gate_from_thread(
            skill_id=skill_id,
            gate="predict",
            outcome="pass" if status == "success" else "fail",
            content_hash=art_ref["content_hash"],
        )
        return cast(RunResult, result)

    def export_diagnostics(self, result: RunResult) -> PredictDiagnosticExport:
        """Expose PredictResult through the Studio in-process diagnostic contract."""
        return export_predict_diagnostics(result)

    def _persist_predict_result(
        self,
        skill_dir: Path,
        run_id: str,
        result: RunResult,
        *,
        status: Literal["success", "failed"],
        content_hash: str,
        artifact_ref: dict[str, Any],
        runtime_config: dict[str, Any],
    ) -> None:
        workspace_dir = workspace_dir_for(skill_dir)
        from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

        run_dir = workspace_dir / "runs" / run_id
        trace_file = run_dir / "trace.jsonl"
        store = LocalRunArtifactStore(root=workspace_dir)
        store.begin_run(run_id, metadata=_artifact_store_metadata("predict", artifact_ref))
        # Readers reach a sealed run through its manifest, so anything left out of
        # the seal is unreachable however plainly it sits in the directory. Predict
        # used to seal result.json alone while the engine wrote the trace and the
        # final context beside it, which is why every question about a finished
        # predict came back artifact.not_found.
        store.put_batch(
            run_id,
            {
                "result.json": result.model_dump_json().encode("utf-8"),
                "final_state.json": json.dumps(result.context, ensure_ascii=False, default=str).encode("utf-8"),
                "trace.jsonl": trace_file.read_bytes() if trace_file.exists() else b"",
            },
        )
        store.seal_run(run_id)

        run_dir.mkdir(parents=True, exist_ok=True)
        write_runtime_snapshot(run_dir, runtime_config)
        (run_dir / "result.json").write_text(
            result.model_dump_json(),
            encoding="utf-8",
        )
        run_manager.record_predict_outcome(
            run_id=run_id,
            run_dir=run_dir,
            status=status,
            started_at=result.started_at or datetime.now(UTC),
        )
        if result.success:
            # Persist predict-pass server-side so the run-spawn path can enforce the
            # MVP1 "predict-pass unlocks Run" prerequisite for any caller, not just the UI.
            # Bind it to the compiled content_hash so a later edit invalidates the pass.
            from app.services.predict_gate import record_predict_pass

            record_predict_pass(skill_dir, result.skill_id, run_id, content_hash=content_hash)
        else:
            logger.info(
                "predictor predict_pass=not_recorded skill_id=%s run_id=%s reason=predict_failed",
                result.skill_id,
                run_id,
            )


def _fallback_trace_from_skill(skill_dir: Path, raw_result: Any) -> list[dict[str, Any]]:
    del raw_result
    adapter = build_engine_adapter()
    try:
        return adapter.get_fallback_trace(str(skill_dir))
    except Exception:
        return []


predictor_service = PredictorService()


_ARTIFACT_IDENTITY_KEYS = (
    "artifact_id",
    "content_hash",
    "store",
    "version",
    "manifest_ref",
    "source_map_ref",
    "execution_fingerprint",
)


def _public_artifact_ref(artifact_ref: dict[str, Any]) -> dict[str, Any]:
    return {key: artifact_ref[key] for key in _ARTIFACT_IDENTITY_KEYS if key in artifact_ref}


def _result_artifact_fields(artifact_ref: dict[str, Any]) -> dict[str, Any]:
    public = _public_artifact_ref(artifact_ref)
    fields: dict[str, Any] = {"artifact_ref": public}
    source_map_ref = public.get("source_map_ref")
    if isinstance(source_map_ref, str):
        fields["source_map_ref"] = source_map_ref
    execution_fingerprint = public.get("execution_fingerprint")
    if isinstance(execution_fingerprint, str):
        fields["execution_fingerprint"] = execution_fingerprint
    return fields


def _artifact_store_metadata(source: str, artifact_ref: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {"source": source}
    public = _public_artifact_ref(artifact_ref)
    metadata["artifact_ref"] = public
    for key, value in public.items():
        metadata[key] = value
    return metadata


def _predict_event_subscriber(run_id: str) -> Callable[[CallbackEvent], None]:
    loop = _current_event_loop()

    def _emit(event: CallbackEvent) -> None:
        payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else event
        if not isinstance(payload, dict):
            return
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(run_manager.emit_transient_run_event, run_id, payload)
        else:
            run_manager.emit_transient_run_event(run_id, payload)

    return _emit


def _finish_predict_event_stream(run_id: str) -> None:
    loop = _current_event_loop()
    if loop is not None and loop.is_running():
        loop.call_soon_threadsafe(run_manager.finish_transient_predict_run, run_id)
    else:
        run_manager.finish_transient_predict_run(run_id)


def _current_event_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None

__all__ = [
    "MAX_PHASE_REVISITS",
    "PredictArtifactError",
    "PredictDeadlockError",
    "PredictorService",
    "predictor_service",
]
