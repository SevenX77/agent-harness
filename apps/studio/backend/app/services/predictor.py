"""Predict V2 in-process orchestration service."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from graph_agent import RunResult, predict_skill
from graph_agent.core.loader import SkillLoader

from app.models.runs import PredictDiagnosticExport
from app.services.diagnostic_export import export_predict_diagnostics
from app.services.gateway_resolver import build_gateway_model_resolver
from app.services.skill_resolver import build_studio_skill_resolver
from app.services.skills import ensure_workspace_skill_dir, workspace_dir_for

logger = logging.getLogger(__name__)

MAX_PHASE_REVISITS = 10


class PredictDeadlockError(RuntimeError):
    """Raised when P2 heuristic stubs appear to trap routing in a loop."""

    def __init__(self, phase_name: str, actual_path: list[str]) -> None:
        self.phase_name = phase_name
        self.actual_path = actual_path
        super().__init__(
            f"Predict P2 deadlock guard tripped for phase '{phase_name}' "
            f"after {actual_path.count(phase_name)} visits"
        )


class PredictorService:
    """Studio Backend orchestration layer for Predict V2 runs."""

    def __init__(self, run_skill_fn: Any = None) -> None:
        self._run_skill = run_skill_fn

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

        if self._run_skill is not None:
            raw_result = self._run_skill(
                skill_dir,
                workspace_dir=workspace_dir_for(skill_dir),
                mock_llm=mock_param,
                current_hashes=current_hashes,
                model_resolver=build_gateway_model_resolver(),
                skill_resolver=build_studio_skill_resolver(),
                unattended=True,
                **(input_data or {}),
            )
            result: RunResult
            if isinstance(raw_result, dict):
                from graph_agent.core.result import PathDiff, PhaseRecord, WorkflowMetrics, WorkflowResult
                context = raw_result.get("context", raw_result)
                if not isinstance(context, dict):
                    context = {}
                raw_phases = context.get("predict_trace") or context.get("phases") or []
                phases_list = []
                for item in raw_phases:
                    if isinstance(item, dict):
                        phases_list.append(PhaseRecord(
                            phase_name=item.get("phase_name", ""),
                            type=item.get("type", "logic"),
                            inputs=item.get("inputs", {}),
                            outputs=item.get("outputs", {}),
                            mocked_source=item.get("mocked_source"),
                        ))

                path_diff = None
                actual_path = [str(i) for i in context.get("actual_path", [])]
                expected_path = getattr(mock_param, "expected_path", None) if mock_param else None
                if expected_path:
                    from graph_agent.core._predict_internal.path_diff import compute_diff
                    rd = compute_diff([str(item) for item in expected_path], actual_path)
                    path_diff = PathDiff(
                        expected_path=rd.expected_path,
                        actual_path=rd.actual_path,
                        missing=rd.missing,
                        extra=rd.extra,
                        order_mismatch=rd.order_mismatch,
                    )

                result = WorkflowResult(
                    success=True,
                    run_id=raw_result.get("run_id") or "predict-workspace-run",
                    skill_id=skill_id,
                    context=context,
                    metrics=WorkflowMetrics(),
                    source="predict",
                    phases=phases_list,
                    path_diff=path_diff,
                )
            else:
                result = raw_result

            self._persist_predict_result(skill_dir, result.run_id, result)
            return result

        # 直接调用 SDK 的 predict_skill
        from graph_agent.core.runner import PredictDeadlockError as SDKPredictDeadlockError
        try:
            result = predict_skill(
                skill_dir,
                workspace_dir=workspace_dir_for(skill_dir),
                mock_llm=mock_param,
                current_hashes=current_hashes,
                model_resolver=build_gateway_model_resolver(),
                skill_resolver=build_studio_skill_resolver(),
                unattended=True,
                **(input_data or {}),
            )
        except SDKPredictDeadlockError as exc:
            raise PredictDeadlockError(exc.phase_name, exc.actual_path) from exc

        self._persist_predict_result(skill_dir, result.run_id, result)
        return result

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


def _fallback_trace_from_skill(skill_dir: Path, raw_result: Any) -> list[dict[str, Any]]:
    del raw_result
    try:
        compiled = SkillLoader().compile_skill(
            skill_dir,
            skill_resolver=build_studio_skill_resolver(),
        )
    except Exception:
        return []
    mode_by_phase = {node.phase_name: node.mode for node in compiled.nodes}
    return [
        {
            "phase_name": phase_name,
            "type": "llm" if mode_by_phase.get(phase_name) == "agent" else "logic",
            "inputs": {},
            "outputs": {},
        }
        for phase_name in compiled.manifest.phases
    ]


predictor_service = PredictorService()

__all__ = [
    "MAX_PHASE_REVISITS",
    "PredictDeadlockError",
    "PredictorService",
    "predictor_service",
]
