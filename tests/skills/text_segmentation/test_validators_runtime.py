"""Runtime smoke tests for skills/text-segmentation/script/validators.py.

Per PHASE2_DESIGN.md §6.2, every live SKILL validator needs a runtime
smoke test that simulates the CognitiveFlow schema branch real-data
flow. The text-segmentation SKILL exposes two validators on its
LLMPhases (both phases declare ``output_schema: script.models.Segment``):

* ``segment`` phase → ``validate_segmentation_structure``
* ``review`` phase → ``validate_final_format``

These tests build realistic Segment payloads (matching the Pydantic
schema field names + types) and verify happy-path acceptance plus a
couple of failure-mode rejections per validator.

The validator script has no Python package (``skills/text-segmentation``
contains a hyphen), so we load it via ``importlib.util.spec_from_file_location``
— the same pattern as ``tests/graph_agent/tools/test_md_to_json.py``.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ValidatorFn = Callable[[list[dict[str, Any]]], tuple[bool, list[str]]]


def _load_module() -> ModuleType:
    repo_root = Path(__file__).resolve().parents[3]
    validators_path = repo_root / "skills/text-segmentation/script/validators.py"
    spec = importlib.util.spec_from_file_location(
        "_text_segmentation_validators_under_test", validators_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def validators() -> ModuleType:
    return _load_module()


def _segment(
    *,
    index: int,
    type_: str = "B",
    start_line: int = 1,
    end_line: int = 5,
    content: str = "测试段落内容",
    confidence: float = 0.95,
    description: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Build one Segment dict matching ``script.models.Segment``.

    Mirrors the Pydantic field set so payloads look identical to what
    md_to_json hands the validator at runtime.
    """
    item: dict[str, Any] = {
        "index": index,
        "type": type_,
        "start_line": start_line,
        "end_line": end_line,
        "content": content,
        "confidence": confidence,
    }
    if description is not None:
        item["description"] = description
    if notes is not None:
        item["notes"] = notes
    return item


def _continuous_segments() -> list[dict[str, Any]]:
    return [
        _segment(index=1, type_="B", start_line=1, end_line=10),
        _segment(index=2, type_="A", start_line=11, end_line=20),
        _segment(index=3, type_="B", start_line=21, end_line=30),
    ]


class TestValidateSegmentationStructure:
    def test_accepts_continuous_segments(
        self, validators: ModuleType
    ) -> None:
        payload = _continuous_segments()

        is_valid, issues = validators.validate_segmentation_structure(payload)

        assert is_valid is True, issues
        assert issues == []

    def test_rejects_empty_payload(self, validators: ModuleType) -> None:
        is_valid, issues = validators.validate_segmentation_structure([])

        assert is_valid is False
        assert any("No segments" in issue for issue in issues)

    def test_rejects_invalid_type(self, validators: ModuleType) -> None:
        bad = _segment(index=1, type_="X")  # not A/B/C
        payload = [bad]

        is_valid, issues = validators.validate_segmentation_structure(payload)

        assert is_valid is False
        assert any("invalid type" in issue for issue in issues)

    def test_rejects_low_confidence(self, validators: ModuleType) -> None:
        bad = _segment(index=1, confidence=0.4)  # < 0.7 threshold
        payload = [bad]

        is_valid, issues = validators.validate_segmentation_structure(payload)

        assert is_valid is False
        assert any("confidence" in issue for issue in issues)

    def test_rejects_line_gap(self, validators: ModuleType) -> None:
        payload = [
            _segment(index=1, start_line=1, end_line=10),
            _segment(index=2, start_line=15, end_line=20),  # gap at 11-14
        ]

        is_valid, issues = validators.validate_segmentation_structure(payload)

        assert is_valid is False
        assert any("Gap" in issue for issue in issues)


class TestValidateFinalFormat:
    def test_accepts_well_formed_final_payload(
        self, validators: ModuleType
    ) -> None:
        payload = _continuous_segments()

        is_valid, issues = validators.validate_final_format(payload)

        assert is_valid is True, issues
        assert issues == []

    def test_rejects_empty_payload(self, validators: ModuleType) -> None:
        is_valid, issues = validators.validate_final_format([])

        assert is_valid is False
        assert any("No segments" in issue for issue in issues)

    def test_rejects_missing_required_field(
        self, validators: ModuleType
    ) -> None:
        bad = _segment(index=1)
        del bad["start_line"]  # required
        payload = [bad]

        is_valid, issues = validators.validate_final_format(payload)

        assert is_valid is False
        assert any("missing required field" in issue for issue in issues)

    def test_rejects_invalid_type(self, validators: ModuleType) -> None:
        bad = _segment(index=1, type_="Z")
        payload = [bad]

        is_valid, issues = validators.validate_final_format(payload)

        assert is_valid is False
        assert any("type must be" in issue for issue in issues)

    def test_rejects_inverted_line_range(
        self, validators: ModuleType
    ) -> None:
        bad = _segment(index=1, start_line=20, end_line=10)
        payload = [bad]

        is_valid, issues = validators.validate_final_format(payload)

        assert is_valid is False
        assert any("start_line" in issue and "end_line" in issue for issue in issues)

    def test_rejects_duplicate_indices(self, validators: ModuleType) -> None:
        payload = [
            _segment(index=1, start_line=1, end_line=10),
            _segment(index=1, start_line=11, end_line=20),  # dup index
        ]

        is_valid, issues = validators.validate_final_format(payload)

        assert is_valid is False
        assert any("Duplicate" in issue for issue in issues)
