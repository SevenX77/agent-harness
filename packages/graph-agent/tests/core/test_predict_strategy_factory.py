from __future__ import annotations

import json
from pathlib import Path

import pytest
from graph_agent.core._predict_internal.strategy import (
    BacktestStrategy,
    GoldenCaseStrategy,
    HeuristicStubStrategy,
    MockStrategy,
    OverrideStrategy,
    PredictMockStrategyError,
)


def _golden_payload() -> dict[str, object]:
    return {
        "inputs": {"topic": "predict"},
        "metadata": {
            "phase_name": "draft",
            "prompt_hash": "abc",
            "io_outputs_schema_hash": "def",
            "expected_path": ["draft", "finish"],
        },
        "expected_traces": {"draft": {"text": "golden"}},
    }


def test_from_param_none_returns_heuristic_strategy() -> None:
    strategy = MockStrategy.from_param(None)

    assert isinstance(strategy, HeuristicStubStrategy)
    assert strategy.has_phase("any-phase") is True
    assert strategy.get_phase_schema("missing") is None


def test_from_param_dict_returns_override_strategy() -> None:
    strategy = MockStrategy.from_param(
        {
            "draft": {"text": "manual"},
            "review": {"source": "copilot", "output": {"score": 1}},
        }
    )

    assert isinstance(strategy, OverrideStrategy)
    assert strategy.has_manual_override("draft") is True
    assert strategy.get_manual_override("draft") == {"text": "manual"}
    assert strategy.get_manual_source("draft") == "manual"
    assert strategy.get_manual_override("review") == {"score": 1}
    assert strategy.get_manual_source("review") == "copilot"


def test_from_param_path_loads_golden_case(tmp_path: Path) -> None:
    path = tmp_path / "case.golden.json"
    path.write_text(json.dumps(_golden_payload()), encoding="utf-8")

    strategy = MockStrategy.from_param(path)

    assert isinstance(strategy, GoldenCaseStrategy)
    assert strategy.has_golden_case("draft") is True
    assert strategy.get_golden_output("draft") == {"text": "golden"}
    assert strategy.expected_path == ["draft", "finish"]


def test_from_param_list_returns_backtest_strategy() -> None:
    strategy = MockStrategy.from_param([_golden_payload()])

    assert isinstance(strategy, BacktestStrategy)
    assert strategy.has_golden_case("draft") is True
    assert strategy.get_golden_output("draft") == {"text": "golden"}


def test_path_json_errors_are_wrapped_with_friendly_message(tmp_path: Path) -> None:
    path = tmp_path / "broken.golden.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(PredictMockStrategyError, match="Invalid golden case JSON"):
        MockStrategy.from_param(path)


def test_path_validation_errors_are_wrapped_with_friendly_message(tmp_path: Path) -> None:
    path = tmp_path / "bad.golden.json"
    path.write_text(json.dumps({"inputs": {}, "metadata": {}}), encoding="utf-8")

    with pytest.raises(PredictMockStrategyError, match="Invalid golden case schema"):
        MockStrategy.from_param(path)
