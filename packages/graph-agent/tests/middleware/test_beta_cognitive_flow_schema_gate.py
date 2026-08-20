"""RED-LIGHT tests for PR β CognitiveFlow SchemaEngine strict gate."""

from __future__ import annotations


def test_finish_task_rejects_business_data_that_violates_io_outputs_schema() -> None:
    """Unit: finish_task must reject payloads that do not match compiled io.outputs."""

    from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware

    validate_finish_task = CognitiveFlowMiddleware.validate_finish_task_with_schema_gate
    result = validate_finish_task(
        business_data_md='{"answer": 42}',
        output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        state={},
        phase_name="main",
    )

    assert result.accepted is False
    assert result.error_code == "[F-v3-agent-output-schema-invalid]"


def test_schema_failure_returns_llm_visible_tool_message_and_no_state_write() -> None:
    """Unit: schema failure must be retry feedback, not final business data."""

    from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware

    validate_finish_task = CognitiveFlowMiddleware.validate_finish_task_with_schema_gate
    result = validate_finish_task(
        business_data_md='{"answer": 42}',
        output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        state={},
        phase_name="main",
    )

    assert result.tool_message is not None
    assert result.tool_message.status == "error"
    assert result.final_write is None


def test_missing_compiled_output_schema_is_fatal_not_silent_pass() -> None:
    """Unit: finish_task validation cannot silently pass without compiled io.outputs."""

    from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware

    validate_finish_task = CognitiveFlowMiddleware.validate_finish_task_with_schema_gate
    result = validate_finish_task(
        business_data_md='{"answer": "ok"}',
        output_schema=None,
        state={},
        phase_name="main",
    )

    assert result.accepted is False
    assert result.error_code == "[F-v3-agent-output-schema-missing]"
