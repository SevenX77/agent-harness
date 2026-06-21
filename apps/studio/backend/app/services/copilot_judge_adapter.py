"""Copilot-to-golden evaluation boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, NoReturn

from app.core.exceptions import error_response, raise_error_response
from app.models.golden import CopilotJudgeDiffSummary, CopilotJudgeResponse
from app.services.golden_headless import (
    evaluate_golden_headless,
    golden_headless_request_from_ref,
    persist_compare_result_for_golden,
)
from app.services.skills import resolve_skill_dir, validate_run_id_segment


@dataclass(frozen=True)
class CopilotJudgeRefs:
    run_results_ref: str
    baseline_ref: str
    run_id: str
    baseline_id: str


class CopilotJudgeAdapter:
    """Prepare immutable golden comparison facts for Copilot commentary."""

    def prepare(
        self,
        skill_id: str,
        *,
        run_results_ref: str,
        baseline_ref: str | None = None,
        against: str | None = None,
    ) -> CopilotJudgeResponse:
        refs = validate_copilot_judge_refs(skill_id, run_results_ref, baseline_ref, against)
        compare_result = evaluate_golden_headless(
            golden_headless_request_from_ref(refs.run_results_ref, refs.baseline_ref)
        )
        diff_summary = CopilotJudgeDiffSummary(
            baseline_id=compare_result.baseline_id,
            run_results_ref=compare_result.run_results_ref,
            total_score=compare_result.total_score,
            node_group_count=len(compare_result.node_groups),
            failed_node_count=sum(1 for group in compare_result.node_groups if group.status == "fail"),
        )
        compare_result_ref = persist_compare_result_for_golden(skill_id, compare_result)
        judge_context_ref = self._write_judge_context(
            skill_id=skill_id,
            refs=refs,
            compare_result_ref=compare_result_ref,
            diff_summary=diff_summary.model_dump(mode="json"),
        )
        return CopilotJudgeResponse(
            compare_result_ref=compare_result_ref,
            judge_context_ref=judge_context_ref,
            baseline_ref=refs.baseline_ref,
            diff_summary=diff_summary,
        )

    def _write_judge_context(
        self,
        *,
        skill_id: str,
        refs: CopilotJudgeRefs,
        compare_result_ref: str,
        diff_summary: dict[str, Any],
    ) -> str:
        judge_dir = (
            resolve_skill_dir(skill_id)
            / ".workspace"
            / "runs"
            / refs.run_id
            / "copilot_judge"
            / refs.baseline_id
        )
        judge_dir.mkdir(parents=True, exist_ok=True)
        judge_context_ref = f"{skill_id}/runs/{refs.run_id}/copilot_judge/{refs.baseline_id}/judge_context.json"
        (judge_dir / "judge_context.json").write_text(
            json.dumps(
                {
                    "skill_id": skill_id,
                    "run_results_ref": refs.run_results_ref,
                    "baseline_ref": refs.baseline_ref,
                    "compare_result_ref": compare_result_ref,
                    "diff_summary": diff_summary,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return judge_context_ref


def validate_copilot_judge_refs(
    skill_id: str,
    run_results_ref: str,
    baseline_ref: str | None,
    against: str | None = None,
) -> CopilotJudgeRefs:
    run_parts = _ref_parts(run_results_ref)
    if (
        run_parts is None
        or len(run_parts) != 4
        or run_parts[0] != skill_id
        or run_parts[1] != "runs"
        or run_parts[3] != "result.json"
    ):
        _raise_invalid_judge_ref("run_results_ref", run_results_ref, skill_id)
    run_id = run_parts[2]

    baseline_parts = _ref_parts(baseline_ref) if baseline_ref is not None else None
    if baseline_ref is not None and baseline_parts is not None and (
        len(baseline_parts) == 4
        and baseline_parts[0] == skill_id
        and baseline_parts[1] == "golden"
        and baseline_parts[3] == "baseline.json"
    ):
        baseline_id = baseline_parts[2]
        normalized_baseline_ref = baseline_ref
    elif baseline_ref is not None and baseline_parts is not None and (
        len(baseline_parts) == 4
        and baseline_parts[0] == ".workspace"
        and baseline_parts[1] == "golden"
        and baseline_parts[3] == "baseline.json"
    ):
        baseline_id = baseline_parts[2]
        normalized_baseline_ref = f"{skill_id}/golden/{baseline_id}/baseline.json"
    elif baseline_ref is None and against is not None:
        try:
            baseline_id = validate_run_id_segment(against)
        except Exception:
            _raise_invalid_judge_ref("against", against, skill_id)
        normalized_baseline_ref = f"{skill_id}/golden/{baseline_id}/baseline.json"
    else:
        _raise_invalid_judge_ref("baseline_ref", baseline_ref or "", skill_id)

    return CopilotJudgeRefs(
        run_results_ref=run_results_ref,
        baseline_ref=normalized_baseline_ref,
        run_id=run_id,
        baseline_id=baseline_id,
    )


def raise_missing_judge_ref(ref_kind: str, skill_id: str) -> NoReturn:
    raise_error_response(
        error_response(
            error_code="copilot.judge_ref_missing",
            http_status=422,
            message=f"Missing Copilot Judge {ref_kind}",
            details={
                "ref_kind": ref_kind,
                "expected_skill_id": skill_id,
            },
            retry_strategy="not_retryable",
        )
    )


def _ref_parts(ref: str) -> tuple[str, ...] | None:
    if not ref or "\\" in ref:
        return None
    path = PurePosixPath(ref)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.parts


def _raise_invalid_judge_ref(ref_kind: str, ref: str, skill_id: str) -> NoReturn:
    raise_error_response(
        error_response(
            error_code="copilot.judge_ref_invalid",
            http_status=422,
            message=f"Invalid Copilot Judge {ref_kind}",
            details={
                "ref_kind": ref_kind,
                "ref": ref,
                "expected_skill_id": skill_id,
            },
            retry_strategy="not_retryable",
        )
    )
