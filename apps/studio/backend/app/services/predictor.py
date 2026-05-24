"""Predict V2 in-process orchestration service."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from graph_agent import run_skill
from graph_agent.core._predict_internal.exporter import assemble_phase_record
from graph_agent.core._predict_internal.models import (
    GoldenCase,
    PathDiff,
    PhaseRecord,
    PredictResult,
)
from graph_agent.core._predict_internal.path_diff import compute_diff
from graph_agent.core._predict_internal.strategy import (
    BaseMockStrategy,
    GoldenCaseStrategy,
    HeuristicStubStrategy,
    MockStrategy,
)
from graph_agent.core._predict_internal.tracing import PredictTracingCallback
from graph_agent.core.loader import SkillLoader

from app.models.runs import PredictDiagnosticExport
from app.services.diagnostic_export import export_predict_diagnostics
from app.services.skill_resolver import studio_skill_resolver_from_config
from app.services.skills import ensure_workspace_skill_dir, predict_dir_for

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

    def __init__(self, run_skill_fn: Callable[..., Any] = run_skill) -> None:
        self._run_skill = run_skill_fn

    def dispatch_predict_job(
        self,
        skill_id: str,
        mock_param: Any = None,
        *,
        input_data: dict[str, Any] | None = None,
        current_hashes: dict[str, dict[str, str]] | None = None,
    ) -> PredictResult:
        """Resolve strategy, run graph_agent in Predict mode, and assemble result."""
        strategy = self.resolve_fill_strategy(mock_param)
        skill_dir = ensure_workspace_skill_dir(skill_id)
        self._warn_on_stale_golden_hashes(strategy, current_hashes or {})
        tracing_callback = PredictTracingCallback()
        tracing_callback.on_chain_start(metadata={})

        raw_result = self._run_skill(
            skill_dir,
            mock_llm=mock_param,
            unattended=True,
            callbacks=[tracing_callback],
            skill_resolver=studio_skill_resolver_from_config(),
            **(input_data or {}),
        )
        trace_phases = tracing_callback.phases or _fallback_trace_from_skill(skill_dir, raw_result)
        raw_result = _attach_predict_trace(raw_result, trace_phases)
        actual_path = _actual_path_from_raw(raw_result)
        if _is_p2_strategy(strategy):
            self._raise_if_deadlocked(actual_path)

        path_diff = self._path_diff_for_strategy(strategy, actual_path)
        result = self.assemble_trace(raw_result, path_diff)
        self._persist_predict_result(skill_dir, result)
        return result

    def resolve_fill_strategy(self, mock_param: Any) -> BaseMockStrategy:
        """Convert polymorphic mock input into an internal strategy object."""
        return MockStrategy.from_param(mock_param)

    def assemble_trace(
        self,
        raw_result: Any,
        path_diff: PathDiff | None = None,
    ) -> PredictResult:
        """Convert raw graph result into PredictResult."""
        phases = _phase_records_from_raw(raw_result)
        status: Literal["success", "failed"] = "success"
        if path_diff and (path_diff.missing or path_diff.extra or path_diff.order_mismatch):
            status = "failed"
        return PredictResult(status=status, phases=phases, path_diff=path_diff)

    def export_diagnostics(self, result: PredictResult) -> PredictDiagnosticExport:
        """Expose PredictResult through the Studio in-process diagnostic contract."""

        return export_predict_diagnostics(result)

    def _persist_predict_result(self, skill_dir: Path, result: PredictResult) -> None:
        predict_root = predict_dir_for(skill_dir)
        predict_root.mkdir(parents=True, exist_ok=True)
        (predict_root / "latest_predict.json").write_text(
            result.model_dump_json(),
            encoding="utf-8",
        )

    def _path_diff_for_strategy(
        self,
        strategy: BaseMockStrategy,
        actual_path: list[str],
    ) -> PathDiff | None:
        expected_path = getattr(strategy, "expected_path", None)
        if not expected_path:
            return None
        return compute_diff([str(item) for item in expected_path], actual_path)

    def _raise_if_deadlocked(self, actual_path: list[str]) -> None:
        counts = Counter(actual_path)
        for phase_name, count in counts.items():
            if count > MAX_PHASE_REVISITS:
                raise PredictDeadlockError(phase_name, actual_path)

    def _warn_on_stale_golden_hashes(
        self,
        strategy: BaseMockStrategy,
        current_hashes: dict[str, dict[str, str]],
    ) -> None:
        golden_cases = _golden_cases_for_strategy(strategy)
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


def _is_p2_strategy(strategy: BaseMockStrategy) -> bool:
    return type(strategy) is HeuristicStubStrategy


def _golden_cases_for_strategy(strategy: BaseMockStrategy) -> list[GoldenCase]:
    if isinstance(strategy, GoldenCaseStrategy):
        return [strategy.golden_case]
    raw_cases = getattr(strategy, "golden_cases", None)
    if isinstance(raw_cases, list):
        return [case for case in raw_cases if isinstance(case, GoldenCase)]
    return []


def _phase_records_from_raw(raw_result: Any) -> list[PhaseRecord]:
    context = _context_from_raw(raw_result)
    raw_phases = context.get("predict_trace") or context.get("phases") or []
    if not isinstance(raw_phases, list):
        return []

    phases: list[PhaseRecord] = []
    for item in raw_phases:
        if not isinstance(item, dict):
            continue
        phases.append(assemble_phase_record(item))
    return phases


def _actual_path_from_raw(raw_result: Any) -> list[str]:
    context = _context_from_raw(raw_result)
    raw_path = context.get("actual_path")
    if isinstance(raw_path, list):
        return [str(item) for item in raw_path]
    phases = _phase_records_from_raw(raw_result)
    return [phase.phase_name for phase in phases]


def _attach_predict_trace(raw_result: Any, trace_phases: list[dict[str, Any]]) -> Any:
    if not trace_phases:
        return raw_result
    if isinstance(raw_result, dict):
        context = raw_result.get("context", raw_result)
        if isinstance(context, dict):
            context.setdefault("predict_trace", trace_phases)
        return raw_result
    context = getattr(raw_result, "context", None)
    if isinstance(context, dict):
        context.setdefault("predict_trace", trace_phases)
    return raw_result


def _fallback_trace_from_skill(skill_dir: Path, raw_result: Any) -> list[dict[str, Any]]:
    del raw_result
    try:
        compiled = SkillLoader().compile_skill(
            skill_dir,
            skill_resolver=studio_skill_resolver_from_config(),
        )
    except Exception:
        return []
    mode_by_phase = {node.phase_name: node.mode for node in compiled.nodes}
    return [
        {
            "phase_name": phase.id,
            "type": "llm" if mode_by_phase.get(phase.id) == "skill" else "logic",
            "inputs": {},
            "outputs": {},
        }
        for phase in compiled.manifest.phases
    ]


def _context_from_raw(raw_result: Any) -> dict[str, Any]:
    if isinstance(raw_result, dict):
        context = raw_result.get("context", raw_result)
    else:
        context = getattr(raw_result, "context", {})
    return context if isinstance(context, dict) else {}


predictor_service = PredictorService()

__all__ = [
    "MAX_PHASE_REVISITS",
    "PredictDeadlockError",
    "PredictorService",
    "predictor_service",
]
