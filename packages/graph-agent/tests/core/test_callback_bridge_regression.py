from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage

from graph_agent.core.callback_bridge import _extract_text_content, _HarnessCallbackBridge


def test_extract_text_content_handles_provider_block_lists() -> None:
    content = [
        "lead",
        {"type": "thinking", "text": "hidden"},
        {"type": "text", "text": "visible"},
        {"text": "fallback"},
        {"type": "text", "text": ""},
        {"type": "image", "text": "caption"},
        123,
    ]

    assert _extract_text_content(content) == "lead\nvisible\nfallback\ncaption"


def test_extract_text_content_handles_scalar_and_empty_values() -> None:
    assert _extract_text_content("plain text") == "plain text"
    assert _extract_text_content([]) == ""
    assert _extract_text_content(None) == ""
    assert _extract_text_content({"unexpected": "shape"}) == "{'unexpected': 'shape'}"


def test_extract_tokens_prefers_llm_output_token_usage() -> None:
    response = SimpleNamespace(
        llm_output={"token_usage": {"prompt_tokens": "11", "completion_tokens": "7"}},
        generations=[[SimpleNamespace(generation_info={"usage": {"prompt_tokens": 1}})]],
    )

    assert _HarnessCallbackBridge._extract_tokens(response) == (11, 7)


def test_extract_tokens_reads_generation_info_usage() -> None:
    response = SimpleNamespace(
        generations=[
            [
                SimpleNamespace(
                    generation_info={"usage": {"prompt_tokens": 5, "completion_tokens": 3}}
                )
            ]
        ]
    )

    assert _HarnessCallbackBridge._extract_tokens(response) == (5, 3)


def test_extract_tokens_reads_message_response_metadata_aliases() -> None:
    message = SimpleNamespace(
        response_metadata={"usage": {"input_tokens": 13, "output_tokens": 2}}
    )
    response = SimpleNamespace(generations=[[SimpleNamespace(message=message)]])

    assert _HarnessCallbackBridge._extract_tokens(response) == (13, 2)


def test_extract_response_data_preserves_actual_runtime_settings_metadata() -> None:
    actual_runtime_settings = {
        "max_output_tokens": {"value": 555, "source": "call_override"},
        "temperature": {
            "authored_value": 1.2,
            "provider_value": 0.6,
            "source": "call_override",
            "protocol": "anthropic_compatible",
        },
        "reasoning.enabled": {"value": True, "source": "call_override"},
    }
    message = AIMessage(
        content="ok",
        response_metadata={
            "actual_runtime_settings": actual_runtime_settings,
            "usage": {"input_tokens": 13, "output_tokens": 2},
        },
    )
    response = SimpleNamespace(
        llm_output={"model_name": "claude-sonnet-4-6"},
        generations=[[SimpleNamespace(message=message)]],
    )

    data = _HarnessCallbackBridge._extract_response_data(response)

    assert data["response_metadata"]["actual_runtime_settings"] == actual_runtime_settings


def test_extract_tokens_returns_zero_tuple_for_unknown_shapes() -> None:
    response = SimpleNamespace(llm_output={"token_usage": {}}, generations=[])

    assert _HarnessCallbackBridge._extract_tokens(response) == (0, 0)
