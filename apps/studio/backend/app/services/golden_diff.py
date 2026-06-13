from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.exceptions import standard_http_exception
from app.models.compare import CompareResult
from app.models.golden import GoldenBaseline
from app.services.diagnostic_export import assert_trace_can_be_promoted_to_golden
from app.services.golden_headless import (  # noqa: F401
    GoldenHeadlessRequest,
    GoldenHeadlessResult,
    evaluate_golden_headless,
    resolve_existing_run_result_file,
)
from app.services.skills import golden_dir_for, resolve_skill_dir, run_dir_for


def list_golden_baselines_for_skill(skill_id: str) -> list[GoldenBaseline]:
    """Return all persisted golden baselines for a skill."""
    golden_root = _golden_root_for(skill_id)
    if not golden_root.exists():
        return []

    baselines: list[GoldenBaseline] = []
    for metadata_path in golden_root.glob("*/golden_metadata.json"):
        try:
            baselines.append(GoldenBaseline.model_validate_json(metadata_path.read_text()))
        except Exception:
            continue
    return sorted(baselines, key=lambda item: item.created_at, reverse=True)


def set_golden_baseline_for_run(skill_id: str, run_id: str, *, lock: bool) -> GoldenBaseline:
    """Copy one run's final state into the skill golden baseline store."""
    source_path = resolve_existing_run_result_file(run_dir_for(skill_id, run_id))
    if not source_path.exists():
        raise standard_http_exception(
            "RESUME_CHECKPOINT_NOT_FOUND",
            f"Run final state not found: {run_id}",
            {"skill_id": skill_id, "run_id": run_id},
        )
    assert_trace_can_be_promoted_to_golden(
        _read_json(source_path),
        skill_id=skill_id,
        run_id=run_id,
    )

    baseline_dir = _golden_dir_for(skill_id, run_id)
    baseline_dir.mkdir(parents=True, exist_ok=True)
    content_path = baseline_dir / "result.json"
    shutil.copyfile(source_path, content_path)

    baseline = GoldenBaseline(
        id=run_id,
        linked_input_id=run_id,
        created_at=datetime.now(UTC),
        locked=lock,
        content_path=str(content_path),
    )
    (baseline_dir / "golden_metadata.json").write_text(
        baseline.model_dump_json(),
        encoding="utf-8",
    )
    return baseline


def delete_golden_baseline_for_skill(skill_id: str, golden_id: str) -> None:
    if Path(golden_id).name != golden_id or golden_id in {"", ".", ".."}:
        raise standard_http_exception(
            "RESUME_CHECKPOINT_NOT_FOUND",
            f"Golden baseline not found: {golden_id}",
            {"skill_id": skill_id, "golden_id": golden_id},
        )
    baseline_dir = _golden_dir_for(skill_id, golden_id)
    if not baseline_dir.exists():
        raise standard_http_exception(
            "RESUME_CHECKPOINT_NOT_FOUND",
            f"Golden baseline not found: {golden_id}",
            {"skill_id": skill_id, "golden_id": golden_id},
        )
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
        raise standard_http_exception(
            "RESUME_CHECKPOINT_NOT_FOUND",
            f"Golden baseline not found for skill: {skill_id}",
            {"skill_id": skill_id},
        )

    # Use GoldenHeadlessRequest contract
    req = GoldenHeadlessRequest(
        run_results_ref=f"{skill_id}/runs/{run_id}/result.json",
        baseline_ref=f"{skill_id}/golden/{golden_run_id}/result.json",
    )
    result = evaluate_golden_headless(req)

    return CompareResult(
        differences=result.differences,
        total_score=result.total_score,
        golden_run_id=golden_run_id,
        node_results=result.node_results,
    )


def _golden_root_for(skill_id: str) -> Path:
    return golden_dir_for(resolve_skill_dir(skill_id))


def _golden_dir_for(skill_id: str, run_id: str) -> Path:
    return _golden_root_for(skill_id) / run_id


def _latest_golden_run_id(skill_id: str) -> str | None:
    baselines = list_golden_baselines_for_skill(skill_id)
    return baselines[0].id if baselines else None


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
