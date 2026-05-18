from __future__ import annotations

import pytest
from graph_agent.core.subagents import build_subagent_input_model, validate_subagent_tool_args


def _input_model() -> type:
    return build_subagent_input_model(
        "BeatInput",
        {
            "type": "object",
            "properties": {"scene_text": {"type": "string"}},
            "required": ["scene_text"],
        },
    )


def test_subagent_runtime_rejects_non_array_inputs() -> None:
    model = _input_model()

    result = validate_subagent_tool_args(
        tool_name="call_subagent_beat",
        subagent_name="beat",
        input_model=model,
        expected_schema=model.model_json_schema(),
        args={"inputs": {"scene_text": "x"}},
        retry_count=1,
    )

    assert not isinstance(result, list)
    payload = result.to_tool_result()
    assert payload["ok"] is False
    assert payload["error_type"] == "validation"
    assert payload["expected_schema"]["properties"]["scene_text"]["type"] == "string"
    assert payload["errors"][0]["loc"] == ["inputs"]


def test_subagent_runtime_rejects_invalid_item_schema() -> None:
    model = _input_model()

    result = validate_subagent_tool_args(
        tool_name="call_subagent_beat",
        subagent_name="beat",
        input_model=model,
        expected_schema=model.model_json_schema(),
        args={"inputs": [{"text": "wrong"}]},
        retry_count=1,
    )

    assert not isinstance(result, list)
    payload = result.to_tool_result()
    assert payload["retry_count"] == 1
    assert payload["errors"][0]["loc"] == ["inputs", 0, "scene_text"]


def test_subagent_runtime_accepts_valid_input_array() -> None:
    model = _input_model()

    result = validate_subagent_tool_args(
        tool_name="call_subagent_beat",
        subagent_name="beat",
        input_model=model,
        expected_schema=model.model_json_schema(),
        args={"inputs": [{"scene_text": "a"}, {"scene_text": "b"}]},
        retry_count=1,
    )

    assert isinstance(result, list)
    assert [item.model_dump() for item in result] == [{"scene_text": "a"}, {"scene_text": "b"}]


def test_subagent_runtime_fails_after_ten_schema_retries() -> None:
    model = _input_model()

    with pytest.raises(RuntimeError, match="retry_count=11"):
        validate_subagent_tool_args(
            tool_name="call_subagent_beat",
            subagent_name="beat",
            input_model=model,
            expected_schema=model.model_json_schema(),
            args={"inputs": []},
            retry_count=11,
        )
