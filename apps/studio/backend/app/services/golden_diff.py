from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Any, Protocol

from app.core.exceptions import error_response, raise_error_response
from app.models.compare import CompareResult
from app.models.golden import (
    GoldenBaseline,
    GoldenBaselineCase,
    GoldenBaselineFile,
    GoldenBaselinePlan,
    SetManualGoldenReq,
)
from app.services.diagnostic_export import assert_trace_can_be_promoted_to_golden
from app.services.golden_headless import (  # noqa: F401
    GoldenHeadlessRequest,
    GoldenHeadlessResult,
    evaluate_golden_headless,
    golden_headless_request_from_ref,
    read_run_result_payload_for_golden,
    read_run_result_snapshot_for_golden,
)
from app.services.skills import golden_dir_for, resolve_skill_dir, validate_run_id_segment

BASELINE_FILENAME = "baseline.json"
REPORT_FILENAME = "report.json"
CASES_DIRNAME = "cases"


# codeql[py/path-injection] skill_id is validated by resolve_skill_dir before golden_root is used for filesystem access.
def list_golden_baselines_for_skill(skill_id: str) -> list[GoldenBaseline]:
    """Return all persisted golden baselines for a skill."""
    golden_root = _golden_root_for(skill_id)
    # codeql[py/path-injection] golden_root comes from resolve_skill_dir, which validates skill_id as a path segment.
    if not golden_root.exists():
        return []

    baselines: list[GoldenBaseline] = []
    # codeql[py/path-injection] golden_root is the validated skill workspace golden directory.
    for baseline_path in golden_root.glob(f"*/{BASELINE_FILENAME}"):
        try:
            baselines.append(_baseline_for_baseline_path(baseline_path.parent.name, baseline_path))
        except Exception:
            continue
    return sorted(baselines, key=lambda item: item.created_at, reverse=True)


def set_golden_baseline_for_run(
    skill_id: str,
    run_id: str,
    *,
    lock: bool,
    node_id: str | None = None,
) -> GoldenBaseline:
    """Promote sealed run output into per-node golden cases.

    With ``node_id`` only that agent node's case is (re)written; sibling nodes'
    golden cases stay on disk untouched (F6: a valid golden is not auto-overwritten
    by writing a different node).
    """
    plan = plan_golden_baseline_for_run(skill_id, run_id, lock=lock, node_id=node_id)
    baseline_dir = _golden_dir_for(skill_id, run_id)
    baseline_dir.mkdir(parents=True, exist_ok=True)
    for file in plan.files:
        relative = _relative_workspace_golden_path(run_id, file.path)
        target = baseline_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file.content, encoding="utf-8")
    return plan.baseline


def plan_manual_golden_for_node(
    skill_id: str,
    node_id: str,
    expected_output: dict[str, Any],
) -> GoldenBaselinePlan:
    """Build the author-defined golden payload for the native-fs writer (no persistence).

    Parity with ``plan_golden_baseline_for_run``: it returns the same
    ``GoldenBaselinePlan`` shape (a ``baseline`` DTO + the ordered ``files`` to write —
    ``baseline.json``/``report.json``/``cases/{case_id}.json``) so the Rust sole writer
    can write each file on desktop. This is run-less: it does NOT read a sealed-run
    snapshot and does NOT go through the predict-trace promote guard (a manual golden
    has no source run; the expected output is author-defined).

    This is the single source of file-content construction: the ``/golden/manual/plan``
    endpoint returns this plan for the Rust native-fs sole writer (the desktop write path),
    and the internal/test helper ``set_manual_golden_for_node`` writes exactly these files.
    """
    case_id = validate_run_id_segment(node_id)
    baseline_dir = _golden_dir_for(skill_id, node_id)
    created_at = datetime.now(UTC)

    case_record = {
        "case_id": case_id,
        "node_id": node_id,
        "phase_id": node_id,
        "expected_output_ref": f"{CASES_DIRNAME}/{case_id}.json",
    }
    baseline_payload = {
        "baseline_id": node_id,
        "source_run_id": None,
        "source": "manual",
        "locked": False,
        "cases": [case_record],
    }
    report_payload = {
        "baseline_id": node_id,
        "source_run_id": None,
        "source": "manual",
        "case_count": 1,
        "node_ids": [node_id],
        "created_at": created_at.isoformat(),
    }
    case_payload = {
        "case_id": case_id,
        "node_id": node_id,
        "phase_id": node_id,
        "expected_output": expected_output,
    }

    baseline = GoldenBaseline(
        id=node_id,
        source_run_id=None,
        source_run_results_ref=None,
        baseline_ref=_workspace_golden_path(node_id, BASELINE_FILENAME),
        linked_input_id=node_id,
        created_at=created_at,
        locked=False,
        content_path=str(baseline_dir / BASELINE_FILENAME),
        cases=[_case_record_to_model(case_record)],
    )
    return GoldenBaselinePlan(
        baseline=baseline,
        files=[
            GoldenBaselineFile(
                path=_workspace_golden_path(node_id, BASELINE_FILENAME),
                content=json.dumps(baseline_payload, ensure_ascii=False, sort_keys=True),
            ),
            GoldenBaselineFile(
                path=_workspace_golden_path(node_id, REPORT_FILENAME),
                content=json.dumps(report_payload, ensure_ascii=False, sort_keys=True),
            ),
            GoldenBaselineFile(
                path=_workspace_golden_path(node_id, f"{CASES_DIRNAME}/{case_id}.json"),
                content=json.dumps(case_payload, ensure_ascii=False, sort_keys=True),
            ),
        ],
    )


