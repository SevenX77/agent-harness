"""Runtime smoke tests for skills/event-extraction/script/validators.py.

Per PHASE2_DESIGN.md §6.2, every live SKILL validator must have a
runtime smoke test that simulates the CognitiveFlow schema branch
real-data flow. The validator under test (``validate_event_extraction``)
is mounted on the ``settings`` LLMPhase of
``skills/event-extraction/SKILL.md`` with
``output_schema: script.models.Setting``.

After Phase 2 A1 the framework parses the LLM markdown into a
``list[dict[str, Any]]`` of Setting fields and hands that list to the
validator. These tests build realistic Setting payloads (matching the
Pydantic schema field names + types) and verify happy-path acceptance
plus a couple of failure-mode rejections.

The validator script has no Python package (``skills/event-extraction``
contains a hyphen), so we load it via ``importlib.util.spec_from_file_location``
— the same pattern as ``tests/graph_agent/tools/test_md_to_json.py``.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ValidatorFn = Callable[[list[dict[str, Any]]], tuple[bool, list[str]]]


def _load_validator() -> ValidatorFn:
    repo_root = Path(__file__).resolve().parents[3]
    validators_path = repo_root / "skills/event-extraction/script/validators.py"
    spec = importlib.util.spec_from_file_location(
        "_event_extraction_validators_under_test", validators_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_event_extraction  # type: ignore[no-any-return]


@pytest.fixture
def validate() -> ValidatorFn:
    return _load_validator()


def _good_setting(setting_id: str = "SET_001") -> dict[str, Any]:
    return {
        "setting_id": setting_id,
        "paragraph_indices": [3, 4, 5],
        "related_event_id": "EVT_001",
        "core_knowledge": (
            "诡异的弱点是火焰与高频电流，普通热武器对其无效。这是末日世界"
            "对战斗角色提出的核心硬约束，决定了主角必须囤积特殊弹药。"
        ),
    }


class TestHappyPath:
    def test_validator_accepts_list_of_well_formed_settings(
        self, validate: ValidatorFn
    ) -> None:
        payload = [_good_setting("SET_001"), _good_setting("SET_002")]

        is_valid, issues = validate(payload)

        assert is_valid is True, issues
        assert issues == []

    def test_validator_accepts_single_setting(self, validate: ValidatorFn) -> None:
        payload = [_good_setting("SET_007")]

        is_valid, issues = validate(payload)

        assert is_valid is True, issues
        assert issues == []


class TestFailPaths:
    def test_validator_rejects_empty_payload(self, validate: ValidatorFn) -> None:
        is_valid, issues = validate([])

        assert is_valid is False
        assert any("settings 为空" in issue for issue in issues)

    def test_validator_rejects_malformed_setting_id(
        self, validate: ValidatorFn
    ) -> None:
        bad = _good_setting()
        bad["setting_id"] = "world-rule-1"  # not SET_<digits>
        payload = [bad]

        is_valid, issues = validate(payload)

        assert is_valid is False
        assert any("SET_数字" in issue for issue in issues)

    def test_validator_rejects_duplicate_setting_ids(
        self, validate: ValidatorFn
    ) -> None:
        payload = [_good_setting("SET_001"), _good_setting("SET_001")]

        is_valid, issues = validate(payload)

        assert is_valid is False
        assert any("重复" in issue for issue in issues)

    def test_validator_rejects_empty_paragraph_indices(
        self, validate: ValidatorFn
    ) -> None:
        bad = _good_setting()
        bad["paragraph_indices"] = []
        payload = [bad]

        is_valid, issues = validate(payload)

        assert is_valid is False
        assert any("paragraph_indices" in issue for issue in issues)

    def test_validator_rejects_missing_related_event_id(
        self, validate: ValidatorFn
    ) -> None:
        bad = _good_setting()
        bad["related_event_id"] = ""
        payload = [bad]

        is_valid, issues = validate(payload)

        assert is_valid is False
        assert any("related_event_id" in issue for issue in issues)

    def test_validator_rejects_starvation_core_knowledge(
        self, validate: ValidatorFn
    ) -> None:
        bad = _good_setting()
        bad["core_knowledge"] = "太短"  # well below the 30-char floor
        payload = [bad]

        is_valid, issues = validate(payload)

        assert is_valid is False
        assert any("信息密度不足" in issue for issue in issues)

    def test_validator_rejects_overrun_core_knowledge(
        self, validate: ValidatorFn
    ) -> None:
        bad = _good_setting()
        bad["core_knowledge"] = "啰嗦" * 200  # 400 chars >> 200-char ceiling
        payload = [bad]

        is_valid, issues = validate(payload)

        assert is_valid is False
        assert any("应精炼" in issue for issue in issues)
