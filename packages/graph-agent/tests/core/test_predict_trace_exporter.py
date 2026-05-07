from __future__ import annotations

from graph_agent.core._predict_internal.exporter import assemble_phase_record


def test_assemble_phase_record_outputs_business_fields_only() -> None:
    record = assemble_phase_record(
        {
            "name": "draft",
            "type": "llm",
            "inputs": {"topic": "mars"},
            "outputs": {"story": "hello", "usage": {"total_tokens": 999}},
            "metrics": {"input_tokens": 10, "total_cost": 4.2},
            "mocked_source": "manual",
            "internal_run_id": "ignored",
        }
    )

    assert record.phase_name == "draft"
    assert record.type == "llm"
    assert record.inputs == {"topic": "mars"}
    assert record.outputs == {"story": "hello"}
    assert record.mocked_source == "manual"
    assert set(record.model_dump()) == {
        "phase_name",
        "type",
        "inputs",
        "outputs",
        "mocked_source",
    }


def test_assemble_phase_record_keeps_logic_phase_without_mocked_source() -> None:
    record = assemble_phase_record(
        {
            "phase_name": "validate",
            "inputs": {"draft": "text"},
            "outputs": {"passed": True},
        }
    )

    assert record.phase_name == "validate"
    assert record.type == "logic"
    assert record.mocked_source is None


def test_assemble_phase_record_truncates_large_fields_with_marker() -> None:
    record = assemble_phase_record(
        {
            "phase_name": "draft",
            "type": "llm",
            "inputs": {},
            "outputs": {"text": "x" * 80},
            "mocked_source": "heuristic_stub",
        },
        max_field_chars=16,
    )

    assert record.outputs["text"] == "x" * 16
    assert record.outputs["truncated"] is True
    assert record.outputs["truncated_fields"] == ["text"]
