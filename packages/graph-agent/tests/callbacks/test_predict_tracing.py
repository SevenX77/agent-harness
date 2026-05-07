from __future__ import annotations

import json
from pathlib import Path

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

    callback.on_phase_start("draft", {"topic": "mars"})
    record_mock_source("draft", "heuristic_stub")
    callback.on_phase_end(
        "draft",
        {"story": "stub"},
        {"input_tokens": 41, "output_tokens": 19, "total_cost": 3.14},
    )

    phase = callback.phases[-1]
    assert phase["inputs"] == {"topic": "mars"}
    assert phase["outputs"] == {"story": "stub"}
    assert phase["mocked_source"] == "heuristic_stub"
    assert phase["metrics"]["input_tokens"] == 0
    assert phase["metrics"]["output_tokens"] == 0
    assert phase["metrics"]["total_cost"] == 0


def test_phase_source_cache_is_consumed_after_backfill() -> None:
    clear_mock_source_cache()
    callback = PredictTracingCallback()

    callback.on_phase_start("draft", {})
    record_mock_source("draft", "manual")
    callback.on_phase_end("draft", {}, {})
    callback.on_phase_start("draft", {})
    callback.on_phase_end("draft", {}, {})

    assert callback.phases[0]["mocked_source"] == "manual"
    assert "mocked_source" not in callback.phases[1]


def test_predict_llm_call_forces_zero_usage() -> None:
    callback = PredictTracingCallback()

    callback.on_phase_start("draft", {})
    callback.on_llm_call("draft", 123, 456, response_data={"usage": {"total_cost": 9}})

    summary = callback.summary()
    assert summary["total_input_tokens"] == 0
    assert summary["total_output_tokens"] == 0
    assert callback.phases_in_progress[-1]["input_tokens"] == 0
    assert callback.phases_in_progress[-1]["output_tokens"] == 0
    assert callback.phases_in_progress[-1]["llm_calls"][0]["input_tokens"] == 0
    assert callback.phases_in_progress[-1]["llm_calls"][0]["output_tokens"] == 0
