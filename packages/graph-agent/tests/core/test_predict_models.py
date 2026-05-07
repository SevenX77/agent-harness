from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core._predict_internal.models import (
    GoldenCase,
    HeuristicStub,
    PathDiff,
    PhaseRecord,
    PredictResult,
)
from graph_agent.core._predict_internal.strategy import MockLLMParam
from pydantic import ValidationError


def _golden_case() -> GoldenCase:
    return GoldenCase(
        inputs={"topic": "predict"},
        metadata={
            "phase_name": "draft",
            "prompt_hash": "abc123",
            "io_outputs_schema_hash": "def456",
        },
        expected_traces={"draft": {"text": "approved"}},
    )


def test_golden_case_json_round_trip() -> None:
    golden = _golden_case()

    restored = GoldenCase.model_validate_json(golden.model_dump_json())

    assert restored == golden
    assert restored.metadata["phase_name"] == "draft"
    assert restored.expected_traces["draft"] == {"text": "approved"}


def test_golden_case_missing_required_fields_fail_closed() -> None:
    with pytest.raises(ValidationError):
        GoldenCase.model_validate({"inputs": {}, "metadata": {}})


@pytest.mark.parametrize(
    "source",
    ["golden_case", "copilot", "heuristic_stub", "manual", None],
)
def test_phase_record_accepts_fixed_mocked_source_values(source: str | None) -> None:
    record = PhaseRecord(
        phase_name="draft",
        type="llm",
        inputs={"topic": "predict"},
        outputs={"text": "<mock_text>"},
        mocked_source=source,
    )

    assert record.mocked_source == source


def test_phase_record_rejects_unknown_mocked_source() -> None:
    with pytest.raises(ValidationError):
        PhaseRecord(
            phase_name="draft",
            type="llm",
            inputs={},
            outputs={},
            mocked_source="fixture",
        )


def test_predict_result_status_is_success_or_failed_only() -> None:
    phase = PhaseRecord(
        phase_name="draft",
        type="llm",
        inputs={},
        outputs={},
        mocked_source="heuristic_stub",
    )
    diff = PathDiff(
        expected_path=["start", "draft", "finish"],
        actual_path=["start", "finish"],
        missing=["draft"],
        order_mismatch=False,
    )

    result = PredictResult(status="failed", phases=[phase], path_diff=diff)

    assert result.status == "failed"
    assert result.path_diff == diff
    with pytest.raises(ValidationError):
        PredictResult(status="stale", phases=[phase])


def test_heuristic_stub_type_alias_is_plain_dict() -> None:
    stub: HeuristicStub = {"text": "<mock_data>"}

    assert stub["text"] == "<mock_data>"


def test_mock_llm_param_accepts_none_dict_path_and_golden_list(tmp_path: Path) -> None:
    golden = _golden_case()
    golden_path = tmp_path / "case.golden.json"

    assert MockLLMParam.validate_python(None) is None
    assert MockLLMParam.validate_python({"draft": {"text": "manual"}}) == {
        "draft": {"text": "manual"}
    }
    assert MockLLMParam.validate_python(golden_path) == golden_path
    assert MockLLMParam.validate_python([golden]) == [golden]


def test_mock_llm_param_rejects_invalid_list_payload() -> None:
    with pytest.raises(ValidationError):
        MockLLMParam.validate_python([{"inputs": {}, "metadata": {}}])
