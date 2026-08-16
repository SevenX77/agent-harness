from __future__ import annotations

import json
from pathlib import Path

from graph_agent.callbacks.events import PhaseEndEvent, PhaseStartEvent
from graph_agent.core._predict_internal.models import GoldenCase
from graph_agent.core._predict_internal.strategy import (
    BacktestStrategy,
    GoldenCaseStrategy,
    HeuristicStubStrategy,
    MockStrategy,
    OverrideStrategy,
)
from graph_agent.core._predict_internal.tracing import (
    PredictMockSourceCache,
    PredictTracingCallback,
)


def test_p2_strategy_uses_heuristic_stub_source() -> None:
    strategy = MockStrategy.from_param(None)

    assert isinstance(strategy, HeuristicStubStrategy)
    assert strategy.has_phase("draft") is True


def test_p1_strategy_uses_dict_override_source() -> None:
    manual = MockStrategy.from_param({"draft": {"text": "manual draft"}})
    copilot = MockStrategy.from_param(
        {"draft": {"source": "copilot", "output": {"text": "copilot draft"}}}
    )

    assert isinstance(manual, OverrideStrategy)
    assert manual.get_manual_source("draft") == "manual"
    assert manual.get_manual_override("draft") == {"text": "manual draft"}
    assert isinstance(copilot, OverrideStrategy)
    assert copilot.get_manual_source("draft") == "copilot"
    assert copilot.get_manual_override("draft") == {"text": "copilot draft"}


def test_p0_strategy_loads_golden_case_source(tmp_path: Path) -> None:
    golden_path = _write_golden_case(tmp_path, expected_path=["prepare", "draft"])

    strategy = MockStrategy.from_param(golden_path)

    assert isinstance(strategy, GoldenCaseStrategy)
    assert strategy.expected_path == ["prepare", "draft"]
    assert strategy.get_golden_output("draft") == {"text": "golden draft"}


def test_backtest_strategy_merges_golden_cases() -> None:
    cases = [
        GoldenCase(
            inputs={},
            metadata={"expected_path": ["draft"]},
            expected_traces={"draft": {"text": "a"}},
        ),
        GoldenCase(inputs={}, metadata={}, expected_traces={"review": {"ok": True}}),
    ]

    strategy = MockStrategy.from_param(cases)

    assert isinstance(strategy, BacktestStrategy)
    assert strategy.get_golden_output("draft") == {"text": "a"}
    assert strategy.get_golden_output("review") == {"ok": True}


def test_predict_tracing_consumes_mock_source_cache() -> None:
    source_cache = PredictMockSourceCache()
    callback = PredictTracingCallback(source_cache=source_cache)
    callback.on_chain_start(metadata={})
    callback.on_event(PhaseStartEvent(phase_name="draft", phase_execution_id="exec-1", context={"topic": "mars"}))
    source_cache.record("draft", "heuristic_stub")

    callback.on_event(
        PhaseEndEvent(
            phase_name="draft",
            phase_execution_id="exec-1",
            context={"draft": {"text": "stub"}},
            metrics={"total_input_tokens": 123},
        )
    )

    assert callback.root_metadata["is_predict"] is True
    assert callback.phases[0]["mocked_source"] == "heuristic_stub"
    assert source_cache.get("draft") is None


def _write_golden_case(tmp_path: Path, *, expected_path: list[str]) -> Path:
    path = tmp_path / "case.golden.json"
    path.write_text(
        json.dumps(
            {
                "inputs": {"topic": "mars"},
                "metadata": {
                    "phase_name": "draft",
                    "prompt_hash": "old-prompt",
                    "io_outputs_schema_hash": "old-schema",
                    "expected_path": expected_path,
                },
                "expected_traces": {"draft": {"text": "golden draft"}},
            }
        ),
        encoding="utf-8",
    )
    return path
