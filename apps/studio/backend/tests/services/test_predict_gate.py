from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services.predict_gate import (
    has_passing_predict,
    last_predict_path_for,
    record_predict_pass,
    require_passing_predict,
)
from app.services.skills import resolve_skill_dir
from fastapi import HTTPException


def test_has_passing_predict_is_false_without_record(
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    assert has_passing_predict("text-segmentation") is False


def test_require_passing_predict_raises_run_requires_predict_without_record(
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    with pytest.raises(HTTPException) as excinfo:
        require_passing_predict("text-segmentation")
    detail = excinfo.value.detail
    assert isinstance(detail, dict)
    assert detail["error_code"] == "RUN_REQUIRES_PREDICT"
    assert detail["http_status"] == 409
    assert detail["details"]["skill_id"] == "text-segmentation"


def test_record_then_require_predict_pass_is_allowed(
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    skill_dir = resolve_skill_dir("text-segmentation")

    record_path = record_predict_pass(skill_dir, "text-segmentation", "predict-1")

    assert record_path == last_predict_path_for(skill_dir)
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["skill_id"] == "text-segmentation"
    assert payload["run_id"] == "predict-1"
    assert has_passing_predict("text-segmentation") is True
    # Should not raise now that a passing predict is on record.
    require_passing_predict("text-segmentation")


def test_corrupt_record_is_treated_as_no_pass(
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    skill_dir = resolve_skill_dir("text-segmentation")
    record_path = last_predict_path_for(skill_dir)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text("{not json", encoding="utf-8")

    assert has_passing_predict("text-segmentation") is False