def set_manual_golden_for_node(skill_id: str, request: SetManualGoldenReq) -> GoldenBaseline:
    """Persist an author-defined golden for one agent node (N4 atom #33 manual write).

    Internal/test helper only (NOT exposed as an HTTP write endpoint): it builds the plan
    via ``plan_manual_golden_for_node`` (the single source of file content) and writes each
    plan file to disk through the Python ``Path`` writer. In the product, the frontend writes
    the same files through the Rust native-fs sole writer (D12) — it calls ``/golden/manual/plan``
    and lets the Rust writer perform the write; web degrades to Desktop-only (no persist).
    This helper exists so service-level tests can assert the on-disk result equals the plan.
    The baseline is keyed by ``node_id`` so the canvas/properties badge flips to 🟢
    has-golden via the same ``cases`` projection used by run-promoted goldens.
    """
    node_id = request.node_id
    plan = plan_manual_golden_for_node(skill_id, node_id, request.expected_output)
    baseline_dir = _golden_dir_for(skill_id, node_id)
    baseline_dir.mkdir(parents=True, exist_ok=True)
    for file in plan.files:
        relative = _relative_workspace_golden_path(node_id, file.path)
        target = baseline_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file.content, encoding="utf-8")
    return plan.baseline


def plan_golden_baseline_for_run(
    skill_id: str,
    run_id: str,
    *,
    lock: bool,
    node_id: str | None = None,
) -> GoldenBaselinePlan:
    """Prepare a golden baseline payload for the native-fs writer without persisting it.

    With ``node_id`` the plan covers exactly that agent node (only its case file is
    emitted), while ``baseline.json``/``report.json`` merge in the sibling nodes'
    cases already on disk so a single-node write does not drop other golden cases.
    """
    source_run_results_ref, snapshot, node_outputs = read_run_result_snapshot_for_golden(skill_id, run_id)
    assert_trace_can_be_promoted_to_golden(
        snapshot.model_dump(mode="json"),
        skill_id=skill_id,
        run_id=run_id,
    )

    target_node_ids = _select_target_node_ids(snapshot, node_outputs, node_id=node_id)
    case_files = [_build_case_file(run_id, target_id, node_outputs[target_id]) for target_id in target_node_ids]
    case_records = _merge_case_records(skill_id, run_id, target_node_ids)

    baseline_dir = _golden_dir_for(skill_id, run_id)
    baseline_payload = {
        "baseline_id": run_id,
        "source_run_id": run_id,
        "source_run_results_ref": source_run_results_ref,
        "locked": lock,
        "cases": case_records,
    }
    report_payload = {
        "baseline_id": run_id,
        "source_run_id": run_id,
        "source_run_results_ref": source_run_results_ref,
        "case_count": len(case_records),
        "node_ids": [record["node_id"] for record in case_records],
        "created_at": datetime.now(UTC).isoformat(),
    }
    baseline = GoldenBaseline(
        id=run_id,
        source_run_id=run_id,
        source_run_results_ref=source_run_results_ref,
        baseline_ref=_workspace_golden_path(run_id, BASELINE_FILENAME),
        linked_input_id=run_id,
        created_at=datetime.now(UTC),
        locked=lock,
        content_path=str(baseline_dir / BASELINE_FILENAME),
        cases=[_case_record_to_model(record) for record in case_records],
    )
    return GoldenBaselinePlan(
        baseline=baseline,
        files=[
            GoldenBaselineFile(
                path=_workspace_golden_path(run_id, BASELINE_FILENAME),
                content=json.dumps(baseline_payload, ensure_ascii=False, sort_keys=True),
            ),
            GoldenBaselineFile(
                path=_workspace_golden_path(run_id, REPORT_FILENAME),
                content=json.dumps(report_payload, ensure_ascii=False, sort_keys=True),
            ),
            *case_files,
        ],
    )


