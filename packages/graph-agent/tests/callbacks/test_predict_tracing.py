from __future__ import annotations

import json
from pathlib import Path

from graph_agent.callbacks.events import LLMCallEvent, PhaseEndEvent, PhaseStartEvent
from graph_agent.core._predict_internal.tracing import (
    PredictTracingCallback,
    clear_mock_source_cache,
    record_mock_source,
)


def test_predict_chain_start_marks_root_metadata() -> None:
    callback = PredictTracingCallback()
    metadata: dict[str, object] = {"thread_id": "thread-1"}

    callback.on_chain_start(metadata=metadata)

    assert metadata["is_predict"] is True
    assert callback.root_metadata["is_predict"] is True
    assert callback.root_metadata["thread_id"] == "thread-1"


def test_predict_trace_summary_persists_root_metadata(tmp_path) -> None:
    callback = PredictTracingCallback()
    callback.on_chain_start(metadata={})

    trace_path = callback.save(tmp_path)

    trace = json.loads(Path(trace_path).read_text(encoding="utf-8"))
    assert trace["metadata"]["is_predict"] is True


def test_phase_end_backfills_mocked_source_from_interception_cache() -> None:
    clear_mock_source_cache()
    callback = PredictTracingCallback()

    callback.on_event(PhaseStartEvent(phase_name="draft", phase_execution_id="exec-1", context={"topic": "mars"}))
    record_mock_source("draft", "heuristic_stub")
    callback.on_event(
        PhaseEndEvent(
            phase_name="draft",
            phase_execution_id="exec-1",
            status="completed",
            context={"story": "stub"},
        )
    )

    phase = callback.phases[-1]
    assert phase["inputs"] == {"topic": "mars"}
    assert phase["outputs"] == {"story": "stub"}
    assert phase["mocked_source"] == "heuristic_stub"
    # A stubbed phase makes no call, so the phase's own tally stays at zero —
    # which is the tally every reader uses, not a zeroed copy handed along.
    assert phase["input_tokens"] == 0
    assert phase["output_tokens"] == 0
    assert phase["llm_calls"] == []


def test_phase_source_cache_is_consumed_after_backfill() -> None:
    clear_mock_source_cache()
    callback = PredictTracingCallback()

    callback.on_event(PhaseStartEvent(phase_name="draft", phase_execution_id="exec-1", context={}))
    record_mock_source("draft", "manual")
    callback.on_event(PhaseEndEvent(phase_name="draft", phase_execution_id="exec-1", status="completed", context={}))
    callback.on_event(PhaseStartEvent(phase_name="draft", phase_execution_id="exec-1", context={}))
    callback.on_event(PhaseEndEvent(phase_name="draft", phase_execution_id="exec-1", status="completed", context={}))

    assert callback.phases[0]["mocked_source"] == "manual"
    assert "mocked_source" not in callback.phases[1]


def test_predict_llm_call_forces_zero_usage() -> None:
    callback = PredictTracingCallback()

    callback.on_event(PhaseStartEvent(phase_name="draft", phase_execution_id="exec-1", context={}))
    callback.on_event(
        LLMCallEvent(
            step_id="step-1",
            phase_name="draft",
            input_tokens=123,
            output_tokens=456,
            response_data={"usage": {"total_cost": 9}},
        )
    )

    summary = callback.summary()
    assert summary["total_input_tokens"] == 0
    assert summary["total_output_tokens"] == 0
    assert callback.phases_in_progress[-1]["input_tokens"] == 0
    assert callback.phases_in_progress[-1]["output_tokens"] == 0
    assert callback.phases_in_progress[-1]["llm_calls"][0]["input_tokens"] == 0
    assert callback.phases_in_progress[-1]["llm_calls"][0]["output_tokens"] == 0
