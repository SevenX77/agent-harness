"""RED-LIGHT tests for PR β validator runtime signature."""

from __future__ import annotations

from typing import Any


def test_validator_receives_output_dict_state_slice_and_kwargs_after_schema_passes() -> None:
    """Unit: validator runtime must use γ0 signature, not the legacy list tuple API."""

    from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware

    calls: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []

    def validate(output: dict[str, Any], state_slice: dict[str, Any], **kwargs: Any) -> None:
        calls.append((output, state_slice, kwargs))

    invoke_validator = CognitiveFlowMiddleware.invoke_validator_with_contract
    result = invoke_validator(
        validator=validate,
        output={"answer": "ok"},
        state_slice={"inputs": {"question": "q"}},
        phase_name="main",
        attempt=2,
    )

    assert result.accepted is True
    assert calls == [
        (
            {"answer": "ok"},
            {"inputs": {"question": "q"}},
            {"phase_name": "main", "attempt": 2},
        )
    ]


def test_validator_return_none_accepts_finish_task_output() -> None:
    """Unit: None return means business validation passed."""

    from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware

    invoke_validator = CognitiveFlowMiddleware.invoke_validator_with_contract
    result = invoke_validator(
        validator=lambda output, state_slice, **kwargs: None,
        output={"answer": "ok"},
        state_slice={"inputs": {"question": "q"}},
        phase_name="main",
    )

    assert result.accepted is True
    assert result.feedback is None


def test_validator_return_dict_accepts_and_exposes_enriched_output() -> None:
    """Unit: dict return means validation passed with enriched/corrected output."""

    from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware

    invoke_validator = CognitiveFlowMiddleware.invoke_validator_with_contract
    dict_result = invoke_validator(
        validator=lambda output, state_slice, **kwargs: {"answer": "ok", "score": 1},
        output={"answer": "ok"},
        state_slice={"inputs": {"question": "q"}},
        phase_name="main",
    )

    assert dict_result.accepted is True
    assert dict_result.output == {"answer": "ok", "score": 1}
    assert dict_result.feedback is None


def test_validator_non_dict_or_exception_becomes_agent_validator_failed_feedback() -> None:
    """Unit: explicit contract failure must become [F-v3-agent-validator-failed] feedback."""

    from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware

    invoke_validator = CognitiveFlowMiddleware.invoke_validator_with_contract
    explicit_failure = invoke_validator(
        validator=lambda output, state_slice, **kwargs: False,
        output={"answer": "ok"},
        state_slice={"inputs": {"question": "q"}},
        phase_name="main",
    )

    def raises_validator(
        output: dict[str, Any], state_slice: dict[str, Any], **kwargs: Any
    ) -> None:
        raise ValueError("bad answer")

    exception_result = invoke_validator(
        validator=raises_validator,
        output={"answer": "ok"},
        state_slice={"inputs": {"question": "q"}},
        phase_name="main",
    )

    assert explicit_failure.accepted is False
    assert explicit_failure.error_code == "[F-v3-agent-validator-failed]"
    assert "false" in explicit_failure.feedback
    assert exception_result.accepted is False
    assert exception_result.error_code == "[F-v3-agent-validator-failed]"
    assert "bad answer" in exception_result.feedback