class _NodeResultRow(Protocol):
    @property
    def agent_node_id(self) -> str: ...


class _RunResultsRef(Protocol):
    @property
    def run_id(self) -> str: ...


class _SealedRunSnapshot(Protocol):
    """Structural view of the sealed-run snapshot this module consumes.

    Avoids importing the engine SDK concrete ``RunResultSnapshot`` into the
    Studio business layer (forbidden by the SDK-import boundary guard); the
    snapshot enters through the ``golden_headless`` port and is read structurally.
    Read-only properties so the concrete SDK types match covariantly.
    """

    @property
    def node_results(self) -> Sequence[_NodeResultRow]: ...

    @property
    def run_results_ref(self) -> _RunResultsRef: ...


def _select_target_node_ids(
    snapshot: _SealedRunSnapshot,
    node_outputs: dict[str, Any],
    *,
    node_id: str | None,
) -> list[str]:
    """Resolve which sealed-run nodes this promote covers (one node, or all)."""
    ordered_node_ids = [node.agent_node_id for node in snapshot.node_results if node.agent_node_id in node_outputs]
    if node_id is None:
        return ordered_node_ids
    if node_id not in node_outputs:
        raise_error_response(
            error_response(
                error_code="golden.node_not_in_run",
                http_status=422,
                message=f"Agent node is not present in the sealed run: {node_id}",
                details={
                    "node_id": node_id,
                    "run_id": snapshot.run_results_ref.run_id,
                    "available_node_ids": ordered_node_ids,
                },
                retry_strategy="not_retryable",
            )
        )
    return [node_id]


