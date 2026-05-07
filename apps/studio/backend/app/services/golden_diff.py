"""Golden baseline persistence and run diffing."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.core.exceptions import standard_http_exception
from app.models.compare import CompareResult, FieldDifference, FieldDiffType
from app.models.golden import GoldenBaseline
from app.services.diagnostic_export import assert_trace_can_be_promoted_to_golden
from app.services.skills import run_dir_for


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
    source_path = run_dir_for(skill_id, run_id) / "final_state.json"
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
    content_path = baseline_dir / "final_state.json"
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


def compare_run_to_golden(
    skill_id: str,
    run_id: str,
    *,
    against: str | None = None,
) -> CompareResult:
    """Compare a run's final state with a selected or latest golden baseline."""
    current_path = run_dir_for(skill_id, run_id) / "final_state.json"
    if not current_path.exists():
        raise standard_http_exception(
            "RESUME_CHECKPOINT_NOT_FOUND",
            f"Run final state not found: {run_id}",
            {"skill_id": skill_id, "run_id": run_id},
        )

    golden_run_id = against or _latest_golden_run_id(skill_id)
    if golden_run_id is None:
        raise standard_http_exception(
            "RESUME_CHECKPOINT_NOT_FOUND",
            f"Golden baseline not found for skill: {skill_id}",
            {"skill_id": skill_id},
        )
    golden_path = _golden_dir_for(skill_id, golden_run_id) / "final_state.json"
    if not golden_path.exists():
        raise standard_http_exception(
            "RESUME_CHECKPOINT_NOT_FOUND",
            f"Golden baseline not found: {golden_run_id}",
            {"skill_id": skill_id, "golden_run_id": golden_run_id},
        )

    current = _read_json(current_path)
    golden = _read_json(golden_path)
    differences = _diff_value("output", current, golden, depth=0)
    total_score = (
        round(sum(item.score for item in differences) / len(differences) * 100, 2)
        if differences
        else 100.0
    )
    return CompareResult(
        differences=differences,
        total_score=total_score,
        golden_run_id=golden_run_id,
    )


def _golden_root_for(skill_id: str) -> Path:
    return run_dir_for(skill_id, "_").parent.parent / "golden"


def _golden_dir_for(skill_id: str, run_id: str) -> Path:
    return _golden_root_for(skill_id) / run_id


def _latest_golden_run_id(skill_id: str) -> str | None:
    baselines = list_golden_baselines_for_skill(skill_id)
    return baselines[0].id if baselines else None


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _diff_value(field_path: str, current: Any, golden: Any, *, depth: int) -> list[FieldDifference]:
    diff_type = _diff_type(current, golden)
    if diff_type == "dict" and depth < 5 and isinstance(current, dict) and isinstance(golden, dict):
        child_differences = [
            child
            for key in sorted(set(current) | set(golden))
            for child in _diff_value(
                f"{field_path}.{key}",
                current.get(key),
                golden.get(key),
                depth=depth + 1,
            )
        ]
        return [_field_difference(field_path, current, golden, diff_type, child_differences)] + (
            child_differences
        )
    if diff_type == "list" and depth < 5 and isinstance(current, list) and isinstance(golden, list):
        child_differences = [
            child
            for index in range(max(len(current), len(golden)))
            for child in _diff_value(
                f"{field_path}[{index}]",
                current[index] if index < len(current) else None,
                golden[index] if index < len(golden) else None,
                depth=depth + 1,
            )
        ]
        return [_field_difference(field_path, current, golden, diff_type, child_differences)] + (
            child_differences
        )
    return [_field_difference(field_path, current, golden, diff_type, [])]


def _field_difference(
    field_path: str,
    current: Any,
    golden: Any,
    diff_type: FieldDiffType,
    child_differences: list[FieldDifference],
) -> FieldDifference:
    if child_differences:
        score = sum(item.score for item in child_differences) / len(child_differences)
    else:
        score = _score(current, golden, diff_type)
    return FieldDifference(
        field_path=field_path,
        type=diff_type,
        current_value=current,
        golden_value=golden,
        score=round(score, 4),
        changed=current != golden,
    )


def _diff_type(current: Any, golden: Any) -> FieldDiffType:
    sample = current if current is not None else golden
    if isinstance(sample, bool):
        return "bool"
    if isinstance(sample, str):
        return "text"
    if isinstance(sample, int | float):
        return "number"
    if isinstance(sample, list):
        return "list"
    if isinstance(sample, dict):
        return "dict"
    if sample is None:
        return "null"
    return "unknown"


def _score(current: Any, golden: Any, diff_type: FieldDiffType) -> float:
    if current == golden:
        return 1.0
    if diff_type == "text":
        return SequenceMatcher(None, str(golden or ""), str(current or "")).ratio()
    if diff_type == "number":
        try:
            current_number = float(current)
            golden_number = float(golden)
        except (TypeError, ValueError):
            return 0.0
        denominator = max(abs(current_number), abs(golden_number), 1.0)
        return max(0.0, 1.0 - (abs(current_number - golden_number) / denominator))
    if diff_type in {"bool", "null"}:
        return 0.0
    return 0.0
