"""Tests for reasoning_content LangChain monkey patches."""
from __future__ import annotations

import langchain_openai.chat_models.base as lc_openai_base
from graph_agent.models import reasoning_patch
from graph_agent.models.reasoning_patch import _apply_reasoning_content_patch
from langchain_core.messages import AIMessage, HumanMessage


def test_message_to_dict_echoes_ai_reasoning_content() -> None:
    _apply_reasoning_content_patch()
    message = AIMessage(
        content="answer",
        additional_kwargs={"reasoning_content": "hidden reasoning trace"},
    )

    payload = lc_openai_base._convert_message_to_dict(message)

    assert payload["role"] == "assistant"
    assert payload["content"] == "answer"
    assert payload["reasoning_content"] == "hidden reasoning trace"


def test_message_to_dict_does_not_add_reasoning_content_to_non_ai() -> None:
    _apply_reasoning_content_patch()
    message = HumanMessage(
        content="question",
        additional_kwargs={"reasoning_content": "should not be echoed"},
    )

    payload = lc_openai_base._convert_message_to_dict(message)

    assert payload["role"] == "user"
    assert "reasoning_content" not in payload


def test_apply_reasoning_patch_wraps_receive_and_send_converters() -> None:
    reasoning_patch._reasoning_patch_applied = False

    _apply_reasoning_content_patch()
    received = lc_openai_base._convert_dict_to_message(
        {"role": "assistant", "content": "answer", "reasoning_content": "trace"}
    )
    sent = lc_openai_base._convert_message_to_dict(
        AIMessage(content="answer", additional_kwargs={"reasoning_content": "trace"})
    )

    assert isinstance(received, AIMessage)
    assert received.additional_kwargs["reasoning_content"] == "trace"
    assert sent["reasoning_content"] == "trace"


def test_apply_reasoning_patch_is_idempotent() -> None:
    _apply_reasoning_content_patch()

    assert reasoning_patch._reasoning_patch_applied is True