def _build_case_file(run_id: str, node_id: str, expected_output: Any) -> GoldenBaselineFile:
    case_id = validate_run_id_segment(node_id)
    case_relative_ref = f"{CASES_DIRNAME}/{case_id}.json"
    return GoldenBaselineFile(
        path=_workspace_golden_path(run_id, case_relative_ref),
        content=json.dumps(
            {
                "case_id": case_id,
                "node_id": node_id,
                "phase_id": node_id,
                "expected_output": expected_output,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )


def _case_record(node_id: str) -> dict[str, str]:
    case_id = validate_run_id_segment(node_id)
    return {
        "case_id": case_id,
        "node_id": node_id,
        "phase_id": node_id,
        "expected_output_ref": f"{CASES_DIRNAME}/{case_id}.json",
    }


def _merge_case_records(skill_id: str, run_id: str, target_node_ids: list[str]) -> list[dict[str, str]]:
    """Union the freshly-written nodes with sibling cases already on disk.

    Order is stable: previously-persisted nodes keep their stored order (a target
    node already on disk is refreshed in place), and never-before-seen target nodes
    are appended in run order. This keeps run-faithful node ordering for the diff.
    """
    ordered_node_ids: list[str] = []
    merged: dict[str, dict[str, str]] = {}
    for record in _read_persisted_case_records(skill_id, run_id):
        node = record.get("node_id")
        if isinstance(node, str) and node and node not in merged:
            merged[node] = record
            ordered_node_ids.append(node)
    for node_id in target_node_ids:
        if node_id not in merged:
            ordered_node_ids.append(node_id)
        merged[node_id] = _case_record(node_id)
    return [merged[node_id] for node_id in ordered_node_ids]


def _read_persisted_case_records(skill_id: str, run_id: str) -> list[dict[str, Any]]:
    baseline_path = _golden_dir_for(skill_id, run_id) / BASELINE_FILENAME
    # codeql[py/path-injection] baseline_path is confined to the skill golden root by _golden_dir_for.
    if not baseline_path.exists():
        return []
    payload = _read_json(baseline_path)
    if not isinstance(payload, dict):
        return []
    cases = payload.get("cases")
    if not isinstance(cases, list):
        return []
    return [case for case in cases if isinstance(case, dict)]


def _case_record_to_model(record: dict[str, str]) -> GoldenBaselineCase:
    node_id = record["node_id"]
    case_id = record.get("case_id") or node_id
    return GoldenBaselineCase(
        case_id=case_id,
        node_id=node_id,
        phase_id=record.get("phase_id") or node_id,
        expected_output_ref=record.get("expected_output_ref") or f"{CASES_DIRNAME}/{case_id}.json",
    )


def delete_golden_baseline_for_skill(skill_id: str, golden_id: str) -> None:
    baseline_dir = _golden_dir_for(skill_id, golden_id)
    # codeql[py/path-injection] baseline_dir is built from validate_run_id_segment via _golden_dir_for.
    if not baseline_dir.exists():
        raise_error_response(
            error_response(
                error_code="golden.baseline_not_found",
                http_status=404,
                message=f"Golden baseline not found: {golden_id}",
                details={"skill_id": skill_id, "golden_id": golden_id},
                retry_strategy="not_retryable",
            )
        )
    # codeql[py/path-injection] baseline_dir is confined to the skill golden root by _golden_dir_for.
    shutil.rmtree(baseline_dir)


def compare_run_to_golden(
    skill_id: str,
    run_id: str,
    *,
    against: str | None = None,
) -> CompareResult:
    """Compare a run's final state with a selected or latest golden baseline."""
    golden_run_id = against or _latest_golden_run_id(skill_id)
    if golden_run_id is None:
        raise_error_response(
            error_response(
                error_code="golden.baseline_not_found",
                http_status=404,
                message=f"Golden baseline not found for skill: {skill_id}",
                details={"skill_id": skill_id},
                retry_strategy="not_retryable",
            )
        )

    run_results_ref, _result_content = read_run_result_payload_for_golden(skill_id, run_id)
    req = golden_headless_request_from_ref(
        run_results_ref,
        f"{skill_id}/golden/{golden_run_id}/{BASELINE_FILENAME}",
    )
    result = evaluate_golden_headless(req)

    return CompareResult(
        baseline_id=result.baseline_id,
        source_run_id=result.source_run_id,
        source_run_results_ref=result.source_run_results_ref,
        baseline_ref=result.baseline_ref,
        run_results_ref=result.run_results_ref,
        total_score=result.total_score,
        node_groups=result.node_groups,
    )


def _golden_root_for(skill_id: str) -> Path:
    return golden_dir_for(resolve_skill_dir(skill_id))


def _golden_dir_for(skill_id: str, run_id: str) -> Path:
    safe_run_id = validate_run_id_segment(run_id)
    return _golden_root_for(skill_id) / safe_run_id


def _workspace_golden_path(run_id: str, filename: str) -> str:
    safe_run_id = validate_run_id_segment(run_id)
    return f".workspace/golden/{safe_run_id}/{filename}"


def _relative_workspace_golden_path(run_id: str, path: str) -> Path:
    safe_run_id = validate_run_id_segment(run_id)
    prefix = PurePath(".workspace") / "golden" / safe_run_id
    target = PurePath(path)
    try:
        return Path(target.relative_to(prefix))
    except ValueError as exc:
        raise ValueError(f"Golden plan file escapes baseline directory: {path}") from exc


def _baseline_for_baseline_path(baseline_id: str, baseline_path: Path) -> GoldenBaseline:
    payload = _read_json(baseline_path)
    if not isinstance(payload, dict):
        payload = {}
    created_at = datetime.fromtimestamp(baseline_path.stat().st_mtime, UTC)
    source_run_id = payload.get("source_run_id")
    source_run_results_ref = payload.get("source_run_results_ref")
    locked = payload.get("locked")
    return GoldenBaseline(
        id=baseline_id,
        source_run_id=source_run_id if isinstance(source_run_id, str) else baseline_id,
        source_run_results_ref=source_run_results_ref if isinstance(source_run_results_ref, str) else None,
        baseline_ref=_workspace_golden_path(baseline_id, BASELINE_FILENAME),
        linked_input_id=baseline_id,
        created_at=created_at,
        locked=locked if isinstance(locked, bool) else False,
        content_path=str(baseline_path),
        cases=_cases_from_payload(payload),
    )


def _cases_from_payload(payload: dict[str, Any]) -> list[GoldenBaselineCase]:
    """Project the per-node cases stored in baseline.json into the API DTO."""
    cases = payload.get("cases")
    if not isinstance(cases, list):
        return []
    projected: list[GoldenBaselineCase] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        node_id = case.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            continue
        projected.append(_case_record_to_model(case))
    return projected


def _latest_golden_run_id(skill_id: str) -> str | None:
    baselines = list_golden_baselines_for_skill(skill_id)
    return baselines[0].id if baselines else None


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
