"""Predict V2 in-process orchestration service."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from app.core.adapters.engine import (
    RunResult,
)
from app.core.adapters.transport_factory import build_engine_adapter
from app.models.runs import PredictDiagnosticExport
from app.services.diagnostic_export import export_predict_diagnostics
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

        try:
            result = adapter.predict_artifact(
                {
                    "artifact_ref": _public_artifact_ref(art_ref),
                    "mock_llm": mock_param,
                    "current_hashes": current_hashes,
                    "inputs": input_data or {},
                    "workspace_dir": str(workspace_dir_for(skill_dir)),
                    "execution_context": {"runtime_config": runtime_config},
                }
            )
        except StudioAdapterError as exc:
            if exc.error_code == "engine.predict_deadlock":
                raise PredictDeadlockError(exc.error_payload["phase_name"], exc.error_payload["actual_path"]) from exc
            raise exc

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
        self._persist_predict_result(
            skill_dir,
            result.run_id,
            result,
            content_hash=art_ref["content_hash"],
            artifact_ref=art_ref,
            runtime_config=runtime_config,
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
        content_hash: str,
        artifact_ref: dict[str, Any],
        runtime_config: dict[str, Any],
    ) -> None:
        workspace_dir = workspace_dir_for(skill_dir)
        from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

        store = LocalRunArtifactStore(root=workspace_dir)
        store.begin_run(run_id, metadata=_artifact_store_metadata("predict", artifact_ref))
        store.put_batch(run_id, {"result.json": result.model_dump_json().encode("utf-8")})
        store.seal_run(run_id)

        run_dir = workspace_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        write_runtime_snapshot(run_dir, runtime_config)
        (run_dir / "result.json").write_text(
            result.model_dump_json(),
            encoding="utf-8",
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

__all__ = [
    "MAX_PHASE_REVISITS",
    "PredictArtifactError",
    "PredictDeadlockError",
    "PredictorService",
    "predictor_service",
]
