"""Predict V2 in-process orchestration service."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from app.core.adapters.engine import (
    RunResult,
)
from app.models.runs import PredictDiagnosticExport
from app.services.diagnostic_export import export_predict_diagnostics
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

        from app.core.adapters.engine import EngineAdapter

        adapter = EngineAdapter(transport="in_process")

        art_ref = adapter.compile(
            {
                "skill_dir": str(skill_dir),
                "skill_id": skill_id,
                "artifact_scope": "ephemeral",
            }
        )

        # Route through EngineAdapter predict_artifact
        from app.core.adapters.http_transport import StudioAdapterError

        try:
            result = adapter.predict_artifact(
                {
                    "artifact_ref": {
                        "artifact_id": art_ref["artifact_id"],
                        "content_hash": art_ref["content_hash"],
                        "store": art_ref["store"],
                        "manifest_ref": art_ref["manifest_ref"],
                    },
                    "mock_llm": mock_param,
                    "current_hashes": current_hashes,
                    "inputs": input_data or {},
                    "workspace_dir": str(workspace_dir_for(skill_dir)),
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
        self._persist_predict_result(skill_dir, result.run_id, result)
        return cast(RunResult, result)

    def export_diagnostics(self, result: RunResult) -> PredictDiagnosticExport:
        """Expose PredictResult through the Studio in-process diagnostic contract."""
        return export_predict_diagnostics(result)

    def _persist_predict_result(self, skill_dir: Path, run_id: str, result: RunResult) -> None:
        run_dir = workspace_dir_for(skill_dir) / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "result.json").write_text(
            result.model_dump_json(),
            encoding="utf-8",
        )
        if result.success:
            # Persist predict-pass server-side so the run-spawn path can enforce the
            # MVP1 "predict-pass unlocks Run" prerequisite for any caller, not just the UI.
            from app.services.predict_gate import record_predict_pass

            record_predict_pass(skill_dir, result.skill_id, run_id)
        else:
            logger.info(
                "predictor predict_pass=not_recorded skill_id=%s run_id=%s reason=predict_failed",
                result.skill_id,
                run_id,
            )


def _fallback_trace_from_skill(skill_dir: Path, raw_result: Any) -> list[dict[str, Any]]:
    del raw_result
    from app.core.adapters.engine import EngineAdapter

    adapter = EngineAdapter(transport="in_process")
    try:
        return adapter.get_fallback_trace(str(skill_dir))
    except Exception:
        return []


predictor_service = PredictorService()

__all__ = [
    "MAX_PHASE_REVISITS",
    "PredictArtifactError",
    "PredictDeadlockError",
    "PredictorService",
    "predictor_service",
]
